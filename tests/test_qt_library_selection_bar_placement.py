"""Selection toolbar geometry and entity ownership, using offscreen Qt."""

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF
from PySide6.QtTest import QTest

from tests.test_qt_scene_port import qt_app, qt_main, saved, visual_item


@pytest.mark.parametrize("route", ["all", "channels", "playlists", "videos", "audio"])
@pytest.mark.parametrize("size", [(760, 600), (1100, 800)])
def test_selection_bar_above_collection_with_one_entity(
    tmp_path, monkeypatch, route, size
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [
        saved(tmp_path, f"Item{n}", kind) for n in range(8) for kind in ("MP4", "MP3")
    ]
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        window.resize(*size)
        window.show()
        bridge.select("Library")
        bridge.navigateLibrary(route)
        app.processEvents()
        scene = window.findChild(QObject, "libraryBrowseScene")
        scene.setProperty("selectionMode", True)
        app.processEvents()
        QTest.qWait(50)
        if route in ("channels", "playlists"):
            flow = window.findChild(QObject, "libraryGroupFlow")
            checkbox = visual_item(flow, "libraryGroupSelectionCheckbox")
            checkbox.activated.emit()
        else:
            flow = window.findChild(QObject, "libraryMediaFlow")
            card = next(
                item
                for item in flow.childItems()
                if item.property("modelData") is not None
            )
            checkbox = next(
                item
                for item in card.childItems()
                if str(item.property("accessibilityLabel") or "").startswith("Select ")
            )
            checkbox.activated.emit()
        app.processEvents()
        QTest.qWait(50)
        assert scene.property("selectedEntityCount") == 1
        assert checkbox.property("selected")
        actions = window.findChild(QObject, "librarySelectionActionsButton")
        bar = actions.parentItem()
        label = next(
            item for item in bar.childItems() if item.property("text") is not None
        )
        assert label.property("text") == "1 selected"
        assert actions.isVisible()
        viewport = window.findChild(QObject, "libraryViewport")
        viewport.property("contentItem").setProperty("contentY", max(0, bar.y() - 12))
        app.processEvents()
        bottom = bar.mapToItem(scene, QPointF(0, bar.height())).y()
        top = flow.mapToItem(scene, QPointF(0, 0)).y()
        assert bottom <= top, (route, bottom, top)
        assert bar.mapToItem(scene, QPointF(0, 0)).y() >= 0
        assert bottom <= scene.height()
        assert (
            label.x() + label.width() <= actions.x()
            or label.y() + label.height() <= actions.y()
        )
        assert actions.y() + actions.height() <= bar.height()
        assert bridge.libraryScene["route"] == route
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
