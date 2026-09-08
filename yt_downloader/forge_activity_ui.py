"""Forge-only phase presentation; the complete technical log stays lossless."""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk
from typing import Any

from .activity_ui import ActivityLogText
from .library_state import library_phase_from_status
from .ui_theme import THEME
from .ui_widgets import bind_smooth_vertical_wheel


def friendly_phase(status: str) -> str | None:
    """Use the existing worker-status contract, never parse arbitrary log prose."""
    terminal = {
        "Completed": "[success] Download complete",
        "Failed": "ERROR: Download failed. Open Technical details for the cause.",
        "Partial": "WARNING: Some items could not finish. See Technical details.",
        "Stopped": "Download stopped",
        "Skipped": "Download skipped",
    }
    if status in terminal:
        return terminal[status]
    # yt-dlp emits this after EACH audio/video stream, before conversion.
    # It is not the application's finalizing stage.
    if status == "Download finished; finalizing output…":
        return None
    phase = library_phase_from_status(status)
    label = {
        "Preparing": "Getting video information",
        "Downloading": "Downloading media",
        "Transcoding": "Converting media",
        "Validating": "Checking the output",
        "Finalizing": "Finishing the download",
    }.get(phase or "")
    if label is None:
        return None
    item = re.match(r"(?:Video|Batch URL) \d+ of (\d+)", status)
    return f"{item[0]} · {label}" if item and int(item[1]) > 1 else label


class ForgeActivityPanel(ttk.Frame):
    """Own one bounded friendly view and its pinned technical disclosure."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, style="FocusShell.TFrame")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._runs: dict[str, list[str]] = {}
        self._selected = ""
        self._raw = ""
        self.expanded = False
        self._opened = False
        options: dict[str, Any] = {
            "compact": True,
            "height": 3,
            "width": 1,
            "wrap": "word",
            "state": "disabled",
            "bg": THEME["bg"],
            "fg": THEME["muted"],
            "relief": "flat",
            "bd": 0,
            "highlightthickness": 0,
            "padx": 0,
            "takefocus": 0,
        }
        self.friendly = ActivityLogText(self, **options)
        self.friendly.grid(row=0, column=0, sticky="nsew")
        self.technical = ActivityLogText(self, **options)
        self.toggle = ttk.Button(
            self,
            text="▸ Technical details",
            style="FocusQuiet.TButton",
            command=self.toggle_details,
        )
        self.toggle.grid(row=2, column=0, sticky="w", pady=(4, 0))
        bind_smooth_vertical_wheel(self.friendly, mode="pixels")
        bind_smooth_vertical_wheel(self.technical, mode="pixels")

    def toggle_details(self) -> None:
        self.expanded = not self.expanded
        self.rowconfigure(1, weight=2 if self.expanded else 0)
        if self.expanded:
            self.technical.grid(row=1, column=0, sticky="nsew")
            if not self._opened:
                self._opened = True
                self.technical.after_idle(lambda: self.technical.see("end"))
        else:
            self.technical.grid_remove()
        self.toggle.configure(
            text=("▾" if self.expanded else "▸") + " Technical details"
        )

    def observe(self, run_id: str, status: str) -> None:
        label = friendly_phase(status)
        if not run_id or label is None:
            return
        rows = self._runs.setdefault(run_id, [])
        if label not in rows and not (rows and rows[-1].endswith(" · " + label)):
            rows.append(label)
            del rows[:-64]
        # This is a bounded session projection, not a second run-history store.
        if len(self._runs) > 128:
            del self._runs[next(iter(self._runs))]
        if self._selected == run_id:
            self.show(run_id, self._raw)

    def show(self, run_id: str, raw: str) -> None:
        self._selected, self._raw = run_id, raw
        rows = list(self._runs.get(run_id, ()))
        if not rows:
            rows = [
                "Open Technical details for this run’s saved activity."
                if run_id
                else "Your next run’s progress will appear here."
            ]
        if re.search(r"(?im)^(?:\d{2}:\d{2}:\d{2}\s+)?(?:WARNING:|\[warning\])", raw):
            rows.append("WARNING: A warning was reported. See Technical details.")
        if re.search(r"(?im)^(?:\d{2}:\d{2}:\d{2}\s+)?(?:ERROR:|\[error\])", raw):
            rows.append("ERROR: An error was reported. See Technical details.")
        first, last = self.friendly.yview()
        locked = getattr(self.friendly, "_vodforge_user_scroll_locked", False)
        if self.friendly.request("\n".join(rows)):
            if locked or last < 0.995:
                self.friendly.yview_moveto(first)
            else:
                self.friendly.see("end")
