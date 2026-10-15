"""Optional, consent-gated event mirror. No desktop replay or exception contents."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.request
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .failure_diagnostics import FAILURE_CODES, FAILURE_REASONS, FAILURE_STAGES
from .telemetry_features import (
    DIMENSION_CHOICES,
    DIMENSION_RANGES,
    FEATURE_ACTIONS,
    system_dimensions,
)

if TYPE_CHECKING:
    from .product_telemetry import ProductTelemetryEvent

HOSTS = frozenset({"https://us.i.posthog.com"})
VERSION = re.compile(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]{1,30})?\Z")
SAFE_DIMENSIONS = frozenset(
    {
        "processing_bucket",
        "wait_bucket",
        "duration_bucket",
        "size_bucket",
        "preset",
        "encoder",
        "rate_control",
        "input_kind",
        "resolution",
        "outcome",
        "update_stage",
    }
)


def valid_qa_run_id(value: str) -> str | None:
    try:
        parsed = uuid.UUID(value)
        return str(parsed) if parsed.version == 4 else None
    except (ValueError, AttributeError, TypeError):
        return None


def new_session_id() -> str:
    """UUIDv7 compatible with supported Python 3.11+, without a new SDK."""
    random_bits = uuid.uuid4().int
    value = (int(time.time() * 1000) << 80) | (random_bits & ((1 << 80) - 1))
    value = (value & ~(15 << 76)) | (7 << 76)
    value = (value & ~(3 << 62)) | (2 << 62)
    return str(uuid.UUID(int=value))


@dataclass(frozen=True)
class PosthogConfig:
    enabled: bool = False
    project_key: str = ""
    host: str = ""

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] = os.environ
    ) -> PosthogConfig:
        try:
            public = json.loads(
                (
                    Path(__file__).resolve().parent.parent
                    / "assets/posthog-public-config.json"
                ).read_text()
            )
        except (OSError, ValueError):
            public = {}
        key = environment.get(
            "VODFORGE_POSTHOG_PUBLIC_KEY", public.get("public_key", "")
        )
        host = environment.get(
            "VODFORGE_POSTHOG_HOST", public.get("ingest_host", "")
        ).rstrip("/")
        enabled = (
            public.get("project_id") == 664300
            and public.get("capture_enabled") is True
            and environment.get("VODFORGE_POSTHOG_ENABLED", "true") == "true"
            and re.fullmatch(r"phc_[A-Za-z0-9]{10,200}", key) is not None
            and host in HOSTS
            and host == public.get("ingest_host")
            and key == public.get("public_key")
            and (
                not environment.get("VODFORGE_POSTHOG_QA_RUN")
                or valid_qa_run_id(environment["VODFORGE_POSTHOG_QA_RUN"]) is not None
            )
        )
        return cls(enabled, key if enabled else "", host if enabled else "")


def installation_distinct_id(install_id: str) -> str:
    return (
        "vf_install_"
        + hashlib.sha256(
            ("vodforge:posthog:installation:" + install_id).encode()
        ).hexdigest()
    )


def capture_payload(event: ProductTelemetryEvent) -> dict[str, Any] | None:
    # Canonical producers validate event vocabulary. The secondary boundary
    # still rebuilds a small payload instead of forwarding the public payload.
    from .product_telemetry import PRODUCT_EVENT_NAMES

    try:
        uuid.UUID(event.event_id)
        uuid.UUID(event.install_id)
        datetime.fromisoformat(event.occurred_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return None

    if (
        event.event_name not in PRODUCT_EVENT_NAMES
        or not VERSION.fullmatch(event.app_version)
        or event.platform not in {"macos", "windows", "linux", "unknown"}
        or event.release_channel not in {"production", "development", "test"}
    ):
        return None
    properties: dict[str, Any] = {
        "surface": "desktop",
        "app_version": event.app_version,
        "os": event.platform,
        "architecture": system_dimensions()["architecture"],
        "release_channel": event.release_channel,
        "$insert_id": event.event_id,
        "$geoip_disable": True,
        "$ip": "0.0.0.0",
        "$process_person_profile": False,
        "schema_version": "2",
        "measurement_scope": "production",
        "environment": "production",
        "is_test": event.release_channel != "production",
    }
    try:
        session = uuid.UUID(event.posthog_session_id or "")
        if session.version == 7:
            properties["$session_id"] = str(session)
    except (ValueError, TypeError, AttributeError):
        pass
    for name, value, maximum in (
        ("event_sequence", event.posthog_sequence, 1000000),
        ("session_elapsed_ms", event.posthog_elapsed_ms, 86400000),
    ):
        if type(value) is int and 0 <= value <= maximum:
            properties[name] = value
    qa = valid_qa_run_id(event.posthog_qa_run_id or "")
    if qa:
        properties.update(
            qa_run_id=qa,
            measurement_scope="qa",
            release_channel="test",
            validation_id=qa,
            is_test=True,
            build_release_channel=event.release_channel,
        )
    for name, value in (("attempt_id", event.attempt_id), ("retry_of", event.retry_of)):
        try:
            if value and uuid.UUID(value).version == 5:
                properties[name] = value
        except (ValueError, AttributeError, TypeError):
            pass
    if event.feature is not None:
        if (
            event.feature not in FEATURE_ACTIONS
            or event.action not in FEATURE_ACTIONS[event.feature]
        ):
            return None
        properties.update(feature=event.feature, action=event.action)
    if event.run_kind in {"youtube", "local_audio_video"}:
        properties["run_kind"] = event.run_kind
    if event.output_type in {"mp4", "mp3", "original"}:
        properties["output_type"] = event.output_type
    if event.failure_reason in FAILURE_REASONS:
        properties["failure_reason"] = event.failure_reason
    for name in DIMENSION_CHOICES:
        value = event.dimensions.get(name)
        if isinstance(value, str) and value in DIMENSION_CHOICES[name]:
            properties[name] = value
    for name in (
        "item_count",
        "committed_count",
        "reused_count",
        "failed_count",
        "skipped_count",
        "sidecar_failure_count",
        "observation_drop_count",
        "verified_count",
        "unresolved_count",
        "collision_count",
        "identity_mismatch_count",
        "missing_count",
        "unavailable_count",
    ):
        value = event.dimensions.get(name, "")
        if isinstance(value, str) and re.fullmatch(r"0|[1-9][0-9]{0,5}", value):
            low, high = DIMENSION_RANGES[name]
            if low <= int(value) <= high:
                properties[name] = int(value)
    revision = event.dimensions.get("build_revision", "")
    if isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}", revision):
        properties["build_revision"] = revision
    operation_id = event.dimensions.get("operation_id", "")
    try:
        if uuid.UUID(operation_id).version in {4, 5}:
            properties["operation_id"] = operation_id
            step = event.dimensions.get("operation_step", "")
            if re.fullmatch(r"[1-9][0-9]{0,5}", step):
                properties["operation_step"] = int(step)
    except (ValueError, AttributeError, TypeError):
        pass
    if event.failure_detail and event.failure_detail.stage in FAILURE_STAGES:
        properties["failure_stage"] = event.failure_detail.stage
        if event.failure_detail.failure_code in FAILURE_CODES:
            properties["failure_code"] = event.failure_detail.failure_code
    # Raw messages, stacks, metadata, media paths and all arbitrary dimensions
    # are excluded, even when an injected caller supplies them.
    return {
        "event": "vf_app_" + event.event_name,
        "uuid": event.event_id,
        "distinct_id": installation_distinct_id(event.install_id),
        "timestamp": event.occurred_at,
        "properties": properties,
    }


class PosthogEventSink:
    def __init__(
        self,
        config: PosthogConfig | None = None,
        *,
        opener: Any = urllib.request.urlopen,
    ):
        self.config = config or PosthogConfig.from_environment()
        self.enabled = bool(
            self.config.enabled
            and self.config.host in HOSTS
            and re.fullmatch(r"phc_[A-Za-z0-9]{10,200}", self.config.project_key)
        )
        self._opener = opener

    def first_run_confirmed(self, event: ProductTelemetryEvent) -> bool:
        return self._capture(event, first_run=True)

    def __call__(self, event: ProductTelemetryEvent) -> bool:
        return self._capture(event)

    def _capture(
        self, event: ProductTelemetryEvent, *, first_run: bool = False
    ) -> bool:
        if not self.enabled:
            return False
        payload = capture_payload(event)
        if payload is None:
            return False
        if first_run:
            payload["event"] = "vf_app_first_run_confirmed"
        delivered = self._send(payload)
        if (
            event.feature == "application_lifecycle"
            and event.action == "screen_viewed"
            and event.dimensions.get("view")
            in {"forge", "library", "watch", "activity"}
        ):
            screen_id = str(uuid.uuid5(uuid.UUID(event.event_id), "screen"))
            screen = {
                **payload,
                "event": "$screen",
                "uuid": screen_id,
                "properties": {
                    **payload["properties"],
                    "$insert_id": screen_id,
                    "$screen_name": event.dimensions["view"],
                },
            }
            return self._send(screen) and delivered
        if (
            event.feature == "application_lifecycle"
            and event.action == "unhandled_exception"
            and event.dimensions.get("exception_kind")
            in DIMENSION_CHOICES["exception_kind"]
            and event.dimensions.get("exception_origin")
            in DIMENSION_CHOICES["exception_origin"]
        ):
            kind = event.dimensions["exception_kind"]
            origin = event.dimensions["exception_origin"]
            exception = {
                **payload,
                "event": "$exception",
                "uuid": str(uuid.uuid5(uuid.UUID(event.event_id), "exception")),
                "properties": {
                    **payload["properties"],
                    "$exception_list": [
                        {
                            "type": "VODForge_" + kind,
                            "value": "Unhandled application exception (content omitted)",
                            "mechanism": {"handled": False, "synthetic": False},
                            "stacktrace": {"type": "raw", "frames": []},
                        }
                    ],
                    "$exception_fingerprint": "vodforge:" + kind + ":" + origin,
                    "$exception_level": "error",
                },
            }
            exception["properties"]["$insert_id"] = exception["uuid"]
            return self._send(exception) and delivered
        return delivered

    def _send(self, payload: dict[str, Any]) -> bool:
        request = urllib.request.Request(
            self.config.host + "/i/v0/e/",
            data=json.dumps({"api_key": self.config.project_key, **payload}).encode(),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "VODForge-PostHog/1",
            },
            method="POST",
        )
        try:
            with self._opener(request, timeout=4.0) as response:
                return 200 <= response.status < 300
        except (OSError, ValueError):
            return False
