from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from functools import partial
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any

from .archive_artwork import ArchiveArtworkMixin
from .library_state import format_duration
from .run_identity import metadata_output_profile
from .ui_layout import ellipsize_wrapped_text
from .ui_theme import FONT_UI, FONT_UI_SMALL, THEME
from .ui_widgets import SleekScrollbar, bind_smooth_vertical_wheel
from .watch_library import WatchVideo, watch_rails


class WatchView(ArchiveArtworkMixin, ttk.Frame):
    """Playlist rails and channel destinations, backed by the Library projection."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_play: Callable[[int], None],
        on_details: Callable[[int], None],
        thumbnail_path: Callable[[dict[str, Any]], Any],
        on_usage: Callable[..., None] | None = None,
    ) -> None:
        super().__init__(master, style="FocusShell.TFrame")
        self._records: tuple[dict[str, Any], ...] = ()
        self._on_play, self._on_details, self._thumbnail_path = (
            on_play,
            on_details,
            thumbnail_path,
        )
        self._mode = "playlists"
        self._channel = ""
        self._page = 0
        self._offsets: dict[str, int] = {}
        self._targets: list[tuple[tuple[int, int, int, int], Callable[[], None]]] = []
        self._render_after: str | None = None
        self._closed = False
        self._keyboard_target = 0
        self._text_fonts: dict[Any, Any] = {}
        self._on_usage = on_usage or (lambda *args, **kwargs: None)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        heading = ttk.Frame(self, style="FocusShell.TFrame")
        heading.grid(row=0, column=0, sticky="ew", padx=18, pady=(20, 10))
        heading.columnconfigure(0, weight=1)
        self.heading_var = tk.StringVar(self, "Watch")
        ttk.Label(
            heading, textvariable=self.heading_var, style="FocusTitle.TLabel"
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            heading,
            text="Your saved playlists, channels and collections.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.search = tk.StringVar(self, "")
        ttk.Label(heading, text="Search saved videos", style="Muted.TLabel").grid(
            row=1, column=1, sticky="w", pady=(4, 0)
        )
        entry = ttk.Entry(heading, textvariable=self.search, width=28)
        entry.grid(row=0, column=1, sticky="e")
        self.search.trace_add("write", lambda *_args: self._filters_changed())
        filters = ttk.Frame(self, style="FocusShell.TFrame")
        filters.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 14))
        self._mode_buttons = {}
        for mode, label in (
            ("playlists", "Playlists"),
            ("channels", "Channels"),
            ("collections", "Collections"),
        ):
            button = ttk.Button(
                filters,
                text=label,
                command=partial(self._navigate, mode),
                style="FocusQuiet.TButton",
            )
            button.pack(side="left", padx=(0, 8))
            self._mode_buttons[mode] = button
        self.canvas = tk.Canvas(
            self, bg=THEME["bg"], highlightthickness=0, bd=0, takefocus=True
        )
        self.canvas.grid(row=2, column=0, sticky="nsew", padx=18)
        scrollbar = SleekScrollbar(self, command=self.canvas.yview)
        scrollbar.grid(row=2, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.bind("<Configure>", self._queue_render)
        self.canvas.bind("<Button-1>", self._click)
        bind_smooth_vertical_wheel(self.canvas, mode="pixels")
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
            "<FocusOut>", lambda event: self.canvas.delete("keyboard-focus")
        )
        footer = ttk.Frame(self, style="FocusShell.TFrame")
        footer.grid(row=3, column=0, sticky="ew", padx=18, pady=10)
        footer.columnconfigure(0, weight=1)
        self.count_var = tk.StringVar(self, "")
        ttk.Label(footer, textvariable=self.count_var, style="Muted.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(
            footer,
            text="Previous",
            command=lambda: self._change_page(-1),
            style="FocusQuiet.TButton",
        ).grid(row=0, column=1)
        ttk.Button(
            footer,
            text="Next",
            command=lambda: self._change_page(1),
            style="FocusQuiet.TButton",
        ).grid(row=0, column=2, padx=(6, 0))
        self._artwork_setup(thumbnail_path, (320, 180), "watch")
        self.bind("<Destroy>", self._destroyed, add="+")

    def set_records(self, records: Sequence[dict[str, Any]]) -> None:
        incoming = tuple(records)
        if incoming == self._records:
            return
        self._records = incoming
        self._artwork_attempted.clear()
        self._queue_render()

    def activate(self) -> None:
        for name, button in self._mode_buttons.items():
            button.configure(
                style="Accent.TButton" if name == self._mode else "FocusQuiet.TButton"
            )
        self._queue_render()

    def _navigate(self, mode: str, channel: str = "") -> None:
        self._on_usage("watch", "channel_opened" if channel else mode, watch_mode=mode)
        self._mode, self._channel, self._page = mode, channel, 0
        for name, button in self._mode_buttons.items():
            button.configure(
                style="Accent.TButton" if name == mode else "FocusQuiet.TButton"
            )
        self.heading_var.set(channel or "Watch")
        self.canvas.yview_moveto(0)
        self._queue_render()

    def _filters_changed(self) -> None:
        if self.search.get().strip():
            self._on_usage("watch", "searched")
        self._page = 0
        self._queue_render()

    def _change_page(self, delta: int) -> None:
        self._page = max(0, self._page + delta)
        self.canvas.yview_moveto(0)
        self._queue_render()

    def _queue_render(self, _event: Any = None) -> None:
        if not self._closed and self._render_after is None:
            self._render_after = self.after(24, self._render)

    def _button(
        self,
        x: int,
        y: int,
        width: int,
        label: str,
        action: Callable[[], None],
        *,
        accent: bool = False,
    ) -> None:
        bounds = (x, y, x + width, y + 34)
        self.canvas.create_rectangle(
            *bounds, fill=THEME["accent"] if accent else THEME["surface_2"], outline=""
        )
        self.canvas.create_text(
            x + width / 2, y + 17, text=label, fill=THEME["text"], font=FONT_UI_SMALL
        )
        self._targets.append((bounds, action))

    def _cover(self, record: dict[str, Any], x: int, y: int) -> None:
        self.canvas.create_rectangle(
            x, y, x + 320, y + 180, fill=THEME["surface_2"], outline=THEME["border"]
        )
        image = self._artwork_image(record)
        if image is not None:
            self.canvas.create_image(x, y, anchor="nw", image=image)
        else:
            self.canvas.create_polygon(
                x + 147,
                y + 68,
                x + 147,
                y + 112,
                x + 184,
                y + 90,
                fill=THEME["accent"],
                outline="",
            )
        self.canvas.create_rectangle(
            x + 262, y + 153, x + 312, y + 174, fill=THEME["panel"], outline=""
        )
        self.canvas.create_text(
            x + 287,
            y + 164,
            text=format_duration(record.get("duration")),
            fill=THEME["text"],
            font=FONT_UI_SMALL,
        )

    def _fit(
        self, value: str, width: int, lines: int, font: Any = FONT_UI_SMALL
    ) -> str:
        key = tuple(font)
        if key not in self._text_fonts:
            self._text_fonts[key] = tkfont.Font(root=self, font=font)
        return ellipsize_wrapped_text(
            str(value)[:2000],
            maximum_width=max(1, width),
            maximum_lines=lines,
            measure_width=self._text_fonts[key].measure,
        )

    def _paint_focus(self) -> None:
        self.canvas.delete("keyboard-focus")
        if not self._targets or self.canvas.focus_get() is not self.canvas:
            return
        self._keyboard_target = min(self._keyboard_target, len(self._targets) - 1)
        bounds, _action = self._targets[self._keyboard_target]
        self.canvas.create_rectangle(
            *bounds, outline=THEME["accent"], width=2, tags="keyboard-focus"
        )

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

    def _video(
        self,
        video: WatchVideo,
        x: int,
        y: int,
        *,
        singleton: bool = False,
        width: int = 700,
    ) -> int:
        record = self._records[video.indices[0]]
        self._cover(record, x, y)
        selected = video.indices[0]
        self._targets.append(
            ((x, y, x + 320, y + 180), partial(self._on_play, selected))
        )
        profile = metadata_output_profile(record)
        if len(video.indices) > 1:
            profile = f"{len(video.indices)} saved export versions · {profile}"
        if singleton:
            self._on_usage("watch", "singleton_shown")
        if singleton and width >= 620:
            left = x + 344
            text_width = width - 360
            title_item = self.canvas.create_text(
                left,
                y + 10,
                text=self._fit(video.title, text_width, 2, (FONT_UI[0], 18, "bold")),
                fill=THEME["text"],
                font=(FONT_UI[0], 18, "bold"),
                anchor="nw",
                width=text_width,
            )
            title_box = self.canvas.bbox(title_item)
            description_top = max(y + 60, (title_box[3] if title_box else y + 50) + 10)
            description = str(
                record.get("description") or "A saved video from this playlist."
            )
            description_item = self.canvas.create_text(
                left,
                description_top,
                text=self._fit(description, text_width, 3),
                fill=THEME["muted"],
                font=FONT_UI_SMALL,
                anchor="nw",
                width=text_width,
            )
            description_box = self.canvas.bbox(description_item)
            profile_top = max(
                y + 118,
                (description_box[3] if description_box else description_top) + 10,
            )
            profile_item = self.canvas.create_text(
                left,
                profile_top,
                text=self._fit(profile, text_width, 2),
                fill=THEME["muted"],
                font=FONT_UI_SMALL,
                anchor="nw",
                width=text_width,
            )
            profile_box = self.canvas.bbox(profile_item)
            controls_top = max(
                y + 148, (profile_box[3] if profile_box else profile_top) + 12
            )
            self._button(
                left,
                controls_top,
                96,
                "Play",
                partial(self._on_play, selected),
                accent=True,
            )
            self._button(
                left + 106,
                controls_top,
                126,
                "View in Library",
                partial(self._on_details, selected),
            )
            return max(192, controls_top - y + 46)
        self.canvas.create_text(
            x,
            y + 191,
            text=self._fit(video.title, 312, 2, FONT_UI),
            fill=THEME["text"],
            font=FONT_UI,
            anchor="nw",
            width=312,
        )
        self.canvas.create_text(
            x,
            y + 226,
            text=self._fit(profile, 312, 2),
            fill=THEME["muted"],
            font=FONT_UI_SMALL,
            anchor="nw",
            width=312,
        )
        self._button(
            x,
            y + 263,
            96,
            "Play",
            partial(self._on_play, selected),
            accent=True,
        )
        self._button(
            x + 106,
            y + 263,
            126,
            "View in Library",
            partial(self._on_details, selected),
        )
        return 310

    def _render(self) -> None:
        self._render_after = None
        if not self.winfo_ismapped():
            return
        self.canvas.delete("all")
        self._targets.clear()
        self._artwork_begin()
        width = max(340, self.canvas.winfo_width() - 4)
        query = self.search.get()
        rails = watch_rails(
            self._records,
            channel=self._channel,
            collection_mode=self._mode == "collections",
            query=query,
        )
        y = 8
        if self._mode == "channels" and not self._channel:
            channels = tuple(dict.fromkeys(rail.channel for rail in rails))
            per_page = 12
            self._page = min(self._page, max(0, (len(channels) - 1) // per_page))
            columns = max(1, width // 344)
            for position, channel in enumerate(
                channels[self._page * per_page : (self._page + 1) * per_page]
            ):
                items = [rail for rail in rails if rail.channel == channel]
                record = self._records[items[0].videos[0].indices[0]]
                x = (position % columns) * 344
                top = (position // columns) * 260 + 8
                self._cover(record, x, top)
                self.canvas.create_text(
                    x,
                    top + 191,
                    text=channel,
                    fill=THEME["text"],
                    font=FONT_UI,
                    anchor="nw",
                    width=320,
                )
                self.canvas.create_text(
                    x,
                    top + 218,
                    text=f"{len(items)} saved playlists / video groups",
                    fill=THEME["muted"],
                    font=FONT_UI_SMALL,
                    anchor="nw",
                    width=320,
                )
                self._targets.append(
                    (
                        (x, top, x + 320, top + 245),
                        partial(self._navigate, "channels", channel),
                    )
                )
            y = (
                max(
                    1,
                    (min(per_page, len(channels) - self._page * per_page) + columns - 1)
                    // columns,
                )
                * 260
            )
            self.count_var.set(f"{len(channels)} channels · Page {self._page + 1}")
        else:
            per_page = 4
            self._page = min(self._page, max(0, (len(rails) - 1) // per_page))
            for rail in rails[self._page * per_page : (self._page + 1) * per_page]:
                self.canvas.create_text(
                    0,
                    y,
                    text=rail.title,
                    fill=THEME["text"],
                    font=(FONT_UI[0], 16, "bold"),
                    anchor="nw",
                    width=max(180, width - 260),
                )
                count = f"{rail.downloaded_count} downloaded video" + (
                    "s" if rail.downloaded_count != 1 else ""
                )
                context = (
                    rail.channel + " · "
                    if rail.channel and rail.channel != self._channel
                    else ""
                ) + count
                self.canvas.create_text(
                    0,
                    y + 29,
                    text=context,
                    fill=THEME["muted"],
                    font=FONT_UI_SMALL,
                    anchor="nw",
                )
                if len(rail.videos) == 1:
                    height = self._video(
                        rail.videos[0], 0, y + 55, singleton=True, width=width
                    )
                else:
                    visible = min(6, max(1, width // 344))
                    offset = min(
                        self._offsets.get(rail.key, 0),
                        max(0, len(rail.videos) - visible),
                    )
                    self._offsets[rail.key] = offset
                    self._button(
                        width - 86,
                        y,
                        36,
                        "‹",
                        partial(self._move_rail, rail.key, -1),
                    )
                    self._button(
                        width - 44,
                        y,
                        36,
                        "›",
                        partial(self._move_rail, rail.key, 1),
                    )
                    for position, video in enumerate(
                        rail.videos[offset : offset + visible]
                    ):
                        self._video(video, position * 344, y + 55)
                    height = 310
                y += height + 96
            self.count_var.set(
                f"{len(rails)} {'collections' if self._mode == 'collections' else 'saved playlists / video groups'} · Page {self._page + 1}"
            )
        if not rails:
            self.canvas.create_text(
                20,
                40,
                text="Your saved videos will appear here.\nBrowse channels, playlists or your Library collections.",
                fill=THEME["muted"],
                font=FONT_UI,
                anchor="nw",
                width=width - 40,
            )
        self.canvas.configure(scrollregion=(0, 0, width, max(y, 200)))
        self._paint_focus()
        self._artwork_request()

    def _move_rail(self, key: str, delta: int) -> None:
        self._on_usage("watch", "rail_scrolled")
        self._offsets[key] = max(0, self._offsets.get(key, 0) + delta)
        self._queue_render()

    def _click(self, event: Any) -> None:
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        action = next(
            (
                action
                for (left, top, right, bottom), action in reversed(self._targets)
                if left <= x <= right and top <= y <= bottom
            ),
            None,
        )
        if action:
            action()

    def _wheel(self, event: Any) -> str:
        delta = int(event.delta)
        self.canvas.yview_scroll(
            -max(1, abs(delta) // 120) if delta > 0 else max(1, abs(delta) // 120),
            "units",
        )
        return "break"

    def _destroyed(self, event: Any) -> None:
        if event.widget is not self:
            return
        self._closed = True
        self._artwork_close()
        for after_id in (self._render_after,):
            if after_id:
                self.after_cancel(after_id)
