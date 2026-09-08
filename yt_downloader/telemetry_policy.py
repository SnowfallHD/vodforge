"""Build provenance, independent of version and user analytics permission.

Only explicitly opted-in release artifacts may contact production telemetry.
Ordinary journeys remain disabled. Explicit preview artifacts can contact only
the isolated preview service with a private QA key and a separate profile.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PREVIEW_ORIGIN = "https://vodforge-preview.little-mountain-f558.workers.dev"


def preview_telemetry_allowed() -> bool:
    """Explicit packaged QA only; never interprets a version as build provenance."""
    if os.environ.get("VODFORGE_DISABLE_TELEMETRY"):
        return False
    root = getattr(sys, "_MEIPASS", None)
    key = os.environ.get("VODFORGE_QA_ACCESS_KEY", "")
    profile = os.environ.get("VODFORGE_QA_PROFILE", "")
    if not root or len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
        return False
    if not profile or not Path(profile).is_absolute():
        return False
    try:
        return (
            Path(root) / "VODFORGE_TELEMETRY_POLICY"
        ).read_text().strip() == "preview"
    except (OSError, UnicodeError):
        return False


def telemetry_collection_allowed() -> bool:
    return production_telemetry_allowed() or preview_telemetry_allowed()


def telemetry_site_origin() -> str:
    return PREVIEW_ORIGIN if preview_telemetry_allowed() else "https://getvodforge.com"


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
