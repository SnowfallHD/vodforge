"""Read-only technical facts: lossless snapshots, one local render owner.

This layer never invents, normalizes, or drops source/output facts. Canonical
formatters still supply the complete text; only its typography is projected.
"""

from __future__ import annotations

import re
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from .ui_button_contract import ProductButton
from .ui_layout import (
    bounded_window_size,
    centered_toplevel_geometry,
    window_logical_metrics,
)
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
        self._metrics = window_logical_metrics(parent)
        px = self._metrics.px
        options: dict[str, Any] = {
            "bg": THEME["bg"],
            "fg": THEME["text"],
            "font": self._metrics.font(FONT_UI_SMALL),
            "relief": "flat",
            "bd": 0,
            "highlightthickness": 0,
            "padx": 0,
            "pady": px(4),
            "wrap": "word",
            "state": "disabled",
            "width": 1,
            "spacing1": px(2),
            "spacing3": px(3),
        }
        self._fit_content = bool(kwargs.pop("fit_content", False))
        options.update(kwargs)
        super().__init__(parent, **options)
        self._snapshot: str | None = None
        self._lines: tuple[DetailLine, ...] = ()
        self._row_offsets: list[int] = []
        self._layout: tuple[int, tuple[bool, ...]] | None = None
        self.tag_configure("fact-label", foreground=THEME["muted"])
        self.tag_configure("block-label", spacing1=px(10), spacing3=px(4))
        self.tag_configure("block-value", spacing1=0, spacing3=px(10), lmargin2=0)
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
        self._lines = detail_lines(text)
        self._snapshot = text
        self._layout = None
        self._resize(preserve=False)
        return True

    def line_start(self, row: int) -> str:
        """Address a source line even when a long fact occupies two text lines."""
        return f"1.0 + {self._row_offsets[row]} chars"

    def _resize(self, _event: Any = None, *, preserve: bool = True) -> None:
        # Hidden, not-yet-laid-out documents use a readable initial width.
        width = self.winfo_width()
        px = self._metrics.px
        width = px(600) if width <= 1 else max(px(80), width)
        width -= 2 * int(self.cget("padx")) + px(6)

        def measure(text: str) -> int:
            return int(self.tk.call("font", "measure", self.cget("font"), text))

        label_limit = max(px(80), min(px(220), int(width * 0.64)))
        labels = [measure(line.label) + px(18) for line in self._lines]
        stop = max((size for size in labels if size <= label_limit), default=px(80))
        blocks = tuple(
            bool(line.label)
            and (
                labels[index] > label_limit
                or (
                    ("\\\\" in line.value or "/" in line.value)
                    and measure(line.value) > max(px(80), width - stop)
                )
                or measure(line.value) > max(px(80), width - stop) * 1.7
            )
            for index, line in enumerate(self._lines)
        )
        layout = (stop, blocks)
        if layout == self._layout:
            self._fit_height()
            return
        # A tab and a newline each occupy one character. Swapping that separator
        # keeps all character offsets stable, including selections and headings.
        selections = (
            tuple(
                int((self.count("1.0", index, "chars") or (0,))[0])
                for index in self.tag_ranges("sel")
            )
            if preserve
            else ()
        )
        sections = (
            tuple(
                int((self.count("1.0", index, "chars") or (0,))[0])
                for index in self.tag_ranges("section")
            )
            if preserve
            else ()
        )
        top = (
            int((self.count("1.0", self.index("@0,0"), "chars") or (0,))[0])
            if preserve
            else 0
        )
        self.configure(state="normal", tabs=(stop, "left"), tabstyle="wordprocessor")
        self.delete("1.0", "end")
        self._row_offsets = []
        offset = 0
        for index, (line, block) in enumerate(zip(self._lines, blocks, strict=True)):
            if index:
                self.insert("end", "\n")
            offset = int((self.count("1.0", "end-1c", "chars") or (0,))[0])
            self._row_offsets.append(offset)
            if line.label:
                self.insert(
                    "end",
                    line.label,
                    ("fact-label", "block-label" if block else "fact-row"),
                )
                self.insert(
                    "end",
                    ("\n" if block else "\t") + line.value,
                    "block-value" if block else "fact-row",
                )
            else:
                self.insert("end", line.raw)
        self.tag_configure("fact-row", lmargin2=stop)
        self.tag_configure("block-value", lmargin1=stop, lmargin2=stop)
        for tag, positions in (("sel", selections), ("section", sections)):
            for start, end in zip(positions[::2], positions[1::2], strict=True):
                self.tag_add(tag, f"1.0 + {start} chars", f"1.0 + {end} chars")
        self.configure(state="disabled")
        self.yview(f"1.0 + {top} chars")
        self._layout = layout
        self._fit_height()

    def _fit_height(self) -> None:
        if self._fit_content:
            logical = int(self.index("end-1c").split(".")[0])
            displayed = (
                int((self.count("1.0", "end-1c", "displaylines") or (0,))[0]) + 1
            )
            pixels = int((self.count("1.0", "end", "ypixels") or (0,))[0])
            line_height = max(
                1, int(self.tk.call("font", "metrics", self.cget("font"), "-linespace"))
            )
            height = min(
                16,
                max(1, logical, displayed, (pixels + line_height - 1) // line_height),
            )
            if int(self.cget("height")) != height:
                self.configure(height=height)


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
        metrics = window_logical_metrics(popup)
        px = metrics.px
        limit = bounded_window_size(
            popup.winfo_screenwidth(), popup.winfo_screenheight()
        )
        popup.minsize(min(px(460), limit[0]), min(px(320), limit[1]))
        self.popup = popup
        self.sections = sections
        surface = ActionDialogSurface(popup)
        surface.body.rowconfigure(2, weight=1)
        ttk.Label(
            surface.body,
            text="Output details",
            style="FocusTitle.TLabel",
            font=metrics.font((FONT_UI[0], 18, "bold")),
        ).grid(row=0, column=0, sticky="w")
        if title:
            title_label = ttk.Label(
                surface.body,
                text=title,
                style="Muted.TLabel",
                wraplength=px(490),
                font=metrics.font(FONT_UI_SMALL),
            )
            title_label.grid(row=1, column=0, sticky="ew", pady=(px(6), px(12)))
            title_label.bind(
                "<Configure>",
                lambda event: title_label.configure(
                    wraplength=max(1, event.width - px(2))
                ),
                add="+",
            )
        document = FactsText(surface.body, height=16, font=metrics.font(FONT_UI))
        document.grid(row=2, column=0, sticky="nsew", pady=(px(12), 0))
        document.request(
            "\n\n".join(f"{heading}\n{content}" for heading, content in sections)
        )
        document.tag_configure(
            "section",
            foreground=THEME["accent"],
            font=metrics.font((*FONT_UI, "bold")),
            spacing1=px(12),
            spacing3=px(8),
        )
        line = 0
        for heading, content in sections:
            start = document.line_start(line)
            document.tag_add("section", start, f"{start} lineend")
            line += (heading + "\n" + content).count("\n") + 2
        scrollbar = SleekScrollbar(surface.body, command=document.yview)
        scrollbar.grid(row=2, column=1, sticky="ns", pady=(px(12), 0))
        document.configure(yscrollcommand=scrollbar.set)
        self.documents = [document]
        ProductButton(
            surface.footer, text="Done", style="Accent.TButton", command=popup.destroy
        ).pack(side="right")
        popup.bind("<Escape>", lambda _event: popup.destroy())
        popup.update_idletasks()
        reveal_toplevel(
            popup, centered_toplevel_geometry(parent, 620, 700, target=popup)
        )
