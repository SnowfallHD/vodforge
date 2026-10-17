"""Verify per-architecture loader edges in a completed macOS payload."""

from __future__ import annotations

import re
import subprocess
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


def apple(path):
    return path.startswith(("/usr/lib/", "/System/Library/"))


def load_commands(path, arch, run):
    text = run(["/usr/bin/otool", "-arch", arch, "-l", str(path)])
    deps, rpaths = [], []
    for block in text.split("Load command"):
        if re.search(
            r"cmd\s+LC_(?:LOAD_DYLIB|LOAD_WEAK_DYLIB|REEXPORT_DYLIB|LOAD_UPWARD_DYLIB)\b",
            block,
        ):
            match = re.search(r"\bname (.+?) \(offset", block)
            if match:
                deps.append(match.group(1))
        if re.search(r"cmd\s+LC_RPATH\b", block):
            match = re.search(r"\bpath (.+?) \(offset", block)
            if match:
                rpaths.append(match.group(1))
    return deps, rpaths


def audit_payload(root: Path, run=None):
    """Thin dylibs are valid only with matching, closed load edges; entries are fat."""
    if run is None:
        run = lambda args: subprocess.check_output(args, text=True)
    root = root.resolve()
    files, errors, incoming = {}, [], set()
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        with path.open("rb") as stream:
            if stream.read(4) not in MACHO:
                continue
        slices = set(run(["/usr/bin/lipo", "-archs", str(path)]).split())
        files[path.resolve()] = slices
        if (
            (path.suffix != ".dylib" and not ARCHES <= slices)
            or not slices
            or not slices <= ARCHES
        ):
            errors.append(
                {
                    "path": str(path.relative_to(root)),
                    "error": "universal entry slices missing",
                    "slices": sorted(slices),
                }
            )
    cache = {}

    def commands(path, arch):
        if (path, arch) not in cache:
            cache[path, arch] = load_commands(path, arch, run)
        return cache[path, arch]

    def executable_dir(path):
        for parent in path.parents:
            if parent.suffix == ".app" and parent.is_relative_to(root):
                return parent / "Contents/MacOS"
        return root

    def expand(value, loader, exedir):
        if value.startswith("@loader_path/"):
            return (loader.parent / value[13:]).resolve()
        if value.startswith("@executable_path/"):
            return (exedir / value[17:]).resolve()
        if value.startswith("/"):
            return Path(value).resolve()
        return None

    checked = set()

    def walk(path, arch, inherited, exedir):
        # Include inherited rpaths in the key: the same library can have different
        # valid callers, and each actual edge must resolve within that context.
        _, local = commands(path, arch)
        rpaths = tuple(
            dict.fromkeys(
                [p for r in local if (p := expand(r, path, exedir)) is not None]
                + list(inherited)
            )
        )
        key = path, arch, rpaths, exedir
        if key in checked:
            return
        checked.add(key)
        deps, _ = commands(path, arch)
        for dep in deps:
            if apple(dep):
                continue
            if dep.startswith("@rpath/"):
                candidates = [(r / dep[7:]).resolve() for r in rpaths]
            else:
                resolved = expand(dep, path, exedir)
                candidates = [resolved] if resolved else []
            target = next(
                (
                    p
                    for p in candidates
                    if p.is_relative_to(root) and p in files and arch in files[p]
                ),
                None,
            )
            if target is None:
                errors.append(
                    {
                        "path": str(path.relative_to(root)),
                        "arch": arch,
                        "dependency": dep,
                        "error": "unresolved or external architecture provider",
                    }
                )
                continue
            incoming.add((target, arch))
            walk(target, arch, rpaths, exedir)

    # Python extensions, framework binaries, executables and dynamically loaded
    # fat plugins are roots. Thin libraries must be reached from an actual edge.
    for path, slices in files.items():
        if path.suffix != ".dylib" or ARCHES <= slices:
            for arch in sorted(slices & ARCHES):
                exedir = executable_dir(path)
                main = exedir / "VODForge"
                inherited = []
                if main in files and arch in files[main]:
                    inherited = [
                        p
                        for r in commands(main, arch)[1]
                        if (p := expand(r, main, exedir)) is not None
                    ]
                walk(path, arch, inherited, exedir)
    for path, slices in files.items():
        if not ARCHES <= slices:
            for arch in slices:
                if (path, arch) not in incoming:
                    errors.append(
                        {
                            "path": str(path.relative_to(root)),
                            "arch": arch,
                            "error": "unreferenced thin library",
                        }
                    )
    if not files:
        errors.append({"error": "no native payload"})
    return {
        "native_files": [
            {"path": str(p.relative_to(root)), "slices": sorted(a)}
            for p, a in files.items()
        ],
        "errors": errors,
        "qualified": not errors,
    }
