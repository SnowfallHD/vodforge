from __future__ import annotations

import subprocess  # nosec B404 - fixed argv to trusted bundled FFmpeg
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .platform_services import hidden_window_subprocess_kwargs
from .playback_backend import MediaPlayerError
from .process_lifecycle import ActiveChildProcessRegistry


class MediaPreviewOwner:
    """Own bounded, offline FFmpeg thumbnail extraction outside live playback."""

    def __init__(
        self,
        *,
        ffmpeg: str,
        diagnostic: Callable[[str], None] | None = None,
        popen: Callable[..., Any] = subprocess.Popen,
    ) -> None:
        self.ffmpeg = ffmpeg
        self._popen = popen
        self._registry = ActiveChildProcessRegistry(diagnostic=diagnostic)
        self._lock = threading.RLock()
        self._path: Path | None = None
        self._generation = 0

    def load(self, path: Path) -> None:
        with self._lock:
            self._path = path
            self._generation += 1

    def preview_png(self, position: float) -> bytes:
        with self._lock:
            path = self._path
            generation = self._generation
        if path is None:
            raise MediaPlayerError("Choose a saved Library item first.")
        try:
            process = self._popen(  # nosec B603 - fixed argv to resolved FFmpeg
                [
                    self.ffmpeg,
                    "-nostdin",
                    "-v",
                    "error",
                    "-ss",
                    f"{max(0.0, position):.3f}",
                    "-i",
                    str(path),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=192:108:force_original_aspect_ratio=decrease,pad=192:108:(ow-iw)/2:(oh-ih)/2",
                    "-f",
                    "image2pipe",
                    "-vcodec",
                    "png",
                    "pipe:1",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                **hidden_window_subprocess_kwargs(),
            )
            self._registry.register(process, timeout_seconds=1.0)
            output, _stderr = process.communicate(timeout=12)
        except (OSError, subprocess.SubprocessError) as exc:
            raise MediaPlayerError(
                "A preview thumbnail could not be generated."
            ) from exc
        finally:
            if "process" in locals():
                self._registry.finalize(
                    process,
                    timeout_seconds=1.0,
                    confirmed_exited=process.poll() is not None,
                )
        with self._lock:
            if path != self._path or generation != self._generation:
                raise MediaPlayerError("Preview generation was cancelled.")
        if not output or len(output) > 5 * 1024 * 1024:
            raise MediaPlayerError("A preview thumbnail was invalid.")
        return bytes(output)

    def shutdown(self) -> None:
        with self._lock:
            self._generation += 1
            self._path = None
        self._registry.terminate_all(timeout_seconds=1.5)
