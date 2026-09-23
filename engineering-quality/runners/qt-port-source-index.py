"""Index every code file for the Tk-to-Qt port review.

This is a coverage map, not a parity verdict. A source file remains open until
its behavior and rendered result are bound in qt-port-code-parity.md.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path

CODE_SUFFIXES = {".py", ".qml", ".sh", ".ps1", ".js", ".ts", ".yaml", ".yml"}


def index(root: Path) -> list[dict[str, object]]:
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    entries: list[dict[str, object]] = []
    for raw in sorted(set(result.stdout.split(b"\0"))):
        if not raw:
            continue
        relative = Path(raw.decode("utf-8"))
        if relative.suffix not in CODE_SUFFIXES:
            continue
        source = (root / relative).read_bytes()
        entry: dict[str, object] = {
            "path": relative.as_posix(),
            "sha256": hashlib.sha256(source).hexdigest(),
            "lines": source.count(b"\n") + bool(source and not source.endswith(b"\n")),
        }
        if relative.suffix == ".py":
            tree = ast.parse(source, filename=str(relative))
            imports: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module)
            entry["tk_import"] = any(
                name == "tkinter" or name.startswith("tkinter.") for name in imports
            )
            entry["qt_import"] = any(
                name == "PySide6" or name.startswith("PySide6.") for name in imports
            )
            entry["local_imports"] = sorted(
                name for name in imports if name.startswith("yt_downloader")
            )
            entry["top_level"] = [
                node.name
                for node in tree.body
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                )
            ]
        entries.append(entry)
    return entries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    entries = index(root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(entries, indent=2, sort_keys=True) + "\n")
    print(f"Indexed {len(entries)} code files into {args.output}")


if __name__ == "__main__":
    main()
