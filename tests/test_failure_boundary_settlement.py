"""Private fault-injection reproductions; regressions from independently confirmed fault paths."""

import threading
from dataclasses import replace
from pathlib import Path

import pytest

from tests.test_run_identity import make_job
from yt_downloader import run_state
from yt_downloader.qt_quick.runtime import DownloadRuntime


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    return DownloadRuntime()


def test_download_thread_start_failure_settles_then_next_job_runs(
    runtime, tmp_path, monkeypatch
):
    job = make_job(tmp_path / "out")

    def fail(_):
        raise RuntimeError("can't start new thread")

    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, "start", fail)
        with pytest.raises(RuntimeError):
            runtime.start_job(job)
    assert runtime.active_job is None and not runtime.busy
    assert runtime.recovery.store.load()["state"] != "active"
    assert runtime.recovered[0].terminal_status == "Failed"
    admitted = []
    monkeypatch.setattr(runtime, "_make_worker", lambda j: admitted.append(j.run_id))
    queued = replace(job, run_id="queued", output_dir=tmp_path / "other")
    runtime.start_job(queued)
    assert admitted == ["queued"]


def test_output_resolution_failure_becomes_global_recovery_lockout(
    runtime, tmp_path, monkeypatch
):
    job = make_job(tmp_path / "out")
    runtime.recovery.store.begin(job)
    runtime.recovered, runtime.queued = runtime.recovery.prepare_startup()
    # prepare_startup already ran once at construction; simulate fresh startup.
    runtime.recovery.store._preparation_done = False
    runtime.recovered, runtime.queued = runtime.recovery.prepare_startup()
    runtime._refresh_resource_recoveries()
    queued = replace(job, run_id="queued", output_dir=tmp_path / "other")
    runtime.start_job(queued)
    admitted = []

    def worker(j):
        admitted.append(j.run_id)
        runtime.active_job = j

    monkeypatch.setattr(runtime, "_make_worker", worker)
    original = Path.resolve

    def deny(path, *args, **kwargs):
        if path == job.output_dir:
            raise PermissionError(13, "fixture output traversal denied")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "resolve", deny)
        runtime.resume_queued()
        runtime._recovery_thread.join(3)
        assert not runtime._recovery_thread.is_alive()
        runtime.poll()
    row = runtime.recovery.store.recovery_records()[0]
    assert row["recovery_state"] == "failed"
    assert row["recovery_inflight"] is False
    assert not runtime.recovery_notice and not runtime.recovery_pending
    assert admitted == ["queued"]
    runtime.active_job = None
    assert runtime.retry_resource_recovery(job.run_id)
    if runtime._recovery_thread:
        runtime._recovery_thread.join(3)
    runtime.poll()


def test_cleanup_permission_error_leaks_provider_intent(tmp_path, monkeypatch):
    from tests.worker_fixtures import (
        _worker_test_app,
        _worker_test_export_plan,
        _worker_test_job,
    )
    from yt_downloader import download_service as app

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(app, "write_diagnostic", lambda *_: None)
    worker = _worker_test_app()
    job = _worker_test_job(tmp_path / "out")
    info = {"id": "abc123", "title": "Video", "channel": "Creator"}
    analyzed = app._AnalyzedDownloadItem(
        preflight_info=info,
        display_info=info,
        plan=_worker_test_export_plan(),
        session_cookies=(),
        cookie_source_loaded=False,
    )
    coordinator = app.ProviderNetworkCoordinator()
    source = app._DownloadSourceContext(
        ytdlp_module=object(),
        provider_network=coordinator,
        playlist_info={},
        max_height=1080,
    )
    item = app._DownloadItemContext(
        entry=info, index=1, total=1, video_url=job.url, label="Video"
    )
    result = app._DownloadItemResult(
        outcome=app.DownloadOutcome(),
        analysis=analyzed,
        metadata=info,
        plan=analyzed.plan,
    )
    stage = job.output_dir / ".vfstage" / "fixture"
    stage.mkdir(parents=True)
    (stage / "keep.part").write_bytes(b"keep")
    monkeypatch.setattr(app, "create_staging_dir", lambda *_: stage)

    def download_failed(*args, **kwargs):
        raise OSError("fixture transfer failure")

    worker._download_item_to_staging = download_failed
    original = Path.lstat

    def denied(path, *args, **kwargs):
        if path == stage:
            raise PermissionError(13, "fixture cleanup traversal denied")
        return original(path, *args, **kwargs)

    coordinator.begin_primary()
    with monkeypatch.context() as patch:
        patch.setattr(Path, "lstat", denied)
        with pytest.raises(app._DownloadItemExecutionError) as caught:
            worker._complete_staged_download_item(job, source, item, result)
        assert isinstance(caught.value.__cause__, OSError)
        assert str(caught.value.__cause__) == "fixture transfer failure"
    assert coordinator._primary_intents == 0
    assert coordinator._primary_operations == 0
    assert (stage / "keep.part").read_bytes() == b"keep"
    # No primary work remains; a real preview reservation can execute again.
    calls = []
    assert coordinator.run_preview(
        lambda: calls.append("ran"), should_abort=lambda: False
    ) == (True, None)
    assert calls == ["ran"]


