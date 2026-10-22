"""Explicit local diagnostics are isolated and contain geometry, never UI contents."""

import json
import os
import sys
from types import SimpleNamespace

import pytest

from yt_downloader.qt_quick.mac_header import (
    header_timeline_sample,
    validate_header_timeline,
)


@pytest.mark.parametrize("current", [False, True])
def test_header_trace_uses_current_native_geometry_and_closed_field_set(current):
    geometry = [0.0] * 98
    geometry[27:31] = [5, 8, 1400, 44]
    geometry[82:86] = [5, 8, 1400, 44]
    packet = {"host_screen": [0, 0, 1400, 44], "private_text": "NOT_FOR_TRACE"}
    values = {"nativeRowPacket": packet, "nativeHeaderInputReady": False}
    owner = SimpleNamespace(
        retired=False,
        _host=SimpleNamespace(snapshot=lambda: (1, 1793 if current else 1, geometry)),
    )
    window = SimpleNamespace(
        property=values.get,
        devicePixelRatio=lambda: 2,
        _native_header_diagnostic={"stage": "native_header_pending_alignment"},
        _native_window_controls=owner,
    )
    header = SimpleNamespace(property=lambda name: 3, x=lambda: 2)
    row = header_timeline_sample(window, header)
    assert row["actual_screen_x"] == (10 if current else None)
    assert row["input_ready"] is False
    assert "NOT_FOR_TRACE" not in json.dumps(row)
    assert set(row) == {
        "alignment",
        "input_ready",
        "packet_host",
        "packet_content",
        "packet_transition",
        "packet_state",
        "target_x",
        "animated_x",
        "inset",
        "native_host",
        "native_child",
        "actual_screen_x",
        "device_pixel_ratio",
    }


@pytest.mark.skipif(sys.platform != "darwin", reason="Mac-only native QA gate")
@pytest.mark.parametrize(
    "invalid", ["normal-home", "telemetry", "outside", "existing", None]
)
def test_header_trace_gate_precedes_profile_mutation(tmp_path, monkeypatch, invalid):
    import pwd

    home = tmp_path / "home"
    path = tmp_path / "trace.jsonl"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    if invalid == "normal-home":
        monkeypatch.setenv("HOME", pwd.getpwuid(os.getuid()).pw_dir)
    elif invalid == "telemetry":
        monkeypatch.delenv("VODFORGE_DISABLE_TELEMETRY")
    elif invalid == "outside":
        path = tmp_path / "outside" / "trace.jsonl"
    elif invalid == "existing":
        path.write_text("preserve")
    if invalid:
        with pytest.raises((RuntimeError, FileExistsError)):
            validate_header_timeline(path)
    else:
        assert validate_header_timeline(path) == path
    assert not home.exists()
    assert (
        path.read_text() == "preserve" if invalid == "existing" else not path.exists()
    )


@pytest.mark.skipif(sys.platform != "darwin", reason="Mac-only native QA gate")
def test_header_trace_timer_is_local_and_stops_at_elapsed_bound(tmp_path, monkeypatch):
    import time

    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtQuick import QQuickItem, QQuickWindow
    from PySide6.QtTest import QTest

    from tests.test_qt_scene_port import qt_app
    from yt_downloader.qt_quick.mac_header import start_header_timeline

    app = qt_app()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    window = QQuickWindow()
    header = QQuickItem(window.contentItem())
    header.setObjectName("focusHeader")
    path = tmp_path / "timeline.jsonl"
    timer, finish = start_header_timeline(window, path)
    try:
        QTest.qWait(65)
        finish()
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        assert rows and all(row["actual_screen_x"] is None for row in rows)
        assert not timer.isActive()
        next_timer, next_finish = start_header_timeline(
            window, tmp_path / "bounded.jsonl"
        )
        with monkeypatch.context() as context:
            now = time.monotonic()
            context.setattr(time, "monotonic", lambda: now + 121)
            next_timer.timeout.emit()
        assert not next_timer.isActive()
        next_finish()
        assert (tmp_path / "bounded.jsonl").read_text() == ""
    finally:
        finish()
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
