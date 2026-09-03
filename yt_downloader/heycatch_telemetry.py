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
