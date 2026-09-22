"""Bounded local artwork presentation shared by Archive and Watch widgets."""

from __future__ import annotations

import os
import time
import tkinter as tk
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from .archive_browser import archive_directory
from .archive_relink import record_fingerprint
from .archive_work import ArchiveWorkOwner
from .library_artwork_source import ArtworkAsset
from .presentation_diagnostics import PresentationProbe, canvas_snapshot
from .telemetry_features import time_bucket


@dataclass(frozen=True)
class _ArtworkPixels:
    bitmap: Any
    source: Any
    source_key: tuple[str, str]


def _fit_artwork_pixels(
    source: Any, size: tuple[int, int], backdrop: str, radius: int, role: str
) -> Any:
    """One fitting/shading owner for worker output and cached resize redraw."""
    from PIL import Image, ImageChops, ImageDraw, ImageOps

    bitmap = ImageOps.fit(source, size, method=Image.Resampling.LANCZOS)
    if backdrop:
        horizontal = Image.new("L", (size[0], 1))
        horizontal.putdata(
            [
                round(
                    232
                    * (1 - min(1.0, max(0.0, x / max(1, size[0] - 1) - 0.48) / 0.28))
                    ** 1.35
                )
                for x in range(size[0])
            ]
        )
        vertical = Image.new("L", (1, size[1]))
        vertical.putdata(
            [
                round(
                    (218 if role == "banner" else 32) * (y / max(1, size[1] - 1)) ** 2
                )
                for y in range(size[1])
            ]
        )
        if role == "playlist":
            horizontal.putdata(
                [round(100 * (1 - x / max(1, size[0] - 1))) for x in range(size[0])]
            )
            vertical.putdata(
                [
                    round(228 * min(1, y / max(1, size[1] - 1) / 0.72) ** 1.2)
                    for y in range(size[1])
                ]
            )
        shade = ImageChops.screen(horizontal.resize(size), vertical.resize(size))
        if role == "banner":
            # Match the channel header's bounded copy column.
            # Compact banners reserve the full readable width.
            text_end = min(
                size[0] - 36,
                (214 if size[0] >= 1000 else 174 if size[0] >= 680 else 32) + 620,
            )
            fade_end = min(size[0], text_end + size[0] * 0.22)
            horizontal.putdata(
                [
                    round(
                        232
                        * (
                            1
                            - min(
                                1.0,
                                max(0.0, x - text_end) / max(1.0, fade_end - text_end),
                            )
                        )
                        ** 1.35
                    )
                    for x in range(size[0])
                ]
            )
            vertical.putdata(
                [round(48 * (y / max(1, size[1] - 1)) ** 2) for y in range(size[1])]
            )
            shade = ImageChops.screen(horizontal.resize(size), vertical.resize(size))

        bitmap = Image.composite(Image.new("RGB", size, backdrop), bitmap, shade)
    mask = Image.new("L", (size[0] * 2, size[1] * 2))
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size[0] * 2 - 1, size[1] * 2 - 1),
        radius=radius * 2,
        fill=255,
    )
    bitmap = bitmap.convert("RGBA")
    bitmap.putalpha(mask.resize(size, Image.Resampling.LANCZOS))
    if size[0] != size[1]:
        from .ui_theme import THEME

        edge = Image.new("RGBA", (size[0] * 2, size[1] * 2))
        ImageDraw.Draw(edge).rounded_rectangle(
            (1, 1, size[0] * 2 - 2, size[1] * 2 - 2),
            radius=radius * 2,
            outline=THEME["border"],
            width=2,
        )
        bitmap = Image.alpha_composite(
            bitmap, edge.resize(size, Image.Resampling.LANCZOS)
        )
    return bitmap


