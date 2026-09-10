from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import colorchooser, ttk
from typing import Any

from .models import CookieSource, OutputType
from .ui_chrome import pro_wordmark
from .ui_layout import centered_toplevel_geometry
from .ui_theme import CUSTOM_THEME_NAME, THEME
from .ui_widgets import (
    ActionDialogSurface,
    ChoiceDropdown,
    ModernCheckbox,
    ProductEntry,
    SegmentedSelector,
    ToolTip,
    reveal_toplevel,
)
from .youtube_access import (
    ACCESS_DESCRIPTION,
    ACCESS_TITLE,
    ACCESS_TOOLTIP,
    BROWSER_TOOLTIP,
)


@dataclass(frozen=True, slots=True)
class FocusSettingsBindings:
    """Tk variables whose semantic values remain owned by ``DownloaderApp``."""

    output: tk.StringVar
    url_list_file: tk.StringVar
    single_video_only: tk.BooleanVar
    cookie_source: tk.StringVar
    cookie_file: tk.StringVar
    cookie_browser: tk.StringVar
    tags: tk.StringVar
    quality: tk.StringVar
    export_mode_choice: tk.StringVar
    export_mode_description: tk.StringVar
    manual_video_bitrate: tk.StringVar
    manual_audio_bitrate: tk.StringVar
    manual_audio_codec: tk.StringVar
    manual_sample_rate: tk.StringVar
    manual_channels: tk.StringVar
    manual_preset: tk.StringVar
    write_thumbnail: tk.BooleanVar
    write_info_json: tk.BooleanVar
    embed_thumbnail: tk.BooleanVar
    embed_metadata: tk.BooleanVar
    use_nvenc: tk.BooleanVar
    mp3_quality: tk.StringVar
    mp3_sample_rate: tk.StringVar
    mp3_channels: tk.StringVar
    mp3_embed_metadata: tk.BooleanVar
    mp3_cover_art_mode: tk.StringVar
    mp3_cover_art_description: tk.StringVar
    mp3_custom_cover_art: tk.StringVar
    appearance_theme: tk.StringVar
    custom_accent: tk.StringVar
    anonymous_usage_analytics: tk.BooleanVar
    manual_rate_control: tk.StringVar | None = None
    manual_crf: tk.StringVar | None = None


@dataclass(frozen=True, slots=True)
class FocusSettingsOptions:
    quality: tuple[str, ...]
    export_modes: tuple[str, ...]
    manual_audio_codecs: tuple[str, ...]
    cookie_sources: tuple[str, ...]
    cookie_browsers: tuple[str, ...]
    mp3_quality: tuple[str, ...]
    mp3_sample_rates: tuple[str, ...]
    mp3_channels: tuple[str, ...]
    mp3_cover_art: tuple[str, ...]
    appearance_themes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FocusSettingsActions:
    browse_output: Callable[[], object]
    load_url_list_file: Callable[[], object]
    load_cookie_file: Callable[[], object]
    browser_cookie_selected: Callable[[], object]
    refresh_manual_visibility: Callable[[], object]
    choose_custom_cover_art: Callable[[], object]
    clear_custom_cover_art: Callable[[], object]
    open_cloud_early_access: Callable[[], object]
    preview_metadata: Callable[[], bool]
    record_cloud_cta_seen: Callable[[], object]
    apply_appearance: Callable[[], object]
    on_closed: Callable[[], object]
    help_feedback: Callable[[], object] | None = None


