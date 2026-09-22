"""Typed negative evidence evaluation; flags and file hashes are not detection."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


def evaluate_native_channels(report: Mapping[str, Any], requirement: str) -> str:
    """Evaluate observations rather than trusting report.checks/status.

    Narrowly qualifies OS-injected Channels source traces, not visible compositor
    frames, physical pointer input, or any other behavioral domain.
    """
    try:
        events = report["events"]
        renders = report["renders"]
        windows = report["windows"]
        if not all(
            isinstance(rows, list) and rows for rows in (events, renders, windows)
        ):
            return "unproven"
        for rows in (events, renders, windows):
            times = [float(row["t"]) for row in rows]
            if not all(math.isfinite(t) and t >= 0 for t in times) or times != sorted(
                times
            ):
                return "unproven"
        press = [e["t"] for e in events if e["phase"] == "press"]
        release = [e["t"] for e in events if e["phase"] == "release"]
        if len(press) != 1 or len(release) != 1 or press[0] >= release[0]:
            return "unproven"
        if not any(r["t"] < press[0] for r in renders) or not any(
            r["t"] > release[0] for r in renders
        ):
            return "unproven"
        pressed = [w for w in windows if w["phase"] == "pressed"]
        released = [w for w in windows if w["phase"] == "released"]
        if len(pressed) < 3 or len(released) < 3:
            return "unproven"
        if (
            max(w["bounds"]["Width"] for w in windows)
            - min(w["bounds"]["Width"] for w in windows)
            < 60
        ):
            return "unproven"
        if report.get("errors") or report.get("dropped_samples", 0):
            return "unproven"
        if requirement == "channels-duplicate-artwork":
            image_count = 0
            overlap = False
            for render in renders:
                images = render["images"]
                image_count += len(images)
                for index, a in enumerate(images):
                    x, y, right, bottom = a["bbox"]
                    for b in images[index + 1 :]:
                        bx, by, br, bb = b["bbox"]
                        overlap |= min(right, br) > max(x, bx) and min(
                            bottom, bb
                        ) > max(y, by)
            return (
                ("detected" if overlap else "not_detected")
                if image_count
                else "unproven"
            )
        if requirement == "resize-live-layout":
            widths = set()
            for row in renders:
                if not press[0] < row["t"] < release[0]:
                    continue
                layout = row.get("layout_width")
                if layout is None:
                    region = str(row.get("scrollregion", "")).split()
                    if len(region) != 4:
                        return "unproven"
                    layout = float(region[2]) - float(region[0])
                if abs(float(layout) - (row["canvas_width"] - 4)) <= 1:
                    widths.add(float(layout))
            return "detected" if len(widths) < 3 else "not_detected"
        if requirement == "resize-release-following-pointer":
            # This establishes post-release movement, not its physical cause.
            shapes = {(w["bounds"]["Width"], w["bounds"]["Height"]) for w in released}
            return "detected" if len(shapes) > 1 else "not_detected"
    except (KeyError, TypeError, ValueError, OverflowError):
        return "unproven"
    return "unproven"
