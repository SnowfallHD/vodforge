"""Fault controls for the class of unwanted surface and decoration artifacts."""

import pytest
from PIL import Image, ImageDraw, ImageFilter
from quality_harness.surface_artifacts import (
    clipped_shadow_edges,
    outside_allowed_surface,
    stale_decoration,
)


def backdrop(kind):
    image = Image.new("RGB", (220, 130), "#343139")
    draw = ImageDraw.Draw(image)
    if kind == "stripes":
        for x in range(0, 220, 17):
            draw.rectangle((x, 0, x + 6, 130), fill="#43404b")
    else:
        for y in range(130):
            value = 40 + y // 7
            draw.line((0, y, 220, y), fill=(value, value - 3, value + 5))
    return image


def geometry():
    # Design-owned 160x64 face and six-pixel soft-shadow support, fixed before
    # evaluating output. Never infer a bound from the faulty screenshot.
    face = Image.new("L", (220, 130))
    ImageDraw.Draw(face).rounded_rectangle((30, 33, 190, 97), radius=12, fill=255)
    allowed = face.filter(ImageFilter.MaxFilter(13)).point(lambda n: 255 if n else 0)
    return face, allowed


@pytest.mark.parametrize("kind", ["stripes", "tonal"])
def test_background_detector_accepts_shaped_depth_rejects_opaque_wrapper(kind):
    background = backdrop(kind)
    face, allowed = geometry()
    shadow = face.filter(ImageFilter.GaussianBlur(2))
    # Finite six-pixel support is part of this fixture's design contract.
    shadow = Image.composite(shadow, Image.new("L", shadow.size), allowed)
    actual = Image.composite(
        Image.new("RGB", background.size, "#232128"), background, shadow
    )
    actual = Image.composite(Image.new("RGB", background.size, "#39363f"), actual, face)
    assert outside_allowed_surface(actual, background, allowed).clean
    faulty = actual.copy()
    ImageDraw.Draw(faulty).rectangle((15, 20, 205, 110), fill="#39363f")
    result = outside_allowed_surface(faulty, background, allowed)
    assert not result.clean and result.unexpected_pixels > 100
    assert result.bounds is not None


def test_clipped_shadow_negative_and_valid_soft_falloff():
    raster = Image.new("RGBA", (100, 60))
    mask = Image.new("L", raster.size)
    ImageDraw.Draw(mask).rounded_rectangle((15, 15, 85, 45), radius=9, fill=150)
    mask = mask.filter(ImageFilter.GaussianBlur(3))
    raster.putalpha(mask)
    assert not clipped_shadow_edges(raster)
    bad = raster.copy()
    ImageDraw.Draw(bad).line((0, 0, 99, 0), fill=(0, 0, 0, 15))
    assert clipped_shadow_edges(bad)


def test_focus_positive_exit_and_stale_ring_negative():
    idle = backdrop("stripes")
    focused = idle.copy()
    ImageDraw.Draw(focused).rounded_rectangle(
        (28, 31, 192, 99), radius=14, outline="#80d5ef", width=2
    )
    focus_allowance = Image.new("L", idle.size)
    ImageDraw.Draw(focus_allowance).rounded_rectangle(
        (28, 31, 192, 99), radius=14, outline=255, width=2
    )
    assert outside_allowed_surface(focused, idle, focus_allowance).clean
    region = Image.new("L", idle.size, 255)
    assert not stale_decoration(focused, idle, region).clean
    assert stale_decoration(idle.copy(), idle, region).clean
    # A ring left after focus exits is the same visible fault.
    assert stale_decoration(focused, idle, region).unexpected_pixels > 100


def test_detector_rejects_unbound_dimensions():
    with pytest.raises(ValueError):
        outside_allowed_surface(
            Image.new("RGB", (2, 2)), Image.new("RGB", (3, 3)), Image.new("L", (2, 2))
        )
