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
        "native_endpoint_geometry",
        "native_presentation",
    }
    if current:
        endpoint = row["native_endpoint_geometry"]
        assert set(endpoint) == {
            "view_bounds",
            "host_in_own_window",
            "content_layout",
            "main_frame",
            "presentation_flags",
            "control_bounds",
            "fullscreen_transition",
            "measured_endpoint_offsets",
        }
        assert endpoint["fullscreen_transition"] is None
        assert endpoint["host_in_own_window"] == [0, 0, 0, 0]
    else:
        assert row["native_endpoint_geometry"] is None


def test_endpoint_trace_unknown_measurements_are_json_null_not_inferred():
    geometry = [float("nan")] * 98
    geometry[27:31] = geometry[82:86] = [5, 8, 1400, 44]
    host = SimpleNamespace(
        snapshot=lambda: (1, 1793, geometry),
        _row=SimpleNamespace(transition=0),
    )
    window = SimpleNamespace(
        property=lambda name: {} if name == "nativeRowPacket" else False,
        devicePixelRatio=lambda: 2,
        _native_window_controls=SimpleNamespace(retired=False, _host=host),
    )
    header = SimpleNamespace(
        property=lambda name: 0 if name == "nativeHeaderInset" else float("nan"),
        x=lambda: 0,
    )
    row = header_timeline_sample(window, header)
    endpoint = row["native_endpoint_geometry"]
    assert endpoint["fullscreen_transition"] == 0
    assert endpoint["presentation_flags"] == [None, None, None]
    assert endpoint["measured_endpoint_offsets"] == [None, None]
    # Other old QML fields deliberately remain unknown in this stub; the new
    # fixed observables themselves must be serializable without NaN guesses.
    json.dumps(endpoint, allow_nan=False)


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


def test_header_trace_accepts_real_qml_object_packet():
    from PySide6.QtQml import QJSEngine
    from tests.test_qt_scene_port import qt_app

    app = qt_app()
    engine = QJSEngine()
    packet = engine.evaluate("({host_screen: [1, 2, 3, 4], transition: 1})")
    window = SimpleNamespace(
        property=lambda name: packet if name == "nativeRowPacket" else False,
        devicePixelRatio=lambda: 2,
    )
    header = SimpleNamespace(property=lambda name: 0, x=lambda: 0)
    row = header_timeline_sample(window, header)
    assert row["packet_host"] == [1, 2, 3, 4]
    assert row["packet_transition"] == 1
    assert app is not None
