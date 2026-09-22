"""Durable annotation ownership through actual retry/admission and storage faults."""

from dataclasses import replace

import pytest

from tests.test_library_action_diagnostics import diagnostic_rows
from tests.test_presentation_diagnostics import real_owner
from tests.test_preview_admission import prepared_app
from tests.test_state_authority import Value, make_job
from yt_downloader import library_annotations, run_state
from yt_downloader.history import load_history
from yt_downloader.library_annotations import LibraryAnnotation, LibraryAnnotationsOwner
from yt_downloader.library_state import ANNOTATION_OWNER_KEY, LibraryProjectionOwner
from yt_downloader.run_state import RunRecoveryOwner, deserialize_download_job

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")

ORIGINAL = LibraryAnnotation("PRIVATE saved note", ("research", "later"), "Learning")
EDITED = LibraryAnnotation("PRIVATE edited note", ("edited",), "Favorites")


def retry_app(tmp_path, monkeypatch, *, busy=True, status="Stopped"):
    app = prepared_app(tmp_path / "app", monkeypatch, busy=busy, hold_worker=False)
    app.library_projection = LibraryProjectionOwner()
    app.run_recovery = RunRecoveryOwner(tmp_path / "run-state.json")
    app._refresh_focus_run_deck = lambda: None
    app._append_job_log = lambda *_args: None
    app.history_path = tmp_path / "history.json"
    app.library_output_type_var = Value("MP4")
    previous = make_job(tmp_path, video_id="retry-subject")
    previous.terminal_status = status
    previous.preview_info = {
        "id": "retry-subject",
        "title": "PRIVATE retry subject",
        "webpage_url": previous.url,
        "vodforge_output_type": "MP4",
        "playlist_id": "PRIVATE playlist",
    }
    sibling = make_job(tmp_path, video_id="untouched-sibling")
    sibling.terminal_status = "Stopped"
    sibling.preview_info = {"id": "untouched-sibling", "vodforge_output_type": "MP4"}
    app._terminal_jobs = [previous, sibling]
    for job in app._terminal_jobs:
        app.run_recovery.terminal_attempt(job, job.terminal_status, "PRIVATE terminal")
    app.library_annotations.replace("run:" + previous.run_id, ORIGINAL)
    app.library_annotations.replace(
        "run:" + sibling.run_id, LibraryAnnotation("Sibling")
    )
    app._build_download_job_from_current_settings = lambda *_a, **_k: replace(previous)
    app._reconcile_library_projection()
    return app, previous, sibling


def writer_fault(code):
    def fail(*_a, **_k):
        raise OSError(code, "PRIVATE annotation /Users/private/notes.json")

    return fail


def submit_retry(app, previous, route):
    if route == "retry":
        app._retry_terminal_job(previous)
    else:
        replacement = replace(
            previous,
            run_id="automatic-replacement",
            terminal_status=None,
            admission_observer=None,
        )
        assert app._start_or_queue_download_job(replacement, clear_source=False)
    if app.worker is not None and hasattr(app.worker, "join"):
        app.worker.join(2)


def disk_projection(app, *, busy):
    recovery = RunRecoveryOwner(app.run_recovery.store.path)
    annotations = LibraryAnnotationsOwner(app.library_annotations.path)
    annotations.load()
    queued = recovery.store.load_queued_jobs()
    active = None if busy else deserialize_download_job(recovery.store.load()["job"])
    projection = LibraryProjectionOwner().reconcile(
        history_items=[],
        active_job=active,
        queued_jobs=queued,
        terminal_jobs=recovery.store.load_terminal_jobs(),
        annotations=annotations.snapshot,
    )
    row = next(row for row in projection.rows if row.get("id") == "retry-subject")
    return (queued[-1] if busy else active), annotations, row


