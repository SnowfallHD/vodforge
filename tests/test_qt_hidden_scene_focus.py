"""Retire outgoing hidden editors without claiming an intermittent native click fix."""

from PySide6.QtCore import QObject, QPoint, QPointF, Qt
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch, _visual_descendants
from tests.test_qt_scene_port import saved, visual_item


def click(window, item):
    point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
    QTest.mouseClick(
        window, Qt.LeftButton, pos=QPoint(round(point.x()), round(point.y()))
    )
    QTest.qWait(50)


def test_hidden_composer_retires_focus_then_watch_first_clicks_work(
    tmp_path, monkeypatch
):
    records = [saved(tmp_path, "First", "MP4"), saved(tmp_path, "Second", "MP4")]
    records[1]["channel"] = "Second channel"
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, records)
    try:
        window.resize(1400, 800)
        editor = window.findChild(QObject, "forgeUrlInput")
        editor.forceActiveFocus()
        assert window.property("editingText")
        bridge.select("Watch")
        QTest.qWait(100)
        assert not editor.isVisible()
        assert not editor.hasActiveFocus()
        assert not window.property("editingText")
        assert window.activeFocusItem().isVisible()
        trigger = visual_item(window.contentItem(), "watchHeroMoreButton")
        popup = window.findChild(QObject, "watchHeroMorePopup")
        click(window, trigger)
        assert popup.property("visible")
        QTest.keyClick(window, Qt.Key_Escape)
        QTest.qWait(50)
        assert not popup.property("visible")
        assert not editor.hasActiveFocus()
        assert not window.property("editingText")
        # First pointer request after closing the popup still opens it.
        click(window, trigger)
        assert popup.property("visible")
        popup.close()
        bridge.navigateWatch("channels")
        QTest.qWait(100)
        cards = [
            item
            for item in _visual_descendants(window.contentItem())
            if item.property("channel") is True
            and item.property("group") is not None
            and item.isVisible()
        ]
        card = cards[1]
        group = card.property("group")
        if hasattr(group, "toVariant"):
            group = group.toVariant()
        viewport = window.findChild(QObject, "watchViewport")
        page = viewport.property("contentItem")
        page.setProperty(
            "contentY", max(0, card.mapToItem(page, QPointF(0, 0)).y() - 80)
        )
        QTest.qWait(100)
        click(window, card)
        assert bridge.watchScene["route"] == "group"
        assert bridge.watchScene["groupTitle"] == group["title"]
        assert not window.property("editingText")
        assert not editor.hasActiveFocus()
        app.processEvents()
    finally:
        _close(bridge, engine, window)


def test_visible_shared_editor_focus_is_not_retired(tmp_path, monkeypatch):
    app, bridge, engine, window = _launch(
        tmp_path, monkeypatch, [saved(tmp_path, "First", "MP4")]
    )
    try:
        bridge.select("Library")
        QTest.qWait(50)
        editor = window.findChild(QObject, "headerSearchInput")
        editor.forceActiveFocus()
        app.processEvents()
        bridge.select("Watch")
        QTest.qWait(100)
        assert editor.isVisible()
        assert editor.hasActiveFocus()
        assert window.property("editingText")
    finally:
        _close(bridge, engine, window)


def test_tab_and_enter_remain_available_after_hidden_focus_retirement(
    tmp_path, monkeypatch
):
    _app, bridge, engine, window = _launch(
        tmp_path, monkeypatch, [saved(tmp_path, "First", "MP4")]
    )
    try:
        window.findChild(QObject, "forgeUrlInput").forceActiveFocus()
        bridge.select("Watch")
        QTest.qWait(100)
        QTest.keyClick(window, Qt.Key_Tab)
        QTest.qWait(50)
        assert window.activeFocusItem().isVisible()
        trigger = visual_item(window.contentItem(), "watchHeroMoreButton")
        trigger.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_Return)
        QTest.qWait(50)
        assert window.findChild(QObject, "watchHeroMorePopup").property("visible")
    finally:
        _close(bridge, engine, window)
