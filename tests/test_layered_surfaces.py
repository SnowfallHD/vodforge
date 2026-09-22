"""Layered chrome is shared, palette-aware and safe before native mapping."""

from yt_downloader.ui_chrome import (
    action_button_image,
    field_border_image,
    layered_surface_image,
)
from yt_downloader.ui_theme import THEME


def test_surface_has_tonal_depth_and_transparent_corners():
    image = layered_surface_image(
        240, 140, fill=THEME["surface"], edge=THEME["border"], illumination=0.22
    )
    assert image.mode == "RGBA"
    assert image.getpixel((120, 10)) != image.getpixel((120, 130))
    assert image.getpixel((0, 0))[3] < 100
    assert image.getpixel((120, 70))[3] == 255


def test_controls_handle_unmapped_sizes_and_share_the_active_palette(monkeypatch):
    assert field_border_image(1, 1).size == (1, 1)
    assert action_button_image(1, 1, accent=True).size == (1, 1)
    before = action_button_image(80, 32, accent=True).getpixel((40, 16))
    monkeypatch.setitem(THEME, "surface", "#22bb99")
    after = action_button_image(80, 32, accent=True).getpixel((40, 16))
    assert after != before


def test_native_nine_slice_center_and_edges_are_tile_safe():
    from yt_downloader.ui_chrome import ttk_surface_image

    bitmap = ttk_surface_image(28, fill=THEME["surface"], edge=THEME["border"])
    center = {bitmap.getpixel((x, y)) for x in range(9, 19) for y in range(9, 19)}
    assert len(center) == 1
    assert len({bitmap.getpixel((x, 1)) for x in range(9, 19)}) == 1
    assert len({bitmap.getpixel((1, y)) for y in range(9, 19)}) == 1
    assert bitmap.getpixel((14, 1)) != bitmap.getpixel((14, 14))
