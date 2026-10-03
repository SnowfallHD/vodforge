"""Growing the Watch window must not abruptly shrink its primary video."""

from itertools import pairwise

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QObject, QTimer

from tests.test_qt_scene_port import qt_app, saved
from yt_downloader.qt_quick import main as qt_main


def settle():
    loop = QEventLoop()
    QTimer.singleShot(30, loop.quit)
    loop.exec()


def test_header_and_related_admission_preserve_primary_video_size(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    bridge._engagement.presented_welcome()
    bridge._settings["whats_new_seen"] = qt_main.SHOWCASE_ID
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    bridge._window = window
    bridge._runtime.history = [saved(tmp_path, "Resize", "MP4")]
    (tmp_path / "Resize.mp4").write_bytes(b"layout fixture")
    window.setProperty("playerVolume", 0)
    assert bridge.openLibraryItem(0)
    scene = window.findChild(QObject, "watchPlayerScene")
    stage = window.findChild(QObject, "playerMediaStage")
    header = window.findChild(QObject, "focusHeader")
    side = window.findChild(QObject, "playerRelatedSide")
    compact = window.findChild(QObject, "playerRelatedCompact")
    widths = (
        940,
        950,
        958,
        960,
        966,
        976,
        990,
        1080,
        1100,
        1118,
        1122,
        1140,
        1180,
        1240,
        1300,
        1440,
    )
    samples = []
    try:
        for width in widths:
            window.resize(width, 740)
            settle()
            samples.append(
                (
                    window.width(),
                    header.height(),
                    scene.width(),
                    stage.width(),
                    stage.height(),
                    bool(side.property("visible")),
                )
            )
            assert stage.width() / stage.height() == pytest.approx(16 / 9, abs=0.01)
            assert compact is None
            assert stage.x() == 0
            assert stage.parentItem().parentItem().x() == 0
        assert {row[1] for row in samples} == {44}
        assert {row[-1] for row in samples} == {True}
        # Preserve the existing 12→20px outer gutters (at most16px total).
        # Header wrapping and sidebar admission previously lost~100–170px.
        assert all(after[3] >= before[3] - 16 for before, after in pairwise(samples)), (
            samples
        )
        # Exercise the same boundaries inward; layout may move recommendations,
        # but the primary frame must not suddenly grow as its window shrinks.
        reverse = []
        for width in reversed(widths):
            window.resize(width, 740)
            settle()
            reverse.append(stage.width())
        assert all(after <= before + 16 for before, after in pairwise(reverse)), reverse
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
