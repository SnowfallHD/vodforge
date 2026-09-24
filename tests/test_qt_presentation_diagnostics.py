"""The Qt renderer must report real image faults through the shared owner."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuickControls2 import QQuickStyle

from tests.test_qt_scene_port import saved
from yt_downloader.product_telemetry import BoundProductOperation
from yt_downloader.qt_quick import main as qt_main
from yt_downloader.qt_quick.presentation import QtPresentationProbe
from yt_downloader.telemetry_features import validate_dimensions


class Sink:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.events: list[tuple[str, dict[str, str]]] = []
        self.operation_keys: list[str] = []

    def permitted(self) -> bool:
        return self.allowed

    def bind_operation(self, feature: str, *, operation_key: str):
        assert feature == "presentation_operation"

        def record(action: str, dimensions: dict[str, str]) -> None:
            validate_dimensions(dimensions)
            self.events.append((action, dict(dimensions)))
            self.operation_keys.append(operation_key)

        return BoundProductOperation(self.permitted, record)


def test_qt_presentation_owner_import_does_not_require_tcl():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import yt_downloader.qt_quick.presentation; assert 'tkinter' not in sys.modules",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _scene(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, artwork: bool = False):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    QQuickStyle.setStyle("Basic")
    app = QGuiApplication.instance() or QGuiApplication([])
    bridge = qt_main.Bridge(None)
    if artwork:
        image_path = tmp_path / "PRIVATE-thumbnail.jpg"
        Image.new("RGB", (640, 360), "#7197b8").save(image_path)
        record = saved(tmp_path, "PRIVATE saved media", "MP4")
        record["preview_thumbnail_path"] = str(image_path)
        bridge._runtime.history = [record]
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    window.show()
    bridge.select("Library")
    if artwork:
        bridge.navigateLibrary("all")
    app.processEvents()
    return app, bridge, engine, window


def _image(window, *, source_fragment: str = "", object_name: str = ""):
    def visual_children(item):
        yield item
        for child in item.childItems():
            yield from visual_children(child)

    for item in visual_children(window.contentItem()):
        if object_name and item.objectName() != object_name:
            continue
        source = item.property("source")
        if (
            source is not None
            and source_fragment in source.toString()
            and bool(item.property("visible"))
        ):
            return item
    raise AssertionError(f"No visible image for {object_name or source_fragment}")


def _close(app, bridge, engine, window, probe):
    probe.close()
    window.close()
    engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    bridge.close()


@pytest.mark.parametrize("source_fragment", ["/button/", "/field/"])
def test_qt_shared_control_fault_and_recovery_is_role_stable(
    tmp_path, monkeypatch, source_fragment
):
    app, bridge, engine, window = _scene(tmp_path, monkeypatch)
    sink = Sink()
    probe = QtPresentationProbe(bridge, window, sink)
    try:
        probe.sample()
        image = _image(window, source_fragment=source_fragment)
        assert image.property("presentationRole") == "control"
        original = image.property("source")
        image.setProperty("source", "file:///PRIVATE-missing-material.png")
        app.processEvents()
        probe.sample()
        image.setProperty("source", original)
        app.processEvents()
        probe.sample()
        assert [action for action, _ in sink.events][-3:] == [
            "fault",
            "recovered",
            "settled",
        ]
        assert sink.events[-3][1]["missing_image_role"] == "control"
        assert sink.events[-3][1]["missing_image_bucket"] == "1"
        assert "PRIVATE" not in json.dumps(sink.events)
    finally:
        _close(app, bridge, engine, window, probe)


def test_qt_visible_library_artwork_fault_and_recovery(tmp_path, monkeypatch):
    app, bridge, engine, window = _scene(tmp_path, monkeypatch, artwork=True)
    sink = Sink()
    probe = QtPresentationProbe(bridge, window, sink)
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if bridge._artwork.poll():
                bridge.historyChanged.emit()
            app.processEvents()
            try:
                image = _image(window, object_name="libraryMediaArtworkImage")
                if image.property("source").toLocalFile():
                    break
            except AssertionError:
                pass
            time.sleep(0.005)
        else:
            raise AssertionError("Library artwork did not render")
        probe.sample()
        original = image.property("source")
        image.setProperty("source", "file:///PRIVATE-missing-artwork.png")
        app.processEvents()
        probe.sample()
        bridge.historyChanged.emit()
        image.setProperty("source", original)
        app.processEvents()
        probe.sample()
        assert any(
            action == "fault" and row["missing_image_role"] == "artwork"
            for action, row in sink.events
        )
        assert any(action == "recovered" for action, _ in sink.events)
        assert sink.events[-1][0] == "settled"
        fault = next(
            index for index, (action, _) in enumerate(sink.events) if action == "fault"
        )
        recovered = next(
            index
            for index, (action, _) in enumerate(sink.events)
            if action == "recovered"
        )
        assert sink.operation_keys[fault] == sink.operation_keys[recovered]
        assert "PRIVATE" not in json.dumps(sink.events)
    finally:
        _close(app, bridge, engine, window, probe)


def test_qt_presentation_consent_and_resize_boundary(tmp_path, monkeypatch):
    app, bridge, engine, window = _scene(tmp_path, monkeypatch)
    sink = Sink(allowed=False)
    probe = QtPresentationProbe(bridge, window, sink)
    try:
        probe.sample()
        assert not sink.events
        assert window.property("presentationDiagnosticSnapshot").toVariant() == {}
        sink.allowed = True
        probe.sample()
        assert any(action == "settled" for action, _ in sink.events)
        window.setWidth(window.width() + 120)
        app.processEvents()
        probe.sample()
        assert any(row["presentation_trigger"] == "resize" for _, row in sink.events)
        count = len(sink.events)
        sink.allowed = False
        image = _image(window, source_fragment="/button/")
        image.setProperty("source", "file:///PRIVATE-denied-image.png")
        app.processEvents()
        probe.sample()
        assert len(sink.events) == count
    finally:
        _close(app, bridge, engine, window, probe)
