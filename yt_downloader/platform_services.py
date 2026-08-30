from __future__ import annotations

import os
import shutil
# This service accepts only a fixed or resolved executable and never invokes a shell.
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any, Callable


def open_path(
    path: Path,
    *,
    platform_name: str | None = None,
    popen: Callable[[list[str]], Any] = subprocess.Popen,
    which: Callable[[str], str | None] = shutil.which,
    startfile: Callable[[Path], Any] | None = None,
) -> None:
    """Open a folder without deferring executable selection to subprocess PATH lookup."""
    path.mkdir(parents=True, exist_ok=True)
    platform_name = sys.platform if platform_name is None else platform_name
    if platform_name.startswith("win"):
        windows_startfile = (
            getattr(os, "startfile", None) if startfile is None else startfile
        )
        if not callable(windows_startfile):
            raise RuntimeError("The Windows folder opener is unavailable.")
        windows_startfile(path)
        return

    if platform_name == "darwin":
        opener = Path("/usr/bin/open")
    else:
        resolved = which("xdg-open")
        candidate = Path(resolved) if resolved else None
        if candidate is None or not candidate.is_absolute():
            raise RuntimeError("No trusted system folder opener is available.")
        try:
            opener = candidate.resolve(strict=True)
        except OSError as exc:
            raise RuntimeError("No trusted system folder opener is available.") from exc
        if not opener.is_file() or not os.access(opener, os.X_OK):
            raise RuntimeError("No trusted system folder opener is available.")

    popen([str(opener), str(path)])
