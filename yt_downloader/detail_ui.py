"""Read-only technical facts: lossless snapshots, one local render owner.

This layer never invents, normalizes, or drops source/output facts. Canonical
formatters still supply the complete text; only its typography is projected.
"""

from __future__ import annotations

import re
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from .ui_layout import centered_toplevel_geometry
from .ui_theme import FONT_UI, FONT_UI_SMALL, THEME
from .ui_widgets import (
    ActionDialogSurface,
    SleekScrollbar,
    bind_smooth_vertical_wheel,
    reveal_toplevel,
)


@dataclass(frozen=True, slots=True)
class DetailLine:
    raw: str
    label: str = ""
    value: str = ""


def detail_lines(text: str) -> tuple[DetailLine, ...]:
    result = []
    for raw in text.splitlines():
        # Match the two existing formatter contracts, never media identity.
        match = re.match(r"^([^:\t]+?):[ \t]+(.*)$", raw)
        if match is None:
            match = re.match(r"^(.+?)(?:\t| {2,})(.*)$", raw)
        result.append(DetailLine(raw, match[1], match[2]) if match else DetailLine(raw))
    return tuple(result)


class FactsText(tk.Text):
    """Selectable label/value document; identical snapshots are a cheap no-op."""

    def __init__(self, parent: tk.Misc, **kwargs: Any) -> None:
        options: dict[str, Any] = {
            "bg": THEME["bg"],
            "fg": THEME["text"],
            "font": FONT_UI_SMALL,
            "relief": "flat",
            "bd": 0,
            "highlightthickness": 0,
            "padx": 0,
            "pady": 4,
            "wrap": "word",
            "state": "disabled",
            "width": 1,
            "spacing1": 2,
            "spacing3": 3,
        }
        options.update(kwargs)
        super().__init__(parent, **options)
        self._snapshot: str | None = None
        self._label_width = 120
        self._layout_width = -1
        self.tag_configure("fact-label", foreground=THEME["muted"])
        self.bind("<Configure>", self._resize, add="+")
        bind_smooth_vertical_wheel(self, mode="pixels")

    @property
    def raw_snapshot(self) -> str:
        return self._snapshot or ""

    def apply_theme(self) -> None:
        self.tag_configure("fact-label", foreground=THEME["muted"])
        self.tag_configure("section", foreground=THEME["accent"])

    def request(self, text: str) -> bool:
        if self._snapshot == text:
            return False
        lines = detail_lines(text)
        font = tkfont.Font(root=self, font=self.cget("font"))
        self._label_width = max(
            (font.measure(line.label) + 18 for line in lines if line.label), default=120
        )
        self.configure(state="normal")
        self.delete("1.0", "end")
        for index, line in enumerate(lines):
            if index:
                self.insert("end", "\n")
            if line.label:
                self.insert("end", line.label, ("fact-row", "fact-label"))
                self.insert("end", "\t" + line.value, "fact-row")
            else:
                self.insert("end", line.raw)
        self.configure(state="disabled")
        self._snapshot = text
        self._layout_width = -1
        self._resize()
        return True

    def _resize(self, _event: Any = None) -> None:
        width = max(80, self.winfo_width())
        stop = min(self._label_width, max(80, int(width * 0.46)))
        if stop == self._layout_width:
            return
        self.configure(tabs=(stop, "left"), tabstyle="wordprocessor")
        self.tag_configure("fact-row", lmargin2=stop)
        self._layout_width = stop


class OutputDetailsDialog:
    """Document-only overflow is allowed; dismissal remains a protected sibling."""

    def __init__(
        self,
        parent: tk.Tk | tk.Toplevel,
        *,
        title: str = "",
        sections: tuple[tuple[str, str], ...],
    ) -> None:
        popup = tk.Toplevel(parent)
        popup.withdraw()
        popup.title("VODForge Output details")
        popup.transient(parent)
        popup.configure(bg=THEME["bg"])
        popup.minsize(460, 320)
        self.popup = popup
        self.sections = sections
        surface = ActionDialogSurface(popup)
        surface.body.rowconfigure(2, weight=1)
        ttk.Label(surface.body, text="Output details", style="FocusTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        if title:
            ttk.Label(
                surface.body, text=title, style="Muted.TLabel", wraplength=490
            ).grid(row=1, column=0, sticky="w", pady=(6, 12))
        document = FactsText(surface.body, height=16, font=FONT_UI)
        document.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        document.request(
            "\n\n".join(f"{heading}\n{content}" for heading, content in sections)
        )
        document.tag_configure(
            "section",
            foreground=THEME["accent"],
            font=(*FONT_UI, "bold"),
            spacing1=12,
            spacing3=8,
        )
        line = 1
        for heading, content in sections:
            document.tag_add("section", f"{line}.0", f"{line}.end")
            line += (heading + "\n" + content).count("\n") + 2
        scrollbar = SleekScrollbar(surface.body, command=document.yview)
        scrollbar.grid(row=2, column=1, sticky="ns", pady=(12, 0))
        document.configure(yscrollcommand=scrollbar.set)
        self.documents = [document]
        ttk.Button(
            surface.footer, text="Done", style="Accent.TButton", command=popup.destroy
        ).pack(side="right")
        popup.bind("<Escape>", lambda _event: popup.destroy())
        popup.update_idletasks()
        reveal_toplevel(popup, centered_toplevel_geometry(parent, 620, 700))
