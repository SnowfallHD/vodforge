"""Create a private universal2 DMG without Finder automation.

New single-icon packaging takes a separately signed Install VODForge.app.
The original app input retains historical drag-layout tooling for old receipts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import shutil
import subprocess
import tempfile
from pathlib import Path

from scripts.macos_native_closure import audit_payload


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
    graph = audit_payload(app, run)
    if not graph["qualified"]:
        raise ValueError(
            "Universal2 slices missing or dependency closure invalid: "
            + repr(graph["errors"])
        )
    run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)])
    run(["/usr/bin/xcrun", "stapler", "validate", str(app)])
    return {
        "bundle_version": info.get("CFBundleShortVersionString"),
        "native_files": graph["native_files"],
        "dependency_errors": graph["errors"],
    }


def require_installer_app(app: Path, run=command):
    """Refuse a renamed ordinary app or an unbound/unsigned installer."""
    if app.is_symlink() or app.name != "Install VODForge.app" or not app.is_dir():
        raise ValueError("Expected a real Install VODForge.app")
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    if (
        info.get("CFBundleIdentifier") != "com.snowfallhd.vodforge.installer"
        or info.get("CFBundleExecutable") != "VODForgeInstaller"
    ):
        raise ValueError("Unexpected installer identity")
    main = app / "Contents/MacOS/VODForgeInstaller"
    if main.is_symlink() or not main.is_file():
        raise ValueError("Missing real installer executable")
    payload = app / "Contents/Resources/VODForge.app"
    audit = require_universal_app(payload, run)
    with (payload / "Contents/MacOS/VODForge").open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if info.get("VFExecutableSHA256") != digest:
        raise ValueError("Installer payload does not match its bound executable")
    graph = audit_payload(app, run)
    if not graph["qualified"]:
        raise ValueError("Installer native dependency closure is incomplete")
    requirement = (
        'anchor apple generic and identifier "com.snowfallhd.vodforge.installer" '
        'and certificate leaf[subject.OU] = "76G5W4954G"'
    )
    run(
        [
            "/usr/bin/codesign",
            "--verify",
            "--deep",
            "--strict",
            "--all-architectures",
            "-R=" + requirement,
            str(app),
        ]
    )
    run(["/usr/bin/xcrun", "stapler", "validate", str(app)])
    return {
        "payload": audit,
        "payload_executable_sha256": digest,
        "native_files": graph["native_files"],
        "layout": "single installer icon",
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
    installer = app.name == "Install VODForge.app"
    audit = require_installer_app(app) if installer else require_universal_app(app)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="dmg-stage-", dir=output.parent))
    command(["/usr/bin/ditto", str(app), str(stage / app.name)])
    if installer:
        from scripts.macos_installer_window import BACKGROUND, write_assets

        artwork = stage / ".generated-artwork"
        write_assets(artwork, logo)
        (artwork / BACKGROUND).rename(stage / BACKGROUND)
        shutil.rmtree(artwork)  # Only this newly generated temporary artwork.
    else:
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
            "Install VODForge" if installer else "VODForge",
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
        if installer:
            from scripts.macos_installer_window import (
                decorate_volume as decorate_installer,
            )

            decorate_installer(mount)
        else:
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
    build_dmg(args.app.absolute(), args.output.absolute(), args.logo.resolve())
