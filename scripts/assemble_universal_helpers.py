"""Assemble verified thin helper dependencies, never finished PyInstaller apps."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

HELPERS = {"ffmpeg", "ffprobe", "deno"}
ARCHES = ("arm64", "x86_64")


def run(args):
    return subprocess.check_output(args, text=True)


def dependency_names(path: Path, arch: str):
    identity = set(
        run(["/usr/bin/otool", "-arch", arch, "-D", str(path)]).splitlines()[1:]
    )
    return [
        line.strip().split(" (compatibility version")[0]
        for line in run(["/usr/bin/otool", "-arch", arch, "-L", str(path)]).splitlines()
        if line.startswith("\t")
        and line.strip().split(" (compatibility version")[0] not in identity
    ]


def check_edges(slices, dependencies):
    errors = []
    for name, architectures in slices.items():
        for arch in architectures:
            for dep in dependencies(name, arch):
                if dep.startswith(("/usr/lib/", "/System/Library/")):
                    continue
                if not dep.startswith("@loader_path/") or "/" in dep.removeprefix(
                    "@loader_path/"
                ):
                    errors.append((name, arch, dep, "nonlocal dependency"))
                    continue
                target = dep.removeprefix("@loader_path/")
                if target not in slices or arch not in slices[target]:
                    errors.append((name, arch, dep, "missing architecture provider"))
    return errors


def assemble(arm: Path, intel: Path, output: Path):
    if output.exists():
        raise ValueError("Refusing existing helper output")
    sources = {"arm64": arm.resolve(), "x86_64": intel.resolve()}
    inventories = {}
    for arch, folder in sources.items():
        files = {}
        for path in folder.iterdir():
            if (
                path.is_symlink()
                or not path.is_file()
                or (path.name not in HELPERS and path.suffix != ".dylib")
            ):
                raise ValueError("Unexpected helper input: " + str(path))
            if set(run(["/usr/bin/lipo", "-archs", str(path)]).split()) != {arch}:
                raise ValueError("Expected exact thin input: " + str(path))
            files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        if not HELPERS <= files.keys():
            raise ValueError("Missing standalone helper")
        inventories[arch] = files
    output.mkdir(parents=True)
    thin = output.with_name(output.name + "-thin-inputs")
    thin.mkdir()
    for arch, folder in sources.items():
        stage = thin / arch
        stage.mkdir()
        for name in inventories[arch]:
            source, target = folder / name, stage / name
            shutil.copy2(source, target)
            deps = dependency_names(source, arch)
            for dep in deps:
                if dep.startswith(("/usr/lib/", "/System/Library/")):
                    continue
                provider = Path(dep).name
                if provider not in inventories[arch]:
                    raise ValueError(f"Unresolved {arch} dependency {name}: {dep}")
                run(
                    [
                        "/usr/bin/install_name_tool",
                        "-change",
                        dep,
                        "@loader_path/" + provider,
                        str(target),
                    ]
                )
            if name.endswith(".dylib"):
                run(
                    ["/usr/bin/install_name_tool", "-id", "@rpath/" + name, str(target)]
                )
            load = run(["/usr/bin/otool", "-l", str(target)])
            for block in load.split("Load command"):
                if re.search(r"cmd\s+LC_RPATH\b", block):
                    match = re.search(r"\bpath\s+(\S+)", block)
                    if match:
                        run(
                            [
                                "/usr/bin/install_name_tool",
                                "-delete_rpath",
                                match.group(1),
                                str(target),
                            ]
                        )
    slices = {}
    for name in sorted(set(inventories["arm64"]) | set(inventories["x86_64"])):
        inputs = [thin / arch / name for arch in ARCHES if name in inventories[arch]]
        destination = output / name
        if len(inputs) == 2:
            run(
                [
                    "/usr/bin/lipo",
                    "-create",
                    *map(str, inputs),
                    "-output",
                    str(destination),
                ]
            )
        else:
            if not name.endswith(".dylib"):
                raise ValueError("Standalone helper lacks both architectures")
            shutil.copy2(inputs[0], destination)
        run(["/usr/bin/codesign", "--force", "--sign", "-", str(destination)])
        slices[name] = sorted(
            run(["/usr/bin/lipo", "-archs", str(destination)]).split()
        )
    errors = check_edges(
        slices, lambda name, arch: dependency_names(output / name, arch)
    )
    if errors:
        raise ValueError("Helper closure failed: " + repr(errors))
    for arch, folder in sources.items():
        for name, digest in inventories[arch].items():
            if hashlib.sha256((folder / name).read_bytes()).hexdigest() != digest:
                raise ValueError("Input changed during helper assembly")
    # Stage receipts stay in the sibling thin-inputs directory; only
    # the manifest-named top-level binaries belong to the final helper payload.
    receipt = {
        "input_roots": {k: str(v) for k, v in sources.items()},
        "input_sha256": inventories,
        "slices": slices,
        "dependency_errors": errors,
        "output_sha256": {
            name: hashlib.sha256((output / name).read_bytes()).hexdigest()
            for name in slices
        },
        "scope": "Ad-hoc local dependency assembly with per-architecture load-edge validation; not final bundle signing/native OS qualification",
    }
    (output / "universal-helper-closure.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", type=Path, required=True)
    parser.add_argument("--intel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assemble(args.arm, args.intel, args.output)
