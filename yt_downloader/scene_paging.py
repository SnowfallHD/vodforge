"""Bounded scene pages that keep every matching record reachable."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ScenePage(Generic[T]):
    items: tuple[T, ...]
    index: int
    count: int
    total: int


def scene_page(items: Sequence[T], index: int, limit: int) -> ScenePage[T]:
    if limit <= 0:
        raise ValueError("A page must have room for at least one item.")
    count = max(1, (len(items) + limit - 1) // limit)
    index = min(max(0, index), count - 1)
    return ScenePage(
        tuple(items[index * limit : (index + 1) * limit]), index, count, len(items)
    )


def visible_scene_rows(
    count: int,
    columns: int,
    row_height: int,
    content_top: int,
    scroll_top: float,
    viewport_height: int,
    *,
    overscan: int = 1,
) -> tuple[int, int]:
    """Half-open row window; item count never depends on total catalog length."""
    if columns < 1 or row_height < 1 or overscan < 0:
        raise ValueError(
            "A scene window needs positive geometry and nonnegative overscan."
        )
    rows = max(0, math.ceil(count / columns))
    if not rows:
        return 0, 0
    if overscan == 0:
        if scroll_top + max(1, viewport_height) <= content_top:
            return 0, 0
        if scroll_top >= content_top + rows * row_height:
            return rows, rows
    first = min(
        rows - 1, max(0, math.floor((scroll_top - content_top) / row_height) - overscan)
    )
    last = min(
        rows,
        max(
            first + 1,
            math.ceil((scroll_top + max(1, viewport_height) - content_top) / row_height)
            + overscan,
        ),
    )
    return first, last
