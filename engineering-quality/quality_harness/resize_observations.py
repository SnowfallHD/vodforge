"""Release geometry selection; event posting and observation remain distinct."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


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
