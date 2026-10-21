"""Actual runtime + durable journal + blocked resource worker; no provider/network."""

import threading
from dataclasses import replace

import pytest

from tests.test_run_identity import make_job
from yt_downloader import run_state
from yt_downloader.process_lifecycle import ProcessOwnershipError
from yt_downloader.qt_quick.runtime import DownloadRuntime


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("same_output", [False, True])
def test_submit_while_recovery_inspection_blocks_is_durable_then_admitted_once(
    tmp_path, monkeypatch, cancel, same_output
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    job = replace(
        make_job(tmp_path / "out"),
        preview_info={"title": "Actual interrupted video", "channel": "Same channel"},
    )
    store = run_state.ActiveRunStore(run_state.run_state_file_path())
    store.begin(job)
    stage = job.output_dir / ".vfstage" / "preserved"
    stage.mkdir(parents=True)
    (stage / "media.part").write_bytes(b"untouched partial")
    store.add_staging_dir(job.run_id, stage)
    store.child_started(999991, ["ffmpeg", str(stage)], birth_time=123)
    entered, release = threading.Event(), threading.Event()
    calls = []

    def deny(children, stages):
        calls.append((children, stages))
        entered.set()
        assert release.wait(3)
        raise ProcessOwnershipError("Cannot inspect child") from PermissionError(
            13, "Fictional denial"
        )

    monkeypatch.setattr(run_state, "terminate_recorded_children", deny)
    runtime = DownloadRuntime()
    admitted = []

    def worker(next_job):
        assert not runtime._recovery_thread or not runtime._recovery_thread.is_alive()
        admitted.append(next_job.run_id)
        runtime.active_job = next_job
        runtime._reset_active_feedback(next_job)

    monkeypatch.setattr(runtime, "_make_worker", worker)
    try:
        assert runtime.recovery_pending
        runtime.resume_queued()
        assert entered.wait(2)
        first = replace(
            job,
            run_id="new-independent-run",
            output_dir=job.output_dir if same_output else tmp_path / "other",
        )
        runtime.start_job(first)
        assert not admitted and runtime.queued == [first]
        cold = run_state.ActiveRunStore(store.path)
        assert [j.run_id for j in cold.load_queued_jobs()] == [first.run_id]
        assert cold.load()["queue_waiting_for_recovery"] is True
        if cancel:
            assert runtime.cancel_recovery(job.run_id)
            runtime.poll()
            assert (
                not admitted
            )  # cancellation cannot promote while inspection is still in flight
        release.set()
        runtime._recovery_thread.join(2)
        runtime.poll()
        runtime.poll()
        assert admitted == [first.run_id]
        assert runtime.active_job is first
        record = cold.recovery_records()[0]
        assert record["recovery_state"] == ("cancelled" if cancel else "failed")
        assert record["ownership"]["children"][0]["pid"] == 999991
        assert (stage / "media.part").read_bytes() == b"untouched partial"
        assert len(calls) == 1
    finally:
        release.set()
        runtime.close()


def test_crash_with_waiting_submission_preserves_intent_and_never_repeats_failed_attempt(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    store = run_state.ActiveRunStore(run_state.run_state_file_path())
    job = make_job(tmp_path / "out")
    store.begin(job)
    store.prepare_recovery()
    store.claim_recovery(job.run_id)  # abrupt process death before result
    queued = replace(job, run_id="durably-waiting")
    store.replace_queue([queued])
    runtime = DownloadRuntime()
    admitted = []
    monkeypatch.setattr(
        runtime, "_make_worker", lambda job: admitted.append(job.run_id)
    )
    try:
        assert not runtime.recovery_pending
        assert runtime.resource_recoveries[job.run_id]["recovery_state"] == "failed"
        runtime.resume_queued()
        runtime.resume_queued()
        assert admitted == [queued.run_id]
        assert not store.load_queued_jobs()
        assert runtime._recovery_thread is None
    finally:
        runtime.close()


def test_settled_inspection_preserves_files_and_does_not_retry_on_every_start(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    store = run_state.ActiveRunStore(run_state.run_state_file_path())
    job = make_job(tmp_path / "out")
    store.begin(job)
    stage = job.output_dir / ".vfstage" / "retained"
    stage.mkdir(parents=True)
    (stage / "video.part").write_bytes(b"keep")
    store.add_staging_dir(job.run_id, stage)
    runtime = DownloadRuntime()
    runtime.resume_queued()
    runtime._recovery_thread.join(2)
    runtime.poll()
    assert runtime.resource_recoveries[job.run_id]["recovery_state"] == "ready"
    assert (stage / "video.part").read_bytes() == b"keep"
    runtime.close()
    reopened = DownloadRuntime()
    try:
        assert not reopened.recovery_pending
        reopened.resume_queued()
        assert reopened._recovery_thread is None
    finally:
        reopened.close()


def test_thread_start_failure_is_one_failed_attempt_with_explicit_retry(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    store = run_state.ActiveRunStore(run_state.run_state_file_path())
    job = make_job(tmp_path / "out")
    store.begin(job)
    runtime = DownloadRuntime()
    starts = []

    def unavailable(_thread):
        starts.append(1)
        raise RuntimeError("Fictional thread resource failure")

    monkeypatch.setattr(threading.Thread, "start", unavailable)
    try:
        runtime.resume_queued()
        assert starts == [1]
        assert not runtime.recovery_pending
        assert runtime.resource_recoveries[job.run_id]["recovery_state"] == "failed"
        runtime.resume_queued()
        assert starts == [1]
        assert runtime.retry_resource_recovery(job.run_id)
        assert starts == [1, 1]  # only the explicit Retry authorizes another attempt
        assert not runtime.recovery_pending
    finally:
        runtime.close()


@pytest.mark.parametrize("live", [True, False])
def test_another_live_recovery_owner_is_not_misclassified_as_a_crashed_attempt(
    tmp_path, monkeypatch, live
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    store = run_state.ActiveRunStore(run_state.run_state_file_path())
    job = make_job(tmp_path / "out")
    store.begin(job)
    store.prepare_recovery()
    store.claim_recovery(job.run_id)
    payload = store.load()
    record = payload["recovered_failures"][0]
    record.update(recovery_owner_pid=999992, recovery_owner_birth=123)
    store._write_unlocked(payload)
    before = store.path.read_bytes()
    monkeypatch.setattr(
        run_state, "process_command", lambda _pid: "owned app" if live else None
    )
    monkeypatch.setattr(run_state, "process_birth_time", lambda _pid: 123)
    runtime = DownloadRuntime()
    try:
        if live:
            assert runtime.recovery_notice
            assert store.path.read_bytes() == before
        else:
            assert not runtime.recovery_notice
            assert runtime.resource_recoveries[job.run_id]["recovery_state"] == "failed"
            assert not runtime.recovery_pending
    finally:
        runtime.close()


@pytest.mark.parametrize("birth", [float("nan"), float("inf"), True, -1])
def test_invalid_owner_birth_never_proves_pid_reuse(birth, monkeypatch):
    monkeypatch.setattr(run_state, "process_command", lambda _pid: "live")
    with pytest.raises(run_state.RunStateError):
        run_state.RunRecoveryOwner._other_live_owner(999992, birth)
