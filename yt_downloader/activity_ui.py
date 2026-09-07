"""Lossless log typography, independent of log persistence and run state."""

from __future__ import annotations

import re
import tkinter as tk
from typing import Any

from .ui_theme import FONT_MONO, FONT_UI, THEME
from .ui_widgets import _tinted_ui_icon

_LOG_TOKEN = re.compile(
    r"(^\d{2}:\d{2}:\d{2})|(\[(?:info|download|warning|error|debug)\][ \t]*)",
    re.MULTILINE | re.IGNORECASE,
)


class ActivityLogText(tk.Text):
    """Decorate real log tokens without rewriting or dropping a character."""

    def __init__(
        self, parent: tk.Misc, *, compact: bool = False, **kwargs: Any
    ) -> None:
        kwargs.update(
            font=FONT_MONO if compact else FONT_UI,
            spacing1=0 if compact else 6,
            spacing3=0 if compact else 8,
        )
        super().__init__(parent, **kwargs)
        self.tag_configure("log-time", foreground=THEME["muted"])
        self.tag_configure("log-level", foreground=THEME["accent"])
        self.tag_configure("log-hidden", elide=True)
        self._event_icon = _tinted_ui_icon("activity", size=(12, 12), color="#a0a4af")
        self._snapshot: str | None = None

    def request(self, text: str) -> bool:
        if self._snapshot == text:
            return False
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.insert("end", text)
        self.configure(state="disabled")
        self._snapshot = text
        return True

    def apply_theme(self) -> None:
        self.tag_configure("log-time", foreground=THEME["muted"])
        self.tag_configure("log-level", foreground=THEME["accent"])

    def insert(self, index: Any, chars: str, *args: Any) -> None:
        self._snapshot = None
        if args or index not in {"end", "1.0"}:
            super().insert(index, chars, *args)
            return
        # A right-gravity mark preserves order even when inserting at 1.0.
        self.mark_set("log-insert", index)
        self.mark_gravity("log-insert", "right")
        start = 0
        for match in _LOG_TOKEN.finditer(chars):
            super().insert("log-insert", chars[start : match.start()])
            if (
                match[2]
                and self._event_icon
                and match[0].strip().lower() in {"[info]", "[download]", "[debug]"}
            ):
                # Keep original tokens in the selectable document; one shared
                # neutral glyph replaces their variable-width visual chrome.
                super().insert("log-insert", match[0], "log-hidden")
                self.image_create(
                    "log-insert", image=self._event_icon, padx=4, align="center"
                )
            else:
                super().insert(
                    "log-insert", match[0], "log-time" if match[1] else "log-level"
                )
            start = match.end()
        super().insert("log-insert", chars[start:])
        self.mark_unset("log-insert")

    def delete(self, index1: Any, index2: Any = None) -> None:
        self._snapshot = None
        super().delete(index1, index2)
