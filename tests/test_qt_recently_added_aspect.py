"""Recently Added scales its complete cards and retains uncropped artwork."""

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject
from PySide6.QtGui import QColor, QImage
from PySide6.QtQml import QQmlExpression

from tests.test_qt_scene_port import qt_app, saved
from yt_downloader.qt_quick import main


@pytest.mark.parametrize("route", ["home", "group"])
@pytest.mark.parametrize("width", [720, 1025, 1500])
@pytest.mark.parametrize("image_size", [(320, 180), (200, 300), (600, 200)])
def test_recent_cards_scale_complete_artwork_and_text(
    tmp_path, monkeypatch, width, image_size, route
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    image = QImage(*image_size, QImage.Format_RGB32)
    image.fill(QColor("orange"))
    image_path = tmp_path / "art.png"
    assert image.save(str(image_path))
    bridge = main.Bridge(None)
    bridge._runtime.history = [saved(tmp_path, f"Card {i}", "MP4") for i in range(8)]
    monkeypatch.setattr(bridge, "mediaArtwork", lambda _owner: image_path.as_uri())
    engine = main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        window.setWidth(width)
        bridge.select("Watch")
        if route == "group":
            group = bridge.watchScene["channels"][0]
            bridge.navigateWatchGroup("channel", group["key"])
        else:
            bridge.navigateWatch("home")
        for _ in range(4):
            app.processEvents()
        flow = window.findChild(QObject, "watchMediaFlow")
        repeater = window.findChild(QObject, "watchMediaRepeater")
        expression = QQmlExpression(engine.rootContext(), repeater, "itemAt(0)")
        card, _undefined = expression.evaluate()
        art = card.findChild(QObject, "watchMediaArtworkImage")
        assert art.property("cover") is False
        assert flow.property("artworkHeight") == pytest.approx(
            min(450, card.width() * 9 / 16)
        )
        assert card.height() == pytest.approx(flow.property("artworkHeight") + 49)
        assert flow.property("rowStride") == pytest.approx(card.height() + 12)
        assert repeater.property("count") <= (
            flow.property("columns") if route == "home" else 8
        )
        texts = [
            child
            for child in card.childItems()
            if child.property("text") in ("Card 0", "Unknown creator")
        ]
        assert texts
        assert all(child.y() >= art.y() + art.height() for child in texts)
        assert all(child.y() + child.height() <= card.height() for child in texts)
        scale = min(art.width() / image_size[0], art.height() / image_size[1])
        assert image_size[0] * scale <= art.width() + 0.01
        assert image_size[1] * scale <= art.height() + 0.01
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
