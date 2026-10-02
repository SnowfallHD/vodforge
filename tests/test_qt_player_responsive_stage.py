"""Player and recommendations share viewport growth without stretching video."""

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject

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
        sizes = []
        for width, height in ((820, 650), (1100, 800), (1280, 800), (2400, 1200)):
            window.resize(width, height)
            for _ in range(8):
                app.processEvents()
            assert stage.width() / stage.height() == pytest.approx(16 / 9, abs=0.02)
            assert stage.width() <= stage.parentItem().width() + 1
            assert bool(side.property("visible")) == bool(scene.property("wide"))
            assert bool(compact.property("visible")) != bool(scene.property("wide"))
            if side.property("visible"):
                assert 310 <= side.width() <= 480
                gap = side.x() - (stage.parentItem().x() + stage.x() + stage.width())
                assert 15 <= gap <= 40
                sizes.append((stage.width(), side.width()))
        assert sizes[1][0] > sizes[0][0] * 1.3
        assert sizes[1][1] > sizes[0][1] * 1.3
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
