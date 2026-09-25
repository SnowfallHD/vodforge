"""Rendered artwork fit and channel mask contract shared by Library and Watch."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PIL import Image


def render_probe(source: Path, avatar: Path, component: Path, output: Path) -> None:
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
    view.setWidth(120)
    view.setHeight(120)
    view.show()
    for circular, name, path in (
        (False, "square.png", source),
        (True, "circle.png", avatar),
    ):
        artwork.setProperty("circular", circular)
        artwork.setProperty("source", QUrl.fromLocalFile(str(path)))
        settled = QEventLoop()
        QTimer.singleShot(300 if not circular else 100, settled.quit)
        settled.exec()
        if not view.grabWindow().save(str(output / name)):
            raise RuntimeError("Artwork render capture failed")
    view.close()
    app.quit()


def test_artwork_fits_with_even_margins_and_channel_is_circular(tmp_path):
    from yt_downloader.qt_quick.artwork import circular_avatar_asset

    source = tmp_path / "artwork.png"
    Image.new("RGB", (320, 180), "#4488cc").save(source)
    avatar = circular_avatar_asset(source, tmp_path / "avatars", (120, 120))
    assert avatar is not None
    with Image.open(avatar) as prepared:
        assert prepared.size == (120, 120)
        assert prepared.getpixel((0, 0))[3] == 0
        opaque = prepared.getchannel("A").point(
            lambda alpha: 255 if alpha == 255 else 0
        )
        bounds = opaque.getbbox()
        assert bounds is not None
        assert abs((bounds[2] - bounds[0]) / (bounds[3] - bounds[1]) - 16 / 9) < 0.04
    component = (
        Path(__file__).resolve().parents[1] / "yt_downloader/qt_quick/ArtworkImage.qml"
    )
    result = subprocess.run(
        [
            sys.executable,
            __file__,
            "--probe",
            str(source),
            str(avatar),
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
        # A direct rectangular thumbnail would paint outside the circular
        # avatar. The prepared asset must retain its original aspect ratio.
        assert image.getpixel((5, 30))[:3] == (34, 34, 34)


if __name__ == "__main__":
    render_probe(
        Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5])
    )
