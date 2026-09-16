"""Privacy-safe observations for archive feature owners.

Uses the existing product telemetry owner for consent, correlation and transport.
Observation failures must never change a user's media/history operation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .telemetry_features import time_bucket


def operation(
    telemetry: Any,
    feature: str,
    action: str,
    key: str | None,
    dimensions: Mapping[str, str] | None = None,
) -> bool:
    if telemetry is None or key is None:
        return False
    try:
        return bool(
            telemetry.record_operation(
                feature,
                action,
                operation_key=key,
                dimensions=dimensions,
            )
        )
    except Exception:  # noqa: BLE001 - optional observations cannot own user effects
        return False


def usage(
    telemetry: Any,
    feature: str,
    action: str,
    dimensions: Mapping[str, str] | None = None,
) -> bool:
    if telemetry is None:
        return False
    try:
        return bool(telemetry.record_feature(feature, action, dimensions=dimensions))
    except Exception:  # noqa: BLE001 - optional observations cannot own user effects
        return False


def relink_dimensions(preview: Any) -> dict[str, str]:
    counts = preview.counts
    ready = counts.get("ready", 0)
    return {
        "item_count": str(min(5000, len(preview.entries))),
        "verified_count": str(min(5000, ready)),
        "unresolved_count": str(min(5000, len(preview.entries) - ready)),
        "collision_count": str(min(5000, counts.get("collision", 0))),
        "missing_count": str(min(5000, counts.get("missing", 0))),
        "unavailable_count": str(
            min(5000, counts.get("unavailable", 0) + counts.get("foreign_platform", 0))
        ),
        "processing_bucket": time_bucket(preview.elapsed_ms / 1000),
    }