@pytest.mark.parametrize(
    "outcome,kind",
    [
        ({"success_count": 0}, "stopped"),
        ({"success_count": 1, "sidecar_failure_count": 1}, "partial"),
        ({"success_count": 1}, "done"),
    ],
)
def test_terminal_outcome_counterexamples(tmp_path, outcome, kind):
    from tests.worker_fixtures import _worker_test_app, _worker_test_job
    from yt_downloader import download_service as app

    worker = _worker_test_app()
    worker._finish_download_run_outcome(
        _worker_test_job(tmp_path), app.DownloadOutcome(**outcome), emit_done=True
    )
    events = []
    while not worker.events.empty():
        events.append(worker.events.get_nowait())
    assert events[-1][0] == kind


@pytest.mark.parametrize("ready", [False, True])
def test_update_thread_start_failure_releases_busy_and_retains_ready(
    monkeypatch, tmp_path, ready
):
    from yt_downloader.qt_quick.update_session import QtUpdateSession

    session = QtUpdateSession("0.2.6")
    payload = tmp_path / "verified.zip" if ready else None
    session.ready = payload
    session._ready_digest = "verified" if ready else None

    def fail(_):
        raise RuntimeError("can't start new thread")

    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, "start", fail)
        assert session.check() is False
    assert not session.busy and session.worker is None
    assert session.ready == payload
    assert session._ready_digest == ("verified" if ready else None)
    assert session.check_failed
    assert session.take_observations() == [("failed", {"update_stage": "check"})]
    monkeypatch.setattr(
        session,
        "_check_worker",
        lambda: session.events.put(("error", ("fixture", None))),
    )
    assert session.check()
    session.worker.join(3)
    session.poll()
    assert not session.busy


@pytest.mark.parametrize("boundary", ["finish_recovery", "release_recovery_claim"])
def test_real_recovery_persistence_failure_still_blocks_admission(
    runtime, tmp_path, monkeypatch, boundary
):
    job = make_job(tmp_path / "out")
    runtime.recovery.store.begin(job)
    runtime.recovery.store._preparation_done = False
    runtime.recovered, runtime.queued = runtime.recovery.prepare_startup()
    runtime._refresh_resource_recoveries()

    def fail(*a, **kw):
        raise run_state.RunStateError("fixture journal write denied")

    monkeypatch.setattr(runtime.recovery.store, boundary, fail)
    runtime.resume_queued()
    runtime._recovery_thread.join(3)
    runtime.poll()
    assert runtime.recovery_notice
    with pytest.raises(run_state.RunStateError):
        runtime.start_job(replace(job, run_id="new", output_dir=tmp_path / "other"))
    assert runtime.active_job is None


def test_download_start_settlement_failure_retains_owned_slot_and_queue(
    runtime, tmp_path, monkeypatch
):
    job = make_job(tmp_path / "out")
    other = replace(job, run_id="queued", output_dir=tmp_path / "other")
    runtime.queued = [other]
    runtime.recovery.queue_changed([other])

    def fail_start(_):
        raise RuntimeError("fixture thread start failure")

    def fail_terminal(*a, **kw):
        raise run_state.RunStateError("fixture terminal write denied")

    monkeypatch.setattr(threading.Thread, "start", fail_start)
    monkeypatch.setattr(runtime.recovery, "terminal", fail_terminal)
    with pytest.raises(run_state.RunStateError):
        runtime._launch(job)
    assert runtime.active_job is job and runtime.queued == [other]
    assert (
        runtime.recovery_notice and runtime.recovery.store.load()["state"] == "active"
    )
    assert [j.run_id for j in runtime.recovery.store.load_queued_jobs()] == ["queued"]
