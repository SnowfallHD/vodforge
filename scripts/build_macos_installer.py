"""Assemble a fresh single-entry installer app; signing/qualification are separate.

Never installs into Applications, opens an app, or creates a distributable DMG.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import subprocess
from pathlib import Path

from scripts.build_macos_dmg import require_universal_app


def run(args):
    return subprocess.check_output(args, text=True)


def compile_helper(output: Path):
    if output.exists():
        raise ValueError("Require a fresh helper output")
    output.parent.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).with_name("macos_installer.m").resolve()
    slices = []
    for arch, minimum in (("arm64", "26.0"), ("x86_64", "15.0")):
        thin = output.with_name(output.name + "-" + arch)
        if thin.exists():
            raise ValueError("Refusing existing architecture output")
        run(
            [
                "/usr/bin/clang",
                "-fobjc-arc",
                "-arch",
                arch,
                "-mmacosx-version-min=" + minimum,
                "-framework",
                "AppKit",
                "-framework",
                "Security",
                str(source),
                "-o",
                str(thin),
            ]
        )
        slices.append(thin)
    run(["/usr/bin/lipo", "-create", *map(str, slices), "-output", str(output)])
    if set(run(["/usr/bin/lipo", "-archs", str(output)]).split()) != {
        "arm64",
        "x86_64",
    }:
        raise RuntimeError("Installer architectures do not match")


def build_installer(payload: Path, output: Path):
    if output.exists() or output.is_symlink() or output.name != "Install VODForge.app":
        raise ValueError("Require fresh Install VODForge.app; refusing overwrite")
    if output.parent.exists() and any(output.parent.iterdir()):
        raise ValueError("Require a fresh empty assembly directory")
    audit = require_universal_app(payload)
    executable = payload / "Contents/MacOS/VODForge"
    with executable.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    contents = output / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    (contents / "Resources").mkdir()
    compile_helper(contents / "MacOS/VODForgeInstaller")
    run(["/usr/bin/ditto", str(payload), str(contents / "Resources/VODForge.app")])
    # Thin compile intermediates are evidence beside the bundle, never shipped.
    for arch in ("arm64", "x86_64"):
        thin = contents / ("MacOS/VODForgeInstaller-" + arch)
        thin.rename(output.parent / ("VODForgeInstaller-" + arch))
    run(["/bin/cp", "assets/VODForge.icns", str(contents / "Resources/VODForge.icns")])
    (contents / "Info.plist").write_bytes(
        plistlib.dumps(
            {
                "CFBundleIdentifier": "com.snowfallhd.vodforge.installer",
                "CFBundleName": "Install VODForge",
                "CFBundleDisplayName": "Install VODForge",
                "CFBundleExecutable": "VODForgeInstaller",
                "CFBundlePackageType": "APPL",
                "CFBundleIconFile": "VODForge.icns",
                "CFBundleShortVersionString": audit["bundle_version"],
                "CFBundleVersion": "1",
                "LSMinimumSystemVersionByArchitecture": {
                    "arm64": "26.0",
                    "x86_64": "15.0",
                },
                "NSHighResolutionCapable": True,
                "VFExecutableSHA256": digest,
            }
        )
    )
    (output.parent / "installer-assembly.json").write_text(
        json.dumps(
            {
                "payload": str(payload),
                "payload_audit": audit,
                "payload_executable_sha256": digest,
                "installer": str(output),
                "state": "unsigned assembly; not launch/install/Finder/Apple acceptance",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    options = parser.parse_args()
    build_installer(options.payload.absolute(), options.output.absolute())
