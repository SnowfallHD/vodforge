from __future__ import annotations

import pytest

from tests.test_history_diagnostics import make_app

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


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
