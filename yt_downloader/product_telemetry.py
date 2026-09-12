from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, cast, get_args

from .analytics_consent import analytics_allowed
from .cloud_funnel import (
    InstallationIdentityError,
    installation_platform,
    load_or_create_installation_state,
)
from .failure_diagnostics import (
    FAILURE_REASONS,
    FailureDiagnostic,
    validate_failure_detail,
)
from .heycatch_telemetry import record_product_event as record_heycatch_event
from .history import application_data_dir
from .private_files import write_private_bytes
from .telemetry_credentials import RejectedTelemetryEvent, TelemetryCredentialOwner
from .telemetry_features import (
    FEATURE_ACTIONS,
    attempt_identifier,
    time_bucket,
    validate_dimensions,
)
from .telemetry_policy import preview_telemetry_allowed, telemetry_collection_allowed
from .telemetry_transport import telemetry_urlopen

PRODUCT_TELEMETRY_ENDPOINT = "https://getvodforge.com/api/telemetry/events"
PRODUCT_TELEMETRY_SCHEMA_VERSION = 2
PRODUCT_TELEMETRY_STATE_VERSION = 1
PRODUCT_TELEMETRY_STATE_FILENAME = "product-telemetry.json"
MAX_OUTBOX_EVENTS = 256
MAX_STATE_BYTES = 512 * 1024
NETWORK_TIMEOUT_SECONDS = 4.0

ProductEventName = Literal[
    "app_opened",
    "run_started",
    "run_completed",
    "run_failed",
    "run_stopped",
    "playback_started",
    "local_conversion_completed",
    "media_exported",
    "run_queued",
    "run_dequeued",
    "run_skipped",
    "local_conversion_started",
    "local_conversion_failed",
    "local_conversion_stopped",
    "feature_used",
]
RunKind = Literal["youtube", "local_audio_video"]
OutputKind = Literal["mp4", "mp3", "original"]
ReleaseChannel = Literal["production", "development", "test"]

PRODUCT_EVENT_NAMES = frozenset(get_args(ProductEventName))
_EVENT_NAMES = PRODUCT_EVENT_NAMES
_RUN_KINDS = {"youtube", "local_audio_video"}
_OUTPUT_KINDS = {"mp4", "mp3", "original"}
_RELEASE_CHANNELS = {"production", "development", "test"}
_PLATFORMS = {"macos", "windows", "linux", "unknown"}


def product_output_kind(value: str) -> OutputKind | None:
    """Normalize only known product output labels; never send arbitrary text."""
    normalized = "original" if value.lower() == "original audio" else value.lower()
    return cast(OutputKind, normalized) if normalized in _OUTPUT_KINDS else None


@dataclass(frozen=True, slots=True)
class ProductTelemetryEvent:
    event_id: str
    install_id: str
    event_name: ProductEventName
    occurred_at: str
    app_version: str
    platform: str
    release_channel: ReleaseChannel
    schema_version: int = PRODUCT_TELEMETRY_SCHEMA_VERSION
    run_kind: RunKind | None = None
    output_type: OutputKind | None = None
    failure_reason: str | None = None
    failure_detail: FailureDiagnostic | None = None
    attempt_id: str | None = None
    retry_of: str | None = None
    feature: str | None = None
    action: str | None = None
    dimensions: dict[str, str] = field(default_factory=dict)
    d1_delivered: bool = False
    heycatch_delivered: bool = False

    def public_payload(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "install_id": self.install_id,
            "event_name": self.event_name,
            "occurred_at": self.occurred_at,
            "app_version": self.app_version,
            "platform": self.platform,
            "release_channel": self.release_channel,
            "schema_version": self.schema_version,
            **(
                {
                    "attempt_id": self.attempt_id,
                    "retry_of": self.retry_of,
                    "feature": self.feature,
                    "action": self.action,
                    "dimensions": dict(self.dimensions),
                }
                if self.schema_version == 2
                else {}
            ),
            "run_kind": self.run_kind,
            "output_type": self.output_type,
            **(
                {"failure_reason": self.failure_reason or "unknown"}
                if self.event_name == "run_failed"
                else {}
            ),
            **(
                {"failure_detail": self.failure_detail.payload()}
                if self.event_name == "run_failed" and self.failure_detail
                else {}
            ),
        }


