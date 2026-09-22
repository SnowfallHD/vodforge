from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from functools import partial
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any

from .archive_artwork import ArchiveArtworkMixin
from .archive_presentation import media_badge
from .library_search_ui import LibrarySearchField
from .library_state import format_duration
from .presentation_diagnostics import count_bucket
from .ui_button_contract import ProductButton
from .ui_canvas_actions import CanvasActions
from .ui_chrome import CanvasSurfaceCache, draw_scene_focus_material
from .ui_layout import ellipsize_wrapped_text
from .ui_materials import draw_matte_backdrop
from .ui_scrolling import bind_smooth_scroll
from .ui_theme import FONT_UI_SMALL, THEME
from .ui_transition import cancel_view_transition
from .ui_widgets import SleekScrollbar
from .watch_library import watch_channels, watch_rails
from .watch_scene_ui import WatchSceneMixin


class WatchView(WatchSceneMixin, ArchiveArtworkMixin, ttk.Frame):
    """Playlist rails and channel destinations, backed by the Library projection."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_play: Callable[[int], None],
        on_details: Callable[[int], None],
        on_queue: Callable[[Sequence[str], str, bool], None] | None = None,
        thumbnail_path: Callable[[dict[str, Any]], Any],
        on_usage: Callable[..., None] | None = None,
        telemetry: Any = None,
        artwork_source: Callable[..., Any] | None = None,
        channel_profile: Callable[..., Any] | None = None,
        on_forge: Callable[[], None] | None = None,
        on_library: Callable[[], None] | None = None,
        progress_for: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__(master, style="FocusShell.TFrame")
        self._records: tuple[dict[str, Any], ...] = ()
        self._on_play, self._on_details, self._thumbnail_path = (
            on_play,
            on_details,
            thumbnail_path,
        )
        self._on_queue = on_queue
        self._mode = "playlists"
        self._scene_route = "home"
        self._selected_playlist = ""
        self._on_forge = on_forge or (lambda: None)
        self._on_library = on_library or (lambda: None)
        self._progress_for = progress_for
        self._channel_profile = channel_profile or (lambda _record: {})
        self._channel = ""
        self._page = 0
        self._channel_return_state = (0, 0.0)
        self._channel_return_mode = "channels"
        self._initial_mode_set = False
        self._mode_origin = "default"
        self._presentation_eligible = 0
        self._presentation_matching = 0
        self._presentation_mode_eligible = 0
        self._presentation_mode_counts: dict[tuple[str, str], int] = {}
        self._presentation_rendered: set[str] = set()
        self._hero_seen_key = ""
        self._card_width = 320
        self._card_height = 180
        self._offsets: dict[str, int] = {}
        self._targets: list[tuple[tuple[int, int, int, int], Callable[[], None]]] = []
        self._play_regions: list[tuple[int, int, int, int]] = []
        self._render_after: str | None = None
        self._closed = False
        self._keyboard_target = 0
        self._text_fonts: dict[Any, Any] = {}
        self._on_usage = on_usage or (lambda *args, **kwargs: None)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        heading = ttk.Frame(self, style="FocusShell.TFrame")
        self._browse_heading = heading
        heading.grid(row=0, column=0, sticky="ew", padx=18, pady=(10, 10))
        heading.columnconfigure(0, weight=1)
        self.heading_var = tk.StringVar(self, "Watch")
        self._channel_heading = ttk.Label(
            heading, textvariable=self.heading_var, style="FocusActiveTitle.TLabel"
        )
        self.subtitle_var = tk.StringVar(self, "Your playlists, ready to watch.")

        self.search = tk.StringVar(self, "")
        self.search_field = LibrarySearchField(
            heading, variable=self.search, width=21, placeholder="Search saved videos"
        )
        self.search_field.grid(row=0, column=1, sticky="e")
        self.search.trace_add("write", lambda *_args: self._filters_changed())
        filters = ttk.Frame(heading, style="FocusShell.TFrame")
        filters.grid(row=0, column=0, sticky="w")
        self.back_button = ProductButton(
            filters,
            text="‹  All channels",
            command=self._return_from_channel,
            style="Media.FocusQuiet.TButton",
        )
        self.back_button.pack(side="right")
        self.back_button.pack_forget()
        self._mode_buttons = {}
        for mode, label in (
            ("playlists", "Playlists"),
            ("collections", "Categories"),
            ("channels", "Channels"),
        ):
            button = ProductButton(
                filters,
                text=label,
                command=partial(self._navigate, mode),
                width=8,
                style="Media.FocusNav.TButton",
            )
            button.pack(side="left", padx=(0, 8))
            self._mode_buttons[mode] = button
        self.canvas = tk.Canvas(
            self, bg=THEME["bg"], highlightthickness=0, bd=0, takefocus=True
        )
        self._depth = CanvasSurfaceCache(self.canvas)
        self._card_actions: list[
            tuple[tuple[int, int, int, int], tuple[int, int, int, int]]
        ] = []
        self.canvas.grid(row=2, column=0, sticky="nsew", padx=0, pady=(16, 0))
        scrollbar = SleekScrollbar(self, command=self._scene_scroll_command)
        scrollbar.grid(row=2, column=1, sticky="ns")
        self._scene_scrollbar = scrollbar
        self.canvas.configure(yscrollcommand=self._scene_scroll_changed)
        self.canvas.bind("<Configure>", self._queue_render)
        self._pointer_actions = CanvasActions(self.canvas, lambda: self._targets)
        self.canvas.bind("<Motion>", self._hover, add="+")
        self.canvas.bind("<Leave>", self._leave_hover, add="+")
        self.canvas.bind(
            "<Escape>",
            lambda event: self._return_from_channel() if self._channel else None,
        )
        bind_smooth_scroll(
            self.canvas, mode="pixels", on_scroll=self._scene_catalog_scroll_used
        )
        for sequence, delta in (
            ("<Right>", 1),
            ("<Down>", 1),
            ("<Left>", -1),
            ("<Up>", -1),
        ):
            self.canvas.bind(sequence, partial(self._focus_target, delta))
        self.canvas.bind("<Return>", self._activate_target)
        self.canvas.bind("<space>", self._activate_target)
        self.canvas.bind("<Next>", lambda event: self._change_page(1))
        self.canvas.bind("<Prior>", lambda event: self._change_page(-1))
        self.canvas.bind("<FocusIn>", lambda event: self._paint_focus())
        self.canvas.bind(
            "<FocusOut>",
            lambda event: self.canvas.delete("keyboard-focus", "focus-play"),
        )
        footer = ttk.Frame(self, style="FocusShell.TFrame")
        self._browse_footer = footer
        footer.grid(row=3, column=0, sticky="ew", padx=18, pady=10)
        footer.columnconfigure(0, weight=1)
        self.count_var = tk.StringVar(self, "")
        ttk.Label(footer, textvariable=self.count_var, style="Muted.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.previous = ProductButton(
            footer,
            text="Previous",
            command=lambda: self._change_page(-1),
            style="Media.FocusNav.TButton",
        )
        self.previous.grid(row=0, column=1)
        self.next = ProductButton(
            footer,
            text="Next",
            command=lambda: self._change_page(1),
            style="Media.FocusNav.TButton",
        )
        self.next.grid(row=0, column=2, padx=(6, 0))
        self._artwork_setup(
            thumbnail_path, (320, 180), "watch", source_path=artwork_source
        )
        self._presentation_setup(telemetry, "watch")
        self.bind("<Destroy>", self._destroyed, add="+")

    def set_records(self, records: Sequence[dict[str, Any]]) -> None:
        for rail in self.__dict__.get("_scene_rails", {}).values():
            rail.retire()
            rail._records = ()
        incoming = tuple(records)
        if incoming == self._records:
            return
        if self.__dict__.get("_scene_window"):
            self._remember_scene_anchor()
            self._scene_pending_anchor = self.__dict__.get("_scene_anchor")
        self._scene_window = None
        self._records = incoming
        # Hidden scenes may not repaint immediately. Release the retired snapshot
        # now, rather than retaining its records until a later visible render.
        self.__dict__.pop("_scene_projection_records", None)
        cache = self.__dict__.get("_scene_projection_cache")
        if cache is not None:
            cache.clear()
        if getattr(self, "_targets", None) is not None:
            self._targets.clear()
        self._presentation_mode_counts.clear()
        self._presentation_eligible = len(
            {video.key for rail in watch_rails(incoming) for video in rail.videos}
        )
        self._presentation_change("data")
        if not self._initial_mode_set and watch_rails(incoming):
            self._initial_mode_set = True
            if watch_rails(incoming, collection_mode=True):
                self._mode = "collections"
        self._artwork_attempted.clear()
        self._queue_render()

    def activate(self) -> None:
        for name, button in self._mode_buttons.items():
            button.configure(
                style="FocusNavActive.TButton"
                if name == self._mode
                else "FocusNav.TButton"
            )
        self._queue_render()

    def _return_from_channel(self) -> None:
        if self.__dict__.get("_scene_history"):
            self._scene_back()
        else:
            self._navigate(self._channel_return_mode, restore=True)

    def _navigate(self, mode: str, channel: str = "", *, restore: bool = False) -> None:
        cancel_view_transition(self)
        for rail in self.__dict__.get("_scene_rails", {}).values():
            rail.retire()
        if channel:
            self._scene_open("channel")
        else:
            self._scene_history = []
        self._targets.clear()
        self._scene_route = "channel" if channel else mode
        returning = restore and bool(self._channel)
        if channel and not self._channel:
            self._channel_return_state = (self._page, self.canvas.yview()[0])
            self._channel_return_mode = self._mode
        if returning:
            mode = self._channel_return_mode
        self._initial_mode_set = True
        self._mode_origin = "user"
        self._presentation_change("navigation")
        self._on_usage("watch", "channel_opened" if channel else mode, watch_mode=mode)
        self._mode, self._channel, self._page = mode, channel, 0
        self.activate()
        self.heading_var.set(
            next(
                (
                    item.name
                    for item in watch_channels(self._records)
                    if item.key == channel
                ),
                channel,
            )
            or "Watch"
        )
        self.subtitle_var.set(
            "Saved playlists and videos from this channel."
            if channel
            else "Browse the channels in your library."
            if mode == "channels"
            else "Your personal Library categories, ready to watch."
            if mode == "collections"
            else "Your playlists, ready to watch."
        )
        if channel:
            self.back_button.configure(
                text="‹  All channels"
                if self._channel_return_mode == "channels"
                else "‹  Back to browse"
            )
            self.back_button.pack(side="right", padx=(14, 0))
            self._channel_heading.grid(
                row=1, column=0, columnspan=2, sticky="w", pady=(12, 0)
            )
        else:
            self.back_button.pack_forget()
            self._channel_heading.grid_remove()
        self._scene_window = None
        self.__dict__.pop("_scene_pending_anchor", None)
        self.__dict__.pop("_scene_catalog_scroll_seen", None)
        self.canvas.yview_moveto(0)
        if returning:
            self._page, scroll = self._channel_return_state
            self._render()
            self.canvas.yview_moveto(scroll)
        else:
            self._queue_render()

    def _filters_changed(self) -> None:
        cancel_view_transition(self)
        for rail in self.__dict__.get("_scene_rails", {}).values():
            rail.retire()
        self._presentation_change("filter")
        if self.search.get().strip():
            self._on_usage("watch", "searched")
        self._page = 0
        self._scene_window = None
        self.__dict__.pop("_scene_pending_anchor", None)
        self.__dict__.pop("_scene_catalog_scroll_seen", None)
        self.canvas.yview_moveto(0)
        self._queue_render()

    def _change_page(self, delta: int) -> None:
        if self.__dict__.get("_scene_window"):
            self._scene_scroll_command("scroll", delta, "pages")
            return
        self._presentation_change("navigation")
        self._page = max(0, self._page + delta)
        self.canvas.yview_moveto(0)
        self._queue_render()

    def _queue_render(self, _event: Any = None) -> None:
        self._queue_scene_render(_event)

    def _cover(
        self, record: dict[str, Any], x: int, y: int, *, duration: bool = True
    ) -> None:
        width, height = self._card_width, self._card_height
        self._depth.draw((x, y, x + width, y + height))
        image = self._artwork_image(record)
        if image is not None:
            self.canvas.create_image(
                x, y, anchor="nw", image=image, tags=("presentation-artwork",)
            )
        else:
            self.canvas.create_polygon(
                x + width / 2 - 12,
                y + height / 2 - 18,
                x + width / 2 - 12,
                y + height / 2 + 18,
                x + width / 2 + 17,
                y + height / 2,
                fill=THEME["accent"],
                outline="",
            )
        if duration:
            media_badge(
                self.canvas,
                format_duration(record.get("duration")),
                right=x + width - 8,
                bottom=y + height - 8,
                maximum_width=width - 16,
                font=FONT_UI_SMALL,
                fill=THEME["panel"],
                foreground=THEME["text"],
            )

    def _fit(
        self, value: str, width: int, lines: int, font: Any = FONT_UI_SMALL
    ) -> str:
        key = tuple(font)
        if key not in self._text_fonts:
            self._text_fonts[key] = tkfont.Font(
                root=self,
                family=key[0],
                size=key[1],
                weight=key[2] if len(key) > 2 else "normal",
            )
        return ellipsize_wrapped_text(
            str(value)[:2000],
            maximum_width=max(1, width),
            maximum_lines=lines,
            measure_width=self._text_fonts[key].measure,
        )

    def _paint_focus(self) -> None:
        self.canvas.delete("keyboard-focus")
        self.canvas.delete("focus-play")
        if not self._targets or self.canvas.focus_get() is not self.canvas:
            return
        self._keyboard_target = min(self._keyboard_target, len(self._targets) - 1)
        bounds, _action = self._targets[self._keyboard_target]
        draw_scene_focus_material(self.canvas, bounds)
        card = next(
            (
                cover
                for cover, details in self._card_actions
                if bounds in (cover, details)
            ),
            None,
        )
        if card is not None:
            self._paint_play_affordance(card, "focus-play")
            self.canvas.tag_raise("keyboard-focus")
        elif bounds in self._play_regions:
            self._paint_play_affordance(bounds, "focus-play")

    def _focus_target(self, delta: int, _event: Any = None) -> str:
        if self._targets:
            self._keyboard_target = max(
                0, min(len(self._targets) - 1, self._keyboard_target + delta)
            )
            bounds, _action = self._targets[self._keyboard_target]
            top, bottom = (
                self.canvas.canvasy(0),
                self.canvas.canvasy(self.canvas.winfo_height()),
            )
            if bounds[1] < top or bounds[3] > bottom:
                region = self.canvas.bbox("all")
                if region:
                    self.canvas.yview_moveto(max(0, bounds[1] - 12) / max(1, region[3]))
            self._paint_focus()
        return "break"

    def _activate_target(self, _event: Any = None) -> str:
        if self._targets:
            self._targets[min(self._keyboard_target, len(self._targets) - 1)][1]()
        return "break"

    def _observe_hero(self, key: str) -> None:
        if key != self._hero_seen_key:
            self._hero_seen_key = key
            self._on_usage("watch", "hero_shown", watch_mode=self._mode)

    def _play_hero(self, index: int) -> None:
        self._on_usage("watch", "hero_played", watch_mode=self._mode)
        self._on_play(index)

    def _render(self) -> None:
        if self._render_after is not None:
            self.after_cancel(self._render_after)
        self._render_after = None
        if not self.winfo_ismapped():
            self._presentation_settle(rendered=False)
            return
        if self.__dict__.get("_scene_window") and not self.__dict__.get(
            "_scene_pending_anchor"
        ):
            self._remember_scene_anchor()
            self._scene_pending_anchor = self.__dict__.get("_scene_anchor")
        self._presentation_rendered.clear()
        with self._depth.frame():
            self.canvas.delete("all")
            draw_matte_backdrop(self.canvas)
            self._button_images: list[Any] = []
            self._button_labels: list[Any] = []
            self._targets.clear()
            self._play_regions.clear()
            self._card_actions.clear()
            width = max(340, self.canvas.winfo_width() - 4)
            columns = max(1, min(5, (width + 14) // 244))
            self._card_width = (width - 14 * (columns - 1)) // columns
            numerator, denominator = getattr(self, "_thumbnail_aspect", (9, 20))
            self._card_height = self._card_width * numerator // denominator
            self._artwork_resize((self._card_width, self._card_height))
            self._artwork_begin()
            self._render_streaming_scene(width, columns)

    def _presentation_dimensions(self) -> dict[str, str]:
        return {
            "presentation_mode": "channel" if self._channel else self._mode,
            "mode_origin": self._mode_origin,
            "presentation_population": "saved_media",
            "eligible_bucket": count_bucket(self._presentation_eligible),
            "mode_eligible_bucket": count_bucket(self._presentation_mode_eligible),
            "query_state": "active" if self.search.get().strip() else "inactive",
            "filter_state": "inactive",
            "matching_bucket": count_bucket(self._presentation_matching),
            "rendered_bucket": count_bucket(len(self._presentation_rendered)),
        }

    def _move_rail(self, key: str, delta: int) -> None:
        self._presentation_change("navigation")
        self._on_usage("watch", "rail_scrolled")
        self._offsets[key] = max(0, self._offsets.get(key, 0) + delta)
        self._queue_render()

    def _leave_hover(self, _event: Any) -> None:
        self.canvas.configure(cursor="")
        self.canvas.delete("hover-play")
        for _bounds, label, normal, enabled in getattr(self, "_button_labels", ()):
            self.canvas.itemconfigure(
                label, fill=normal if enabled else THEME["subtle"]
            )

    def _paint_play_affordance(
        self, region: tuple[int, int, int, int], tag: str
    ) -> None:
        left, top, right, bottom = region
        details = next(
            (box for cover, box in self._card_actions if cover == region), None
        )
        controls = (
            [
                ((left + 8, bottom - 42, left + 76, bottom - 10), "Play"),
                (details, "Details"),
            ]
            if details
            else [
                (
                    (
                        (left + right) // 2 - 38,
                        (top + bottom) // 2 - 18,
                        (left + right) // 2 + 38,
                        (top + bottom) // 2 + 18,
                    ),
                    "Play",
                )
            ]
        )
        for bounds, label in controls:
            background = self._depth.draw(bounds, role="action")
            self.canvas.addtag_withtag(tag, background)
            self.canvas.create_text(
                (bounds[0] + bounds[2]) / 2,
                (bounds[1] + bounds[3]) / 2,
                text=label,
                fill=THEME["text"],
                font=FONT_UI_SMALL,
                tags=tag,
            )

    def _hover(self, event: Any) -> None:
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        active = any(
            left <= x <= right and top <= y <= bottom
            for (left, top, right, bottom), _action in self._targets
        )
        self.canvas.configure(cursor="hand2" if active else "")
        for bounds, label, normal, enabled in self._button_labels:
            hovered = bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]
            self.canvas.itemconfigure(
                label,
                fill=THEME["text"]
                if hovered and enabled
                else normal
                if enabled
                else THEME["subtle"],
            )
        self.canvas.delete("hover-play")
        region = next(
            (
                box
                for box in self._play_regions
                if box[0] <= x <= box[2] and box[1] <= y <= box[3]
            ),
            None,
        )
        if region:
            self._paint_play_affordance(region, "hover-play")

    def _destroyed(self, event: Any) -> None:
        if event.widget is not self:
            return
        self._closed = True
        self._depth.clear()
        self._artwork_close()
        for after_id in (self._render_after,):
            if after_id:
                self.after_cancel(after_id)
