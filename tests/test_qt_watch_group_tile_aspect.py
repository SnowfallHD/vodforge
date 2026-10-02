"""Shared playlist tiles keep full artwork and proportional grid geometry."""

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject
from PySide6.QtQml import QQmlExpression

from tests.test_qt_library_window_model import visual_descendants
from tests.test_qt_scene_port import qt_app, saved
from yt_downloader.qt_quick import main


@pytest.mark.parametrize("width", [720, 1025, 1500])
@pytest.mark.parametrize("route", ["home", "playlists", "channels"])
def test_group_tile_geometry_matches_viewport_stride(
    tmp_path, monkeypatch, width, route
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = main.Bridge(None)
    bridge._runtime.history = [
        dict(
            saved(tmp_path, f"Media {i}", "MP4"),
            channel=f"Channel {i}",
            playlist_id=f"List {i}",
        )
        for i in range(12)
    ]
    engine = main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        window.setWidth(width)
        bridge.select("Watch")
        bridge.navigateWatch(route)
        for _ in range(4):
            app.processEvents()
        if route == "home":
            rail = next(
                item
                for item in visual_descendants(window.contentItem())
                if item.objectName() == "watchHomeRail_playlists"
            )
            repeater = next(
                item
                for item in visual_descendants(rail)
                if item.objectName() == "watchHomeGroupRepeater"
            )
            flow = None
        else:
            flow = next(
                item
                for item in visual_descendants(window.contentItem())
                if item.objectName() == "watchGroupFlow"
                and item.property("totalRows") > 0
            )
            repeater = next(
                item
                for item in flow.childItems()
                if item.objectName() == "watchGroupRepeater"
            )
        card, _ = QQmlExpression(engine.rootContext(), repeater, "itemAt(0)").evaluate()
        art = card.findChild(QObject, "watchGroupArtworkImage")
        assert art.property("cover") is False
        assert art.property("circular") is (route == "channels")
        if route == "channels":
            assert art.width() == art.height()
            scale = max(1, min(2, card.width() / 260))
            assert card.height() == pytest.approx(82 * scale)
            assert art.width() == pytest.approx(
                (64 - (card.property("artworkFaceInset") - 7) * 2) * scale
            )
            texts = [
                item for item in card.childItems() if item.property("text") is not None
            ]
            assert all(item.y() + item.height() <= card.height() for item in texts)
            assert all(item.x() + item.width() <= card.width() for item in texts)
        else:
            assert card.height() == pytest.approx(min(450, card.width() * 9 / 16) + 53)
            assert art.height() == pytest.approx(
                card.property("artworkHeight") - card.property("artworkFaceInset")
            )
        if flow:
            assert flow.property("rowStride") == pytest.approx(card.height() + 12)
        else:
            assert rail.height() >= card.height() + 12
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
