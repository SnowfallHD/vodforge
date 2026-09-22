"""State material excludes legacy perimeter highlights across shipped palettes."""

import pytest
from PIL import ImageChops, ImageColor

from yt_downloader.ui_chrome import (
    action_button_image,
    field_border_image,
    navigation_button_image,
)
from yt_downloader.ui_theme import THEME, THEME_PRESETS


@pytest.mark.parametrize("theme", list(THEME_PRESETS))
@pytest.mark.parametrize(
    "family", ["field", "navigation", "selected-navigation", "action"]
)
def test_focus_uses_distinct_material_without_accent_perimeter(
    theme, family, monkeypatch
):
    for key, value in THEME_PRESETS[theme].items():
        monkeypatch.setitem(THEME, key, value)

    def render(focused):
        if family == "field":
            return field_border_image(140, 38, focused=focused, stretch=False)
        if family == "action":
            return action_button_image(140, 38, accent=False, focused=focused)
        return navigation_button_image(
            140,
            38,
            background=THEME["bg"],
            selected=family == "selected-navigation",
            state="focus" if focused else "normal",
        )

    idle, focused = render(False), render(True)
    assert ImageChops.difference(idle.convert("RGB"), focused.convert("RGB")).getbbox()
    bright = ImageColor.getrgb(THEME["focus"])
    assert not any(
        tuple(pixel[:3]) == bright and pixel[3]
        for pixel in (
            focused.getpixel((x, y))
            for y in range(focused.height)
            for x in range(focused.width)
        )
    ), "Legacy focus perimeter returned"
    assert focused.getpixel((70, 19))[:3] == ImageColor.getrgb(THEME["focus_surface"])
    assert render(False).tobytes() == idle.tobytes()


def test_resting_interactive_navigation_has_raised_material():
    image = navigation_button_image(160, 44, background=THEME["bg"])
    assert image.getchannel("A").getbbox(), (
        "Interactive idle navigation disappeared into flat background"
    )
    background = ImageColor.getrgb(THEME["bg"])
    # Raised material needs light and shadow around a stable, semantic face.
    pixels = [
        pixel
        for pixel in (
            image.getpixel((x, y))
            for y in range(image.height)
            for x in range(image.width)
        )
        if pixel[3] > 200
    ]
    assert any(sum(pixel[:3]) > sum(background) for pixel in pixels)
    assert any(sum(pixel[:3]) < sum(background) for pixel in pixels)


def test_navigation_hover_keeps_semantic_face_while_reversing_depth():
    idle = navigation_button_image(160, 44, background=THEME["bg"])
    hover = navigation_button_image(160, 44, background=THEME["bg"], state="hover")
    assert idle.getpixel((80, 22)) == hover.getpixel((80, 22))
    assert ImageChops.difference(idle.convert("RGB"), hover.convert("RGB")).getbbox()
