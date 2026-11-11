"""A download that doesn't stop within the quit wait still records its end.

Closing waits up to 10 s for the download worker. If it is still running, its
end is never handled, so the run had a "started" event and no outcome.
"""

from __future__ import annotations

from tests.test_run_identity import make_job
from yt_downloader.qt_quick import runtime as runtime_module


class StuckWorker:
    """A worker thread that is still running after the quit wait."""

    def is_alive(self):
        return True

    def join(self, timeout=None):
        pass


def test_download_still_running_at_quit_is_recorded_as_stopped(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    runtime = runtime_module.DownloadRuntime()
    recorded = []

    class Telemetry:
        def record(self, event_name, **fields):
            recorded.append((event_name, fields["dimensions"].get("outcome")))
            return True

    runtime.product_telemetry = Telemetry()
    runtime.active_job = make_job(tmp_path)
    runtime.worker = StuckWorker()
    runtime.close()
    assert recorded == [("run_stopped", "stopped")]
