"""Cross-owner regression for the Tk-to-Qt download handoff."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from yt_downloader.app import DownloaderApp, DownloadWorkerCore
from yt_downloader.qt_quick import runtime as qt_runtime
from yt_downloader.run_state import ActiveRunStore


def test_tk_qt_and_harness_share_the_non_widget_worker() -> None:
    from quality_harness.pipeline import TracingQueue, make_headless_app

    headless = make_headless_app(TracingQueue())
    assert isinstance(headless, DownloadWorkerCore)
    assert not isinstance(headless, DownloaderApp)
    assert issubclass(DownloaderApp, DownloadWorkerCore)
    assert (
        DownloaderApp._download_worker_single
        is DownloadWorkerCore._download_worker_single
    )


def test_qt_queue_survives_stopped_attempt_and_starts_next(
    tmp_path: Path, monkeypatch: Any
) -> None:
    history_path = tmp_path / "download-history.json"
    state_path = tmp_path / "active-run.json"
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.setattr(qt_runtime, "history_file_path", lambda: history_path)
    monkeypatch.setattr(qt_runtime, "run_state_file_path", lambda: state_path)
    first_may_finish = threading.Event()

    def worker(self: DownloadWorkerCore, job: Any) -> None:
        if job.url.endswith("/first"):
            assert first_may_finish.wait(timeout=5)
            self.events.put(("stopped", "First stopped"))
        else:
            self.events.put(("done", "Second completed"))

    monkeypatch.setattr(DownloadWorkerCore, "_download_worker", worker)
    runtime = qt_runtime.DownloadRuntime()
    try:
        first = runtime.start(
            "https://example.com/first", output_dir, "MP4", "Everyday"
        )
        second = runtime.start(
            "https://example.com/second", output_dir, "MP3", "Everyday"
        )
        assert runtime.active_job is first
        assert [
            job.run_id for job in ActiveRunStore(state_path).load_queued_jobs()
        ] == [second.run_id]
        first_may_finish.set()
        terminal: list[str] = []
        deadline = time.monotonic() + 5
        while len(terminal) < 2 and time.monotonic() < deadline:
            terminal.extend(
                kind
                for kind, _payload in runtime.poll()
                if kind in {"done", "partial", "stopped", "error"}
            )
            time.sleep(0.01)
        assert terminal == ["stopped", "done"]
        assert runtime.active_job is None
        assert runtime.queued == []
        assert [
            job.run_id for job in ActiveRunStore(state_path).load_terminal_jobs()
        ] == [first.run_id]
    finally:
        first_may_finish.set()
        runtime.close()