def product_telemetry_path(**kwargs: Any) -> Path:
    return application_data_dir(**kwargs) / PRODUCT_TELEMETRY_STATE_FILENAME


def release_channel(
    app_version: str, *, environment: Mapping[str, str] = os.environ
) -> ReleaseChannel:
    explicit = str(environment.get("VODFORGE_TELEMETRY_CHANNEL") or "").strip().lower()
    if explicit in _RELEASE_CHANNELS:
        return explicit  # type: ignore[return-value]
    version = str(app_version).strip().lower()
    return (
        "production"
        if version and all(part.isdigit() for part in version.split("."))
        else "development"
    )


def _valid_uuid(value: Any, *, version: int | None = None) -> str:
    parsed = uuid.UUID(str(value).strip())
    if version is not None and parsed.version != version:
        raise ValueError("unexpected UUID version")
    return str(parsed)


def _parse_event(value: Any) -> ProductTelemetryEvent:
    if not isinstance(value, dict):
        raise TypeError("telemetry event is not an object")
    event_name = str(value.get("event_name") or "")
    run_kind = value.get("run_kind")
    output_type = value.get("output_type")
    failure_reason = value.get("failure_reason")
    detail = value.get("failure_detail")
    if detail is not None and (
        not isinstance(detail, dict) or event_name != "run_failed"
    ):
        raise ValueError("invalid failure detail")
    if failure_reason is not None and (
        failure_reason not in FAILURE_REASONS or event_name != "run_failed"
    ):
        raise ValueError("invalid failure reason")
    feature, action = value.get("feature"), value.get("action")
    if event_name == "feature_used":
        if feature not in FEATURE_ACTIONS or action not in FEATURE_ACTIONS[feature]:
            raise ValueError("invalid feature action")
    elif feature is not None or action is not None:
        raise ValueError("unexpected feature action")
    if value.get("retry_of") and (
        not value.get("attempt_id") or value["retry_of"] == value["attempt_id"]
    ):
        raise ValueError("invalid retry relationship")
    channel = str(value.get("release_channel") or "")
    if event_name not in _EVENT_NAMES:
        raise ValueError("telemetry event name is invalid")
    if run_kind is not None and run_kind not in _RUN_KINDS:
        raise ValueError("telemetry run kind is invalid")
    if output_type is not None and output_type not in _OUTPUT_KINDS:
        raise ValueError("telemetry output type is invalid")
    if channel not in _RELEASE_CHANNELS:
        raise ValueError("telemetry release channel is invalid")
    app_version = str(value.get("app_version") or "").strip()
    platform = str(value.get("platform") or "").strip()
    if not app_version or len(app_version) > 64:
        raise ValueError("telemetry app version is invalid")
    if platform not in _PLATFORMS:
        raise ValueError("telemetry platform is invalid")
    if value.get("schema_version") not in (1, 2):
        raise ValueError("telemetry schema version is invalid")
    occurred_at = str(value.get("occurred_at") or "")
    datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
    return ProductTelemetryEvent(
        event_id=_valid_uuid(value.get("event_id")),
        install_id=_valid_uuid(value.get("install_id"), version=4),
        event_name=cast(ProductEventName, event_name),
        occurred_at=occurred_at,
        app_version=app_version,
        platform=platform,
        release_channel=cast(ReleaseChannel, channel),
        schema_version=value["schema_version"],
        attempt_id=_valid_uuid(value["attempt_id"])
        if value.get("attempt_id")
        else None,
        retry_of=_valid_uuid(value["retry_of"]) if value.get("retry_of") else None,
        feature=value.get("feature"),
        action=value.get("action"),
        dimensions=validate_dimensions(value.get("dimensions")),
        run_kind=cast(RunKind | None, run_kind),
        output_type=cast(OutputKind | None, output_type),
        failure_reason=failure_reason,
        failure_detail=validate_failure_detail(detail) if detail is not None else None,
        d1_delivered=value.get("d1_delivered") is True,
        heycatch_delivered=value.get("heycatch_delivered") is True,
    )


