from __future__ import annotations

import json
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

HEYCATCH_CAPTURE_ENDPOINT = "https://in.heycatch.ai/capture/"
HEYCATCH_INGEST_KEY = "phc_oiDt6uXiBiEA2aT43SMzMAFE9D4gMVkRP3BtvYRsmHqe"
HEYCATCH_PROJECT_KEY = "hck_pk_R3INGrBG09B3VTAx8YpycEqKLkFEVFv0"
NETWORK_TIMEOUT_SECONDS = 4.0
MAX_RESPONSE_BYTES = 4096


def _uuid4(value: str) -> str:
    parsed = uuid.UUID(str(value).strip())
    if parsed.version != 4:
        raise ValueError("HeyCatch distinct ID must be a random UUID4")
    return str(parsed)


def _capture(
    event: str,
    distinct_id: str,
    properties: Mapping[str, str | bool],
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
    timeout_seconds: float = NETWORK_TIMEOUT_SECONDS,
) -> bool:
    normalized_id = _uuid4(distinct_id)
    payload = {
        "api_key": HEYCATCH_INGEST_KEY,
        "event": event,
        "distinct_id": normalized_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "properties": {
            **properties,
            "heycatch_project_key": HEYCATCH_PROJECT_KEY,
            "$groups": {"project": HEYCATCH_PROJECT_KEY},
        },
    }
    request = urllib.request.Request(
        HEYCATCH_CAPTURE_ENDPOINT,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "VODForge-HeyCatch/1",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=timeout_seconds) as response:
            status = int(getattr(response, "status", 200))
            body = response.read(MAX_RESPONSE_BYTES + 1)
        if status < 200 or status >= 300 or len(body) > MAX_RESPONSE_BYTES:
            return False
        decoded = json.loads(body.decode("utf-8"))
        return isinstance(decoded, dict) and decoded.get("status") == "Ok"
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return False


def record_first_launch(
    install_id: str,
    *,
    app_version: str,
    platform: str,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> bool:
    return _capture(
        "first_launch",
        install_id,
        {
            "$insert_id": str(
                uuid.uuid5(uuid.NAMESPACE_URL, f"vodforge:first_launch:{install_id}")
            ),
            "app_version": str(app_version),
            "platform": str(platform),
        },
        opener=opener,
    )


def record_product_event(
    install_id: str,
    *,
    event_name: str,
    event_id: str,
    app_version: str,
    platform: str,
    release_channel: str,
    run_kind: str | None = None,
    output_type: str | None = None,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> bool:
    allowed_events = {
        "app_opened",
        "run_started",
        "run_completed",
        "run_failed",
        "run_stopped",
        "playback_started",
        "local_conversion_completed",
    }
    if event_name not in allowed_events:
        raise ValueError("unsupported HeyCatch product event")
    properties: dict[str, str | bool] = {
        "$insert_id": str(uuid.UUID(event_id)),
        "app_version": str(app_version),
        "platform": str(platform),
        "release_channel": str(release_channel),
        "telemetry_schema_version": "1",
    }
    if run_kind is not None:
        properties["run_kind"] = str(run_kind)
    if output_type is not None:
        properties["output_type"] = str(output_type)
    return _capture(event_name, install_id, properties, opener=opener)
