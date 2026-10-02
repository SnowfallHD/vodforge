"""Retry recovery membership follows terminal lineage, independently of entry UI."""

from dataclasses import replace

import pytest

from tests.test_run_identity import make_job
from yt_downloader.archive_browser import _is_issue_without_export
from yt_downloader.library_state import LibraryProjectionOwner
from yt_downloader.qt_quick.runtime import DownloadRuntime


def issue_rows(runtime):
    rows = (
        LibraryProjectionOwner()
        .reconcile(
            history_items=runtime.history,
            active_job=runtime.active_job,
            queued_jobs=runtime.queued,
            terminal_jobs=runtime.recovered,
            annotations={},
        )
        .rows
    )
    return [row for row in rows if _is_issue_without_export(row, None)]


@pytest.mark.parametrize("queued", [False, True])
@pytest.mark.parametrize("ending", ["done", "error", "stopped"])
def test_forge_retry_lifecycle(tmp_path, monkeypatch, queued, ending):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    runtime = DownloadRuntime()
    failed = make_job(tmp_path)
    runtime.recovery.terminal_attempt(failed, "Failed", "Original failure")
    runtime.recovered = runtime.recovery.store.load_terminal_jobs()
    if queued:
        active = replace(
            make_job(tmp_path),
            run_id="other",
            url="https://youtu.be/other",
            urls=["https://youtu.be/other"],
        )
        runtime.recovery.begin(active, [])
        runtime.active_job = active
    monkeypatch.setattr(
        runtime, "_make_worker", lambda job: setattr(runtime, "active_job", job)
    )
    url = runtime.terminal_retry_source(failed.run_id)[1]
    current = replace(make_job(tmp_path), url=url, urls=[url])
    retry = runtime.retry_terminal(failed.run_id, current_job=current)
    assert retry.run_id != failed.run_id
    assert retry.retry_of_run_id == failed.run_id
    assert retry.origin_run_id == failed.run_id
    assert len(issue_rows(runtime)) == 1
    if queued:
        restored = runtime.recovery.store.load_queued_jobs()
        assert restored[0].preview_info["vodforge_issue_retry"] is True
        runtime.active_job = None
        runtime._launch_next_queued()
    runtime.events.put(("job_metadata", {"job": retry, "info": {"title": "Fresh"}}))
    runtime.poll()
    assert len(issue_rows(runtime)) == 1
    runtime._finish(ending, "Final outcome")
    after = DownloadRuntime()
    assert len(after.recovered) == (0 if ending == "done" else 1)
    assert not after.queued
    assert len(issue_rows(after)) == (0 if ending == "done" else 1)
    runtime.close()
    after.close()


def test_ordinary_job_excluded(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    runtime = DownloadRuntime()
    runtime.active_job = make_job(tmp_path)
    runtime.events.put(
        ("job_metadata", {"job": runtime.active_job, "info": {"title": "Ordinary"}})
    )
    runtime.poll()
    assert not issue_rows(runtime)
    runtime.active_job = None
    runtime.close()


def test_legacy_queued_retry_membership_derived_from_lineage(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    runtime = DownloadRuntime()
    job = replace(make_job(tmp_path), origin_run_id="prior", retry_of_run_id="prior")
    runtime.recovery.queue_changed([job])
    restored = DownloadRuntime()
    assert restored.queued[0].retry_of_run_id == "prior"
    assert len(issue_rows(restored)) == 1
    runtime.close()
    restored.close()
