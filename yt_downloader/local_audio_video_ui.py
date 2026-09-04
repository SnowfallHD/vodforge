from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any, Literal

from PIL import Image, ImageTk

from .local_audio_video import (
    LOCAL_VIDEO_PROFILE_OPTIONS,
    LocalAudioVideoCancelled,
    LocalAudioVideoConversionOwner,
    LocalAudioVideoProgress,
    LocalAudioVideoResult,
    LocalVideoProfile,
    load_local_still_image,
    local_video_profile_spec,
    new_local_audio_video_request,
)
from .ui_layout import centered_toplevel_geometry
from .ui_theme import FONT_UI_MEDIUM, THEME
from .ui_widgets import ActionDialogSurface, SleekProgressbar, reveal_toplevel


def compact_dialog_path(path: Path, *, maximum: int = 108) -> str:
    """Keep an output path informative without allowing it to grow the dialog."""
    value = str(path)
    if len(value) <= maximum:
        return value
    head = max(12, maximum // 3)
    tail = max(12, maximum - head - 1)
    prefix = value[:head].rstrip("/\\")
    suffix = value[-tail:].lstrip("/\\")
    return f"{prefix}…{suffix}"


class LocalAudioVideoDialog:
    """Own the local MP3 + still-image form and its immutable worker events."""

    def __init__(
        self,
        owner: tk.Tk,
        *,
        converter: LocalAudioVideoConversionOwner,
        output_dir: Path,
        profile_variable: tk.StringVar,
        on_complete: Callable[[LocalAudioVideoResult], None],
        on_closed: Callable[[], None],
    ) -> None:
        self.owner = owner
        self.converter = converter
        self.output_dir = Path(output_dir)
        self.profile_var = profile_variable
        self.on_complete = on_complete
        self.on_closed = on_closed
        self.audio_path: Path | None = None
        self.image_path: Path | None = None
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._close_when_idle = False
        self._closed = False
        self._preview_image: Any | None = None

        popup = tk.Toplevel(owner)
        popup.withdraw()
        popup.title("Create MP4 from audio")
        popup.transient(owner)
        popup.configure(bg=THEME["bg"])
        popup.resizable(True, False)
        popup.minsize(620, 500)
        self.popup = popup

        self._build_content()
        popup.protocol("WM_DELETE_WINDOW", self._request_close)
        popup.bind("<Escape>", lambda _event: self._request_close())
        popup.bind("<Destroy>", self._destroyed, add="+")

    def _build_content(self) -> None:
        surface = ActionDialogSurface(self.popup, padx=26, pady=24, footer_gap=16)
        self.dialog_surface = surface
        root = surface.body
        root.columnconfigure(0, weight=1)
        self._build_intro(root)
        self._build_choices(root)
        self._build_preview_and_profile(root)
        self._build_destination(root)
        self._build_progress(root)
        self._build_actions(surface.footer)

    @staticmethod
    def _build_intro(root: ttk.Frame) -> None:
        ttk.Label(root, text="Create MP4 from audio", style="FocusTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            root,
            text=(
                "Pair a local MP3 with one still image. VODForge creates a "
                "playable MP4 without changing either source file."
            ),
            style="Muted.TLabel",
            wraplength=650,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(5, 20))

    def _build_choices(self, root: ttk.Frame) -> None:
        choices = ttk.Frame(root, style="FocusShell.TFrame")
        choices.grid(row=2, column=0, sticky="ew")
        choices.columnconfigure(0, weight=1)
        self.audio_name_var = tk.StringVar(value="Choose an MP3 file")
        self.image_name_var = tk.StringVar(value="Choose a still image")
        self._build_file_row(choices, row=0, kind="audio")
        self._build_file_row(choices, row=1, kind="image")

    def _build_preview_and_profile(self, root: ttk.Frame) -> None:
        row = ttk.Frame(root, style="FocusShell.TFrame")
        row.grid(row=3, column=0, sticky="ew", pady=(18, 18))
        row.columnconfigure(1, weight=1)
        self._build_preview(row)
        self._build_profile(row)

    def _build_preview(self, parent: ttk.Frame) -> None:
        preview_shell = tk.Frame(
            parent,
            bg=THEME["surface"],
            width=192,
            height=108,
            bd=0,
            highlightthickness=1,
            highlightbackground=THEME["border"],
        )
        preview_shell.grid(row=0, column=0, sticky="nw", padx=(0, 18))
        preview_shell.grid_propagate(False)
        self.preview = tk.Label(
            preview_shell,
            text="Still preview",
            bg=THEME["surface"],
            fg=THEME["subtle"],
            font=FONT_UI_MEDIUM,
            bd=0,
            highlightthickness=0,
        )
        self.preview.pack(fill="both", expand=True)

    def _build_profile(self, parent: ttk.Frame) -> None:
        profile = ttk.Frame(parent, style="FocusShell.TFrame")
        profile.grid(row=0, column=1, sticky="new")
        profile.columnconfigure(0, weight=1)
        ttk.Label(profile, text="OUTPUT PROFILE", style="FocusEyebrow.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.profile_combo = ttk.Combobox(
            profile,
            textvariable=self.profile_var,
            values=LOCAL_VIDEO_PROFILE_OPTIONS,
            state="readonly",
        )
        self.profile_combo.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        self.profile_description_var = tk.StringVar()
        ttk.Label(
            profile,
            textvariable=self.profile_description_var,
            style="Muted.TLabel",
            wraplength=350,
            justify="left",
        ).grid(row=2, column=0, sticky="ew", pady=(7, 0))
        self.profile_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._sync_profile_description(),
            add="+",
        )
        self._sync_profile_description()

    def _sync_profile_description(self) -> None:
        try:
            spec = local_video_profile_spec(self.profile_var.get())
        except ValueError:
            self.profile_var.set(LocalVideoProfile.STANDARD.value)
            spec = local_video_profile_spec(LocalVideoProfile.STANDARD)
        self.profile_description_var.set(spec.description)

    def _build_destination(self, root: ttk.Frame) -> None:
        destination = ttk.Frame(root, style="FocusShell.TFrame")
        destination.grid(row=4, column=0, sticky="ew")
        destination.columnconfigure(0, weight=1)
        ttk.Label(destination, text="OUTPUT", style="FocusEyebrow.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            destination,
            text=compact_dialog_path(self.output_dir),
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="ew", pady=(5, 0))
        ttk.Label(
            destination,
            text="The MP4 is placed directly here. No parent folder is added.",
            style="Muted.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(3, 0))

    def _build_progress(self, root: ttk.Frame) -> None:
        self.progress = SleekProgressbar(root, maximum=100, value=0, height=7)
        self.progress.grid(row=5, column=0, sticky="ew", pady=(22, 7))
        self.status_var = tk.StringVar(value="Choose both files to continue.")
        ttk.Label(
            root,
            textvariable=self.status_var,
            style="Muted.TLabel",
        ).grid(row=6, column=0, sticky="w")

    def _build_actions(self, actions: ttk.Frame) -> None:
        actions.columnconfigure(0, weight=1)
        self.cancel_button = ttk.Button(
            actions,
            text="Cancel",
            command=self._request_close,
            style="FocusQuiet.TButton",
        )
        self.cancel_button.grid(row=0, column=1, padx=(0, 8))
        self.create_button = ttk.Button(
            actions,
            text="Create MP4",
            command=self._start,
            style="Accent.TButton",
            state="disabled",
        )
        self.create_button.grid(row=0, column=2)

    def _build_file_row(
        self,
        parent: ttk.Frame,
        *,
        row: int,
        kind: Literal["audio", "image"],
    ) -> None:
        is_audio = kind == "audio"
        eyebrow = "MP3 AUDIO" if is_audio else "STILL IMAGE"
        variable = self.audio_name_var if is_audio else self.image_name_var
        button_text = "Choose MP3" if is_audio else "Choose image"
        command = self._choose_audio if is_audio else self._choose_image
        item = ttk.Frame(parent, style="FocusShell.TFrame")
        item.grid(row=row, column=0, sticky="ew", pady=(0, 13))
        item.columnconfigure(0, weight=1)
        ttk.Label(item, text=eyebrow, style="FocusEyebrow.TLabel").grid(
            row=0, column=0, sticky="w", columnspan=2
        )
        field = ttk.Entry(item, textvariable=variable, state="readonly")
        field.grid(row=1, column=0, sticky="ew", pady=(5, 0), padx=(0, 9))
        button = ttk.Button(
            item,
            text=button_text,
            command=command,
            style="FocusQuiet.TButton",
        )
        button.grid(row=1, column=1, sticky="e", pady=(5, 0))
        if is_audio:
            self.audio_button = button
        else:
            self.image_button = button

    def _choose_audio(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.popup,
            title="Choose MP3 audio",
            filetypes=(("MP3 audio", "*.mp3"),),
        )
        if not selected:
            return
        self.audio_path = Path(selected)
        self.audio_name_var.set(self.audio_path.name)
        self._sync_ready_state()

    def _choose_image(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.popup,
            title="Choose still image",
            filetypes=(
                ("Images", ("*.jpg", "*.jpeg", "*.png", "*.webp")),
                ("JPEG", ("*.jpg", "*.jpeg")),
                ("PNG", "*.png"),
                ("WebP", "*.webp"),
            ),
        )
        if not selected:
            return
        candidate = Path(selected)
        if not self._render_preview(candidate):
            self.image_path = None
            self.image_name_var.set("Choose a supported still image")
            self._sync_ready_state(
                status="Choose a valid JPG, PNG, or WebP still image."
            )
            return
        self.image_path = candidate
        self.image_name_var.set(candidate.name)
        self._sync_ready_state()

    def _render_preview(self, path: Path) -> bool:
        try:
            image = load_local_still_image(path)
            try:
                image.thumbnail((190, 106), getattr(Image, "Resampling", Image).LANCZOS)
                canvas = Image.new("RGB", (190, 106), THEME["surface"])
                canvas.paste(
                    image,
                    (
                        (canvas.width - image.width) // 2,
                        (canvas.height - image.height) // 2,
                    ),
                )
            finally:
                image.close()
            try:
                self._preview_image = ImageTk.PhotoImage(canvas)
            finally:
                canvas.close()
            self.preview.configure(
                image=self._preview_image,
                text="",
                width=190,
                height=106,
            )
            return True
        except (OSError, RuntimeError, tk.TclError, ValueError):
            self._preview_image = None
            self.preview.configure(image="", text="Preview unavailable")
            return False

    def _sync_ready_state(self, *, status: str | None = None) -> None:
        ready = self.audio_path is not None and self.image_path is not None
        self.create_button.configure(state="normal" if ready else "disabled")
        self.status_var.set(
            status
            or (
                "Ready to create the MP4."
                if ready
                else "Choose both files to continue."
            )
        )

    def _start(self) -> None:
        if (
            self.audio_path is None
            or self.image_path is None
            or self._worker is not None
        ):
            return
        request = new_local_audio_video_request(
            self.audio_path,
            self.image_path,
            self.output_dir,
            profile=self.profile_var.get(),
        )
        self.audio_button.configure(state="disabled")
        self.image_button.configure(state="disabled")
        self.profile_combo.configure(state="disabled")
        self.create_button.configure(state="disabled")
        self.cancel_button.configure(text="Stop")
        self.status_var.set("Checking local files…")

        def run() -> None:
            try:
                result = self.converter.convert(
                    request,
                    on_progress=lambda progress: self._events.put(
                        ("progress", progress)
                    ),
                )
                self._events.put(("complete", result))
            except LocalAudioVideoCancelled as exc:
                self._events.put(("cancelled", str(exc)))
            except Exception as exc:  # noqa: BLE001 - presentation boundary
                self._events.put(("error", str(exc)))

        self._worker = threading.Thread(
            target=run,
            name="vodforge-local-audio-video",
            daemon=True,
        )
        self._worker.start()
        self.popup.after(60, self._pump_events)

    def _pump_events(self) -> None:
        if self._closed:
            return
        terminal = False
        while True:
            try:
                kind, payload = self._events.get_nowait()
            except queue.Empty:
                break
            if kind == "progress" and isinstance(payload, LocalAudioVideoProgress):
                self.progress.configure(value=payload.fraction * 100)
                self.status_var.set(payload.label)
            elif kind == "complete" and isinstance(payload, LocalAudioVideoResult):
                terminal = True
                self._worker = None
                self.on_complete(payload)
                self._destroy()
            elif kind in {"cancelled", "error"}:
                terminal = True
                self._worker = None
                message = str(payload) or "The conversion did not finish."
                self.cancel_button.configure(text="Cancel", state="normal")
                self.audio_button.configure(state="normal")
                self.image_button.configure(state="normal")
                self.profile_combo.configure(state="readonly")
                self._sync_ready_state(status=message)
                if self._close_when_idle:
                    self._destroy()
        if not terminal and self._worker is not None:
            self.popup.after(60, self._pump_events)

    def _request_close(self) -> None:
        if self._worker is None:
            self._destroy()
            return
        self._close_when_idle = True
        self.converter.cancel()
        self.status_var.set("Stopping safely…")
        self.cancel_button.configure(state="disabled")

    def close_for_application(self) -> None:
        self.converter.cancel()
        self._destroy()

    def _destroy(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.popup.grab_release()
        except tk.TclError:
            pass
        try:
            self.popup.destroy()
        except tk.TclError:
            pass
        self.on_closed()

    def _destroyed(self, event: tk.Event[tk.Misc]) -> None:
        if event.widget is self.popup and not self._closed:
            self._closed = True
            self.on_closed()

    def show(self) -> None:
        reveal_toplevel(
            self.popup,
            centered_toplevel_geometry(self.owner, width=700, height=570),
        )
        self.popup.grab_set()
        self.popup.focus_force()

    def focus(self) -> None:
        try:
            self.popup.deiconify()
            self.popup.lift()
            self.popup.focus_force()
        except tk.TclError:
            pass
