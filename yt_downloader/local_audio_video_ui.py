from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any, Literal

from PIL import Image

from .failure_diagnostics import FailureDiagnostic, capture_failure
from .local_audio_video import (
    LOCAL_VIDEO_PROFILE_OPTIONS,
    LocalAudioVideoCancelled,
    LocalAudioVideoCommit,
    LocalAudioVideoConversionOwner,
    LocalAudioVideoProgress,
    LocalAudioVideoResult,
    LocalVideoProfile,
    load_local_still_image,
    local_video_profile_spec,
    new_local_audio_video_request,
)
from .platform_services import create_surface_image, surface_backing_scale
from .ui_button_contract import ProductButton
from .ui_layout import (
    bounded_window_size,
    centered_toplevel_geometry,
    window_logical_metrics,
)
from .ui_theme import FONT_UI, FONT_UI_MEDIUM, THEME
from .ui_widgets import (
    ActionDialogSurface,
    ChoiceDropdown,
    ProductEntry,
    SleekProgressbar,
    reveal_toplevel,
)


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


@dataclass(frozen=True)
class LocalConversionFailure:
    # Message remains local presentation data; only diagnostic reaches telemetry.
    message: str
    diagnostic: FailureDiagnostic


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
        choose_output: Callable[[], Path] | None = None,
        on_telemetry: Callable[..., None] | None = None,
    ) -> None:
        self.owner = owner
        self.converter = converter
        self.output_dir = Path(output_dir)
        self.profile_var = profile_variable
        self.on_telemetry = on_telemetry or (lambda *_args: None)
        self._telemetry_run_id = ""
        self.on_complete = on_complete
        self.on_closed = on_closed
        self.choose_output = choose_output
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
        self.metrics = window_logical_metrics(popup)
        limit = bounded_window_size(
            popup.winfo_screenwidth(), popup.winfo_screenheight()
        )
        popup.minsize(min(self._px(620), limit[0]), min(self._px(500), limit[1]))
        self.popup = popup

        self._build_content()
        popup.protocol("WM_DELETE_WINDOW", self._request_close)
        popup.bind("<Escape>", lambda _event: self._request_close())
        popup.bind("<Destroy>", self._destroyed, add="+")

    def _build_content(self) -> None:
        surface = ActionDialogSurface(
            self.popup,
            padx=26,
            pady=16,
            footer_gap=10,
            protect_status=True,
            allow_body_scroll=self.metrics.scale > 1,
        )
        self.dialog_surface = surface
        root = surface.body
        root.columnconfigure(0, weight=1)
        self._build_intro(root)
        self._build_choices(root)
        self._build_preview_and_profile(root)
        self._build_destination(root)
        if surface.status is None:  # pragma: no cover - construction contract
            raise RuntimeError("Local conversion requires protected status content")
        self._build_progress(surface.status)
        self._build_actions(surface.footer)

    def _px(self, value: int) -> int:
        return self.metrics.px(value)

    def _label(self, parent: tk.Misc, **options) -> ttk.Label:
        role = ttk.Style(parent).lookup(options.get("style", "TLabel"), "font")
        font = tuple(parent.tk.splitlist(role)) if role else FONT_UI
        label = ttk.Label(parent, font=self.metrics.font(font), **options)
        if options.get("wraplength"):
            maximum = int(options["wraplength"])

            def fit(_event):
                # A withdrawn popup has only requested geometry. Feeding that
                # back into text wrapping can alternate its natural widths.
                if not self.popup.winfo_viewable() or label.winfo_width() <= 1:
                    return
                width = min(maximum, max(1, label.winfo_width() - 2))
                if int(label.cget("wraplength")) != width:
                    label.configure(wraplength=width)

            label.bind("<Configure>", fit, add="+")
            label.bind("<Map>", fit, add="+")
        return label

    def _build_intro(self, root: ttk.Frame) -> None:
        self._label(root, text="Create MP4 from audio", style="FocusTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self._label(
            root,
            text=("Pair an MP3 with a still image. Your originals stay unchanged."),
            style="Muted.TLabel",
            wraplength=self._px(650),
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(self._px(5), self._px(12)))

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
        row.grid(row=3, column=0, sticky="ew", pady=(self._px(12), self._px(12)))
        row.columnconfigure(1, weight=1)
        self._build_preview(row)
        self._build_profile(row)

    def _build_preview(self, parent: ttk.Frame) -> None:
        preview_shell = tk.Frame(
            parent,
            bg=THEME["surface"],
            width=self._px(168),
            height=self._px(94),
            bd=0,
            highlightthickness=1,
            highlightbackground=THEME["border"],
        )
        preview_shell.grid(row=0, column=0, sticky="nw", padx=(0, self._px(16)))
        preview_shell.pack_propagate(False)
        self.preview = tk.Label(
            preview_shell,
            text="Image preview",
            bg=THEME["surface"],
            fg=THEME["subtle"],
            font=self.metrics.font(FONT_UI_MEDIUM),
            bd=0,
            highlightthickness=0,
        )
        self.preview.pack(fill="both", expand=True)

    def _build_profile(self, parent: ttk.Frame) -> None:
        profile = ttk.Frame(parent, style="FocusShell.TFrame")
        profile.grid(row=0, column=1, sticky="new")
        profile.columnconfigure(0, weight=1)
        self._label(profile, text="OUTPUT PROFILE", style="FocusEyebrow.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.profile_combo = ChoiceDropdown(
            profile,
            textvariable=self.profile_var,
            values=LOCAL_VIDEO_PROFILE_OPTIONS,
            state="readonly",
        )
        self.profile_combo.grid(row=1, column=0, sticky="ew", pady=(self._px(5), 0))
        self.profile_description_var = tk.StringVar()
        self._label(
            profile,
            textvariable=self.profile_description_var,
            style="Muted.TLabel",
            wraplength=self._px(350),
            justify="left",
        ).grid(row=2, column=0, sticky="ew", pady=(self._px(7), 0))
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
        self._label(destination, text="OUTPUT", style="FocusEyebrow.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.destination_var = tk.StringVar(destination, value=str(self.output_dir))
        self.destination_entry = ProductEntry(
            destination,
            textvariable=self.destination_var,
            state="readonly",
        )
        self.destination_entry.grid(row=1, column=0, sticky="ew", pady=(self._px(5), 0))
        self.destination_button = ProductButton(
            destination,
            text="Choose folder",
            command=self._choose_output,
            style="FocusQuiet.TButton",
            state="normal" if self.choose_output is not None else "disabled",
        )
        self.destination_button.grid(
            row=1, column=1, padx=(self._px(10), 0), pady=(self._px(5), 0)
        )
        self._label(
            destination,
            text="Your MP4 saves directly here. No extra folder.",
            style="Muted.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(self._px(3), 0))

    def _build_progress(self, root: ttk.Frame) -> None:
        self.progress = SleekProgressbar(root, maximum=100, value=0, height=7)
        self.progress.grid(row=0, column=0, sticky="ew")
        self.status_var = tk.StringVar(value="Choose both files to continue.")
        self._label(
            root,
            textvariable=self.status_var,
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(self._px(6), 0))

    def _build_actions(self, actions: ttk.Frame) -> None:
        actions.columnconfigure(0, weight=1)
        self.cancel_button = ProductButton(
            actions,
            text="Cancel",
            command=self._request_close,
            style="FocusQuiet.TButton",
        )
        self.cancel_button.grid(row=0, column=1, padx=(0, self._px(8)))
        self.create_button = ProductButton(
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
        item.grid(row=row, column=0, sticky="ew", pady=(0, self._px(9)))
        item.columnconfigure(0, weight=1)
        self._label(item, text=eyebrow, style="FocusEyebrow.TLabel").grid(
            row=0, column=0, sticky="w", columnspan=2
        )
        field = ProductEntry(item, textvariable=variable, state="readonly")
        field.grid(
            row=1, column=0, sticky="ew", pady=(self._px(5), 0), padx=(0, self._px(9))
        )
        button = ProductButton(
            item,
            text=button_text,
            command=command,
            style="FocusQuiet.TButton",
        )
        button.grid(row=1, column=1, sticky="e", pady=(self._px(5), 0))
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
                logical_size = (self._px(166), self._px(92))
                density = surface_backing_scale(self.popup)
                pixels = tuple(value * density for value in logical_size)
                image.thumbnail(pixels, getattr(Image, "Resampling", Image).LANCZOS)
                canvas = Image.new("RGB", pixels, THEME["surface"])
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
                self._preview_image = create_surface_image(
                    self.popup, canvas, density, logical_size=logical_size
                )[0]
            finally:
                canvas.close()
            self.preview.configure(
                image=self._preview_image,
                text="",
                width=self._px(166),
                height=self._px(92),
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

    def _choose_output(self) -> None:
        if self._worker is not None or self.choose_output is None:
            return
        self.output_dir = self.choose_output()
        self.destination_var.set(str(self.output_dir))

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
        self.destination_button.configure(state="disabled")
        self.profile_combo.configure(state="disabled")
        self.create_button.configure(state="disabled")
        self.cancel_button.configure(text="Stop")
        self.status_var.set("Checking local files…")

        def run() -> None:
            diagnostics: list[FailureDiagnostic] = []
            try:
                result = self.converter.convert(
                    request,
                    on_progress=lambda progress: self._events.put(
                        ("progress", progress)
                    ),
                    on_failure=diagnostics.append,
                    on_commit=lambda committed: self._events.put(
                        ("committed", committed)
                    ),
                )
                self._events.put(("complete", result))
            except LocalAudioVideoCancelled as exc:
                self._events.put(("cancelled", str(exc)))
            except Exception as exc:  # noqa: BLE001 - presentation boundary
                diagnostic = diagnostics[-1] if diagnostics else capture_failure(exc)
                self._events.put(
                    ("error", LocalConversionFailure(str(exc), diagnostic))
                )

        self._worker = threading.Thread(
            target=run,
            name="vodforge-local-audio-video",
            daemon=True,
        )
        self._telemetry_run_id = request.run_id
        self._worker.start()
        self.on_telemetry("local_conversion_started", request.run_id)
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
            elif kind == "committed" and isinstance(payload, LocalAudioVideoCommit):
                self.on_telemetry(
                    "local_conversion_committed", self._telemetry_run_id, None, payload
                )
            elif kind == "complete" and isinstance(payload, LocalAudioVideoResult):
                terminal = True
                self._worker = None
                self.on_complete(payload)
                self._destroy()
            elif kind in {"cancelled", "error"}:
                self.on_telemetry(
                    "local_conversion_stopped"
                    if kind == "cancelled"
                    else "local_conversion_failed",
                    self._telemetry_run_id,
                    *(
                        [payload.diagnostic]
                        if isinstance(payload, LocalConversionFailure)
                        else []
                    ),
                )
                terminal = True
                self._worker = None
                message = (
                    payload.message
                    if isinstance(payload, LocalConversionFailure)
                    else str(payload)
                ) or "The conversion did not finish."
                self.cancel_button.configure(text="Cancel", state="normal")
                self.audio_button.configure(state="normal")
                self.image_button.configure(state="normal")
                self.destination_button.configure(
                    state="normal" if self.choose_output is not None else "disabled"
                )
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
            centered_toplevel_geometry(
                self.owner, width=700, height=570, target=self.popup
            ),
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
