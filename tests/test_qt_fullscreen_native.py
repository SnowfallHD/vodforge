"""Opt-in macOS proof that retiring presentation removes its fullscreen Space."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QTest

from tests.test_qt_scene_port import qt_app, saved
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
