"""Shared static matte artwork sized once for the display, then moved on resize."""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

from .product_theme import THEME


def material_asset(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / "assets" / "materials" / (name + "-v2" + ".png")


@lru_cache(maxsize=8)
def backdrop_pixels(
    motif: str,
    background: str,
    tint: str,
    size: tuple[int, int] = (1200, 800),
) -> Image.Image:
    """Cache one full composition, with readable quiet zones and soft edges."""
    with Image.open(material_asset(motif)) as source:
        mask = ImageOps.fit(source.convert("L"), size, Image.Resampling.LANCZOS)
    # Full-height composition rather than a decorative heading strip. The
    # source's quiet left zone protects content hierarchy; edge fades eliminate
    # hard bitmap boundaries. Raster work occurs on first use, theme changes,
    # or when a window actually outgrows the display-sized shared image.
    fade = Image.new("L", (1, mask.height))
    fade.putdata(
        [
            round(255 * min(1, y / 90, (mask.height - 1 - y) / 90))
            for y in range(mask.height)
        ]
    )
    mask = ImageChops.multiply(mask, fade.resize(mask.size)).point(
        lambda n: round(n * 0.28)
    )
    return Image.composite(
        Image.new("RGB", mask.size, tint), Image.new("RGB", mask.size, background), mask
    )


def tint_brand(source: Image.Image, *, wordmark: bool = False) -> Image.Image:
    """Preserve approved geometry, alpha and luminance texture; tint app UI only."""
    image = source.convert("RGBA")
    tinted = ImageOps.colorize(
        ImageOps.grayscale(image),
        THEME["bg"],
        THEME["text"] if wordmark else THEME["accent"],
    )
    tinted.putalpha(image.getchannel("A"))
    return tinted
