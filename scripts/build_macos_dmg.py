"""Create a private universal2 drag-to-Applications DMG without Finder automation."""

from __future__ import annotations

import argparse
import json
import plistlib
import subprocess
import tempfile
from pathlib import Path

MACHO = {
    bytes.fromhex(x)
    for x in (
        "feedface",
        "cefaedfe",
        "feedfacf",
        "cffaedfe",
        "cafebabe",
        "bebafeca",
        "cafebabf",
        "bfbafeca",
    )
}
ARCHES = {"arm64", "x86_64"}


def command(args):
    return subprocess.check_output(args, text=True)


def require_universal_app(app: Path, run=command):
    """Fail before staging/mounting on any missing native slice or wrong owner."""
    if app.is_symlink() or app.name != "VODForge.app" or not app.is_dir():
        raise ValueError("Expected a real VODForge.app")
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    if info.get("CFBundleIdentifier") != "com.snowfallhd.vodforge":
        raise ValueError("Unexpected bundle identity")
    main = app / "Contents/MacOS/VODForge"
    if main.is_symlink() or not main.is_file():
        raise ValueError("Missing app executable")
    rows, errors = [], []
    for path in sorted(app.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        with path.open("rb") as stream:
            if stream.read(4) not in MACHO:
                continue
        slices = set(run(["/usr/bin/lipo", "-archs", str(path)]).split())
        rows.append({"path": str(path.relative_to(app)), "slices": sorted(slices)})
        if not ARCHES <= slices:
            errors.append(str(path.relative_to(app)))
    if not rows or errors:
        raise ValueError(
            "Universal2 slices missing: " + ", ".join(errors or ["no Mach-O files"])
        )
    run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)])
    run(["/usr/bin/xcrun", "stapler", "validate", str(app)])
    return {
        "bundle_version": info.get("CFBundleShortVersionString"),
        "native_files": rows,
    }


def write_background(path: Path, logo: Path):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1280, 840), "#101923")
    draw = ImageDraw.Draw(image)
    font = "/System/Library/Fonts/Supplemental/Arial.ttf"
    title = ImageFont.truetype(font, 54)
    body = ImageFont.truetype(font, 25)
    mark = Image.open(logo).convert("RGBA")
    mark.thumbnail((110, 110))
    image.paste(mark, ((1280 - mark.width) // 2, 48), mark)
    draw.text((640, 178), "VODForge", font=title, fill="#ffffff", anchor="mm")
    draw.text(
        (640, 245),
        "Drag VODForge to Applications",
        font=body,
        fill="#c7d3df",
        anchor="mm",
    )
    draw.line((550, 420, 730, 420), fill="#63b4ed", width=8)
    draw.polygon([(730, 420), (704, 402), (704, 438)], fill="#63b4ed")
    draw.text(
        (640, 704),
        "Apple Silicon: macOS 26+  •  Intel: macOS 15+",
        font=body,
        fill="#acbac8",
        anchor="mm",
    )
    draw.text(
        (640, 752),
        "Open VODForge from Applications after copying.",
        font=body,
        fill="#acbac8",
        anchor="mm",
    )
    image.save(path, dpi=(144, 144))


def decorate_volume(volume: Path):
    from ds_store import DSStore
    from mac_alias import Alias

    background = volume / ".background/install.png"
    with DSStore.open(str(volume / ".DS_Store"), "w+") as store:
        store["."]["bwsp"] = {
            "WindowBounds": "{{120, 120}, {640, 420}}",
            "ShowToolbar": False,
            "ShowSidebar": False,
            "ShowStatusBar": False,
        }
        store["."]["icvp"] = {
            "viewOptionsVersion": 1,
            "backgroundType": 2,
            "backgroundImageAlias": Alias.for_file(str(background)).to_bytes(),
            "iconSize": 112.0,
            "textSize": 13.0,
            "labelOnBottom": True,
            "arrangeBy": "none",
            "gridOffsetX": 0.0,
            "gridOffsetY": 0.0,
            "gridSpacing": 100.0,
        }
        store["."]["vSrn"] = ("long", 1)
        store["VODForge.app"]["Iloc"] = (180, 205)
        store["Applications"]["Iloc"] = (460, 205)


def build_dmg(app: Path, output: Path, logo: Path):
    if output.exists() or output.suffix != ".dmg":
        raise ValueError("Require fresh .dmg output; refusing overwrite")
    audit = require_universal_app(app)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="dmg-stage-", dir=output.parent))
    command(["/usr/bin/ditto", str(app), str(stage / "VODForge.app")])
    (stage / "Applications").symlink_to("/Applications")
    (stage / ".background").mkdir()
    write_background(stage / ".background/install.png", logo)
    (stage / "Compatibility.txt").write_text(
        "Apple Silicon: macOS 26 or newer. Intel: macOS 15 or newer.\nPrivate candidate; release acceptance is separate.\n"
    )
    writable = output.with_suffix(".rw.dmg")
    if writable.exists():
        raise ValueError("Refusing existing writable image")
    command(
        [
            "/usr/bin/hdiutil",
            "create",
            "-srcfolder",
            str(stage),
            "-fs",
            "HFS+",
            "-format",
            "UDRW",
            "-volname",
            "VODForge",
            str(writable),
        ]
    )
    mount = stage / "mounted"
    mount.mkdir()
    device = None
    try:
        attach = plistlib.loads(
            subprocess.check_output(
                [
                    "/usr/bin/hdiutil",
                    "attach",
                    "-plist",
                    "-nobrowse",
                    "-noautoopen",
                    "-owners",
                    "off",
                    "-mountpoint",
                    str(mount),
                    str(writable),
                ]
            )
        )
        matching = [
            row
            for row in attach["system-entities"]
            if row.get("mount-point") == str(mount)
        ]
        if len(matching) != 1:
            raise RuntimeError("Owned mountpoint not established")
        device = matching[0]["dev-entry"]
        decorate_volume(mount)
    finally:
        if device:
            command(["/usr/bin/hdiutil", "detach", device])
    command(
        [
            "/usr/bin/hdiutil",
            "convert",
            str(writable),
            "-format",
            "UDZO",
            "-o",
            str(output),
        ]
    )
    command(["/usr/bin/hdiutil", "verify", str(output)])
    output.with_suffix(".json").write_text(
        json.dumps(
            {
                "app": str(app),
                "audit": audit,
                "image": str(output),
                "stage": str(stage),
                "scope": "Private packaging candidate; DMG signing/notarization and native install acceptance still required",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--logo", type=Path, default=Path("assets/brand/vf-mark.png"))
    args = parser.parse_args()
    build_dmg(args.app.resolve(), args.output.resolve(), args.logo.resolve())
