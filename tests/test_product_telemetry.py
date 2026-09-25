from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")

from yt_downloader.cloud_funnel import (
    load_or_create_installation_state,
    mark_attribution_claim_confirmed,
)
from yt_downloader.product_telemetry import (
    ProductTelemetryEvent,
    ProductTelemetryOwner,
)


def _permitted_installation(path: Path) -> str:
    from yt_downloader.analytics_consent import AnalyticsConsentOwner

    AnalyticsConsentOwner(path.parent).choose(True)
    state = load_or_create_installation_state(path)
    mark_attribution_claim_confirmed(path, state.install_id)
    return state.install_id


@pytest.mark.parametrize("permitted", [False, True])
def test_original_audio_events_obey_deployed_vocabulary(tmp_path, permitted):
    from yt_downloader.models import OutputType
    from yt_downloader.product_telemetry import product_output_kind

    installation = tmp_path / "installation.json"
    if permitted:
        _permitted_installation(installation)
    else:
        load_or_create_installation_state(installation)
    owner = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=installation,
        app_version="0.1.9",
        d1_recorder=lambda _event: True,
        heycatch_recorder=lambda *_args, **_kwargs: True,
    )
    for output in OutputType:
        kind = product_output_kind(output.value)
        assert kind in ("mp4", "mp3", "original")
        for event in ("run_started", "run_completed", "playback_started"):
            assert owner.record(event, output_type=kind) is permitted
    assert product_output_kind("Original audio") == "original"
    assert owner.shutdown(2)


@pytest.mark.parametrize("preview_mode", [False, True])
def test_preview_excludes_provider_without_fabricating_delivery(
    tmp_path, monkeypatch, preview_mode
):
    from yt_downloader import product_telemetry

    monkeypatch.setattr(
        product_telemetry, "preview_telemetry_allowed", lambda: preview_mode
    )
    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    queue = tmp_path / "product-telemetry.json"
    owner = ProductTelemetryOwner(
        state_path=queue,
        installation_state_path=installation,
        app_version="0.1.8",
        d1_recorder=lambda _event: True,
        heycatch_recorder=lambda *_args, **_kwargs: False,
    )
    assert owner.record_app_opened()
    assert owner.shutdown(2)
    if preview_mode:
        assert not queue.exists()
    else:
        events = product_telemetry._load_outbox(queue)
        assert len(events) == 1
        assert events[0].d1_delivered
        assert not events[0].heycatch_delivered


def test_permanent_server_rejection_retires_event_without_claiming_delivery(tmp_path):
    from yt_downloader.telemetry_credentials import RejectedTelemetryEvent

    installation_path = tmp_path / "installation.json"
    _permitted_installation(installation_path)
    state_path = tmp_path / "product-telemetry.json"
    calls = []

    def reject(event):
        calls.append(event.event_id)
        raise RejectedTelemetryEvent()

    owner = ProductTelemetryOwner(
        state_path=state_path,
        installation_state_path=installation_path,
        app_version="0.1.8",
        d1_recorder=reject,
        heycatch_recorder=lambda *_args, **_kwargs: True,
    )
    assert owner.record_app_opened()
    assert owner.shutdown(1.0)
    owner.flush_async()
    assert owner.shutdown(1.0)
    assert len(calls) == 1
    assert not state_path.exists()


