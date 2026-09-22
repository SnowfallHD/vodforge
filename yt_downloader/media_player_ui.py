from __future__ import annotations

import io
import math
import queue
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from collections import deque
from collections.abc import Callable, Sequence
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from .failure_diagnostics import FailureDiagnostic, capture_failure, classify_failure
from .history import sanitize_chapters, sanitize_heatmap
from .media_preview import MediaPreviewOwner
from .playback_backend import (
    MediaPlayerError,
    PlaybackBackend,
    PlaybackSnapshot,
    VolumeObservation,
)
from .playback_progress import PlaybackProgressOwner
from .playback_progress_binding import PlaybackProgressBinding
from .playback_surface import TkPlaybackSurfaceOwner
from .player_presentation_ui import PlayerPresentationMixin
from .player_scene_ui import PlayerSceneMixin
from .ui_button_contract import ProductButton
from .ui_chrome import prototype_treeview_style, rounded_alpha
from .ui_layout import (
    centered_toplevel_geometry,
    ellipsize_wrapped_text,
    window_logical_metrics,
)
from .ui_theme import FONT_UI, FONT_UI_MEDIUM, FONT_UI_SMALL, THEME
from .ui_widgets import (
    ActionDialogSurface,
    KeyboardScope,
    SleekScrollbar,
    ToolTip,
    _tinted_ui_icon,
    bind_smooth_vertical_wheel,
    reveal_toplevel,
)
from .watch_library import watch_media_kind

try:
    from PIL import Image, ImageDraw, ImageOps, ImageTk
except ImportError:  # pragma: no cover - required by production package
    Image = ImageDraw = ImageOps = ImageTk = None  # type: ignore[assignment]

PREVIEW_WIDTH = 132
PREVIEW_HEIGHT = 74
CHAPTER_ROWS_MAX = 8
DETAIL_ROWS_MAX = 12


class PosterPlayButton(ProductButton):
    """Native button whose rounded corners show the poster beneath it.

    Tk child windows cannot expose a sibling image through transparent pixels.
    Composite the poster crop into the existing button chrome instead.
    """

    def __init__(self, master: tk.Misc, *, command: Callable[[], Any]) -> None:
        super().__init__(master, text="▶  Play", command=command, takefocus=True)
        self._poster: Any = None
        self._poster_origin = (1, 1)
        self._backgrounds = [
            ImageTk.PhotoImage(Image.new("RGB", (176, 48), "black"), master=self)
            for _ in range(2)
        ]
        style = ttk.Style(self)
        name = "PosterPlay.Accent.TButton"
        style.layout(name, [("Button.label", {"sticky": ""})])
        self.configure(
            {
                "style": name,
                "compound": "center",
                "image": (
                    self._backgrounds[0],
                    "active",
                    self._backgrounds[1],
                    "pressed",
                    self._backgrounds[1],
                    "focus",
                    self._backgrounds[1],
                ),
            },
        )
        self.bind("<Configure>", self._paint_background, add="+")
        self._paint_background()

    def set_poster(self, image: Any, origin: tuple[int, int]) -> None:
        self._poster, self._poster_origin = image, origin
        self._paint_background()

    def _paint_background(self, _event: tk.Event[Any] | None = None) -> None:
        width, height = 176, 48
        left = self.winfo_x() - self._poster_origin[0]
        top = self.winfo_y() - self._poster_origin[1]
        background = (
            self._poster.crop((left, top, left + width, top + height))
            if self._poster is not None
            else Image.new("RGB", (width, height), "black")
        )
        from .ui_chrome import action_button_image

        for photo, state in zip(self._backgrounds, ("normal", "hover"), strict=True):
            composed = background.convert("RGBA")
            composed.alpha_composite(
                action_button_image(width, height, accent=True, state=state)
            )
            photo.paste(composed.convert("RGB"))

    def apply_theme(self) -> None:
        self._paint_background()


class PlayerTransportButton(ProductButton):
    """Image-backed native button; playback state remains engine-owned."""

    def __init__(self, parent: tk.Misc, *, command: Callable[[], Any]) -> None:
        self._metrics = window_logical_metrics(parent)
        self._icons = {
            label: _tinted_ui_icon(
                icon,
                size=(self._metrics.px(18),) * 2,
                color=THEME["icon"],
                widget=parent,
            )
            for label, icon in (("Play", "play"), ("Pause", "pause"))
        }
        super().__init__(
            parent,
            text="Play",
            image=self._icons["Play"] or "",
            command=command,
            style="Transport.TButton",
            compound="none",
            width=0,
            takefocus=True,
        )
        ToolTip(self, lambda: f"{self.cget('text')} (Space)")

    def configure(self, cnf: Any = None, **kwargs: Any) -> Any:
        if kwargs.get("text") in self._icons:
            kwargs["image"] = self._icons[kwargs["text"]]
        return super().configure(cnf, **kwargs)

    def apply_theme(self) -> None:
        for label, icon in (("Play", "play"), ("Pause", "pause")):
            self._icons[label] = _tinted_ui_icon(
                icon, size=(self._metrics.px(18),) * 2, color=THEME["icon"], widget=self
            )
        self.configure(text=str(self.cget("text")))


