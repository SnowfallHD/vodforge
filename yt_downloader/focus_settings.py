from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import colorchooser, ttk
from typing import Any

from .models import CookieSource, OutputType
from .ui_layout import centered_toplevel_geometry
from .ui_theme import CUSTOM_THEME_NAME, THEME
from .ui_widgets import SegmentedSelector, ToolTip, reveal_toplevel


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
    on_closed: Callable[[], object]


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

        popup = tk.Toplevel(owner)
        popup.withdraw()
        popup.title(f"{app_name} Settings")
        popup.transient(owner)
        popup.configure(bg=THEME["bg"])
        popup.resizable(True, True)
        popup.minsize(700, 540)
        self.popup = popup

        root = ttk.Frame(popup, style="FocusShell.TFrame")
        root.pack(fill="both", expand=True, padx=22, pady=20)
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(2, weight=1)

        self._build_heading(root)
        self._build_source_section(root)
        self._build_mp4_section(root, macos=macos)
        self._build_mp3_section(root)
        self._build_appearance_section(root)
        self._build_cloud_section(root)
        self._build_footer(root)

        popup.protocol("WM_DELETE_WINDOW", self.close)
        popup.bind("<Escape>", lambda _event: self.close())
        popup.bind("<Destroy>", self._on_destroy, add="+")

    def _build_heading(self, root: ttk.Frame) -> None:
        heading = ttk.Frame(root, style="FocusShell.TFrame")
        heading.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 16))
        heading.columnconfigure(0, weight=1)
        ttk.Label(
            heading,
            text="Forge settings",
            style="FocusTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            heading,
            text="Every option is available here; the main workspace stays focused.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

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
        ttk.Entry(destination, textvariable=self.bindings.output).grid(
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
        ignore_playlists = ttk.Checkbutton(
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
            text="YOUTUBE ACCESS",
            style="FocusEyebrow.TLabel",
        ).grid(row=6, column=0, sticky="w", pady=(16, 5))
        ttk.Label(
            source,
            text="Optional — use an authorized account only when public access is not enough.",
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
            "Public uses no cookies. Choose cookies.txt or Browser only when YouTube requires sign-in.",
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
            "Use an exported YouTube cookies.txt file for content that requires your authorized account.",
        )

        browser_frame = ttk.Frame(source, style="FocusShell.TFrame")
        browser_frame.grid(row=9, column=0, sticky="ew", pady=(7, 0))
        browser_frame.columnconfigure(0, weight=1)
        browser_combo = ttk.Combobox(
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
            "Read YouTube cookies directly from the selected local browser. "
            "VODForge does not save their contents.",
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
        tags_entry = ttk.Entry(source, textvariable=self.bindings.tags)
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
        quality_combo = ttk.Combobox(
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
            text="Output mode",
            style="Muted.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=4)
        export_combo = ttk.Combobox(
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
        manual_fields = (
            ("Video bitrate (kbps)", bindings.manual_video_bitrate, None),
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
                widget: ttk.Entry | ttk.Combobox = ttk.Entry(
                    field,
                    textvariable=variable,
                )
            else:
                widget = ttk.Combobox(
                    field,
                    textvariable=variable,
                    values=values,
                    state="readonly",
                    width=12,
                )
                self._bind_readonly_combo(widget)
            widget.grid(row=1, column=0, sticky="ew")
        self.manual_frame = manual

    def _build_mp4_output_flags(
        self,
        mp4_output: ttk.Frame,
        *,
        macos: bool,
    ) -> None:
        bindings = self.bindings
        ttk.Checkbutton(
            mp4_output,
            text="Save thumbnail",
            variable=bindings.write_thumbnail,
        ).grid(row=5, column=0, sticky="w", pady=2)
        ttk.Checkbutton(
            mp4_output,
            text="Save compact JSON",
            variable=bindings.write_info_json,
        ).grid(row=5, column=1, sticky="w", pady=2)
        ttk.Checkbutton(
            mp4_output,
            text="Embed thumbnail",
            variable=bindings.embed_thumbnail,
        ).grid(row=6, column=0, sticky="w", pady=2)
        ttk.Checkbutton(
            mp4_output,
            text="Embed metadata",
            variable=bindings.embed_metadata,
        ).grid(row=6, column=1, sticky="w", pady=2)
        nvenc_label = (
            "NVIDIA NVENC (Windows only)" if macos else "Use NVIDIA NVENC GPU encoding"
        )
        nvenc = ttk.Checkbutton(
            mp4_output,
            text=nvenc_label,
            variable=bindings.use_nvenc,
        )
        nvenc.grid(row=7, column=0, columnspan=2, sticky="w", pady=2)
        ToolTip(
            nvenc,
            "Use a supported NVIDIA GPU for MP4 encoding on Windows. "
            "CPU encoding remains the compatibility default.",
        )
        if macos:
            nvenc.state(["disabled"])

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
        mp3_quality_combo = ttk.Combobox(
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
        sample_rate_combo = ttk.Combobox(
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
        channels_combo = ttk.Combobox(
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
        mp3_metadata = ttk.Checkbutton(
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
                "Maximum 320 kbps minimizes additional encoding loss. Preserve source "
                "avoids unnecessary resampling; choose 44.1 or 48 kHz only when your "
                "music or DAW workflow requires it."
            ),
            style="Muted.TLabel",
            wraplength=330,
            justify="left",
        ).grid(row=8, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.mp3_cover_file_frame = cover_file

    def _build_cloud_section(self, root: ttk.Frame) -> None:
        cloud = ttk.Frame(root, style="CloudPreview.TFrame", padding=(14, 10))
        cloud.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        cloud.columnconfigure(0, weight=1)
        ttk.Label(
            cloud,
            text="VODForge Cloud",
            style="CloudTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            cloud,
            text="Run downloads even when this computer is offline.",
            style="FocusSurfaceMuted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        cloud_action = ttk.Frame(cloud, style="FocusSurface.TFrame")
        cloud_action.grid(row=0, column=1, rowspan=2, sticky="e", padx=(18, 0))
        ttk.Label(
            cloud_action,
            text="EARLY ACCESS",
            style="CloudBadge.TLabel",
        ).pack(anchor="e", pady=(0, 4))
        cloud_button = ttk.Button(
            cloud_action,
            text="Join early access",
            command=self.actions.open_cloud_early_access,
            style="FocusQuiet.TButton",
        )
        cloud_button.pack(anchor="e")
        ToolTip(
            cloud_button,
            "Open the VODForge Cloud early-access signup page in your browser.",
        )

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
        theme_combo = ttk.Combobox(
            appearance,
            textvariable=self.bindings.appearance_theme,
            values=self.options.appearance_themes,
            state="readonly",
            width=18,
        )
        theme_combo.grid(row=1, column=1, sticky="ew", padx=(0, 18))
        self._bind_readonly_combo(theme_combo)
        ttk.Label(appearance, text="Custom accent", style="Muted.TLabel").grid(
            row=1, column=2, sticky="w", padx=(0, 8)
        )
        accent_controls = ttk.Frame(appearance, style="FocusShell.TFrame")
        accent_controls.grid(row=1, column=3, sticky="ew")
        accent_controls.columnconfigure(0, weight=1)
        ttk.Entry(
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
            text="Choose Custom accent to use a #RRGGBB color. Appearance updates the next time VODForge opens.",
            style="Muted.TLabel",
            wraplength=680,
            justify="left",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(5, 0))

    def _choose_accent_color(self) -> None:
        _rgb, selected = colorchooser.askcolor(
            color=self.bindings.custom_accent.get(),
            title="Choose VODForge accent color",
            parent=self.popup,
        )
        if selected:
            self.bindings.custom_accent.set(str(selected).lower())
            self.bindings.appearance_theme.set(CUSTOM_THEME_NAME)

    def _build_footer(self, root: ttk.Frame) -> None:
        footer = ttk.Frame(root, style="FocusShell.TFrame")
        footer.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        footer.columnconfigure(0, weight=1)
        preview_button = ttk.Button(
            footer,
            text="Preview metadata",
            command=self._preview_and_close,
            style="FocusQuiet.TButton",
        )
        preview_button.grid(row=0, column=0, sticky="w")
        ttk.Button(
            footer,
            text="Done",
            command=self.close,
            style="Accent.TButton",
        ).grid(row=0, column=1, sticky="e")

    def _bind_readonly_combo(
        self,
        combo: ttk.Combobox,
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
        width = min(820, max(700, self.popup.winfo_reqwidth()))
        height = min(720, max(560, self.popup.winfo_reqheight()))
        reveal_toplevel(
            self.popup,
            centered_toplevel_geometry(self.owner, width, height),
        )
        self.owner.after_idle(self.actions.record_cloud_cta_seen)

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
        self.actions.on_closed()
