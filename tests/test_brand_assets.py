"""Approved artwork must survive export; a polygon substitute must fail."""

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]


def test_brand_exports_match_approved_source_pixels():
    source = ROOT / "docs/references/approved-vf-matte-logo.png"
    assert (
        hashlib.sha256(source.read_bytes()).hexdigest()
        == "4ea899554339f84c07366c2aa511b03fc96a077aab199a66c4779f50cd595c7f"
    )
    with Image.open(source) as raw:
        original = raw.convert("RGB")
    for name, box in [
        ("approved-app-tile-source.png", (100, 176, 688, 764)),
        ("vf-mark.png", (165, 297, 633, 707)),
        ("vf-wordmark.png", (758, 375, 1480, 580)),
    ]:
        with Image.open(ROOT / "assets/brand" / name) as image:
            assert (
                ImageChops.difference(
                    image.convert("RGB"), original.crop(box)
                ).getbbox()
                is None
            )
            assert image.mode == "RGBA"
            assert image.getchannel("A").getextrema() == (0, 255)


def test_platform_icon_sizes_and_export_manifest():
    root = ROOT / "assets"
    with Image.open(root / "VODForge.ico") as ico:
        assert {(16, 16), (32, 32), (48, 48), (128, 128), (256, 256)} <= ico.ico.sizes()
    with Image.open(root / "VODForge.icns") as icns:
        assert (512, 512, 2) in icns.info["sizes"]
        assert icns.convert("RGBA").getpixel((0, 0))[3] == 0
    manifest = json.loads((root / "brand/manifest.json").read_text())
    assert manifest["tagline"] == "Your media. Your way."
    for name, expected in manifest["exports"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name


def test_social_preview_is_monochromatic():
    with Image.open(ROOT / "assets/brand/social-preview.png") as preview:
        assert preview.size == (1200, 630)
        red, green, blue = preview.convert("RGB").split()
        assert ImageChops.difference(red, green).getbbox() is None
        assert ImageChops.difference(green, blue).getbbox() is None


def test_icns_representations_preserve_export_pixels():
    with Image.open(ROOT / "assets/VODForge-macos.png") as raw:
        master = raw.convert("RGBA")
    with Image.open(ROOT / "assets/VODForge.icns") as container:
        representations = list(container.info["sizes"])
    for representation in representations:
        with Image.open(ROOT / "assets/VODForge.icns") as container:
            container.size = representation[:2]
            container.load(scale=representation[2])
            decoded = container.convert("RGBA")
            expected = master.resize(decoded.size, Image.Resampling.BICUBIC)
            difference = ImageChops.difference(decoded, expected)
            assert all(channel.getextrema() == (0, 0) for channel in difference.split())
