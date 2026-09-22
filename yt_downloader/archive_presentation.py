"""Shared Canvas geometry for Archive and Watch presentation."""

from __future__ import annotations

from typing import Any


def rounded_surface(
    canvas: Any,
    bounds: tuple[float, float, float, float],
    *,
    radius: int = 8,
    **options: Any,
) -> int:
    x1, y1, x2, y2 = bounds
    radius = min(radius, int((x2 - x1) / 2), int((y2 - y1) / 2))
    points = (
        x1 + radius,
        y1,
        x2 - radius,
        y1,
        x2,
        y1,
        x2,
        y1 + radius,
        x2,
        y2 - radius,
        x2,
        y2,
        x2 - radius,
        y2,
        x1 + radius,
        y2,
        x1,
        y2,
        x1,
        y2 - radius,
        x1,
        y1 + radius,
        x1,
        y1,
    )
    return int(canvas.create_polygon(*points, smooth=True, splinesteps=16, **options))


def media_badge(
    canvas: Any,
    label: str,
    *,
    right: float,
    bottom: float,
    maximum_width: float,
    font: Any,
    fill: str,
    foreground: str,
) -> tuple[int, int]:
    """Fit the actual Tk text ink inside a small, inset thumbnail label."""
    import tkinter.font as tkfont

    from .ui_layout import ellipsize_wrapped_text

    padding_x, padding_y = 8, 4
    measured = tkfont.Font(root=canvas, font=font)
    text = ellipsize_wrapped_text(
        str(label)[:2000],
        maximum_width=max(1, int(maximum_width) - 2 * padding_x - 2),
        maximum_lines=1,
        measure_width=measured.measure,
    )
    item = canvas.create_text(
        0,
        0,
        text=text,
        font=font,
        fill=foreground,
        anchor="nw",
        tags=("media-badge-text",),
    )
    ink = canvas.bbox(item)
    if ink is None:
        return item, item
    width, height = ink[2] - ink[0], ink[3] - ink[1]
    canvas.move(
        item, right - padding_x - width - ink[0], bottom - padding_y - height - ink[1]
    )
    plate = rounded_surface(
        canvas,
        (right - width - 2 * padding_x, bottom - height - 2 * padding_y, right, bottom),
        radius=4,
        fill=fill,
        outline="",
        tags=("media-badge-plate",),
    )
    canvas.tag_lower(plate, item)
    return plate, item
