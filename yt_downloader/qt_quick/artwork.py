"""Async Qt adapter for the existing LibraryArtworkSource owner."""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl

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
        self._executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="qt-artwork"
        )
        self._cancelled = threading.Event()
        self._pending: dict[str, Future[str]] = {}
        self._ready: dict[str, str] = {}
        self._unavailable: set[str] = set()

    def request(self, record: dict[str, Any]) -> str:
        owner = history_archive_owner(record)
        if not owner:
            return ""
        if owner in self._ready:
            return self._ready[owner]
        if (
            owner in self._unavailable
            or owner in self._pending
            or len(self._pending) >= 16
        ):
            return ""
        self._pending[owner] = self._executor.submit(self._resolve, dict(record))
        return ""

    def _resolve(self, record: dict[str, Any]) -> str:
        asset = self._source.resolve_asset(record, (320, 180), "media", self._cancelled)
        return (
            QUrl.fromLocalFile(str(asset.path)).toString() if asset is not None else ""
        )

    def poll(self) -> bool:
        changed = False
        for owner, future in tuple(self._pending.items()):
            if not future.done():
                continue
            del self._pending[owner]
            try:
                url = future.result()
            except (OSError, RuntimeError, ValueError):
                url = ""
            if url:
                self._ready[owner] = url
                changed = True
            else:
                self._unavailable.add(owner)
        return changed

    def close(self) -> None:
        self._cancelled.set()
        self._source.close()
        self._executor.shutdown(wait=False, cancel_futures=True)
