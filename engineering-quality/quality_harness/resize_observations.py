"""Release geometry selection; event posting and observation remain distinct."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import groupby
from typing import Any


def assess_pointer_tracking(
    samples: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    *,
    maximum_lag_px: int = 24,
) -> dict[str, Any]:
    """Require the native right edge to follow a held pointer during both drags.

    Query intervals over 20 ms cannot tie the pointer and window rectangle to
    one moment. Ignore those samples; fail if too few sound samples remain.
    """
    starts = [row for row in events if row.get("event") == "drag_start"]
    ends = [row for row in events if row.get("event") == "drag_end"]
    if len(starts) < 2 or len(ends) < 2:
        return {"passed": False, "reason": "Two native drag intervals required"}
    drags = []
    for start, end in zip(starts, ends, strict=False):
        rows = [
            row
            for row in samples
            if start["t"] <= row["sample_start"]
            and row["t"] <= end["t"]
            and row["pressed"]
            and row["query_ms"] <= 20
        ]
        if len(rows) < 30:
            drags.append(
                {
                    "passed": False,
                    "reason": "Too few paired pointer/edge samples",
                    "samples": len(rows),
                }
            )
            continue
        errors = sorted(abs(row["pointer"][0] - (row["rect"][2] - 2)) for row in rows)
        pointer_span = max(row["pointer"][0] for row in rows) - min(
            row["pointer"][0] for row in rows
        )
        edge_span = max(row["rect"][2] for row in rows) - min(
            row["rect"][2] for row in rows
        )
        plateau_travel = 0.0
        for _edge, plateau in groupby(rows, key=lambda row: row["rect"][2]):
            positions = [row["pointer"][0] for row in plateau]
            plateau_travel = max(plateau_travel, max(positions) - min(positions))
        p95 = errors[int((len(errors) - 1) * 0.95)]
        drags.append(
            {
                "passed": (
                    pointer_span >= 80
                    and edge_span >= 80
                    and p95 <= maximum_lag_px
                    and plateau_travel <= maximum_lag_px
                ),
                "samples": len(rows),
                "pointer_span_px": round(pointer_span, 1),
                "edge_span_px": round(edge_span, 1),
                "p95_edge_lag_px": round(p95, 1),
                "max_plateau_pointer_travel_px": round(plateau_travel, 1),
            }
        )
    return {
        "passed": len(drags) >= 2 and all(row["passed"] for row in drags),
        "drags": drags,
    }


def released_geometry_samples(
    samples: Sequence[Mapping[str, Any]],
    first_up: Mapping[str, Any] | None,
) -> list[Mapping[str, Any]]:
    """Include first-up bounds: geometry is queried after the button read ends."""
    if first_up is None:
        return []
    boundary = first_up["button_sample_ended"]
    return [row for row in samples if row["button_sample_ended"] >= boundary]


def overlapping_heartbeat_gaps(
    samples: Sequence[Mapping[str, Any]],
    intervals: Sequence[tuple[float, float]],
) -> list[float]:
    """Retain stalls crossing gesture boundaries, once per measured callback.

    A native drag can defer timers until after release. Its full callback gap
    overlaps the gesture even when neither callback endpoint lies inside it.
    This measures timer deferral, not cursor/frame or displayed-pixel latency.
    """
    return [
        row["gap_ms"]
        for row in samples
        if any(
            row["t"] >= start and row["t"] - row["gap_ms"] / 1000 <= end
            for start, end in intervals
        )
    ]
