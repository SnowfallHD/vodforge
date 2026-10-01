"""Playlist artwork retains its full frame as responsive cards resize."""

from pathlib import Path

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtTest import QTest

from tests.test_qt_scene_port import qt_app, saved, visual_item
from yt_downloader.qt_quick import main as qt_main


@pytest.mark.parametrize("width", [820, 1100, 2400])
@pytest.mark.parametrize("real_art", [False, True])
def test_playlist_art_frame(tmp_path, monkeypatch, width, real_art):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [saved(tmp_path, "Fictional media", "MP4")]
    if real_art:
        image = QImage(640, 360, QImage.Format_RGB32)
        image.fill(QColor("#276080"))
        painter = QPainter(image)
        painter.fillRect(0, 0, 640, 24, QColor("#ffb000"))
        painter.fillRect(0, 336, 640, 24, QColor("#ef5060"))
        painter.fillRect(0, 24, 24, 312, QColor("#44dd99"))
        painter.fillRect(616, 24, 24, 312, QColor("#aa88ff"))
        painter.end()
        filename = tmp_path / "full-frame.png"
        image.save(str(filename))
        bridge._group_artwork = lambda *_: QUrl.fromLocalFile(str(filename)).toString()
    else:
        bridge._group_artwork = lambda *_: ""
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        window.resize(width, 900)
        bridge.select("Library")
        bridge.navigateLibrary("playlists")
        for _ in range(3):
            app.processEvents()
        art = visual_item(window.contentItem(), "libraryGroupArtworkImage")
        assert art is not None
        window.grabWindow()
        QTest.qWait(250)
        app.processEvents()
        assert abs(art.width() / art.height() - 16 / 9) < 0.01
        assert art.property("cover") is False
        card = art.parentItem()
        assert card.height() >= art.y() + art.height() + 40
        capture = window.grabWindow()
        assert not capture.isNull()
        if real_art:
            assert art.property("hasArtwork") is True
            assert not art.property("waitingForPaint")
        output = (
            Path(__file__).parents[2]
            / "integration-evidence"
            / "playlist-art-intake"
            / "renders"
        )
        output.mkdir(parents=True, exist_ok=True)
        assert capture.save(
            str(output / f"playlist-{width}-{'art' if real_art else 'placeholder'}.png")
        )
    finally:
        bridge.close()
        engine.deleteLater()
        app.processEvents()