def test_full_outbox_replays_on_new_session_after_delivery_recovers(tmp_path):
    from yt_downloader.product_telemetry import (
        MAX_OUTBOX_EVENTS,
        _load_outbox,
        _save_outbox,
    )

    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    state_path = tmp_path / "product-telemetry.json"
    blocked = ProductTelemetryOwner(
        state_path=state_path,
        installation_state_path=installation,
        app_version="0.2.3",
        d1_recorder=lambda _event: False,
        heycatch_recorder=lambda *_args, **_kwargs: True,
    )
    assert blocked.record_app_opened()
    assert blocked.shutdown(2)
    first = _load_outbox(state_path)[0]
    queued = [replace(first, event_id=str(uuid4())) for _ in range(MAX_OUTBOX_EVENTS)]
    _save_outbox(state_path, queued)

    delivered: list[str] = []
    resumed = ProductTelemetryOwner(
        state_path=state_path,
        installation_state_path=installation,
        app_version="0.2.3",
        d1_recorder=lambda event: delivered.append(event.event_id) is None,
        heycatch_recorder=lambda *_args, **_kwargs: True,
    )
    assert not resumed.record_app_opened()  # The bounded outbox rejects this new event.
    assert resumed.shutdown(5)
    assert delivered == [event.event_id for event in queued]
    assert not state_path.exists()


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
        "schema_version": 2,
        "attempt_id": None,
        "retry_of": None,
        "feature": None,
        "action": None,
        "dimensions": {},
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
    assert owner.record_feature("library", "opened")
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
    # A later startup callback may run after successful delivery removed the
    # event from the outbox. Session deduplication must outlive that queue row.
    assert first.shutdown(1.0)
    assert first.record_app_opened()
    assert first.shutdown(1.0)
    second = owner("2531948d-2918-5ddb-8e32-4bfe845d5165")
    assert second.record_app_opened()
    assert second.shutdown(1.0)

    assert len(delivered) == len(set(delivered)) == 2

    first.set_enabled(False)
    assert not first.record_app_opened()
    first.set_enabled(True)
    assert first.record_app_opened()
    assert first.shutdown(1.0)
    assert len(delivered) == 2


@pytest.mark.parametrize("kind", ["app_opened", "feature_used"])
def test_repeated_startup_callback_retries_pending_event_without_recreating_it(
    tmp_path: Path,
    kind: str,
):
    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    attempts = []

    def deliver(event):
        attempts.append(event.public_payload())
        return len(attempts) > 1

    owner = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=installation,
        app_version="0.2.2",
        d1_recorder=deliver,
        heycatch_recorder=lambda *_args, **_kwargs: True,
    )
    record = (
        owner.record_app_opened
        if kind == "app_opened"
        else lambda: owner.record_feature("library", "opened")
    )
    assert record()
    assert owner.shutdown(2)
    assert len(attempts) == 1
    # Enrollment completion retries the same immutable queued app-open event.
    assert record()
    assert owner.shutdown(2)
    assert len(attempts) == 2
    assert attempts[0] == attempts[1]
    assert record()
    assert owner.shutdown(2)
    assert len(attempts) == 2


def test_event_recorded_while_empty_delivery_worker_exits_is_not_stranded(
    tmp_path: Path, monkeypatch
):
    import threading

    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    delivered = []
    owner = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=installation,
        app_version="0.2.2",
        d1_recorder=lambda event: delivered.append(event.event_id) or True,
        heycatch_recorder=lambda *_args, **_kwargs: True,
    )
    empty_worker_done = threading.Event()
    release_worker = threading.Event()
    original_flush = owner._flush

    def pause_at_exit():
        original_flush()
        if not empty_worker_done.is_set():
            empty_worker_done.set()
            assert release_worker.wait(3)

    monkeypatch.setattr(owner, "_flush", pause_at_exit)
    owner.flush_async()
    try:
        assert empty_worker_done.wait(2)
        assert owner.record_app_opened()
    finally:
        release_worker.set()
    assert owner.shutdown(2)
    assert len(delivered) == 1


