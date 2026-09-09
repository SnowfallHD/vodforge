"""Lossless log typography, independent of log persistence and run state."""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any

from .ui_theme import FONT_UI, THEME
from .ui_widgets import _tinted_ui_icon

_LOG_TOKEN = re.compile(
    r"(^\d{2}:\d{2}:\d{2})|(\[(?:info|download|success|warning|error|debug)\][ \t]*)"
    r"|(^WARNING:[ \t]*|^ERROR:[ \t]*)"
    r"|(^(?=\S)(?!\d{2}:\d{2}:\d{2}|\[(?:info|download|success|warning|error|debug)\]))",
    re.MULTILINE | re.IGNORECASE,
)


def terminal_activity_line(status: str, message: str) -> str:
    """Decorate an explicit run outcome, never infer it from message text."""
    level = {"Completed": "success", "Failed": "error", "Partial": "warning"}.get(
        status
    )
    return f"[{level}] {message}" if level else message


class ActivitySummary(ttk.Frame):
    """Small presentation owner for the existing run status/title bindings."""

    def __init__(
        self,
        parent: tk.Misc,
    ) -> None:
        super().__init__(parent, style="FocusShell.TFrame")
        self._status = tk.StringVar(self, "Ready")
        self._title = tk.StringVar(self, "")
        self._detail = tk.StringVar(self, "")
        self._snapshot: tuple[str, str, str] | None = None
        self.columnconfigure(2, weight=1)
        self._last_status: str | None = None
        self._icon = ttk.Label(self, style="Accent.TLabel")
        self._icon.grid(row=0, column=0, padx=(0, 8))
        self._label = ttk.Label(self, textvariable=self._status, style="Accent.TLabel")
        self._label.grid(row=0, column=1, sticky="w", padx=(0, 12))
        self._title_label = ttk.Label(
            self, textvariable=self._title, style="Muted.TLabel", width=1
        )
        self._title_label.grid(row=0, column=2, sticky="ew")
        self._detail_label = ttk.Label(
            self, textvariable=self._detail, style="Muted.TLabel", width=1
        )
        self._detail_label.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(7, 0))
        self.bind("<Configure>", self._resize, add="+")
        self._refresh()

    def _resize(self, event: Any) -> None:
        self._title_label.configure(wraplength=max(80, event.width - 150))
        self._detail_label.configure(wraplength=max(80, event.width))

    def request(self, *, title: str, status: str, detail: str) -> bool:
        snapshot = (title, status, detail)
        if snapshot == self._snapshot:
            return False
        self._snapshot = snapshot
        self._title.set(title)
        self._status.set(status)
        self._detail.set(detail)
        self._refresh()
        return True

    def apply_theme(self) -> None:
        self._last_status = None
        self._refresh()

    def _refresh(self, *_args: Any) -> None:
        status = self._status.get()
        if status == self._last_status:
            return
        self._last_status = status
        color = (
            THEME["danger"]
            if status == "Failed"
            else THEME["warning"]
            if status in {"Partial", "Stopped", "Skipped"}
            else THEME["accent"]
        )
        self._image = _tinted_ui_icon(
            "check" if status == "Completed" else "circle-dashed",
            size=(18, 18),
            color=color,
        )
        self._icon.configure(image=self._image or "")
        self._label.configure(foreground=color)


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
        self._success_icon = _tinted_ui_icon(
            "check", size=self._icon_size, color=THEME["accent"]
        )
        self._divider.put(THEME["accent"], to=(0, 0, 1, 18))
        for child in self.winfo_children():
            if isinstance(child, tk.Label):
                child.configure(
                    bg=self.cget("bg"),
                    fg=THEME["warning"]
                    if child.cget("text") == "WARNING: "
                    else THEME["danger"],
                )
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
        previous_success = str(self._success_icon)
        self._success_icon = _tinted_ui_icon(
            "check", size=self._icon_size, color=THEME["accent"]
        )
        for name in self.image_names():
            if self.image_cget(name, "image") != str(self._divider):
                icon = (
                    self._success_icon
                    if self.image_cget(name, "image") == previous_success
                    else self._event_icon
                )
                if icon is not None:
                    self.image_configure(name, image=icon)
        self._divider.put(THEME["accent"], to=(0, 0, 1, 18))

    def insert(self, index: Any, chars: str, *args: Any) -> None:
        self._snapshot = None
        if args or index not in {"end", "1.0"}:
            super().insert(index, chars, *args)
            return
        # A right-gravity mark preserves order even when inserting at 1.0.
        self.mark_set("log-insert", "end-1c" if index == "end" else index)
        self.mark_gravity("log-insert", "right")
        indents: dict[str, int] = {}

        def remember_text_start() -> None:
            line = self.index("log-insert").split(".")[0] + ".0"
            width = 0
            font = tkfont.Font(self, font=self.cget("font"))
            for kind, value, position in self.dump(
                line, "log-insert", text=True, image=True
            ):
                if kind == "image":
                    width += int(
                        self.tk.call("image", "width", self.image_cget(value, "image"))
                    )
                    width += 2 * int(self.image_cget(value, "padx"))
                elif "log-hidden" not in self.tag_names(position):
                    width += font.measure(value)
            indents[line] = width

        start = 0
        for match in _LOG_TOKEN.finditer(chars):
            super().insert("log-insert", chars[start : match.start()])
            severity = match[0].strip().strip("[]:").lower()
            if severity in {"warning", "error"}:
                if self.index("log-insert").endswith(".0"):
                    self.image_create(
                        "log-insert", image=self._divider, padx=10, align="center"
                    )
                if self._event_icon is not None:
                    self.image_create(
                        "log-insert", image=self._event_icon, padx=12, align="center"
                    )
                remember_text_start()
                # Preserve the source token in the document, but give every
                # producer spelling the same visible severity label.
                super().insert(
                    "log-insert", match[0], ("log-hidden", f"log-{severity}")
                )
                label = tk.Label(
                    self,
                    text=severity.upper() + ": ",
                    font=self.cget("font"),
                    bg=self.cget("bg"),
                    fg=THEME["warning"] if severity == "warning" else THEME["danger"],
                    bd=0,
                    padx=0,
                    pady=0,
                    highlightthickness=0,
                )
                self.window_create("log-insert", window=label, align="center")
                start = match.end()
                continue
            if match[4] is not None:
                # Live providers emit plain lines, not the timestamped tokens
                # used by older logs. Decorate each actual line once, without
                # inventing timestamps or changing the underlying document.
                if self.index("log-insert").endswith(".0"):
                    self.image_create(
                        "log-insert", image=self._divider, padx=10, align="center"
                    )
                    if self._event_icon is not None:
                        self.image_create(
                            "log-insert",
                            image=self._event_icon,
                            padx=12,
                            align="center",
                        )
                    remember_text_start()
                start = match.end()
                continue
            icon = (
                self._success_icon
                if match[0].strip().lower() == "[success]"
                else self._event_icon
            )
            if (
                match[2]
                and icon is not None
                and match[0].strip().lower()
                in {"[info]", "[download]", "[debug]", "[success]"}
            ):
                # Keep original tokens in the selectable document; shared
                # theme-aware chrome never becomes log or run authority.
                if self.index("log-insert").endswith(".0"):
                    self.image_create(
                        "log-insert", image=self._divider, padx=10, align="center"
                    )
                super().insert("log-insert", match[0], "log-hidden")
                self.image_create(
                    "log-insert",
                    image=icon,
                    padx=12,
                    align="center",
                )
                remember_text_start()
            else:
                tag = "log-time" if match[1] else "log-level"
                super().insert("log-insert", match[0], tag)
                if match[1]:
                    self.image_create(
                        "log-insert", image=self._divider, padx=10, align="center"
                    )
            start = match.end()
        super().insert("log-insert", chars[start:])
        for line, width in indents.items():
            tag = f"log-indent-{width}"
            self.tag_configure(tag, lmargin2=width)
            self.tag_add(tag, line, f"{line} lineend +1c")
        self.mark_unset("log-insert")

    def delete(self, index1: Any, index2: Any = None) -> None:
        self._snapshot = None
        end = index2 if index2 is not None else f"{self.index(index1)} +1c"
        for kind, value, _position in self.dump(index1, end, window=True):
            if kind == "window" and value:
                self.nametowidget(value).destroy()
        super().delete(index1, index2)
