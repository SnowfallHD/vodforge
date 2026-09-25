"""Rendered artwork fit and channel mask contract shared by Library and Watch."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PIL import Image


def render_probe(source: Path, component: Path, output: Path) -> None:
    """Keep QQuickView teardown outside the repository's long pytest process."""
    from PySide6.QtCore import QEventLoop, QTimer, QUrl
    from PySide6.QtGui import QColor, QGuiApplication
    from PySide6.QtQuick import QQuickView

    app = QGuiApplication([])
    view = QQuickView()
    view.setColor(QColor("#222222"))
    view.setSource(QUrl.fromLocalFile(str(component)))
    if view.errors():
        raise RuntimeError("Artwork component failed to load")
    artwork = view.rootObject()
    artwork.setWidth(120)
    artwork.setHeight(120)
    artwork.setProperty("source", QUrl.fromLocalFile(str(source)))
    view.setWidth(120)
    view.setHeight(120)
    view.show()
    for circular, name in ((False, "square.png"), (True, "circle.png")):
        artwork.setProperty("circular", circular)
        settled = QEventLoop()
        QTimer.singleShot(300 if not circular else 100, settled.quit)
        settled.exec()
        if not view.grabWindow().save(str(output / name)):
            raise RuntimeError("Artwork render capture failed")
    view.close()
    app.quit()


def test_artwork_fits_with_even_margins_and_channel_is_circular(tmp_path):
    source = tmp_path / "artwork.png"
    Image.new("RGB", (320, 180), "#4488cc").save(source)
    component = (
        Path(__file__).resolve().parents[1] / "yt_downloader/qt_quick/ArtworkImage.qml"
    )
    result = subprocess.run(
        [
            sys.executable,
            __file__,
            "--probe",
            str(source),
            str(component),
            str(tmp_path),
        ],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    with Image.open(tmp_path / "square.png") as image:
        assert image.getpixel((60, 60))[:3] == (68, 136, 204)
        assert image.getpixel((60, 4))[:3] == (34, 34, 34)
        assert image.getpixel((60, 115))[:3] == (34, 34, 34)
    with Image.open(tmp_path / "circle.png") as image:
        assert image.getpixel((60, 60))[:3] == (68, 136, 204)
        assert image.getpixel((10, 10))[:3] == (34, 34, 34)
        assert image.getpixel((4, 60))[:3] == (68, 136, 204)


if __name__ == "__main__":
    render_probe(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
