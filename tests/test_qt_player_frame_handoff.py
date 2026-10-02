"""Terminal video frames and late native visibility retain one presentation owner."""

import pytest
from PySide6.QtCore import QObject
from PySide6.QtGui import QColor, QImage
from PySide6.QtMultimedia import QVideoFrame
from PySide6.QtQuick import QQuickWindow

from tests.test_qt_floating_player_chrome import (
    player_scene as presentation_fixture,  # noqa: F401
)
from tests.test_qt_player_hover_aspect import flush
from tests.test_qt_scene_port import saved


@pytest.fixture
def player_scene(presentation_fixture):  # noqa: F811
    app, window, scene, floating = presentation_fixture
    scene.property("appBridge")._window = window
    return app, window, scene, floating


@pytest.mark.parametrize("mode", ["floating", "fullscreen"])
def test_terminal_frame_reaches_new_sink_without_playback_restart(player_scene, mode):
    app, window, scene, _ = player_scene
    bridge = scene.property("appBridge")
    bridge._window = window
    bridge._playback_record = saved(
        bridge._runtime.history_path.parent, "Terminal", "MP4"
    )
    bridge.playerSceneChanged.emit()
    flush(app)
    source = window.findChild(QObject, "watchVideoSurface").property("videoSink")
    image = QImage(160, 90, QImage.Format_RGBA8888)
    image.fill(QColor("#227799"))
    source.setVideoFrame(QVideoFrame(image))
    flush(app)
    assert source.videoFrame().isValid()
    assert bridge._playback_retained_frame.isValid(), (
        scene.property("displayedOwner"),
        bridge._playback_frame_owner,
    )
    scene.setProperty("presentationMode", mode)
    flush(app)
    target = window.findChild(QObject, "watchPresentationVideoSurface").property(
        "videoSink"
    )
    assert target.videoFrame().isValid()
    assert target.videoFrame().toImage().pixelColor(80, 45) == image.pixelColor(80, 45)


def test_late_native_show_is_retired_after_embedded_return(player_scene):
    app, window, scene, floating = player_scene
    bridge = scene.property("appBridge")
    bridge._playback_record = saved(
        bridge._runtime.history_path.parent, "Terminal", "MP4"
    )
    bridge.playerSceneChanged.emit()
    scene.setProperty("presentationMode", "fullscreen")
    flush(app)
    scene.setProperty("presentationMode", "embedded")
    flush(app)
    assert not floating.isVisible()
    # Cocoa's fullscreen transition may finish after the first hide receipt.
    floating.setVisibility(QQuickWindow.Windowed)
    flush(app)
    assert scene.property("presentationMode") == "embedded"
    assert not floating.isVisible()
    assert window.property("playerSurfaceBound")


def test_pending_retirement_cannot_hide_new_floating_owner(player_scene):
    app, _, scene, floating = player_scene
    bridge = scene.property("appBridge")
    bridge._playback_record = saved(
        bridge._runtime.history_path.parent, "Terminal", "MP4"
    )
    bridge.playerSceneChanged.emit()
    scene.setProperty("presentationMode", "fullscreen")
    flush(app)
    scene.setProperty("presentationMode", "embedded")
    floating.setVisibility(QQuickWindow.Windowed)
    scene.setProperty("presentationMode", "floating")
    flush(app)
    assert floating.isVisible()
    assert scene.property("presentationMode") == "floating"


def test_same_owner_new_generation_cannot_restore_old_frame(player_scene):
    app, window, scene, _ = player_scene
    bridge = scene.property("appBridge")
    bridge._playback_record = saved(
        bridge._runtime.history_path.parent, "Terminal", "MP4"
    )
    bridge.playerSceneChanged.emit()
    flush(app)
    source = window.findChild(QObject, "watchVideoSurface").property("videoSink")
    image = QImage(160, 90, QImage.Format_RGBA8888)
    image.fill(QColor("#227799"))
    source.setVideoFrame(QVideoFrame(image))
    flush(app)
    assert bridge._playback_retained_frame.isValid()
    bridge._playback_generation += 1
    scene.setProperty("presentationMode", "floating")
    flush(app)
    target = window.findChild(QObject, "watchPresentationVideoSurface").property(
        "videoSink"
    )
    assert not target.videoFrame().isValid()


def test_unknown_sink_changed_source_and_close_reject_frame_reuse(player_scene):
    from PySide6.QtCore import QUrl

    app, window, scene, _ = player_scene
    bridge = scene.property("appBridge")
    bridge._playback_record = saved(
        bridge._runtime.history_path.parent, "Terminal", "MP4"
    )
    bridge.playerSceneChanged.emit()
    flush(app)
    source_item = window.findChild(QObject, "watchVideoSurface")
    source = source_item.property("videoSink")
    image = QImage(160, 90, QImage.Format_RGBA8888)
    image.fill(QColor("#227799"))
    source.setVideoFrame(QVideoFrame(image))
    flush(app)
    unknown = QObject()
    unknown.setObjectName("watchVideoSurface")
    assert (
        bridge._owned_playback_sink(unknown, scene.property("displayedOwner")) is None
    )
    bridge._playback_url = QUrl.fromLocalFile("/tmp/fictional-other-owner.mp4")
    assert (
        bridge._owned_playback_sink(source_item, scene.property("displayedOwner"))
        is None
    )
    bridge.closePlayback(True)
    assert not bridge._playback_retained_frame.isValid()
    assert bridge._playback_frame_generation == -1
    assert bridge._playback_record is None


def test_mini_latest_frame_is_retained_for_return_not_pre_mini_frame(player_scene):
    app, window, scene, _ = player_scene
    bridge = scene.property("appBridge")
    bridge._playback_record = saved(
        bridge._runtime.history_path.parent, "Terminal", "MP4"
    )
    bridge.playerSceneChanged.emit()
    flush(app)
    first = QImage(160, 90, QImage.Format_RGBA8888)
    first.fill(QColor("blue"))
    inline = window.findChild(QObject, "watchVideoSurface").property("videoSink")
    inline.setVideoFrame(QVideoFrame(first))
    flush(app)
    window.setProperty("miniPlayerActive", True)
    flush(app)
    latest = QImage(160, 90, QImage.Format_RGBA8888)
    latest.fill(QColor("red"))
    mini = window.findChild(QObject, "miniVideoSurface").property("videoSink")
    mini.setVideoFrame(QVideoFrame(latest))
    flush(app)
    assert bridge._playback_retained_frame.toImage().pixelColor(80, 45) == QColor("red")
    inline.setVideoFrame(QVideoFrame())
    window.setProperty("miniPlayerActive", False)
    flush(app)
    assert inline.videoFrame().toImage().pixelColor(80, 45) == QColor("red")