@pytest.mark.parametrize("route", ["retry", "automatic"])
@pytest.mark.parametrize("busy", [True, False])
@pytest.mark.parametrize("status", ["Stopped", "Failed", "Skipped"])
@pytest.mark.parametrize("fault", [None, 13, 28])
def test_annotation_survives_admission_reload_and_edit(
    tmp_path, monkeypatch, route, busy, status, fault
):
    app, previous, sibling = retry_app(tmp_path, monkeypatch, busy=busy, status=status)
    app.product_telemetry = real_owner(tmp_path / "telemetry")
    before = app.library_annotations.path.read_bytes()
    with monkeypatch.context() as faults:
        if fault:
            faults.setattr(
                library_annotations, "write_private_bytes", writer_fault(fault)
            )
        submit_retry(app, previous, route)
    replacement, ledger, row = disk_projection(app, busy=busy)
    assert replacement.run_id != previous.run_id
    assert previous.run_id not in {job.run_id for job in app._terminal_jobs}
    assert row["vodforge_user_note"] == ORIGINAL.note
    assert tuple(row["vodforge_user_tags"]) == ORIGINAL.tags
    assert row["vodforge_user_category"] == ORIGINAL.category
    owner = row[ANNOTATION_OWNER_KEY]
    assert owner == "run:" + (previous.run_id if fault else replacement.run_id)
    if fault:
        assert app.library_annotations.path.read_bytes() == before
    ledger.replace(owner, EDITED)
    _, ledger, edited = disk_projection(app, busy=busy)
    assert edited["vodforge_user_note"] == EDITED.note
    assert tuple(edited["vodforge_user_tags"]) == EDITED.tags
    assert edited["vodforge_user_category"] == EDITED.category
    assert ledger.annotation_for("run:" + sibling.run_id).note == "Sibling"
    rows = diagnostic_rows(app, tmp_path)
    assert [row["action"] for row in rows] == (
        ["requested", "admitted", "annotation_retained", "completed"]
        if fault
        else ["requested", "admitted", "completed"]
    )
    if fault:
        event = rows[2]
        assert event["failure_reason"] == (
            "permission_denied" if fault == 13 else "disk_full"
        )
        assert event["failure_detail"]["os_error"] == fault
        assert event["failure_detail"]["source_module"] == "library_annotations"
        assert event["dimensions"]["library_boundary"] == "annotation"


@pytest.mark.parametrize("busy", [True, False])
@pytest.mark.parametrize("route", ["retry", "automatic"])
def test_refused_admission_preserves_prior_disk_ownership(
    tmp_path, monkeypatch, busy, route
):
    app, previous, _sibling = retry_app(tmp_path, monkeypatch, busy=busy)
    app.product_telemetry = real_owner(tmp_path / "telemetry")
    state_before = app.run_recovery.store.path.read_bytes()
    notes_before = app.library_annotations.path.read_bytes()
    with monkeypatch.context() as faults:
        faults.setattr(run_state, "write_private_bytes", writer_fault(13))
        if route == "retry":
            app._retry_terminal_job(previous)
        else:
            replacement = replace(previous, run_id="rejected-new", terminal_status=None)
            assert not app._start_or_queue_download_job(replacement, clear_source=False)
    assert app.run_recovery.store.path.read_bytes() == state_before
    assert app.library_annotations.path.read_bytes() == notes_before
    assert previous in app._terminal_jobs
    assert not app.pending_jobs
    assert [r["action"] for r in diagnostic_rows(app, tmp_path)] == [
        "requested",
        "rejected",
    ]


def test_repeated_retry_resolves_retained_owner_and_clear_does_not_resurrect(
    tmp_path, monkeypatch
):
    app, previous, sibling = retry_app(tmp_path, monkeypatch)
    with monkeypatch.context() as faults:
        faults.setattr(library_annotations, "write_private_bytes", writer_fault(13))
        submit_retry(app, previous, "retry")
    first, ledger, row = disk_projection(app, busy=True)
    ledger.replace(row[ANNOTATION_OWNER_KEY], EDITED)
    app.library_annotations = ledger
    first.terminal_status = "Stopped"
    app.pending_jobs = []
    app._terminal_jobs = [first, sibling]
    app.run_recovery.queue_changed([])
    app.run_recovery.terminal_attempt(first, "Stopped", "Stopped again")
    app._reconcile_library_projection()
    with monkeypatch.context() as faults:
        faults.setattr(library_annotations, "write_private_bytes", writer_fault(28))
        submit_retry(app, first, "retry")
    second, ledger, row = disk_projection(app, busy=True)
    assert second.annotation_source_owner == "run:" + previous.run_id
    assert row["vodforge_user_note"] == EDITED.note
    ledger.replace(row[ANNOTATION_OWNER_KEY], LibraryAnnotation())
    _, ledger, row = disk_projection(app, busy=True)
    assert "vodforge_user_note" not in row
    assert row[ANNOTATION_OWNER_KEY] == "run:" + second.run_id
    assert ledger.annotation_for("run:" + sibling.run_id).note == "Sibling"


