"""Explicit build-time AppKit helper compilation; never invoked by app startup."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from scripts.macos_native_closure import MACHO, apple, load_commands

FLOORS = {"arm64": "26.0", "x86_64": "15.0"}
LIBRARY = "libvodforge_fullscreen.dylib"
PACKAGE_DESTINATION = "yt_downloader/platforms/macos"


def deployment_minimum(arch, configured=None):
    """A package may raise its requirement, never advertise below its helper."""
    if arch not in FLOORS:
        raise ValueError("Unsupported macOS target architecture")
    value = configured or FLOORS[arch]
    if not re.fullmatch(r"\d+(?:\.\d+){0,2}", value):
        raise ValueError("Invalid macOS deployment minimum")
    normalize = lambda text: (
        tuple(map(int, text.split("."))) + (0,) * (3 - len(text.split(".")))
    )
    if normalize(value) < normalize(FLOORS[arch]):
        raise ValueError("Configured minimum is below the native helper requirement")
    return value


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate(path, arches, run):
    if not path.is_file() or path.read_bytes()[:4] not in MACHO:
        raise ValueError("Native fullscreen compiler produced no Mach-O helper")
    actual = set(run(["/usr/bin/lipo", "-archs", str(path)]).split())
    if actual != set(arches):
        raise ValueError("Native fullscreen helper architecture mismatch")
    for arch in arches:
        text = run(["/usr/bin/otool", "-arch", arch, "-l", str(path)])
        floors = []
        for block in text.split("Load command"):
            field = (
                "minos"
                if re.search(r"cmd\s+LC_BUILD_VERSION\b", block)
                else "version"
                if re.search(r"cmd\s+LC_VERSION_MIN_MACOSX\b", block)
                else None
            )
            match = (
                re.search(r"\b" + field + r"\s+(\d+(?:\.\d+){0,2})", block)
                if field
                else None
            )
            if match:
                floors.append(tuple(int(n) for n in match.group(1).split(".")))
        expected = tuple(int(n) for n in FLOORS[arch].split("."))
        normalize = lambda value: value + (0,) * (3 - len(value))
        if not floors or any(
            normalize(value) != normalize(expected) for value in floors
        ):
            raise ValueError("Native fullscreen helper deployment floor mismatch")
        dependencies, _ = load_commands(path, arch, run)
        if any(not apple(dependency) for dependency in dependencies):
            raise ValueError("Native fullscreen helper has a non-system dependency")


def build(source: Path, output: Path, arches, run=None):
    """Compile immutable source to a new output directory, recording provenance."""
    arches = tuple(arches)
    if (
        not arches
        or len(set(arches)) != len(arches)
        or any(a not in FLOORS for a in arches)
    ):
        raise ValueError("Expected unique supported target architectures")
    source = source.resolve()
    output = output.absolute()
    if not source.is_file():
        raise ValueError("Required native fullscreen source is missing")
    header_source = source.with_name("header_toolbar.m")
    if not header_source.is_file():
        raise ValueError("Required native header toolbar source is missing")
    sources = (source, header_source)
    if output.exists():
        raise ValueError("Refusing existing native fullscreen build output")
    if run is None:
        run = lambda args: subprocess.check_output(
            args, text=True, stderr=subprocess.STDOUT
        )
    output.mkdir(parents=True)
    receipt = {
        "source": str(source),
        "source_sha256": _sha(source),
        "source_inputs": [
            {"path": str(item), "sha256": _sha(item)} for item in sources
        ],
        "architectures": list(arches),
        "deployment_floors": {a: FLOORS[a] for a in arches},
        "commands": [],
        "qualified": False,
        "scope": "Build-time helper only; no runtime/UI or signed acceptance",
    }
    try:
        slices = []
        for arch in arches:
            target = output / (arch + ".dylib")
            command = [
                "/usr/bin/xcrun",
                "clang",
                "-dynamiclib",
                "-arch",
                arch,
                "-mmacosx-version-min=" + FLOORS[arch],
                "-fno-objc-arc",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-framework",
                "AppKit",
                "-framework",
                "Foundation",
                "-install_name",
                "@rpath/" + LIBRARY,
                *map(str, sources),
                "-o",
                str(target),
            ]
            receipt["commands"].append(command)
            run(command)
            _validate(target, [arch], run)
            slices.append(target)
        library = output / LIBRARY
        if len(slices) == 1:
            shutil.copy2(slices[0], library)
        else:
            command = [
                "/usr/bin/lipo",
                "-create",
                *map(str, slices),
                "-output",
                str(library),
            ]
            receipt["commands"].append(command)
            run(command)
        _validate(library, arches, run)
        if any(
            _sha(item) != bound["sha256"]
            for item, bound in zip(sources, receipt["source_inputs"])
        ):
            raise ValueError(
                "Native fullscreen/header source changed during compilation"
            )
        receipt.update(
            library=str(library), output_sha256=_sha(library), qualified=True
        )
    except Exception as error:
        receipt["error"] = str(error)
        raise
    finally:
        (output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--arch", action="append", choices=tuple(FLOORS), required=True)
    args = parser.parse_args()
    build(args.source, args.output, args.arch)
