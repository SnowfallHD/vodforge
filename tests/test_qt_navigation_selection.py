"""Top navigation uses the existing Archive emblem token and a latched pressed face."""

import os
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QPoint, QPointF, Qt
from PySide6.QtGui import QAccessible, QColor
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch
from tests.test_qt_scene_port import polish_scene, visual_item


def settle(app, window):
    QTest.qWait(90)
    app.processEvents()
    polish_scene(window.contentItem())


def face(button):
    return next(
        c
        for c in button.children()
        if c.property("source") is not None
        and str(c.property("source").toString()).startswith("image://vodforge/button/")
    )


def capture(item):
    result = item.grabToImage()
    assert result is not None
    for _ in range(100):
        if not result.image().isNull():
            return result.image()
        QTest.qWait(10)
    raise AssertionError("No actual item image")


def test_obsolete_navigation_underline_code_is_removed():
    source = Path("yt_downloader/qt_quick/Main.qml").read_text()
    assert "navigationSelectedBar_" not in source


@pytest.mark.parametrize(
    "theme", ["Violet", "Cobalt", "Jade", "Ember", "Rose", "Custom accent"]
)
def test_top_emblem_reuses_archive_selection_across_themes(
    tmp_path, monkeypatch, theme
):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        bridge.setAppearance(theme, "#28896c")
        bridge.selectHome("Library")
        settle(app, window)
        button = visual_item(window.contentItem(), "navigationButton_Library")
        icons = [
            c
            for c in button.findChildren(QObject)
            if c.metaObject().className().startswith("SceneIcon_")
        ]
        icon = next(c for c in icons if c.property("visible"))
        sidebar = visual_item(window.contentItem(), "librarySidebarIcon_all")
        assert icon.property("tone") == sidebar.property("tone") == QColor("#bda0ff")
        assert icon.property("name") == sidebar.property("name") == "folder"
        # Actual painted Canvas has opaque strokes at the existing selection color.
        image = capture(icon)
        assert any(
            image.pixelColor(x, y).alpha() > 240
            and image.pixelColor(x, y).name() == "#bda0ff"
            for y in range(image.height())
            for x in range(image.width())
        )
        if folder := os.environ.get("VODFORGE_UI_EVIDENCE_DIR"):
            target = Path(folder)
            target.mkdir(parents=True, exist_ok=True)
            assert window.grabWindow().save(
                str(target / ("navigation-" + theme.replace(" ", "-") + ".png"))
            )
    finally:
        _close(bridge, engine, window)


def test_selected_face_matches_real_held_press_and_keyboard_focus_remains(
    tmp_path, monkeypatch
):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        bridge.selectHome("Library")
        settle(app, window)
        button = visual_item(window.contentItem(), "navigationButton_Library")
        window.requestActivate()
        window.contentItem().forceActiveFocus()
        QTest.mouseMove(window, QPoint(window.width() - 10, window.height() - 10))
        settle(app, window)
        idle = capture(face(button))
        center = button.mapToScene(
            QPointF(button.width() / 2, button.height() / 2)
        ).toPoint()
        QTest.mousePress(window, Qt.LeftButton, pos=center)
        settle(app, window)
        held = capture(face(button))
        QTest.mouseRelease(window, Qt.LeftButton, pos=center)
        settle(app, window)
        assert idle == held, "Selected idle must retain the actual pressed material"
        activity = visual_item(window.contentItem(), "navigationButton_Activity")
        activity.forceActiveFocus(Qt.TabFocusReason)
        settle(app, window)
        ring = activity.findChild(QObject, "stoneKeyboardFocusRing")
        assert ring.property("visible")
        QTest.keyClick(window, Qt.Key_Return)
        settle(app, window)
        assert bridge.selection == "Activity"
        interface = QAccessible.queryAccessibleInterface(activity)
        assert interface is not None and interface.state().selected
        assert ring.property("visible"), (
            "Latched selection must not erase keyboard focus"
        )
    finally:
        _close(bridge, engine, window)
