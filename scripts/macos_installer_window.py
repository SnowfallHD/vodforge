"""Single-entry Finder window assets; never installs, launches, or signs an app.

The native installer is a separate prerequisite. A background preview is not a
Finder screenshot or evidence that a double-click installation succeeded.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import json
import shutil
import subprocess
from pathlib import Path

WIDTH, HEIGHT = 640, 440
ENTRY = "Install VODForge.app"
ICON_POSITION = (320, 252)
BACKGROUND = ".background.tiff"


def _set_custom_icon_flag(volume: Path):
    # CPython's macOS os module does not expose getxattr/setxattr. Use Darwin's
    # public filesystem calls on this already-validated, owned volume root only.
    system = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    system.getxattr.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_uint32,
        ctypes.c_int,
    ]
    system.getxattr.restype = ctypes.c_ssize_t
    system.setxattr.argtypes = system.getxattr.argtypes
    system.setxattr.restype = ctypes.c_int
    data = ctypes.create_string_buffer(32)
    path = bytes(volume)
    length = system.getxattr(path, b"com.apple.FinderInfo", data, 32, 0, 0)
    if length < 0:
        number = ctypes.get_errno()
        if number != errno.ENOATTR:
            raise OSError(number, "Cannot read owned volume FinderInfo")
        info = bytearray(32)
    elif length == 32:
        info = bytearray(data.raw)
    else:
        raise ValueError("Unexpected FinderInfo length")
    info[8:10] = (int.from_bytes(info[8:10], "big") | 0x0400).to_bytes(2, "big")
    data = ctypes.create_string_buffer(bytes(info), 32)
    if system.setxattr(path, b"com.apple.FinderInfo", data, 32, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "Cannot set owned volume custom icon")


def background_image(logo: Path, scale: int = 2):
    from PIL import Image, ImageDraw, ImageFont

    from yt_downloader.product_theme import THEME
    from yt_downloader.visual_chrome import control_surface_image, layered_surface_image

    if scale not in (1, 2):
        raise ValueError("Only 1x and 2x Finder artwork is supported")
    image = layered_surface_image(
        WIDTH * scale, HEIGHT * scale, fill=THEME["bg"], radius=0
    )
    # Reuse the app's actual recessed matte renderer, rather than a new style.
    well = control_surface_image(
        216,
        height=196,
        fill=THEME["bg"],
        edge=THEME["border"],
        recessed=True,
        depth=1.25,
        radius=30,
        density=scale,
        stretch=False,
    )
    image.alpha_composite(well, (212 * scale, 166 * scale))
    mark = Image.open(logo).convert("RGBA")
    mark.thumbnail((30 * scale, 30 * scale), Image.Resampling.LANCZOS)
    image.alpha_composite(mark, (30 * scale, 26 * scale))
    draw = ImageDraw.Draw(image)
    font = "/System/Library/Fonts/Supplemental/Arial.ttf"

    def text(x, y, value, size, color, anchor="mm"):
        draw.text(
            (x * scale, y * scale),
            value,
            font=ImageFont.truetype(font, size * scale),
            fill=color,
            anchor=anchor,
        )

    text(70, 41, "VODForge", 16, THEME["text"], "lm")
    text(320, 103, "Install VODForge", 32, THEME["text"])
    text(320, 140, "Double-click the icon below", 16, THEME["muted"])
    text(320, 394, "Apple Silicon: macOS 26+  ·  Intel: macOS 15+", 12, THEME["muted"])
    text(
        320, 416, "You’ll choose where to install in the next step.", 12, THEME["muted"]
    )
    return image.convert("RGB")


def write_assets(output: Path, logo: Path):
    """Write fresh retina TIFF plus an explicitly labelled composition preview."""
    if output.exists():
        raise ValueError("Require a fresh artwork directory; refusing overwrite")
    output.mkdir(parents=True)
    for scale in (1, 2):
        background_image(logo, scale).save(
            output / f"background-{scale}x.tiff", dpi=(72 * scale, 72 * scale)
        )
    subprocess.run(
        [
            "/usr/bin/tiffutil",
            "-cat",
            str(output / "background-1x.tiff"),
            str(output / "background-2x.tiff"),
            "-out",
            str(output / BACKGROUND),
        ],
        check=True,
        capture_output=True,
    )
    # Preview contains the icon/label that Finder will add, not a baked-in button.
    from PIL import Image, ImageDraw, ImageFont

    preview = background_image(logo).convert("RGBA")
    icon = Image.open("assets/brand/icon-512.png").convert("RGBA")
    icon.thumbnail((240, 240), Image.Resampling.LANCZOS)
    preview.alpha_composite(icon, (640 - icon.width // 2, 504 - icon.height // 2))
    draw = ImageDraw.Draw(preview)
    draw.text(
        (640, 654),
        "Install VODForge",
        font=ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 26),
        fill="#f4f3f5",
        anchor="mm",
    )
    preview.convert("RGB").save(output / "composition-preview.png")
    (output / "receipt.json").write_text(
        json.dumps(
            {
                "window_points": [WIDTH, HEIGHT],
                "entry": ENTRY,
                "icon_position_points": ICON_POSITION,
                "background": BACKGROUND,
                "preview": "composition-preview.png",
                "limits": "Rendered artwork only; not actual Finder pixels, installer transaction, signed app or revised DMG",
            },
            indent=2,
        )
        + "\n"
    )


def decorate_volume(volume: Path, icon: Path = Path("assets/VODForge.icns")):
    """Configure only an already staged, owned single-entry installer volume."""
    visible = sorted(
        path.name for path in volume.iterdir() if not path.name.startswith(".")
    )
    if visible != [ENTRY] or (volume / ENTRY).is_symlink():
        raise ValueError("Require exactly the real Install VODForge.app entry")
    if not (volume / ENTRY).is_dir() or not (volume / BACKGROUND).is_file():
        raise ValueError("Missing installer app or retina background")
    for name in (BACKGROUND, ".DS_Store", ".VolumeIcon.icns"):
        if (volume / name).is_symlink():
            raise ValueError("Refusing linked installer metadata")
    if icon.is_symlink() or not icon.is_file():
        raise ValueError("Missing real VODForge volume icon")
    from ds_store import DSStore
    from mac_alias import Alias

    with DSStore.open(str(volume / ".DS_Store"), "w+") as store:
        store["."]["bwsp"] = {
            "WindowBounds": f"{{{{120, 120}}, {{{WIDTH}, {HEIGHT}}}}}",
            "ContainerShowSidebar": False,
            "PreviewPaneVisibility": False,
            "ShowToolbar": False,
            "ShowSidebar": False,
            "ShowStatusBar": False,
            "ShowPathbar": False,
            "ShowTabView": False,
            "SidebarWidth": 180,
        }
        store["."]["icvl"] = ("type", b"icnv")
        store["."]["icvp"] = {
            "viewOptionsVersion": 1,
            "backgroundType": 2,
            "backgroundColorRed": 1.0,
            "backgroundColorGreen": 1.0,
            "backgroundColorBlue": 1.0,
            "backgroundImageAlias": Alias.for_file(str(volume / BACKGROUND)).to_bytes(),
            "iconSize": 120.0,
            "textSize": 13.0,
            "labelOnBottom": True,
            "arrangeBy": "none",
            "gridOffsetX": 0.0,
            "gridOffsetY": 0.0,
            "gridSpacing": 100.0,
            "scrollPositionX": 0.0,
            "scrollPositionY": 0.0,
            "showIconPreview": False,
            "showItemInfo": False,
        }
        store["."]["vSrn"] = ("long", 1)
        store[ENTRY]["Iloc"] = ICON_POSITION
    shutil.copyfile(icon, volume / ".VolumeIcon.icns")
    _set_custom_icon_flag(volume)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artwork-output", type=Path, required=True)
    parser.add_argument("--logo", type=Path, default=Path("assets/brand/vf-mark.png"))
    args = parser.parse_args()
    write_assets(args.artwork_output, args.logo)
