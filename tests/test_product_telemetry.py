from __future__ import annotations

import json
from pathlib import Path

from yt_downloader.cloud_funnel import (
    load_or_create_installation_state,
    mark_attribution_claim_confirmed,
)
from yt_downloader.product_telemetry import (
    ProductTelemetryEvent,
    ProductTelemetryOwner,
)


def _permitted_installation(path: Path) -> str:
    state = load_or_create_installation_state(path)
    mark_attribution_claim_confirmed(path, state.install_id)
    return state.install_id


def test_product_events_are_suppressed_without_permission_or_when_disabled(
    tmp_path: Path,
):
    installation_path = tmp_path / "installation.json"
    load_or_create_installation_state(installation_path)
    calls: list[str] = []
    owner = ProductTelemetryOwner(
        state_path=tmp_path / "product-telemetry.json",
        installation_state_path=installation_path,
        app_version="0.1.8-dev",
        platform_name="darwin",
        d1_recorder=lambda event: calls.append(event.event_name) is None,
        heycatch_recorder=lambda *_args, **_kwargs: True,
    )

    assert owner.record_app_opened() is False
    assert calls == []
    assert not (tmp_path / "product-telemetry.json").exists()

    _permitted_installation(installation_path)
    owner.set_enabled(False)
    assert owner.record_app_opened() is False
    assert calls == []


def test_event_contract_is_minimal_and_delivered_to_both_sinks(tmp_path: Path):
    installation_path = tmp_path / "installation.json"
    install_id = _permitted_installation(installation_path)
    d1_events: list[ProductTelemetryEvent] = []
    heycatch_calls: list[tuple[str, dict[str, object]]] = []

    def d1_recorder(event: ProductTelemetryEvent) -> bool:
        d1_events.append(event)
        return True

    def heycatch_recorder(distinct_id: str, **kwargs: object) -> bool:
        heycatch_calls.append((distinct_id, kwargs))
        return True

    owner = ProductTelemetryOwner(
        state_path=tmp_path / "product-telemetry.json",
        installation_state_path=installation_path,
        app_version="0.1.8-dev",
        platform_name="darwin",
        d1_recorder=d1_recorder,
        heycatch_recorder=heycatch_recorder,
    )

    assert owner.record(
        "run_completed",
        dedupe_key="durable-run-id",
        run_kind="youtube",
        output_type="mp4",
    )
    assert owner.shutdown(1.0)
    assert len(d1_events) == 1
    assert len(heycatch_calls) == 1
    event = d1_events[0]
    assert event.install_id == install_id
    assert event.release_channel == "development"
    assert event.public_payload() == {
        "event_id": event.event_id,
        "install_id": install_id,
        "event_name": "run_completed",
        "occurred_at": event.occurred_at,
        "app_version": "0.1.8-dev",
        "platform": "macos",
        "release_channel": "development",
        "schema_version": 1,
        "run_kind": "youtube",
        "output_type": "mp4",
    }
    assert heycatch_calls[0][0] == install_id
    assert not (tmp_path / "product-telemetry.json").exists()


def test_each_sink_retries_independently_and_disable_clears_unsent_events(
    tmp_path: Path,
):
    installation_path = tmp_path / "installation.json"
    _permitted_installation(installation_path)
    state_path = tmp_path / "product-telemetry.json"
    d1_calls = 0
    heycatch_succeeds = False

    def d1_recorder(_event: ProductTelemetryEvent) -> bool:
        nonlocal d1_calls
        d1_calls += 1
        return True

    def heycatch_recorder(*_args: object, **_kwargs: object) -> bool:
        return heycatch_succeeds

    owner = ProductTelemetryOwner(
        state_path=state_path,
        installation_state_path=installation_path,
        app_version="0.1.8-dev",
        d1_recorder=d1_recorder,
        heycatch_recorder=heycatch_recorder,
    )
    assert owner.record_app_opened()
    assert owner.shutdown(1.0)
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["events"][0]["d1_delivered"] is True
    assert payload["events"][0]["heycatch_delivered"] is False

    heycatch_succeeds = True
    owner.flush_async()
    assert owner.shutdown(1.0)
    assert d1_calls == 1
    assert not state_path.exists()

    heycatch_succeeds = False
    assert owner.record_app_opened()
    assert owner.shutdown(1.0)
    assert state_path.exists()
    owner.set_enabled(False)
    assert not state_path.exists()


def test_app_open_is_once_per_session_but_not_once_per_installation(tmp_path: Path):
    installation_path = tmp_path / "installation.json"
    _permitted_installation(installation_path)
    delivered: list[str] = []

    def recorder(event: ProductTelemetryEvent) -> bool:
        delivered.append(event.event_id)
        return True

    def owner(session_id: str) -> ProductTelemetryOwner:
        return ProductTelemetryOwner(
            state_path=tmp_path / "product-telemetry.json",
            installation_state_path=installation_path,
            app_version="0.1.8-dev",
            session_id=session_id,
            d1_recorder=recorder,
            heycatch_recorder=lambda *_args, **_kwargs: True,
        )

    first = owner("3100042a-a7c5-5de2-a6d7-e40215b7078e")
    assert first.record_app_opened()
    assert first.record_app_opened()
    assert first.shutdown(1.0)
    second = owner("2531948d-2918-5ddb-8e32-4bfe845d5165")
    assert second.record_app_opened()
    assert second.shutdown(1.0)

    assert len(set(delivered)) == 2
