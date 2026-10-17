"""Fail-closed universal2 input preflight and private PyInstaller packaging."""

from __future__ import annotations

import argparse
import json
import plistlib
import re
import subprocess
from pathlib import Path

from scripts.build_macos_fullscreen import PACKAGE_DESTINATION
from scripts.build_macos_fullscreen import build as build_fullscreen
from scripts.macos_native_closure import ARCHES, MACHO, audit_payload


def inspect_inputs(roots, run=subprocess.check_output):
    rows, errors, excluded_debug = [], [], []
    seen = set()
    for root in roots:
        if not root.exists():
            errors.append({"path": str(root), "error": "missing input"})
            continue
        for path in [root] if root.is_file() else sorted(root.rglob("*")):
            if any(parent.suffix == ".dSYM" for parent in path.parents):
                excluded_debug.append(str(path))
                continue
            if path.is_symlink() or not path.is_file() or path.resolve() in seen:
                continue
            seen.add(path.resolve())
            with path.open("rb") as stream:
                if stream.read(4) not in MACHO:
                    continue
            slices = set(run(["/usr/bin/lipo", "-archs", str(path)], text=True).split())
            row = {"path": str(path), "slices": sorted(slices)}
            rows.append(row)
            if not ARCHES <= slices and path.suffix != ".dylib":
                errors.append(
                    {
                        "path": str(path),
                        "error": "missing architecture",
                        "missing": sorted(ARCHES - slices),
                    }
                )
            for arch, maximum in [("arm64", (26, 0, 0)), ("x86_64", (15, 0, 0))]:
                if arch not in slices:
                    continue
                text = run(
                    ["/usr/bin/otool", "-arch", arch, "-l", str(path)], text=True
                )
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
                        floors.append(match.group(1))
                values = [
                    tuple(map(int, v.split("."))) + (0,) * (3 - len(v.split(".")))
                    for v in floors
                ]
                row[arch + "_floors"] = floors
                if not values or max(values) > maximum:
                    errors.append(
                        {
                            "path": str(path),
                            "arch": arch,
                            "error": "unqualified deployment floor",
                            "floors": floors,
                        }
                    )
        # Unique ABI dylibs may be thin only when the actual per-architecture
        # loader graph is closed and each thin slice has an incoming edge.
        if root.is_dir() and any(
            Path(r["path"]).is_relative_to(root) and not ARCHES <= set(r["slices"])
            for r in rows
        ):
            graph = audit_payload(root, lambda args: run(args, text=True))
            errors.extend(graph["errors"])
    if not rows:
        errors.append({"error": "no native inputs inspected"})
    return {
        "native_files": rows,
        "errors": errors,
        "qualified": not errors,
        "excluded_debug_paths": excluded_debug,
    }


