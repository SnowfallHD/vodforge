from __future__ import annotations

import io
import queue
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from .history import sanitize_chapters, sanitize_heatmap
from .media_preview import MediaPreviewOwner
from .playback_backend import MediaPlayerError, PlaybackBackend, PlaybackSnapshot
from .playback_surface import TkPlaybackSurfaceOwner
from .ui_layout import centered_toplevel_geometry
from .ui_theme import FONT_UI_MEDIUM, FONT_UI_SMALL, THEME
from .ui_widgets import reveal_toplevel

try:
    from PIL import Image, ImageOps, ImageTk
except ImportError:  # pragma: no cover - required by production package
    Image = ImageOps = ImageTk = None  # type: ignore[assignment]

PREVIEW_WIDTH = 132
PREVIEW_HEIGHT = 74
CHAPTER_ROWS_MAX = 8
DETAIL_ROWS_MAX = 8


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
        width: int = 112,
    ) -> None:
        super().__init__(
            master,
            width=width,
            height=22,
            bg=THEME["bg"],
            bd=0,
            highlightthickness=0,
            cursor="hand2",
            takefocus=True,
        )
        self.variable = variable
        self.command = command
        self._rendered_value: tuple[int, int] | None = None
        self._trace = variable.trace_add("write", self._value_changed)
        self.bind("<Configure>", self._draw)
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
        width = max(1, self.winfo_width() - 16)
        value = round(min(1.0, max(0.0, (event.x - 8) / width)) * 100)
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
            width = max(24, self.winfo_width())
            value = min(100, max(0, int(self.variable.get())))
        except (tk.TclError, ValueError):
            return
        signature = (width, value)
        if signature == self._rendered_value:
            return
        self._rendered_value = signature
        self.delete("all")
        left, right, center = 8, width - 8, 11
        x = left + ((right - left) * value / 100)
        self.create_line(
            left,
            center,
            right,
            center,
            fill=THEME["border"],
            width=4,
            capstyle="round",
        )
        self.create_line(
            left,
            center,
            x,
            center,
            fill=THEME["accent"],
            width=4,
            capstyle="round",
        )
        self.create_oval(
            x - 6,
            center - 6,
            x + 6,
            center + 6,
            fill=THEME["text"],
            outline=THEME["accent_dark"],
            width=2,
        )

    def _destroyed(self, event: tk.Event[Any]) -> None:
        if event.widget is not self:
            return
        try:
            self.variable.trace_remove("write", self._trace)
        except tk.TclError:
            pass


