"""Local player fallback states and responsive video/side geometry."""

from dataclasses import replace

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject

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
