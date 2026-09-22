from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from .failure_diagnostics import FailureDiagnostic


class MediaPlayerError(RuntimeError):
    """User-facing failure with optional bounded original-provider provenance."""

    def __init__(
        self, message: str, *, diagnostic: FailureDiagnostic | None = None
    ) -> None:
        super().__init__(message)
        self.diagnostic = diagnostic


@dataclass(frozen=True, slots=True)
class VolumeObservation:
    """Provider readback for one desired-state request; never audibility proof."""

    generation: int
    requested: int
    observed: int | None
    disposition: Literal["pending", "applied", "failed"]
    cause: str
    diagnostic: FailureDiagnostic | None = None


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
    volume_observation: VolumeObservation | None = None
    failure_detail: FailureDiagnostic | None = None
    failure_boundary: str = "unknown"
    media_generation: int = 0


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