class MediaPlayerWindow:
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
    ) -> None:
        self.owner = owner
        self.playback = playback
        self.previews = previews
        self.info = info
        self.thumbnail_path = thumbnail_path
        self._on_first_play = on_first_play
        self._first_play_recorded = False
        self._closed = False
        self._poll_after_id: str | None = None
        self._last_snapshot: PlaybackSnapshot | None = None
        self._frame_image: Any | None = None
        self._source_image: Any | None = None
        self._stage_render_after_id: str | None = None
        self._stage_render_signature: tuple[int, int, int] | None = None
        self._timeline_signature: tuple[Any, ...] | None = None
        self._timeline_progress: int | None = None
        self._timeline_handle: int | None = None
        self._preview_queue: queue.Queue[tuple[int, bytes | None]] = queue.Queue()
        self._preview_images: list[Any] = []
        self._surface_owner: TkPlaybackSurfaceOwner | None = None
        self._chapters = sanitize_chapters(info.get("chapters"))
        self._heatmap = sanitize_heatmap(info.get("heatmap"))
        self._audio_only = str(info.get("vodforge_output_type") or "").upper() == "MP3"

        popup = tk.Toplevel(owner)
        popup.withdraw()
        popup.title(f"VODForge Player — {info.get('title') or 'Saved media'}")
        popup.configure(bg=THEME["bg"])
        popup.minsize(980, 690)
        popup.resizable(True, True)
        self.popup = popup

        root = ttk.Frame(popup, style="FocusShell.TFrame")
        root.pack(fill="both", expand=True, padx=22, pady=18)
        root.columnconfigure(0, weight=3)
        root.columnconfigure(1, weight=1, minsize=235)
        root.rowconfigure(1, weight=1, minsize=290)

        self._build_header(root)
        self._build_stage(root)
        self._build_sidebar(root)
        self._build_transport(root)
        self._build_preview_strip(root)

        popup.protocol("WM_DELETE_WINDOW", self.close)
        popup.bind("<Escape>", lambda _event: self.close())
        popup.bind("<space>", lambda _event: self._toggle())
        popup.bind("<Left>", lambda _event: self._seek_relative(-10))
        popup.bind("<Right>", lambda _event: self._seek_relative(10))
        popup.bind("<Destroy>", self._on_destroy, add="+")

    def _build_header(self, root: ttk.Frame) -> None:
        header = ttk.Frame(root, style="FocusShell.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text=str(self.info.get("title") or "Saved media"),
            style="FocusTitle.TLabel",
            wraplength=720,
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        creator = str(
            self.info.get("uploader") or self.info.get("channel") or "Unknown creator"
        )
        category = str(self.info.get("vodforge_user_category") or "").strip()
        subtitle = creator + (f"  •  {category}" if category else "")
        ttk.Label(header, text=subtitle, style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", pady=(3, 0)
        )
        ttk.Button(
            header,
            text="Done",
            command=self.close,
            style="FocusQuiet.TButton",
        ).grid(row=0, column=1, rowspan=2, sticky="e")

    def _build_stage(self, root: ttk.Frame) -> None:
        stage_shell = tk.Frame(
            root,
            bg=THEME["border"],
            bd=0,
            width=690,
            height=388,
        )
        stage_shell.grid(row=1, column=0, sticky="nsew", padx=(0, 18))
        stage_shell.grid_propagate(False)
        stage_shell.columnconfigure(0, weight=1)
        stage_shell.rowconfigure(0, weight=1)
        self.stage_shell = stage_shell
        self.stage = tk.Label(
            stage_shell,
            bg="#000000",
            fg=THEME["muted"],
            text="Preparing local playback…",
            font=FONT_UI_MEDIUM,
            bd=0,
            highlightthickness=0,
        )
        self.stage.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        self.stage.bind("<Configure>", self._queue_stage_render, add="+")
        if self.thumbnail_path is not None:
            self._render_still_image(self.thumbnail_path)
        elif self._audio_only:
            self.stage.configure(text="Audio playback")

    def _build_sidebar(self, root: ttk.Frame) -> None:
        sidebar = ttk.Frame(root, style="FocusShell.TFrame")
        sidebar.grid(row=1, column=1, rowspan=3, sticky="new")
        sidebar.columnconfigure(0, weight=1)
        ttk.Label(sidebar, text="CHAPTERS", style="FocusEyebrow.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        self.chapter_list: tk.Listbox | None = None
        if self._chapters:
            chapter_shell = ttk.Frame(sidebar, style="FocusShell.TFrame")
            chapter_shell.grid(row=1, column=0, sticky="ew")
            chapter_shell.columnconfigure(0, weight=1)
            self.chapter_list = tk.Listbox(
                chapter_shell,
                height=bounded_content_rows(
                    len(self._chapters), maximum=CHAPTER_ROWS_MAX
                ),
                activestyle="none",
                bg=THEME["surface"],
                fg=THEME["text"],
                selectbackground=THEME["accent_dark"],
                selectforeground="#ffffff",
                bd=0,
                highlightthickness=1,
                highlightbackground=THEME["border"],
                font=FONT_UI_SMALL,
            )
            self.chapter_list.grid(row=0, column=0, sticky="ew")
            for chapter in self._chapters:
                label = chapter["title"] or "Untitled chapter"
                self.chapter_list.insert(
                    "end", f"{format_playback_time(chapter['start_time'])}  {label}"
                )
            self.chapter_list.bind("<<ListboxSelect>>", self._chapter_selected)
            if len(self._chapters) > CHAPTER_ROWS_MAX:
                scrollbar = ttk.Scrollbar(
                    chapter_shell,
                    orient="vertical",
                    command=self.chapter_list.yview,
                )
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
        detail_text = "\n\n".join(
            section
            for section in (
                f"Category\n{category}" if category else "",
                f"Tags\n{user_tags}" if user_tags else "",
                f"Notes\n{note}" if note else "",
            )
            if section
        )
        if not detail_text:
            ttk.Label(
                sidebar,
                text="Add a category, tags, or notes from Library actions.",
                style="Muted.TLabel",
                wraplength=220,
                justify="left",
            ).grid(row=4, column=0, sticky="w")
            return
        detail_shell = ttk.Frame(sidebar, style="FocusShell.TFrame")
        detail_shell.grid(row=4, column=0, sticky="ew")
        detail_shell.columnconfigure(0, weight=1)
        details = tk.Text(
            detail_shell,
            height=bounded_content_rows(detail_text, maximum=DETAIL_ROWS_MAX),
            wrap="word",
            bg=THEME["surface"],
            fg=THEME["muted"],
            bd=0,
            highlightthickness=0,
            padx=10,
            pady=9,
            font=FONT_UI_SMALL,
        )
        details.grid(row=0, column=0, sticky="ew")
        details.insert("1.0", detail_text)
        details.configure(state="disabled")
        if bounded_content_rows(detail_text, maximum=10_000) > DETAIL_ROWS_MAX:
            scrollbar = ttk.Scrollbar(
                detail_shell,
                orient="vertical",
                command=details.yview,
            )
            scrollbar.grid(row=0, column=1, sticky="ns")
            details.configure(yscrollcommand=scrollbar.set)

    def _build_transport(self, root: ttk.Frame) -> None:
        transport = ttk.Frame(root, style="FocusShell.TFrame")
        transport.grid(row=2, column=0, sticky="ew", padx=(0, 18), pady=(12, 0))
        transport.columnconfigure(1, weight=1)
        self.play_button = ttk.Button(
            transport,
            text="Play",
            command=self._toggle,
            style="Accent.TButton",
            width=8,
        )
        self.play_button.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 12))
        self.timeline = tk.Canvas(
            transport,
            height=42,
            bg=THEME["bg"],
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        self.timeline.grid(row=0, column=1, columnspan=3, sticky="ew")
        self.timeline.bind("<Configure>", lambda _event: self._draw_timeline_base())
        self.timeline.bind("<Button-1>", self._timeline_clicked)
        self.timeline.bind("<B1-Motion>", self._timeline_clicked)
        self.time_var = tk.StringVar(value="0:00 / 0:00")
        ttk.Label(transport, textvariable=self.time_var, style="Muted.TLabel").grid(
            row=1, column=1, sticky="w"
        )
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(transport, textvariable=self.status_var, style="Muted.TLabel").grid(
            row=1, column=2, sticky="e", padx=(12, 14)
        )
        self.volume_var = tk.IntVar(value=self.playback.snapshot.volume)
        self.volume_label_var = tk.StringVar(value=f"Volume  {self.volume_var.get()}%")
        ttk.Label(
            transport,
            textvariable=self.volume_label_var,
            style="Muted.TLabel",
        ).grid(row=1, column=3, sticky="e", padx=(12, 5))
        volume = PlayerVolumeControl(
            transport,
            variable=self.volume_var,
            command=self._schedule_volume,
        )
        volume.grid(row=1, column=4, sticky="e")

    def _build_preview_strip(self, root: ttk.Frame) -> None:
        self.preview_labels: list[tk.Label] = []
        if self._audio_only:
            return
        strip = ttk.Frame(root, style="FocusShell.TFrame")
        strip.grid(row=3, column=0, sticky="ew", padx=(0, 18), pady=(13, 0))
        for index in range(5):
            strip.columnconfigure(index, weight=1, uniform="preview")
        ttk.Label(
            strip,
            text="PREVIEW MOMENTS",
            style="FocusEyebrow.TLabel",
        ).grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 6))
        for index in range(5):
            position = self.playback.snapshot.duration * ((index + 0.5) / 5)
            label = tk.Label(
                strip,
                text="Loading preview…",
                bg=THEME["surface"],
                fg=THEME["subtle"],
                width=16,
                height=4,
                bd=0,
                font=FONT_UI_SMALL,
                cursor="hand2",
            )
            label.grid(
                row=1,
                column=index,
                sticky="ew",
                padx=(0 if index == 0 else 4, 0),
            )
            label.bind("<Button-1>", self._preview_seek_handler(index))
            self.preview_labels.append(label)
            ttk.Label(
                strip,
                text=format_playback_time(position),
                style="Muted.TLabel",
            ).grid(row=2, column=index, sticky="w", padx=(2, 0), pady=(4, 0))

    def _preview_seek_handler(self, index: int) -> Any:
        def seek(_event: tk.Event[Any]) -> None:
            self._seek_preview(index)

        return seek

    def show(self) -> None:
        reveal_toplevel(
            self.popup,
            centered_toplevel_geometry(self.owner, width=1100, height=800),
        )
        self.popup.focus_force()
        if not self._audio_only:
            try:
                self._surface_owner = TkPlaybackSurfaceOwner(self.popup, self.stage)
                self.playback.attach_render_surface(self._surface_owner.surface)
            except MediaPlayerError as exc:
                messagebox.showerror("VODForge Player", str(exc), parent=self.popup)
                self.close()
                return
        self._poll()
        if self.playback.snapshot.path is not None and not self._audio_only:
            threading.Thread(
                target=self._generate_previews,
                daemon=True,
                name="vodforge-player-previews",
            ).start()
        self._toggle()

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
        try:
            was_playing = self.playback.snapshot.status in {"Starting", "Playing"}
            self.playback.toggle()
            if not was_playing and not self._first_play_recorded:
                self._first_play_recorded = True
                if self._on_first_play is not None:
                    self._on_first_play()
        except MediaPlayerError as exc:
            messagebox.showerror("VODForge Player", str(exc), parent=self.popup)

    def _seek_relative(self, amount: float) -> None:
        snapshot = self.playback.snapshot
        self._seek_to(snapshot.position + amount)

    def _timeline_clicked(self, event: tk.Event[Any]) -> None:
        width = max(1, self.timeline.winfo_width() - 20)
        fraction = min(1.0, max(0.0, (event.x - 10) / width))
        self._seek_to(self.playback.snapshot.duration * fraction)

    def _chapter_selected(self, _event: tk.Event[Any]) -> None:
        if self.chapter_list is None:
            return
        selection = self.chapter_list.curselection()
        if selection and selection[0] < len(self._chapters):
            self._seek_to(self._chapters[selection[0]]["start_time"])

    def _seek_preview(self, index: int) -> None:
        duration = self.playback.snapshot.duration
        self._seek_to(duration * ((index + 0.5) / len(self.preview_labels)))

    def _seek_to(self, position: float) -> None:
        try:
            self.playback.seek(position)
        except MediaPlayerError as exc:
            self.status_var.set(str(exc))

    def _schedule_volume(self, _value: str) -> None:
        self.volume_label_var.set(f"Volume  {self.volume_var.get()}%")
        try:
            self.playback.set_volume(self.volume_var.get())
        except MediaPlayerError as exc:
            self.status_var.set(str(exc))

    def _draw_timeline_base(self) -> None:
        snapshot = self.playback.snapshot
        width = max(1, self.timeline.winfo_width())
        signature = (
            width,
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
        left, right, center = 10, width - 10, 29
        usable = max(1, right - left)
        self.timeline.create_rectangle(
            left, center - 2, right, center + 2, fill=THEME["border"], outline=""
        )
        for index, value in enumerate(
            heatmap_buckets(self._heatmap, snapshot.duration, min(160, usable))
        ):
            x = left + (index / max(1, min(160, usable) - 1)) * usable
            height = 4 + value * 14
            self.timeline.create_line(
                x,
                center - 4,
                x,
                center - height,
                fill=THEME["accent_dark"],
                width=max(1, usable // 160),
            )
        for chapter in self._chapters:
            if snapshot.duration <= 0:
                continue
            x = left + (chapter["start_time"] / snapshot.duration) * usable
            self.timeline.create_line(
                x, center - 7, x, center + 7, fill=THEME["muted"], width=1
            )
        self._timeline_progress = self.timeline.create_rectangle(
            left, center - 2, left, center + 2, fill=THEME["accent"], outline=""
        )
        self._timeline_handle = self.timeline.create_oval(
            left - 4,
            center - 6,
            left + 4,
            center + 6,
            fill=THEME["text"],
            outline=THEME["accent"],
            width=2,
        )

    def _update_timeline_value(self, snapshot: PlaybackSnapshot) -> None:
        self._draw_timeline_base()
        if self._timeline_progress is None or self._timeline_handle is None:
            return
        width = max(1, self.timeline.winfo_width())
        left, right, center = 10, width - 10, 29
        fraction = snapshot.position / snapshot.duration if snapshot.duration else 0
        x = left + min(1.0, max(0.0, fraction)) * max(1, right - left)
        self.timeline.coords(self._timeline_progress, left, center - 2, x, center + 2)
        self.timeline.coords(
            self._timeline_handle, x - 4, center - 6, x + 4, center + 6
        )

    def _poll(self) -> None:
        if self._closed:
            return
        snapshot = self.playback.snapshot
        previous = self._last_snapshot
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
        self._drain_previews()
        self._last_snapshot = snapshot
        self._poll_after_id = self.popup.after(100, self._poll)

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
        self._frame_image = ImageTk.PhotoImage(image)
        self.stage.configure(image=self._frame_image, text="")

    def _generate_previews(self) -> None:
        snapshot = self.playback.snapshot
        path = snapshot.path
        if path is None:
            return
        for index in range(len(self.preview_labels)):
            if self._closed:
                return
            position = snapshot.duration * ((index + 0.5) / len(self.preview_labels))
            try:
                data = self.previews.preview_png(position)
            except MediaPlayerError:
                data = None
            self._preview_queue.put((index, data))

    def _drain_previews(self) -> None:
        if Image is None or ImageOps is None or ImageTk is None:
            return
        while True:
            try:
                index, data = self._preview_queue.get_nowait()
            except queue.Empty:
                return
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
            self._preview_images.append(rendered)
            apply_preview_image(self.preview_labels[index], rendered)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
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
        self.playback.shutdown()
        self.previews.shutdown()
        if self._surface_owner is not None:
            self._surface_owner.close()
            self._surface_owner = None
        try:
            self.popup.destroy()
        except tk.TclError:
            pass

    def _on_destroy(self, event: tk.Event[Any]) -> None:
        if event.widget is self.popup and not self._closed:
            self.close()
