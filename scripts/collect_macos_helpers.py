"""Collect FFmpeg, ffprobe and Deno with every library they load, for one architecture.

The universal build needs each architecture's helpers as a flat folder: the three
executables plus each non-system library they load (directly or indirectly),
stored under the name the loader asks for. `scripts/assemble_universal_helpers.py`
then rewrites those references and combines two such folders.

Run it on the architecture being collected (the release workflow runs it on the
Apple silicon and Intel runners after installing the Homebrew tools):

    python -m scripts.collect_macos_helpers --output helpers-arm64
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

HELPERS = ("ffmpeg", "ffprobe", "deno")
SYSTEM_PREFIXES = ("/usr/lib/", "/System/Library/")


def _otool(args, path: Path) -> str:
    return subprocess.check_output(["/usr/bin/otool", *args, str(path)], text=True)


def load_commands(path: Path, run=_otool) -> tuple[list[str], list[str]]:
    """The libraries a Mach-O file loads (excluding its own id) and its rpaths."""
    identity = set(run(["-D"], path).splitlines()[1:])
    dependencies = [
        line.strip().split(" (compatibility version")[0]
        for line in run(["-L"], path).splitlines()
        if line.startswith("\t")
    ]
    dependencies = [name for name in dependencies if name not in identity]
    rpaths = []
    lines = run(["-l"], path).splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "cmd LC_RPATH":
            for following in lines[index + 1 : index + 4]:
                parts = following.split()
                if parts and parts[0] == "path":
                    rpaths.append(parts[1])
                    break
    return dependencies, rpaths


def _expand(value: str, owner: Path, executable: Path) -> Path:
    if value.startswith("@loader_path"):
        return owner.parent / value.removeprefix("@loader_path").lstrip("/")
    if value.startswith("@executable_path"):
        return executable.parent / value.removeprefix("@executable_path").lstrip("/")
    return Path(value)


def resolve(reference: str, owner: Path, executable: Path, rpaths: list[Path]) -> Path:
    """Find the file a load command refers to, the way dyld would.

    `rpaths` are already absolute: each was expanded against the file that
    declared it, since an inherited `@loader_path` rpath means that file's folder.
    """
    if reference.startswith("@rpath/"):
        name = reference.removeprefix("@rpath/")
        for rpath in rpaths:
            candidate = rpath / name
            if candidate.exists():
                return candidate.resolve()
        raise FileNotFoundError(f"{owner}: cannot resolve {reference} via {rpaths}")
    candidate = _expand(reference, owner, executable)
    if not candidate.exists():
        raise FileNotFoundError(f"{owner}: missing dependency {reference}")
    return candidate.resolve()


def collect(output: Path, tools: dict[str, Path], run=_otool) -> dict:
    if output.exists():
        raise ValueError(f"Refusing existing output: {output}")
    files: dict[str, Path] = {}
    queue: list[tuple[Path, Path, list[Path]]] = []
    for name in HELPERS:
        executable = tools[name].resolve()
        files[name] = executable
        queue.append((executable, executable, []))
    while queue:
        path, executable, inherited = queue.pop()
        dependencies, rpaths = load_commands(path, run)
        search = [_expand(value, path, executable) for value in rpaths] + inherited
        for reference in dependencies:
            if reference.startswith(SYSTEM_PREFIXES):
                continue
            target = resolve(reference, path, executable, search)
            name = Path(reference).name
            if name in files:
                if files[name] != target:
                    raise ValueError(
                        f"Two different libraries are both named {name}: "
                        f"{files[name]} and {target}"
                    )
                continue
            files[name] = target
            queue.append((target, executable, search))
    output.mkdir(parents=True)
    for name, source in sorted(files.items()):
        destination = output / name
        shutil.copyfile(source, destination)
        os.chmod(destination, 0o755)
    receipt = {
        "architecture": platform.machine(),
        "files": {
            name: {
                "source": str(source),
                "sha256": hashlib.sha256((output / name).read_bytes()).hexdigest(),
            }
            for name, source in sorted(files.items())
        },
    }
    (output.parent / f"{output.name}-receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    tools = {}
    for name in HELPERS:
        found = shutil.which(name)
        if not found:
            raise SystemExit(f"{name} was not found on PATH")
        tools[name] = Path(found)
    receipt = collect(args.output, tools)
    print(f"Collected {len(receipt['files'])} files into {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