def format_playback_time(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def heatmap_buckets(
    heatmap: list[dict[str, float]], duration: float, count: int
) -> tuple[float, ...]:
    if duration <= 0 or count <= 0:
        return ()
    buckets = [0.0] * count
    for point in heatmap:
        midpoint = (point["start_time"] + point["end_time"]) / 2
        index = min(count - 1, max(0, int((midpoint / duration) * count)))
        buckets[index] = max(buckets[index], point["value"])
    return tuple(buckets)


def bounded_content_rows(
    content: str | int,
    *,
    minimum: int = 3,
    maximum: int = 8,
) -> int:
    """Return a compact, bounded row count for player detail surfaces."""

    if isinstance(content, int):
        count = content
    else:
        lines = str(content or "").splitlines() or [""]
        count = sum(max(1, (len(line) + 35) // 36) for line in lines)
    return min(maximum, max(minimum, count))


def apply_preview_image(label: tk.Label, image: Any) -> None:
    """Assign a preview without retaining the placeholder's text dimensions.

    Tk interprets Label ``width`` and ``height`` as character units while text is
    displayed, but as pixels after an image is assigned.  Reassert the intended
    pixel dimensions at the same time as the image so the placeholder's 16 x 4
    character geometry cannot clip a 132 x 74 thumbnail.
    """

    label.configure(
        image=image,
        text="",
        width=PREVIEW_WIDTH,
        height=PREVIEW_HEIGHT,
    )


class PlayerVolumeControl(tk.Canvas):
    """Own one compact volume binding and its minimal Canvas rendering."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        variable: tk.IntVar,
        command: Any,
        width: int = 92,
        background: str | None = None,
    ) -> None:
        self._metrics = window_logical_metrics(master)
        super().__init__(
            master,
            width=self._metrics.px(width),
            height=self._metrics.px(22),
            bg=background or THEME["bg"],
            bd=0,
            highlightthickness=0,
            cursor="hand2",
            takefocus=True,
        )
        self.variable = variable
        self.command = command
        self._rendered_value: tuple[object, ...] | None = None
        self._trace = variable.trace_add("write", self._value_changed)
        self.bind("<Configure>", self._draw)
        self.bind("<FocusIn>", self._draw)
        self.bind("<FocusOut>", self._draw)
        self.bind("<Button-1>", self._set_from_pointer)
        self.bind("<B1-Motion>", self._set_from_pointer)
        self.bind("<Left>", lambda _event: self._step(-5))
        self.bind("<Right>", lambda _event: self._step(5))
        self.bind("<Home>", lambda _event: self._set_value(0))
        self.bind("<End>", lambda _event: self._set_value(100))
        self.bind("<Destroy>", self._destroyed, add="+")

    def _value_changed(self, *_args: object) -> None:
        self._draw()
        self.command(str(self.variable.get()))

    def _set_from_pointer(self, event: tk.Event[Any]) -> str:
        width = max(1, self.winfo_width() - self._metrics.px(16))
        value = round(min(1.0, max(0.0, (event.x - self._metrics.px(8)) / width)) * 100)
        self._set_value(value)
        self.focus_set()
        return "break"

    def _step(self, amount: int) -> str:
        self._set_value(self.variable.get() + amount)
        return "break"

    def _set_value(self, value: int) -> str:
        self.variable.set(min(100, max(0, int(value))))
        return "break"

    def _draw(self, _event: tk.Event[Any] | None = None) -> None:
        try:
            width = max(self._metrics.px(24), self.winfo_width())
            value = min(100, max(0, int(self.variable.get())))
        except (tk.TclError, ValueError):
            return
        focused = self.focus_get() is self
        signature = (
            width,
            value,
            focused,
            THEME["border"],
            THEME["progress"],
            THEME["text"],
            THEME["accent_dark"],
            THEME["focus_surface"],
        )
        if signature == self._rendered_value:
            return
        self._rendered_value = signature
        self.delete("all")
        if focused:
            from .platform_services import create_surface_image, surface_backing_scale
            from .ui_chrome import field_border_image

            scale = surface_backing_scale(self)
            height = self._metrics.px(22)
            surface = field_border_image(
                width,
                height,
                focused=True,
                density=scale,
                unit_scale=self._metrics.scale,
            )
            self._focus_image, _ = create_surface_image(
                self,
                surface,
                scale,
                logical_size=(width, height),
                existing=getattr(self, "_focus_image", None),
            )
            self.create_image(
                0, 0, image=self._focus_image, anchor="nw", tags="focus-material"
            )
        px = self._metrics.px
        left, right, center = px(8), width - px(8), px(11)
        x = left + ((right - left) * value / 100)
        from .ui_chrome import draw_matte_track

        draw_matte_track(
            self, left, center, right, value / 100, unit_scale=self._metrics.scale
        )
        self.create_oval(
            x - px(6),
            center - px(6),
            x + px(6),
            center + px(6),
            fill=THEME["text"],
            outline=THEME["accent_dark"],
            width=px(2),
        )

    def apply_theme(self) -> None:
        self.configure(bg=THEME["bg"])
        self._rendered_value = None
        self._draw()

    def _destroyed(self, event: tk.Event[Any]) -> None:
        if event.widget is not self:
            return
        try:
            self.variable.trace_remove("write", self._trace)
        except tk.TclError:
            pass


class ChapterList(ttk.Treeview):
    """Native keyboard/scroll/selection with readable chapter rows."""

    def __init__(self, parent: tk.Misc, chapters: list[dict[str, Any]]) -> None:
        metrics = window_logical_metrics(parent)
        super().__init__(
            parent,
            columns=("title", "time"),
            show="",
            selectmode="browse",
            height=bounded_content_rows(len(chapters), maximum=CHAPTER_ROWS_MAX),
            style=prototype_treeview_style(parent, "Player.Chapters.Treeview"),
            takefocus=True,
        )
        self.column(
            "title", width=metrics.px(180), minwidth=metrics.px(80), stretch=True
        )
        self.column(
            "time",
            width=metrics.px(50),
            minwidth=metrics.px(44),
            stretch=False,
            anchor="e",
        )
        for index, chapter in enumerate(chapters):
            self.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    chapter["title"] or "Untitled chapter",
                    format_playback_time(chapter["start_time"]),
                ),
            )

    def curselection(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self.selection())

    def selection_clear(
        self, _first: Any = None, _last: Any = None, **_kwargs: Any
    ) -> None:
        self.selection_remove(*self.selection())


class MediaPlayerWindow(PlayerSceneMixin, PlayerPresentationMixin):
    """Own the player window and minimally render immutable playback snapshots."""

    def __init__(
        self,
        owner: tk.Tk,
        *,
        playback: PlaybackBackend,
        previews: MediaPreviewOwner,
        info: dict[str, Any],
        thumbnail_path: Path | None = None,
        on_first_play: Callable[[], None] | None = None,
        on_feature: Callable[..., None] | None = None,
        on_operation: Callable[..., None] | None = None,
        host: tk.Misc | None = None,
        on_closed: Callable[[], None] | None = None,
        on_details: Callable[[], None] | None = None,
        autoplay: bool = False,
        poster_image: Any = None,
        source_details: str = "",
        output_details: str = "",
        on_edit_notes: Callable[[], None] | None = None,
        progress_owner: PlaybackProgressOwner | None = None,
        entry_origin: str = "watch",
        library_records: Sequence[dict[str, Any]] = (),
        on_related_play: Callable[[dict[str, Any]], None] | None = None,
        on_record_details: Callable[[dict[str, Any]], None] | None = None,
        related_thumbnail_path: Callable[[dict[str, Any]], Any] | None = None,
        related_artwork_source: Callable[..., Any] | None = None,
        queue_keys: Sequence[str] | None = None,
        unmuted_volume: int = 80,
        initial_presentation: str = "embedded",
        initial_presentation_host: Any = None,
        on_state: Callable[..., None] | None = None,
    ) -> None:
        self.owner = owner
        self._queue_keys = tuple(queue_keys) if queue_keys is not None else None
        self._on_state = on_state
        self._entry_origin = "library" if entry_origin == "library" else "watch"
        self._library_records = tuple(library_records)
        self._on_related_play = on_related_play
        self._on_record_details = on_record_details
        self._related_thumbnail_path = related_thumbnail_path or (lambda _row: None)
        self._related_artwork_source = related_artwork_source
        self._related_view: Any = None
        self.embedded = host is not None
        self._native_overlay: Any = None
        self._overlay_actions: deque[tuple[str, Any]] = deque()
        self._presentation_window: Any = None
        self._presentation_mode = "embedded"
        self._video_fill = False
        self._display_signature: tuple[bool, int, int] | None = None
        self._unmuted_volume = max(1, min(100, unmuted_volume))
        self._initial_presentation = initial_presentation
        self._initial_presentation_host = initial_presentation_host
        self._on_closed = on_closed
        self._on_details = on_details
        self._autoplay = autoplay
        self._poster_image = poster_image
        self._detail_targets: dict[str, str] = {}
        self._source_details = source_details
        self._output_details = output_details
        self._on_edit_notes = on_edit_notes
        self._autoplay_after_id: str | None = None
        self._shortcut_bindings: list[tuple[str, str]] = []
        self.playback = playback
        self._bound_playback = playback
        self._bound_media = playback.snapshot
        self.previews = previews
        self.info = info
        self.thumbnail_path = thumbnail_path
        self._on_feature = on_feature or (lambda _action, **_fields: None)
        self._on_operation = on_operation or (lambda *_args, **_fields: None)
        self._operation_play_observed = False
        self._on_first_play = on_first_play
        self._first_play_recorded = False
        self._closed = False
        self._shown_once = False
        self._poll_after_id: str | None = None
        self._last_snapshot: PlaybackSnapshot | None = None
        self._volume_latest: VolumeObservation | None = None
        self._volume_first_pending: VolumeObservation | None = None
        self._volume_last_emitted: tuple[str, str] | None = None
        self._volume_stable_since = 0.0
        self._volume_phase = "unknown"
        self._frame_image: Any | None = None
        self._source_image: Any | None = None
        self._stage_render_after_id: str | None = None
        self._stage_render_signature: tuple[int, int, int] | None = None
        self._timeline_signature: tuple[Any, ...] | None = None
        self._timeline_progress: int | None = None
        self._timeline_handle: int | None = None
        self._surface_owner: TkPlaybackSurfaceOwner | None = None
        self._chapters = sanitize_chapters(info.get("chapters"))
        self._heatmap = sanitize_heatmap(info.get("heatmap"))
        self._audio_only = watch_media_kind(info) == "audio"

        popup: Any
        if host is None:
            popup = tk.Toplevel(owner)
            popup.withdraw()
            popup.title(f"VODForge Player — {info.get('title') or 'Saved media'}")
            popup.configure(bg=THEME["bg"])
            popup.minsize(980, 690)
            popup.resizable(True, True)
        else:
            popup = tk.Frame(host, bg=THEME["bg"])  # type: ignore[assignment]
            popup.pack(fill="both", expand=True)
        self.popup = popup

        if self.embedded:
            self._page_surface = ActionDialogSurface(
                popup,
                padx=0,
                pady=10,
                footer_gap=0,
                allow_body_scroll=True,
            )
            self._page_surface.footer.grid_remove()
            root = self._page_surface.body
        else:
            root = ttk.Frame(popup, style="FocusShell.TFrame")
            root.pack(fill="both", expand=True, padx=22, pady=18)
        self._content_root = root
        self._details_visible = not self.embedded
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=0, minsize=0 if self.embedded else 235)
        root.rowconfigure(1, weight=1, minsize=160 if self.embedded else 290)

        self._build_header(root)
        self._build_stage(root)
        self._build_sidebar(root)
        self._build_transport(root)
        self._build_preview_strip(root)
        if self.embedded:
            self._build_streaming_related()

        if not self.embedded:
            popup.protocol("WM_DELETE_WINDOW", self.close)
        self._keyboard_scope = KeyboardScope(
            popup,
            {
                "<Escape>": self.close,
                "<space>": self._toggle,
                "<Left>": lambda: self._seek_relative(-10),
                "<Right>": lambda: self._seek_relative(10),
            },
        )
        self._progress_binding = (
            PlaybackProgressBinding(
                progress_owner,
                info,
                snapshot=playback.snapshot,
                seek=playback.seek,
                observe=self._on_operation,
            )
            if progress_owner is not None
            else None
        )
        popup.bind("<Destroy>", self._on_destroy, add="+")

    def _build_header(self, root: ttk.Frame) -> None:
        if self.embedded:
            self._build_streaming_identity(root)
            return
        header = ttk.Frame(root, style="FocusShell.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(2, 14))
        header.columnconfigure(1, weight=1)
        ProductButton(
            header, text="Done", command=self.close, style="Media.FocusNav.TButton"
        ).grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 18))
        title = ttk.Label(
            header,
            text=str(self.info.get("title") or "Saved media"),
            style="FocusActiveTitle.TLabel",
            wraplength=600,
            justify="left",
        )
        title.grid(row=0, column=1, sticky="w")
        creator = str(
            self.info.get("uploader") or self.info.get("channel") or "Unknown creator"
        )
        category = str(self.info.get("vodforge_user_category") or "").strip()
        creator_label = ttk.Label(
            header,
            text=creator + (f" · {category}" if category else ""),
            style="Muted.TLabel",
            wraplength=600,
        )
        creator_label.grid(row=1, column=1, sticky="w", pady=(4, 0))
        if self._on_details is not None:
            ProductButton(
                header,
                text="View in Library",
                command=self._on_details,
                style="Media.FocusNav.TButton",
            ).grid(row=0, column=2, rowspan=2, sticky="e", padx=(16, 0))
        full_title = str(self.info.get("title") or "Saved media")
        full_creator = creator + (f" · {category}" if category else "")
        title_font = tkfont.Font(
            root=root, font=ttk.Style(root).lookup("FocusActiveTitle.TLabel", "font")
        )
        creator_font = tkfont.Font(
            root=root, font=ttk.Style(root).lookup("Muted.TLabel", "font")
        )
        ToolTip(title, full_title)
        ToolTip(creator_label, full_creator)

        def fit_identity(event: Any) -> None:
            width = max(200, event.width - 320)
            title.configure(
                wraplength=width,
                text=ellipsize_wrapped_text(
                    full_title,
                    maximum_width=width,
                    maximum_lines=2,
                    measure_width=title_font.measure,
                ),
            )
            creator_label.configure(
                wraplength=width,
                text=ellipsize_wrapped_text(
                    full_creator,
                    maximum_width=width,
                    maximum_lines=1,
                    measure_width=creator_font.measure,
                ),
            )

        header.bind("<Configure>", fit_identity, add="+")

    def _select_information_panel(self, panel: str) -> None:
        """Reveal an existing expanded section; never manufacture an action target."""
        section = self._information_sections.get(panel)
        viewport = self._page_surface.viewport
        if section is None or viewport is None or self._closed:
            return
        bounds = viewport.bbox("all")
        if bounds:
            offset = section.winfo_rooty() - self._content_root.winfo_rooty()
            viewport.yview_moveto(max(0, offset - 16) / max(1, bounds[3]))

    def _build_stage(self, root: ttk.Frame) -> None:
        stage_shell = tk.Frame(
            root,
            bg=THEME["bg"] if self.embedded else THEME["panel"],
            bd=0,
            width=690,
            height=388,
        )
        stage_shell.grid(
            row=1, column=0, sticky="nsew", padx=(0, 16) if not self.embedded else 0
        )
        stage_shell.grid_propagate(False)
        stage_shell.columnconfigure(0, weight=1)
        stage_shell.rowconfigure(0, weight=1)
        self.stage_shell = stage_shell
        self.stage = tk.Label(
            stage_shell,
            bg=THEME["bg"] if self.embedded else "#000000",
            fg=THEME["muted"],
            text="Preparing local playback…",
            font=FONT_UI_MEDIUM,
            bd=0,
            highlightthickness=0,
        )
        self.stage.grid(row=0, column=0, sticky="nsew", padx=1, pady=(1, 0))
        self.stage.bind("<Configure>", self._queue_stage_render, add="+")
        self.stage.bind(
            "<ButtonRelease-1>",
            lambda _event: self._toggle() if self._native_overlay is None else None,
        )
        self.play_overlay = PosterPlayButton(stage_shell, command=self._toggle)
        self.play_overlay.place(relx=0.5, rely=0.5, anchor="center")
        if self._poster_image is not None:
            self._source_image = self._poster_image
            self._queue_stage_render()
        elif self.thumbnail_path is not None:
            self._render_still_image(self.thumbnail_path)
        elif self._audio_only:
            self.stage.configure(text="Audio playback")

    def _build_sidebar(self, root: ttk.Frame) -> None:
        if self.embedded:
            self._build_streaming_information(root)
            return
        sidebar = ttk.Frame(root, style="FocusShell.TFrame")
        sidebar.grid(row=1, column=1, rowspan=3, sticky="new")
        sidebar.columnconfigure(0, weight=1)
        ttk.Label(sidebar, text="CHAPTERS", style="FocusEyebrow.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        self.chapter_list: ChapterList | None = None
        if self._chapters:
            chapter_shell = ttk.Frame(sidebar, style="FocusShell.TFrame")
            chapter_shell.grid(row=1, column=0, sticky="ew")
            chapter_shell.columnconfigure(0, weight=1)
            self.chapter_list = ChapterList(chapter_shell, self._chapters)
            self.chapter_list.grid(row=0, column=0, sticky="ew")
            self.chapter_list.bind("<<ListboxSelect>>", self._chapter_selected)
            self.chapter_list.bind("<<TreeviewSelect>>", self._chapter_selected)
            if len(self._chapters) > CHAPTER_ROWS_MAX:
                scrollbar = SleekScrollbar(
                    chapter_shell, command=self.chapter_list.yview
                )
                scrollbar.configure(bg=THEME["bg"])
                scrollbar.grid(row=0, column=1, sticky="ns")
                self.chapter_list.configure(yscrollcommand=scrollbar.set)
        else:
            ttk.Label(
                sidebar,
                text="No chapters in this media.",
                style="Muted.TLabel",
                wraplength=220,
                justify="left",
            ).grid(row=1, column=0, sticky="w")
        ttk.Label(sidebar, text="YOUR DETAILS", style="FocusEyebrow.TLabel").grid(
            row=2, column=0, sticky="w", pady=(16, 6)
        )
        user_tags = ", ".join(
            str(tag) for tag in self.info.get("vodforge_user_tags", ())
        )
        note = str(self.info.get("vodforge_user_note") or "").strip()
        category = str(self.info.get("vodforge_user_category") or "").strip()
        detail_text = "\n".join(
            section
            for section in (
                f"Collection\n{category}" if category else "",
                f"Tags\n{user_tags}" if user_tags else "",
                f"Your note\n{note}" if note else "",
            )
            if section
        )
        if not detail_text:
            ttk.Label(
                sidebar,
                text="Keep a note, add tags, or choose a collection.",
                style="Muted.TLabel",
                wraplength=220,
                justify="left",
            ).grid(row=4, column=0, sticky="w")
            return
        detail_shell = ttk.Frame(sidebar, style="FocusShell.TFrame")
        detail_shell.grid(row=4, column=0, sticky="ew")
        detail_shell.columnconfigure(0, weight=1)
        detail_shell.rowconfigure(0, weight=1)
        details = tk.Text(
            detail_shell,
            width=1,
            height=bounded_content_rows(detail_text, maximum=DETAIL_ROWS_MAX),
            wrap="word",
            bg=THEME["bg"],
            fg=THEME["text"],
            bd=0,
            highlightthickness=0,
            padx=8,
            pady=6,
            font=FONT_UI,
            spacing1=2,
            spacing3=4,
        )
        details.grid(row=0, column=0, sticky="nsew")
        details.insert("1.0", detail_text)
        details.tag_configure(
            "heading",
            foreground=THEME["muted"],
            font=FONT_UI_SMALL,
            spacing1=14,
            spacing3=6,
        )
        for number, line in enumerate(detail_text.splitlines(), 1):
            if line in {"Collection", "Tags", "Your note"}:
                details.tag_add("heading", f"{number}.0", f"{number}.end")
        details.configure(state="disabled")
        bind_smooth_vertical_wheel(details, mode="pixels")
        if (
            self.embedded
            or bounded_content_rows(detail_text, maximum=10000) > DETAIL_ROWS_MAX
        ):
            scrollbar = SleekScrollbar(detail_shell, command=details.yview)
            scrollbar.configure(bg=THEME["bg"])
            scrollbar.grid(row=0, column=1, sticky="ns")
            details.configure(yscrollcommand=scrollbar.set)

    def _build_transport(self, root: ttk.Frame) -> None:
        metrics = window_logical_metrics(root)
        px = metrics.px
        transport = ttk.Frame(
            root, style="FocusPanel.TFrame", padding=(px(12), px(2), px(12), px(10))
        )
        transport.grid(
            row=2, column=0, sticky="ew", padx=(0, px(16)) if not self.embedded else 0
        )
        self.transport = transport
        transport.columnconfigure(2, weight=1)
        self.timeline = tk.Canvas(
            transport,
            height=px(28),
            bg=THEME["panel"],
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        self.timeline.grid(row=0, column=0, columnspan=5, sticky="ew", pady=(0, px(4)))
        self.timeline.bind("<Configure>", lambda _event: self._draw_timeline_base())
        self.timeline.bind("<Button-1>", self._timeline_clicked)
        self.timeline.bind("<B1-Motion>", self._timeline_clicked)
        self.play_button = PlayerTransportButton(transport, command=self._toggle)
        self.play_button.grid(row=1, column=0, sticky="w", padx=(0, px(14)))
        font = metrics.font(
            tuple(
                root.tk.splitlist(
                    ttk.Style(root).lookup("Player.Transport.TLabel", "font")
                )
            )
        )
        self.time_var = tk.StringVar(value="0:00 / 0:00")
        self.time_label = ttk.Label(
            transport,
            textvariable=self.time_var,
            style="Player.Transport.TLabel",
            font=font,
        )
        self.time_label.grid(row=1, column=1, sticky="w")
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(
            transport,
            textvariable=self.status_var,
            style="Player.Transport.TLabel",
            font=font,
        )
        self.status_label.grid(row=1, column=2, sticky="e", padx=(px(12), px(18)))
        self.volume_var = tk.IntVar(value=self.playback.snapshot.volume)
        self.volume_label_var = tk.StringVar(value=f"Volume  {self.volume_var.get()}%")
        self._volume_icon = _tinted_ui_icon(
            "volume-2", size=(px(16), px(16)), color=THEME["icon"], widget=transport
        )
        self.volume_label = ttk.Label(
            transport,
            textvariable=self.volume_label_var,
            image=self._volume_icon or "",
            compound="left",
            style="Player.Transport.TLabel",
            font=font,
        )
        self.volume_label.grid(row=1, column=3, sticky="e", padx=(0, px(8)))
        self.volume_control = PlayerVolumeControl(
            transport,
            variable=self.volume_var,
            command=self._schedule_volume,
            background=THEME["panel"],
        )
        self.volume_control.grid(row=1, column=4, sticky="e")

    def _build_preview_strip(self, root: ttk.Frame) -> None:
        self._preview_queue: queue.Queue[tuple[int, int | None, bytes | None]] = (
            queue.Queue()
        )
        self._preview_generation = 0
        self._preview_target: tuple[Path, float] | None = None
        self._preview_worker_generation: int | None = None
        self._preview_completed_generation: int | None = None
        self._preview_images: list[Any] = []
        self.preview_labels: list[tk.Label] = []
        self._preview_captions: list[ttk.Label] = []
        if self._audio_only:
            return
        if self.embedded:
            strip = self._information_section("Moments")
        else:
            strip = ttk.Frame(root, style="FocusShell.TFrame")
            strip.grid(row=3, column=0, sticky="ew", padx=(0, 18), pady=(13, 0))
        for index in range(2 if self.embedded else 5):
            strip.columnconfigure(index, weight=1, uniform="preview")
        ttk.Label(
            strip,
            text="Select a moment to jump there."
            if self.embedded
            else "PREVIEW MOMENTS",
            style="Player.PanelMuted.TLabel"
            if self.embedded
            else "FocusEyebrow.TLabel",
        ).grid(
            row=0,
            column=0,
            columnspan=2 if self.embedded else 5,
            sticky="w",
            pady=(0, 6),
        )
        for index in range(5):
            label = tk.Label(
                strip,
                text="Play for preview",
                bg=THEME["panel"] if self.embedded else THEME["surface"],
                fg=THEME["subtle"],
                width=16,
                height=4,
                bd=0,
                font=FONT_UI_SMALL,
                cursor="hand2",
            )
            label.grid(
                row=1 + (index // 2) * 2 if self.embedded else 1,
                column=index % 2 if self.embedded else index,
                sticky="ew",
                padx=(0 if index % (2 if self.embedded else 5) == 0 else 8, 0),
            )
            label.bind("<Button-1>", self._preview_seek_handler(index))
            self.preview_labels.append(label)
            caption = ttk.Label(
                strip,
                text="—",
                style="Player.PanelMuted.TLabel" if self.embedded else "Muted.TLabel",
            )
            caption.grid(
                row=2 + (index // 2) * 2 if self.embedded else 2,
                column=index % 2 if self.embedded else index,
                sticky="w",
                padx=(2, 0),
                pady=(4, 8),
            )
            self._preview_captions.append(caption)

    def _preview_seek_handler(self, index: int) -> Any:
        def seek(_event: tk.Event[Any]) -> None:
            self._seek_preview(index)

        return seek

    def show(self) -> None:
        if self._closed:
            return
        if self._shown_once:
            self.focus_existing()
            return
        self._shown_once = True
        if self.embedded:
            self.popup.update_idletasks()
            # A queued video keeps its visible fullscreen/floating host. Focusing
            # the background main-window child can switch macOS out of that Space.
            if (
                self.__dict__.get("_initial_presentation_host") is None
                or self._audio_only
            ):
                self.popup.focus_set()
        else:
            reveal_toplevel(
                self.popup,
                centered_toplevel_geometry(self.owner, width=1100, height=800),
            )
            self.popup.focus_force()
        self._poll()
        if self._autoplay:
            self._autoplay_after_id = self.popup.after_idle(self._autoplay_ready)

    def _autoplay_ready(self) -> None:
        self._autoplay_after_id = None
        if not self._closed:
            self._toggle()
            mode = self.__dict__.pop("_initial_presentation", "embedded")
            host = self.__dict__.pop("_initial_presentation_host", None)
            if mode in {"fullscreen", "floating"} and not self._closed:
                if self._audio_only:
                    if host is not None:
                        host.close()
                    self._set_control_notice(
                        "This audio item plays in the main window."
                    )
                else:
                    try:
                        if host is None:
                            self._open_presentation(mode)
                        else:
                            self._open_presentation(mode, host)
                    except MediaPlayerError as exc:
                        self._report_control_failure(mode, exc)
                        if callback := self.__dict__.get("_on_state"):
                            callback(
                                self,
                                "Failed",
                                failure_boundary="presentation",
                                failure_detail=capture_failure(
                                    exc, stage="playback", inspect_text=False
                                ),
                            )
                        self._set_control_notice(
                            "That playback view is unavailable right now."
                        )

    def _ensure_render_surface(self) -> bool:
        if self._audio_only or self._surface_owner is not None:
            return True
        try:
            self._surface_owner = TkPlaybackSurfaceOwner(
                self.popup.winfo_toplevel(),
                self.stage,
                on_layout=self._native_surface_changed,
            )
            self.playback.attach_render_surface(self._surface_owner.surface)
            self._install_native_controls()
        except MediaPlayerError as exc:
            diagnostic = capture_failure(exc, stage="playback")
            self._on_operation("failed", diagnostic)
            if callback := self.__dict__.get("_on_state"):
                callback(
                    self,
                    "Failed",
                    failure_boundary="surface",
                    failure_detail=diagnostic,
                )
            messagebox.showerror("VODForge Player", str(exc), parent=self.popup)
            if self._surface_owner is not None:
                self._surface_owner.close()
                self._surface_owner = None
            return False
        return True

    def focus_existing(self) -> bool:
        try:
            if not self.popup.winfo_exists():
                return False
            self.popup.lift()
            self.popup.focus_force()
            return True
        except tk.TclError:
            return False

    def _toggle(self) -> None:
        if self._closed:
            return
        try:
            observed = self.playback.snapshot
            # A replay can arrive between timer ticks. Consume the terminal
            # observation before the provider changes state again.
            self._present_snapshot(observed)
            was_playing = observed.status in {"Starting", "Playing"}
            if not was_playing and not self._ensure_render_surface():
                return
            self.playback.toggle()
            if not was_playing and not self._first_play_recorded:
                self._first_play_recorded = True
                if self._on_first_play is not None:
                    self._on_first_play()
            if not was_playing:
                self.play_overlay.place_forget()
        except MediaPlayerError as exc:
            messagebox.showerror("VODForge Player", str(exc), parent=self.popup)

    def _media_intent_current(self) -> bool:
        """Absolute positions and metadata belong to the view's loaded media."""
        if self._closed or self.playback is not self._bound_playback:
            return False
        current = self.playback.snapshot
        return (
            current.status != "Closed"
            and current.path == self._bound_media.path
            and current.media_generation == self._bound_media.media_generation
        )

    def _seek_relative(self, amount: float) -> None:
        if self._closed:
            return
        snapshot = self.playback.snapshot
        self._seek_to(snapshot.position + amount, current_media=True)

    def _timeline_clicked(self, event: tk.Event[Any]) -> None:
        if not self._media_intent_current():
            return
        px = window_logical_metrics(self.timeline).px
        width = max(1, self.timeline.winfo_width() - px(20))
        fraction = min(1.0, max(0.0, (event.x - px(10)) / width))
        self._seek_to(self.playback.snapshot.duration * fraction)
        if self._heatmap and event.y < px(29):
            self._on_feature("heatmap")

    def _chapter_selected(self, _event: tk.Event[Any]) -> None:
        if not self._media_intent_current():
            return
        if self.chapter_list is None:
            return
        selection = self.chapter_list.curselection()
        if selection and selection[0] < len(self._chapters):
            self._seek_to(self._chapters[selection[0]]["start_time"])
            self._on_feature("chapter")

    def _seek_preview(self, index: int) -> None:
        if not self._media_intent_current():
            return
        duration = self.playback.snapshot.duration
        self._seek_to(duration * ((index + 0.5) / len(self.preview_labels)))
        self._on_feature("preview")

    def _seek_to(self, position: float, *, current_media: bool = False) -> None:
        if self._closed:
            return
        bound = self._media_intent_current()
        if not current_media and not bound:
            return
        try:
            result = self.playback.seek(position)
            progress = self.__dict__.get("_progress_binding")
            if progress is not None and bound:
                progress.manual_seek(result)
            if result.status == "Failed":
                self.status_var.set(result.error)
                return
            if bound:
                self._on_feature("seek")
        except MediaPlayerError as exc:
            self.status_var.set(str(exc))

    def _schedule_volume(self, _value: str) -> None:
        if self._closed:
            return
        self.volume_label_var.set(f"Volume  {self.volume_var.get()}%")
        try:
            self._observe_volume(self.playback.set_volume(self.volume_var.get()))
        except MediaPlayerError as exc:
            self.status_var.set(str(exc))
            self._observe_volume(self.playback.snapshot)

    def _observe_volume(
        self, snapshot: PlaybackSnapshot | None = None, *, closing: bool = False
    ) -> None:
        observation = (
            snapshot.volume_observation
            if snapshot is not None
            else self.__dict__.get("_volume_latest")
        )
        if observation is None or not 1 <= observation.generation <= 999999:
            return
        previous = self.__dict__.get("_volume_latest")
        if previous is None or previous.generation != observation.generation:
            self._volume_stable_since = time.monotonic()
            self._volume_first_pending = (
                observation if observation.disposition == "pending" else None
            )
            self._volume_last_emitted = None
        self._volume_latest = observation
        if snapshot is not None:
            self._volume_phase = snapshot.status.lower()
        if not closing and time.monotonic() - self._volume_stable_since < 0.25:
            return

        def emit(value: VolumeObservation, outcome: str) -> None:
            signature = (outcome, value.cause)
            if signature == self.__dict__.get("_volume_last_emitted"):
                return
            count = self.__dict__.get("_volume_event_count", 0)
            if count >= 32 and not closing:
                return
            dimensions = {
                "volume_request": str(value.generation),
                "volume_requested": str(value.requested),
                "volume_outcome": outcome,
                "volume_cause": value.cause,
                "volume_phase": "closed" if closing else self._volume_phase,
            }
            if value.observed is not None:
                dimensions["volume_observed"] = str(value.observed)
            action = (
                "volume_unresolved"
                if outcome == "pending_at_close"
                else "volume_" + outcome
            )
            try:
                self._on_operation(
                    action,
                    value.diagnostic
                    if outcome in {"failed", "pending_at_close"}
                    else None,
                    dimensions=dimensions,
                )
            except Exception:  # noqa: BLE001, S110 - optional observation cannot change playback or close
                pass
            self._volume_last_emitted = signature
            self._volume_event_count = count + 1

        pending = self.__dict__.get("_volume_first_pending")
        if pending is not None:
            if not closing:
                emit(pending, "pending")
            self._volume_first_pending = None
        emit(
            observation,
            "pending_at_close"
            if closing and observation.disposition == "pending"
            else observation.disposition,
        )

    def _draw_timeline_base(self) -> None:
        px = window_logical_metrics(self.timeline).px
        snapshot = self.playback.snapshot
        width = max(1, self.timeline.winfo_width())
        timeline_height = self.timeline.winfo_height()
        if width < px(24) or timeline_height < px(24):
            return
        signature = (
            width,
            timeline_height,
            round(snapshot.duration, 3),
            tuple(
                (chapter["start_time"], chapter["end_time"])
                for chapter in self._chapters
            ),
            tuple(
                (point["start_time"], point["end_time"], point["value"])
                for point in self._heatmap
            ),
        )
        if signature == self._timeline_signature:
            return
        self._timeline_signature = signature
        self.timeline.delete("all")
        left, right, center = (
            px(10),
            width - px(10),
            max(px(10), self.timeline.winfo_height() - px(10)),
        )
        usable = max(1, right - left)
        self.timeline.create_rectangle(
            left,
            center - px(2),
            right,
            center + px(2),
            fill=THEME["border"],
            outline="",
        )
        for index, value in enumerate(
            heatmap_buckets(self._heatmap, snapshot.duration, min(160, usable))
        ):
            x = left + (index / max(1, min(160, usable) - 1)) * usable
            stroke = min(px(8), max(px(1), usable // 160))
            height = px(4) + value * max(0, center - stroke - px(7))
            self.timeline.create_line(
                x,
                center - px(4),
                x,
                center - height,
                fill=THEME["accent_dark"],
                width=stroke,
            )
        for chapter in self._chapters:
            if snapshot.duration <= 0:
                continue
            x = left + (chapter["start_time"] / snapshot.duration) * usable
            self.timeline.create_line(
                x, center - px(7), x, center + px(7), fill=THEME["muted"], width=px(1)
            )
        self._timeline_progress = self.timeline.create_rectangle(
            left,
            center - px(2),
            left,
            center + px(2),
            fill=THEME["progress"],
            outline="",
        )
        self._timeline_handle = self.timeline.create_oval(
            left - px(4),
            center - px(6),
            left + px(4),
            center + px(6),
            fill=THEME["text"],
            outline=THEME["progress"],
            width=px(2),
        )

    def _update_timeline_value(self, snapshot: PlaybackSnapshot) -> None:
        self._draw_timeline_base()
        if self._timeline_progress is None or self._timeline_handle is None:
            return
        width = max(1, self.timeline.winfo_width())
        px = window_logical_metrics(self.timeline).px
        left, right, center = (
            px(10),
            width - px(10),
            max(px(10), self.timeline.winfo_height() - px(10)),
        )
        fraction = snapshot.position / snapshot.duration if snapshot.duration else 0
        x = left + min(1.0, max(0.0, fraction)) * max(1, right - left)
        self.timeline.coords(
            self._timeline_progress, left, center - px(2), x, center + px(2)
        )
        self.timeline.coords(
            self._timeline_handle, x - px(4), center - px(6), x + px(4), center + px(6)
        )

    def _poll(self) -> None:
        if self._closed:
            return
        self._present_snapshot(self.playback.snapshot)
        if not self._closed:
            self._poll_after_id = self.popup.after(100, self._poll)

    def _present_snapshot(self, snapshot: PlaybackSnapshot) -> None:
        if self.__dict__.get("_page_surface") is not None:
            self._observe_information()
        previous = self._last_snapshot
        progress = self.__dict__.get("_progress_binding")
        if progress is not None:
            progress.present(snapshot)
        self._observe_volume(snapshot)
        if snapshot.status == "Playing" and not self._operation_play_observed:
            self._operation_play_observed = True
            self._on_operation("started")
        if (
            previous is None or previous.status != snapshot.status
        ) and snapshot.status in {"Ended", "Failed"}:
            fields = {}
            if snapshot.status == "Failed" and snapshot.failure_boundary != "unknown":
                fields["dimensions"] = {
                    "playback_failure_boundary": snapshot.failure_boundary
                }
            self._on_operation(
                "completed" if snapshot.status == "Ended" else "failed",
                (
                    snapshot.failure_detail
                    or FailureDiagnostic(
                        reason=classify_failure(snapshot.error), stage="playback"
                    )
                )
                if snapshot.status == "Failed"
                else None,
                **fields,
            )
        if (
            previous is None or previous.status != snapshot.status
        ) and snapshot.status in {"Ended", "Failed"}:
            self._on_feature("completed" if snapshot.status == "Ended" else "failed")
        if previous is None or (
            snapshot.status,
            round(snapshot.position, 1),
            snapshot.duration,
            snapshot.error,
        ) != (
            previous.status,
            round(previous.position, 1),
            previous.duration,
            previous.error,
        ):
            self.time_var.set(
                f"{format_playback_time(snapshot.position)} / {format_playback_time(snapshot.duration)}"
            )
            self.status_var.set(snapshot.status)
            self.play_button.configure(
                text=("Pause" if snapshot.status in {"Playing", "Starting"} else "Play")
            )
            self._update_timeline_value(snapshot)
        if (
            snapshot.volume_observation is not None
            and snapshot.volume_observation.disposition == "failed"
            and snapshot.status in {"Playing", "Paused"}
        ):
            self.status_var.set("Volume unavailable")
        if progress is not None and progress.notice:
            self.status_var.set(progress.notice)
        self._refresh_previews(snapshot)
        self._drain_previews()
        self._present_native_controls(snapshot)
        self._last_snapshot = snapshot
        if (previous is None or previous.status != snapshot.status) and (
            on_state := self.__dict__.get("_on_state")
        ) is not None:
            on_state(self, snapshot.status)

    def _render_still_image(self, path: Path) -> None:
        if Image is None or ImageOps is None or ImageTk is None:
            return
        try:
            with Image.open(path) as source:
                self._source_image = source.convert("RGB").copy()
            self._queue_stage_render()
        except (OSError, ValueError):
            return

    def _queue_stage_render(self, _event: tk.Event[Any] | None = None) -> None:
        if self._source_image is None or self._closed:
            return
        if self._stage_render_after_id is not None:
            try:
                self.popup.after_cancel(self._stage_render_after_id)
            except tk.TclError:
                pass
        self._stage_render_after_id = self.popup.after(16, self._commit_stage_render)

    def _commit_stage_render(self) -> None:
        self._stage_render_after_id = None
        if (
            self._source_image is None
            or ImageOps is None
            or ImageTk is None
            or self._closed
        ):
            return
        try:
            width = max(240, self.stage.winfo_width())
            height = max(135, self.stage.winfo_height())
        except tk.TclError:
            return
        signature = (id(self._source_image), width, height)
        if signature == self._stage_render_signature:
            return
        self._stage_render_signature = signature
        image = ImageOps.pad(
            self._source_image,
            (width, height),
            color="#000000",
        )
        if self.embedded:
            # The native video clips to the same radius. Its transparent corners
            # must reveal the page, not the square Tk poster underneath.
            backdrop = Image.new("RGB", image.size, THEME["bg"])
            backdrop.paste(image, (0, 0), rounded_alpha(width, height, 11))
            image = backdrop
        self._frame_image = ImageTk.PhotoImage(image)
        self.stage.configure(image=self._frame_image, text="")
        self.play_overlay.set_poster(
            image, (self.stage.winfo_x(), self.stage.winfo_y())
        )

    def _refresh_previews(self, snapshot: PlaybackSnapshot) -> None:
        if self._closed or not self.preview_labels:
            return
        if self.embedded and not self._details_visible:
            return
        target = (
            (snapshot.path, round(snapshot.duration, 3))
            if snapshot.path is not None
            and math.isfinite(snapshot.duration)
            and snapshot.duration > 0
            else None
        )
        if target != self._preview_target:
            self._preview_target = target
            self._preview_generation += 1
            self._preview_images = [None] * len(self.preview_labels)
            for index, label in enumerate(self.preview_labels):
                label.configure(
                    image="",
                    text="Loading preview…" if target else "Play for preview",
                    width=16,
                    height=4,
                )
                position = (
                    target[1] * ((index + 0.5) / len(self.preview_labels))
                    if target
                    else 0
                )
                self._preview_captions[index].configure(
                    text=format_playback_time(position) if target else "—"
                )
        if target is not None and self._preview_worker_generation is None:
            # Completed generations keep their images. A newer generation waits
            # for the old worker to retire before starting more FFmpeg children.
            if self._preview_completed_generation == self._preview_generation:
                return
            self._preview_worker_generation = self._preview_generation
            threading.Thread(
                target=self._generate_previews,
                args=(self._preview_generation, target[1], len(self.preview_labels)),
                daemon=True,
                name="vodforge-player-previews",
            ).start()

    def _generate_previews(self, generation: int, duration: float, count: int) -> None:
        try:
            for index in range(count):
                if self._closed or generation != self._preview_generation:
                    return
                position = duration * ((index + 0.5) / count)
                try:
                    data = self.previews.preview_png(position)
                except MediaPlayerError:
                    data = None
                self._preview_queue.put((generation, index, data))
        finally:
            self._preview_queue.put((generation, None, None))

    def _drain_previews(self) -> None:
        if Image is None or ImageOps is None or ImageTk is None:
            return
        while True:
            try:
                generation, index, data = self._preview_queue.get_nowait()
            except queue.Empty:
                return
            if index is None:
                if generation == self._preview_worker_generation:
                    self._preview_worker_generation = None
                    self._preview_completed_generation = generation
                continue
            if generation != self._preview_generation:
                continue
            if data is None:
                self.preview_labels[index].configure(text="No preview")
                continue
            try:
                with Image.open(io.BytesIO(data)) as source:
                    image = ImageOps.pad(
                        source.convert("RGB"),
                        (PREVIEW_WIDTH, PREVIEW_HEIGHT),
                        color="#000000",
                    )
                rendered = ImageTk.PhotoImage(image)
            except (OSError, ValueError):
                self.preview_labels[index].configure(text="No preview")
                continue
            self._preview_images[index] = rendered
            apply_preview_image(self.preview_labels[index], rendered)

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        keyboard_scope = self.__dict__.get("_keyboard_scope")
        if keyboard_scope is not None:
            keyboard_scope.close()
        initial_host = self.__dict__.pop("_initial_presentation_host", None)
        if initial_host is not None:
            initial_host.close()
        for sequence, binding in self._shortcut_bindings:
            try:
                (self.owner if self.embedded else self.popup).unbind(sequence, binding)
            except tk.TclError:
                pass
        self._shortcut_bindings.clear()
        if self._autoplay_after_id is not None:
            try:
                self.popup.after_cancel(self._autoplay_after_id)
            except tk.TclError:
                pass
            self._autoplay_after_id = None
        progress = self.__dict__.get("_progress_binding")
        if progress is not None:
            progress.close()
        self._observe_volume(closing=True)
        self._on_operation("closed")
        if self._poll_after_id is not None:
            try:
                self.popup.after_cancel(self._poll_after_id)
            except tk.TclError:
                pass
        if self._stage_render_after_id is not None:
            try:
                self.popup.after_cancel(self._stage_render_after_id)
            except tk.TclError:
                pass
        self._close_native_controls()
        self.playback.detach_render_surface()
        if self._surface_owner is not None:
            self._surface_owner.close()
            self._surface_owner = None
        self._close_presentation_window()
        try:
            self.popup.destroy()
        except tk.TclError:
            pass
        # Shared libVLC session retirement is asynchronous. The visible player
        # and its native child are gone before provider teardown begins.
        self.playback.shutdown()
        self.previews.shutdown()
        if self._on_closed is not None:
            callback, self._on_closed = self._on_closed, None
            callback()

    def _on_destroy(self, event: tk.Event[Any]) -> None:
        if event.widget is self.popup and not self._closed:
            self.close()
