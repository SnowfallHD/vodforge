"""Opt-in macOS proof that retiring presentation removes its fullscreen Space."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QTest

from tests.test_qt_scene_port import qt_app, saved
from yt_downloader.playback_backend import PlaybackSnapshot
from yt_downloader.playback_progress import PlaybackProgressOwner
from yt_downloader.qt_quick import main as qt_main

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="requires an isolated native macOS Qt run",
)


@pytest.mark.parametrize("destination", ["embedded", "floating"])
@pytest.mark.parametrize("playing", [True, False])
def test_retiring_fullscreen_exits_native_space(
    tmp_path, monkeypatch, destination, playing
):
    import objc
    from AppKit import NSWindowStyleMaskFullScreen

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "cocoa")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    assert app.platformName() == "cocoa"
    bridge = qt_main.Bridge(None)
    record = saved(tmp_path, "Fullscreen fixture", "MP4")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("real native playback requires ffmpeg")
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=15",
            "-t",
            "20",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            record["vodforge_output_path"],
        ],
        check=True,
        timeout=30,
    )
    bridge._runtime.history = [record]
    bridge._engagement.presented_welcome()
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.select("Library")
        assert bridge.openLibraryItem(0)
        QTest.qWait(400)
        player = window.property("mediaPlayer")
        assert player.property("playbackState") == QMediaPlayer.PlayingState
        if not playing:
            player.pause()
            app.processEvents()
        scene = window.findChild(QObject, "watchPlayerScene")
        presentation = window.findChild(QObject, "watchPresentationWindow")
        scene.setPresentation("fullscreen")
        QTest.qWait(1800)
        native = objc.objc_object(c_void_p=int(presentation.winId())).window()
        assert native.styleMask() & NSWindowStyleMaskFullScreen
        if destination == "embedded":
            # This is the actual Back route, including its mode retirement.
            scene.closeRequested.emit()
        else:
            scene.setPresentation("floating")
        QTest.qWait(1800)
        assert not native.styleMask() & NSWindowStyleMaskFullScreen
        assert presentation.isVisible() is (destination == "floating")
        assert scene.property("presentationMode") == destination
        if destination == "embedded":
            assert bridge.selection == "Library"
            assert window.property("miniPlayerActive") is playing
        if playing:
            position = player.property("position")
            QTest.qWait(250)
            assert player.property("position") > position
        else:
            assert bridge.playbackUrl.isEmpty() is (destination == "embedded")
    finally:
        presentation.showNormal()
        QTest.qWait(1200)
        presentation.close()
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


@pytest.mark.parametrize("close_route", ["mini", "paused_back"])
def test_native_replay_back_keeps_watch_hero_progress_current(
    tmp_path, monkeypatch, close_route
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "cocoa")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("real native playback requires ffmpeg")
    record = saved(tmp_path, "Replay fixture", "MP4")
    record["duration"] = 8
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=15",
            "-t",
            "8",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            record["vodforge_output_path"],
        ],
        check=True,
        timeout=30,
    )
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [record]
    progress = bridge._playback_progress
    session = progress.begin(record)
    assert progress.observe(session, PlaybackSnapshot(None, "Paused", 4, 8, 80))
    assert progress.retire(session)
    bridge._engagement.presented_welcome()
    bridge.selectHome("Watch")
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    presentation = window.findChild(QObject, "watchPresentationWindow")

    def until(predicate):
        for _ in range(100):
            app.processEvents()
            if predicate():
                return True
            QTest.qWait(100)
        return False

    try:
        watch = window.findChild(QObject, "watchBrowseScene")
        label = window.findChild(QObject, "watchHeroProgressLabel")
        projection = watch.property("projection")
        assert label.property("text") == "0:04 / 0:08"
        bridge.playWatchHero(projection["hero"]["owner"])
        player = window.property("mediaPlayer")
        scene = window.findChild(QObject, "watchPlayerScene")
        assert until(lambda: player.property("position") >= 4000)
        scene.setPresentation("fullscreen")
        assert until(lambda: bridge._playback_status == "Ended")
        assert label.property("text") == ""
        # Play at EndOfMedia is the actual replay command, not a synthetic seek.
        scene.togglePlayback()
        assert until(lambda: 1000 <= player.property("position") < 4000)
        scene.setPresentation("floating")
        if close_route == "paused_back":
            player.pause()
            app.processEvents()
        scene.closeRequested.emit()
        if close_route == "mini":
            assert until(
                lambda: window.property("miniPlayerActive") and watch.isVisible()
            )
            player.pause()
        app.processEvents()
        observed = progress.for_record(record)
        assert observed and 1 <= observed.position < 4 and not observed.completed
        assert label.property("text") == "0:0" + str(int(observed.position)) + " / 0:08"
        if close_route == "mini":
            assert watch.property("projection") == projection
            window.findChild(QObject, "miniPlayerClose").activated.emit()
        assert until(lambda: bridge.playbackUrl.isEmpty())
        reopened = PlaybackProgressOwner(progress.path)
        reopened.load()
        assert reopened.for_record(record).position == observed.position
        assert not reopened.for_record(record).completed
    finally:
        presentation.showNormal()
        QTest.qWait(1200)
        presentation.close()
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


@pytest.mark.parametrize("surface", ["embedded", "mini", "floating"])
def test_qt_ended_video_retains_frame_and_replays(tmp_path, monkeypatch, surface):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "cocoa")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    media = saved(tmp_path, "Last frame", "MP4")
    media["duration"] = 2
    subprocess.run(
        [
            shutil.which("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x3399ff:size=320x180:rate=15",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            media["vodforge_output_path"],
        ],
        check=True,
        timeout=30,
    )
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [media]
    bridge._engagement.presented_welcome()
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    presentation = window.findChild(QObject, "watchPresentationWindow")

    def until(predicate):
        for _ in range(100):
            app.processEvents()
            if predicate():
                return True
            QTest.qWait(50)
        return False

    try:
        bridge.selectHome("Library")
        assert bridge.openLibraryItem(0)
        player = window.property("mediaPlayer")
        scene = window.findChild(QObject, "watchPlayerScene")
        assert until(lambda: player.property("position") >= 200)
        if surface == "mini":
            scene.closeRequested.emit()
            output = window.findChild(QObject, "miniVideoSurface")
            assert window.property("miniPlayerActive")
        elif surface == "floating":
            scene.setPresentation("floating")
            output = window.findChild(QObject, "watchPresentationVideoSurface")
        else:
            output = window.findChild(QObject, "watchVideoSurface")
        target = presentation if surface == "floating" else window

        def blue_frame():
            image = target.grabWindow()
            if image.isNull():
                return False
            point = output.mapToScene(QPointF(output.width() / 2, output.height() / 2))
            ratio = image.devicePixelRatio()
            color = image.pixelColor(round(point.x() * ratio), round(point.y() * ratio))
            return color.blue() > 180 and color.red() < 80

        assert until(blue_frame), "fixture must render before EndOfMedia"
        assert until(lambda: player.property("mediaStatus") == QMediaPlayer.EndOfMedia)
        QTest.qWait(150)
        assert blue_frame(), (
            "ended playback must retain its frame instead of a blank surface"
        )
        assert bridge._playback_progress.for_record(media).completed
        if surface == "mini":
            window.findChild(QObject, "miniPlayerPause").activated.emit()
        else:
            scene.togglePlayback()
        assert until(lambda: 100 <= player.property("position") < 1000)
        assert until(blue_frame)
        assert not bridge._playback_progress.for_record(media).completed
    finally:
        presentation.close()
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
