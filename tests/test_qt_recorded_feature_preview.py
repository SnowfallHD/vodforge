"""Local demo decoding and lifecycle; fixture footage is not a UI recording."""

import shutil
import subprocess
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QObject, QTimer, QUrl
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtQml import QQmlComponent, QQmlContext, QQmlEngine

from tests.test_qt_scene_port import qt_app
from yt_downloader.qt_quick import main


def wait_until(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        loop = QEventLoop()
        QTimer.singleShot(20, loop.quit)
        loop.exec()
    assert predicate()


@pytest.mark.parametrize(
    "asset",
    [None, "forge-feedback", "watch-player", "library-actions", "captions-player"],
)
def test_recorded_preview_decodes_silently_and_releases_hidden_media(
    tmp_path, monkeypatch, asset
):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("Existing FFmpeg required to make local decoder fixture")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    movie = tmp_path / "decoder-fixture.mp4"
    if asset:
        movie = Path(__file__).parents[1] / "assets/whats-new" / f"{asset}.mp4"
    else:
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=red:s=320x180:r=20",
                "-t",
                "1",
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(movie),
            ],
            check=True,
            timeout=15,
        )
    qt_app()
    bridge = main.Bridge(None)
    engine = main.create_engine(bridge)
    window = engine.rootObjects()[0]
    context = QQmlContext(QQmlEngine.contextForObject(window))
    component = QQmlComponent(
        engine,
        QUrl.fromLocalFile(
            str(
                Path(__file__).parents[1]
                / "yt_downloader/qt_quick/RecordedFeaturePreview.qml"
            )
        ),
    )
    preview = component.create(context)
    assert preview is not None, component.errors()
    preview.setParentItem(window.contentItem())
    preview.setWidth(430)
    preview.setHeight(242)
    preview.setProperty("recordingSource", QUrl.fromLocalFile(str(movie)))
    preview.setProperty("foreground", True)
    try:
        assert not preview.property("loadRecording")
        preview.setProperty("active", True)
        wait_until(
            lambda: preview.findChild(QObject, "recordedPreviewPlayer") is not None
        )
        player = preview.findChild(QObject, "recordedPreviewPlayer")
        wait_until(
            lambda: (
                player.playbackState() == QMediaPlayer.PlayingState
                and preview.property("frameReady")
            )
        )
        assert player.audioOutput().isMuted()
        assert player.audioOutput().volume() == 0
        wait_until(lambda: player.duration() > 0)
        player.setPosition(player.duration() - 100)
        wait_until(
            lambda: (
                player.position() < 500
                and player.playbackState() == QMediaPlayer.PlayingState
            )
        )
        preview.setProperty("pausedByUser", True)
        wait_until(lambda: player.playbackState() == QMediaPlayer.PausedState)
        assert preview.property("frameReady")
        preview.setProperty("foreground", False)
        preview.setProperty("pausedByUser", False)
        assert not preview.property("playRecording")
        preview.setProperty("reducedMotion", True)
        wait_until(lambda: preview.findChild(QObject, "recordedPreviewPlayer") is None)
        assert not preview.property("loadRecording")
        preview.setProperty("reducedMotion", False)
        preview.setProperty("foreground", True)
        wait_until(
            lambda: preview.findChild(QObject, "recordedPreviewPlayer") is not None
        )
        preview.setProperty("active", False)
        wait_until(lambda: preview.findChild(QObject, "recordedPreviewPlayer") is None)
        preview.setProperty("active", True)
        wait_until(
            lambda: preview.findChild(QObject, "recordedPreviewPlayer") is not None
        )
        preview.setVisible(False)
        wait_until(lambda: preview.findChild(QObject, "recordedPreviewPlayer") is None)
        preview.setVisible(True)
        wait_until(
            lambda: preview.findChild(QObject, "recordedPreviewPlayer") is not None
        )
        window.hide()
        wait_until(lambda: preview.findChild(QObject, "recordedPreviewPlayer") is None)
        assert bridge._playback_binding is None
    finally:
        preview.deleteLater()
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
