from __future__ import annotations

import json
import os
import threading
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, cast

from .cloud_funnel import (
    InstallationIdentityError,
    installation_platform,
    load_or_create_installation_state,
)
from .heycatch_telemetry import record_product_event as record_heycatch_event
from .history import application_data_dir
from .private_files import write_private_bytes

PRODUCT_TELEMETRY_ENDPOINT = "https://getvodforge.com/api/telemetry/events"
PRODUCT_TELEMETRY_SCHEMA_VERSION = 1
PRODUCT_TELEMETRY_STATE_VERSION = 1
PRODUCT_TELEMETRY_STATE_FILENAME = "product-telemetry.json"
MAX_OUTBOX_EVENTS = 256
MAX_STATE_BYTES = 128 * 1024
NETWORK_TIMEOUT_SECONDS = 4.0

ProductEventName = Literal[
    "app_opened",
    "run_started",
    "run_completed",
    "run_failed",
    "run_stopped",
    "playback_started",
    "local_conversion_completed",
]
RunKind = Literal["youtube", "local_audio_video"]
OutputKind = Literal["mp4", "mp3"]
ReleaseChannel = Literal["production", "development", "test"]

_EVENT_NAMES = {
    "app_opened",
    "run_started",
    "run_completed",
    "run_failed",
    "run_stopped",
    "playback_started",
    "local_conversion_completed",
}
_RUN_KINDS = {"youtube", "local_audio_video"}
_OUTPUT_KINDS = {"mp4", "mp3"}
_RELEASE_CHANNELS = {"production", "development", "test"}
_PLATFORMS = {"macos", "windows", "linux", "unknown"}


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
            "run_kind": self.run_kind,
            "output_type": self.output_type,
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
    if value.get("schema_version") != PRODUCT_TELEMETRY_SCHEMA_VERSION:
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
        schema_version=PRODUCT_TELEMETRY_SCHEMA_VERSION,
        run_kind=cast(RunKind | None, run_kind),
        output_type=cast(OutputKind | None, output_type),
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
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> bool:
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
        self._d1_recorder = d1_recorder
        self._heycatch_recorder = heycatch_recorder
        self._diagnostic = diagnostic or (lambda _message: None)
        self._session_id = _valid_uuid(session_id or uuid.uuid4())
        self._lock = threading.RLock()
        self._worker: threading.Thread | None = None

    def _permitted(self) -> tuple[bool, str | None]:
        if not self._enabled:
            return False, None
        try:
            state = load_or_create_installation_state(self._installation_state_path)
        except (InstallationIdentityError, OSError):
            return False, None
        return state.product_telemetry_allowed, state.install_id

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)
            if not self._enabled:
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
    ) -> bool:
        if event_name not in _EVENT_NAMES:
            raise ValueError("unsupported product telemetry event")
        if run_kind is not None and run_kind not in _RUN_KINDS:
            raise ValueError("unsupported product telemetry run kind")
        if output_type is not None and output_type not in _OUTPUT_KINDS:
            raise ValueError("unsupported product telemetry output type")
        permitted, install_id = self._permitted()
        if not permitted or install_id is None:
            return False
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
        )
        with self._lock:
            try:
                events = _load_outbox(self._state_path)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                self._diagnostic(
                    f"product telemetry outbox could not be loaded: {type(exc).__name__}"
                )
                return False
            if any(candidate.event_id == event.event_id for candidate in events):
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
        self.flush_async()
        return True

    def record_app_opened(self) -> bool:
        return self.record("app_opened", dedupe_key=self._session_id)

    def flush_async(self) -> None:
        with self._lock:
            if not self._enabled or (
                self._worker is not None and self._worker.is_alive()
            ):
                return
            self._worker = threading.Thread(
                target=self._flush,
                name="vodforge-product-telemetry",
                daemon=True,
            )
            self._worker.start()

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
            d1_delivered = event.d1_delivered or self._d1_recorder(event)
            heycatch_delivered = event.heycatch_delivered or self._heycatch_recorder(
                event.install_id,
                event_name=event.event_name,
                event_id=event.event_id,
                app_version=event.app_version,
                platform=event.platform,
                release_channel=event.release_channel,
                run_kind=event.run_kind,
                output_type=event.output_type,
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
                remaining = (
                    latest[1:]
                    if d1_delivered and heycatch_delivered
                    else [updated, *latest[1:]]
                )
                _save_outbox(self._state_path, remaining)
            if not (d1_delivered and heycatch_delivered):
                return

    def shutdown(self, timeout_seconds: float = 1.0) -> bool:
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=max(0.0, timeout_seconds))
        return worker is None or not worker.is_alive()
