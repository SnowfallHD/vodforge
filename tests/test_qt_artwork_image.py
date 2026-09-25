"""Rendered artwork fit and channel mask contract shared by Library and Watch."""

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtQuick import QQuickView


def test_artwork_fits_with_even_margins_and_channel_is_circular(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    QGuiApplication.instance() or QGuiApplication([])
    source = tmp_path / "artwork.png"
    Image.new("RGB", (320, 180), "#4488cc").save(source)
    component = (
        Path(__file__).resolve().parents[1] / "yt_downloader/qt_quick/ArtworkImage.qml"
    )
    view = QQuickView()
    view.setColor(QColor("#222222"))
    view.setSource(QUrl.fromLocalFile(str(component)))
    assert not view.errors()
    artwork = view.rootObject()
    artwork.setWidth(120)
    artwork.setHeight(120)
    artwork.setProperty("source", QUrl.fromLocalFile(str(source)))
    view.setWidth(120)
    view.setHeight(120)
    view.show()
    try:
        settled = QEventLoop()
        QTimer.singleShot(300, settled.quit)
        settled.exec()
        image = view.grabWindow()
        assert image.pixelColor(60, 60) == QColor("#4488cc")
        assert image.pixelColor(60, 4) == QColor("#222222")
        assert image.pixelColor(60, 115) == QColor("#222222")

        artwork.setProperty("circular", True)
        settled = QEventLoop()
        QTimer.singleShot(100, settled.quit)
        settled.exec()
        image = view.grabWindow()
        assert image.pixelColor(60, 60) == QColor("#4488cc")
        assert image.pixelColor(10, 10) == QColor("#222222")
        assert image.pixelColor(4, 60) == QColor("#4488cc")
    finally:
        view.close()
