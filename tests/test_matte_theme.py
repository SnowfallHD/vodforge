"""Independent contrast, palette hue, asset identity and bounded-cache checks."""

import colorsys
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from yt_downloader.ui_materials import backdrop_pixels, tint_brand
from yt_downloader.ui_theme import (
    FOREGROUND_ROLES,
    MATERIAL_ROLES,
    THEME,
    THEME_NAMES,
    apply_theme_selection,
    theme_motif,
)


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


def test_brand_tint_preserves_geometry_and_source_alpha():
    with Image.open(
        Path(__file__).resolve().parents[1] / "assets/brand/vf-mark.png"
    ) as source:
        original = source.convert("RGBA")
    for name in THEME_NAMES:
        apply_theme_selection(name)
        tinted = tint_brand(original)
        assert tinted.size == original.size
        assert (
            ImageChops.difference(
                tinted.getchannel("A"), original.getchannel("A")
            ).getbbox()
            is None
        )
    apply_theme_selection("Violet")


def test_raised_material_falls_to_transparent_before_bitmap_boundary():
    from yt_downloader.ui_chrome import action_button_image

    for width, height in ((28, 28), (140, 44), (220, 40)):
        image = action_button_image(width, height, accent=True)
        alpha = image.getchannel("A")
        assert alpha.crop((0, 0, width, 1)).getextrema() == (0, 0)
        assert alpha.crop((0, height - 1, width, height)).getextrema() == (0, 0)
        assert alpha.crop((0, 0, 1, height)).getextrema() == (0, 0)
        assert alpha.crop((width - 1, 0, width, height)).getextrema() == (0, 0)
        assert alpha.getpixel((width // 2, height // 2)) == 255


@pytest.mark.parametrize("accent", [False, True])
def test_shared_hover_is_an_inset_without_a_new_face_or_border(accent):
    """The pre-change bright-hover renderer fails this center/contour oracle."""
    from yt_downloader.ui_chrome import (
        _blend_color,
        action_button_image,
        control_material_roles,
        primary_action_color,
        ttk_surface_image,
    )

    idle = action_button_image(140, 44, accent=accent)
    hover = action_button_image(140, 44, accent=accent, state="hover")
    legacy_fill = _blend_color(
        primary_action_color() if accent else THEME["surface"], THEME["accent"], 0.10
    )
    legacy_hover = ttk_surface_image(
        140,
        height=44,
        fill=legacy_fill,
        edge=_blend_color(legacy_fill, THEME["accent"], 0.28 if accent else 0.14),
        stretch=False,
        inset_face=True,
    )
    # The old brighter fill visibly changes the usable center, while the new
    # hover leaves it untouched and moves only the tactile material contour.
    assert legacy_hover.getpixel((70, 22)) != idle.getpixel((70, 22))
    assert idle.getpixel((70, 22)) == hover.getpixel((70, 22))
    assert (
        ImageChops.difference(idle.convert("RGB"), hover.convert("RGB")).getbbox()
        is not None
    )
    assert (
        ImageChops.difference(idle.getchannel("A"), hover.getchannel("A")).getbbox()
        is not None
    )

    roles = control_material_roles()
    assert roles["hover"] == roles["button"]
    assert roles["accent_hover"] == roles["accent"]
    assert roles["nav_hover"] == roles["nav_idle"]
    assert roles["nav_selected"] == roles["nav_idle"]
    assert roles["transport_hover"] == roles["transport"]
    assert roles["focus"] != roles["button"]


def test_shared_field_hover_replaces_the_prior_bright_face_with_an_inset_contour():
    from yt_downloader.ui_chrome import (
        _blend_color,
        field_border_image,
        ttk_surface_image,
    )

    idle = field_border_image(140, 44)
    hover = field_border_image(140, 44, hovered=True)
    legacy_hover = ttk_surface_image(
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


def test_navigation_uses_shared_inset_hover_and_selection_without_accent_edge():
    from yt_downloader.ui_chrome import navigation_button_image

    idle = navigation_button_image(140, 44, background=THEME["panel"])
    hover = navigation_button_image(140, 44, background=THEME["panel"], state="hover")
    focus = navigation_button_image(140, 44, background=THEME["panel"], state="focus")
    selected = navigation_button_image(
        140, 44, background=THEME["panel"], selected=True
    )
    selected_hover = navigation_button_image(
        140, 44, background=THEME["panel"], selected=True, state="hover"
    )
    # Idle remains raised per the explicit resting-control contract. A fully
    # transparent idle face would remove its material depth.
    assert idle.getchannel("A").getpixel((70, 22)) == 255
    assert idle.getchannel("A").getpixel((0, 0)) == 0
    assert (
        ImageChops.difference(idle.convert("RGB"), hover.convert("RGB")).getbbox()
        is not None
    )
    assert (
        ImageChops.difference(idle.getchannel("A"), hover.getchannel("A")).getbbox()
        is not None
    )
    assert ImageChops.difference(idle, focus).getbbox() is not None
    assert selected.getpixel((70, 41))[:3] != tuple(
        int(THEME["selection"][i : i + 2], 16) for i in (1, 3, 5)
    )
    # An opaque same-hue face is not a color highlight: composited center
    # remains the page material while diffuse inner shading establishes depth.
    assert selected.getpixel((70, 22))[:3] == tuple(
        int(THEME["panel"][i : i + 2], 16) for i in (1, 3, 5)
    )
    assert ImageChops.difference(selected, selected_hover).getbbox() is None


@pytest.mark.parametrize("density", [1, 2])
def test_full_action_keeps_rounded_corner_outside_ttk_stretch_zone(density):
    from yt_downloader.ui_chrome import action_button_image

    image = action_button_image(140, 44, accent=True, density=density)
    assert image.size == (140 * density, 44 * density)
    alpha = image.getchannel("A")
    # The face starts five logical pixels in, with a seven-pixel radius.
    # The old nine-slice normalization flattened this curve at x/y=9.
    assert alpha.getpixel((9 * density, 5 * density)) < 200
    assert alpha.getpixel((5 * density, 9 * density)) < 200
    assert alpha.getpixel((12 * density, 5 * density)) == 255
    assert alpha.getpixel((5 * density, 12 * density)) == 255


@pytest.mark.parametrize(
    "idle,hover", [("button", "hover"), ("accent", "accent_hover")]
)
def test_ttk_owner_renders_raised_to_recessed_hover(monkeypatch, idle, hover):
    """Exercise the actual default ttk owner, not only the scene renderer."""
    from types import SimpleNamespace

    from yt_downloader import ui_chrome

    class Bitmap:
        def __init__(self, image, **_kwargs):
            self.image = image.copy()

    root = SimpleNamespace(bind=lambda *_args, **_kwargs: "binding")
    owner = ui_chrome.ProductChromeOwner(root)
    monkeypatch.setattr(ui_chrome, "surface_backing_scale", lambda _root: 1)
    monkeypatch.setattr(ui_chrome.ImageTk, "PhotoImage", Bitmap)
    monkeypatch.setattr(
        ui_chrome,
        "create_surface_image",
        lambda _root, image, *_args, **_kwargs: (Bitmap(image), None),
    )
    monkeypatch.setattr(owner, "_install", lambda _style: None)
    owner.request(None)
    resting, hovered = owner.images[idle].image, owner.images[hover].image
    assert ImageChops.difference(
        resting.convert("RGB"), hovered.convert("RGB")
    ).getbbox()
    # Equal role colors require the material direction to provide the response.
    # The top/bottom contour illumination reverses, with the face preserved.
    assert resting.getpixel((14, 14)) == hovered.getpixel((14, 14))
    assert resting.getpixel((14, 2)) != hovered.getpixel((14, 2))
