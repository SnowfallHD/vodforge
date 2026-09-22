from __future__ import annotations

import math
import subprocess  # nosec B404 - fixed argv to trusted bundled FFmpeg
import threading
import time
from collections import OrderedDict
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
        self._extraction_lock = threading.Lock()
        self._path: Path | None = None
        self._generation = 0
        self._identity: tuple[int, ...] | None = None
        self._cache: OrderedDict[tuple[int, float], bytes] = OrderedDict()

    def load(self, path: Path) -> None:
        try:
            stat = path.stat()
        except OSError as exc:
            raise MediaPlayerError(
                "The saved media is unavailable for preview."
            ) from exc
        identity = (
            stat.st_dev,
            stat.st_ino,
            stat.st_size,
            stat.st_mtime_ns,
            stat.st_ctime_ns,
        )
        with self._lock:
            self._path = path
            self._identity = identity
            self._generation += 1
            self._cache.clear()

    def preview_png(
        self,
        position: float,
        *,
        cancel: threading.Event | None = None,
        expected_path: Path | None = None,
    ) -> bytes:
        if not math.isfinite(position):
            raise MediaPlayerError("That preview position is unavailable.")
        while not self._extraction_lock.acquire(timeout=0.05):
            if cancel is not None and cancel.is_set():
                raise MediaPlayerError("Preview generation was cancelled.")
        try:
            return self._extract_png(
                position, cancel=cancel, expected_path=expected_path
            )
        finally:
            self._extraction_lock.release()

    def _extract_png(
        self,
        position: float,
        *,
        cancel: threading.Event | None,
        expected_path: Path | None,
    ) -> bytes:
        with self._lock:
            path = self._path
            generation = self._generation
            loaded_identity = self._identity
        if cancel is not None and cancel.is_set():
            raise MediaPlayerError("Preview generation was cancelled.")
        if path is None:
            raise MediaPlayerError("Choose a saved Library item first.")
        if expected_path is not None and path != expected_path:
            raise MediaPlayerError("Preview generation was cancelled.")
        try:
            before = path.stat()
            identity = (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            if identity != loaded_identity:
                raise MediaPlayerError(
                    "The saved media changed. Open it again to preview."
                )
            key = (generation, max(0.0, position))
            with self._lock:
                cached = self._cache.get(key)
                if cached is not None:
                    self._cache.move_to_end(key)
                    return cached
            process = self._popen(  # nosec B603 - fixed argv to resolved FFmpeg
                [
                    self.ffmpeg,
                    "-nostdin",
                    "-v",
                    "error",
                    "-ss",
                    f"{max(0.0, position):.3f}",
                    "-protocol_whitelist",
                    "file,pipe",
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
            # Popen may return after shutdown or replacement has invalidated
            # this request. Reject/reap that child before any communicate work.
            # Registration shares the generation lock with shutdown admission;
            # the potentially slow Popen itself never holds the UI-facing lock.
            with self._lock:
                if (
                    generation != self._generation
                    or path != self._path
                    or (cancel is not None and cancel.is_set())
                ):
                    raise MediaPlayerError("Preview generation was cancelled.")
                self._registry.register(process, timeout_seconds=1.0)
            if cancel is None:
                output, _stderr = process.communicate(timeout=12)
            else:
                deadline = time.monotonic() + 12
                while True:
                    if cancel.is_set():
                        raise MediaPlayerError("Preview generation was cancelled.")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired("preview", 12)
                    try:
                        output, _stderr = process.communicate(
                            timeout=min(0.1, remaining)
                        )
                        break
                    except subprocess.TimeoutExpired:
                        continue
            if process.poll() != 0:
                raise MediaPlayerError("A preview thumbnail could not be generated.")
            after = path.stat()
            if identity != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                raise MediaPlayerError(
                    "The saved media changed while creating a preview."
                )
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
        if cancel is not None and cancel.is_set():
            raise MediaPlayerError("Preview generation was cancelled.")
        data = bytes(output)
        with self._lock:
            if len(data) <= 256 * 1024 and generation == self._generation:
                self._cache[key] = data
                self._cache.move_to_end(key)
                while len(self._cache) > 24:
                    self._cache.popitem(last=False)
        return data

    def shutdown(self) -> None:
        with self._lock:
            self._generation += 1
            self._path = None
            self._cache.clear()
        self._registry.terminate_all(timeout_seconds=1.5)
