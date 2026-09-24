"""Actual Qt Quick image-status producers for the local telemetry Worker gate."""

from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuickControls2 import QQuickStyle

from yt_downloader.qt_quick.main import Bridge, create_engine
from yt_downloader.qt_quick.presentation import QtPresentationProbe

QT_PRESENTATION_CASES = (
    "qt_artwork_ready",
    "qt_control_fault",
    "qt_artwork_fault",
    "qt_surface_fault",
    "qt_resize",
)


def _visual_children(item):
    yield item
    for child in item.childItems():
        yield from _visual_children(child)


def _image(window, *, name: str = "", role: str = "", source_part: str = ""):
    for item in _visual_children(window.contentItem()):
        if name and item.objectName() != name:
            continue
        if role and item.property("presentationRole") != role:
            continue
        source = item.property("source")
        if (
            source is not None
            and source_part in source.toString()
            and bool(item.property("visible"))
        ):
            return item
    raise AssertionError("Required visible Qt image was not rendered")


def qt_presentation_case(directory: Path, telemetry, case: str):
    assert case in QT_PRESENTATION_CASES
    directory.mkdir(parents=True, exist_ok=True)
    thumbnail = directory / "PRIVATE-thumbnail.jpg"
    Image.new("RGB", (640, 360), "#7197b8").save(thumbnail)
    record = {
        "id": "PRIVATE-video",
        "title": "PRIVATE title",
        "channel": "PRIVATE channel",
        "playlist_id": "PRIVATE playlist",
        "vodforge_output_dir": str(directory),
        "vodforge_output_path": str(directory / "PRIVATE-video.mp4"),
        "vodforge_output_type": "MP4",
        "preview_thumbnail_path": str(thumbnail),
    }
    app = None
    bridge = engine = window = probe = None
    with patch.dict(
        os.environ,
        {
            "HOME": str(directory),
            "LOCALAPPDATA": str(directory),
            "QT_QPA_PLATFORM": "offscreen",
            "VODFORGE_DISABLE_TELEMETRY": "1",
        },
    ):
        try:
            app = QGuiApplication.instance()
            if app is None:
                QQuickStyle.setStyle("Basic")
                app = QGuiApplication([])
            bridge = Bridge(None)
            bridge._runtime.history = [record]
            engine = create_engine(bridge)
            window = engine.rootObjects()[0]
            window.show()
            bridge.select("Library")
            bridge.navigateLibrary("all")
            probe = QtPresentationProbe(bridge, window, telemetry)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if bridge._artwork.poll():
                    bridge.historyChanged.emit()
                app.processEvents()
                try:
                    artwork = _image(
                        window, name="libraryMediaArtworkImage", source_part="file:"
                    )
                    if artwork.property("source").toLocalFile():
                        break
                except AssertionError:
                    pass
                time.sleep(0.005)
            else:
                raise AssertionError("Qt Library artwork did not become visible")
            probe.sample()
            if case == "qt_control_fault":
                target = _image(window, role="control", source_part="/button/")
            elif case == "qt_artwork_fault":
                target = artwork
            elif case == "qt_surface_fault":
                target = _image(window, role="surface", source_part="/backdrop/")
            else:
                target = None
            if target is not None:
                original = target.property("source")
                target.setProperty("source", "file:///PRIVATE-missing-qt-image.png")
                app.processEvents()
                probe.sample()
                target.setProperty("source", original)
                app.processEvents()
                probe.sample()
            if case == "qt_resize":
                window.setWidth(930)
                app.processEvents()
                probe.sample()
            snapshot = window.property("presentationDiagnosticSnapshot").toVariant()
            assert snapshot["visible"] is True
            assert snapshot["artworkExpected"] >= 1
            assert snapshot["artworkDisplayed"] >= 1
            return {
                "case": case,
                "renderer": "qt",
                "visible_artwork": True,
                "geometry_changed": case == "qt_resize" and window.width() == 930,
            }
        finally:
            if probe is not None:
                probe.close()
            if window is not None:
                window.close()
            if engine is not None:
                engine.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                app.processEvents()
            if bridge is not None:
                bridge.close()
