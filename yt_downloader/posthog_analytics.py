"""Optional, consent-gated event mirror. No desktop replay or exception contents."""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .failure_diagnostics import FAILURE_REASONS, FAILURE_STAGES
from .telemetry_features import DIMENSION_CHOICES, FEATURE_ACTIONS, system_dimensions

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
    }
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
    for name in SAFE_DIMENSIONS:
        value = event.dimensions.get(name)
        if isinstance(value, str) and value in DIMENSION_CHOICES[name]:
            properties[name] = value
    if event.failure_detail and event.failure_detail.stage in FAILURE_STAGES:
        properties["failure_stage"] = event.failure_detail.stage
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
