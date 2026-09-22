"""Actual admission/removal producers, durable queue and private outbox."""

from __future__ import annotations

import json
from types import MethodType

import pytest

from tests.test_presentation_diagnostics import real_owner
from tests.test_preview_admission import prepared_app, submit
from yt_downloader import app as app_module
from yt_downloader.analytics_consent import AnalyticsConsentOwner
from yt_downloader.app import DownloaderApp
from yt_downloader.product_telemetry import _load_outbox
from yt_downloader.run_state import RunRecoveryOwner

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


def setup(tmp_path, monkeypatch, *, busy=True):
    app = prepared_app(tmp_path / "app", monkeypatch, busy=busy, hold_worker=False)
    app.run_recovery = RunRecoveryOwner(tmp_path / "run-state.json")
    app.product_telemetry = real_owner(tmp_path / "telemetry")
    app._record_queue_event = MethodType(DownloaderApp._record_queue_event, app)
    return app


def diagnostic_rows(app, tmp_path):
    assert app.product_telemetry.shutdown(2)
    rows = [
        event.public_payload()
        for event in _load_outbox(tmp_path / "telemetry/events.json")
    ]
    encoded = json.dumps(rows)
    assert "Private" not in encoded and str(tmp_path) not in encoded
    assert "https://" not in encoded
    return [row for row in rows if row.get("feature") == "library_action_operation"]


@pytest.mark.parametrize("route", ["library", "forge"])
@pytest.mark.parametrize("busy", [False, True])
def test_durable_admission_has_an_ordered_context_and_completion(
    tmp_path, monkeypatch, route, busy
):
    app = setup(tmp_path, monkeypatch, busy=busy)
    submit(app, route)
    rows = diagnostic_rows(app, tmp_path)
    assert [row["action"] for row in rows] == ["requested", "admitted", "completed"]
    assert len({row["dimensions"]["operation_id"] for row in rows}) == 1
    assert [row["dimensions"]["operation_step"] for row in rows] == ["1", "2", "3"]
    assert rows[1]["dimensions"]["library_boundary"] == ("queue" if busy else "launch")
    assert rows[0]["dimensions"]["library_subject"] == (
        "preview" if route == "library" else "source"
    )
    if busy:
        assert (
            app.run_recovery.store.load_queued_jobs()[0].run_id == app.built_job.run_id
        )
    else:
        app.worker.join(2)
        assert not app.worker.is_alive()


@pytest.mark.parametrize("busy", [False, True])
def test_persistence_refusal_records_no_admission_or_start(tmp_path, monkeypatch, busy):
    app = setup(tmp_path, monkeypatch, busy=busy)

    def denied(*_args, **_kwargs):
        raise app_module.RunStateError("PRIVATE persistence location")

    monkeypatch.setattr(app.run_recovery, "queue_changed" if busy else "begin", denied)
    submit(app, "library")
    rows = diagnostic_rows(app, tmp_path)
    assert [row["action"] for row in rows] == ["requested", "rejected"]
    assert rows[-1]["dimensions"]["library_boundary"] == ("queue" if busy else "launch")
    assert not app.run_recovery.store.load_queued_jobs()
    assert app.active_job is not app.built_job
    assert not any(
        event.event_name == "run_started"
        for event in _load_outbox(tmp_path / "telemetry/events.json")
    )


def test_later_preview_failure_cannot_erase_durable_admission_evidence(
    tmp_path, monkeypatch
):
    app = setup(tmp_path, monkeypatch)

    def fail(*_args):
        raise RuntimeError("PRIVATE preview scheduling failure")

    app._enqueue_queue_preview = fail
    with pytest.raises(RuntimeError):
        submit(app, "library")
    rows = diagnostic_rows(app, tmp_path)
    assert [row["action"] for row in rows] == ["requested", "admitted"]
    assert app.run_recovery.store.load_queued_jobs()[0].run_id == app.built_job.run_id


def test_annotation_failure_is_retention_after_admission_not_refusal(
    tmp_path, monkeypatch
):
    app = setup(tmp_path, monkeypatch)

    def fail(*_args):
        raise app_module.LibraryAnnotationsError("PRIVATE annotation path")

    monkeypatch.setattr(app.library_annotations, "transfer", fail)
    submit(app, "library")
    rows = diagnostic_rows(app, tmp_path)
    assert [row["action"] for row in rows] == [
        "requested",
        "admitted",
        "annotation_retained",
        "completed",
    ]
    assert rows[2]["dimensions"]["library_boundary"] == "annotation"
    assert app.run_recovery.store.load_queued_jobs()[0].run_id == app.built_job.run_id


def test_consent_change_inside_validation_never_rebinds_the_original_operation(
    tmp_path, monkeypatch
):
    app = setup(tmp_path, monkeypatch)

    def regrant(*_args, **_kwargs):
        consent = AnalyticsConsentOwner(tmp_path / "telemetry")
        consent.choose(False)
        app.product_telemetry.set_enabled(False)
        consent.choose(True)
        app.product_telemetry.set_enabled(True)
        return app.built_job

    app._build_download_job_from_current_settings = regrant
    submit(app, "library")
    assert diagnostic_rows(app, tmp_path) == []


@pytest.mark.parametrize("busy", [False, True])
@pytest.mark.parametrize("code,reason", [(13, "permission_denied"), (28, "disk_full")])
def test_actual_chained_persistence_cause_is_bounded(
    tmp_path, monkeypatch, busy, code, reason
):
    from yt_downloader import run_state

    app = setup(tmp_path, monkeypatch, busy=busy)

    def fail(*_a, **_k):
        raise OSError(code, "PRIVATE cause /Users/private.mp4")

    monkeypatch.setattr(run_state, "write_private_bytes", fail)
    submit(app, "library")
    rows = diagnostic_rows(app, tmp_path)
    assert [row["action"] for row in rows] == ["requested", "rejected"]
    assert rows[-1]["failure_reason"] == reason
    assert rows[-1]["failure_detail"]["os_error"] == code
    assert rows[-1]["failure_detail"]["source_module"] == "run_state"
    assert rows[-1]["failure_detail"]["stage"] == "dispatch"
    assert not app.run_recovery.store.load_queued_jobs()
