"""Durable annotation ownership through actual retry/admission and storage faults."""

from dataclasses import replace

import pytest

from tests.test_state_authority import make_job
from yt_downloader import run_state
from yt_downloader.library_annotations import LibraryAnnotation, LibraryAnnotationsOwner
from yt_downloader.library_state import LibraryProjectionOwner
from yt_downloader.run_state import RunRecoveryOwner, deserialize_download_job

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")

ORIGINAL = LibraryAnnotation("PRIVATE saved note", ("research", "later"), "Learning")
EDITED = LibraryAnnotation("PRIVATE edited note", ("edited",), "Favorites")


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


def test_legacy_run_state_defaults_to_its_own_annotation_owner(tmp_path):
    job = make_job(tmp_path)
    payload = run_state.serialize_download_job(job)
    payload.pop("annotation_source_owner")
    assert deserialize_download_job(payload).annotation_source_owner is None
