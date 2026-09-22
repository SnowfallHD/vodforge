from __future__ import annotations

import json

import pytest
from quality_harness.playback_probe import CASES, run_case

from tests.test_history_diagnostics import make_app, payloads

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


@pytest.mark.parametrize("case", CASES)
def test_control_and_failure_producers_preserve_bounded_distinctions(
    tmp_path, monkeypatch, case
):
    holder = make_app(tmp_path, monkeypatch, consent=True)
    result = run_case(tmp_path / "provider", holder.product_telemetry, case)
    events = payloads(holder)
    assert len(events) <= (38 if case == "command_flood" else 10)
    assert "PRIVATE" not in json.dumps(events)
    assert all(event["dimensions"]["playback_origin"] == "watch" for event in events)
    volume = [event for event in events if event["action"].startswith("volume_")]
    outcomes = [event["dimensions"]["volume_outcome"] for event in volume]
    if case == "immediate_mute":
        assert outcomes == ["applied"]
        assert volume[0]["dimensions"]["volume_observed"] == "0"
    elif case == "delayed_mute":
        assert outcomes == ["pending", "applied"]
    elif case in {
        "pending_at_close",
        "accepted_mismatch",
        "readback_unavailable",
        "readback_exception",
    }:
        assert outcomes == ["pending", "pending_at_close"]
        assert "applied" not in outcomes
    elif case == "setter_exception":
        assert outcomes == ["failed"]
        assert volume[0]["failure_detail"]["error_type"] == "RuntimeError"
        assert volume[0]["failure_detail"]["source_module"] == "libvlc_backend"
    elif case == "superseded_request":
        assert outcomes == ["pending", "applied"]
        assert all(event["dimensions"]["volume_request"] == "2" for event in volume)
        assert volume[-1]["dimensions"]["volume_observed"] == "37"
    elif case == "output_recreated":
        assert outcomes == ["applied", "pending", "applied"]
    elif case == "command_flood":
        assert len(volume) == 33
        assert outcomes[-1] == "pending_at_close"
        assert volume[-1]["dimensions"]["volume_request"] == "202"
        assert volume[-1]["dimensions"]["volume_requested"] == "37"
        assert events[-1]["action"] == "closed"
    elif case in {"provider_event", "state_read"}:
        failure = next(event for event in events if event["action"] == "failed")
        assert failure["dimensions"]["playback_failure_boundary"] == case
        if case == "state_read":
            assert failure["failure_detail"]["error_type"] == "OSError"
            assert failure["failure_detail"]["os_error"] == 5
    assert result["physical_input"] is False and result["audibility_observed"] is False


@pytest.mark.parametrize("consent", [False, "revoked"])
def test_control_observations_respect_denied_and_revoked_consent(
    tmp_path, monkeypatch, consent
):
    holder = make_app(tmp_path, monkeypatch, consent=consent == "revoked")
    if consent == "revoked":
        holder.product_telemetry.set_enabled(False)
    result = run_case(tmp_path / "provider", holder.product_telemetry, "delayed_mute")
    assert result["volume"]["observed"] == 0
    assert payloads(holder) == []


def test_volume_diagnostics_sink_exception_preserves_playback_and_close(
    tmp_path, monkeypatch
):
    holder = make_app(tmp_path, monkeypatch, consent=True)

    def unavailable(_event):
        raise OSError("PRIVATE telemetry sink path")

    diagnostic = []
    holder.product_telemetry._diagnostic = diagnostic.append
    holder.product_telemetry._d1_recorder = unavailable
    result = run_case(tmp_path / "provider", holder.product_telemetry, "delayed_mute")
    events = payloads(holder)
    assert result["volume"]["observed"] == 0
    assert events[-1]["action"] == "closed"
    assert "PRIVATE" not in json.dumps(events)
    assert diagnostic and all("PRIVATE" not in value for value in diagnostic)
    holder.product_telemetry._d1_recorder = lambda event: True
    holder.product_telemetry._heycatch_recorder = lambda *_args, **_fields: True
    holder.product_telemetry.flush_async()
    assert payloads(holder) == []


def test_failed_sink_retires_worker_and_revoked_epoch_cannot_replay(
    tmp_path, monkeypatch
):
    from yt_downloader import product_telemetry as telemetry_module
    from yt_downloader.analytics_consent import AnalyticsConsentOwner
    from yt_downloader.product_telemetry import _load_outbox

    holder = make_app(tmp_path, monkeypatch, consent=True)
    owner = holder.product_telemetry
    calls = []
    diagnostic = []

    def unavailable(event):
        calls.append(event.event_id)
        raise OSError("PRIVATE sink")

    owner._diagnostic = diagnostic.append
    owner._d1_recorder = unavailable
    assert owner.record_app_opened()
    assert owner.shutdown(2)
    assert owner._worker is None and len(calls) == 1
    retained = _load_outbox(tmp_path / "events.json")
    assert len(retained) == 1 and retained[0].d1_delivered is False
    old_event = retained[0].event_id
    owner.flush_async()
    assert owner.shutdown(2)
    assert owner._worker is None and calls == [old_event, old_event]
    assert diagnostic == ["product telemetry delivery paused: OSError"] * 2

    # Simulate a locked outbox during revocation. A new consent epoch must
    # discard retained old data even after a failed sink is usable again.
    consent = AnalyticsConsentOwner(tmp_path)
    consent.choose(False)
    original_save = telemetry_module._save_outbox

    def locked(path, events):
        if not events:
            raise PermissionError("PRIVATE locked outbox")
        return original_save(path, events)

    with monkeypatch.context() as scoped:
        scoped.setattr(telemetry_module, "_save_outbox", locked)
        owner.set_enabled(False)
    assert (tmp_path / "events.json").exists()
    consent.choose(True)
    delivered = []
    owner._d1_recorder = lambda event: delivered.append(event) or True
    owner._heycatch_recorder = lambda *_args, **_fields: True
    owner.set_enabled(True)
    assert owner.shutdown(2) and owner._worker is None
    assert delivered == [] and not (tmp_path / "events.json").exists()
    assert owner.record("app_opened")
    assert owner.shutdown(2)
    assert len(delivered) == 1 and delivered[0].event_id != old_event
    assert delivered[0].consent_epoch == consent.snapshot()["collection_epoch"]


def test_exhausted_volume_budget_quick_close_emits_only_final_summary(
    tmp_path, monkeypatch
):
    holder = make_app(tmp_path, monkeypatch, consent=True)
    run_case(
        tmp_path / "provider",
        holder.product_telemetry,
        "command_flood",
        close_before_settle=True,
    )
    events = payloads(holder)
    volume = [event for event in events if event["action"].startswith("volume_")]
    assert len(volume) == 33
    assert volume[-1]["action"] == "volume_unresolved"
    assert volume[-1]["dimensions"]["volume_request"] == "202"
    assert events[-1]["action"] == "closed"
