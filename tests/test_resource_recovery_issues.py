"""Protected resource issues survive a separate same-video active download."""

from dataclasses import replace

import pytest

from tests.test_qt_retry_recovery_membership import issue_rows
from tests.test_run_identity import make_job
from yt_downloader import run_state
from yt_downloader.qt_quick.runtime import DownloadRuntime


@pytest.mark.parametrize("outcome", ["failed", "cancelled", "ready"])
def test_protected_original_remains_identifiable_in_issues_beside_new_active_run(
    tmp_path, monkeypatch, outcome
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    store = run_state.ActiveRunStore(run_state.run_state_file_path())
    job = make_job(tmp_path / "output")
    job.preview_info = {
        "id": "abc123",
        "title": "Recovering video",
        "channel": "Creator",
        "playlist_title": "Playlist",
    }
    store.begin(job)
    store.prepare_recovery()
    token = store.claim_recovery(job.run_id)
    if outcome == "cancelled":
        store.cancel_recovery(job.run_id)
        store.release_recovery_claim(job.run_id, token)
    else:
        store.finish_recovery(
            job.run_id, outcome, "Protected resource receipt", token=token
        )
    runtime = DownloadRuntime()
    monkeypatch.setattr(
        runtime, "_make_worker", lambda job: setattr(runtime, "active_job", job)
    )
    try:
        runtime.start_job(replace(job, run_id="separate-execution"))
        rows = issue_rows(runtime)
        assert len(rows) == 1
        assert rows[0]["vodforge_terminal_run_id"] == job.run_id
        assert rows[0]["title"] == "Recovering video"
        assert (
            rows[0]["vodforge_terminal_status"]
            == {"failed": "Failed", "cancelled": "Stopped", "ready": "Paused"}[outcome]
        )
        assert runtime.active_job.run_id == "separate-execution"
    finally:
        runtime.close()
