"""Local player fallback states and responsive video/side geometry."""

from dataclasses import replace

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject
from PySide6.QtQml import QQmlExpression
from PySide6.QtTest import QTest

from tests.test_qt_scene_port import qt_app, saved
from yt_downloader.qt_quick import main


@pytest.mark.parametrize("width,height", [(820, 560), (1280, 800), (1920, 1080)])
@pytest.mark.parametrize("others", [0, 1, 3])
def test_player_local_fallback_is_owner_safe_and_balanced(
    tmp_path, monkeypatch, width, height, others
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    original_plan = main.player_related_plan

    def fallback_plan(*args):
        plan = original_plan(*args)
        return replace(plan, up_next=(), recent=plan.recent + plan.recent[:1])

    monkeypatch.setattr(main, "player_related_plan", fallback_plan)
    bridge = main.Bridge(None)
    bridge._runtime.history = [
        saved(tmp_path, str(i), "MP4") for i in range(others + 1)
    ]
    for i in range(others + 1):
        (tmp_path / f"{i}.mp4").write_bytes(b"fixture")
    engine = main.create_engine(bridge)
    window = engine.rootObjects()[0]
    bridge._window = window
    try:
        assert bridge.openLibraryItem(0)
        window.resize(width, height)
        for _ in range(5):
            app.processEvents()
        side = window.findChild(QObject, "playerRelatedSide")
        compact = window.findChild(QObject, "playerRelatedCompact")
        scene = side.parentItem().parentItem().parentItem().parentItem()
        # Locate the production scene by its declared relatedCards property.
        while scene is not None and scene.property("relatedCards") is None:
            scene = scene.parentItem()
        cards = scene.property("relatedCards").toVariant()
        assert len(cards) == others
        assert len({row["owner"] for row in cards}) == others
        assert bridge.playerScene["owner"] not in {row["owner"] for row in cards}
        assert side.property("visible") is (width >= 1080)
        assert compact.property("visible") is (width < 1080)
        stage = window.findChild(QObject, "playerMediaStage")
        assert stage.width() / stage.height() == pytest.approx(16 / 9)
        assert stage.height() <= scene.height()
        if width >= 1080:
            assert stage.width() > scene.width() * 0.55
            assert 270 <= side.width() <= 360
        add = window.findChild(
            QObject,
            "playerRelatedAddMedia"
            if width >= 1080
            else "playerRelatedCompactAddMedia",
        )
        assert add.property("visible") is (others == 0)
        assert (
            window.findChild(QObject, "playerRecentRail").property("visible") is False
        )
        assert scene.property("relatedLoading") is False
        bridge._playback_record = None
        bridge.playerSceneChanged.emit()
        app.processEvents()
        assert scene.property("relatedLoading") is True
        assert add.property("visible") is False
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


@pytest.mark.parametrize(
    "size,rotation,expected",
    [
        ((640, 360), 0, 16 / 9),
        ((320, 480), 0, 2 / 3),
        ((640, 360), 90, 9 / 16),
        ((400, 200), 270, 0.5),
    ],
)
def test_embedded_stage_follows_qt_displayed_frame_aspect(
    tmp_path, monkeypatch, size, rotation, expected
):
    from PySide6.QtGui import QImage
    from PySide6.QtMultimedia import QtVideo, QVideoFrame

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = main.Bridge(None)
    bridge._runtime.history = [saved(tmp_path, "frame", "MP4")]
    (tmp_path / "frame.mp4").write_bytes(b"fixture")
    engine = main.create_engine(bridge)
    window = engine.rootObjects()[0]
    bridge._window = window
    try:
        assert bridge.openLibraryItem(0)
        window.resize(1280, 800)
        window.show()
        QTest.qWait(100)
        for _ in range(3):
            app.processEvents()
        output = window.findChild(QObject, "watchVideoSurface")
        frame = QVideoFrame(QImage(*size, QImage.Format_RGB32))
        frame.setRotation(QtVideo.Rotation(rotation))
        output.property("videoSink").setVideoFrame(frame)
        QTest.qWait(100)
        for _ in range(5):
            app.processEvents()
        stage = window.findChild(QObject, "playerMediaStage")
        assert stage.width() / stage.height() == pytest.approx(expected)
        assert QQmlExpression(
            engine.rootContext(), output, "fillMode === 1"
        ).evaluate()[0]
        rect = output.property("contentRect")
        assert rect.width() <= output.width() + 0.1
        assert rect.height() <= output.height() + 0.1
        scene = stage.parentItem()
        while scene.property("displayedVideoAspect") is None:
            scene = scene.parentItem()
        scene.setProperty("videoFill", True)
        QTest.qWait(50)
        assert stage.width() / stage.height() == pytest.approx(expected)
        assert scene.property("videoAspect") == pytest.approx(expected)
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_embedded_stage_respects_decoded_sample_aspect_ratio(tmp_path, monkeypatch):
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg required for real SAR fixture")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x240:r=2",
            "-vf",
            "setsar=2",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(tmp_path / "sar.mp4"),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    qt_app()
    bridge = main.Bridge(None)
    bridge._runtime.history = [saved(tmp_path, "sar", "MP4")]
    engine = main.create_engine(bridge)
    window = engine.rootObjects()[0]
    bridge._window = window
    try:
        window.resize(1280, 800)
        window.show()
        assert bridge.openLibraryItem(0)
        stage = window.findChild(QObject, "playerMediaStage")
        for _ in range(40):
            QTest.qWait(50)
            if abs(stage.width() / stage.height() - 8 / 3) < 0.001:
                break
        assert stage.width() / stage.height() == pytest.approx(8 / 3)
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
