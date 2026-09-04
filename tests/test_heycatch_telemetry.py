from __future__ import annotations

import json
from typing import Any, Self

from yt_downloader.heycatch_telemetry import (
    HEYCATCH_CAPTURE_ENDPOINT,
    HEYCATCH_INGEST_KEY,
    HEYCATCH_PROJECT_KEY,
    record_first_launch,
    record_product_event,
)

INSTALL_ID = "f9c775b1-4c5a-47c4-87bb-81fe51881e54"


class JsonResponse:
    status = 200

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return b'{"status":"Ok"}'


def test_first_launch_uses_confirmed_native_contract_and_public_routing_fields():
    captured: dict[str, Any] = {}

    def opener(request: Any, *, timeout: float) -> JsonResponse:
        captured.update(
            url=request.full_url,
            payload=json.loads(request.data.decode("utf-8")),
            timeout=timeout,
            user_agent=request.headers["User-agent"],
        )
        return JsonResponse()

    assert record_first_launch(
        INSTALL_ID,
        app_version="0.1.8-dev",
        platform="macos",
        opener=opener,
    )
    assert captured["url"] == HEYCATCH_CAPTURE_ENDPOINT
    assert captured["timeout"] == 4.0
    assert captured["user_agent"] == "VODForge-HeyCatch/1"
    assert captured["payload"] == {
        "api_key": HEYCATCH_INGEST_KEY,
        "event": "first_launch",
        "distinct_id": INSTALL_ID,
        "timestamp": captured["payload"]["timestamp"],
        "properties": {
            "$insert_id": captured["payload"]["properties"]["$insert_id"],
            "app_version": "0.1.8-dev",
            "platform": "macos",
            "heycatch_project_key": HEYCATCH_PROJECT_KEY,
            "$groups": {"project": HEYCATCH_PROJECT_KEY},
        },
    }


def test_first_launch_fails_closed_on_unacknowledged_or_oversized_response():
    class BadResponse(JsonResponse):
        status = 403

    assert not record_first_launch(
        INSTALL_ID,
        app_version="0.1.7",
        platform="windows",
        opener=lambda *_args, **_kwargs: BadResponse(),
    )


def test_first_launch_rejects_non_uuid_identity_before_network():
    called = False

    def opener(*_args: Any, **_kwargs: Any) -> JsonResponse:
        nonlocal called
        called = True
        return JsonResponse()

    try:
        record_first_launch(
            "hardware-fingerprint",
            app_version="0.1.7",
            platform="macos",
            opener=opener,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("invalid identity was accepted")
    assert called is False


def test_product_event_uses_the_same_identity_and_minimal_contract():
    captured: dict[str, Any] = {}

    def opener(request: Any, *, timeout: float) -> JsonResponse:
        captured.update(
            payload=json.loads(request.data.decode("utf-8")),
            timeout=timeout,
        )
        return JsonResponse()

    assert record_product_event(
        INSTALL_ID,
        event_name="run_completed",
        event_id="3100042a-a7c5-5de2-a6d7-e40215b7078e",
        app_version="0.1.8-dev",
        platform="macos",
        release_channel="development",
        run_kind="youtube",
        output_type="mp4",
        opener=opener,
    )
    assert captured["timeout"] == 4.0
    assert captured["payload"]["distinct_id"] == INSTALL_ID
    assert captured["payload"]["event"] == "run_completed"
    assert captured["payload"]["properties"] == {
        "$insert_id": "3100042a-a7c5-5de2-a6d7-e40215b7078e",
        "app_version": "0.1.8-dev",
        "platform": "macos",
        "release_channel": "development",
        "telemetry_schema_version": "1",
        "run_kind": "youtube",
        "output_type": "mp4",
        "heycatch_project_key": HEYCATCH_PROJECT_KEY,
        "$groups": {"project": HEYCATCH_PROJECT_KEY},
    }
