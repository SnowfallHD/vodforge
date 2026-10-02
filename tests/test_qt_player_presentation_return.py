"""Fullscreen/native exit restores the originating surface and inline recovery."""

import pytest
from PySide6.QtCore import Property, QObject, Qt
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QVideoFrame
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from tests.test_qt_floating_player_chrome import (
    player_scene as presentation_fixture,  # noqa: F401
)
from tests.test_qt_player_hover_aspect import flush
from tests.test_qt_scene_port import saved


@pytest.fixture
def player_scene(presentation_fixture):  # noqa: F811
    return presentation_fixture


@pytest.mark.parametrize("origin", ["embedded", "floating"])
@pytest.mark.parametrize("exit_kind", ["escape", "native", "inline", "close"])
def test_origin_return_owns_one_surface_and_preserves_state(
    player_scene,
    origin,
    exit_kind,
):
    app, window, scene, floating = player_scene
    bridge = scene.property("appBridge")
    bridge._playback_record = saved(
        bridge._runtime.history_path.parent, "Fictional", "MP4"
    )
    bridge.playerSceneChanged.emit()
    flush(app)
    bridge.select("Watch")
    window.findChild(QObject, "watchBrowseScene").setProperty("visible", False)
    scene.setProperty("visible", True)
    flush(app)

    class Paused(QObject):
        activeSubtitleTrack = Property(int, lambda self: -1, constant=True)
        subtitleTracks = Property("QVariantList", lambda self: [], constant=True)
        playbackState = Property(int, lambda self: 2, constant=True)
        position = Property(int, lambda self: 12345, constant=True)
        duration = Property(int, lambda self: 20000, constant=True)

    snapshot = Paused()
    scene.setProperty("player", snapshot)
    for _ in range(2):
        scene.setProperty("presentationMode", origin)
        flush(app)
        scene.setProperty("presentationMode", "fullscreen")
        flush(app)
        assert scene.property("fullscreenReturnMode") == origin
        assert scene.property("fullscreenEntered")
        placeholder = window.findChild(QObject, "inlinePlaybackElsewhere")
        button = window.findChild(QObject, "inlinePlaybackReturn")
        assert placeholder.isVisible()
        assert button.property("label") == (
            "Exit fullscreen" if origin == "embedded" else "Exit external player"
        )
        assert not scene.findChild(QObject, "watchVideoSurface").isVisible()
        assert not scene.findChild(QObject, "embeddedPlayerOverlay").isVisible()
        if exit_kind == "escape":
            floating.requestActivate()
            QTest.keyClick(floating, Qt.Key_Escape)
        elif exit_kind == "native":
            floating.setVisibility(QQuickWindow.Windowed)
        elif exit_kind == "inline":
            button.activated.emit()
        else:
            floating.close()
        flush(app)
        expected = origin if exit_kind in {"escape", "native"} else "embedded"
        assert scene.property("presentationMode") == expected
        assert scene.property("activeSurfaceName") == (
            "watchVideoSurface"
            if expected == "embedded"
            else "watchPresentationVideoSurface"
        )
        assert floating.isVisible() == (expected == "floating")
        assert window.property("playerSurfaceBound")
        assert scene.property("player") is snapshot
        assert snapshot.property("position") == 12345
        assert snapshot.property("playbackState") == 2


def test_initial_popout_uses_actual_rotated_frame_and_media_reset(player_scene):
    app, window, scene, floating = player_scene
    bridge = scene.property("appBridge")
    bridge._window = window
    first = saved(bridge._runtime.history_path.parent, "First", "MP4")
    bridge._playback_record = first
    bridge.playerSceneChanged.emit()
    flush(app)
    assert not scene.property("videoFill")
    scene.setProperty("videoFill", True)
    bridge.playerSceneChanged.emit()
    flush(app)
    assert scene.property("videoFill")  # Same owner refresh preserves explicit choice.
    bridge._playback_record = saved(
        bridge._runtime.history_path.parent, "Second", "MP4"
    )
    bridge.playerSceneChanged.emit()
    flush(app)
    assert not scene.property("videoFill")
    scene.setProperty("presentationMode", "floating")
    image = QImage(320, 180, QImage.Format_RGB32)
    image.fill(0xFF4488AA)
    frame = QVideoFrame(image)
    frame.setRotationAngle(QVideoFrame.Rotation90)
    surface = floating.findChild(QObject, "watchPresentationVideoSurface")
    surface.property("videoSink").setVideoFrame(frame)
    QTest.qWait(30)
    flush(app)
    assert floating.property("displayedAspect") == pytest.approx(9 / 16)
    assert floating.width() / floating.height() == pytest.approx(9 / 16, abs=0.01)
    assert not floating.property("naturalSizePending")
    # A deliberate manual crop remains available; no global aspect lock/gesture inference.
    scene.setProperty("videoFill", True)
    floating.resize(700, 410)
    flush(app)
    assert (floating.width(), floating.height()) == (700, 410)


def test_deferred_native_exit_does_not_retarget_new_presentation(player_scene):
    app, window, scene, floating = player_scene
    bridge = scene.property("appBridge")
    bridge._playback_record = saved(bridge._runtime.history_path.parent, "Old", "MP4")
    bridge.playerSceneChanged.emit()
    flush(app)
    scene.setProperty("presentationMode", "fullscreen")
    flush(app)
    floating.setVisibility(QQuickWindow.Windowed)
    # Before its queued exit runs, a new presentation and owner take ownership.
    scene.setProperty("presentationMode", "floating")
    bridge._playback_record = saved(bridge._runtime.history_path.parent, "New", "MP4")
    bridge.playerSceneChanged.emit()
    scene.setProperty("presentationMode", "fullscreen")
    flush(app)
    assert scene.property("presentationMode") == "fullscreen"
    assert floating.visibility() == QQuickWindow.FullScreen
    assert window.property("playerSurfaceBound")
    floating.setVisibility(QQuickWindow.Windowed)
    floating.close()
    flush(app)
    assert scene.property("presentationMode") == "embedded"
    assert not floating.isVisible()
    assert window.property("playerSurfaceBound")
