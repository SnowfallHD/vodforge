"""Bound initial video client geometry without changing resize policy."""

from __future__ import annotations

import math


def initial_player_client_size(
    desired_width: float,
    aspect: float,
    available: tuple[int, int],
    chrome: tuple[int, int],
    minimum: tuple[int, int],
) -> tuple[int, int, bool]:
    values = (desired_width, aspect, *available, *chrome, *minimum)
    if not all(math.isfinite(value) for value in values) or aspect <= 0:
        raise ValueError("Invalid player geometry")
    if desired_width <= 0 or min(available) <= 0 or min(minimum) <= 0:
        raise ValueError("Invalid player geometry bounds")
    maximum_width = min(available[0] - chrome[0], (available[1] - chrome[1]) * aspect)
    minimum_width = max(minimum[0], minimum[1] * aspect)
    width = max(math.ceil(minimum_width), math.floor(min(desired_width, maximum_width)))
    height = round(width / aspect)
    overflow = width + chrome[0] > available[0] or height + chrome[1] > available[1]
    return width, height, overflow


def clamp_player_origin(
    origin: tuple[int, int],
    available: tuple[int, int, int, int],
    margins: tuple[int, int, int, int],
    size: tuple[int, int],
) -> tuple[int, int]:
    left, top, width, height = available
    lower_x, lower_y = left + margins[0], top + margins[1]
    upper_x = left + width - size[0] - margins[2]
    upper_y = top + height - size[1] - margins[3]
    return max(lower_x, min(origin[0], upper_x)), max(lower_y, min(origin[1], upper_y))
