"""Privacy-safe observations for archive feature owners.

Uses the existing product telemetry owner for consent, correlation and transport.
Observation failures must never change a user's media/history operation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from .failure_diagnostics import FailureDiagnostic, capture_failure
from .history import HistoryError
from .telemetry_features import time_bucket


def operation(
    telemetry: Any,
    feature: str,
    action: str,
    key: str | None,
    dimensions: Mapping[str, str] | None = None,
    *,
    failure_detail: FailureDiagnostic | None = None,
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
                failure_detail=failure_detail,
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


def history_operation(
    telemetry: Any,
    action: str,
    key: str,
    boundary: str,
    *,
    error: HistoryError | None = None,
    item_count: int | None = None,
) -> bool:
    """Observe a single boundary invocation; never infer cross-process identity."""
    try:
        dimensions = {"history_boundary": boundary}
        detail = None
        if error is not None:
            dimensions.update(
                history_document=error.document, history_phase=error.phase
            )
            detail = history_failure(error)
        if item_count is not None:
            dimensions["item_count"] = str(min(5000, max(0, item_count)))
        return operation(
            telemetry,
            "archive_history_operation",
            action,
            key,
            dimensions,
            failure_detail=detail,
        )
    except Exception:  # noqa: BLE001 - optional diagnostics cannot own history
        return False


def history_failure(error: HistoryError) -> FailureDiagnostic:
    """Use explicit ledger validation and typed OS facts, never local text."""
    detail = capture_failure(error, stage="history", inspect_text=False)
    if error.cause != "unknown":
        detail = replace(
            detail, failure_code="history_" + error.cause, reason="validation"
        )
    return detail
