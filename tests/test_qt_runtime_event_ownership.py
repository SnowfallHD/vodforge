"""Actual worker sink callbacks belong to a job object, not a reused run ID."""

from dataclasses import replace

import pytest

from tests.test_run_identity import make_job
from yt_downloader.qt_quick import runtime as runtime_module


class DormantThread:
    def __init__(self, **kwargs):
        self.target = kwargs["target"]
        self.args = kwargs.get("args", ())

    def start(self):
        pass

    def is_alive(self):
        return False


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(runtime_module.threading, "Thread", DormantThread)
    owner = runtime_module.DownloadRuntime()
    try:
        yield owner
    finally:
        owner.close()


def launch(runtime, job):
    runtime.recovery.begin(job, [])
    runtime._make_worker(job)
    return runtime._worker_app.events


@pytest.mark.parametrize("terminal", ["done", "partial", "stopped", "error"])
def test_late_worker_callbacks_cannot_mutate_successor_with_same_run_id(
    runtime, tmp_path, terminal
):
    old = make_job(tmp_path)
    old_sink = launch(runtime, old)
    successor = replace(old, preview_info={"title": "Successor"}, activity_lines=[])
    assert successor is not old and successor.run_id == old.run_id
    sink = launch(runtime, successor)
    sink.put(("status", "Successor downloading"))
    sink.put(("progress", 23))
    runtime.poll()
    old_sink.put(("status", "Old run failed"))
    old_sink.put(("progress", 99))
    old_sink.put(("job_metadata", {"job": old, "info": {"title": "Stale"}}))
    old_sink.put(("job_log", {"job": old, "line": "Old log"}))
    old_sink.put(
        (
            "history_record",
            {"job": old, "info": {"id": "stale"}, "output_dir": str(tmp_path)},
        )
    )
    old_sink.put((terminal, "Old terminal result"))
    assert runtime.poll() == []
    assert runtime.active_job is successor
    assert runtime.active_status == "Successor downloading"
    assert runtime.active_progress == 23
    assert successor.preview_info == {"title": "Successor"}
    assert successor.activity_lines == []
    assert not runtime._history_error
    assert runtime.history == []
    assert runtime.recovered == []


def test_worker_promotion_resets_canonical_status_and_rejects_finished_sink(
    runtime, tmp_path
):
    first = make_job(tmp_path)
    first_sink = launch(runtime, first)
    next_job = replace(first, run_id="next-job", urls=["https://youtu.be/next"])
    runtime.recovery.queue_changed([next_job])
    runtime.queued = [next_job]
    first_sink.put(("status", "First finalizing"))
    first_sink.put(("progress", 100))
    first_sink.put(("done", "First completed"))
    assert runtime.poll()[-1] == ("done", "First completed")
    assert runtime.active_job is next_job
    assert runtime.active_status == "Preparing download"
    assert runtime.active_progress == 0
    first_sink.put(("status", "Late finalizing"))
    first_sink.put(("error", "Late failure"))
    assert runtime.poll() == []
    assert runtime.active_job is next_job


def test_owned_worker_events_preserve_payload_and_current_batch_child_log(
    runtime, tmp_path
):
    job = make_job(tmp_path)
    job.batch_mode = True
    sink = launch(runtime, job)
    child = replace(job, urls=[job.url])
    metadata = {"job": job, "info": {"title": "Current media"}}
    sink.put_nowait(("job_metadata", metadata))
    sink.put(("job_log", {"job": child, "line": "Current batch child"}))
    sink.put(("progress_determinate", None))
    sink.put(("status", "Transcoding"))
    sink.put(("progress", 41.5))
    events = runtime.poll()
    assert events == [
        ("job_metadata", metadata),
        ("log", "Current batch child"),
        ("progress_determinate", None),
        ("status", "Transcoding"),
        ("progress", 41.5),
    ]
    assert events[0][1] is metadata
    assert job.activity_lines == ["Current batch child"]
    assert job.preview_info == {"title": "Current media"}
    assert runtime.active_status == "Transcoding"
    assert runtime.active_progress == 41.5


def test_current_error_object_retains_action_and_durable_terminal(runtime, tmp_path):
    class FolderError(Exception):
        action = "choose_output_folder"

    job = make_job(tmp_path)
    sink = launch(runtime, job)
    error = FolderError("Choose another output folder")
    sink.put(("error", error))
    events = runtime.poll()
    assert events == [("error", error)]
    assert events[0][1] is error
    assert runtime.active_job is None
    assert runtime.active_status == ""
    assert runtime.active_progress == 0
    assert runtime.recovered[0].terminal_status == "Failed"
    assert runtime.recovered[0].terminal_message == str(error)
    sink.put(("status", "Late after terminal"))
    assert runtime.poll() == []


def test_manual_active_job_and_trusted_direct_events_remain_supported(
    runtime, tmp_path
):
    job = make_job(tmp_path)
    runtime.active_job = job
    assert runtime.active_status == "Preparing download"
    assert runtime.active_progress == 0
    runtime.events.put(("status", "Direct fixture status"))
    runtime.events.put(("progress", 18))
    assert runtime.poll() == [("status", "Direct fixture status"), ("progress", 18)]
    assert runtime.active_status == "Direct fixture status"
    assert runtime.active_progress == 18
    runtime.active_job = replace(job)
    assert runtime.active_status == "Preparing download"
    assert runtime.active_progress == 0


def test_owned_batch_history_and_item_terminal_keep_existing_identity_guards(
    runtime, tmp_path
):
    job = make_job(tmp_path)
    job.batch_mode = True
    job.urls = [job.url]
    sink = launch(runtime, job)
    batch_child = replace(job, urls=[job.url], activity_lines=["Saved batch child"])
    info = {"id": "abc123", "title": "Owned batch media"}
    sink.put(
        (
            "history_record",
            {"job": batch_child, "info": info, "output_dir": str(tmp_path)},
        )
    )
    terminal_child = replace(
        job,
        run_id="terminal-child",
        origin_run_id=job.run_id,
        execution_run_id=job.run_id,
        terminal_status="Skipped",
        terminal_message="Skipped child",
    )
    sink.put(
        (
            "item_terminal",
            {"job": terminal_child, "info": {"title": "Owned skipped child"}},
        )
    )
    sink.put(("log", "Plain worker log"))
    events = runtime.poll()
    assert [kind for kind, _ in events] == ["history_record", "item_terminal", "log"]
    assert runtime.active_job is job
    assert len(runtime.history) == 1
    assert runtime.history[0]["title"] == "Owned batch media"
    assert runtime.history[0]["vodforge_run_activity"] == ["Saved batch child"]
    assert runtime.recovered[0].run_id == terminal_child.run_id
    assert runtime.recovered[0].terminal_status == "Skipped"
