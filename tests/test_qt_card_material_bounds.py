"""Artwork-card materials keep the same bounded raster contract as fields."""

import pytest
from PySide6.QtCore import QSize

from tests.test_qt_scene_port import qt_app
from yt_downloader.qt_quick.main import Materials


@pytest.mark.parametrize("height", [535, 2048])
def test_tall_artwork_card_material_is_rendered(height):
    qt_app()
    provider = Materials()
    size = QSize()
    image = provider.requestImage(f"button/742/{height}/normal/0/r0", size, QSize())
    assert not image.isNull()
    assert (image.width(), image.height()) == (742, height)
    assert size == QSize(742, height)


@pytest.mark.parametrize("width,height", [(0, 535), (4097, 535), (742, 0), (742, 2049)])
def test_card_material_remains_bounded(width, height):
    qt_app()
    with pytest.raises(ValueError, match="button image dimensions out of bounds"):
        Materials().requestImage(
            f"button/{width}/{height}/normal/0/r0", QSize(), QSize()
        )
