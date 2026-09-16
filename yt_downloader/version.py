from __future__ import annotations

import re
import sys
from pathlib import Path

DEFAULT_VERSION = "0.1.0-dev"
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def bundled_version_file() -> Path | None:
    raw_meipass = getattr(sys, "_MEIPASS", None)
    if not raw_meipass:
        return None
    return Path(raw_meipass) / "VODFORGE_VERSION"


def read_app_version(path: Path | None = None) -> str:
    path = bundled_version_file() if path is None else path
    if path is None:
        return DEFAULT_VERSION
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return DEFAULT_VERSION
    return value if VERSION_RE.fullmatch(value) else DEFAULT_VERSION


__version__ = read_app_version()


def read_build_revision(path: Path | None = None) -> str:
    """Build-time provenance only; never infer a commit from a user's checkout."""
    if path is None:
        bundle = getattr(sys, "_MEIPASS", None)
        if not bundle:
            return "unknown"
        path = Path(bundle) / "VODFORGE_BUILD_REVISION"
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    return value if re.fullmatch(r"[0-9a-f]{40}", value) else "unknown"
