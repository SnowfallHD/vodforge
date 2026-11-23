"""Check that an app's stated macOS minimum is exactly what its files need.

macOS refuses to open an app whose Info.plist minimum is above the running
system, before any code runs. A minimum below what a file needs is as wrong:
the app opens and then fails to load that file. This check keeps the two in
step. It cannot tell that a file was compiled for a newer macOS than its code
needs (the 0.2.9 mistake, where one helper was built for macOS 26); the release
workflow catches that by opening the app and installer on a macOS 15 runner.

Usage: python -m scripts.check_macos_minimum "VODForge.app" ["Install VODForge.app" ...]
"""

from __future__ import annotations

import plistlib
import re
import subprocess
import sys
from pathlib import Path

from scripts.macos_native_closure import MACHO

ARCHES = ("arm64", "x86_64")


def _version(text):
    parts = [int(part) for part in str(text).split(".")]
    return tuple(parts + [0] * (3 - len(parts)))


def file_minimum(path, arch, run):
    """The newest macOS minimum among one slice's load commands, or None."""
    text = run(["/usr/bin/otool", "-arch", arch, "-l", str(path)])
    found = []
    for block in text.split("Load command"):
        if re.search(r"cmd\s+LC_BUILD_VERSION\b", block):
            match = re.search(r"\bminos\s+(\d+(?:\.\d+){0,2})", block)
        elif re.search(r"cmd\s+LC_VERSION_MIN_MACOSX\b", block):
            match = re.search(r"\bversion\s+(\d+(?:\.\d+){0,2})", block)
        else:
            continue
        if match:
            found.append(match.group(1))
    return max(found, key=_version) if found else None


def needed_minimums(app: Path, run):
    """Per architecture: the newest minimum any file needs, and which file."""
    needed = {}
    for path in sorted(app.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        with path.open("rb") as stream:
            if stream.read(4) not in MACHO:
                continue
        slices = set(run(["/usr/bin/lipo", "-archs", str(path)]).split())
        for arch in ARCHES:
            if arch not in slices:
                continue
            minimum = file_minimum(path, arch, run)
            if minimum and (
                arch not in needed or _version(minimum) > _version(needed[arch][0])
            ):
                needed[arch] = (minimum, str(path.relative_to(app)))
    return needed


def minimum_errors(app: Path, run=None) -> list[str]:
    if run is None:
        run = lambda args: subprocess.check_output(args, text=True)
    info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    by_arch = info.get("LSMinimumSystemVersionByArchitecture") or {}
    overall = info.get("LSMinimumSystemVersion")
    needed = needed_minimums(app, run)
    errors = []
    for arch in ARCHES:
        if arch not in needed:
            errors.append(f"{app.name}: no {arch} code found")
            continue
        stated = by_arch.get(arch) or overall
        need, where = needed[arch]
        if not stated:
            errors.append(f"{app.name}: no stated macOS minimum for {arch}")
        elif _version(stated) > _version(need):
            errors.append(
                f"{app.name}: states macOS {stated} for {arch}, but its files "
                f"need only {need} ({where}); macOS would refuse to open it on "
                "Macs that can run it"
            )
        elif _version(stated) < _version(need):
            errors.append(
                f"{app.name}: states macOS {stated} for {arch}, but {where} "
                f"needs {need}"
            )
    return errors


def main(argv=None) -> int:
    apps = [Path(arg) for arg in (sys.argv[1:] if argv is None else argv)]
    if not apps:
        print(__doc__)
        return 2
    errors = [error for app in apps for error in minimum_errors(app)]
    for error in errors:
        print("ERROR: " + error)
    if not errors:
        print(
            "Stated macOS minimums match the files: " + ", ".join(a.name for a in apps)
        )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