def _load_outbox(path: Path) -> list[ProductTelemetryEvent]:
    if not path.exists():
        return []
    if path.stat().st_size > MAX_STATE_BYTES:
        raise ValueError("product telemetry outbox is unexpectedly large")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != PRODUCT_TELEMETRY_STATE_VERSION
    ):
        raise ValueError("product telemetry outbox schema is invalid")
    raw_events = payload.get("events")
    if not isinstance(raw_events, list) or len(raw_events) > MAX_OUTBOX_EVENTS:
        raise ValueError("product telemetry outbox events are invalid")
    return [_parse_event(item) for item in raw_events]


def _save_outbox(path: Path, events: list[ProductTelemetryEvent]) -> None:
    encoded = json.dumps(
        {
            "schema_version": PRODUCT_TELEMETRY_STATE_VERSION,
            "events": [asdict(event) for event in events],
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if len(encoded) > MAX_STATE_BYTES:
        raise ValueError("product telemetry outbox exceeds its safe size")
    if not events:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_private_bytes(path, encoded)


def _post_d1_event(
    event: ProductTelemetryEvent,
    *,
    opener: Callable[..., Any] = telemetry_urlopen,
) -> bool:
    if not telemetry_collection_allowed():
        return False
    request = urllib.request.Request(
        PRODUCT_TELEMETRY_ENDPOINT,
        data=json.dumps(
            {"events": [event.public_payload()]}, separators=(",", ":")
        ).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "VODForge-Product-Telemetry/1",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
            status = int(getattr(response, "status", 200))
            body = response.read(4097)
        if not 200 <= status < 300 or len(body) > 4096:
            return False
        result = json.loads(body.decode("utf-8"))
        return (
            isinstance(result, dict)
            and result.get("ok") is True
            and int(result.get("accepted") or 0) >= 1
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return False


class ProductTelemetryOwner:
    """Own privacy gating, immutable events, delivery, and the bounded retry outbox."""

    def __init__(
        self,
        *,
        state_path: Path,
        installation_state_path: Path,
        app_version: str,
        platform_name: str | None = None,
        enabled: bool = True,
        d1_recorder: Callable[[ProductTelemetryEvent], bool] = _post_d1_event,
        heycatch_recorder: Callable[..., bool] = record_heycatch_event,
        diagnostic: Callable[[str], None] | None = None,
        session_id: str | None = None,
    ) -> None:
        self._state_path = state_path
        self._installation_state_path = installation_state_path
        self._app_version = str(app_version)
        self._platform = installation_platform(platform_name)
        self._release_channel = release_channel(app_version)
        self._enabled = bool(enabled)
        credential_owner = TelemetryCredentialOwner(installation_state_path.parent)
        self._d1_recorder = (
            (lambda event: credential_owner.event(event.public_payload()))
            if d1_recorder is _post_d1_event
            else d1_recorder
        )
        self._heycatch_recorder = heycatch_recorder
        self._diagnostic = diagnostic or (lambda _message: None)
        self._session_id = _valid_uuid(session_id or uuid.uuid4())
        self._recorded_dedupe_ids: set[str] = set()
        self._attempt_started: dict[str, float] = {}
        self._attempt_queued: dict[str, float] = {}
        self._feature_observed: set[tuple[str, str]] = set()
        self._lock = threading.RLock()
        self._worker: threading.Thread | None = None
        self._flush_requested = False

    def _permitted(self) -> tuple[bool, str | None]:
        if not telemetry_collection_allowed() or not self._enabled:
            return False, None
        try:
            state = load_or_create_installation_state(self._installation_state_path)
        except (InstallationIdentityError, OSError):
            return False, None
        return analytics_allowed(self._installation_state_path.parent), state.install_id

    def permitted(self) -> bool:
        """Expose the current privacy decision for detached operation handoffs."""
        return self._permitted()[0]

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)
            if not self._enabled:
                self._feature_observed.clear()
                self._attempt_started.clear()
                self._attempt_queued.clear()
                try:
                    _save_outbox(self._state_path, [])
                except OSError as exc:
                    self._diagnostic(
                        f"product telemetry outbox could not be cleared: {type(exc).__name__}"
                    )
                return
        self.flush_async()

    def record(
        self,
        event_name: ProductEventName,
        *,
        dedupe_key: str | None = None,
        run_kind: RunKind | None = None,
        output_type: OutputKind | None = None,
        failure_reason: str | None = None,
        failure_detail: dict[str, Any] | None = None,
        attempt_key: str | None = None,
        retry_key: str | None = None,
        feature: str | None = None,
        action: str | None = None,
        dimensions: Mapping[str, str] | None = None,
    ) -> bool:
        clean_dimensions = validate_dimensions(dimensions)
        if event_name == "feature_used":
            if feature not in FEATURE_ACTIONS or action not in FEATURE_ACTIONS[feature]:
                raise ValueError("unsupported telemetry feature action")
        elif feature is not None or action is not None:
            raise ValueError("unexpected telemetry feature action")
        if retry_key is not None and (attempt_key is None or retry_key == attempt_key):
            raise ValueError("invalid telemetry retry relationship")
        if event_name not in _EVENT_NAMES:
            raise ValueError("unsupported product telemetry event")
        if failure_detail is not None and event_name != "run_failed":
            raise ValueError("unexpected failure detail")
        detail = (
            validate_failure_detail(failure_detail)
            if failure_detail is not None
            else None
        )
        if failure_reason is not None and (
            failure_reason not in FAILURE_REASONS or event_name != "run_failed"
        ):
            raise ValueError("unsupported failure reason")
        if run_kind is not None and run_kind not in _RUN_KINDS:
            raise ValueError("unsupported product telemetry run kind")
        if output_type is not None and output_type not in _OUTPUT_KINDS:
            raise ValueError("unsupported product telemetry output type")
        permitted, install_id = self._permitted()
        if not permitted or install_id is None:
            return False
        now = time.monotonic()
        with self._lock:
            if attempt_key:
                if (
                    event_name == "run_queued"
                    and len(self._attempt_queued) < MAX_OUTBOX_EVENTS
                ):
                    self._attempt_queued.setdefault(attempt_key, now)
                if event_name in {"run_started", "local_conversion_started"}:
                    if len(self._attempt_started) < MAX_OUTBOX_EVENTS:
                        self._attempt_started.setdefault(attempt_key, now)
                    queued = self._attempt_queued.pop(attempt_key, None)
                    if queued is not None:
                        clean_dimensions["wait_bucket"] = time_bucket(now - queued)
                elif event_name in {
                    "run_completed",
                    "run_failed",
                    "run_stopped",
                    "local_conversion_completed",
                    "local_conversion_failed",
                    "local_conversion_stopped",
                }:
                    started = self._attempt_started.pop(attempt_key, None)
                    if started is not None:
                        clean_dimensions["processing_bucket"] = time_bucket(
                            now - started
                        )
                elif event_name == "run_dequeued":
                    self._attempt_queued.pop(attempt_key, None)
        identity = dedupe_key or str(uuid.uuid4())
        event_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"vodforge:product:{install_id}:{event_name}:{identity}",
            )
        )
        event = ProductTelemetryEvent(
            event_id=event_id,
            install_id=install_id,
            event_name=event_name,
            occurred_at=datetime.now(timezone.utc).isoformat(),
            app_version=self._app_version,
            platform=self._platform,
            release_channel=self._release_channel,
            run_kind=run_kind,
            output_type=output_type,
            failure_reason=(failure_reason or "unknown")
            if event_name == "run_failed"
            else None,
            failure_detail=detail,
            attempt_id=attempt_identifier(install_id, attempt_key)
            if attempt_key
            else None,
            retry_of=attempt_identifier(install_id, retry_key) if retry_key else None,
            feature=feature,
            action=action,
            dimensions=clean_dimensions,
        )
        with self._lock:
            if dedupe_key is not None and event_id in self._recorded_dedupe_ids:
                self.flush_async()
                return True
            try:
                events = _load_outbox(self._state_path)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                self._diagnostic(
                    f"product telemetry outbox could not be loaded: {type(exc).__name__}"
                )
                return False
            if any(candidate.event_id == event.event_id for candidate in events):
                if dedupe_key is not None:
                    self._recorded_dedupe_ids.add(event_id)
                self.flush_async()
                return True
            if len(events) >= MAX_OUTBOX_EVENTS:
                self._diagnostic(
                    "product telemetry outbox is full; event was not retained"
                )
                return False
            try:
                _save_outbox(self._state_path, [*events, event])
            except (OSError, ValueError) as exc:
                self._diagnostic(
                    f"product telemetry event could not be retained: {type(exc).__name__}"
                )
                return False
            if dedupe_key is not None:
                # Delivery removes the outbox row, but repeated callbacks must
                # not recreate the same ID with a different timestamp.
                self._recorded_dedupe_ids.add(event_id)
        self.flush_async()
        return True

    def record_feature(
        self, feature: str, action: str, *, dimensions: Mapping[str, str] | None = None
    ) -> bool:
        """Record engagement once per session/action; avoid text-entry event floods."""
        if not self._permitted()[0]:
            return False
        key = (feature, action)
        with self._lock:
            if feature != "updater" and key in self._feature_observed:
                self.flush_async()
                return True
            accepted = self.record(
                "feature_used", feature=feature, action=action, dimensions=dimensions
            )
            if accepted:
                self._feature_observed.add(key)
            return accepted

    def record_app_opened(self) -> bool:
        return self.record("app_opened", dedupe_key=self._session_id)

    def flush_async(self) -> None:
        with self._lock:
            if not self._enabled:
                return
            if self._worker is not None and self._worker.is_alive():
                self._flush_requested = True
                return
            self._flush_requested = False
            self._worker = threading.Thread(
                target=self._flush_worker,
                name="vodforge-product-telemetry",
                daemon=True,
            )
            self._worker.start()

    def _flush_worker(self) -> None:
        try:
            while True:
                self._flush()
                with self._lock:
                    if not self._flush_requested:
                        # Retire under the same lock used by producers: a new
                        # request must either wake this worker or start another.
                        self._worker = None
                        return
                    self._flush_requested = False
        finally:
            with self._lock:
                if self._worker is threading.current_thread():
                    self._worker = None

    def _flush(self) -> None:
        while True:
            permitted, _install_id = self._permitted()
            if not permitted:
                return
            with self._lock:
                try:
                    events = _load_outbox(self._state_path)
                except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                    self._diagnostic(
                        f"product telemetry outbox could not be loaded: {type(exc).__name__}"
                    )
                    return
                if not events:
                    return
                event = events[0]
                # Privacy retention matches server acceptance. Expiration is a
                # local discard, never a fabricated delivery acknowledgement.
                if (
                    datetime.now(timezone.utc)
                    - datetime.fromisoformat(event.occurred_at.replace("Z", "+00:00"))
                ).total_seconds() > 30 * 86400:
                    _save_outbox(self._state_path, events[1:])
                    self._diagnostic("expired telemetry event discarded after 30 days")
                    continue
            try:
                d1_delivered = event.d1_delivered or self._d1_recorder(event)
            except RejectedTelemetryEvent:
                with self._lock:
                    latest = _load_outbox(self._state_path)
                    _save_outbox(
                        self._state_path,
                        [item for item in latest if item.event_id != event.event_id],
                    )
                self._diagnostic(
                    "permanently rejected telemetry event discarded; not delivered"
                )
                continue
            if not self._permitted()[0]:
                return
            heycatch_delivered = event.heycatch_delivered or self._heycatch_recorder(
                event.install_id,
                event_name=event.event_name,
                event_id=event.event_id,
                app_version=event.app_version,
                platform=event.platform,
                release_channel=event.release_channel,
                run_kind=event.run_kind,
                output_type=event.output_type,
                dimensions=event.dimensions,
                attempt_id=event.attempt_id,
                retry_of=event.retry_of,
                feature=event.feature,
                action=event.action,
                schema_version=event.schema_version,
            )
            updated = replace(
                event,
                d1_delivered=d1_delivered,
                heycatch_delivered=heycatch_delivered,
            )
            with self._lock:
                latest = _load_outbox(self._state_path)
                if not latest or latest[0].event_id != event.event_id:
                    continue
                delivery_complete = d1_delivered and (
                    heycatch_delivered or preview_telemetry_allowed()
                )
                remaining = latest[1:] if delivery_complete else [updated, *latest[1:]]
                _save_outbox(self._state_path, remaining)
            if not delivery_complete:
                return

    def shutdown(self, timeout_seconds: float = 1.0) -> bool:
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=max(0.0, timeout_seconds))
        return worker is None or not worker.is_alive()
