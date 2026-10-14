"""Floating playback must request usable native chrome, including with on-top."""

import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, Qt, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from tests.test_qt_scene_port import qt_app
from yt_downloader.product_theme import THEME
from yt_downloader.qt_quick import main as qt_main


@pytest.fixture
def player_scene(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    scene = window.findChild(QObject, "watchPlayerScene")
    presentation = window.findChild(QObject, "watchPresentationWindow")
    try:
        yield app, window, scene, presentation
    finally:
        presentation.close()
        window.close()
        app.processEvents()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        bridge.close()


def test_floating_player_explicitly_requests_native_chrome(player_scene):
    app, _, scene, presentation = player_scene
    scene.setProperty("presentationMode", "floating")
    app.processEvents()
    flags = presentation.flags()
    for hint in (
        Qt.WindowTitleHint,
        Qt.WindowSystemMenuHint,
        Qt.WindowMinimizeButtonHint,
        Qt.WindowMaximizeButtonHint,
        Qt.WindowCloseButtonHint,
        Qt.WindowStaysOnTopHint,
    ):
        assert flags & hint, hint
    assert bool(flags & Qt.FramelessWindowHint) == (sys.platform == "win32")


def test_fullscreen_return_restores_floating_chrome_and_surface(player_scene):
    app, window, scene, presentation = player_scene
    for mode in ("floating", "fullscreen", "floating"):
        scene.setProperty("presentationMode", mode)
        app.processEvents()
        assert scene.property("activeSurfaceName") == "watchPresentationVideoSurface"
        assert window.property("playerSurfaceBound")
        assert bool(presentation.flags() & Qt.WindowStaysOnTopHint) == (
            mode == "floating"
        )
    assert presentation.flags() & Qt.WindowTitleHint
    assert presentation.flags() & Qt.WindowCloseButtonHint
    assert presentation.close()
    app.processEvents()
    assert scene.property("presentationMode") == "embedded"
    assert not presentation.isVisible()
    assert scene.property("activeSurfaceName") == "watchVideoSurface"
    assert window.property("playerSurfaceBound")


def test_floating_escape_returns_to_embedded_without_losing_player(player_scene):
    app, window, scene, presentation = player_scene
    scene.setProperty("presentationMode", "floating")
    app.processEvents()
    presentation.requestActivate()
    app.processEvents()
    QTest.keyClick(presentation, Qt.Key_Escape)
    app.processEvents()
    assert scene.property("presentationMode") == "embedded"
    assert not presentation.isVisible()
    assert scene.property("activeSurfaceName") == "watchVideoSurface"
    assert window.property("playerSurfaceBound")


def test_shared_windows_controls_change_real_window_state():
    # Exercise production controls on any CI host; substitute only OS eligibility.
    app = qt_app()
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("theme", dict(THEME))
    engine.rootContext().setContextProperty("buttonFontFamily", "Sans Serif")
    engine.rootContext().setContextProperty("bridge", {"themeRevision": 0})
    engine.rootContext().setContextProperty(
        "buttonMetrics",
        {
            name: {
                "height": metrics.height,
                "fontPixels": metrics.font_pixels,
                "horizontalPadding": metrics.horizontal_padding,
                "iconPixels": metrics.icon_pixels,
            }
            for name, metrics in qt_main.BUTTON_METRICS.items()
        },
    )
    engine.addImageProvider("vodforge", qt_main.Materials())
    path = Path(qt_main.__file__).with_name("WindowsFrame.qml")
    component = QQmlComponent(engine)
    component.setData(
        path.read_bytes().replace(b'Qt.platform.os === "windows"', b"true"),
        QUrl.fromLocalFile(str(path)),
    )
    window = QQuickWindow()
    window.resize(500, 300)
    frame = component.createWithInitialProperties({"appWindow": window})
    assert frame is not None, component.errors()
    frame.setParentItem(window.contentItem())
    window.show()
    app.processEvents()

    def click(name):
        def find(item):
            if item.objectName() == "window" + name:
                return item
            return next(
                (
                    found
                    for child in item.childItems()
                    if (found := find(child)) is not None
                ),
                None,
            )

        item = find(frame)
        assert item is not None and item.isVisible()
        point = item.mapToScene(item.boundingRect().center())
        QTest.mouseClick(
            window, Qt.LeftButton, pos=QPoint(round(point.x()), round(point.y()))
        )
        app.processEvents()

    try:
        click("Maximize")
        assert window.visibility() == QQuickWindow.Maximized
        click("Maximize")
        assert window.visibility() == QQuickWindow.Windowed
        click("Minimize")
        assert window.visibility() == QQuickWindow.Minimized
        window.showNormal()
        app.processEvents()
        click("Close")
        assert not window.isVisible()
    finally:
        window.close()
        frame.setParentItem(None)
        frame.deleteLater()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
