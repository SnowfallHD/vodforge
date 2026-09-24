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

    def request(
        self,
        record: dict[str, Any],
        size: tuple[int, int] = (320, 180),
        role: str = "media",
    ) -> str:
        owner = history_archive_owner(record)
        if not owner:
            return ""
        key = f"{owner}\0{role}\0{size[0]}x{size[1]}"
        if key in self._ready:
            return self._ready[key]
        if key in self._unavailable or key in self._pending or len(self._pending) >= 16:
            return ""
        self._pending[key] = self._executor.submit(
            self._resolve, dict(record), size, role
        )
        return ""

    def channel_profile(self, record: dict[str, Any]) -> dict[str, str]:
        return self._source.channels.snapshot(record)

    def _resolve(self, record: dict[str, Any], size: tuple[int, int], role: str) -> str:
        asset = self._source.resolve_asset(record, size, role, self._cancelled)
        return (
            QUrl.fromLocalFile(str(asset.path)).toString() if asset is not None else ""
        )

    def poll(self) -> bool:
        changed = False
        for key, future in tuple(self._pending.items()):
            if not future.done():
                continue
            del self._pending[key]
            try:
                url = future.result()
            except (OSError, RuntimeError, ValueError):
                url = ""
            if url:
                self._ready[key] = url
                changed = True
            else:
                self._unavailable.add(key)
        return changed

    def close(self) -> None:
        self._cancelled.set()
        self._source.close()
        self._executor.shutdown(wait=False, cancel_futures=True)
