"""One conversion boundary for fixed-DPI prototype geometry, fonts and raster."""

import pytest
from PIL import ImageChops

from yt_downloader.visual_chrome import field_border_image


@pytest.mark.parametrize("focused", [False, True])
def test_physical_chrome_matches_native_density_rendering_and_detects_unscaled_edges(
    focused,
):
    expected = field_border_image(240, 34, density=2, focused=focused)
    actual = field_border_image(480, 68, unit_scale=2, focused=focused)
    assert actual.size == (480, 68)
    assert (
        ImageChops.difference(actual.convert("RGB"), expected.convert("RGB")).getbbox()
        is None
    )
    assert (
        ImageChops.difference(
            actual.getchannel("A"), expected.getchannel("A")
        ).getbbox()
        is None
    )
    color_only = actual.copy()
    x, y = actual.width // 2, actual.height // 2
    red, green, blue, alpha = color_only.getpixel((x, y))
    color_only.putpixel((x, y), ((red + 1) % 256, green, blue, alpha))
    assert (
        ImageChops.difference(
            actual.getchannel("A"), color_only.getchannel("A")
        ).getbbox()
        is None
    )
    assert (
        ImageChops.difference(
            actual.convert("RGB"), color_only.convert("RGB")
        ).getbbox()
        is not None
    )
    wrong = field_border_image(480, 68, focused=focused)
    assert ImageChops.difference(actual, wrong).convert("RGB").getbbox() is not None
