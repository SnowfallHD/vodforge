"""Content identity for tracked and nonignored source, including dirty edits."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess  # nosec B404 - fixed git argv, no shell
from pathlib import Path, PurePosixPath
from typing import Any


def source_manifest(root: Path) -> dict[str, Any]:
    root = root.resolve()

    def git(*args: str) -> bytes:
        return subprocess.run(  # nosec B603 B607 - fixed git arguments in owned checkout
            ["git", "-C", str(root), *args], check=True, capture_output=True
        ).stdout

    if Path(os.fsdecode(git("rev-parse", "--show-toplevel")).strip()).resolve() != root:
        raise ValueError("Source identity requires the exact checkout root")
    names = sorted(
        set(
            os.fsdecode(
                git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
            ).split("\0")
        )
        - {""}
    )
    files: dict[str, Any] = {}
    for name in names:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe source manifest path")
        path = root / relative
        if not path.resolve().is_relative_to(root):
            raise ValueError("Source file resolves outside checkout")
        if path.is_symlink():
            files[name] = {"kind": "symlink", "target": os.readlink(path)}
            if path.is_file():
                files[name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        elif path.is_file():
            files[name] = {
                "kind": "file",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        elif not path.exists():
            files[name] = {"kind": "missing"}
        else:
            raise ValueError("Unsupported directory or special source entry: " + name)
    payload = {"format": "vodforge-source-files-v1", "files": files}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {**payload, "sha256": digest}


def validate_manifest(value: Any, expected: str) -> bool:
    """Recompute content identity; an echoed 64-character label is insufficient."""
    if not isinstance(value, dict) or value.get("format") != "vodforge-source-files-v1":
        return False
    files = value.get("files")
    if not isinstance(files, dict) or not files:
        return False
    for name, entry in files.items():
        if not isinstance(name, str) or not name or "\\\\" in name:
            return False
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or str(path) != name:
            return False
        if not isinstance(entry, dict):
            return False
        kind = entry.get("kind")
        if kind == "file":
            if set(entry) != {"kind", "sha256"}:
                return False
        elif kind == "missing":
            if set(entry) != {"kind"}:
                return False
        elif kind == "symlink":
            target = entry.get("target")
            if (
                not isinstance(target, str)
                or not target
                or set(entry) - {"kind", "target", "sha256"}
            ):
                return False
        else:
            return False
        if "sha256" in entry and not re.fullmatch("[0-9a-f]{64}", str(entry["sha256"])):
            return False
    payload = {"format": value["format"], "files": files}
    actual = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return actual == expected and value.get("sha256") == actual
