"""Independent contrast, palette hue, asset identity and bounded-cache checks."""

import colorsys

import pytest
from PIL import ImageChops

from yt_downloader.product_theme import (
    FOREGROUND_ROLES,
    MATERIAL_ROLES,
    THEME,
    THEME_NAMES,
    apply_theme_selection,
    theme_motif,
)
from yt_downloader.visual_materials import backdrop_pixels


def luminance(color):
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return sum(c * w for c, w in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))


def contrast(a, b):
    a, b = sorted((luminance(a), luminance(b)))
    return (b + 0.05) / (a + 0.05)


@pytest.mark.parametrize("name", THEME_NAMES)
def test_matte_materials_single_hue_and_foreground_contrast(name):
    try:
        apply_theme_selection(name, "#ff4400")
        for text in ("text", "muted"):
            for surface in ("bg", "panel", "surface", "surface_2"):
                assert contrast(THEME[text], THEME[surface]) >= 4.5, (
                    name,
                    text,
                    surface,
                )
        assert contrast(THEME["on_accent"], THEME["accent_dark"]) >= 4.5
        assert contrast(THEME["focus"], THEME["surface"]) >= 3
        hues = []
        for role in MATERIAL_ROLES:
            color = THEME[role]
            rgb = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
            hue, _light, _sat = colorsys.rgb_to_hls(*rgb)
            if max(rgb) - min(rgb) > 0.025:
                hues.append(hue)
        assert max(hues) - min(hues) < 0.06
        for role in FOREGROUND_ROLES:
            for surface in ("bg", "surface", "surface_2"):
                assert contrast(THEME[role], THEME[surface]) >= 4.5, (
                    name,
                    role,
                    surface,
                )
        assert THEME["icon"] == THEME["action"]
        assert THEME["icon"] == THEME["accent"]
        assert THEME["selection"] == THEME["progress"]
        assert (
            len(
                {
                    THEME[role]
                    for role in ("action", "selection", "success", "warning", "danger")
                }
            )
            == 5
        )
        backdrop = backdrop_pixels(theme_motif(), THEME["bg"], THEME["accent"])
        assert backdrop.size == (1200, 800)
        brightest = "#" + "".join(f"{high:02x}" for _low, high in backdrop.getextrema())
        assert contrast(THEME["muted"], brightest) >= 4.5, (name, brightest)

        assert backdrop_pixels(theme_motif(), THEME["bg"], THEME["accent"]) is backdrop
        assert backdrop_pixels.cache_info().currsize <= 8
    finally:
        apply_theme_selection("Violet")


def test_raised_material_falls_to_transparent_before_bitmap_boundary():
    from yt_downloader.visual_chrome import action_button_image

    for width, height in ((28, 28), (140, 44), (220, 40)):
        image = action_button_image(width, height, accent=True)
        alpha = image.getchannel("A")
        assert alpha.crop((0, 0, width, 1)).getextrema() == (0, 0)
        assert alpha.crop((0, height - 1, width, height)).getextrema() == (0, 0)
        assert alpha.crop((0, 0, 1, height)).getextrema() == (0, 0)
        assert alpha.crop((width - 1, 0, width, height)).getextrema() == (0, 0)
        assert alpha.getpixel((width // 2, height // 2)) == 255


def test_shared_field_hover_replaces_the_prior_bright_face_with_an_inset_contour():
    from yt_downloader.visual_chrome import (
        _blend_color,
        control_surface_image,
        field_border_image,
    )

    idle = field_border_image(140, 44)
    hover = field_border_image(140, 44, hovered=True)
    legacy_hover = control_surface_image(
        140,
        height=44,
        fill=THEME["surface_2"],
        edge=_blend_color(THEME["surface"], THEME["border"], 0.65),
        recessed=True,
        depth=0.5,
    )
    assert legacy_hover.getpixel((70, 22)) != idle.getpixel((70, 22))
    assert hover.getpixel((70, 22)) == idle.getpixel((70, 22))
    assert (
        ImageChops.difference(idle.convert("RGB"), hover.convert("RGB")).getbbox()
        is not None
    )
    # The field hover does not alter hit geometry or alpha support.
    assert (
        ImageChops.difference(idle.getchannel("A"), hover.getchannel("A")).getbbox()
        is None
    )


@pytest.mark.parametrize("density", [1, 2])
def test_full_action_keeps_rounded_corner_outside_ttk_stretch_zone(density):
    from yt_downloader.visual_chrome import action_button_image

    image = action_button_image(140, 44, accent=True, density=density)
    assert image.size == (140 * density, 44 * density)
    alpha = image.getchannel("A")
    # The face starts five logical pixels in, with a seven-pixel radius.
    # The old nine-slice normalization flattened this curve at x/y=9.
    assert alpha.getpixel((9 * density, 5 * density)) < 200
    assert alpha.getpixel((5 * density, 9 * density)) < 200
    assert alpha.getpixel((12 * density, 5 * density)) == 255
    assert alpha.getpixel((5 * density, 12 * density)) == 255
