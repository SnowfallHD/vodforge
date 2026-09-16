"""Write provenance at build time; dirty or non-Git sources stay unknown."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def source_revision(root: Path) -> str:
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        revision = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return (
        revision
        if not status and re.fullmatch(r"[0-9a-f]{40}", revision)
        else "unknown"
    )


if __name__ == "__main__":
    destination = Path(sys.argv[1])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(source_revision(Path.cwd()), encoding="utf-8")
