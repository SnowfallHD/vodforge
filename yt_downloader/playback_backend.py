from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable


class MediaPlayerError(RuntimeError):
    """Raised when an internal media backend cannot satisfy playback safely."""


PlaybackStatus = Literal[
    "Idle",
    "Ready",
    "Starting",
    "Playing",
    "Paused",
    "Stopped",
    "Ended",
    "Failed",
    "Closed",
]
RenderSurfaceKind = Literal["hwnd", "nsview"]


@dataclass(frozen=True, slots=True)
class PlaybackSnapshot:
    """Immutable rendering value derived from the media engine's current state."""

    path: Path | None
    status: PlaybackStatus
    position: float
    duration: float
    volume: int
    error: str = ""


@dataclass(frozen=True, slots=True)
class NativeRenderSurface:
    """One platform-native child surface owned by the player window."""

    kind: RenderSurfaceKind
    handle: int


@runtime_checkable
class PlaybackBackend(Protocol):
    """Single-engine playback contract consumed by VODForge-owned UI."""

    @property
    def snapshot(self) -> PlaybackSnapshot: ...

    def attach_render_surface(self, surface: NativeRenderSurface) -> None: ...

    def detach_render_surface(self) -> None: ...

    def load(
        self,
        path: Path,
        *,
        duration: float | None = None,
        audio_only: bool | None = None,
    ) -> PlaybackSnapshot: ...

    def play(self) -> PlaybackSnapshot: ...

    def pause(self) -> PlaybackSnapshot: ...

    def toggle(self) -> PlaybackSnapshot: ...

    def seek(self, position: float) -> PlaybackSnapshot: ...

    def set_volume(self, value: int) -> PlaybackSnapshot: ...

    def stop(self) -> PlaybackSnapshot: ...

    def shutdown(self) -> None: ...
