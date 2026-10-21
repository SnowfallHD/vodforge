"""Application fullscreen uses one main-window owner, preserving Qt restore state."""

import sys

import pytest
from PySide6.QtCore import QMetaObject, QObject, Qt
from PySide6.QtGui import QWindow
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch
from tests.test_qt_scene_port import visual_item


def settle(app):
    QTest.qWait(75)
    app.processEvents()


def toggle(window):
    assert QMetaObject.invokeMethod(window, "toggleApplicationFullscreen")


@pytest.mark.parametrize("maximized", [False, True])
def test_application_fullscreen_repeated_toggle_restores_prior_state_and_geometry(
    tmp_path, monkeypatch, maximized
):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        shortcut = window.findChild(QObject, "mainFullscreenToggle")
        assert shortcut is not None
        assert shortcut.property("context") == Qt.WindowShortcut
        assert bool(shortcut.property("enabled")) == (sys.platform == "win32")
        window.showNormal()
        window.setGeometry(47, 63, 1080, 710)
        settle(app)
        normal = window.geometry()
        if maximized:
            window.showMaximized()
            settle(app)
        original = window.visibility()
        geometry = window.geometry()
        for _ in range(3):
            toggle(window)
            settle(app)
            assert window.visibility() == QWindow.FullScreen
            assert window.geometry() == window.screen().geometry()
            header = window.findChild(QObject, "focusHeader")
            assert header.y() == pytest.approx(5)
            toggle(window)
            settle(app)
            assert window.visibility() == original
            assert window.geometry() == geometry
        if maximized:
            window.showNormal()
            settle(app)
            assert window.geometry() == normal
    finally:
        _close(bridge, engine, window)


def test_fullscreen_escape_restores_maximized_and_modal_escape_priority(
    tmp_path, monkeypatch
):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        window.showMaximized()
        settle(app)
        toggle(window)
        settle(app)
        popup = window.findChild(QObject, "downloadSettingsPopup")
        QMetaObject.invokeMethod(popup, "open")
        settle(app)
        escape = window.findChild(QObject, "mainFullscreenEscape")
        assert not escape.property("enabled")
        QMetaObject.invokeMethod(popup, "close")
        settle(app)
        window.requestActivate()
        settle(app)
        QTest.keyClick(window, Qt.Key_Escape)
        settle(app)
        assert window.visibility() == QWindow.Maximized
    finally:
        _close(bridge, engine, window)


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Actual Windows F11 dispatch; other hosts test shared controller",
)
def test_windows_f11_with_focused_input_and_another_window(tmp_path, monkeypatch):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    other = QQuickWindow()
    try:
        editor = visual_item(window.contentItem(), "forgeUrlInput")
        window.requestActivate()
        editor.forceActiveFocus()
        editor.setProperty("text", "Fictional preserved input")
        settle(app)
        for _ in range(2):
            QTest.keyClick(window, Qt.Key_F11)
            settle(app)
            assert window.visibility() == QWindow.FullScreen
            QTest.keyClick(window, Qt.Key_F11)
            settle(app)
            assert window.visibility() == QWindow.Windowed
            assert editor.property("text") == "Fictional preserved input"
            assert editor.hasActiveFocus()
        other.show()
        other.requestActivate()
        settle(app)
        QTest.keyClick(other, Qt.Key_F11)
        settle(app)
        assert window.visibility() == QWindow.Windowed, (
            "Main app shortcut must not capture another presentation window"
        )
    finally:
        other.close()
        _close(bridge, engine, window)
