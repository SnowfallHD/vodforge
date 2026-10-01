"""Folder inspector growth is viewport-driven, independent of long metadata."""

import pytest
from PySide6.QtCore import QObject

from tests.test_qt_scene_port import qt_app, saved
from yt_downloader.qt_quick import main as qt_main


@pytest.mark.parametrize("width", [820, 1100, 2400])
def test_folder_columns_responsive(tmp_path, monkeypatch, width):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    record = saved(tmp_path, "Fixture", "MP4")
    record["title"] = "Long title " * 12
    bridge._runtime.history = [record]
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        window.resize(width, 900)
        bridge.select("Library")
        bridge.navigateLibraryFolders("all")
        component = bridge.libraryFolders["components"][0]
        bridge.selectLibraryFolderComponent(component["key"])
        app.processEvents()
        assert not window.grabWindow().isNull()
        browser = window.findChild(QObject, "libraryFolderBrowser")
        content = window.findChild(QObject, "libraryFolderContentColumn")
        inspector = window.findChild(QObject, "libraryFolderInspector")
        assert bool(browser.property("showInspector")) == (width >= 920)
        assert content.width() > 250
        if width == 1100:
            assert inspector.width() == 380
        elif width == 2400:
            assert 600 <= inspector.width() <= 680
        before = content.width()
        bridge._runtime.history[0]["title"] = "Short"
        bridge.historyChanged.emit()
        app.processEvents()
        assert content.width() == before
    finally:
        bridge.close()
        engine.deleteLater()
        app.processEvents()
