"""Library groups are selected entities, not prematurely expanded media owners."""

from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Qt, QUrl
from PySide6.QtGui import QColor, QImage, QPainter

from tests.test_qt_scene_port import qt_app, saved, visual_item
from yt_downloader.qt_quick import main as qt_main


@pytest.mark.parametrize("route", ["channels", "playlists"])
@pytest.mark.parametrize("width", [820, 1100, 2400])
def test_group_checkbox_counts_one_entity_and_prunes_stale(
    tmp_path, monkeypatch, route, width
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [
        saved(tmp_path, "One", "MP4"),
        saved(tmp_path, "Two", "MP4"),
    ]
    avatar = QImage(160, 160, QImage.Format_ARGB32)
    avatar.fill(Qt.transparent)
    painter = QPainter(avatar)
    painter.setBrush(QColor("#b6a3db"))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(0, 0, 160, 160)
    painter.end()
    avatar_path = tmp_path / "fictional-avatar.png"
    avatar.save(str(avatar_path))
    bridge._group_artwork = lambda *_: QUrl.fromLocalFile(str(avatar_path)).toString()
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        window.resize(width, 900)
        bridge.select("Library")
        bridge.navigateLibrary(route)
        for _ in range(3):
            app.processEvents()
        scene = window.findChild(QObject, "libraryBrowseScene")
        scene.setProperty("selectionMode", True)
        app.processEvents()
        checkbox = visual_item(window.contentItem(), "libraryGroupSelectionCheckbox")
        assert checkbox is not None and checkbox.isVisible()
        assert checkbox.property("label") == ""
        checkbox.activated.emit()
        app.processEvents()
        assert checkbox.property("label") == "✓"
        assert scene.property("selectedEntityCount") == 1
        assert scene.property("selectedOwners").toVariant() == []
        checkbox.activated.emit()
        app.processEvents()
        assert scene.property("selectedEntityCount") == 0
        checkbox.activated.emit()
        assert scene.property("selectedEntityCount") == 1
        if route == "channels":
            assert checkbox.parentItem().width() <= 280
            assert checkbox.parentItem().height() == 178
            art = visual_item(checkbox.parentItem(), "libraryGroupArtworkImage")
            assert art.property("circular") is True
            assert art.width() == art.height() == 96
        capture = window.grabWindow()
        root = (
            Path(__file__).parents[2]
            / "integration-evidence/library-groups-batch9/renders"
        )
        root.mkdir(parents=True, exist_ok=True)
        capture.save(str(root / f"{route}-{width}-selected.png"))
        bridge._runtime.history = []
        bridge.historyChanged.emit()
        for _ in range(3):
            app.processEvents()
        assert scene.property("selectedEntityCount") == 0
        bridge.navigateLibrary("all")
        app.processEvents()
        assert not scene.property("selectionMode")
    finally:
        bridge.close()
        engine.deleteLater()
        app.processEvents()


def test_actions_expand_only_at_dispatch():
    source = (Path(qt_main.__file__).parent / "LibraryScene.qml").read_text(
        encoding="utf-8"
    )
    assert (
        "resolveScopedLibrarySelection(scene.selectionSection, scene.selectionTargets())"
        in source
    )
    assert "selectedOwners = group.owners.slice()" not in source
    assert "for (const owner of modelData.owners)" not in source
