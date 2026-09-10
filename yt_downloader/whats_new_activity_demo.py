"""Offline presentation loop using production widgets and recorded example lines."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .forge_activity_ui import ForgeActivityPanel


class ActivityDemo(ttk.Frame):
    """Own exactly one cancellable timer; never run download or telemetry services."""

    def __init__(self, parent: tk.Misc, *, interval_ms: int = 500) -> None:
        super().__init__(parent, style="FocusShell.TFrame")
        self.panel = ForgeActivityPanel(self)
        self.panel.pack(fill="both", expand=True)
        self.interval_ms = interval_ms
        self.preferred_width = 470
        self.preferred_height = 180
        self.timer: str | None = None
        self.step = 0
        self.cycle = 0
        self.bind("<Destroy>", self._destroy, add="+")
        self._tick()

    def _cancel(self) -> None:
        if self.timer is not None:
            self.after_cancel(self.timer)
            self.timer = None

    def _destroy(self, event: tk.Event) -> None:
        if event.widget is self:
            self._cancel()

    def _tick(self) -> None:
        self.timer = None
        phases = (
            "Video 1 of 1 — analyzing source formats",
            "Video 1 of 1 — downloading",
            "Video 1 of 1 — transcoding",
            "Video 1 of 1 — validating output",
            "Completed",
        )
        lines = (
            "Video 1 of 1: selected format 270+251",
            "Video 1 of 1: Auto CBR target 6000 kbps video + 192 kbps audio.",
            "Video 1 of 1: downloading",
            "Video 1 of 1: FFmpeg command started (1/1) using CPU libx264",
        )
        if self.step == 0:
            self.cycle += 1
            self.panel.set_technical(False)
            self.panel.technical.request("")
            self.panel.show(str(self.cycle), "")
        if self.step < 5:
            self.panel.observe(str(self.cycle), phases[self.step])
        elif self.step == 6:
            self.panel.technical.request(lines[0])
            self.panel.set_technical(True)
        elif 7 <= self.step <= 9:
            self.panel.technical.request("\n".join(lines[: self.step - 5]))
            self.panel.technical.see("end")
        elif self.step == 12:
            self.panel.set_technical(False)
        self.step = (self.step + 1) % 15
        self.timer = self.after(self.interval_ms, self._tick)
