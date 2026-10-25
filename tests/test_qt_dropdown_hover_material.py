"""Actual scene dropdown hover material; native macOS delivery is separate."""

import pytest
from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QUrl
from PySide6.QtQml import QQmlComponent
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch
from yt_downloader.product_theme import THEME_NAMES
from yt_downloader.qt_quick import main


def walk(item):
    yield item
    for child in item.childItems():
        yield from walk(child)


def face(button):
    return next(
        child
        for child in button.childItems()
        if str(child.property("source")).startswith("PySide6.QtCore.QUrl")
        and "image://vodforge/button/" in child.property("source").toString()
    )


def center(button):
    return button.mapToScene(QPointF(button.width() / 2, button.height() / 2)).toPoint()


def crop(window, button):
    image = window.grabWindow()
    assert not image.isNull()
    ratio = image.devicePixelRatio()
    point = button.mapToScene(QPointF())
    image = image.copy(
        round(point.x() * ratio),
        round(point.y() * ratio),
        round(button.width() * ratio),
        round(button.height() * ratio),
    )
    return bytes(image.constBits())


@pytest.mark.parametrize("theme_name", THEME_NAMES)
def test_format_dropdown_pointer_hover_press_focus_and_disabled_material(
    tmp_path, monkeypatch, theme_name
):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        assert bridge.setAppearance(theme_name, "#7170ff")
        QTest.qWait(100)
        popup = window.findChild(QObject, "forgeFormatPopup")
        trigger = window.findChild(QObject, "forgeFormatButton")
        # Exercise actual trigger click, not only calling Popup.open().
        QTest.mouseClick(window, Qt.LeftButton, pos=center(trigger))
        QTest.qWait(300)
        assert popup.property("visible")
        assert popup.property("anchorItem") is trigger
        content = popup.property("contentItem")
        assert content.window() is window
        buttons = {
            item.property("label"): item
            for item in walk(content)
            if item.property("label") in {"MP4", "MP3", "Original audio"}
        }
        assert set(buttons) == {"MP4", "MP3", "Original audio"}
        assert buttons["MP4"].property("selected")
        for label in ("MP3", "Original audio"):
            button = buttons[label]
            material = face(button)
            geometry = (button.x(), button.y(), button.width(), button.height())
            QTest.mouseMove(window, QPoint(2, 2))
            QTest.qWait(50)
            assert "/normal/" in material.property("source").toString()
            normal = crop(window, button)
            QTest.mouseMove(window, center(button))
            QTest.qWait(60)
            assert button.property("hovered")
            assert "/hover/" in material.property("source").toString()
            hover = crop(window, button)
            assert hover != normal
            QTest.mousePress(window, Qt.LeftButton, pos=center(button))
            QTest.qWait(30)
            assert "/pressed/" in material.property("source").toString()
            assert crop(window, button) != hover
            # Release outside this row to avoid executing an export choice.
            QTest.mouseRelease(window, Qt.LeftButton, pos=QPoint(2, 2))
            if not popup.property("visible"):
                popup.open()
                QTest.qWait(300)
            QTest.mouseMove(window, QPoint(2, 2))
            QTest.qWait(50)
            button.forceActiveFocus(Qt.TabFocusReason)
            app.processEvents()
            assert button.hasActiveFocus()
            assert "/hover/" in material.property("source").toString()
            button.setProperty("persistentMaterial", False)
            ring = button.findChild(QObject, "stoneKeyboardFocusRing")
            assert ring.isVisible()
            button.setEnabled(False)
            QTest.mouseMove(window, center(button))
            QTest.qWait(50)
            assert "/normal/" in material.property("source").toString()
            assert not button.property("activeFocusOnTab")
            button.setEnabled(True)
            button.setFocus(False)
            assert (button.x(), button.y(), button.width(), button.height()) == geometry
        assert bridge.outputFormat == "MP4"
    finally:
        _close(bridge, engine, window)


def test_inline_dropdown_reuses_same_hover_without_layout_shift(tmp_path, monkeypatch):
    _app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    component = QQmlComponent(engine)
    component.setData(
        b"""import QtQuick
import "."
InlineSelector {
    objectName: "hoverAuditSelector"
    width: 250; x: 100; y: 150
    options: [{label: "First", value: "first"}, {label: "Second", value: "second"}]
    currentValue: "first"; expanded: true
}""",
        QUrl.fromLocalFile(str(main.SOURCE / "yt_downloader/qt_quick/hover-audit.qml")),
    )
    selector = component.create()
    assert selector is not None, component.errors()
    selector.setParentItem(window.contentItem())
    selector.setZ(1000)
    try:
        QTest.qWait(300)
        button = next(
            i
            for i in walk(selector)
            if i.objectName() == "hoverAuditSelector_option_second"
        )
        geometry = (selector.height(), button.width(), button.height())
        QTest.mouseMove(window, QPoint(2, 2))
        QTest.qWait(30)
        assert "/normal/" in face(button).property("source").toString()
        QTest.mouseMove(window, center(button))
        QTest.qWait(50)
        assert button.property("hovered")
        assert "/hover/" in face(button).property("source").toString()
        assert (selector.height(), button.width(), button.height()) == geometry
    finally:
        selector.deleteLater()
        _close(bridge, engine, window)
