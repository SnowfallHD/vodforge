"""Floating playback must request usable native chrome, including with on-top."""

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt
from PySide6.QtTest import QTest

from tests.test_qt_scene_port import qt_app
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
    assert not flags & Qt.FramelessWindowHint


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
