"""Build provenance, independent of version and user analytics permission.

Only explicitly opted-in release artifacts may contact production telemetry.
The journey override can only disable collection, never enable a local build.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def production_telemetry_allowed() -> bool:
    if os.environ.get("VODFORGE_DISABLE_TELEMETRY") or os.environ.get(
        "VODFORGE_QUALITY_E2E"
    ):
        return False
    root = getattr(sys, "_MEIPASS", None)
    if not root:
        return False
    try:
        return (Path(root) / "VODFORGE_TELEMETRY_POLICY").read_text(
            encoding="utf-8"
        ).strip() == "production"
    except (OSError, UnicodeError):
        return False