@pytest.mark.parametrize(
    "event_name,feature,action",
    [
        ("local_conversion_failed", None, None),
        ("feature_used", "player", "failed"),
    ],
)
def test_typed_operation_failures_survive_restart_without_private_exception_data(
    tmp_path, event_name, feature, action
):
    from yt_downloader.failure_diagnostics import capture_failure
    from yt_downloader.product_telemetry import _load_outbox, _parse_event

    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    path = tmp_path / "events.json"
    detail = capture_failure(PermissionError(13, "PRIVATE /path title URL")).payload()
    owner = ProductTelemetryOwner(
        state_path=path,
        installation_state_path=installation,
        app_version="0.2.3-dev",
        d1_recorder=lambda _event: False,
        heycatch_recorder=lambda *_args, **_kwargs: False,
    )
    assert owner.record(
        event_name, feature=feature, action=action, failure_detail=detail
    )
    assert owner.shutdown(2)
    persisted = _load_outbox(path)[0].public_payload()
    assert persisted["failure_reason"] == "permission_denied"
    assert persisted["failure_detail"] == detail
    assert "PRIVATE" not in json.dumps(persisted)
    assert _parse_event(persisted).public_payload() == persisted
    deliveries = []
    restarted = ProductTelemetryOwner(
        state_path=path,
        installation_state_path=installation,
        app_version="0.2.3-dev",
        d1_recorder=lambda event: deliveries.append(event.public_payload()) is None,
        heycatch_recorder=lambda *_args, **_kwargs: True,
    )
    restarted.flush_async()
    assert restarted.shutdown(2)
    assert deliveries == [persisted]
    assert not path.exists()


def test_old_local_failure_replay_does_not_acquire_invented_diagnostic(tmp_path):
    from yt_downloader.product_telemetry import _parse_event

    legacy = {
        "event_id": "a40aa6cc-cfdd-4f7a-96e1-5dce763d2782",
        "install_id": "5fcae92f-8bf0-4810-920d-ff8348a42a0a",
        "event_name": "local_conversion_failed",
        "occurred_at": "2026-09-15T00:00:00+00:00",
        "app_version": "0.2.2",
        "platform": "windows",
        "release_channel": "production",
        "schema_version": 2,
        "attempt_id": None,
        "retry_of": None,
        "feature": None,
        "action": None,
        "dimensions": {},
        "run_kind": "local_audio_video",
        "output_type": "mp4",
    }
    assert _parse_event(legacy).public_payload() == legacy


@pytest.mark.parametrize(
    "event_name,feature,action",
    [
        ("local_conversion_completed", None, None),
        ("feature_used", "player", "completed"),
    ],
)
def test_nonfailure_events_reject_failure_facts(tmp_path, event_name, feature, action):
    owner = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=tmp_path / "installation.json",
        app_version="0.2.3-dev",
    )
    with pytest.raises(ValueError):
        owner.record(
            event_name,
            feature=feature,
            action=action,
            failure_detail={"reason": "permission_denied", "stage": "unknown"},
        )


def test_conflicting_failure_reason_is_rejected_before_outbox(tmp_path):
    owner = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=tmp_path / "installation.json",
        app_version="0.2.3-dev",
    )
    with pytest.raises(ValueError):
        owner.record(
            "local_conversion_failed",
            failure_reason="network",
            failure_detail={"reason": "permission_denied", "stage": "unknown"},
        )
    assert not (tmp_path / "events.json").exists()


def test_settings_reenable_reports_current_observation_without_replaying_denied(
    tmp_path,
):
    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    received = []
    owner = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=installation,
        app_version="0.2.3-dev",
        d1_recorder=lambda event: received.append(event.public_payload()) is None,
        heycatch_recorder=lambda *_args, **_kwargs: True,
    )
    current = {"setting_output_type": "MP4"}
    assert owner.record_feature("settings", "snapshot", dimensions=current)
    assert owner.shutdown(2)
    owner.set_enabled(False)
    assert not owner.record_feature(
        "settings", "snapshot", dimensions={"setting_output_type": "MP3"}
    )
    assert not (tmp_path / "events.json").exists()
    owner.set_enabled(True)
    assert owner.record_feature("settings", "snapshot", dimensions=current)
    assert owner.shutdown(2)
    assert len(received) == 2
    assert all(event["dimensions"] == current for event in received)
    assert received[0]["event_id"] != received[1]["event_id"]


def test_disable_between_permission_and_retention_cannot_recreate_outbox(
    tmp_path, monkeypatch
):
    from yt_downloader import product_telemetry as module

    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    path = tmp_path / "events.json"
    owner = ProductTelemetryOwner(
        state_path=path,
        installation_state_path=installation,
        app_version="0.2.3-dev",
        d1_recorder=lambda event: pytest.fail("disabled event reached sink"),
        heycatch_recorder=lambda *_args, **_kwargs: True,
    )

    def load_after_disable(_path):
        owner.set_enabled(False)
        return []

    monkeypatch.setattr(module, "_load_outbox", load_after_disable)
    assert not owner.record("app_opened")
    assert not path.exists()


