"""Forge-only phase presentation; the complete technical log stays lossless."""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk
from typing import Any

from .activity_ui import ActivityLogText
from .library_state import library_phase_from_status
from .ui_theme import THEME
from .ui_widgets import ToolTip, bind_smooth_vertical_wheel


class ActivityModeSlider(tk.Canvas):
    """Small two-position control, drawn consistently on both desktop platforms."""

    def __init__(self, parent: tk.Misc, command: Any) -> None:
        super().__init__(
            parent,
            width=30,
            height=116,
            bg=THEME["bg"],
            highlightthickness=0,
            takefocus=True,
            cursor="hand2",
        )
        self.command = command
        self.technical = False
        self.bind("<Button-1>", self._pointer)
        self.bind("<B1-Motion>", self._pointer)
        self.bind("<Up>", lambda _e: self._choose(False))
        self.bind("<Down>", lambda _e: self._choose(True))
        self.bind("<space>", lambda _e: self._choose(not self.technical))
        self.bind("<Return>", lambda _e: self._choose(not self.technical))
        self.bind("<FocusIn>", lambda _e: self.apply_theme())
        self.bind("<FocusOut>", lambda _e: self.apply_theme())
        ToolTip(
            self,
            "Top: friendly progress\nBottom: technical details\nClick, drag, or use ↑ / ↓",
        )
        self.apply_theme()

    def _pointer(self, event: tk.Event) -> str:
        self.focus_set()
        return self._choose(event.y >= 58)

    def _choose(self, technical: bool) -> str:
        self.command(technical)
        return "break"

    def apply_theme(self) -> None:
        self.configure(bg=THEME["bg"])
        self.delete("all")
        for cy, technical in ((13, False), (103, True)):
            color = THEME["accent"] if technical == self.technical else THEME["muted"]
            self.create_oval(5, cy - 10, 25, cy + 10, outline=color, width=1.5)
            for x in (11, 19):
                self.create_oval(x - 1, cy - 3, x + 1, cy - 1, fill=color, outline="")
            self.create_arc(
                10,
                cy + (2 if technical else -3),
                20,
                cy + (8 if technical else 5),
                start=0 if technical else 180,
                extent=180,
                style="arc",
                outline=color,
                width=1.5,
            )
        self.create_line(
            15, 35, 15, 81, fill=THEME["surface_2"], width=5, capstyle="round"
        )
        y = 78 if self.technical else 38
        self.create_oval(
            9,
            y - 6,
            21,
            y + 6,
            fill=THEME["text"] if self.focus_get() is self else THEME["accent"],
            outline="",
        )


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
    """Switch one full-height viewport between friendly and technical activity."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, style="FocusShell.TFrame")
        self.columnconfigure(1, weight=1)
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
        self.friendly.grid(row=0, column=1, sticky="nsew")
        self.technical = ActivityLogText(self, **options)
        self.toggle = ActivityModeSlider(self, self.set_technical)
        self.toggle.grid(row=0, column=0, padx=(0, 8))
        bind_smooth_vertical_wheel(self.friendly, mode="pixels")
        bind_smooth_vertical_wheel(self.technical, mode="pixels")

    def toggle_details(self) -> None:
        self.set_technical(not self.expanded)

    def set_technical(self, enabled: bool) -> None:
        if self.expanded == enabled:
            return
        self.expanded = enabled
        if self.expanded:
            self.friendly.grid_remove()
            self.technical.grid(row=0, column=1, sticky="nsew")
            if not self._opened:
                self._opened = True
                self.technical.after_idle(lambda: self.technical.see("end"))
        else:
            self.technical.grid_remove()
            self.friendly.grid(row=0, column=1, sticky="nsew")
        self.toggle.technical = enabled
        self.toggle.apply_theme()

    def observe(self, run_id: str, status: str, message: str = "") -> None:
        label = friendly_phase(status)
        if not run_id or label is None:
            return
        if status in {"Failed", "Partial"} and message:
            label = ("ERROR: " if status == "Failed" else "WARNING: ") + message
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
