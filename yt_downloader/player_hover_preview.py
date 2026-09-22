"""Latest-intent hover previews reuse the existing offline preview owner."""

from __future__ import annotations

import math
import threading
import time
from pathlib import Path
from typing import Any

from .playback_backend import MediaPlayerError

MAX_PREVIEW_BYTES = 256 * 1024


class PlayerHoverPreview:
    """One lazy worker, one pending intent, one result; the preview owner retains cache authority."""

    def __init__(self, previews: Any, *, debounce: float = 0.15) -> None:
        self.previews = previews
        self._debounce = debounce
        self._condition = threading.Condition()
        self._closed = False
        self._generation = 0
        self._request: tuple[Path, int] | None = None
        self._pending: tuple[int, Path, int, float] | None = None
        self._result: tuple[int, float, bytes | None] | None = None
        self._cancel: threading.Event | None = None
        self._worker: threading.Thread | None = None

    def request(self, path: Path, position: float) -> None:
        if not math.isfinite(position) or position < 0:
            self.hide()
            return
        request = (path, int(position))
        with self._condition:
            if self._closed or request == self._request:
                return
            self._request = request
            self._generation += 1
            self._result = None
            if self._cancel is not None:
                self._cancel.set()
            self._pending = (self._generation, *request, time.monotonic())
            if self._worker is None:
                self._worker = threading.Thread(
                    target=self._run, daemon=True, name="vodforge-hover-preview"
                )
                self._worker.start()
            self._condition.notify()

    def hide(self) -> None:
        with self._condition:
            self._generation += 1
            self._request = None
            self._pending = None
            self._result = None
            if self._cancel is not None:
                self._cancel.set()
            self._condition.notify()

    def poll(self) -> tuple[float, bytes | None] | None:
        with self._condition:
            value, self._result = self._result, None
            if value is not None and not self._closed and value[0] == self._generation:
                return value[1], value[2]
        return None

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self.hide()
            self._condition.notify()

    def _run(self) -> None:
        while True:
            with self._condition:
                while self._pending is None and not self._closed:
                    self._condition.wait()
                if self._closed:
                    return
                if self._pending is None:
                    continue
                generation, path, second, requested = self._pending
                remaining = self._debounce - (time.monotonic() - requested)
                if remaining > 0:
                    self._condition.wait(remaining)
                    continue
                self._pending = None
                cancel = self._cancel = threading.Event()
            data = None
            try:
                stat = path.stat()
                identity = (
                    str(path),
                    stat.st_dev,
                    stat.st_ino,
                    stat.st_size,
                    stat.st_mtime_ns,
                    stat.st_ctime_ns,
                )
                data = self.previews.preview_png(
                    second, cancel=cancel, expected_path=path
                )
                current = path.stat()
                if identity[1:] != (
                    current.st_dev,
                    current.st_ino,
                    current.st_size,
                    current.st_mtime_ns,
                    current.st_ctime_ns,
                ):
                    data = None
                if data is not None and (
                    not data.startswith(b"\x89PNG\r\n\x1a\n")
                    or len(data) > MAX_PREVIEW_BYTES
                ):
                    data = None
            except (OSError, MediaPlayerError):
                data = None
            with self._condition:
                if (
                    not self._closed
                    and generation == self._generation
                    and not cancel.is_set()
                ):
                    self._result = (generation, float(second), data)
