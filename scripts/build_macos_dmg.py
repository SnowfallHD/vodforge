"""Create the VODForge DMG around the signed "Install VODForge" app.

The DMG opens a branded window with a single installer icon; its layout is
written directly (no Finder scripting). Sign, notarize and staple the DMG
afterwards (`scripts/finalize_universal_macos.py` does this for releases).
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


def build_dmg(app: Path, output: Path, logo: Path):
    if output.exists() or output.suffix != ".dmg":
        raise ValueError("Require fresh .dmg output; refusing overwrite")
    audit = require_installer_app(app)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="dmg-stage-", dir=output.parent))
    command(["/usr/bin/ditto", str(app), str(stage / app.name)])
    from scripts.macos_installer_window import BACKGROUND, write_assets

    artwork = stage / ".generated-artwork"
    write_assets(artwork, logo)
    (artwork / BACKGROUND).rename(stage / BACKGROUND)
    shutil.rmtree(artwork)  # Only this newly generated temporary artwork.
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
            "Install VODForge",
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
        from scripts.macos_installer_window import decorate_volume

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
                "next": "Sign, notarize and staple this DMG before distributing it",
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
