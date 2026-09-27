"""Qt event and image handoff for the existing offline media preview owner."""

from __future__ import annotations

import math
import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

from yt_downloader.archive_work import ArchiveWorkOwner
from yt_downloader.media_preview import MediaPreviewOwner
from yt_downloader.playback_backend import MediaPlayerError


class PreviewImages(QQuickImageProvider):
    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.Image)
        self._lock = threading.RLock()
        self._images: dict[str, QImage] = {}

    def clear(self) -> None:
        with self._lock:
            self._images.clear()

    def put(self, key: str, data: bytes) -> bool:
        # PySide6's runtime binding accepts the format name as str here even
        # though its current type stub advertises bytes.
        image = QImage.fromData(data, "PNG")  # type: ignore[arg-type]
        if image.isNull() or image.width() > 512 or image.height() > 512:
            return False
        with self._lock:
            self._images[key] = image
            while len(self._images) > 4:
                self._images.pop(next(iter(self._images)))
        return True

    def requestImage(self, image_id: str, size: QSize, requested_size: QSize) -> QImage:
        del requested_size
        with self._lock:
            image = self._images.get(image_id)
        if image is None:
            size.setWidth(1)
            size.setHeight(1)
            empty = QImage(1, 1, QImage.Format_ARGB32_Premultiplied)
            empty.fill(Qt.GlobalColor.transparent)
            return empty
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image


class QtPreviewSession:
    """One current media identity and one latest seek-hover frame."""

    def __init__(
        self,
        ffmpeg: str | None,
        *,
        owner: MediaPreviewOwner | None = None,
    ) -> None:
        self.images = PreviewImages()
        self._owner = owner or (MediaPreviewOwner(ffmpeg=ffmpeg) if ffmpeg else None)
        self._work = ArchiveWorkOwner()
        self._path: Path | None = None
        self._generation = 0
        self._duration = 0.0
        self._desired_position: float | None = None
        self._active_position: float | None = None
        self._image_version = 0
        self._records: list[dict[str, Any]] = []
        self._closed = False

    @property
    def records(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._records]

    def load(self, path: Path | None) -> None:
        self._generation += 1
        self._work.cancel()
        self.images.clear()
        self._path = None
        self._duration = 0.0
        self._desired_position = None
        self._active_position = None
        self._records = []
        if self._closed or self._owner is None or path is None:
            return
        try:
            self._owner.load(path)
        except MediaPlayerError:
            return
        self._path = path

    def request(self, duration: float) -> bool:
        if (
            self._closed
            or self._path is None
            or not math.isfinite(duration)
            or not 0 < duration < 48 * 60 * 60
        ):
            return False
        rounded = round(duration, 3)
        if rounded == self._duration:
            return False
        self._duration = rounded
        self._generation += 1
        self._work.cancel()
        self.images.clear()
        self._records = []
        self._desired_position = None
        self._active_position = None
        return True

    def hover(self, position: float) -> bool:
        if (
            self._closed
            or self._path is None
            or self._duration <= 0
            or not math.isfinite(position)
        ):
            return False
        position = round(min(max(0.0, position), self._duration), 1)
        if (
            self._desired_position is not None
            and abs(self._desired_position - position) < 0.25
        ):
            return False
        if (
            self._desired_position is None
            and self._records
            and abs(self._records[0]["position"] - position) < 0.25
        ):
            return False
        self._desired_position = position
        if not self._records:
            self._records = [
                {"position": position, "image": "", "status": "Loading preview…"}
            ]
        self._start()
        return True

    def _start(self) -> None:
        owner = self._owner
        path = self._path
        position = self._desired_position
        if position is None or owner is None or path is None or self._work.busy:
            return
        if (
            self._records
            and self._records[0]["image"]
            and abs(self._records[0]["position"] - position) < 0.25
        ):
            return

        def work(cancelled: threading.Event) -> bytes | None:
            if cancelled.is_set():
                return None
            try:
                return owner.preview_png(position, cancel=cancelled, expected_path=path)
            except MediaPlayerError:
                return None

        if self._work.submit("player_previews", work) is not None:
            self._active_position = position

    def poll(self) -> bool:
        if self._closed:
            return False
        result = self._work.poll()
        changed = False
        if result is not None and result.kind == "player_previews":
            position = self._active_position
            self._active_position = None
            self._image_version += 1
            key = f"{self._generation}/{self._image_version}"
            if (
                position is not None
                and isinstance(result.value, bytes)
                and self.images.put(key, result.value)
            ):
                self._records = [
                    {
                        "position": position,
                        "image": f"image://vodforge-previews/{key}",
                        "status": "",
                    }
                ]
                changed = True
            elif self._records and not self._records[0]["image"]:
                self._records[0]["status"] = "No preview"
                changed = True
            if position is not None and self._desired_position == position:
                self._desired_position = None
        self._start()
        return changed

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._work.close()
        if self._owner is not None:
            self._owner.shutdown()
        self.images.clear()