@pytest.mark.parametrize("busy", [True, False])
def test_completion_history_preserves_retained_annotation_owner(
    tmp_path, monkeypatch, busy
):
    app, previous, sibling = retry_app(tmp_path, monkeypatch, busy=busy)
    with monkeypatch.context() as faults:
        faults.setattr(library_annotations, "write_private_bytes", writer_fault(13))
        submit_retry(app, previous, "retry")
    replacement, _ledger, _row = disk_projection(app, busy=busy)
    app._record_download_history(
        {
            **replacement.preview_info,
            "vodforge_output_path": str(tmp_path / "video.mp4"),
        },
        tmp_path,
        owning_job=replacement,
    )
    history = load_history(app.history_path)
    ledger = LibraryAnnotationsOwner(app.library_annotations.path)
    ledger.load()
    projection = LibraryProjectionOwner().reconcile(
        history_items=history,
        active_job=None,
        queued_jobs=[],
        terminal_jobs=[],
        annotations=ledger.snapshot,
    )
    row = projection.rows[0]
    assert row["vodforge_user_note"] == ORIGINAL.note
    assert row[ANNOTATION_OWNER_KEY] == "run:" + previous.run_id
    assert ledger.annotation_for("run:" + sibling.run_id).note == "Sibling"


def test_legacy_run_state_defaults_to_its_own_annotation_owner(tmp_path):
    job = make_job(tmp_path)
    payload = run_state.serialize_download_job(job)
    payload.pop("annotation_source_owner")
    assert deserialize_download_job(payload).annotation_source_owner is None


@pytest.mark.parametrize("busy", [True, False])
@pytest.mark.parametrize("fault", [None, 13])
def test_missing_media_uses_explicit_history_owner_over_matching_terminal(
    tmp_path, monkeypatch, busy, fault
):
    from yt_downloader.history import history_identity, save_history
    from yt_downloader.library_media_recovery import (
        LibraryMediaRecoveryOwner,
        LibraryMediaRecoveryPlan,
    )

    app, previous, sibling = retry_app(tmp_path, monkeypatch, busy=busy)
    prior_history_owner = "run:completed-history"
    app.library_annotations.replace(prior_history_owner, EDITED)
    missing = {
        "id": "retry-subject",
        "title": "Saved story",
        "vodforge_output_type": "MP4",
        "vodforge_run_id": "completed-history",
        "vodforge_output_dir": str(tmp_path / "missing"),
        "vodforge_output_path": str(tmp_path / "missing" / "clip.mp4"),
    }
    app.download_history = [missing]
    save_history(app.history_path, app.download_history)
    app.library_media_recovery = LibraryMediaRecoveryOwner()
    app._record_feature = lambda *_a, **_k: None
    replacement = replace(previous, run_id="missing-replacement", terminal_status=None)
    plan = LibraryMediaRecoveryPlan(
        "missing",
        tmp_path,
        job=replacement,
        replaced_history_identity=history_identity(missing),
        previous_annotation_owner=prior_history_owner,
    )
    with monkeypatch.context() as failures:
        if fault:
            failures.setattr(
                library_annotations, "write_private_bytes", writer_fault(fault)
            )
        app._accept_library_redownload(plan)
    if app.worker is not None and hasattr(app.worker, "join"):
        app.worker.join(2)
    replacement, ledger, row = disk_projection(app, busy=busy)
    assert replacement.annotation_source_owner == prior_history_owner
    assert row["vodforge_user_note"] == EDITED.note
    assert tuple(row["vodforge_user_tags"]) == EDITED.tags
    assert row["vodforge_user_category"] == EDITED.category
    assert load_history(app.history_path) == []
    assert ledger.annotation_for("run:" + previous.run_id) == ORIGINAL
    assert previous.run_id in {
        job.run_id for job in app.run_recovery.store.load_terminal_jobs()
    }
    assert ledger.annotation_for("run:" + sibling.run_id).note == "Sibling"


def test_retry_validation_cannot_adopt_later_consent(tmp_path, monkeypatch):
    from yt_downloader.analytics_consent import AnalyticsConsentOwner

    app, previous, _sibling = retry_app(tmp_path, monkeypatch, status="Failed")
    app.product_telemetry = real_owner(tmp_path / "telemetry")

    def regrant(*_a, **_k):
        consent = AnalyticsConsentOwner(tmp_path / "telemetry")
        consent.choose(False)
        app.product_telemetry.set_enabled(False)
        consent.choose(True)
        app.product_telemetry.set_enabled(True)
        return replace(previous)

    app._build_download_job_from_current_settings = regrant
    submit_retry(app, previous, "retry")
    assert diagnostic_rows(app, tmp_path) == []
