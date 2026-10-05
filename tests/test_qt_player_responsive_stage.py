"""Player and recommendations share viewport growth without stretching video."""

from itertools import pairwise

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF

from tests.test_qt_scene_port import qt_app, saved
from yt_downloader.qt_quick import main as qt_main


def test_player_stage_and_recommendations_grow_with_viewport(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [saved(tmp_path, str(i), "MP4") for i in range(3)]
    for i in range(3):
        (tmp_path / f"{i}.mp4").write_bytes(b"layout fixture")
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    bridge._window = window
    try:
        assert bridge.openLibraryItem(0)
        stage = window.findChild(QObject, "playerMediaStage")
        side = window.findChild(QObject, "playerRelatedSide")
        compact = window.findChild(QObject, "playerRelatedCompact")
        scene = window.findChild(QObject, "watchPlayerScene")
        overlay = window.findChild(QObject, "embeddedPlayerOverlay")
        caption = window.findChild(QObject, "embeddedCaptionText")
        sizes = []
        for width, height in (
            (820, 650),
            (1100, 800),
            (1440, 800),
            (1800, 900),
            (2400, 1200),
        ):
            window.resize(width, height)
            for _ in range(8):
                app.processEvents()
            assert stage.width() / stage.height() == pytest.approx(16 / 9, abs=0.02)
            assert stage.width() <= stage.parentItem().width() + 1
            assert stage.x() == 0
            assert stage.parentItem().parentItem().x() == 0
            assert overlay.width() == pytest.approx(stage.width())
            # Fractional font advances can exceed the conservative twelve-point
            # gap budget by a fraction of one layout point on a different font
            # backend. Verify actual row bounds and separation as well.
            assert overlay.property("minimumControlsWidth") <= stage.width() + 1
            left_actions = overlay.findChild(QObject, "playerOverlayLeftActions")
            right_actions = overlay.findChild(QObject, "playerOverlayRightActions")
            assert left_actions.x() >= 0
            assert left_actions.x() + left_actions.width() <= right_actions.x()
            assert right_actions.x() + right_actions.width() <= stage.width()
            assert 0 <= caption.x()
            assert caption.x() + caption.width() <= stage.width()
            assert side.property("visible") is True
            assert bool(side.property("visible")) == bool(
                scene.property("hasRelatedSide")
            )
            assert compact is None
            if side.property("visible"):
                # The bounded sidebar leaves the majority of the row for video.
                assert 270 <= side.width() <= 360
                row = stage.parentItem().parentItem()
                assert stage.width() >= row.width() * 0.60
                assert stage.width() >= scene.width() * 0.50
                assert side.width() <= scene.width() * 0.37
                for item in (stage, side):
                    origin = item.mapToItem(scene, QPointF(0, 0))
                    assert origin.x() >= -1
                    assert origin.x() + item.width() <= scene.width() + 1
                    assert origin.y() >= -1
                    assert origin.y() + item.height() <= scene.height() + 1
                gap = side.x() - (stage.parentItem().x() + stage.x() + stage.width())
                assert 15 <= gap <= 40
                sizes.append((stage.width(), side.width()))
        assert len(sizes) == 5
        assert all(after[0] > before[0] for before, after in pairwise(sizes))
        assert all(after[1] >= before[1] for before, after in pairwise(sizes))
        assert sizes[-1][0] > sizes[0][0] * 1.5
        assert sizes[-1][1] > sizes[0][1]
        assert sizes[-1][1] == pytest.approx(360)
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
