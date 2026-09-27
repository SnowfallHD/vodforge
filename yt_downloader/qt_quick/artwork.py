"""Async Qt adapter for the existing LibraryArtworkSource owner."""

from __future__ import annotations

import hashlib
import io
import json
import math
import threading
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from PySide6.QtCore import QUrl

from yt_downloader.app import (
    THUMBNAIL_MAX_BYTES,
    best_thumbnail_for_download,
    cached_thumbnail_path,
    existing_cached_thumbnail_path,
    save_cached_thumbnail_bytes,
)
from yt_downloader.archive_work import ArchiveWorkOwner
from yt_downloader.history import history_archive_owner, history_output_path
from yt_downloader.library_artwork_source import LibraryArtworkSource
from yt_downloader.private_files import write_private_bytes
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


def _avatar_cache_target(
    source: Path, cache_dir: Path, size: tuple[int, int]
) -> tuple[Path, int] | None:
    try:
        stat = source.stat()
        if not source.is_file() or not 0 < stat.st_size <= 10 * 1024 * 1024:
            return None
        diameter = max(32, min(512, size[0], size[1]))
        identity = (str(source.resolve()), stat.st_size, stat.st_mtime_ns, diameter)
        digest = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
        target = cache_dir / f"avatar-{digest}.png"
        return target, diameter
    except (OSError, ValueError, OverflowError):
        return None


def circular_avatar_asset(
    source: Path, cache_dir: Path, size: tuple[int, int]
) -> Path | None:
    """Cache an uncropped channel image inside a transparent circular avatar."""
    try:
        cached = _avatar_cache_target(source, cache_dir, size)
        if cached is None:
            return None
        target, diameter = cached
        if target.is_file() and target.stat().st_size > 0:
            return target
        with Image.open(source) as opened:
            if opened.width * opened.height > 40_000_000:
                return None
            image = opened.convert("RGBA")
        average = image.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))[:3]
        radius = diameter / 2 - 4
        scale = 2 * radius / math.hypot(image.width, image.height)
        image = image.resize(
            (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
            Image.Resampling.LANCZOS,
        )
        canvas = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
        ImageDraw.Draw(canvas).ellipse(
            (0, 0, diameter - 1, diameter - 1), fill=(*average, 220)
        )
        canvas.alpha_composite(
            image,
            ((diameter - image.width) // 2, (diameter - image.height) // 2),
        )
        output = io.BytesIO()
        canvas.save(output, format="PNG")
        write_private_bytes(target, output.getvalue())
        return target
    except (OSError, ValueError, OverflowError):
        return None


def existing_circular_avatar_asset(
    source: Path, cache_dir: Path, size: tuple[int, int]
) -> Path | None:
    """Find a prepared avatar without decoding or resizing on the UI thread."""
    try:
        cached = _avatar_cache_target(source, cache_dir, size)
        if cached is None:
            return None
        target, _diameter = cached
        return target if target.is_file() and target.stat().st_size > 0 else None
    except (OSError, ValueError, OverflowError):
        return None


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
        self._cached_fallback: dict[str, str] = {}
        self._unavailable: dict[str, float] = {}

    def _private_cached_fallback(self, record: dict[str, Any], key: str) -> str:
        if key in self._cached_fallback:
            return self._cached_fallback[key]
        path = cached_thumbnail_path(record, data_dir=self._source.cache_dir.parent)
        url = ""
        if path is not None:
            try:
                if path.is_file() and 0 < path.stat().st_size <= THUMBNAIL_MAX_BYTES:
                    url = QUrl.fromLocalFile(str(path)).toString()
            except OSError:
                pass
        if url:
            self._cached_fallback[key] = url
        return url

    def _private_cached_avatar_fallback(
        self, record: dict[str, Any], key: str, size: tuple[int, int]
    ) -> str:
        if key in self._cached_fallback:
            return self._cached_fallback[key]
        path = cached_thumbnail_path(record, data_dir=self._source.cache_dir.parent)
        if path is None:
            return ""
        avatar = existing_circular_avatar_asset(
            path, self._source.cache_dir / "avatars", size
        )
        if avatar is None:
            return ""
        url = QUrl.fromLocalFile(str(avatar)).toString()
        self._cached_fallback[key] = url
        return url

    @staticmethod
    def _key(owner: str, size: tuple[int, int], role: str) -> str:
        return f"{owner}\0{role}\0{size[0]}x{size[1]}"

    def state(self, owner: str, size: tuple[int, int], role: str) -> str:
        key = self._key(owner, size, role)
        if key in self._ready or key in self._cached_fallback:
            return "ready"
        if key in self._pending:
            return "pending"
        if self._unavailable.get(key, 0) > time.monotonic():
            return "unavailable"
        return "idle"

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
        key = self._key(owner, size, role)
        if key in self._ready:
            return self._ready[key]
        fallback = (
            self._private_cached_avatar_fallback(record, key, size)
            if role == "avatar"
            else self._private_cached_fallback(record, key)
        )
        if (
            self._unavailable.get(key, 0) > time.monotonic()
            or key in self._pending
            or len(self._pending) >= (16 if role == "media" else 12)
        ):
            return fallback
        self._unavailable.pop(key, None)
        self._pending[key] = (dict(record), size, role)
        self._start_next()
        return fallback

    def _start_next(self) -> None:
        if (
            self._active_key is not None
            or not self._pending
            or self._cancelled.is_set()
        ):
            return
        # Visible media cards take precedence over decorative group artwork.
        # Keep a few queue slots for cards when a page has many channel avatars.
        key, (record, size, role) = next(
            ((key, task) for key, task in self._pending.items() if task[2] == "media"),
            next(iter(self._pending.items())),
        )
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
        if asset is not None and role == "avatar" and not cancelled.is_set():
            avatar = circular_avatar_asset(
                asset.path, self._source.cache_dir / "avatars", size
            )
            return QUrl.fromLocalFile(str(avatar)).toString() if avatar else ""
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
        fallback = self._cached_fallback.get(key, "")
        if result.value and not result.error:
            self._ready[key] = result.value
        else:
            self._unavailable[key] = time.monotonic() + 60
        self._start_next()
        # Repaint only when the presented URL changes. A failed acquisition
        # without fallback must still retire its loading indicator.
        return bool(result.value != fallback or not fallback)

    def close(self) -> None:
        self._cancelled.set()
        self._source.close()
        self._owner.close()
        self._pending.clear()
        self._cached_fallback.clear()