class ArchiveArtworkMixin:
    _render_after: str | None

    def _presentation_setup(self: Any, telemetry: Any, surface: str) -> None:
        self._presentation = PresentationProbe(self, telemetry, surface)
        self._presentation_dirty = True
        self.bind("<Map>", self._presentation_mapped, add="+")
        self.bind("<Unmap>", self._presentation_hidden, add="+")

    def _presentation_mapped(self: Any, event: Any) -> None:
        if event.widget is self:
            self._presentation_change("entry")
            self._queue_render()

    def _presentation_hidden(self: Any, event: Any) -> None:
        if event.widget is self:
            self._presentation_change("hide")

    def _presentation_change(self: Any, trigger: str) -> None:
        probe = getattr(self, "_presentation", None)
        if probe is not None:
            if trigger not in {"hide", "artwork"}:
                self._presentation_dirty = True
            probe.change(trigger)

    def _presentation_configured(self: Any, event: Any) -> bool:
        probe = getattr(self, "_presentation", None)
        if probe is not None and event is not None:
            size = (event.width, event.height)
            if size != probe.last_size:
                probe.last_size = size
                self._presentation_change("resize")
                return True
        return False

    def _queue_scene_render(self: Any, event: Any = None) -> None:
        resized = self._presentation_configured(event)
        if self._closed:
            return
        if resized and self.winfo_ismapped():
            # Native live resize delivers Configure while Tk timers can remain
            # deferred. Commit current geometry at that boundary; position-only
            # Configure events must not repeat scene work.
            if self._render_after is not None:
                self.after_cancel(self._render_after)
                self._render_after = None
            self._artwork_resize_active = True
            try:
                self._render()
            finally:
                self._artwork_resize_active = False
        elif event is None and self._render_after is None:
            self._render_after = self.after(24, self._render)

    def _presentation_settle(self: Any, *, rendered: bool = True) -> None:
        probe = getattr(self, "_presentation", None)
        if probe is not None:
            if rendered:
                self._presentation_dirty = False
            probe.schedule()

    def _presentation_snapshot(self: Any) -> tuple[dict[str, str], bool]:
        dimensions, pending = canvas_snapshot(self, self._presentation_dimensions())
        if self._presentation_dirty:
            dimensions["presentation_scene"] = (
                "awaiting" if self.winfo_ismapped() else "retained"
            )
            pending = True
        return dimensions, pending

    def _artwork_setup(
        self: Any,
        thumbnail_path: Any,
        size: tuple[int, int],
        feature: str = "archive",
        *,
        source_path: Any = None,
    ) -> None:
        self._artwork_feature = feature
        self._artwork_requested_count = 0
        self._artwork_requested_keys: set[str] = set()
        self._artwork_requested_sources: dict[str, tuple[str, str]] = {}
        self._artwork_path = thumbnail_path
        self._artwork_source_path = source_path
        self._artwork_roles: dict[str, str] = {}
        self._artwork_size = size
        self._artwork_submitted_size = size
        self._artwork_images: OrderedDict[str, Any] = OrderedDict()
        self._artwork_image_bytes: dict[str, int] = {}
        self._artwork_source_cache: OrderedDict[
            tuple[str, str], tuple[Any, Any, float]
        ] = OrderedDict()
        self._artwork_source_bytes = 0
        self._artwork_resize_active = False
        self._artwork_displayed: dict[str, Any] = {}
        self._artwork_wanted: dict[str, dict[str, Any]] = {}
        self._artwork_specs: dict[str, tuple[tuple[int, int], str, int]] = {}
        self._artwork_attempted: set[str] = set()
        self._artwork_unavailable: set[str] = set()
        self._artwork_stamps: dict[str, tuple[Any, ...]] = {}
        self._artwork_next_check: dict[str, float] = {}
        self._artwork_owner = ArchiveWorkOwner()
        self._artwork_revision = 0
        self._artwork_closed = False
        self._artwork_after = self.after(60, self._artwork_poll)

    def _artwork_resize(self: Any, size: tuple[int, int]) -> None:
        """Retire default-sized pixels; explicit sizes retain their own identity."""
        if size == self._artwork_size:
            return
        self._artwork_size = size
        # Explicit tile/hero sizes are part of their cache keys and do not
        # depend on the default media size. Retain those valid pixels so channel
        # avatars do not disappear on every Watch viewport change.
        retained = set(self._artwork_specs) & set(self._artwork_images)
        for mapping in (
            self._artwork_images,
            self._artwork_image_bytes,
            self._artwork_specs,
            self._artwork_stamps,
            self._artwork_next_check,
        ):
            for key in list(mapping):
                if key not in retained:
                    del mapping[key]
        self._artwork_attempted.intersection_update(retained)
        self._artwork_unavailable.intersection_update(retained)
        self._artwork_revision += 1

    def _artwork_begin(self: Any) -> None:
        # Call after deleting the preceding scene. Hidden scenes keep their
        # displayed PhotoImages through worker cache replacement and resizing.
        self._artwork_displayed.clear()
        self._artwork_wanted = {}
        self._artwork_roles = {}
        self._artwork_specs = {
            key: spec
            for key, spec in self._artwork_specs.items()
            if key in self._artwork_images
        }

    def _artwork_image(
        self: Any,
        record: dict[str, Any],
        *,
        hero_size: tuple[int, int] | None = None,
        tile_size: tuple[int, int] | None = None,
        role: str = "media",
    ) -> Any:
        # Metadata replacement (including a new path for the same owner) changes
        # presentation identity. This private fingerprint is never telemetry.
        source_key = (record_fingerprint(record), role)
        key = source_key[0]
        if role != "media":
            key += ":" + role
        if hero_size is not None:
            from .ui_theme import THEME

            backdrop = THEME["panel"]
            key += f":hero:{hero_size[0]}:{hero_size[1]}:{backdrop}"
            self._artwork_specs[key] = (hero_size, backdrop, 12)
        elif tile_size is not None:
            key += f":tile:{tile_size[0]}:{tile_size[1]}"
            radius = tile_size[0] // 2 if tile_size[0] == tile_size[1] else 8
            self._artwork_specs[key] = (tile_size, "", radius)
        if len(self._artwork_wanted) < 48:
            self._artwork_wanted[key] = record
            self._artwork_roles[key] = role
        if key not in self._artwork_images and self.__dict__.get(
            "_artwork_resize_active", False
        ):
            cached_source = self._artwork_source_cache.get(source_key)
            if cached_source is not None and cached_source[2] > time.monotonic():
                source, stamp, deadline = cached_source
                self._artwork_source_cache.move_to_end(source_key)
                size, backdrop, radius = self._artwork_specs.get(
                    key, (self._artwork_size, "", 8)
                )
                pixels = _fit_artwork_pixels(source, size, backdrop, radius, role)
                self._cache_artwork_image(key, pixels)
                self._artwork_stamps[key] = stamp
                self._artwork_next_check[key] = deadline
        if key in self._artwork_images:
            self._artwork_images.move_to_end(key)
            image = self._artwork_images[key]
            self._artwork_displayed[str(image)] = image
            return image
        return None

    def _cache_artwork_image(self: Any, key: str, bitmap: Any) -> None:
        from PIL import ImageTk

        self._artwork_images[key] = ImageTk.PhotoImage(bitmap, master=self.canvas)
        self._artwork_image_bytes[key] = bitmap.width * bitmap.height * 4
        self._artwork_images.move_to_end(key)
        # Reuse is bounded independently of images still held by visible items.
        # A single larger requested image remains usable; retire all older entries.
        while len(self._artwork_images) > 1 and (
            len(self._artwork_images) > 64
            or sum(self._artwork_image_bytes.values()) > 32 * 1024 * 1024
        ):
            retired, _photo = self._artwork_images.popitem(last=False)
            self._artwork_image_bytes.pop(retired, None)

    def _cache_artwork_source(self: Any, pixels: _ArtworkPixels, stamp: Any) -> None:
        key, source = pixels.source_key, pixels.source
        if source is None:
            return
        old = self._artwork_source_cache.pop(key, None)
        if old is not None:
            self._artwork_source_bytes -= old[0].width * old[0].height * 3
        cost = source.width * source.height * 3
        if cost <= 64 * 1024 * 1024:
            self._artwork_source_cache[key] = (source, stamp, time.monotonic() + 30)
            self._artwork_source_bytes += cost
        while (
            len(self._artwork_source_cache) > 16
            or self._artwork_source_bytes > 64 * 1024 * 1024
        ):
            _key, (retired, _stamp, _deadline) = self._artwork_source_cache.popitem(
                last=False
            )
            self._artwork_source_bytes -= retired.width * retired.height * 3

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
            or (
                key not in self._artwork_images and key not in self._artwork_unavailable
            )
            or self._artwork_next_check.get(key, 0) <= now
        ][:24]
        if not items:
            return
        self._artwork_attempted.update(key for key, _record in items)
        if len(self._artwork_attempted) > 256:
            retained = set(self._artwork_wanted) | set(self._artwork_images)
            self._artwork_attempted.intersection_update(retained)
            self._artwork_unavailable.intersection_update(retained)
            self._artwork_specs = {
                key: spec
                for key, spec in self._artwork_specs.items()
                if key in retained
            }
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
        requested_size = self._artwork_size
        requested_specs = dict(self._artwork_specs)
        requested_roles = dict(self._artwork_roles)
        requested_sources = {
            key: (record_fingerprint(record), requested_roles.get(key, "media"))
            for key, record in items
        }
        source_path = self._artwork_source_path
        previous_stamps = dict(self._artwork_stamps)
        previous_images = set(self._artwork_images)

        def work(cancelled: Any) -> Any:
            from PIL import Image

            result: list[tuple[str, Any, tuple[Any, ...] | None]] = []
            started = time.monotonic()
            retained_source_bytes = 0
            retained_source_count = 0
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
                    size, backdrop, radius = requested_specs.get(
                        key, (requested_size, "", 8)
                    )
                    asset = (
                        source_path(
                            record, size, requested_roles.get(key, "media"), cancelled
                        )
                        if source_path is not None
                        else self._artwork_path(record)
                    )
                    path = asset.path if isinstance(asset, ArtworkAsset) else asset
                    kind = (
                        asset.kind if isinstance(asset, ArtworkAsset) else "thumbnail"
                    )
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
                        kind,
                        requested_roles.get(key, "media"),
                    )
                    if key in previous_images and previous_stamps.get(key) == stamp:
                        result.append((key, None, stamp))
                        continue
                    with Image.open(path) as source:
                        # Preserve the requested role's spatial detail. Reducing a
                        # hero to card-sized pixels before fitting loses it forever.
                        if source.width * source.height > 40_000_000:
                            raise ValueError("Artwork exceeds the decode limit")
                        decoded = source.convert("RGB")
                        bitmap = _fit_artwork_pixels(
                            decoded,
                            size,
                            backdrop,
                            radius,
                            requested_roles.get(key, "media"),
                        )
                        # Bound originals in the worker result as well as the UI cache.
                        # Larger sources still deliver their fitted output normally.
                        cost = decoded.width * decoded.height * 3
                        retained_source = None
                        if (
                            retained_source_count < 16
                            and retained_source_bytes + cost <= 64 * 1024 * 1024
                        ):
                            retained_source = decoded
                            retained_source_bytes += cost
                            retained_source_count += 1
                        result.append(
                            (
                                key,
                                _ArtworkPixels(
                                    bitmap, retained_source, requested_sources[key]
                                ),
                                stamp,
                            )
                        )
                except (OSError, ValueError):
                    result.append((key, None, None))
            return result

        if self._artwork_owner.submit("archive_artwork", work) is not None:
            self._artwork_requested_count = len(items)
            self._artwork_requested_keys = {key for key, _record in items}
            self._artwork_requested_sources = requested_sources
            self._artwork_submitted_size = requested_size

    def _artwork_poll(self: Any) -> None:
        if self._artwork_closed:
            return
        result = self._artwork_owner.poll()
        if result is not None and self._artwork_submitted_size != self._artwork_size:
            # A resize may finish while a previous-size batch is decoding.
            # Its stamps must not suppress the replacement batch.
            self._artwork_attempted.clear()
            self._artwork_next_check.clear()
            probe = getattr(self, "_presentation", None)
            if probe is not None:
                probe.retired_batch = True
            result = None
        if result is not None:
            if result.value is not None:
                completed_keys = {key for key, _bitmap, _stamp in result.value}
                unprocessed = self._artwork_requested_keys - completed_keys
                self._artwork_attempted.difference_update(unprocessed)
                for key in unprocessed:
                    self._artwork_next_check[key] = 0
            observed = getattr(self, "_on_usage", None)
            if observed is not None:
                count = sum(
                    stamp is not None for _key, _bitmap, stamp in result.value or []
                )
                sources = {
                    stamp[5]
                    for _key, _bitmap, stamp in result.value or []
                    if stamp is not None
                }
                roles = {
                    stamp[6]
                    for _key, _bitmap, stamp in result.value or []
                    if stamp is not None
                }
                observed(
                    self._artwork_feature,
                    "artwork_loaded" if count else "artwork_unavailable",
                    artwork_source=next(iter(sources))
                    if len(sources) == 1
                    else "mixed"
                    if sources
                    else "none",
                    artwork_role=next(iter(roles)) if len(roles) == 1 else "mixed",
                    item_count=str(len(result.value or [])),
                    unavailable_count=str(max(0, len(result.value or []) - count)),
                    processing_bucket=time_bucket(result.elapsed_ms / 1000),
                )
        if result is not None and result.value:
            changed = False
            for key, bitmap, stamp in result.value:
                self._artwork_next_check[key] = time.monotonic() + 30
                if stamp is None:
                    origin = self._artwork_requested_sources.get(key)
                    retired = self._artwork_source_cache.pop(origin, None)
                    if retired is not None:
                        self._artwork_source_bytes -= (
                            retired[0].width * retired[0].height * 3
                        )
                    self._artwork_unavailable.add(key)
                    changed = self._artwork_images.pop(key, None) is not None or changed
                    self._artwork_stamps.pop(key, None)
                    self._artwork_image_bytes.pop(key, None)
                    continue
                self._artwork_unavailable.discard(key)
                self._artwork_stamps[key] = stamp
                origin = self._artwork_requested_sources.get(key)
                cached_source = self._artwork_source_cache.get(origin)
                if cached_source is not None and cached_source[1] == stamp:
                    self._artwork_source_cache[origin] = (
                        cached_source[0],
                        stamp,
                        time.monotonic() + 30,
                    )
                if bitmap is not None:
                    if isinstance(bitmap, _ArtworkPixels):
                        self._cache_artwork_source(bitmap, stamp)
                        bitmap = bitmap.bitmap
                    self._cache_artwork_image(key, bitmap)
                    changed = True
            if changed:
                self._artwork_revision += 1
                self._queue_render()
        if result is not None:
            self._presentation_change("artwork")
        if not self._artwork_owner.busy and self.winfo_ismapped():
            self._artwork_request()
        self._artwork_after = self.after(60, self._artwork_poll)

    def _artwork_close(self: Any) -> None:
        probe = getattr(self, "_presentation", None)
        if probe is not None:
            probe.close()
        self._artwork_closed = True
        self._artwork_owner.close()
        if self._artwork_after is not None:
            try:
                self.after_cancel(self._artwork_after)
            except tk.TclError:
                pass
            self._artwork_after = None
        self._artwork_images.clear()
        self._artwork_image_bytes.clear()
        self._artwork_source_cache.clear()
        self._artwork_source_bytes = 0
        self._artwork_requested_sources.clear()
        self._artwork_displayed.clear()
        self._artwork_wanted.clear()
        self._artwork_specs.clear()
        self._artwork_attempted.clear()
        self._artwork_unavailable.clear()
        self._artwork_stamps.clear()
        self._artwork_next_check.clear()
