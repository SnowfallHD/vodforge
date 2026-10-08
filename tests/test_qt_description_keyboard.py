"""Focused read-only description navigation; offscreen, not native input proof."""

import pytest
from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest

from tests.test_qt_library_details_copy import detail  # noqa: F401


@pytest.mark.parametrize("focus_text", [True, False])
@pytest.mark.parametrize(
    "key,modifiers,direction",
    [
        (Qt.Key_Down, Qt.NoModifier, 1),
        (Qt.Key_Up, Qt.NoModifier, -1),
        (Qt.Key_PageDown, Qt.NoModifier, 1),
        (Qt.Key_PageUp, Qt.NoModifier, -1),
        (Qt.Key_Space, Qt.NoModifier, 1),
        (Qt.Key_Space, Qt.ShiftModifier, -1),
    ],
)
def test_description_keyboard_moves_its_viewport(
    detail,  # noqa: F811
    focus_text,
    key,
    modifiers,
    direction,
):
    app, bridge, owner, _engine, window = detail
    bridge._settings["social_invitation_dismissed"] = True
    assert bridge.saveLibraryDescription(owner, "Description line.\n" * 100)
    app.processEvents()
    scroll = window.findChild(QObject, "libraryDescriptionScroll")
    text = window.findChild(QObject, "libraryDescriptionText")
    inner = scroll.property("contentItem")
    maximum = inner.property("contentHeight") - inner.height()
    inner.setProperty("contentY", maximum / 2)
    (text if focus_text else scroll).forceActiveFocus(Qt.TabFocusReason)
    app.processEvents()
    assert (text if focus_text else scroll).hasActiveFocus()
    before = inner.property("contentY")
    QTest.keyClick(window, key, modifiers)
    app.processEvents()
    after = inner.property("contentY")
    assert after > before if direction > 0 else after < before


def test_description_selection_copy_and_edit_mode_remain_available(detail):  # noqa: F811
    app, bridge, owner, _engine, window = detail
    original = "Description line.\n" * 100
    assert bridge.saveLibraryDescription(owner, original)
    app.processEvents()
    text = window.findChild(QObject, "libraryDescriptionText")
    text.forceActiveFocus(Qt.TabFocusReason)
    text.setProperty("cursorPosition", 0)
    QTest.keyClick(window, Qt.Key_Down, Qt.ShiftModifier)
    assert text.property("selectedText")
    QTest.keySequence(window, QKeySequence(QKeySequence.StandardKey.Copy))
    assert app.clipboard().text() == text.property("selectedText")
    assert text.property("text") == original
    selection = text.property("selectedText")
    cursor = text.property("cursorPosition")
    QTest.keyClick(window, Qt.Key_PageDown)
    assert text.property("selectedText") == selection
    assert text.property("cursorPosition") == cursor
    QTest.keySequence(window, QKeySequence(QKeySequence.StandardKey.SelectAll))
    QTest.keySequence(window, QKeySequence(QKeySequence.StandardKey.Copy))
    assert app.clipboard().text() == original


@pytest.mark.parametrize("at_bottom,key", [(True, Qt.Key_Down), (False, Qt.Key_Up)])
def test_description_keyboard_edges_do_not_scroll_page(detail, at_bottom, key):  # noqa: F811
    app, bridge, owner, _engine, window = detail
    assert bridge.saveLibraryDescription(owner, "Description line.\n" * 100)
    app.processEvents()
    text = window.findChild(QObject, "libraryDescriptionText")
    inner = window.findChild(QObject, "libraryDescriptionScroll").property(
        "contentItem"
    )
    outer = window.findChild(QObject, "libraryDetailViewport").property("contentItem")
    maximum = inner.property("contentHeight") - inner.height()
    inner.setProperty("contentY", maximum if at_bottom else 0)
    text.forceActiveFocus(Qt.TabFocusReason)
    before = outer.property("contentY")
    QTest.keyClick(window, key)
    app.processEvents()
    assert inner.property("contentY") == pytest.approx(maximum if at_bottom else 0)
    assert outer.property("contentY") == before


@pytest.mark.parametrize("key", [Qt.Key_Down, Qt.Key_PageDown, Qt.Key_Space])
def test_short_description_keyboard_scrolls_page(detail, key):  # noqa: F811
    app, bridge, owner, _engine, window = detail
    window.resize(1400, 500)
    assert bridge.saveLibraryDescription(owner, "Short description")
    app.processEvents()
    text = window.findChild(QObject, "libraryDescriptionText")
    inner = window.findChild(QObject, "libraryDescriptionScroll").property(
        "contentItem"
    )
    outer = window.findChild(QObject, "libraryDetailViewport").property("contentItem")
    text.forceActiveFocus(Qt.TabFocusReason)
    outer.setProperty("contentY", 0)
    QTest.keyClick(window, key)
    app.processEvents()
    assert inner.property("contentY") == 0
    assert outer.property("contentY") > 0
