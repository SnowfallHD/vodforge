"""Async Qt adapter for the existing LibraryArtworkSource owner."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl

from yt_downloader.archive_work import ArchiveWorkOwner
from yt_downloader.history import history_archive_owner, history_output_path
from yt_downloader.library_artwork_source import LibraryArtworkSource


def thumbnail_path(record: dict[str, Any]) -> Path | None:
    preview = str(record.get("preview_thumbnail_path") or "").strip()
    if not preview:
        return None
    path = Path(preview)
    return path if path.is_file() else None


class QtArtwork:
    """Bounded background acquisition; QML only sees completed local URLs."""

    def __init__(self, cache_dir: Path) -> None:
        self._source = LibraryArtworkSource(
            cache_dir, thumbnail_path=thumbnail_path, media_path=history_output_path
        )
        # Tk and Qt share the filesystem lane: a blocked OS open cannot hold
        # Python's non-daemon executor shutdown after the window closes.
        self._owner = ArchiveWorkOwner()
        self._cancelled = threading.Event()
        self._pending: dict[str, tuple[dict[str, Any], tuple[int, int], str]] = {}
        self._active_key: str | None = None
        self._ready: dict[str, str] = {}
        self._unavailable: set[str] = set()

    def request(
        self,
        record: dict[str, Any],
        size: tuple[int, int] = (320, 180),
        role: str = "media",
    ) -> str:
        if self._cancelled.is_set():
            return ""
        owner = history_archive_owner(record)
        if not owner:
            return ""
        key = f"{owner}\0{role}\0{size[0]}x{size[1]}"
        if key in self._ready:
            return self._ready[key]
        if key in self._unavailable or key in self._pending or len(self._pending) >= 16:
            return ""
        self._pending[key] = (dict(record), size, role)
        self._start_next()
        return ""

    def _start_next(self) -> None:
        if self._active_key is not None or not self._pending or self._cancelled.is_set():
            return
        key, (record, size, role) = next(iter(self._pending.items()))
        if self._owner.submit(
            "qt_artwork",
            lambda cancelled: self._resolve(record, size, role, cancelled),
        ) is not None:
            self._active_key = key

    def channel_profile(self, record: dict[str, Any]) -> dict[str, str]:
        return self._source.channels.snapshot(record)

    def _resolve(
        self,
        record: dict[str, Any],
        size: tuple[int, int],
        role: str,
        cancelled: threading.Event,
    ) -> str:
        asset = self._source.resolve_asset(record, size, role, cancelled)
        return (
            QUrl.fromLocalFile(str(asset.path)).toString() if asset is not None else ""
        )

    def poll(self) -> bool:
        if self._cancelled.is_set():
            return False
        result = self._owner.poll()
        if result is None or self._active_key is None:
            return False
        key = self._active_key
        self._active_key = None
        self._pending.pop(key, None)
        if result.value and not result.error:
            self._ready[key] = result.value
        else:
            self._unavailable.add(key)
        self._start_next()
        return bool(result.value and not result.error)

    def close(self) -> None:
        self._cancelled.set()
        self._source.close()
        self._owner.close()
        self._pending.clear()
