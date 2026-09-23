"""Whole Library compositions; state and canonical actions stay in LibraryScene."""

from __future__ import annotations

from functools import partial
from types import SimpleNamespace
from typing import Any

from PIL import ImageTk

from .archive_browser import archive_row_owner
from .library_detail_layout import LibraryDetailLayout
from .library_state import format_duration
from .scene_components import ScenePainter, scene_font
from .scene_paging import scene_page, visible_scene_rows
from .ui_button_contract import button_metrics
from .ui_chrome import layered_surface_image
from .ui_layout import window_logical_metrics
from .ui_materials import draw_matte_backdrop
from .ui_theme import THEME, _mix_hex
from .volume_storage import format_storage_bytes
from .watch_library import watch_rails


class LibrarySceneLayout(LibraryDetailLayout):
    _catalog_window: Any

    def _catalog_route_key(self: Any) -> tuple[Any, ...]:
        return (
            self._route,
            self._query,
            self._sort,
            self._filter,
            self._group_kind,
            self._group_key,
            self._category,
        )

    def _catalog_item_key(self: Any, kind: str, item: Any) -> str:
        return archive_row_owner(item[1]) if kind == "media" else item.key

    def _remember_catalog_anchor(self: Any) -> None:
        window = self.__dict__.get("_catalog_window")
        if not window:
            return
        items, kind, columns, stride, origin, _span, route = window
        top = self.canvas.canvasy(0)
        if not items or top < origin:
            self._catalog_anchor = None
            return
        index = min(len(items) - 1, int((top - origin) // stride) * columns)
        self._catalog_anchor = (
            route,
            self._catalog_item_key(kind, items[index]),
            index,
            top - origin - index // columns * stride,
        )

    def _catalog_scroll_used(self: Any) -> None:
        if self.__dict__.get("_closed") or not self.__dict__.get("_catalog_window"):
            return
        route = self._catalog_route_key()
        if self.__dict__.get("_catalog_scroll_seen") != route:
            self._catalog_scroll_seen = route
            self._on_usage("archive", "scene_scrolled", scene_route=self._route)

    def _catalog_scroll_command(self: Any, *arguments: Any) -> None:
        before = self.canvas.yview()
        self.canvas.yview(*arguments)
        if self.canvas.yview() != before:
            self._catalog_scroll_used()

    def _catalog_scroll_changed(self: Any, first: float, last: float) -> None:
        self._catalog_scrollbar.set(first, last)
        window = self.__dict__.get("_catalog_window")
        if not window:
            return
        items, _kind, columns, stride, origin, span, _route = window
        self._remember_catalog_anchor()
        if (
            visible_scene_rows(
                len(items),
                columns,
                stride,
                origin,
                self.canvas.canvasy(0),
                self.canvas.winfo_height(),
                overscan=0 if self._route == "home" else 1,
            )
            != span
        ):
            self._queue_render()

    def _catalog_rows(
        self: Any, items: Any, kind: str, columns: int, stride: int, y: int
    ):
        top = self.canvas.canvasy(0)
        pending = self.__dict__.pop("_catalog_pending_anchor", None)
        extent = y + max(1, (len(items) + columns - 1) // columns) * stride
        if pending and pending[0] == self._catalog_route_key() and items:
            index = next(
                (
                    i
                    for i, item in enumerate(items)
                    if self._catalog_item_key(kind, item) == pending[1]
                ),
                min(pending[2], len(items) - 1),
            )
            top = min(
                max(0, extent - self.canvas.winfo_height()),
                y + index // columns * stride + pending[3],
            )
            self._catalog_restore_top = top
        span = visible_scene_rows(
            len(items),
            columns,
            stride,
            y,
            top,
            self.canvas.winfo_height(),
            overscan=0 if self._route == "home" else 1,
        )
        self._catalog_window = (
            items,
            kind,
            columns,
            stride,
            y,
            span,
            self._catalog_route_key(),
        )
        self._page = 0
        self._matching_count = len(items)
        indices = list(range(span[0] * columns, min(len(items), span[1] * columns)))
        # Admit visible images before overscan. Channel cards request two images;
        # off-screen previews must not consume the bounded request budget first.
        px = window_logical_metrics(self).px
        image_height = stride - px(170) if kind == "media" else px(125)
        bottom = top + self.canvas.winfo_height()
        indices.sort(
            key=lambda index: (
                not (
                    y + index // columns * stride + image_height > top
                    and y + index // columns * stride < bottom
                ),
                index,
            )
        )
        self._rendered_count = len(indices)
        return indices, extent

    def _surface(
        self: Any,
        x: int,
        y: int,
        width: int,
        height: int,
        *,
        fill: str = "",
        edge: str = "",
        radius: int = 10,
        canvas: Any = None,
        dashed: bool = False,
        illumination: float = 0.0,
        role: str = "action",
        selected: bool = False,
        unit_scale: int = 1,
    ) -> None:
        c = canvas or self.canvas
        if not dashed:
            owner = self._depth if canvas is None else self._sidebar_depth
            owner.draw(
                (x, y, x + width, y + height),
                role=role,
                selected=selected,
                fill=fill or THEME["panel"],
                edge=edge or THEME["border"],
                illumination=illumination,
                radius=radius,
                unit_scale=unit_scale,
            )
            return
        image = ImageTk.PhotoImage(
            layered_surface_image(
                width,
                height,
                fill=fill or THEME["panel"],
                edge="" if dashed else edge or THEME["border"],
                radius=radius,
                illumination=illumination,
            ),
            master=c,
        )
        (self._sidebar_images if canvas is not None else self._button_images).append(
            image
        )
        c.create_image(x, y, image=image, anchor="nw")
        if dashed:
            c.create_line(
                x + radius,
                y,
                x + width - radius,
                y,
                x + width,
                y,
                x + width,
                y + radius,
                x + width,
                y + height - radius,
                x + width,
                y + height,
                x + width - radius,
                y + height,
                x + radius,
                y + height,
                x,
                y + height,
                x,
                y + height - radius,
                x,
                y + radius,
                x,
                y,
                x + radius,
                y,
                fill=edge or THEME["accent_dark"],
                dash=(3, 3),
                smooth=True,
                width=1,
            )

    def _center(
        self: Any,
        x: int,
        y: int,
        text: str,
        *,
        size: int = 15,
        bold: bool = False,
        color: str = "",
        unit_scale: int = 1,
    ) -> None:
        self.canvas.create_text(
            x,
            y,
            text=text,
            font=scene_font(size, bold=bold, font_scale=unit_scale),
            fill=color or THEME["text"],
            anchor="n",
        )

    def _pill(
        self: Any,
        p: ScenePainter,
        x: int,
        y: int,
        text: str,
        *,
        maximum: int = 150,
        unit_scale: int = 1,
    ) -> int:
        scale = unit_scale
        label = self._fit(
            text, maximum - (24 * unit_scale), 1, scene_font(12, font_scale=scale)
        )
        width = min(
            maximum,
            max((48 * unit_scale), len(label) * (7 * unit_scale) + (24 * unit_scale)),
        )
        # Category names carry meaning; tones follow the shared theme.
        fill, edge = THEME["accent_surface"], THEME["border"]
        self._surface(
            x,
            y,
            width,
            (29 * unit_scale),
            fill=fill,
            edge=edge,
            radius=(14 * unit_scale),
            unit_scale=scale,
        )
        p.text(
            x + (12 * unit_scale),
            y + (7 * unit_scale),
            label,
            size=12,
            width=width - (24 * unit_scale),
            font_scale=scale,
        )
        return width

    def _draw_sidebar(self: Any) -> None:
        if self._closed or not self.sidebar.winfo_exists():
            return
        metrics = window_logical_metrics(self)
        px, scale = metrics.px, metrics.scale
        c = self.sidebar
        c.delete("all")
        self._sidebar_targets = []
        self._sidebar_images: list[Any] = []
        p = ScenePainter(SimpleNamespace(canvas=c, _fit=self._fit))
        width = max(1, c.winfo_width())
        height = max(1, c.winfo_height())
        c.create_line(
            width - px(1),
            0,
            width - px(1),
            height,
            fill=THEME["border"],
            tags="sidebar-divider",
        )
        p.text(
            px(14),
            px(30),
            "ARCHIVE",
            size=11,
            bold=True,
            color=THEME["muted"],
            font_scale=scale,
        )
        counts = self._counts()
        for index, (name, label, icon) in enumerate(
            (
                ("all", "All Media", "folder"),
                ("channels", "Channels", "channels"),
                ("playlists", "Playlists", "list"),
                ("videos", "Videos", "videos"),
                ("audio", "Audio", "audio"),
            )
        ):
            y = px(54) + index * px(49)
            active = self._route == name or (
                name == "all" and self._route in {"home", "detail", "collections"}
            )
            self._surface(
                px(8),
                y,
                width - px(23),
                px(45),
                fill=THEME["panel"],
                edge=THEME["panel"],
                canvas=c,
                role="navigation",
                selected=active,
                unit_scale=scale,
            )
            p.icon(
                icon,
                px(22),
                y + px(12),
                px(22),
                THEME["selection"] if active else THEME["icon"],
                stroke_width=2 * scale,
            )
            p.text(px(61), y + px(13), label, size=15, font_scale=scale)
            self._surface(
                width - px(62),
                y + px(7),
                px(36),
                px(31),
                fill=THEME["accent_dark"] if active else THEME["surface"],
                edge=THEME["accent_dark"] if active else THEME["surface"],
                radius=px(15),
                canvas=c,
            )
            c.create_text(
                width - px(44),
                y + px(23),
                text=str(counts[name]),
                font=scene_font(13, bold=True, font_scale=scale),
                fill=THEME["text"],
            )
            self._sidebar_targets.append(
                (
                    (px(8), y, width - px(15), y + px(45)),
                    partial(self.navigate, "home" if name == "all" else name),
                )
            )
        before_storage = set(c.find_all())
        y = max(px(343), height - px(141))
        self._sidebar_storage_y = y
        self._surface(px(9), y, width - px(25), px(124), radius=px(10), canvas=c)
        p.icon(
            "drive", px(26), y + px(20), px(27), THEME["muted"], stroke_width=2 * scale
        )
        state = self._storage.snapshot
        title = state.capacity.volume.label if state.capacity else "Local Library"
        p.text(
            px(69),
            y + px(24),
            title,
            size=13,
            bold=True,
            width=width - px(109),
            font_scale=scale,
        )
        p.icon(
            "chevron",
            width - px(46),
            y + px(23),
            px(16),
            THEME["muted"],
            stroke_width=1.4 * scale,
        )
        if state.capacity:
            capacity = state.capacity
            c.create_line(
                px(30),
                y + px(62),
                width - px(36),
                y + px(62),
                fill=THEME["border"],
                width=px(10),
                capstyle="round",
            )
            if capacity.used:
                c.create_line(
                    px(30),
                    y + px(62),
                    px(30) + (width - px(66)) * capacity.fraction_used,
                    y + px(62),
                    fill=THEME["progress"],
                    width=px(10),
                    capstyle="round",
                )
            p.text(
                px(25),
                y + px(79),
                f"{format_storage_bytes(capacity.used)} of {format_storage_bytes(capacity.total)} used",
                size=12,
                font_scale=scale,
                color=THEME["muted"],
                width=width - px(49),
            )
            p.text(
                px(25),
                y + px(101),
                f"{capacity.fraction_used:.0%}",
                size=12,
                font_scale=scale,
                color=THEME["muted"],
            )
            c.create_text(
                width - px(29),
                y + px(101),
                text=f"{format_storage_bytes(capacity.free)} free",
                anchor="ne",
                font=scene_font(12, font_scale=scale),
                fill=THEME["muted"],
            )
        else:
            p.text(
                px(25),
                y + px(78),
                "Checking drive…" if state.status == "loading" else "Drive unavailable",
                size=12,
                font_scale=scale,
                color=THEME["muted"],
            )
        self._sidebar_targets.append(
            ((px(9), y, width - px(16), y + px(124)), self._choose_volume)
        )
        c.configure(scrollregion=(0, 0, width, max(height, y + px(141))))
        for item in set(c.find_all()) - before_storage:
            c.addtag_withtag("sidebar-storage", item)

    def _checkbox(
        self: Any,
        p: ScenePainter,
        x: int,
        y: int,
        owners: tuple[str, ...],
        *,
        unit_scale: int = 1,
    ) -> None:
        scale = unit_scale
        if not self._selection_mode:
            return
        selected = bool(owners) and all(owner in self._selected for owner in owners)
        self._surface(
            x,
            y,
            (30 * unit_scale),
            (30 * unit_scale),
            fill=THEME["accent_surface"] if selected else THEME["surface"],
            radius=(7 * unit_scale),
            unit_scale=scale,
        )
        self.canvas.create_rectangle(
            x + (7 * unit_scale),
            y + (7 * unit_scale),
            x + (23 * unit_scale),
            y + (23 * unit_scale),
            outline=THEME["text"],
            width=1.4 * unit_scale,
        )
        if selected:
            self.canvas.create_line(
                x + (10 * unit_scale),
                y + (15 * unit_scale),
                x + (14 * unit_scale),
                y + (19 * unit_scale),
                x + (21 * unit_scale),
                y + (10 * unit_scale),
                fill=THEME["text"],
                width=2 * unit_scale,
            )
        self._targets.append(
            (
                (x, y, x + (30 * unit_scale), y + (30 * unit_scale)),
                partial(self._toggle_selection, owners),
            )
        )

    def _duration(
        self: Any, p: ScenePainter, row: dict, x: int, y: int, *, unit_scale: int = 1
    ) -> None:
        scale = unit_scale
        text = format_duration(row.get("duration"))
        if text:
            width = max(
                (48 * unit_scale), len(text) * (8 * unit_scale) + (14 * unit_scale)
            )
            self._surface(
                x - width,
                y,
                width,
                (25 * unit_scale),
                fill=THEME["bg"],
                edge=THEME["bg"],
                radius=(5 * unit_scale),
                unit_scale=scale,
            )
            p.text(
                x - width + (7 * unit_scale),
                y + (5 * unit_scale),
                text,
                size=12,
                font_scale=scale,
            )

    def _media_card(
        self: Any, p: ScenePainter, index: int, row: dict, x: int, y: int, width: int
    ) -> None:
        metrics = window_logical_metrics(self)
        px, scale = metrics.px, metrics.scale
        height = width * 9 // 16
        self._depth.draw(
            (x, y, x + width, y + height + px(151)), unit_scale=scale, radius=px(10)
        )
        image = self._artwork_image(row, tile_size=(width, height))
        if image:
            self.canvas.create_image(
                x, y, image=image, anchor="nw", tags="presentation-artwork"
            )
        self._targets.append(
            (
                (x, y, x + width, y + height + px(93)),
                partial(self._toggle_selection, (archive_row_owner(row),))
                if self._selection_mode
                else partial(self.show_details, index),
            )
        )
        self._context_targets.append(
            ((x, y, x + width, y + height + px(153)), archive_row_owner(row))
        )
        self._checkbox(
            p, x + px(7), y + px(7), (archive_row_owner(row),), unit_scale=scale
        )
        self._duration(p, row, x + width - px(7), y + height - px(30), unit_scale=scale)
        p.text(
            x + px(12),
            y + height + px(11),
            str(row.get("title") or "Saved media"),
            size=14,
            bold=True,
            width=width - px(24),
            font_scale=scale,
        )
        p.text(
            x + px(12),
            y + height + px(35),
            str(row.get("channel") or row.get("uploader") or "Local media"),
            size=14,
            color=THEME["muted"],
            width=width - px(24),
            font_scale=scale,
        )
        category = str(
            row.get("vodforge_user_category")
            or (
                row.get("vodforge_user_tags")
                or [row.get("vodforge_output_type") or "Video"]
            )[0]
        )
        self._pill(
            p,
            x + px(12),
            y + height + px(60),
            category,
            maximum=width - px(24),
            unit_scale=scale,
        )
        p.button(
            x + px(8),
            y + height + px(102),
            max(px(78), width - px(button_metrics().height) - px(26)),
            "Play",
            partial(self._action, "play", index),
            icon="play",
            unit_scale=scale,
        )
        p.button(
            x + width - px(8) - px(button_metrics().height),
            y + height + px(102),
            None,
            "",
            partial(self._open_item_menu, archive_row_owner(row)),
            icon="more",
            unit_scale=scale,
        )

    def _collection_card(
        self: Any, p: ScenePainter, group: Any, kind: str, x: int, y: int, width: int
    ) -> None:
        metrics = window_logical_metrics(self)
        px, scale = metrics.px, metrics.scale
        indices = tuple(index for video in group.videos for index in video.indices)
        row = self._records[indices[0]]
        title = group.name if kind == "channels" else group.title
        self._depth.draw(
            (x, y, x + width, y + px(192)), unit_scale=scale, radius=px(10)
        )
        # A channel card has one identity image. Layering a banner and avatar
        # repeats the same fallback thumbnail in two incompatible shapes.
        if kind == "channels":
            image = self._artwork_image(row, tile_size=(px(96), px(96)), role="avatar")
            image_x, image_y = x + (width - px(96)) // 2, y + px(14)
        else:
            image = self._artwork_image(row, tile_size=(width, px(125)), role="media")
            image_x, image_y = x, y
        if image:
            self.canvas.create_image(
                image_x, image_y, image=image, anchor="nw", tags="presentation-artwork"
            )
        elif kind == "channels":
            self.canvas.create_oval(
                image_x,
                image_y,
                image_x + px(96),
                image_y + px(96),
                fill=THEME["accent_surface"],
                outline="",
            )
            self._center(
                image_x + px(48),
                image_y + px(30),
                title[:1].upper(),
                size=28,
                color=THEME["text"],
                unit_scale=scale,
            )
        self._targets.append(
            (
                (x, y, x + width, y + px(192)),
                partial(
                    self._toggle_selection,
                    tuple(archive_row_owner(self._records[i]) for i in indices),
                )
                if self._selection_mode
                else partial(self._group_open, kind, group.key, title),
            )
        )
        self._checkbox(
            p,
            x + px(7),
            y + px(7),
            tuple(archive_row_owner(self._records[i]) for i in indices),
            unit_scale=scale,
        )
        p.text(
            x + px(14),
            y + px(138),
            title,
            size=14,
            bold=True,
            width=width - px(52),
            font_scale=scale,
        )
        audio = sum(self._is_audio(self._records[i]) for i in indices)
        parts = [f"{len(indices)} item" + ("s" if len(indices) != 1 else "")]
        if len(indices) - audio:
            parts.append(
                f"{len(indices) - audio} video"
                + ("s" if len(indices) - audio != 1 else "")
            )
        if audio:
            parts.append(f"{audio} audio")
        p.text(
            x + px(14),
            y + px(166),
            " · ".join(parts),
            size=11,
            color=THEME["muted"],
            width=width - px(28),
            font_scale=scale,
        )
        p.button(
            x + width - px(6) - px(button_metrics("inline").height),
            y + px(129),
            None,
            "",
            partial(self._group_menu, kind, group.key, title, indices),
            icon="more",
            variant="inline",
            unit_scale=scale,
        )

    def _empty_panel(
        self: Any,
        p: ScenePainter,
        y: int,
        width: int,
        *,
        collections: bool = False,
        filtered: bool = False,
        actions: bool = True,
    ) -> int:
        metrics = window_logical_metrics(self)
        px, scale = metrics.px, metrics.scale
        panel_height = px(232) if actions else px(188)
        self._surface(
            0,
            y,
            width,
            panel_height,
            fill=THEME["bg"],
            edge=THEME["accent_dark"],
            dashed=True,
            illumination=0.045,
            unit_scale=scale,
        )
        cx = width // 2
        self._surface(
            cx - px(35),
            y + px(20),
            px(70),
            px(70),
            fill=THEME["panel"],
            edge=_mix_hex(THEME["panel"], THEME["accent"], 0.23),
            radius=px(35),
            illumination=0.17,
            unit_scale=scale,
        )
        p.icon(
            "folder" if collections else "download",
            cx - px(14),
            y + px(42),
            px(28),
            THEME["muted"],
            stroke_width=2 * scale,
        )
        self._center(
            cx,
            y + px(105),
            "No matching media"
            if filtered
            else "No collections yet"
            if collections
            else "No downloads yet",
            size=21,
            bold=True,
            unit_scale=scale,
        )
        copy = (
            "Try a different search or clear your filters."
            if filtered
            else "Your collections will appear here once you start downloading content from Forge."
            if collections
            else "Downloads from Forge will appear here automatically."
        )
        self._center(
            cx, y + px(139), copy, size=14, color=THEME["muted"], unit_scale=scale
        )
        if filtered:
            p.button(
                cx - px(84),
                y + px(173),
                px(168),
                "Clear filters",
                self._clear_filters,
                unit_scale=scale,
            )
        elif actions:
            p.button(
                cx - px(190),
                y + px(173),
                px(177),
                "Go to Forge",
                partial(self._action, "forge", None),
                primary=True,
                icon="play",
                unit_scale=scale,
            )
            p.button(
                cx + px(5),
                y + px(173),
                px(183),
                "Import Media",
                partial(self._action, "import", None),
                icon="download",
                unit_scale=scale,
            )
        return y + panel_height

    def _categories(self: Any, p: ScenePainter, width: int) -> int:
        metrics = window_logical_metrics(self)
        px, scale = metrics.px, metrics.scale
        counts = self._counts()
        columns = max(1, min(4, (width + px(14)) // px(200)))
        tile = (width - px(14) * (columns - 1)) // columns
        for n, (route, title, subtitle, empty, color) in enumerate(
            (
                (
                    "channels",
                    "Channels",
                    "Downloaded channel archives",
                    "No channel archives yet",
                    THEME["accent_dark"],
                ),
                (
                    "playlists",
                    "Playlists",
                    "Your curated collections",
                    "No playlists yet",
                    THEME["accent_dark"],
                ),
                (
                    "videos",
                    "Videos",
                    "All downloaded videos",
                    "No downloaded videos",
                    THEME["accent_dark"],
                ),
                (
                    "audio",
                    "Audio",
                    "Music, podcasts & more",
                    "No audio files yet",
                    THEME["accent_dark"],
                ),
            )
        ):
            x = n % columns * (tile + px(14))
            row_y = n // columns * px(126)
            self._depth.draw(
                (x, row_y + px(94), x + tile, row_y + px(200)),
                unit_scale=scale,
                radius=px(10),
            )
            if tile < px(220):
                # At compact widths the label is the affordance; decorative icons
                # and summaries must not squeeze navigation into ellipses.
                p.text(
                    x + px(16),
                    row_y + px(115),
                    title,
                    size=15,
                    bold=True,
                    width=tile - px(32),
                    font_scale=scale,
                )
                p.text(
                    x + px(16),
                    row_y + px(145),
                    str(counts[route]),
                    size=22,
                    bold=True,
                    color=THEME["muted"],
                    width=tile - px(32),
                    font_scale=scale,
                )
                self._targets.append(
                    (
                        (x, row_y + px(94), x + tile, row_y + px(200)),
                        partial(self.navigate, route),
                    )
                )
                continue
            icon_size = px(64) if tile >= px(255) else px(48)
            self._surface(
                x + px(16),
                row_y + px(115),
                icon_size,
                px(64),
                fill=color,
                edge=color,
                radius=px(9),
                unit_scale=scale,
            )
            p.icon(
                route,
                x + px(16) + (icon_size - px(34)) // 2,
                row_y + px(131),
                px(34),
                stroke_width=2 * scale,
            )
            tx = x + icon_size + px(36)
            p.text(
                tx,
                row_y + px(119),
                title,
                size=16,
                bold=True,
                width=tile - icon_size - px(51),
                font_scale=scale,
            )
            p.text(
                tx,
                row_y + px(146),
                f"{counts[route]} {'audio file' if route == 'audio' else route.removesuffix('s')}"
                + ("s" if counts[route] != 1 else ""),
                size=13,
                color=THEME["muted"],
                width=tile - icon_size - px(51),
                font_scale=scale,
            )
            p.text(
                tx,
                row_y + px(168),
                subtitle if counts[route] else empty,
                size=10,
                color=THEME["muted"],
                width=tile - icon_size - px(51),
                font_scale=scale,
            )
            p.icon(
                "chevron",
                x + tile - px(29),
                row_y + px(137),
                px(17),
                THEME["muted"],
                stroke_width=2 * scale,
            )
            self._targets.append(
                (
                    (x, row_y + px(94), x + tile, row_y + px(200)),
                    partial(self.navigate, route),
                )
            )

        return px(237) + ((4 + columns - 1) // columns - 1) * px(126)

    def _toolbar(self: Any, p: ScenePainter, width: int, y: int, title: str) -> int:
        metrics = window_logical_metrics(self)
        px, scale = metrics.px, metrics.scale
        search_width, search_height = px(200), px(40)
        # Embedded widgets and canvas actions share this owner’s measured units.
        toolbar_span = search_width + px(14) + px(396)
        heading_width = min(width, max(px(240), width - toolbar_span - px(40)))
        p.text(0, y, title, size=24, bold=True, width=heading_width, font_scale=scale)
        p.text(
            0,
            y + px(35),
            "Your latest saved videos and audio."
            if self._route == "home"
            else "Browse your saved media.",
            size=14,
            color=THEME["muted"],
            width=heading_width,
            font_scale=scale,
        )
        if self._route == "home" and not self._records:
            return y + px(68)
        control_y = y if width >= max(px(1000), toolbar_span + px(390)) else y + px(68)
        if self._selection_mode:
            p.text(
                0 if width < px(1000) else width - px(530),
                control_y + px(13),
                f"{len(self._selected)} selected" if self._selected else "Select items",
                size=14,
                color=THEME["muted"],
                font_scale=scale,
            )
            if self._selected:
                p.button(
                    0 if width < px(480) else width - px(277),
                    control_y + px(52) if width < px(480) else control_y,
                    px(175),
                    "Actions…",
                    partial(self._action, "selection_actions", None),
                    unit_scale=scale,
                )
            p.button(
                width - px(88),
                control_y,
                px(88),
                "Done",
                self._clear_selection,
                unit_scale=scale,
            )
            return control_y + (
                px(116) if width < px(480) and self._selected else px(64)
            )
        reserve = (
            px(66) if self._route == "home" and width >= toolbar_span + px(66) else 0
        )
        available = width - reserve
        wrapped = available < toolbar_span
        sx = 0 if wrapped else max(0, available - toolbar_span)
        self._search_window = self.canvas.create_window(
            sx,
            control_y,
            window=self._search_field,
            anchor="nw",
            width=available if wrapped else search_width,
            height=search_height,
        )
        self._project_search_backdrop()
        row_y = control_y + search_height + px(12) if wrapped else control_y
        controls_x = 0 if wrapped else sx + search_width + px(14)
        actions = (
            (
                172,
                "Newest first" if self._sort == "recent" else "Title A–Z",
                self._sort_menu,
                "sort",
            ),
            (
                96,
                "Filter" + (" ·" if self._filter else ""),
                self._filter_menu,
                "filter",
            ),
            (88, "Select", self._start_selection, ""),
        )
        action_x = controls_x
        for canonical_width, label, action, icon in actions:
            action_width = min(width, px(canonical_width))
            if action_x and action_x + action_width > width:
                action_x = 0
                row_y += px(56)
            p.button(
                action_x,
                row_y,
                action_width,
                label,
                action,
                icon=icon,
                unit_scale=scale,
            )
            action_x += action_width + px(12)
        if self._route == "home":
            p.link(
                width - px(51),
                (control_y if reserve else y) + px(11),
                "See All",
                partial(self.navigate, "all"),
                width=px(51),
                unit_scale=scale,
            )
        return max(row_y + px(44), control_y + search_height) + px(20)

    def _paging_controls(
        self: Any, p: ScenePainter, page: Any, width: int, y: int
    ) -> int:
        metrics = window_logical_metrics(self)
        px, scale = metrics.px, metrics.scale
        self._rendered_count = len(page.items)
        self._matching_count = page.total
        if page.count <= 1:
            return y
        if page.index:
            p.button(
                0,
                y,
                px(110),
                "Previous",
                partial(self._change_page, -1),
                unit_scale=scale,
            )
        if page.index + 1 < page.count:
            p.button(
                px(124),
                y,
                px(110),
                "Next",
                partial(self._change_page, 1),
                unit_scale=scale,
            )
        p.text(
            width - px(180),
            y + px(13),
            f"Page {page.index + 1} of {page.count}",
            size=13,
            color=THEME["muted"],
            width=px(180),
            font_scale=scale,
        )
        return y + px(58)

    def _browse(self: Any, p: ScenePainter, width: int) -> int:
        metrics = window_logical_metrics(self)
        px, scale = metrics.px, metrics.scale
        p.text(0, 0, "Library", size=40, bold=True, font_scale=scale)
        p.text(
            0,
            px(53),
            "Your downloaded videos, audio, and collections.",
            size=16,
            color=THEME["muted"],
            width=width,
            font_scale=scale,
        )
        y = self._categories(p, width)
        columns = max(1, min(5, (width + px(14)) // px(200)))
        card = (width - px(14) * (columns - 1)) // columns
        if self._route in {"channels", "playlists", "collections"}:
            kind = self._route
            groups = self._groups(kind)
            y = self._toolbar(p, width, y, kind.title())
            if not groups:
                return self._empty_panel(
                    p, y, width, collections=True, filtered=bool(self._query)
                ) + px(20)
            indices, bottom = self._catalog_rows(groups, kind, columns, px(212), y)
            for n in indices:
                group = groups[n]
                self._collection_card(
                    p,
                    group,
                    kind,
                    n % columns * (card + px(14)),
                    y + n // columns * px(212),
                    card,
                )
            return bottom
        saved = self._matching_media()
        if self._route == "home":
            p.text(0, y, "Collections", size=24, bold=True, font_scale=scale)
            p.text(
                0,
                y + px(35),
                "Your playlists and personal collections.",
                size=14,
                color=THEME["muted"],
                width=width - px(80),
                font_scale=scale,
            )
            if self._records:
                p.link(
                    width - px(51),
                    y + px(5),
                    "See All",
                    partial(self.navigate, "collections"),
                    width=px(51),
                    unit_scale=scale,
                )
            cy = y + px(69)
            groups = watch_rails(self._records, collection_mode=True)
            kind = "collections" if groups else "playlists"
            groups = groups or watch_rails(self._records)
            if not saved:
                y = self._empty_panel(p, cy, width, collections=True) + px(35)
            else:
                shown_groups = groups[: max(1, columns - 1)]
                for n, group in enumerate(shown_groups):
                    self._collection_card(
                        p,
                        group,
                        kind,
                        n % columns * (card + px(14)),
                        cy + n // columns * px(212),
                        card,
                    )
                add_index = len(shown_groups)
                x = add_index % columns * (card + px(14))
                cy += add_index // columns * px(212)
                self._surface(
                    x,
                    cy,
                    card,
                    px(192),
                    fill=THEME["bg"],
                    edge=THEME["accent_dark"],
                    dashed=True,
                    unit_scale=scale,
                )
                self._surface(
                    x + card // 2 - px(26),
                    cy + px(30),
                    px(52),
                    px(52),
                    fill=THEME["accent_surface"],
                    edge=THEME["accent_dark"],
                    radius=px(26),
                    unit_scale=scale,
                )
                p.icon(
                    "plus",
                    x + card // 2 - px(11),
                    cy + px(45),
                    px(22),
                    THEME["icon"],
                    stroke_width=2 * scale,
                )
                self._center(
                    x + card // 2,
                    cy + px(101),
                    "Add Collection",
                    size=17,
                    color=THEME["action"],
                    unit_scale=scale,
                )
                self._center(
                    x + card // 2,
                    cy + px(132),
                    "Group downloads",
                    size=13,
                    color=THEME["muted"],
                    unit_scale=scale,
                )
                self._center(
                    x + card // 2,
                    cy + px(153),
                    "from any source.",
                    size=13,
                    color=THEME["muted"],
                    unit_scale=scale,
                )
                self._targets.append(
                    (
                        (x, cy, x + card, cy + px(192)),
                        partial(self._action, "collection", None),
                    )
                )
                y = cy + px(231)
        y = self._toolbar(
            p,
            width,
            y,
            "Recent Downloads"
            if self._route == "home"
            else self._category or "All Media"
            if self._route == "all"
            else self._route.title(),
        )
        if not saved:
            return self._empty_panel(
                p,
                y,
                width,
                filtered=bool(self._query or self._filter or self._group_key),
                actions=(
                    self._route != "home"
                    or bool(self._records)
                    or bool(self._query or self._filter or self._group_key)
                ),
            ) + px(20)
        stride = card * 9 // 16 + px(170)
        if self._route == "home":
            page = scene_page(saved, 0, columns)
            indices, bottom = self._catalog_rows(
                page.items, "media", columns, stride, y
            )
            self._matching_count = page.total
        else:
            indices, bottom = self._catalog_rows(saved, "media", columns, stride, y)
        for n in indices:
            index, row = saved[n]
            self._media_card(
                p,
                index,
                row,
                n % columns * (card + px(14)),
                y + n // columns * (card * 9 // 16 + px(170)),
                card,
            )
        return bottom

    def _render(self: Any) -> None:
        self._render_after: str | None = None
        if not self.winfo_ismapped():
            self._presentation_settle(rendered=False)
            return
        if (
            self.__dict__.get("_catalog_window")
            and "_catalog_pending_anchor" not in self.__dict__
        ):
            self._remember_catalog_anchor()
            self._catalog_pending_anchor = self.__dict__.get("_catalog_anchor")
        self._catalog_window = None
        with self._depth.frame():
            self.canvas.delete("all")
            draw_matte_backdrop(self.canvas)
            self._targets: list[Any] = []
            self._context_targets: list[Any] = []
            self._button_images: list[Any] = []
            self._button_labels: list[Any] = []
            self._rendered_count = 0
            self._matching_count = 0
            self._artwork_begin()
            p = ScenePainter(self)
            width = max(360, self.canvas.winfo_width() - 4)
            height = (
                self._details(p, width)
                if self._route == "detail"
                else self._browse(p, width)
            )
            self.canvas.configure(scrollregion=(0, 0, width, max(200, height)))
            restore = self.__dict__.pop("_catalog_restore_top", None)
            if restore is not None:
                self.canvas.yview_moveto(restore / max(200, height))
            pending_scroll = self.__dict__.get("_pending_scroll")
            if pending_scroll is not None:
                self._pending_scroll: float | None = None
                self.canvas.yview_moveto(pending_scroll)
            self._artwork_request()
            self._presentation_settle()
