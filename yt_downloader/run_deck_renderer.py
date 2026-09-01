from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any


@dataclass(frozen=True)
class RunDeckTileSnapshot:
    """Immutable render facts for one visible Run Deck tile."""

    structure: tuple[Any, ...]
    status: str
    progress: float


@dataclass(frozen=True)
class RunDeckSnapshot:
    """One immutable Run Deck surface snapshot."""

    layout: str
    capacity: int
    tiles: tuple[RunDeckTileSnapshot, ...]
    summary_text: str
    overflow_text: str
    overflow_visible: bool

    @property
    def structure(self) -> tuple[Any, ...]:
        return (
            self.layout,
            self.capacity,
            tuple(tile.structure for tile in self.tiles),
        )


class RunDeckRenderResult(Enum):
    NOOP = "noop"
    PATCHED = "patched"
    REBUILT = "rebuilt"


class RunDeckRenderOwner:
    """Choose the minimum Run Deck render work for one committed snapshot."""

    def __init__(self) -> None:
        self._snapshot: RunDeckSnapshot | None = None

    @property
    def snapshot(self) -> RunDeckSnapshot | None:
        return self._snapshot

    def render(
        self,
        snapshot: RunDeckSnapshot,
        *,
        patch_values: Callable[[RunDeckSnapshot, RunDeckSnapshot], None],
        rebuild: Callable[[RunDeckSnapshot], None],
    ) -> RunDeckRenderResult:
        previous = self._snapshot
        if previous == snapshot:
            return RunDeckRenderResult.NOOP
        if previous is not None and previous.structure == snapshot.structure:
            patch_values(previous, snapshot)
            result = RunDeckRenderResult.PATCHED
        else:
            rebuild(snapshot)
            result = RunDeckRenderResult.REBUILT
        self._snapshot = snapshot
        return result
