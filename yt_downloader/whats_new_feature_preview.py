"""Offline, compact feature exhibits composed from production UI primitives.

Example values stay local to the exhibit: no persistence, downloads or playback.
Text is rendered by Tk at display resolution, never baked into resized artwork.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageOps, ImageTk

from .activity_ui import ActivityLogText
from .export_planning import EXPORT_MODES, QUALITY_OPTIONS
from .local_audio_video import LOCAL_VIDEO_PROFILE_OPTIONS
from .media_player_ui import PlayerTransportButton, PlayerVolumeControl
from .models import CookieSource
from .ui_theme import THEME
from .ui_widgets import ChoiceDropdown, ModernCheckbox, ProductEntry, SegmentedSelector
from .whats_new import NativePreview
from .whats_new_activity_demo import ActivityDemo
from .whats_new_audio_demo import OriginalAudioDemo
from .youtube_access import COOKIE_BROWSER_OPTIONS, COOKIE_SOURCE_OPTIONS


def render_native_preview(parent: tk.Misc, preview: NativePreview) -> tk.Widget:
    """Single entry point for every present and future carousel exhibit."""
    if preview is NativePreview.WELCOME_ACTIVITY:
        panel = ActivityDemo(parent, interval_ms=200)
        # Center the visible compact exhibit, not a wide empty log viewport.
        panel.preferred_width = 300
        panel.preferred_height = 130
        return panel
    if preview is NativePreview.ACTIVITY_MODE:
        return ActivityDemo(parent)
    if preview is NativePreview.ORIGINAL_AUDIO:
        return OriginalAudioDemo(parent)
    return FeaturePreview(parent, preview.value)


class FeaturePreview(ttk.Frame):
    """Presentation only; real widgets with isolated illustrative values."""

    def __init__(self, parent: tk.Misc, key: str) -> None:
        super().__init__(parent, style="FocusShell.TFrame")
        self.columnconfigure(0, weight=1)
        self.variables: list[tk.Variable] = []
        self.preferred_width = 430
        self.preferred_height = 190
        if key == "ui-activity":
            self.preferred_width = 280
            self.preferred_height = 130
            log = ActivityLogText(
                self,
                compact=True,
                height=6,
                bg=THEME["bg"],
                fg=THEME["muted"],
                bd=0,
                highlightthickness=0,
            )
            log.pack(fill="both", expand=True)
            log.request(
                "Getting video information\nDownloading media\nConverting media\n"
                "Checking the output\n[success] Download complete"
            )
        elif key == "ui-settings":
            self._label("MP4 VIDEO", 0)
            self._choice("1080p Full HD", tuple(QUALITY_OPTIONS), 1)
            self._choice(EXPORT_MODES[0], tuple(EXPORT_MODES), 2)
            value = tk.BooleanVar(self, True)
            self.variables.append(value)
            ModernCheckbox(self, text="Save thumbnail", variable=value).grid(
                row=3, column=0, sticky="w", pady=5
            )
        elif key == "playlists":
            self.preferred_width = 220
            self.preferred_height = 65
            self._label("BATCH AND PLAYLISTS", 0)
            ignore_playlists = tk.BooleanVar(self, False)
            self.variables.append(ignore_playlists)
            ModernCheckbox(
                self, text="Ignore playlists", variable=ignore_playlists
            ).grid(row=1, column=0, sticky="w", pady=5)
        elif key == "youtube-access":
            self.preferred_width = 340
            self.preferred_height = 110
            access = tk.StringVar(self, CookieSource.BROWSER.value)
            self.variables.append(access)
            self._label("YOUTUBE ACCESS", 0)
            SegmentedSelector(
                self,
                variable=access,
                values=COOKIE_SOURCE_OPTIONS,
                background=THEME["bg"],
                compact=True,
            ).grid(row=1, column=0, sticky="w", pady=(0, 8))
            self._choice("Chrome", tuple(COOKIE_BROWSER_OPTIONS), 2)
        elif key == "library":
            self.preferred_height = 210
            self._label("CATEGORY", 0)
            self._choice("Travel", ("Travel",), 1)
            self._label("YOUR TAGS", 2)
            self._entry("mountains, quiet, inspiration", 3)
            self._label("NOTES", 4)
            self._entry("A short film about finding peace in the mountains.", 5)
        elif key == "local-video":
            self._label("MP3 AUDIO", 0)
            self._entry("Choose an MP3 file", 1)
            self._label("STILL IMAGE", 2)
            self._entry("Choose a still image", 3)
            self._label("OUTPUT PROFILE", 4)
            self._choice(LOCAL_VIDEO_PROFILE_OPTIONS[0], LOCAL_VIDEO_PROFILE_OPTIONS, 5)
            self.preferred_height = 210
        elif key in {"ui-player", "player"}:
            self._player(key == "player")
        else:
            raise ValueError(f"Unknown native feature exhibit: {key}")

    def _label(self, text: str, row: int) -> None:
        ttk.Label(self, text=text, style="FocusEyebrow.TLabel").grid(
            row=row, column=0, sticky="w", pady=(5, 2)
        )

    def _entry(self, value: str, row: int) -> None:
        variable = tk.StringVar(self, value)
        self.variables.append(variable)
        ProductEntry(self, textvariable=variable).grid(
            row=row, column=0, sticky="ew", pady=(0, 3)
        )

    def _choice(self, value: str, values: tuple[str, ...], row: int) -> None:
        variable = tk.StringVar(self, value)
        self.variables.append(variable)
        ChoiceDropdown(self, textvariable=variable, values=values).grid(
            row=row, column=0, sticky="ew", pady=(0, 5)
        )

    def _player(self, include_artwork: bool) -> None:
        self.preferred_height = 210 if include_artwork else 110
        if include_artwork:
            path = (
                Path(__file__).resolve().parents[1]
                / "assets/preview_thumbnails/alpine-lake.jpg"
            )
            with Image.open(path) as source:
                self.artwork = ImageTk.PhotoImage(
                    ImageOps.fit(source, (360, 130)), master=self
                )
            tk.Label(self, image=self.artwork, bg=THEME["bg"], bd=0).pack()
        controls = ttk.Frame(self, style="FocusShell.TFrame")
        controls.pack(fill="x", pady=8)
        PlayerTransportButton(controls, command=lambda: None).pack(side="left")
        ttk.Label(controls, text="0:00 / 32:47", style="Muted.TLabel").pack(
            side="left", padx=12
        )
        variable = tk.IntVar(self, 80)
        self.variables.append(variable)
        PlayerVolumeControl(controls, variable=variable, command=lambda *_: None).pack(
            side="right"
        )
        ttk.Label(controls, text="Volume", style="Muted.TLabel").pack(
            side="right", padx=8
        )
        ttk.Label(
            self,
            text="PREVIEW MOMENTS" if include_artwork else "Ready",
            style="Muted.TLabel",
        ).pack(anchor="w")
