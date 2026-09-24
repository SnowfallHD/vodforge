"""Async Qt adapter for the existing LibraryArtworkSource owner."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl

from yt_downloader.app import (
    best_thumbnail_for_download,
    existing_cached_thumbnail_path,
    save_cached_thumbnail_bytes,
)
from yt_downloader.archive_work import ArchiveWorkOwner
from yt_downloader.history import history_archive_owner, history_output_path
from yt_downloader.library_artwork_source import LibraryArtworkSource
from yt_downloader.thumbnail_network import download_bounded_url_bytes


def thumbnail_path(
    record: dict[str, Any], *, data_dir: Path | None = None
) -> Path | None:
    preview = str(record.get("preview_thumbnail_path") or "").strip()
    if preview:
        path = Path(preview)
        if path.is_file():
            return path
    return existing_cached_thumbnail_path(record, data_dir=data_dir)


class QtArtwork:
    """Bounded background acquisition; QML only sees completed local URLs."""

    def __init__(self, cache_dir: Path) -> None:
        self._source = LibraryArtworkSource(
            cache_dir,
            thumbnail_path=lambda record: thumbnail_path(
                record, data_dir=cache_dir.parent
            ),
            media_path=history_output_path,
        )
        # Tk and Qt share the filesystem lane: a blocked OS open cannot hold
        # Python's non-daemon executor shutdown after the window closes.
        self._owner = ArchiveWorkOwner()
        self._cancelled = threading.Event()
        self._pending: dict[str, tuple[dict[str, Any], tuple[int, int], str]] = {}
        self._active_key: str | None = None
        self._ready: dict[str, str] = {}
        self._unavailable: dict[str, float] = {}

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
        if (
            self._unavailable.get(key, 0) > time.monotonic()
            or key in self._pending
            or len(self._pending) >= 16
        ):
            return ""
        self._unavailable.pop(key, None)
        self._pending[key] = (dict(record), size, role)
        self._start_next()
        return ""

    def _start_next(self) -> None:
        if (
            self._active_key is not None
            or not self._pending
            or self._cancelled.is_set()
        ):
            return
        key, (record, size, role) = next(iter(self._pending.items()))
        if (
            self._owner.submit(
                "qt_artwork",
                lambda cancelled: self._resolve(record, size, role, cancelled),
            )
            is not None
        ):
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
        if asset is None and role == "hero" and not cancelled.is_set():
            thumbnail = best_thumbnail_for_download(record)
            url = str((thumbnail or {}).get("url") or "").strip()
            if url:
                try:
                    data = download_bounded_url_bytes(
                        url,
                        source_url=str(record.get("webpage_url") or "") or None,
                        timeout_seconds=15,
                    )
                    if not cancelled.is_set():
                        path = save_cached_thumbnail_bytes(
                            record, data, data_dir=self._source.cache_dir.parent
                        )
                        if path is not None:
                            return QUrl.fromLocalFile(str(path)).toString()
                except (OSError, RuntimeError, ValueError):
                    pass
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
            self._unavailable[key] = time.monotonic() + 60
        self._start_next()
        return bool(result.value and not result.error)

    def close(self) -> None:
        self._cancelled.set()
        self._source.close()
        self._owner.close()
        self._pending.clear()
