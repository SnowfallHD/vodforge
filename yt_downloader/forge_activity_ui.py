"""Forge-only phase presentation; the complete technical log stays lossless."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from .activity_ui import ActivityLogText
from .forge_activity import ForgeActivityProjection, friendly_phase
from .ui_layout import window_logical_metrics
from .ui_theme import THEME
from .ui_widgets import ToolTip, bind_smooth_vertical_wheel

__all__ = ["ActivityModeSlider", "ForgeActivityPanel", "friendly_phase"]


class ActivityModeSlider(tk.Canvas):
    """Small two-position control, drawn consistently on both desktop platforms."""

    def __init__(self, parent: tk.Misc, command: Any) -> None:
        self._metrics = window_logical_metrics(parent)
        super().__init__(
            parent,
            width=self._metrics.px(30),
            height=self._metrics.px(116),
            bg=THEME["bg"],
            highlightthickness=0,
            takefocus=True,
            cursor="hand2",
        )
        self.command = command
        self.technical = False
        self._pointer_command: Any = None
        self.bind("<Button-1>", self._begin_pointer)
        self.bind("<B1-Motion>", self._pointer)
        self.bind("<ButtonRelease-1>", self._end_pointer)
        self.bind("<Unmap>", self._end_pointer)
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

    def _begin_pointer(self, event: tk.Event) -> str:
        self._pointer_command = self.command
        return self._pointer(event)

    def _end_pointer(self, _event: tk.Event) -> None:
        self._pointer_command = None

    def _pointer(self, event: tk.Event) -> str:
        if self._pointer_command is not self.command or not self.winfo_ismapped():
            self._pointer_command = None
            return "break"
        self.focus_set()
        return self._choose(event.y >= self._metrics.px(58))

    def _choose(self, technical: bool) -> str:
        self.command(technical)
        return "break"

    def apply_theme(self) -> None:
        self.configure(bg=THEME["bg"])
        self.delete("all")
        for cy, technical in ((13, False), (103, True)):
            color = THEME["accent"] if technical == self.technical else THEME["muted"]
            self.create_oval(
                5, cy - 10, 25, cy + 10, outline=color, width=1.5 * self._metrics.scale
            )
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
                width=1.5 * self._metrics.scale,
            )
        self.create_line(
            15,
            35,
            15,
            81,
            fill=THEME["surface_2"],
            width=self._metrics.px(5),
            capstyle="round",
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
        self.scale("all", 0, 0, self._metrics.scale, self._metrics.scale)


class ForgeActivityPanel(ttk.Frame):
    """Switch one full-height viewport between friendly and technical activity."""

    def __init__(self, parent: tk.Misc, *, on_technical: Any = None) -> None:
        super().__init__(parent, style="FocusShell.TFrame")
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._projection = ForgeActivityProjection()
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
        self.friendly.configure(height=2)
        self.friendly.request("Your next run’s progress will appear here.")
        self.technical = ActivityLogText(self, **options)
        self._on_technical = on_technical or (lambda: None)
        self.toggle = ActivityModeSlider(self, self.set_technical)
        self.toggle.grid(row=0, column=0, padx=(0, window_logical_metrics(self).px(8)))
        bind_smooth_vertical_wheel(self.friendly, mode="pixels")
        bind_smooth_vertical_wheel(self.technical, mode="pixels")

    def toggle_details(self) -> None:
        self.set_technical(not self.expanded)

    def set_technical(self, enabled: bool) -> None:
        if self.expanded == enabled:
            return
        self.expanded = enabled
        if self.expanded:
            self._on_technical()
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
        changed = self._projection.observe(run_id, status, message)
        if changed and self._selected == run_id:
            self.show(run_id, self._raw)

    def show(self, run_id: str, raw: str) -> None:
        self._selected, self._raw = run_id, raw
        text = self._projection.friendly(run_id, raw)
        first, last = self.friendly.yview()
        locked = getattr(self.friendly, "_vodforge_user_scroll_locked", False)
        self.friendly.configure(height=min(8, max(2, len(text.splitlines()))))
        if self.friendly.request(text):
            if locked or last < 0.995:
                self.friendly.yview_moveto(first)
            else:
                self.friendly.see("end")
