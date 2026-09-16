"""Bounded local artwork presentation shared by Archive and Watch widgets."""

from __future__ import annotations

import os
import time
import tkinter as tk
from collections import OrderedDict
from typing import Any

from .archive_browser import archive_directory
from .archive_relink import record_fingerprint
from .archive_work import ArchiveWorkOwner
from .telemetry_features import time_bucket


class ArchiveArtworkMixin:
    def _artwork_setup(
        self: Any, thumbnail_path: Any, size: tuple[int, int], feature: str = "archive"
    ) -> None:
        self._artwork_feature = feature
        self._artwork_requested_count = 0
        self._artwork_path = thumbnail_path
        self._artwork_size = size
        self._artwork_images: OrderedDict[str, Any] = OrderedDict()
        self._artwork_wanted: dict[str, dict[str, Any]] = {}
        self._artwork_attempted: set[str] = set()
        self._artwork_stamps: dict[str, tuple[Any, ...]] = {}
        self._artwork_next_check: dict[str, float] = {}
        self._artwork_owner = ArchiveWorkOwner()
        self._artwork_revision = 0
        self._artwork_closed = False
        self._artwork_after = self.after(60, self._artwork_poll)

    def _artwork_begin(self: Any) -> None:
        self._artwork_wanted = {}

    def _artwork_image(self: Any, record: dict[str, Any]) -> Any:
        # Metadata replacement (including a new path for the same owner) changes
        # presentation identity. This private fingerprint is never telemetry.
        key = record_fingerprint(record)
        if len(self._artwork_wanted) < 48:
            self._artwork_wanted[key] = record
        if key in self._artwork_images:
            self._artwork_images.move_to_end(key)
            return self._artwork_images[key]
        return None

    def _artwork_request(self: Any) -> None:
        if (
            self._artwork_closed
            or self._artwork_owner.busy
            or not self.winfo_ismapped()
        ):
            return
        now = time.monotonic()
        items = [
            (key, record)
            for key, record in self._artwork_wanted.items()
            if key not in self._artwork_attempted
            or self._artwork_next_check.get(key, 0) <= now
        ][:24]
        if not items:
            return
        self._artwork_attempted.update(key for key, _record in items)
        if len(self._artwork_attempted) > 256:
            retained = set(self._artwork_wanted) | set(self._artwork_images)
            self._artwork_attempted.intersection_update(retained)
            self._artwork_stamps = {
                key: stamp
                for key, stamp in self._artwork_stamps.items()
                if key in retained
            }
            self._artwork_next_check = {
                key: deadline
                for key, deadline in self._artwork_next_check.items()
                if key in retained
            }
        for key, _record in items:
            self._artwork_next_check[key] = now + 30
        previous_stamps = dict(self._artwork_stamps)
        previous_images = set(self._artwork_images)

        def work(cancelled: Any) -> Any:
            from PIL import Image, ImageOps

            result: list[tuple[str, Any, tuple[Any, ...] | None]] = []
            started = time.monotonic()
            for key, record in items:
                if cancelled.is_set() or time.monotonic() - started > 10:
                    break
                directory = archive_directory(record)
                if directory is not None and (directory.style == "windows") != (
                    os.name == "nt"
                ):
                    result.append((key, None, None))
                    continue
                try:
                    path = self._artwork_path(record)
                    if path is None:
                        result.append((key, None, None))
                        continue
                    stat = path.stat()
                    stamp = (
                        str(path),
                        stat.st_dev,
                        stat.st_ino,
                        stat.st_size,
                        stat.st_mtime_ns,
                    )
                    if key in previous_images and previous_stamps.get(key) == stamp:
                        result.append((key, None, stamp))
                        continue
                    with Image.open(path) as source:
                        source.thumbnail((640, 360))
                        result.append(
                            (
                                key,
                                ImageOps.fit(source.convert("RGB"), self._artwork_size),
                                stamp,
                            )
                        )
                except (OSError, ValueError):
                    result.append((key, None, None))
            return result

        if self._artwork_owner.submit("archive_artwork", work) is not None:
            self._artwork_requested_count = len(items)

    def _artwork_poll(self: Any) -> None:
        if self._artwork_closed:
            return
        result = self._artwork_owner.poll()
        if result is not None:
            observed = getattr(self, "_on_usage", None)
            if observed is not None:
                count = sum(
                    stamp is not None for _key, _bitmap, stamp in result.value or []
                )
                observed(
                    self._artwork_feature,
                    "artwork_loaded" if count else "artwork_unavailable",
                    item_count=str(self._artwork_requested_count),
                    unavailable_count=str(
                        max(0, self._artwork_requested_count - count)
                    ),
                    processing_bucket=time_bucket(result.elapsed_ms / 1000),
                )
        if result is not None and result.value:
            from PIL import ImageTk

            changed = False
            for key, bitmap, stamp in result.value:
                self._artwork_next_check[key] = time.monotonic() + 30
                if stamp is None:
                    changed = self._artwork_images.pop(key, None) is not None or changed
                    self._artwork_stamps.pop(key, None)
                    continue
                self._artwork_stamps[key] = stamp
                if bitmap is not None:
                    self._artwork_images[key] = ImageTk.PhotoImage(
                        bitmap, master=self.canvas
                    )
                    self._artwork_images.move_to_end(key)
                    changed = True
            while len(self._artwork_images) > 64:
                self._artwork_images.popitem(last=False)
            if changed:
                self._artwork_revision += 1
                self._queue_render()
        if not self._artwork_owner.busy and self.winfo_ismapped():
            self._artwork_request()
        self._artwork_after = self.after(60, self._artwork_poll)

    def _artwork_close(self: Any) -> None:
        self._artwork_closed = True
        self._artwork_owner.close()
        if self._artwork_after is not None:
            try:
                self.after_cancel(self._artwork_after)
            except tk.TclError:
                pass
            self._artwork_after = None
        self._artwork_images.clear()
        self._artwork_wanted.clear()
        self._artwork_attempted.clear()
        self._artwork_stamps.clear()
        self._artwork_next_check.clear()
