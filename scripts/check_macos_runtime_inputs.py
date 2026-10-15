"""Cheap read-only input floor check, before packaging/signing; not OS acceptance."""

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def version(value):
    return tuple(int(part) for part in value.split(".")) + (0,) * (
        3 - len(value.split("."))
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maximum", default="15.0")
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--python-inputs", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    pending = [Path(value).resolve() for value in args.input]
    if args.python_inputs:
        pending.append(Path(sys.executable).resolve())
        for module in ("_ssl", "_sqlite3", "PySide6.QtCore"):
            spec = importlib.util.find_spec(module)
            if spec and spec.has_location and spec.origin:
                pending.append(Path(spec.origin).resolve())
        for tool in ("ffmpeg", "ffprobe", "deno"):
            path = shutil.which(tool)
            if path:
                pending.append(Path(path).resolve())
    seen, rows, errors = set(), [], []
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        result = subprocess.run(
            ["otool", "-l", str(path)], capture_output=True, text=True, check=False
        )
        floors = []
        for block in result.stdout.split("Load command"):
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
        if (
            result.returncode
            or not floors
            or any(version(v) > version(args.maximum) for v in floors)
        ):
            errors.append({"path": str(path), "floors": floors, "error": result.stderr})
        rows.append({"path": str(path), "floors": floors})
        links = subprocess.run(
            ["otool", "-L", str(path)], capture_output=True, text=True, check=False
        )
        identity = subprocess.run(
            ["otool", "-D", str(path)], capture_output=True, text=True, check=False
        )
        install_names = {
            line.strip()
            for line in identity.stdout.splitlines()[1:]
            if line.strip() and not line.endswith(":")
        }
        for line in links.stdout.splitlines()[1:]:
            name = line.strip().split(" (")[0]
            # A copied dylib's LC_ID_DYLIB may name its original build host.
            # It is identity, not a dependency on that host's current dylib.
            if name in install_names:
                continue
            # Follow host absolute dependencies: this catches Homebrew SQLite,
            # Python and OpenSSL contamination without changing load commands.
            if name.startswith("/") and not name.startswith(("/System/", "/usr/lib/")):
                pending.append(Path(name).resolve())
            elif name.startswith("@loader_path/"):
                dependency = path.parent / name.removeprefix("@loader_path/")
                if dependency.is_file():
                    pending.append(dependency.resolve())
    report = {
        "maximum": args.maximum,
        "inputs": rows,
        "errors": errors,
        "scope": "Input floors/absolute and loader-relative links; final bundle audit and native OS acceptance still required",
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 1 if errors or not rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