def package(source: Path, python: Path, tools: Path, output: Path, version: str):
    if output.exists():
        raise ValueError("Refusing existing package output")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Expected stable semantic version")
    if subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=source, text=True
    ).strip():
        raise ValueError("Private candidate still requires clean source")
    runtime = json.loads(
        subprocess.check_output(
            [
                str(python),
                "-c",
                "import sysconfig,sys,json;print(json.dumps(dict(base=sys.base_prefix,stdlib=sysconfig.get_path('stdlib'))))",
            ],
            text=True,
        )
    )
    # Inspect runtime inputs, not the framework's unused Intel-only alternate
    # launcher, static build objects or debug symbols.
    required = [
        python.resolve(),
        (Path(runtime["base"]) / "Python").resolve(),
        Path(runtime["stdlib"]) / "lib-dynload",
        python.parent.parent / "lib",
        tools,
    ]
    preflight = inspect_inputs(required)
    if not preflight["qualified"]:
        raise ValueError(
            "Universal input qualification failed: " + json.dumps(preflight["errors"])
        )
    for tool in ["ffmpeg", "ffprobe", "deno", "libsqlite3.dylib"]:
        if not (tools / tool).is_file():
            raise ValueError("Missing required tool: " + tool)
    output.mkdir(parents=True)
    native_helper = build_fullscreen(
        source / "yt_downloader/platforms/macos/fullscreen_lifecycle.m",
        output / "native-fullscreen",
        ["arm64", "x86_64"],
    )
    helper_preflight = inspect_inputs([Path(native_helper["library"])])
    if not helper_preflight["qualified"]:
        raise ValueError("Native fullscreen helper input qualification failed")
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=source, text=True
    ).strip()
    metadata = output / "version"
    metadata.mkdir()
    for name, value in {
        "VODFORGE_VERSION": version,
        "VODFORGE_BUILD_REVISION": revision,
        "VODFORGE_TELEMETRY_POLICY": "production",
    }.items():
        (metadata / name).write_text(value)
    command = [
        str(python),
        "-m",
        "PyInstaller",
        "--clean",
        "--windowed",
        "--onedir",
        "--name",
        "VODForge",
        "--target-arch",
        "universal2",
        "--distpath",
        str(output / "dist"),
        "--workpath",
        str(output / "work"),
        "--specpath",
        str(output),
        "--osx-bundle-identifier",
        "com.snowfallhd.vodforge",
        "--icon",
        str(source / "assets/VODForge.icns"),
        "--collect-all",
        "yt_dlp",
        "--collect-all",
        "curl_cffi",
        "--collect-data",
        "certifi",
        "--hidden-import",
        "PySide6.QtMultimedia",
        "--hidden-import",
        "PySide6.QtQuickControls2",
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "PIL.ImageTk",
        "--exclude-module",
        "vlc",
    ]
    for path in metadata.iterdir():
        command += ["--add-data", str(path) + ":."]
    command += ["--add-binary", native_helper["library"] + ":" + PACKAGE_DESTINATION]
    command += [
        "--add-data",
        str(source / "assets") + ":assets",
        "--add-data",
        str(source / "THIRD_PARTY_NOTICES.md") + ":.",
    ]
    for qml in sorted((source / "yt_downloader/qt_quick").glob("*.qml")):
        command += ["--add-data", str(qml) + ":yt_downloader/qt_quick"]
    for tool in [tools / n for n in ["ffmpeg", "ffprobe", "deno"]] + sorted(
        tools.glob("*.dylib")
    ):
        command += ["--add-binary", str(tool) + ":."]
    command.append(str(source / "main.py"))
    subprocess.run(command, cwd=source, check=True)
    plist = output / "dist/VODForge.app/Contents/Info.plist"
    info = plistlib.loads(plist.read_bytes())
    info.update(
        CFBundleShortVersionString=version,
        CFBundleVersion=version,
        LSMinimumSystemVersion="15.0",
        LSMinimumSystemVersionByArchitecture={"arm64": "26.0", "x86_64": "15.0"},
    )
    plist.write_bytes(plistlib.dumps(info))
    closure = audit_payload(output / "dist/VODForge.app")
    (output / "dependency-closure.json").write_text(
        json.dumps(closure, indent=2) + "\n"
    )
    if not closure["qualified"]:
        raise ValueError(
            "Packaged universal dependency closure failed; output preserved"
        )
    (output / "build-receipt.json").write_text(
        json.dumps(
            {
                "source": revision,
                "command": command,
                "preflight": preflight,
                "native_fullscreen": native_helper,
                "scope": "Unsigned private output; signature/complete runtime closure/native OS compatibility/release gates NOT qualified",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", type=Path, default=[])
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--python", type=Path)
    parser.add_argument("--tools", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--version", default="0.2.6")
    args = parser.parse_args()
    if args.build:
        if not all([args.python, args.tools, args.output]):
            parser.error("--build requires --python, --tools and --output")
        package(
            args.source.resolve(),
            args.python.absolute(),
            args.tools.resolve(),
            args.output.absolute(),
            args.version,
        )
        result = {"packaged": True, "release_qualified": False}
    else:
        result = inspect_inputs(args.input)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n")
    raise SystemExit(0 if result.get("qualified") or result.get("packaged") else 1)
