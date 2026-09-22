"""Extract approved raster artwork and export icons. Never redraw the logo."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
APPROVED_SHA = "4ea899554339f84c07366c2aa511b03fc96a077aab199a66c4779f50cd595c7f"
TAGLINE = "Your media. Your way."

def purple_alpha(image: Image.Image) -> Image.Image:
    _, green, blue, _ = image.split()
    return ImageChops.subtract(blue, green).point(
        lambda n: 0 if n <= 7 else 255 if n >= 16 else round((n - 7) * 255 / 9)
    )

def name_alpha(image: Image.Image) -> Image.Image:
    return image.convert("L").point(
        lambda n: 0 if n <= 118 else 255 if n >= 175 else round((n - 118) * 255 / 57)
    )

def export(site: Path | None, font_path: Path) -> dict:
    source = ROOT / "docs/references/approved-vf-matte-logo.png"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == APPROVED_SHA, "Unapproved source artwork"
    brand = ROOT / "assets/brand"
    brand.mkdir(exist_ok=True)
    with Image.open(source) as original:
        image = original.convert("RGB")
    tile = image.crop((100, 176, 688, 764)).convert("RGBA")
    mask = Image.new("L", (2352, 2352))
    ImageDraw.Draw(mask).rounded_rectangle((8, 4, 2336, 2336), radius=472, fill=255)
    tile.putalpha(mask.resize(tile.size, Image.Resampling.LANCZOS))
    tile.save(brand / "approved-app-tile-source.png")
    mark = image.crop((165, 297, 633, 707)).convert("RGBA")
    mark.putalpha(purple_alpha(mark))
    mark.save(brand / "vf-mark.png")
    name = image.crop((987, 415, 1476, 523)).convert("RGBA")
    name.putalpha(name_alpha(name))
    name.save(brand / "vf-name.png")
    wordmark = image.crop((758, 375, 1480, 580)).convert("RGBA")
    alpha = Image.new("L", wordmark.size)
    alpha.paste(purple_alpha(wordmark.crop((0, 0, 232, 205))), (0, 0))
    alpha.paste(name_alpha(wordmark.crop((232, 0, 722, 205))), (232, 0))
    wordmark.putalpha(alpha)
    wordmark.save(brand / "vf-wordmark.png")
    # Platform padding is outside the extracted tile. No geometry/material edit.
    icon = Image.new("RGBA", (1024, 1024))
    icon.alpha_composite(tile.resize((872, 872), Image.Resampling.LANCZOS), (76, 76))
    for filename in ["VODForge.png", "VODForge-macos.png"]:
        icon.save(ROOT / "assets" / filename)
    icon.save(ROOT / "assets/VODForge.ico", sizes=[(n, n) for n in (16,24,32,48,64,128,256)])
    icon.save(ROOT / "assets/VODForge.icns")
    for n in (32,180,192,512):
        icon.resize((n,n), Image.Resampling.LANCZOS).save(brand / f"icon-{n}.png")
    # New statement; exact approved wordmark pixels above it.
    social = Image.new("RGBA", (1200,630), "#090909")
    # Use the larger 468x410 approved mark, never enlarge the 214px lockup mark.
    # Keep the name at source resolution and soften only subpixel alpha edges.
    social_mark = ImageOps.grayscale(mark).convert("RGBA")
    social_mark.putalpha(mark.getchannel("A").filter(ImageFilter.GaussianBlur(.3)))
    social_mark = social_mark.resize((225,197), Image.Resampling.LANCZOS)
    social_name = ImageOps.grayscale(name).convert("RGBA")
    social_name.putalpha(name.getchannel("A").filter(ImageFilter.GaussianBlur(.3)))
    social.alpha_composite(social_mark, (223,146))
    social.alpha_composite(social_name, (488,184))
    font = ImageFont.truetype(str(font_path), 40)
    ImageDraw.Draw(social).text((600,454), TAGLINE, font=font, fill="#c4c4c4", anchor="mm")
    social.convert("RGB").save(brand / "social-preview.png")
    outputs = [ROOT/"assets"/n for n in ["VODForge.png","VODForge-macos.png","VODForge.ico","VODForge.icns"]]
    outputs += sorted(brand.glob("*.png"))
    manifest = {
        "source": str(source.relative_to(ROOT)), "source_sha256": APPROVED_SHA,
        "method": "Original RGB crops; background alpha isolation only; proportional Lanczos resizing",
        "tile_crop": [100,176,688,764], "mark_crop": [165,297,633,707],
        "wordmark_crop": [758,375,1480,580], "tagline": TAGLINE,
        "social_preview": "Grayscale from large mark crop and native-resolution name; 0.3px alpha edge smoothing; no upscaling",
        "source_resolution": list(image.size), "tile_source_resolution": list(tile.size),
        "font_sha256": hashlib.sha256(font_path.read_bytes()).hexdigest(),
        "exports": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in outputs},
    }
    (brand/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    if site:
        dest = site / "public/brand"
        dest.mkdir(exist_ok=True)
        for name in ["vf-mark.png","vf-name.png","vf-wordmark.png","icon-32.png","icon-180.png","icon-192.png","icon-512.png"]:
            shutil.copy2(brand/name, dest/name)
        for src, target in [
            (ROOT/"assets/VODForge.ico",site/"public/favicon.ico"),
            (brand/"vf-mark.png",site/"public/email-vodforge-icon.png"),
            (brand/"social-preview.png",site/"public/social-preview.png"),
            (brand/"icon-180.png",site/"public/apple-touch-icon.png"),
            (ROOT/"assets/VODForge.png",site/"src/assets/product/vodforge-icon.png"),
        ]:
            shutil.copy2(src,target)
        shutil.copy2(brand/"manifest.json",dest/"manifest.json")
    return manifest

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--site",type=Path)
    parser.add_argument("--font",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(export(args.site,args.font),indent=2))