def test_revocation_survives_locked_outbox_and_restart_without_replay(
    tmp_path, monkeypatch
):
    from yt_downloader import product_telemetry as module
    from yt_downloader.analytics_consent import AnalyticsConsentOwner

    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    path = tmp_path / "events.json"
    owner = ProductTelemetryOwner(
        state_path=path,
        installation_state_path=installation,
        app_version="0.2.3-dev",
        d1_recorder=lambda _event: False,
        heycatch_recorder=lambda *_a, **_kw: False,
    )
    assert owner.record_app_opened()
    assert owner.shutdown(2)
    before = path.read_bytes()
    consent = AnalyticsConsentOwner(tmp_path)
    consent.choose(False)

    def locked(*args):
        raise PermissionError("QA locked outbox")

    with monkeypatch.context() as patch:
        patch.setattr(module, "_save_outbox", locked)
        owner.set_enabled(False)
    assert path.read_bytes() == before
    consent.choose(True)
    delivered = []
    restarted = ProductTelemetryOwner(
        state_path=path,
        installation_state_path=installation,
        app_version="0.2.3-dev",
        d1_recorder=lambda event: delivered.append(event) is None,
        heycatch_recorder=lambda *_a, **_kw: True,
    )
    restarted.flush_async()
    assert restarted.shutdown(2)
    assert delivered == []
    assert not path.exists()
    assert restarted.record_app_opened()
    assert restarted.shutdown(2)
    assert len(delivered) == 1
    assert delivered[0].consent_epoch == consent.snapshot()["collection_epoch"]
    assert "consent_epoch" not in delivered[0].public_payload()


def test_revoke_and_reenable_between_sinks_cannot_deliver_old_event_to_second_sink(
    tmp_path,
):
    from yt_downloader.analytics_consent import AnalyticsConsentOwner

    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    consent = AnalyticsConsentOwner(tmp_path)
    secondary = []

    def primary(_event):
        consent.choose(False)
        owner.set_enabled(False)
        consent.choose(True)
        owner.set_enabled(True)
        return True

    owner = ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=installation,
        app_version="0.2.3-dev",
        d1_recorder=primary,
        heycatch_recorder=lambda *args, **kwargs: secondary.append(kwargs) is None,
    )
    assert owner.record_app_opened()
    assert owner.shutdown(2)
    assert secondary == []
    assert not (tmp_path / "events.json").exists()


def test_legacy_denial_also_invalidates_outbox_before_reenable(tmp_path):
    from yt_downloader.analytics_consent import AnalyticsConsentOwner
    from yt_downloader.settings_store import update_analytics_settings

    installation = tmp_path / "installation.json"
    _permitted_installation(installation)
    path = tmp_path / "events.json"
    owner = ProductTelemetryOwner(
        state_path=path,
        installation_state_path=installation,
        app_version="0.2.3-dev",
        d1_recorder=lambda _event: False,
        heycatch_recorder=lambda *_a, **_kw: False,
    )
    assert owner.record_app_opened() and owner.shutdown(2)
    # Historical releases saved choice only; simulate their unpurged outbox.
    update_analytics_settings(tmp_path / "settings.json", {"choice": "denied"})
    consent = AnalyticsConsentOwner(tmp_path)
    assert consent.snapshot().get("collection_epoch")
    consent.choose(True)
    delivered = []
    resumed = ProductTelemetryOwner(
        state_path=path,
        installation_state_path=installation,
        app_version="0.2.3-dev",
        d1_recorder=lambda e: delivered.append(e) is None,
        heycatch_recorder=lambda *_a, **_kw: True,
    )
    resumed.flush_async()
    assert resumed.shutdown(2)
    assert delivered == [] and not path.exists()
