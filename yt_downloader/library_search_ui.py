from __future__ import annotations

import tkinter as tk
from typing import Any

from .ui_theme import FONT_UI, THEME


class LibrarySearchField(tk.Frame):
    """Own one understated Library search field and its focus presentation."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        variable: tk.StringVar,
        width: int = 22,
    ) -> None:
        super().__init__(
            master,
            bg=THEME["surface"],
            bd=0,
            highlightthickness=1,
            highlightbackground=THEME["border"],
            highlightcolor=THEME["accent"],
        )
        self.variable = variable
        self.entry = tk.Entry(
            self,
            textvariable=variable,
            width=width,
            bg=THEME["surface"],
            fg=THEME["text"],
            insertbackground=THEME["text"],
            selectbackground=THEME["accent_dark"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=FONT_UI,
        )
        self.entry.pack(side="left", padx=1, pady=1, ipady=7, ipadx=9)
        self._placeholder = tk.Label(
            self,
            text="⌕  Search library",
            bg=THEME["surface"],
            fg=THEME["muted"],
            bd=0,
            font=FONT_UI,
            cursor="xterm",
        )
        self._placeholder.bind("<Button-1>", self._focus_entry)
        self.entry.bind("<FocusIn>", self._refresh)
        self.entry.bind("<FocusOut>", self._refresh)
        self._variable_trace = variable.trace_add("write", self._refresh)
        self.bind("<Destroy>", self._destroyed, add="+")
        self.after_idle(self._refresh)

    def _focus_entry(self, _event: tk.Event[Any]) -> str:
        self.entry.focus_set()
        return "break"

    def _refresh(self, *_args: object) -> None:
        try:
            focused = self.entry.focus_get() is self.entry
            if focused or self.variable.get():
                self._placeholder.place_forget()
            else:
                self._placeholder.place(x=10, rely=0.5, anchor="w")
            self.configure(
                highlightbackground=(THEME["accent"] if focused else THEME["border"])
            )
        except tk.TclError:
            return

    def _destroyed(self, event: tk.Event[Any]) -> None:
        if event.widget is not self:
            return
        try:
            self.variable.trace_remove("write", self._variable_trace)
        except tk.TclError:
            pass
