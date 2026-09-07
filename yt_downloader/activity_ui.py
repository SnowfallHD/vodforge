"""Lossless log typography, independent of log persistence and run state."""

from __future__ import annotations

import re
import tkinter as tk
from typing import Any

from .ui_theme import FONT_UI, THEME
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
            font=FONT_UI,
            spacing1=3 if compact else 8,
            spacing3=4 if compact else 10,
        )
        super().__init__(parent, **kwargs)
        self.tag_configure("log-time", foreground=THEME["muted"])
        self.tag_configure("log-level", foreground=THEME["accent"])
        self.tag_configure("log-warning", foreground=THEME["warning"])
        self.tag_configure("log-error", foreground=THEME["danger"])
        self.tag_configure("log-hidden", elide=True)
        self._icon_size = (16, 16)
        self._event_icon = _tinted_ui_icon(
            "circle-dashed", size=self._icon_size, color=THEME["accent"]
        )
        self._divider = tk.PhotoImage(master=self, width=1, height=18)
        self._divider.put(THEME["accent"], to=(0, 0, 1, 18))
        self._snapshot: str | None = None
        self._constrained: bool | None = None

    def request_density(self, *, constrained: bool) -> None:
        """The surface owns typography even when its host becomes compact."""
        if self._constrained == constrained:
            return
        self._constrained = constrained
        self.configure(
            font=(FONT_UI[0], 9) if constrained else FONT_UI,
            pady=0 if constrained else 4,
        )

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
        self.tag_configure("log-warning", foreground=THEME["warning"])
        self.tag_configure("log-error", foreground=THEME["danger"])
        self._event_icon = _tinted_ui_icon(
            "circle-dashed", size=self._icon_size, color=THEME["accent"]
        )
        for name in self.image_names():
            if self.image_cget(name, "image") != str(self._divider):
                self.image_configure(name, image=self._event_icon)
        self._divider.put(THEME["accent"], to=(0, 0, 1, 18))

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
                # Keep original tokens in the selectable document; shared
                # theme-aware chrome never becomes log or run authority.
                super().insert("log-insert", match[0], "log-hidden")
                self.image_create(
                    "log-insert", image=self._event_icon, padx=12, align="center"
                )
            else:
                tag = "log-time" if match[1] else "log-level"
                if match[0].strip().lower() == "[warning]":
                    tag = "log-warning"
                elif match[0].strip().lower() == "[error]":
                    tag = "log-error"
                super().insert("log-insert", match[0], tag)
                if match[1]:
                    self.image_create(
                        "log-insert", image=self._divider, padx=10, align="center"
                    )
            start = match.end()
        super().insert("log-insert", chars[start:])
        self.mark_unset("log-insert")

    def delete(self, index1: Any, index2: Any = None) -> None:
        self._snapshot = None
        super().delete(index1, index2)
