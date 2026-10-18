"""Committed media, optional issues and queue callbacks retain exact owners."""

from dataclasses import replace

from tests.test_qt_runtime_event_ownership import DormantThread
from tests.test_run_identity import make_job
from yt_downloader.models import DownloadOutcome
from yt_downloader.qt_quick import runtime as runtime_module
from yt_downloader.worker_events import history_record_event, job_info_event


def test_optional_sidecar_partial_commits_once_advances_queue_and_rejects_late_owner(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    monkeypatch.setattr(runtime_module.threading, "Thread", DormantThread)
    runtime = runtime_module.DownloadRuntime()
    first = make_job(tmp_path)
    first.url = "https://www.youtube.com/watch?v=fixture1&list=fictional"
    first.urls = [first.url]
    next_job = replace(
        first,
        run_id="next-independent",
        url="https://youtu.be/fixture2",
        urls=["https://youtu.be/fixture2"],
        activity_lines=[],
    )
    third = replace(next_job, run_id="third-independent", activity_lines=[])
    runtime.recovery.begin(first, [next_job, third])
    runtime.queued = [next_job, third]
    runtime._make_worker(first)
    worker = runtime._worker_app
    sink = worker.events
    path = tmp_path / "first.mp4"
    path.write_bytes(b"Durable first output remains unchanged")
    info = {
        "id": "fixture1",
        "title": "Same visible title",
        "playlist_id": "fictional",
        "vodforge_output_type": "MP4",
        "vodforge_output_path": str(path),
    }
    try:
        sink.put(job_info_event("job_metadata", first, info))
        sink.put(history_record_event(first, info, str(tmp_path)))
        sink.put(("progress", 100))
        worker._finish_download_run_outcome(
            first,
            DownloadOutcome(success_count=1, sidecar_failure_count=2),
            emit_done=True,
        )
        runtime.poll()
        assert runtime.active_job is next_job
        assert runtime.queued == [third]
        assert first.single_video_only and not first.batch_mode
        assert len(runtime.history) == len(runtime.recovered) == 1
        assert runtime.history[0]["vodforge_run_id"] == first.run_id
        assert runtime.recovered[0].run_id == first.run_id
        assert runtime.recovered[0].terminal_status == "Partial"
        assert "2 optional sidecar failure(s)" in runtime.recovered[0].terminal_message
        # Genuine stale callback envelopes from the completed worker cannot
        # add a second media record or reclassify the active successor.
        sink.put(("partial", "Late first-worker result"))
        sink.put(history_record_event(first, info, str(tmp_path)))
        sink.put(job_info_event("job_metadata", first, {**info, "id": "stale"}))
        assert runtime.poll() == []
        assert runtime.active_job is next_job
        assert len(runtime.history) == len(runtime.recovered) == 1
        next_path = tmp_path / "next.mp4"
        next_path.write_bytes(b"Independent next output")
        next_info = {**info, "id": "fixture2", "vodforge_output_path": str(next_path)}
        next_worker = runtime._worker_app
        next_worker.events.put(history_record_event(next_job, next_info, str(tmp_path)))
        next_worker._finish_download_run_outcome(
            next_job, DownloadOutcome(success_count=1), emit_done=True
        )
        runtime.poll()
        assert runtime.active_job is third
        assert len(runtime.history) == 2  # Same title, two real distinct outputs.
        assert {row["vodforge_run_id"] for row in runtime.history} == {
            first.run_id,
            next_job.run_id,
        }
        assert [job.run_id for job in runtime.recovered] == [first.run_id]
        assert path.read_bytes() == b"Durable first output remains unchanged"
    finally:
        runtime.close()
