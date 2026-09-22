"""Choose usable local artwork for each presentation role, off the UI thread."""

from __future__ import annotations

import hashlib
import io
import json
import math
import subprocess  # nosec B404 - fixed local FFmpeg command
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from .channel_artwork import ChannelArtworkOwner
from .platform_services import find_runtime_executable, hidden_window_subprocess_kwargs
from .private_files import write_private_bytes

MAX_ARTWORK_BYTES = 10 * 1024 * 1024
MAX_ARTWORK_PIXELS = 40_000_000


@dataclass(frozen=True)
class ArtworkAsset:
    path: Path
    kind: str


class LibraryArtworkSource:
    """One bounded local-frame extractor shared by Library and Watch."""

    def __init__(
        self,
        cache_dir: Path,
        *,
        thumbnail_path: Callable[[dict[str, Any]], Path | None],
        media_path: Callable[[dict[str, Any]], Path | None],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cache_dir = cache_dir
        self._thumbnail_path, self._media_path = thumbnail_path, media_path
        self._clock = clock
        self._lock = threading.Lock()
        self._closed = threading.Event()
        self._negative: OrderedDict[str, float] = OrderedDict()
        self.channels = ChannelArtworkOwner(cache_dir / "channels")

    def resolve_asset(
        self,
        record: dict[str, Any],
        size: tuple[int, int],
        role: str,
        cancelled: threading.Event,
    ) -> ArtworkAsset | None:
        role_field = {
            "avatar": "channel_avatar_path",
            "banner": "channel_banner_path",
        }.get(role)
        if role_field and not record.get(role_field):
            profile_path = self.channels.resolve(record, role, cancelled)
            if profile_path is not None:
                return ArtworkAsset(profile_path, "channel_" + role)
        path = self.resolve(record, size, role, cancelled)
        if path is None:
            return None
        if path.parent == self.cache_dir and path.name.startswith("frame-"):
            kind = (
                "embedded_art"
                if str(record.get("vodforge_output_type") or "").casefold()
                in {"mp3", "original audio"}
                else "local_frame"
            )
        elif role == "avatar" and str(path) == record.get("channel_avatar_path"):
            kind = "channel_avatar"
        elif role == "banner" and str(path) == record.get("channel_banner_path"):
            kind = "channel_banner"
        else:
            kind = "thumbnail"
        return ArtworkAsset(path, kind)

    def close(self) -> None:
        self._closed.set()
        self.channels.close()

    @staticmethod
    def _size(path: Path) -> tuple[int, int] | None:
        try:
            if not path.is_file() or not 0 < path.stat().st_size <= MAX_ARTWORK_BYTES:
                return None
            with Image.open(path) as source:
                if source.width * source.height > MAX_ARTWORK_PIXELS:
                    return None
                return source.size
        except (OSError, ValueError):
            return None

    def _best(
        self, candidates: list[Path], size: tuple[int, int]
    ) -> tuple[Path | None, float]:
        best, quality = None, 0.0
        for path in dict.fromkeys(candidates):
            dimensions = self._size(path)
            if dimensions is not None:
                coverage = min(
                    dimensions[0] / max(1, size[0]), dimensions[1] / max(1, size[1])
                )
                if coverage > quality:
                    best, quality = path, coverage
        return best, quality

    def resolve(
        self,
        record: dict[str, Any],
        size: tuple[int, int],
        role: str,
        cancelled: threading.Event,
    ) -> Path | None:
        if self._closed.is_set() or cancelled.is_set():
            return None
        # Role-specific local metadata must never mistake a wide channel banner
        # for the creator avatar. A provider profile resolver can supply these.
        role_field = {
            "avatar": "channel_avatar_path",
            "banner": "channel_banner_path",
        }.get(role)
        if role_field and record.get(role_field):
            role_path = Path(str(record[role_field]))
            if self._size(role_path):
                return role_path
        candidates = []
        fallback = self._thumbnail_path(record)
        if fallback is not None:
            candidates.append(fallback)
        directory = str(record.get("vodforge_output_dir") or "")
        if directory:
            candidates.extend(
                Path(directory) / ("thumbnail." + suffix)
                for suffix in ("jpg", "jpeg", "png", "webp")
            )
        best, coverage = self._best(candidates, size)
        if coverage >= 1:
            return best
        media = self._media_path(record)
        if media is None:
            return best
        # Acquisition is serialized across views. Waiting jobs remain cancellable.
        while not self._lock.acquire(timeout=0.1):
            if self._closed.is_set() or cancelled.is_set():
                return best
        try:
            if self._closed.is_set() or cancelled.is_set():
                return best
            frame = self._frame(record, media, cancelled)
            return self._best([p for p in (best, frame) if p is not None], size)[0]
        finally:
            self._lock.release()

    def _frame(
        self, record: dict[str, Any], media: Path, cancelled: threading.Event
    ) -> Path | None:
        try:
            media = media.resolve(strict=True)
            stat = media.stat()
            if not media.is_file() or stat.st_size <= 0:
                return None
        except OSError:
            return None
        identity = (
            str(media),
            stat.st_dev,
            stat.st_ino,
            stat.st_size,
            stat.st_mtime_ns,
        )
        key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
        target = self.cache_dir / ("frame-" + key + ".jpg")
        if self._size(target):
            return target
        if self._negative.get(key, 0) > self._clock():
            return None
        self._negative.pop(key, None)

        def unavailable(delay: float = 300) -> None:
            self._negative[key] = self._clock() + delay
            self._negative.move_to_end(key)
            while len(self._negative) > 256:
                self._negative.popitem(last=False)

        executable = find_runtime_executable("ffmpeg")
        if not executable:
            unavailable(30)
            return None
        audio = str(record.get("vodforge_output_type") or "").casefold() in {
            "mp3",
            "original audio",
        }
        try:
            duration = float(record.get("duration") or 0)
        except (TypeError, ValueError, OverflowError):
            duration = 0.0
        position = (
            min(8.0, max(0.0, duration * 0.1)) if math.isfinite(duration) else 0.0
        )
        command = [
            executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-protocol_whitelist",
            "file,pipe",
            *([] if audio else ["-ss", f"{position:.3f}"]),
            "-i",
            str(media),
            "-map",
            "0:v:0" if audio else "0:V:0",
            "-frames:v",
            "1",
            "-an",
            "-sn",
            "-dn",
            "-vf",
            "scale='min(2048,iw)':'min(2048,ih)':force_original_aspect_ratio=decrease",
            "-threads",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "-q:v",
            "2",
            "-",
        ]
        process = None
        try:
            process = subprocess.Popen(  # nosec B603 - fixed argv; no shell or remote protocols
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                **hidden_window_subprocess_kwargs(),
            )
            deadline = time.monotonic() + 4
            while True:
                abandoned = cancelled.is_set() or self._closed.is_set()
                if abandoned or time.monotonic() >= deadline:
                    process.kill()
                    process.communicate(timeout=2)
                    if not abandoned:
                        unavailable(15)
                    return None
                try:
                    data, _ = process.communicate(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if process.returncode or not 0 < len(data) <= MAX_ARTWORK_BYTES:
                unavailable()
                return None
            with Image.open(io.BytesIO(data)) as source:
                if source.width * source.height > MAX_ARTWORK_PIXELS:
                    unavailable()
                    return None
                source.verify()
            after = media.stat()
            if identity[1:] != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                return None
            if cancelled.is_set() or self._closed.is_set():
                return None
            self.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            write_private_bytes(target, data)
            self._prune()
            return target
        except (OSError, ValueError, subprocess.SubprocessError):
            if not cancelled.is_set() and not self._closed.is_set():
                unavailable(30)
            return None
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate(timeout=2)

    def _prune(self) -> None:
        # Delete only this owner's generated cache entries, never media or sidecars.
        try:
            files = sorted(
                self.cache_dir.glob("frame-*.jpg"),
                key=lambda path: path.stat().st_mtime_ns,
                reverse=True,
            )
            total = 0
            for index, path in enumerate(files):
                total += path.stat().st_size
                if index >= 128 or total > 256 * 1024 * 1024:
                    path.unlink()
        except OSError:
            return
