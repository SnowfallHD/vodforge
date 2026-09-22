"""Evaluate native scrolling observations, without confusing callbacks and pixels."""

from __future__ import annotations

import math
from collections.abc import Mapping
from itertools import pairwise
from typing import Any

RESPONSE_BUDGET_SECONDS = 0.100
SAMPLING_BUDGET_SECONDS = 0.050


def evaluate_scroll_observations(report: Mapping[str, Any]) -> dict[str, Any]:
    """100ms is an upper responsiveness bound, not proof of 60Hz smoothness."""
    result: dict[str, Any] = {
        "status": "unproven",
        "assertions": {},
        "reason": "Incomplete or invalid native observations",
        "claim_scope": "sampled_response_latency_only",
        "continuous_smoothness": "unproven",
    }
    try:
        events, frames, handled = report["events"], report["frames"], report["handled"]
        if (
            not report.get("completed")
            or report.get("errors")
            or len(events) < 12
            or len(frames) < 8
            or len(handled) < 3
        ):
            return result
        for rows, key in [(events, "t"), (frames, "begin"), (handled, "begin")]:
            times = [float(row[key]) for row in rows]
            if not all(math.isfinite(t) and t >= 0 for t in times) or times != sorted(
                times
            ):
                return result
        for row in [*frames, *handled]:
            end = float(row["end"])
            if not math.isfinite(end) or end < row["begin"]:
                return result
        start, finish = events[0]["t"], events[-1]["t"]
        if (
            finish - start < 0.3
            or max(b["t"] - a["t"] for a, b in pairwise(events)) > 0.05
        ):
            return result
        before = [f for f in frames if f["end"] < start]
        after = [f for f in frames if f["begin"] > finish]
        active = [f for f in frames if f["end"] >= start and f["begin"] <= finish]
        if (
            len(before) < 2
            or not after
            or len(active) < 5
            or before[-2]["sha256"] != before[-1]["sha256"]
        ):
            return result
        # Input posting, handling and presentation have different boundaries.
        # Retain the recorded tail: the first post-input frame can precede the
        # final scroll callback or its visible response.
        observed = [before[-1], *active, *after]
        if (
            max(b["begin"] - a["begin"] for a, b in pairwise(observed))
            > SAMPLING_BUDGET_SECONDS
        ):
            return {**result, "reason": "Frame sampling gap exceeds 50ms"}
        if max(f["end"] - f["begin"] for f in observed) > SAMPLING_BUDGET_SECONDS:
            return {**result, "reason": "Frame capture overhead exceeds 50ms"}
        if not all(
            isinstance(f.get("sha256"), str) and len(f["sha256"]) == 64
            for f in observed
        ):
            return result
        movement = [h for h in handled if h["after"] != h["before"]]
        if (
            len(movement) < 3
            or max(h["after"] for h in movement) - min(h["before"] for h in movement)
            < 100
        ):
            return result
        changes = [
            b["end"] for a, b in pairwise(observed) if a["sha256"] != b["sha256"]
        ]
        response = changes[0] - start if changes else math.inf
        # A boundary legitimately stops pixels despite continuing wheel input.
        # Demand a changed frame after accepted movement, not after every intent.
        response_bounds = [
            next((t - h["begin"] for t in changes if t >= h["begin"]), math.inf)
            for h in movement
        ]
        if any(
            not math.isfinite(bound)
            and observed[-1]["end"] < h["begin"] + RESPONSE_BUDGET_SECONDS
            for h, bound in zip(movement, response_bounds, strict=True)
        ):
            return {
                **result,
                "reason": "Frame tail ends before pending movement can be evaluated",
            }
        worst = max(response_bounds)
        assertions = {
            "first_pixel_change_within_100ms": response <= RESPONSE_BUDGET_SECONDS,
            "no_sampled_pixel_freeze_over_100ms": worst <= RESPONSE_BUDGET_SECONDS,
        }
        return {
            **result,
            "status": "passed" if all(assertions.values()) else "failed",
            "assertions": assertions,
            "movement_response_bounds": [
                {
                    "movement_index": index,
                    "handling_begin": h["begin"],
                    "handling_end": h["end"],
                    "before": h["before"],
                    "after": h["after"],
                    "next_changed_frame_upper_ms": round(bound * 1000, 2)
                    if math.isfinite(bound)
                    else None,
                }
                for index, (h, bound) in enumerate(
                    zip(movement, response_bounds, strict=True)
                )
            ],
            "first_pixel_change_upper_ms": round(response * 1000, 2)
            if math.isfinite(response)
            else None,
            "maximum_movement_to_pixel_change_upper_ms": round(worst * 1000, 2)
            if math.isfinite(worst)
            else None,
            "reason": "Sampled window-server pixels; physical input and refresh-rate smoothness remain separate",
        }
    except (KeyError, TypeError, ValueError, OverflowError):
        return result
