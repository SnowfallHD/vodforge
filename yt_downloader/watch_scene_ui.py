"""Complete Watch scenes. Metadata owners supply identity and playback state."""

from __future__ import annotations

from collections import OrderedDict
from functools import partial
from typing import Any

from .archive_browser import resolve_archive_subject
from .library_state import format_duration
from .scene_components import ScenePainter
from .scene_paging import visible_scene_rows
from .ui_context_menu import ContextMenu
from .ui_theme import THEME
from .ui_transition import cancel_view_transition
from .watch_library import (
    WatchChannel,
    WatchRail,
    WatchVideo,
    unique_watch_videos,
    watch_channels,
    watch_media_summary,
    watch_rails,
)


class WatchSceneMixin:
    _scene_window: Any

    def _scene_strip(
        self: Any,
        key: str,
        items: Any,
        kind: str,
        y: int,
        width: int,
    ) -> int:
        from .scene_rail import SceneRail

        strips = self.__dict__.setdefault("_scene_rails", {})
        self._scene_used_rails.add(key)
        rail: Any = strips.get(key)
        if rail is None:
            rail = SceneRail(
                self.canvas,
                changed=self._queue_render,
                used=self._scene_catalog_scroll_used,
            )
            strips[key] = rail
            rail._fit = self._fit
            rail._cover = lambda record, x, y: type(self)._cover(rail, record, x, y)
            rail._paint_play_affordance = lambda box, tag: type(
                self
            )._paint_play_affordance(rail, box, tag)
            rail.canvas.bind(
                "<Motion>", lambda event: type(self)._hover(rail, event), add="+"
            )
            rail.canvas.bind(
                "<Leave>", lambda event: rail.canvas.delete("hover-play"), add="+"
            )

            def image(*args: Any, **kwargs: Any) -> Any:
                value = self._artwork_image(*args, **kwargs)
                if value is not None:
                    rail._images.append(value)
                return value

            rail._artwork_image = image
        rail._on_play, rail._on_details = self._on_play, self._on_details
        rail._scene_open, rail._navigate = self._scene_open, self._navigate
        rail._records = self._records
        rail._presentation_rendered = self._presentation_rendered
        rail._card_width, rail._card_height = self._card_width, self._card_height
        painter = ScenePainter(rail)
        height = (
            self._card_height + 66
            if kind == "media"
            else 92
            if kind == "channels"
            else 148
        )

        def draw(item: Any, x: int) -> None:
            if kind == "media":
                WatchSceneMixin._scene_media(rail, painter, item, x, 0)
            elif kind == "channels":
                WatchSceneMixin._scene_channel(
                    rail, painter, item, x, 0, self._card_width
                )
            else:
                WatchSceneMixin._scene_playlist(
                    rail, painter, item, x, 0, self._card_width
                )

        rail.present(
            items,
            y=y,
            width=width,
            height=height,
            stride=self._card_width + 14,
            draw=draw,
        )
        return y + height + 18

    def _scene_projection(
        self: Any, channel: str, query: str, collection_mode: bool
    ) -> tuple[tuple[WatchRail, ...], tuple[WatchVideo, ...]]:
        # Repaint/resize must not regroup the full catalog. Bound query variants,
        # and retire all derived identities when the authoritative snapshot changes.
        if self.__dict__.get("_scene_projection_records") is not self._records:
            self._scene_projection_records = self._records
            self._scene_projection_cache: OrderedDict[
                tuple[str, str, bool],
                tuple[tuple[WatchRail, ...], tuple[WatchVideo, ...]],
            ] = OrderedDict()
        key = (channel, query, collection_mode)
        cache = self._scene_projection_cache
        if key not in cache:
            rails = watch_rails(
                self._records,
                channel=channel,
                query=query,
                collection_mode=collection_mode,
            )
            unique = unique_watch_videos(
                self._records, tuple(video for rail in rails for video in rail.videos)
            )
            videos = tuple(sorted(unique, key=lambda video: min(video.indices)))
            cache[key] = (rails, videos)
            while len(cache) > 4:
                cache.popitem(last=False)
        cache.move_to_end(key)
        return cache[key]

    def _scene_catalog_scroll_used(self: Any) -> None:
        if (
            not self.__dict__.get("_closed")
            and (
                self.__dict__.get("_scene_window") or self.__dict__.get("_scene_rails")
            )
            and not self.__dict__.get("_scene_catalog_scroll_seen")
        ):
            self._scene_catalog_scroll_seen = True
            self._on_usage("watch", "catalog_scrolled")

    def _scene_scroll_command(self: Any, *arguments: Any) -> None:
        before = self.canvas.yview()
        self.canvas.yview(*arguments)
        if self.canvas.yview() != before:
            self._scene_catalog_scroll_used()

    def _scene_scroll_changed(self: Any, first: float, last: float) -> None:
        self._scene_scrollbar.set(first, last)
        for rail in self.__dict__.get("_scene_rails", {}).values():
            if rail.visible() != rail._active:
                rail.retire()
                self._queue_render()
        window = self.__dict__.get("_scene_window")
        if not window:
            return
        count, columns, stride, origin, rendered, _videos = window
        self._remember_scene_anchor()
        visible = visible_scene_rows(
            count,
            columns,
            stride,
            origin,
            self.canvas.canvasy(0),
            self.canvas.winfo_height(),
        )
        if visible != rendered:
            self._queue_render()

    def _scene_route_key(self: Any) -> tuple[str, str, str, str]:
        return (
            self._scene_route,
            self._channel,
            self._selected_playlist,
            self.search.get().strip(),
        )

    def _remember_scene_anchor(self: Any) -> None:
        window = self.__dict__.get("_scene_window")
        if not window:
            return
        count, columns, stride, origin, _visible, videos = window
        top = self.canvas.canvasy(0)
        if not count or top < origin:
            self._scene_anchor = None
            return
        index = min(count - 1, int((top - origin) // stride) * columns)
        self._scene_anchor = (
            self._scene_route_key(),
            videos[index].key,
            index,
            top - (origin + index // columns * stride),
        )

    def _scene_media_window(
        self: Any,
        p: ScenePainter,
        videos: tuple[WatchVideo, ...],
        y: int,
        columns: int,
    ) -> int:
        return self._scene_items_window(p, videos, y, columns, "media")

    def _scene_items_window(
        self: Any,
        p: ScenePainter,
        videos: Any,
        y: int,
        columns: int,
        kind: str,
    ) -> int:
        stride = (
            self._card_height + 66
            if kind == "media"
            else 96
            if kind == "channels"
            else 154
        )
        top = self.canvas.canvasy(0)
        pending = self.__dict__.pop("_scene_pending_anchor", None)
        if pending and pending[0] == self._scene_route_key() and videos:
            index = next(
                (
                    index
                    for index, video in enumerate(videos)
                    if video.key == pending[1]
                ),
                min(pending[2], len(videos) - 1),
            )
            extent = y + ((len(videos) + columns - 1) // columns) * stride
            top = min(
                max(0, extent - self.canvas.winfo_height()),
                y + index // columns * stride + pending[3],
            )
            self._scene_restore_top = top
        visible = visible_scene_rows(
            len(videos),
            columns,
            stride,
            y,
            top,
            self.canvas.winfo_height(),
        )
        self._scene_window = (len(videos), columns, stride, y, visible, videos)
        start, end = visible
        for index in range(start * columns, min(len(videos), end * columns)):
            x, row_y = (
                index % columns * (self._card_width + 14),
                y + index // columns * stride,
            )
            if kind == "media":
                self._scene_media(p, videos[index], x, row_y)
            elif kind == "channels":
                self._scene_channel(p, videos[index], x, row_y, self._card_width)
            else:
                self._scene_playlist(p, videos[index], x, row_y, self._card_width)
        return y + max(1, (len(videos) + columns - 1) // columns) * stride

    def _scene_start_queue(
        self: Any, videos: tuple[WatchVideo, ...], kind: str, shuffled: bool = False
    ) -> None:
        callback = self.__dict__.get("_on_queue")
        if callback is not None:
            callback(tuple(video.key for video in videos), kind, shuffled)

    def show_home(self: Any) -> None:
        cancel_view_transition(self)
        for rail in self.__dict__.get("_scene_rails", {}).values():
            rail.retire()
        self._scene_history: list[tuple[dict[str, Any], bool, float]] = []
        self.__dict__.get("_targets", []).clear()
        self._scene_route = "home"
        self._channel = ""
        self._selected_playlist = ""
        self._page = 0
        self.search.set("")
        self._presentation_change("navigation")
        self._scene_window = None
        self.__dict__.pop("_scene_pending_anchor", None)
        self.__dict__.pop("_scene_catalog_scroll_seen", None)
        self.canvas.yview_moveto(0)
        self._queue_render()

    def _scene_open(self: Any, route: str, *, playlist: str = "") -> None:
        cancel_view_transition(self)
        for rail in self.__dict__.get("_scene_rails", {}).values():
            rail.retire()
        if self.search.get() or (route, playlist) != (
            getattr(self, "_scene_route", "home"),
            getattr(self, "_selected_playlist", ""),
        ):
            history = self.__dict__.setdefault("_scene_history", [])
            history.append(
                (
                    {
                        **{
                            name: getattr(self, name, "" if name != "_page" else 0)
                            for name in (
                                "_scene_route",
                                "_selected_playlist",
                                "_channel",
                                "_mode",
                                "_page",
                            )
                        },
                        "_search_query": self.search.get(),
                        "_heading_text": self.heading_var.get()
                        if self.__dict__.get("heading_var") is not None
                        else "Watch",
                        "_subtitle_text": self.subtitle_var.get()
                        if self.__dict__.get("subtitle_var") is not None
                        else "",
                    },
                    bool(getattr(self, "_playlist_is_collection", False)),
                    self.canvas.yview()[0],
                )
            )
            del history[:-32]
        if self.search.get():
            self.search.set("")
        self.__dict__.get("_targets", []).clear()
        self._scene_route = route
        self._selected_playlist = playlist
        self._playlist_is_collection = bool(
            playlist and playlist.startswith("collection\0")
        )
        self._page = 0
        self._presentation_change("navigation")
        self._scene_window = None
        self.__dict__.pop("_scene_pending_anchor", None)
        self.__dict__.pop("_scene_catalog_scroll_seen", None)
        self.canvas.yview_moveto(0)
        self._queue_render()

    def _scene_back(self: Any) -> None:
        history = self.__dict__.get("_scene_history", [])
        if not history:
            self.show_home()
            return
        cancel_view_transition(self)
        for rail in self.__dict__.get("_scene_rails", {}).values():
            rail.retire()
        self.__dict__.get("_targets", []).clear()
        state, collection, scroll = history.pop()
        query = state.pop("_search_query", "")
        heading = state.pop("_heading_text", "Watch")
        subtitle = state.pop("_subtitle_text", "")
        if self.__dict__.get("heading_var") is not None:
            self.heading_var.set(heading)
        if self.__dict__.get("subtitle_var") is not None:
            self.subtitle_var.set(subtitle)
        if self.search.get() != query:
            self.search.set(query)
        for name, value in state.items():
            setattr(self, name, value)
        self._playlist_is_collection = collection
        self._scene_window = None
        self.__dict__.pop("_scene_pending_anchor", None)
        self.__dict__.pop("_scene_catalog_scroll_seen", None)
        self._presentation_change("navigation")
        self._render()
        self.canvas.yview_moveto(scroll)

    def _scene_back_label(self: Any) -> str:
        history = self.__dict__.get("_scene_history", [])
        if history and history[-1][0].get("_search_query"):
            return "Back to results"
        route = history[-1][0]["_scene_route"] if history else "home"
        return "Back to " + {
            "home": "Watch",
            "channel": "channel",
            "channels": "channels",
            "playlists": "playlists",
            "collections": "collections",
            "playlist": "playlist",
            "videos": "videos",
        }.get(route, "Watch")

    def _scene_more(self: Any, index: int) -> None:
        if not 0 <= index < len(self._records):
            return
        captured = dict(self._records[index])

        def show_original_details() -> None:
            current = resolve_archive_subject(self._records, captured)
            if current is not None:
                self._on_details(current[0])
            else:
                self._on_usage("watch", "details_retired")

        menu = ContextMenu(self, tearoff=False)
        menu.add_command(label="View in Library", command=show_original_details)
        menu.add_command(
            label="Browse personal categories",
            command=partial(self._scene_open, "collections"),
        )
        menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def _scene_heading(
        self: Any, p: ScenePainter, title: str, y: int, width: int, action: Any = None
    ) -> int:
        p.text(0, y, title, size=22, bold=True)
        if action:
            p.link(width - 50, y + 4, "See All", action, width=50)
        return y + 34

    def _scene_media(
        self: Any, p: ScenePainter, video: WatchVideo, x: int, y: int
    ) -> None:
        record = self._records[video.indices[0]]
        self._presentation_rendered.add(video.key)
        self._cover(record, x, y)
        box = (x, y, x + self._card_width, y + self._card_height)
        self._play_regions.append(box)
        self._targets.append((box, partial(self._on_play, video.indices[0])))
        p.text(
            x,
            y + self._card_height + 8,
            video.title,
            size=15,
            width=self._card_width,
            lines=1,
        )
        p.text(
            x,
            y + self._card_height + 30,
            format_duration(record.get("duration"))
            + (
                f"  \u00b7  {len(video.indices)} saved versions"
                if len(video.indices) > 1
                else ""
            ),
            size=15,
            color=THEME["muted"],
            width=self._card_width,
        )
        # Details are contextual to the card, revealed on hover/keyboard focus.
        detail = (
            x + self._card_width - 86,
            y + self._card_height - 42,
            x + self._card_width - 8,
            y + self._card_height - 10,
        )
        self._card_actions.append((box, detail))
        self._targets.append((detail, partial(self._on_details, video.indices[0])))

    def _scene_single_video(
        self: Any, p: ScenePainter, video: WatchVideo, y: int, width: int
    ) -> int:
        """Give a lone downloaded episode an intentional, useful full-width card."""
        record = self._records[video.indices[0]]
        self._presentation_rendered.add(video.key)
        observation_key = (self._scene_route, self._selected_playlist, video.key)
        if getattr(self, "_singleton_seen", None) != observation_key:
            self._singleton_seen = observation_key
            self._on_usage("watch", "singleton_shown")
        previous = self.canvas.find_all()
        beneath = previous[-1] if previous else None
        horizontal = width >= 700
        image_width = min(700, int(width * 0.52)) if horizontal else width - 32
        image_height = image_width * 9 // 16
        left, top = 16, y + 16
        self._depth.draw(
            (left, top, left + image_width, top + image_height), role="media"
        )
        artwork = self._artwork_image(record, tile_size=(image_width, image_height))
        if artwork:
            self.canvas.create_image(
                left, top, image=artwork, anchor="nw", tags="presentation-artwork"
            )
        else:
            p.icon(
                "play", left + image_width // 2 - 14, top + image_height // 2 - 16, 30
            )
        play = (
            partial(self._scene_start_queue, (video,), "playlist")
            if self._scene_route == "playlist"
            else partial(self._on_play, video.indices[0])
        )
        image_box = (left, top, left + image_width, top + image_height)
        self._play_regions.append(image_box)
        self._targets.append((image_box, play))
        text_x = image_width + 40 if horizontal else 20
        text_y = (
            top + max(8, (image_height - 260) // 2)
            if horizontal
            else top + image_height + 22
        )
        text_width = width - text_x - 24
        title_item = p.text(
            text_x,
            text_y,
            video.title,
            size=32 if horizontal else 26,
            bold=True,
            width=text_width,
            lines=2,
        )
        title_box = self.canvas.bbox(title_item)
        metadata_y = (title_box[3] if title_box else text_y + 58) + 10
        p.text(
            text_x,
            metadata_y,
            "  \u00b7  ".join(
                str(value)
                for value in (
                    format_duration(record.get("duration")),
                    record.get("vodforge_output_type"),
                    record.get("channel") or record.get("uploader"),
                )
                if value
            ),
            size=14,
            color=THEME["muted"],
            width=text_width,
        )
        description_y = metadata_y + 30
        description_item = p.text(
            text_x,
            description_y,
            str(
                record.get("description")
                or watch_media_summary(self._records, (video,)).fallback_description
            ),
            size=15,
            color=THEME["muted"],
            width=text_width,
            lines=2,
            prose=True,
        )
        description_box = self.canvas.bbox(description_item)
        button_y = (description_box[3] if description_box else description_y + 38) + 22
        p.button(
            text_x,
            button_y,
            120,
            "Play",
            play,
            primary=True,
            icon="play",
        )
        second_x = text_x + 134
        second_y = button_y
        if second_x + 180 > width - 20:
            second_x, second_y = text_x, button_y + 58
        p.button(
            second_x,
            second_y,
            180,
            "View in Library",
            partial(self._on_details, video.indices[0]),
            icon="folder",
        )
        bottom = max(top + image_height + 16, second_y + 64)
        background = self._depth.draw((0, y, width, bottom), role="singleton")
        if beneath is None:
            self.canvas.tag_lower(background)
        else:
            self.canvas.tag_raise(background, beneath)
        return bottom + 24

    def _scene_playlist(
        self: Any,
        p: ScenePainter,
        rail: WatchRail,
        x: int,
        y: int,
        width: int,
        height: int = 136,
    ) -> None:
        record = self._records[rail.videos[0].indices[0]]
        self._depth.draw((x, y, x + width, y + height))
        image = self._artwork_image(record, hero_size=(width, height), role="playlist")
        if image:
            self.canvas.create_image(
                x, y, image=image, anchor="nw", tags="presentation-artwork"
            )
        p.icon("list", x + 16, y + height - 87, 24)
        p.text(
            x + 16, y + height - 53, rail.title, size=16, bold=True, width=width - 32
        )
        media = watch_media_summary(self._records, rail.videos)
        p.text(
            x + 16,
            y + height - 28,
            media.label,
            size=14,
            color=THEME["muted"],
        )
        self._targets.append(
            (
                (x, y, x + width, y + height),
                partial(self._scene_open, "playlist", playlist=rail.key),
            )
        )
        self._presentation_rendered.update(video.key for video in rail.videos)

    def _scene_channel(
        self: Any,
        p: ScenePainter,
        channel: WatchChannel,
        x: int,
        y: int,
        width: int,
        height: int = 80,
    ) -> None:
        self._depth.draw((x, y, x + width, y + height))
        record = self._records[channel.videos[0].indices[0]]
        avatar_size = min(96, height - 20)
        avatar_y = y + (height - avatar_size) // 2
        text_x = x + avatar_size + 34
        avatar = self._artwork_image(
            record, tile_size=(avatar_size, avatar_size), role="avatar"
        )
        if avatar:
            self.canvas.create_image(
                x + 16, avatar_y, image=avatar, anchor="nw", tags="presentation-artwork"
            )
        else:
            self.canvas.create_oval(
                x + 16,
                avatar_y,
                x + 16 + avatar_size,
                avatar_y + avatar_size,
                fill=THEME["accent_surface"],
                outline="",
            )
            p.text(
                x + 16 + avatar_size // 2 - 12,
                y + height // 2 - 12,
                channel.name[:1].upper(),
                size=24,
                bold=True,
            )
        p.text(
            text_x,
            y + height // 2 - 19,
            channel.name,
            size=15,
            width=max(60, width - avatar_size - 48),
        )
        media = watch_media_summary(self._records, channel.videos)
        p.text(
            text_x,
            y + height // 2 + 6,
            media.label,
            size=14,
            color=THEME["muted"],
            width=max(60, width - avatar_size - 48),
        )
        self._targets.append(
            (
                (x, y, x + width, y + height),
                partial(self._navigate, "channels", channel.key),
            )
        )
        self._presentation_rendered.update(video.key for video in channel.videos)

    def _scene_small_library(
        self: Any, p: ScenePainter, rails: tuple[WatchRail, ...], y: int, width: int
    ) -> int:
        """A featured video already covers the only item; show its homes once."""
        collections, _videos = self._scene_projection(self._channel, "", True)
        if collections:
            y = self._scene_heading(
                p, "Collections", y, width, partial(self._scene_open, "collections")
            )
            y = self._scene_strip("collections", collections, "playlists", y, width)
        channels = watch_channels(self._records)
        split = width >= 800
        section_width = (width - 24) // 2 if split else width
        p.text(0, y, "Playlists", size=20, bold=True)
        p.link(
            section_width - 50,
            y + 4,
            "See All",
            partial(self._scene_open, "playlists"),
            width=50,
        )
        for index, rail in enumerate(rails[:2]):
            self._scene_playlist(p, rail, 0, y + 34 + index * 150, section_width)
        playlist_bottom = y + 34 + min(2, len(rails)) * 150
        channel_x = section_width + 24 if split else 0
        channel_y = y if split else playlist_bottom + 12
        p.text(channel_x, channel_y, "Channels", size=20, bold=True)
        p.link(
            channel_x + section_width - 50,
            channel_y + 4,
            "See All",
            partial(self._scene_open, "channels"),
            width=50,
        )
        if channels:
            self._scene_channel(
                p, channels[0], channel_x, channel_y + 34, section_width, height=136
            )
        return max(playlist_bottom, channel_y + 184) + 24

    def _scene_hero(
        self: Any, p: ScenePainter, video: WatchVideo, playlist: str, width: int
    ) -> int:
        record = self._records[video.indices[0]]
        self._presentation_rendered.add(video.key)
        self._observe_hero(video.key)
        media = watch_media_summary(self._records, (video,))
        progress = self._progress_for(record) if self._progress_for else None
        resume = (
            progress is not None and not progress.completed and progress.position >= 1
        )
        p.text(
            36,
            44,
            ("CONTINUE LISTENING" if media.kind == "audio" else "CONTINUE WATCHING")
            if resume
            else ("READY TO PLAY" if media.kind != "video" else "READY TO WATCH"),
            size=11,
            bold=True,
            color=THEME["muted"],
        )
        text_width = min(width - 72, max(268, min(620, width * 55 // 100)))
        title_item = p.text(
            36,
            72,
            video.title,
            size=40 if width >= 1000 else 32,
            bold=True,
            width=text_width,
            lines=2,
        )
        title_box = self.canvas.bbox(title_item)
        chips_y = max(132, title_box[3] + 14 if title_box else 132)
        p.chips(
            36,
            chips_y,
            [
                str(record.get("channel") or record.get("uploader") or ""),
                playlist,
                str(record.get("vodforge_output_type") or ""),
                format_duration(record.get("duration")),
            ],
            text_width,
            reserve_tail=2,
        )
        description_y = chips_y + 46
        description_item = p.text(
            36,
            description_y,
            str(record.get("description") or media.fallback_description),
            size=16,
            color=THEME["muted"],
            width=text_width,
            lines=2,
            prose=True,
        )
        description_box = self.canvas.bbox(description_item)
        content_bottom = description_box[3] if description_box else description_y + 36
        progress_y = max(242, content_bottom + 28)
        if resume and progress is not None:
            track_width = min(400, text_width - 130)
            self.canvas.create_line(
                40,
                progress_y,
                40 + track_width,
                progress_y,
                fill=THEME["border"],
                width=8,
                capstyle="round",
            )
            self.canvas.create_line(
                40,
                progress_y,
                40 + int(track_width * progress.fraction),
                progress_y,
                fill=THEME["progress"],
                width=8,
                capstyle="round",
            )
            p.text(
                56 + track_width,
                progress_y - 8,
                format_duration(progress.position)
                + " / "
                + format_duration(progress.duration),
                size=15,
                color=THEME["text"],
            )
        button_y = max(
            272 if width >= 1000 else 242,
            progress_y + 30 if resume else content_bottom + 32,
        )
        x = 36
        for button_width, label, callback, icon, primary in (
            (
                150,
                "Resume" if resume else "Play",
                partial(self._play_hero, video.indices[0]),
                "play",
                True,
            ),
            (
                181,
                "View in Library",
                partial(self._on_details, video.indices[0]),
                "folder",
                False,
            ),
            (54, "", partial(self._scene_more, video.indices[0]), "more", False),
        ):
            if x > 36 and x + button_width > width - 36:
                x, button_y = 36, button_y + 62
            p.button(
                x,
                button_y,
                button_width,
                label,
                callback,
                icon=icon,
                primary=primary,
            )
            x += button_width + 16
        height = button_y + 78
        surface = self._depth.draw((0, 0, width, height))
        self.canvas.tag_lower(surface)
        image = self._artwork_image(record, hero_size=(width, height))
        if image:
            background = self.canvas.create_image(
                0, 0, image=image, anchor="nw", tags="presentation-artwork"
            )
            self.canvas.tag_raise(background, surface)
        return height + 24

    def _scene_channel_header(
        self: Any,
        p: ScenePainter,
        channel: WatchChannel,
        width: int,
        rails: tuple[WatchRail, ...],
    ) -> int:
        p.button(
            0,
            0,
            190,
            WatchSceneMixin._scene_back_label(self)
            if self.__dict__.get("_scene_history")
            else "Back to channels",
            lambda: self._return_from_channel(),
            icon="back",
            quiet=True,
        )
        record = self._records[channel.videos[0].indices[0]]
        left = 214 if width >= 1000 else 174 if width >= 680 else 32
        avatar_size = 150 if width >= 1000 else 112
        title_y = 60 + (48 if width >= 1000 else 40 if width >= 680 else 178)
        text_width = min(620, width - left - 36)
        title_item = p.text(
            left,
            title_y,
            channel.name,
            size=32,
            bold=True,
            width=text_width,
            lines=2,
        )
        title_box = self.canvas.bbox(title_item)
        description_y = max(
            title_y + 52, title_box[3] + 16 if title_box else title_y + 52
        )
        description_item = p.text(
            left,
            description_y,
            str(
                record.get("channel_description")
                or self._channel_profile(record).get("description")
                or "Your saved media and playlists from " + channel.name + "."
            ),
            size=16,
            color=THEME["muted"],
            width=min(760, text_width),
            lines=2,
            prose=True,
        )
        description_box = self.canvas.bbox(description_item)
        count_y = max(
            description_y + 36,
            description_box[3] + 18 if description_box else description_y + 36,
        )
        count_item = p.text(
            left,
            count_y,
            watch_media_summary(self._records, channel.videos).label
            + "  \u00b7  "
            + f"{len(rails)} playlist"
            + ("s" if len(rails) != 1 else ""),
            size=15,
            color=THEME["muted"],
            width=text_width,
        )
        count_box = self.canvas.bbox(count_item)
        button_y = max(count_y + 36, count_box[3] + 20 if count_box else count_y + 36)
        x = left
        for button_width, label, callback, icon, primary in (
            (
                155,
                "Play Channel",
                partial(self._scene_start_queue, channel.videos, "channel"),
                "play",
                True,
            ),
            (
                125,
                "Shuffle",
                partial(self._scene_start_queue, channel.videos, "channel", True),
                "shuffle",
                False,
            ),
            (
                180,
                "View in Library",
                partial(self._on_details, channel.videos[0].indices[0]),
                "folder",
                False,
            ),
        ):
            if label == "Shuffle" and len(channel.videos) < 2:
                continue
            if x > left and x + button_width > width - 32:
                x, button_y = left, button_y + 58
            p.button(
                x, button_y, button_width, label, callback, icon=icon, primary=primary
            )
            x += button_width + 14
        height = max(310, button_y + 68)
        surface = self._depth.draw((0, 60, width, height), selected=True)
        self.canvas.tag_lower(surface)
        image = self._artwork_image(
            record, hero_size=(width, height - 60), role="banner"
        )
        if image:
            background = self.canvas.create_image(
                0, 60, image=image, anchor="nw", tags="presentation-artwork"
            )
            self.canvas.tag_raise(background, surface)
        avatar = self._artwork_image(
            record, tile_size=(avatar_size, avatar_size), role="avatar"
        )
        if avatar:
            self.canvas.create_image(
                32, 102, image=avatar, anchor="nw", tags="presentation-artwork"
            )
        return height + 28

    def _scene_empty(self: Any, p: ScenePainter, width: int, columns: int) -> int:
        # Empty-state artwork is app-owned: use the shared matte surface.
        # Real library hero artwork remains full color.
        self._depth.draw((0, 0, width, 394))
        p.text(
            36,
            31,
            "W E L C O M E   T O   V O D F O R G E",
            size=11,
            color=THEME["muted"],
        )
        p.text(36, 58, "Nothing to watch yet", size=40, bold=True, width=600)
        p.text(
            36,
            116,
            "Your downloaded videos and audio will appear here\nand be turned into a beautiful, streaming-like\nviewing experience automatically.",
            size=21,
            color=THEME["muted"],
            width=min(560, width - 72),
            lines=3,
        )
        p.button(
            36,
            219,
            217,
            "Go to Forge",
            self._on_forge,
            primary=True,
            icon="download",
        )
        p.button(
            270,
            219,
            225,
            "Open Library",
            self._on_library,
            icon="folder",
        )
        self.canvas.create_line(36, 306, 495, 306, fill=THEME["border"])
        self.canvas.create_oval(38, 330, 64, 356, outline=THEME["muted"], width=1.5)
        p.text(48, 333, "i", size=18, color=THEME["muted"])
        p.text(
            82,
            328,
            "Download a video in Forge or import media in Library\nto get started. It will show up here automatically.",
            size=16,
            color=THEME["muted"],
            width=min(475, width - 118),
            lines=2,
        )
        if width >= 1000:
            center = width * 73 // 100
            from PIL import ImageTk

            from .ui_chrome import watch_welcome_emblem

            emblem = ImageTk.PhotoImage(watch_welcome_emblem(), master=self.canvas)
            self._button_images.append(emblem)
            self.canvas.create_image(center - 128, 42, image=emblem, anchor="nw")
            p.text(
                center - 174,
                272,
                "Download. Organize. Watch Anywhere.",
                size=18,
                color=THEME["muted"],
            )
            p.text(
                center - 112,
                307,
                "Y O U R   M E D I A .   Y O U R   W A Y.",
                size=11,
                color=THEME["muted"],
            )
        y = 415
        columns = max(1, min(4, (width + 14) // 280))
        tile = (width - 14 * (columns - 1)) // columns
        for title, height in (
            ("Recently Added", 132),
            ("Playlists", 100),
            ("Channels", 96),
        ):
            y = self._scene_heading(p, title, y, width)
            for index in range(columns):
                x = index * (tile + 14)
                self._depth.draw((x, y, x + tile, y + height))
                if title == "Recently Added":
                    cx = x + tile // 2
                    self.canvas.create_polygon(
                        cx - 34,
                        y + 71,
                        cx - 11,
                        y + 40,
                        cx + 9,
                        y + 61,
                        cx + 20,
                        y + 50,
                        cx + 36,
                        y + 72,
                        fill=THEME["border"],
                        outline="",
                    )
                    self.canvas.create_oval(
                        cx + 20,
                        y + 22,
                        cx + 37,
                        y + 39,
                        fill=THEME["border"],
                        outline="",
                    )
                    self.canvas.create_line(
                        x + 26,
                        y + 92,
                        x + tile - 70,
                        y + 92,
                        fill=THEME["border"],
                        width=10,
                        capstyle="round",
                    )
                    self.canvas.create_line(
                        x + 26,
                        y + 111,
                        x + tile // 2 - 28,
                        y + 111,
                        fill=THEME["border"],
                        width=10,
                        capstyle="round",
                    )
                else:
                    if title == "Channels":
                        self.canvas.create_oval(
                            x + 22,
                            y + 20,
                            x + 78,
                            y + 76,
                            fill=THEME["border"],
                            outline="",
                        )
                    else:
                        p.icon("list", x + 36, y + 31, 28, THEME["subtle"])
                    self.canvas.create_line(
                        x + 110,
                        y + 39,
                        x + tile - 86,
                        y + 39,
                        fill=THEME["border"],
                        width=11,
                        capstyle="round",
                    )
                    self.canvas.create_line(
                        x + 110,
                        y + 61,
                        x + tile - 150,
                        y + 61,
                        fill=THEME["border"],
                        width=10,
                        capstyle="round",
                    )
            y += height + 27
        return y

    def _scene_pager(self: Any, p: ScenePainter, y: int, page: Any) -> int:
        if page.count <= 1:
            return y
        if page.index > 0:
            p.button(0, y, 110, "Previous", partial(self._change_page, -1))
        if page.index + 1 < page.count:
            p.button(124, y, 110, "Next", partial(self._change_page, 1))
        p.text(
            252,
            y + 13,
            f"Page {page.index + 1} of {page.count}",
            size=14,
            color=THEME["muted"],
        )
        return y + 58

    def _render_streaming_scene(self: Any, width: int, columns: int) -> None:
        p = ScenePainter(self)
        self._scene_used_rails: set[str] = set()
        self._browse_heading.grid_remove()
        self._browse_footer.grid_remove()
        self._scene_window = None
        query = self.search.get().strip()
        route = "videos" if query else self._scene_route
        rails, videos = self._scene_projection(
            self._channel,
            query,
            route == "collections"
            or (
                route == "playlist" and getattr(self, "_playlist_is_collection", False)
            ),
        )
        playlist = (
            next(
                (rail for rail in rails if rail.key == self._selected_playlist),
                None,
            )
            if route == "playlist"
            else None
        )
        if route == "playlist":
            videos = playlist.videos if playlist else ()
        self._presentation_matching = len(videos)
        self._presentation_mode_eligible = (
            len(videos)
            if route == "playlist"
            else len(
                self._scene_projection(
                    self._channel,
                    "",
                    route == "collections",
                )[1]
            )
        )
        if not videos and not query and route == "home":
            height = self._scene_empty(p, width, columns)
        else:
            y = 0
            if route not in {"home", "channel"}:
                p.button(
                    0,
                    0,
                    180,
                    WatchSceneMixin._scene_back_label(self),
                    partial(WatchSceneMixin._scene_back, self),
                    icon="back",
                    quiet=True,
                )
                y = 62
            if route == "home" and videos:
                featured = next(
                    (
                        video
                        for video in videos
                        if self._progress_for
                        and (
                            item := self._progress_for(self._records[video.indices[0]])
                        )
                        and not item.completed
                        and item.position >= 1
                    ),
                    videos[0],
                )
                playlist_label = next(
                    (rail.title for rail in rails if featured in rail.videos), ""
                )
                y = self._scene_hero(p, featured, playlist_label, width)
            if route == "channel":
                channel = next(
                    (
                        item
                        for item in watch_channels(self._records)
                        if self._channel in {item.key, item.name}
                    ),
                    None,
                )
                if channel:
                    y = self._scene_channel_header(p, channel, width, rails)
            if route == "home" and len(videos) == 1:
                y = self._scene_small_library(p, rails, y, width)
            elif route in {"home", "channel"}:
                if len(videos) > 1:
                    y = self._scene_heading(
                        p,
                        "Recently Added",
                        y,
                        width,
                        partial(self._scene_open, "videos"),
                    )
                    y = self._scene_strip("recent", videos, "media", y, width)
                collections, _collection_videos = self._scene_projection(
                    self._channel, "", True
                )
                if collections:
                    y = self._scene_heading(
                        p,
                        "Collections",
                        y,
                        width,
                        partial(self._scene_open, "collections"),
                    )
                    y = self._scene_strip(
                        "collections", collections, "playlists", y, width
                    )
                y = self._scene_heading(
                    p, "Playlists", y, width, partial(self._scene_open, "playlists")
                )
                y = self._scene_strip("playlists", rails, "playlists", y, width)
                if route == "home":
                    y = self._scene_heading(
                        p, "Channels", y, width, partial(self._scene_open, "channels")
                    )
                    y = self._scene_strip(
                        "channels", watch_channels(self._records), "channels", y, width
                    )
                else:
                    y = self._scene_heading(
                        p,
                        watch_media_summary(self._records, videos).heading,
                        y,
                        width,
                        partial(self._scene_open, "videos"),
                    )
                    if len(videos) == 1:
                        y = self._scene_single_video(p, videos[0], y, width)
                    else:
                        y = self._scene_strip(
                            "channel-videos", videos, "media", y, width
                        )
            elif route == "channels":
                y = self._scene_heading(p, "Channels", y, width)
                y = self._scene_items_window(
                    p,
                    watch_channels(self._records, query=query),
                    y,
                    columns,
                    "channels",
                )
            elif route in {"playlists", "collections"}:
                y = self._scene_heading(
                    p,
                    "Collections" if route == "collections" else "Playlists",
                    y,
                    width,
                )
                y = self._scene_items_window(p, rails, y, columns, "playlists")
            else:
                if route == "playlist" and playlist:
                    title = p.text(
                        0,
                        y,
                        playlist.title,
                        size=40,
                        bold=True,
                        width=width,
                        lines=2,
                    )
                    bounds = self.canvas.bbox(title)
                    subtitle_y = (bounds[3] if bounds else y + 48) + 12
                    creators = {
                        str(
                            self._records[video.indices[0]].get("channel")
                            or self._records[video.indices[0]].get("uploader")
                            or ""
                        )
                        for video in videos
                    } - {""}
                    subtitle = (
                        (
                            next(iter(creators)) + "  \u00b7  "
                            if len(creators) == 1
                            else ""
                        )
                        + watch_media_summary(self._records, videos).label
                        + " saved"
                    )
                    p.text(
                        0,
                        subtitle_y,
                        subtitle,
                        size=15,
                        color=THEME["muted"],
                        width=width,
                    )
                    y = subtitle_y + 48
                    if len(videos) > 1:
                        p.button(
                            0,
                            y,
                            154,
                            "Play playlist",
                            partial(self._scene_start_queue, videos, "playlist"),
                            primary=True,
                            icon="play",
                        )
                        p.button(
                            168,
                            y,
                            125,
                            "Shuffle",
                            partial(self._scene_start_queue, videos, "playlist", True),
                            icon="shuffle",
                        )
                        y += 62
                else:
                    y = self._scene_heading(
                        p,
                        "Search results"
                        if query
                        else watch_media_summary(self._records, videos).heading,
                        y,
                        width,
                    )
                if route == "playlist" and len(videos) == 1:
                    y = self._scene_single_video(p, videos[0], y, width)
                else:
                    y = self._scene_media_window(p, videos, y, columns)
                if not videos:
                    p.text(
                        0,
                        y,
                        "No videos found. Try another title, channel or playlist.",
                        color=THEME["muted"],
                        width=width,
                    )
                    y += 60
            height = y
        strips = self.__dict__.get("_scene_rails", {})
        for key in tuple(strips):
            if key not in self._scene_used_rails:
                strips.pop(key).destroy()
        self.canvas.configure(scrollregion=(0, 0, width, max(height, 200)))
        restore = self.__dict__.pop("_scene_restore_top", None)
        if restore is not None:
            self.canvas.yview_moveto(restore / max(height, 200))
        self._remember_scene_anchor()
        self._presentation_extra_canvases = tuple(
            rail.canvas for rail in strips.values() if rail._active and not rail._closed
        )
        self._paint_focus()
        self._artwork_request()
        self._presentation_settle()