class FocusSettingsDialog:
    """Own the Settings window widgets, visibility, and lifecycle only."""

    def __init__(
        self,
        owner: tk.Tk,
        *,
        app_name: str,
        bindings: FocusSettingsBindings,
        options: FocusSettingsOptions,
        actions: FocusSettingsActions,
        macos: bool,
    ) -> None:
        self.owner = owner
        self.bindings = bindings
        self.options = options
        self.actions = actions
        self._closed = False
        self._accent_trace_id: str | None = None

        popup = tk.Toplevel(owner)
        popup.withdraw()
        popup.title(f"{app_name} Settings")
        popup.transient(owner)
        popup.configure(bg=THEME["bg"])
        popup.resizable(True, True)
        popup.minsize(700, 540)
        self.popup = popup

        surface = ActionDialogSurface(
            popup,
            padx=22,
            pady=20,
            footer_gap=14,
            allow_body_scroll=True,
        )
        self.dialog_surface = surface
        root = surface.body
        root.columnconfigure(0, weight=1, uniform="settings-column")
        root.columnconfigure(1, weight=1, uniform="settings-column")
        root.rowconfigure(2, weight=1)

        self._build_heading(root)
        self._build_source_section(root)
        self._build_mp4_section(root, macos=macos)
        self._build_mp3_section(root)
        self._build_original_audio_section(root)
        self._build_appearance_section(root)
        self._build_privacy_section(root)
        self._build_footer(surface.footer)
        self._bind_responsive_copy(root)

        popup.protocol("WM_DELETE_WINDOW", self.close)
        popup.bind("<Escape>", lambda _event: self.close())
        popup.bind("<Destroy>", self._on_destroy, add="+")

    @staticmethod
    def _bind_responsive_copy(parent: tk.Misc) -> None:
        """Settings owns wrapping; helper copy cannot force columns offscreen."""
        for child in parent.winfo_children():
            if isinstance(child, ttk.Label) and int(child.cget("wraplength") or 0) > 0:
                maximum = int(child.cget("wraplength") or 0)

                def fit(event: tk.Event, label=child, limit: int = maximum) -> None:
                    width = min(limit, max(1, event.width - 2))
                    if int(label.cget("wraplength")) != width:
                        label.configure(wraplength=width)

                child.bind("<Configure>", fit, add="+")
            FocusSettingsDialog._bind_responsive_copy(child)

    def _build_heading(self, root: ttk.Frame) -> None:
        heading = ttk.Frame(root, style="FocusShell.TFrame")
        heading.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 16))
        heading.columnconfigure(0, weight=1)
        ttk.Label(
            heading,
            text="Forge settings",
            style="FocusTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")
        self._pro_wordmark = pro_wordmark(heading)
        self.pro_button = ttk.Button(
            heading,
            text="VODForge PRO",
            image=self._pro_wordmark,
            command=self.actions.open_cloud_early_access,
            style="FocusQuiet.TButton",
        )
        self.pro_button.grid(row=0, column=1, sticky="e", padx=(16, 0))
        self._pro_seen_requested = False
        self.pro_button.bind("<Map>", self._record_visible_pro, add="+")
        self.pro_button.bind("<Configure>", self._record_visible_pro, add="+")
        ttk.Label(
            heading,
            text="Every option is available here; the main workspace stays focused.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 0))

    def _record_visible_pro(self, _event: tk.Event | None = None) -> None:
        """Report exposure only after the complete control is in the viewport.

        The telemetry owner retains durable once-per-install and build-policy
        authority; this surface owns only whether its control is visible.
        """
        if self._closed or self._pro_seen_requested:
            return
        try:
            button = self.pro_button
            viewport = self.dialog_surface.viewport
            if viewport is None or not button.winfo_viewable():
                return
            x, y = button.winfo_rootx(), button.winfo_rooty()
            vx, vy = viewport.winfo_rootx(), viewport.winfo_rooty()
            if not (
                vx <= x
                and vy <= y
                and x + button.winfo_width() <= vx + viewport.winfo_width()
                and y + button.winfo_height() <= vy + viewport.winfo_height()
            ):
                return
            self._pro_seen_requested = True
            self.actions.record_cloud_cta_seen()
        except tk.TclError:
            return

    def _build_source_section(self, root: ttk.Frame) -> None:
        source = ttk.Frame(root, style="FocusShell.TFrame")
        source.grid(row=1, column=0, sticky="nsew", padx=(0, 16))
        source.columnconfigure(0, weight=1)
        self._build_destination_controls(source)
        self._build_batch_controls(source)
        self._build_access_controls(source)
        self._build_metadata_controls(source)

    def _build_destination_controls(self, source: ttk.Frame) -> None:
        ttk.Label(
            source,
            text="SAVE LOCATION",
            style="FocusEyebrow.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 7))
        destination = ttk.Frame(source, style="FocusShell.TFrame")
        destination.grid(row=1, column=0, sticky="ew")
        destination.columnconfigure(0, weight=1)
        ProductEntry(destination, textvariable=self.bindings.output).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 6),
        )
        ttk.Button(
            destination,
            text="Browse",
            command=self.actions.browse_output,
            style="FocusQuiet.TButton",
        ).grid(row=0, column=1, sticky="e")

    def _build_batch_controls(self, source: ttk.Frame) -> None:
        ttk.Label(
            source,
            text="BATCH AND PLAYLISTS",
            style="FocusEyebrow.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(16, 7))
        batch_button = ttk.Button(
            source,
            text="Load URL list",
            command=self.actions.load_url_list_file,
            style="FocusQuiet.TButton",
        )
        batch_button.grid(row=3, column=0, sticky="w")
        ToolTip(
            batch_button, "Process a batch of links from a text file, one URL per line."
        )
        ttk.Label(
            source,
            textvariable=self.bindings.url_list_file,
            style="Muted.TLabel",
            wraplength=300,
        ).grid(row=4, column=0, sticky="w", pady=(4, 6))
        ignore_playlists = ModernCheckbox(
            source,
            text="Ignore playlists",
            variable=self.bindings.single_video_only,
        )
        ignore_playlists.grid(row=5, column=0, sticky="w")
        ToolTip(
            ignore_playlists,
            "When a link includes a playlist, download only the linked video or "
            "audio item instead of the full playlist.",
        )

    def _build_access_controls(self, source: ttk.Frame) -> None:
        ttk.Label(
            source,
            text=ACCESS_TITLE,
            style="FocusEyebrow.TLabel",
            wraplength=300,
            justify="left",
        ).grid(row=6, column=0, sticky="w", pady=(16, 5))
        ttk.Label(
            source,
            text=ACCESS_DESCRIPTION,
            style="Muted.TLabel",
            wraplength=300,
            justify="left",
        ).grid(row=7, column=0, sticky="w", pady=(0, 7))
        cookie_selector = SegmentedSelector(
            source,
            variable=self.bindings.cookie_source,
            values=self.options.cookie_sources,
            background=THEME["bg"],
            compact=True,
        )
        cookie_selector.grid(row=8, column=0, sticky="w")
        ToolTip(
            cookie_selector,
            ACCESS_TOOLTIP,
        )

        cookie_file = ttk.Frame(source, style="FocusShell.TFrame")
        cookie_file.grid(row=9, column=0, sticky="ew", pady=(7, 0))
        cookie_file.columnconfigure(0, weight=1)
        ttk.Label(
            cookie_file,
            textvariable=self.bindings.cookie_file,
            style="Muted.TLabel",
            wraplength=180,
        ).grid(row=0, column=0, sticky="w")
        cookie_file_button = ttk.Button(
            cookie_file,
            text="Choose cookies.txt",
            command=self.actions.load_cookie_file,
            style="FocusQuiet.TButton",
        )
        cookie_file_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
        ToolTip(
            cookie_file_button,
            "Manual alternative: choose an exported YouTube cookies.txt file. Try Browser first for easier setup.",
        )

        browser_frame = ttk.Frame(source, style="FocusShell.TFrame")
        browser_frame.grid(row=9, column=0, sticky="ew", pady=(7, 0))
        browser_frame.columnconfigure(0, weight=1)
        browser_combo = ChoiceDropdown(
            browser_frame,
            textvariable=self.bindings.cookie_browser,
            values=self.options.cookie_browsers,
            state="readonly",
            width=24,
        )
        browser_combo.grid(row=0, column=0, sticky="ew")
        self._bind_readonly_combo(
            browser_combo,
            self.actions.browser_cookie_selected,
        )
        ToolTip(
            browser_combo,
            BROWSER_TOOLTIP,
        )
        self.cookie_file_frame = cookie_file
        self.cookie_browser_frame = browser_frame

    def _build_metadata_controls(self, source: ttk.Frame) -> None:
        ttk.Label(
            source,
            text="METADATA",
            style="FocusEyebrow.TLabel",
        ).grid(row=10, column=0, sticky="w", pady=(16, 5))
        ttk.Label(
            source,
            text="Extra tags (comma-separated)",
            style="Muted.TLabel",
        ).grid(row=11, column=0, sticky="w", pady=(0, 3))
        tags_entry = ProductEntry(source, textvariable=self.bindings.tags)
        tags_entry.grid(row=12, column=0, sticky="ew")
        ToolTip(
            tags_entry,
            "Add tags to embedded metadata and the compact metadata file when those outputs are enabled.",
        )

    def _build_mp4_section(self, root: ttk.Frame, *, macos: bool) -> None:
        mp4_output = ttk.Frame(root, style="FocusShell.TFrame")
        mp4_output.grid(row=1, column=1, sticky="nsew", padx=(16, 0))
        mp4_output.columnconfigure(1, weight=1)
        ttk.Label(
            mp4_output,
            text="MP4 VIDEO",
            style="FocusEyebrow.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self._build_mp4_mode_controls(mp4_output)
        self._build_manual_controls(mp4_output)
        self._build_mp4_output_flags(mp4_output, macos=macos)
        self.mp4_frame = mp4_output

    def _build_mp4_mode_controls(self, mp4_output: ttk.Frame) -> None:
        ttk.Label(
            mp4_output,
            text="Quality ceiling",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=4)
        quality_combo = ChoiceDropdown(
            mp4_output,
            textvariable=self.bindings.quality,
            values=self.options.quality,
            state="readonly",
            width=20,
        )
        quality_combo.grid(row=1, column=1, sticky="ew", pady=4)
        self._bind_readonly_combo(quality_combo)
        ToolTip(
            quality_combo,
            "Set the highest resolution VODForge may select from the available YouTube source formats.",
        )
        ttk.Label(
            mp4_output,
            text="Optimize for",
            style="Muted.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=4)
        export_combo = ChoiceDropdown(
            mp4_output,
            textvariable=self.bindings.export_mode_choice,
            values=self.options.export_modes,
            state="readonly",
            width=24,
        )
        export_combo.grid(row=2, column=1, sticky="ew", pady=4)
        self._bind_readonly_combo(
            export_combo,
            self.actions.refresh_manual_visibility,
        )
        ttk.Label(
            mp4_output,
            textvariable=self.bindings.export_mode_description,
            style="Muted.TLabel",
            wraplength=360,
            justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 8))

    def _build_manual_controls(self, mp4_output: ttk.Frame) -> None:
        bindings = self.bindings
        manual = ttk.Frame(mp4_output, style="FocusShell.TFrame")
        manual.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(3, 8))
        manual.columnconfigure(0, weight=1, uniform="manual-field")
        manual.columnconfigure(1, weight=1, uniform="manual-field")
        quality_fields = (
            (
                (
                    "Video rate control",
                    bindings.manual_rate_control,
                    ("CBR", "Quality"),
                ),
                ("Video quality (CRF, 1–51)", bindings.manual_crf, None),
            )
            if bindings.manual_rate_control is not None
            and bindings.manual_crf is not None
            else ()
        )
        manual_fields = quality_fields + (
            ("CBR video bitrate (kbps)", bindings.manual_video_bitrate, None),
            ("Audio bitrate (kbps)", bindings.manual_audio_bitrate, None),
            (
                "Audio codec",
                bindings.manual_audio_codec,
                self.options.manual_audio_codecs,
            ),
            ("Sample rate", bindings.manual_sample_rate, ("44100", "48000")),
            ("Channels", bindings.manual_channels, ("Mono", "Stereo")),
            (
                "Encoding speed",
                bindings.manual_preset,
                (
                    "ultrafast",
                    "superfast",
                    "veryfast",
                    "faster",
                    "fast",
                    "medium",
                    "slow",
                    "slower",
                ),
            ),
        )
        self._custom_rate_widgets: dict[str, ProductEntry | ChoiceDropdown] = {}
        for index, (label, variable, values) in enumerate(manual_fields):
            field = ttk.Frame(manual, style="FocusShell.TFrame")
            field.grid(
                row=index // 2,
                column=index % 2,
                sticky="ew",
                padx=(0, 8) if index % 2 == 0 else (8, 0),
                pady=(0, 7),
            )
            field.columnconfigure(0, weight=1)
            ttk.Label(
                field,
                text=label,
                style="Muted.TLabel",
            ).grid(row=0, column=0, sticky="w", pady=(0, 3))
            if values is None:
                widget: ProductEntry | ChoiceDropdown = ProductEntry(
                    field,
                    textvariable=variable,
                )
            else:
                widget = ChoiceDropdown(
                    field,
                    textvariable=variable,
                    values=values,
                    state="readonly",
                    width=12,
                )
                self._bind_readonly_combo(widget)
            widget.grid(row=1, column=0, sticky="ew")
            if variable is bindings.manual_video_bitrate:
                self._custom_rate_widgets["CBR"] = widget
            elif variable is bindings.manual_crf:
                self._custom_rate_widgets["Quality"] = widget
                ToolTip(
                    widget,
                    "Lower CRF preserves more detail and usually creates a larger file. 18–25 is a useful starting range.",
                )
        self.manual_frame = manual
        if bindings.manual_rate_control is not None:
            self._manual_rate_trace: str | None = (
                bindings.manual_rate_control.trace_add(
                    "write", lambda *_args: self._refresh_custom_rate_controls()
                )
            )
            self._refresh_custom_rate_controls()

    def _refresh_custom_rate_controls(self) -> None:
        variable = self.bindings.manual_rate_control
        if variable is not None:
            for mode, widget in self._custom_rate_widgets.items():
                widget.configure(
                    state="normal" if variable.get() == mode else "disabled"
                )

    def _build_mp4_output_flags(
        self,
        mp4_output: ttk.Frame,
        *,
        macos: bool,
    ) -> None:
        bindings = self.bindings
        ModernCheckbox(
            mp4_output,
            text="Save thumbnail",
            variable=bindings.write_thumbnail,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=5)
        ModernCheckbox(
            mp4_output,
            text="Save compact JSON",
            variable=bindings.write_info_json,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=5)
        ModernCheckbox(
            mp4_output,
            text="Embed thumbnail",
            variable=bindings.embed_thumbnail,
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=5)
        ModernCheckbox(
            mp4_output,
            text="Embed metadata",
            variable=bindings.embed_metadata,
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=5)
        nvenc_label = (
            "NVIDIA NVENC for CBR (Windows only)"
            if macos
            else "Use NVIDIA NVENC for CBR encoding"
        )
        nvenc = ModernCheckbox(
            mp4_output,
            text=nvenc_label,
            variable=bindings.use_nvenc,
        )
        nvenc.grid(row=9, column=0, columnspan=2, sticky="w", pady=5)
        ToolTip(
            nvenc,
            "Use a supported NVIDIA GPU for MP4 encoding on Windows. "
            "CPU encoding remains the compatibility default.",
        )
        if macos:
            nvenc.state(["disabled"])

    def _build_original_audio_section(self, root: ttk.Frame) -> None:
        frame = ttk.Frame(root, style="FocusShell.TFrame")
        frame.grid(row=1, column=1, sticky="nsew", padx=(16, 0))
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text="ORIGINAL AUDIO", style="FocusEyebrow.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 12)
        )
        ttk.Label(
            frame,
            text="Keep the source. Skip the extra compression.",
            style="FocusSection.TLabel",
            wraplength=330,
        ).grid(row=1, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(
            frame,
            text="Saves the best available Opus or AAC audio stream without re-encoding. The codec, sample rate, and channels stay unchanged.",
            style="Muted.TLabel",
            wraplength=330,
            justify="left",
        ).grid(row=2, column=0, sticky="ew")
        ttk.Label(
            frame,
            text="Opus saves as .opus. AAC saves as .m4a.\nNo bitrate or conversion settings needed.",
            style="Muted.TLabel",
            wraplength=330,
            justify="left",
        ).grid(row=3, column=0, sticky="ew", pady=(16, 0))
        self.original_audio_frame = frame

    def _build_mp3_section(self, root: ttk.Frame) -> None:
        mp3_output = ttk.Frame(root, style="FocusShell.TFrame")
        mp3_output.grid(row=1, column=1, sticky="nsew", padx=(16, 0))
        mp3_output.columnconfigure(1, weight=1)
        ttk.Label(
            mp3_output,
            text="MP3 AUDIO",
            style="FocusEyebrow.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self._build_mp3_encoding_controls(mp3_output)
        self._build_mp3_cover_controls(mp3_output)
        self.mp3_frame = mp3_output

    def _build_mp3_encoding_controls(self, mp3_output: ttk.Frame) -> None:
        bindings = self.bindings
        ttk.Label(
            mp3_output,
            text="Encoding quality",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=4)
        mp3_quality_combo = ChoiceDropdown(
            mp3_output,
            textvariable=bindings.mp3_quality,
            values=self.options.mp3_quality,
            state="readonly",
            width=24,
        )
        mp3_quality_combo.grid(row=1, column=1, sticky="ew", pady=4)
        self._bind_readonly_combo(mp3_quality_combo)
        ToolTip(
            mp3_quality_combo,
            "Set the MP3 export bitrate. Higher settings reduce additional encoding "
            "loss but cannot restore detail missing from YouTube's source audio.",
        )
        ttk.Label(
            mp3_output,
            text="Sample rate",
            style="Muted.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=4)
        sample_rate_combo = ChoiceDropdown(
            mp3_output,
            textvariable=bindings.mp3_sample_rate,
            values=self.options.mp3_sample_rates,
            state="readonly",
            width=24,
        )
        sample_rate_combo.grid(row=2, column=1, sticky="ew", pady=4)
        self._bind_readonly_combo(sample_rate_combo)
        ToolTip(
            sample_rate_combo,
            "Preserve source avoids unnecessary resampling. Choose 44.1 or 48 kHz "
            "only when a music or DAW workflow requires it.",
        )
        ttk.Label(
            mp3_output,
            text="Channels",
            style="Muted.TLabel",
        ).grid(row=3, column=0, sticky="w", pady=4)
        channels_combo = ChoiceDropdown(
            mp3_output,
            textvariable=bindings.mp3_channels,
            values=self.options.mp3_channels,
            state="readonly",
            width=24,
        )
        channels_combo.grid(row=3, column=1, sticky="ew", pady=4)
        self._bind_readonly_combo(channels_combo)
        ToolTip(
            channels_combo,
            "Preserve the source channel layout, or force Stereo or Mono for a "
            "specific production workflow.",
        )
        mp3_metadata = ModernCheckbox(
            mp3_output,
            text="Embed title, artist, and tags",
            variable=bindings.mp3_embed_metadata,
        )
        mp3_metadata.grid(row=4, column=0, columnspan=2, sticky="w", pady=(5, 2))
        ToolTip(
            mp3_metadata,
            "Write standard ID3 title, artist, and tag information into the MP3 file.",
        )

    def _build_mp3_cover_controls(self, mp3_output: ttk.Frame) -> None:
        ttk.Label(
            mp3_output,
            text="Cover art",
            style="Muted.TLabel",
        ).grid(row=5, column=0, sticky="w", pady=(8, 4))
        cover_selector = SegmentedSelector(
            mp3_output,
            variable=self.bindings.mp3_cover_art_mode,
            values=self.options.mp3_cover_art,
            background=THEME["bg"],
            compact=True,
        )
        cover_selector.grid(row=5, column=1, sticky="w", pady=(8, 4))
        ToolTip(
            cover_selector,
            "No Art leaves the MP3 unembedded. YouTube art or Custom art writes a "
            "front-cover image into the file.",
        )
        ttk.Label(
            mp3_output,
            textvariable=self.bindings.mp3_cover_art_description,
            style="Muted.TLabel",
            wraplength=330,
            justify="left",
        ).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(3, 0))
        cover_file = ttk.Frame(mp3_output, style="FocusShell.TFrame")
        cover_file.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        cover_file.columnconfigure(0, weight=1)
        ttk.Label(
            cover_file,
            textvariable=self.bindings.mp3_custom_cover_art,
            style="Muted.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            cover_file,
            text="Replace image",
            command=self.actions.choose_custom_cover_art,
            style="FocusQuiet.TButton",
        ).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(
            cover_file,
            text="Clear",
            command=self.actions.clear_custom_cover_art,
            style="FocusQuiet.TButton",
        ).grid(row=0, column=2, padx=(6, 0))
        ttk.Label(
            mp3_output,
            text=(
                "YouTube audio is already compressed. MP3 adds another encoding step; "
                "320 kbps reduces that loss but cannot restore missing detail."
            ),
            style="Muted.TLabel",
            wraplength=330,
            justify="left",
        ).grid(row=8, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.mp3_cover_file_frame = cover_file

    def _build_privacy_section(self, root: ttk.Frame) -> None:
        privacy = ttk.Frame(root, style="FocusShell.TFrame")
        privacy.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        privacy.columnconfigure(0, weight=1)
        ttk.Label(
            privacy,
            text="PRIVACY",
            style="FocusEyebrow.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 7))
        usage = ModernCheckbox(
            privacy,
            text="Share anonymous analytics",
            variable=self.bindings.anonymous_usage_analytics,
        )
        usage.grid(row=1, column=0, sticky="w")
        ToolTip(
            usage,
            "Share coarse feature and reliability events. VODForge never sends "
            "download URLs, titles, filenames, paths, searches, tags, or notes.",
        )
        ttk.Label(
            privacy,
            text=("Analytics helps improve VODForge, turn off at any time."),
            style="Muted.TLabel",
            wraplength=680,
            justify="left",
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))

    def _build_appearance_section(self, root: ttk.Frame) -> None:
        appearance = ttk.Frame(root, style="FocusShell.TFrame")
        appearance.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        appearance.columnconfigure(1, weight=1)
        appearance.columnconfigure(3, weight=1)
        ttk.Label(
            appearance,
            text="APPEARANCE",
            style="FocusEyebrow.TLabel",
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 7))
        ttk.Label(appearance, text="Theme", style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", padx=(0, 8)
        )
        theme_combo = ChoiceDropdown(
            appearance,
            textvariable=self.bindings.appearance_theme,
            values=self.options.appearance_themes,
            state="readonly",
            width=18,
        )
        theme_combo.grid(row=1, column=1, sticky="ew", padx=(0, 18))
        self._bind_readonly_combo(theme_combo, self.actions.apply_appearance)
        ttk.Label(appearance, text="Custom accent", style="Muted.TLabel").grid(
            row=1, column=2, sticky="w", padx=(0, 8)
        )
        accent_controls = ttk.Frame(appearance, style="FocusShell.TFrame")
        accent_controls.grid(row=1, column=3, sticky="ew")
        accent_controls.columnconfigure(0, weight=1)
        ProductEntry(
            accent_controls,
            textvariable=self.bindings.custom_accent,
            width=12,
        ).grid(row=0, column=0, sticky="ew")
        ttk.Button(
            accent_controls,
            text="Choose",
            command=self._choose_accent_color,
            style="FocusQuiet.TButton",
        ).grid(row=0, column=1, padx=(6, 0))
        ttk.Label(
            appearance,
            text="Choose Custom accent to use a #RRGGBB color. Appearance updates immediately.",
            style="Muted.TLabel",
            wraplength=680,
            justify="left",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(5, 0))
        self._accent_trace_id = self.bindings.custom_accent.trace_add(
            "write", lambda *_args: self.actions.apply_appearance()
        )

    def _choose_accent_color(self) -> None:
        _rgb, selected = colorchooser.askcolor(
            color=self.bindings.custom_accent.get(),
            title="Choose VODForge accent color",
            parent=self.popup,
        )
        if selected:
            self.bindings.custom_accent.set(str(selected).lower())
            self.bindings.appearance_theme.set(CUSTOM_THEME_NAME)
            self.actions.apply_appearance()

    def apply_theme(self) -> None:
        """Patch the live Settings surface after its palette changes."""

        try:
            self.popup.configure(bg=THEME["bg"])
        except tk.TclError:
            return
        self.dialog_surface.apply_theme()
        pending = list(self.popup.winfo_children())
        while pending:
            widget = pending.pop()
            apply_theme = getattr(widget, "apply_theme", None)
            if callable(apply_theme):
                apply_theme()
            try:
                pending.extend(widget.winfo_children())
            except tk.TclError:
                continue

    def _build_footer(self, footer: ttk.Frame) -> None:
        footer.columnconfigure(0, weight=1)
        preview_button = ttk.Button(
            footer,
            text="Preview metadata",
            command=self._preview_and_close,
            style="FocusQuiet.TButton",
        )
        preview_button.grid(row=0, column=0, sticky="w")
        if self.actions.help_feedback is not None:
            ttk.Button(
                footer, text="Help & feedback", command=self.actions.help_feedback
            ).grid(row=0, column=1, padx=8)
        ttk.Button(
            footer,
            text="Done",
            command=self.close,
            style="Accent.TButton",
        ).grid(row=0, column=2, sticky="e")

    def _bind_readonly_combo(
        self,
        combo: ChoiceDropdown,
        command: Callable[[], object] | None = None,
    ) -> None:
        """Run the selection action without leaving native entry text selected."""

        def selected(_event: tk.Event[Any]) -> None:
            if command is not None:
                command()

            def release_selection() -> None:
                try:
                    combo.selection_clear()
                    self.popup.focus_set()
                except tk.TclError:
                    return

            self.popup.after_idle(release_selection)

        combo.bind("<<ComboboxSelected>>", selected, add="+")

    @staticmethod
    def _set_frame_visible(frame: ttk.Frame, visible: bool) -> bool:
        try:
            if not frame.winfo_exists():
                return False
            if visible:
                frame.grid()
            else:
                frame.grid_remove()
            return True
        except tk.TclError:
            return False

    def refresh_output_sections(self, output_type: OutputType) -> None:
        self._set_frame_visible(self.mp4_frame, output_type == OutputType.MP4)
        self._set_frame_visible(self.mp3_frame, output_type == OutputType.MP3)
        self._set_frame_visible(
            self.original_audio_frame, output_type == OutputType.ORIGINAL
        )

    def refresh_manual_settings(self, manual_override: bool) -> None:
        self._set_frame_visible(self.manual_frame, manual_override)

    def refresh_cookie_source(self, source: CookieSource) -> None:
        self._set_frame_visible(
            self.cookie_file_frame,
            source == CookieSource.FILE,
        )
        self._set_frame_visible(
            self.cookie_browser_frame,
            source == CookieSource.BROWSER,
        )

    def refresh_cover_art_mode(self, mode: str) -> None:
        self._set_frame_visible(
            self.mp3_cover_file_frame,
            mode == "Custom art",
        )

    def show(self) -> None:
        self.popup.update_idletasks()
        width = 820
        height = 720
        reveal_toplevel(
            self.popup,
            centered_toplevel_geometry(self.owner, width, height),
        )
        self.popup.after_idle(self._record_visible_pro)

    def focus_existing(self) -> bool:
        try:
            if not self.popup.winfo_exists():
                return False
            self.popup.lift()
            self.popup.focus_force()
            return True
        except tk.TclError:
            return False

    def _preview_and_close(self) -> None:
        if self.actions.preview_metadata():
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        try:
            self.popup.destroy()
        except tk.TclError:
            pass
        self._finish_close()

    def _on_destroy(self, event: tk.Event[Any]) -> None:
        if event.widget is self.popup:
            self._finish_close()

    def _finish_close(self) -> None:
        if self._closed:
            return
        self._closed = True
        rate_trace = getattr(self, "_manual_rate_trace", None)
        if rate_trace is not None and self.bindings.manual_rate_control is not None:
            self.bindings.manual_rate_control.trace_remove("write", rate_trace)
            self._manual_rate_trace = None
        accent_trace_id = getattr(self, "_accent_trace_id", None)
        if accent_trace_id is not None:
            try:
                self.bindings.custom_accent.trace_remove("write", accent_trace_id)
            except (tk.TclError, ValueError):
                pass
            self._accent_trace_id = None
        self.actions.on_closed()
