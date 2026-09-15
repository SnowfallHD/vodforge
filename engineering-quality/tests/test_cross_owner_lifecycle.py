"""Cross-subsystem lifecycle invariants: delayed effects are not completed effects.

Fault schedules exercise existing production owners, not a toy state machine.
Player readiness/replace/close cases live in test_playback_control_lifecycle.
"""

from itertools import product

import pytest

from tests.conftest import production_telemetry_contract  # noqa: F401 - shared fixture
from tests.test_product_telemetry import _permitted_installation
from tests.test_settings_store import _Scheduler, _Variable
from yt_downloader import settings_store
from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox


@pytest.mark.parametrize("values", list(product(("MP4", "MP3"), repeat=3)))
@pytest.mark.parametrize("fail_first", [False, True])
def test_latest_intent_survives_debounce_and_failed_commit(
    tmp_path, monkeypatch, values, fail_first
):
    path = tmp_path / "settings.json"
    observations = []
    variable = _Variable(values[0])
    scheduler = _Scheduler()
    owner = settings_store.SettingsPersistenceOwner(path, on_saved=observations.append)
    owner.bind(scheduler, {"output_type": variable})
    real_save = settings_store.save_settings

    def fail(*_args):
        raise settings_store.SettingsError("injected durable-write failure")

    for value in values:
        variable.value = value
        variable.callback()
    assert len(scheduler.pending) == 1, (
        "Debounce must have one authoritative pending commit"
    )
    if fail_first:
        monkeypatch.setattr(settings_store, "save_settings", fail)
        owner.flush()
        assert observations == [] and not path.exists(), (
            "Failed write must not report success"
        )
        monkeypatch.setattr(settings_store, "save_settings", real_save)
    owner.flush()
    assert settings_store.load_settings(path) == {"output_type": values[-1]}
    assert observations == [{"output_type": values[-1]}]
    assert scheduler.pending == {}


@pytest.mark.usefixtures("production_telemetry_contract")
@pytest.mark.parametrize("failed_deliveries", [0, 1, 3])
@pytest.mark.parametrize("withdraw", [False, True])
def test_retry_and_permission_order_preserve_identity_without_false_delivery(
    tmp_path, failed_deliveries, withdraw
):
    _permitted_installation(tmp_path / "installation.json")
    sent = []

    def deliver(event):
        sent.append(event.public_payload())
        return len(sent) > failed_deliveries

    path = tmp_path / "events.json"
    owner = ProductTelemetryOwner(
        state_path=path,
        installation_state_path=tmp_path / "installation.json",
        app_version="0.2.2",
        d1_recorder=deliver,
        heycatch_recorder=lambda *_a, **_k: True,
    )
    assert owner.record_app_opened()
    assert owner.shutdown(2)
    if failed_deliveries:
        assert not _load_outbox(path)[0].d1_delivered
    if withdraw:
        before = len(sent)
        owner.set_enabled(False)
        assert not owner.record_app_opened()
        owner.flush_async()
        assert owner.shutdown(2)
        assert len(sent) == before and not path.exists()
    else:
        for _ in range(failed_deliveries):
            assert owner.record_app_opened()
            assert owner.shutdown(2)
        assert not path.exists()
        before = len(sent)
        assert owner.record_app_opened()
        assert owner.shutdown(2)
        assert len(sent) == before, (
            "A completed effect cannot be recreated by duplicate callbacks"
        )
    assert len({event["event_id"] for event in sent}) == 1
    assert len({event["occurred_at"] for event in sent}) == 1
