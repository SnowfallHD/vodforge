"""Assess sampled, owned-window pixels while a static native UI is resizing."""

from __future__ import annotations

from itertools import groupby
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops


def _changed_fraction(candidate: Path, reference: Image.Image) -> float:
    with Image.open(candidate) as source:
        image = source.convert("RGB")
    if image.size != reference.size:
        raise ValueError("Resize frame size changed without a matching bounds record")
    width, height = image.size
    if width < 80 or height < 100:
        raise ValueError("Resize frame is too small for an interior paint check")
    interior = (20, 60, width - 20, height - 20)
    delta = ImageChops.difference(
        image.crop(interior), reference.crop(interior)
    ).convert("L")
    changed = delta.point(lambda value: 255 if value > 25 else 0)
    return sum(changed.histogram()[1:]) / (delta.width * delta.height)


def assess_static_resize_frames(
    frames: list[dict[str, Any]],
    directory: Path,
    *,
    drag_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fail delayed multi-control repaint while native bounds are unchanged.

    The Forge QA fixture is idle and static. Cursor blinking and edge movement
    occupy much less than two percent of its inner surface. A frame still more
    than two percent different 200 ms after a geometry step is incomplete.
    These are sampled PrintWindow images, not physical display presentation.
    """
    if not frames:
        return {"passed": False, "reason": "No in-flight window pixels captured"}
    drag_changes = []
    if drag_events is not None:
        starts = [row for row in drag_events if row["event"] == "drag_start"]
        ends = [row for row in drag_events if row["event"] == "drag_end"]
        drag_changes = [
            abs(end["rect"][2] - start["rect"][2])
            for start, end in zip(starts, ends, strict=False)
        ]
        if len(drag_changes) < 2 or any(change < 80 for change in drag_changes):
            return {
                "passed": False,
                "reason": "Native drag did not move the owned window enough",
                "drag_width_changes": drag_changes,
            }
    if len({tuple(row["bounds"]) for row in frames}) < 4:
        return {"passed": False, "reason": "Too few distinct in-flight window sizes"}
    examined = []
    for bounds, rows_iter in groupby(frames, key=lambda row: tuple(row["bounds"])):
        rows = list(rows_iter)
        if len(rows) < 4 or rows[-1]["begin"] - rows[0]["begin"] < 0.3:
            continue
        with Image.open(directory / rows[-1]["file"]) as source:
            reference = source.convert("RGB")
        lagging = []
        for row in rows:
            age = row["begin"] - rows[0]["begin"]
            if age < 0.2:
                continue
            fraction = _changed_fraction(directory / row["file"], reference)
            if fraction > 0.02:
                lagging.append({"age_ms": round(age * 1000), "fraction": fraction})
        examined.append(
            {
                "bounds": list(bounds),
                "samples": len(rows),
                "duration_ms": round((rows[-1]["begin"] - rows[0]["begin"]) * 1000),
                "lagging": lagging,
            }
        )
    if not examined:
        return {"passed": False, "reason": "No sustained geometry epoch captured"}
    return {
        "passed": not any(row["lagging"] for row in examined),
        "epochs": examined,
        "drag_width_changes": drag_changes,
        "scope": "sampled own-window server pixels; static Forge fixture",
    }
