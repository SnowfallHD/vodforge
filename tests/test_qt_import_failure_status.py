"""Real Qt bridge terminal import status retains actionable bounded failures."""

import time
from types import SimpleNamespace

import pytest

from tests.test_qt_scene_port import qt_app
from yt_downloader.library_import import ImportFailure
from yt_downloader.qt_quick import main as qt_main


@pytest.mark.parametrize(
    "outcome", ["inspection", "partial", "publication", "recovery"]
)
def test_terminal_import_keeps_failure_advice_and_successes(
    tmp_path, monkeypatch, outcome
):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    _app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._timer.stop()
    try:
        media = tmp_path / "fixture.mp4"
        media.write_bytes(b"preserved fixture")
        record = {
            "id": "local-" + "a" * 32,
            "title": "Fixture",
            "vodforge_output_path": str(media),
            "vodforge_output_type": "MP4",
        }
        completed = [] if outcome == "inspection" else [record]
        failures = (
            [
                ImportFailure(
                    "missing.mp4",
                    "This file is no longer available. Locate or restore it, then import again.",
                )
            ]
            if outcome in {"inspection", "partial"}
            else []
        )
        result = SimpleNamespace(value=(completed, failures), error=None)
        bridge._import_work.close()
        bridge._import_work = SimpleNamespace(poll=lambda: result, close=lambda: None)
        bridge._import_pending = True
        bridge._import_request_count = 2 if outcome == "partial" else 1
        bridge._import_started_at = time.monotonic()
        bridge._import_operation = None
        before = list(bridge._runtime.history)
        if outcome == "publication":

            def fail(*args, **kwargs):
                raise PermissionError("private path and raw exception must not appear")

            monkeypatch.setattr(qt_main, "commit_imports", fail)
        if outcome == "recovery":
            bridge._runtime.recovery_notice = "fixture pending recovery"
        bridge._pump()
        assert media.read_bytes() == b"preserved fixture"
        if outcome in {"inspection", "partial"}:
            assert (
                "missing.mp4" in bridge.status
                and "no longer available" in bridge.status
            )
        elif outcome == "publication":
            assert "access" in bridge.status and "private path" not in bridge.status
        else:
            assert "Finish Library recovery" in bridge.status
        if outcome == "partial":
            assert len(bridge._runtime.history) == len(before) + 1
            assert "Added 1 file" in bridge.status
        else:
            assert bridge._runtime.history == before
    finally:
        bridge.close()
