from __future__ import annotations

import tkinter as tk
from collections.abc import Sequence
from typing import Any

from .library_search import LIBRARY_ALL_CATEGORIES
from .ui_chrome import RoundedFieldBorder
from .ui_theme import FONT_UI, THEME
from .ui_widgets import ChoiceDropdown, _tinted_ui_icon


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
        self._regular_width = max(10, int(width))
        self._compact = False
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
        self._search_icon = _tinted_ui_icon(
            "search", size=(16, 16), color=THEME["muted"]
        )
        self._placeholder = tk.Label(
            self,
            text="  Search library",
            image=self._search_icon or "",
            compound="left",
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
        self._chrome = RoundedFieldBorder(self)
        self.after_idle(self._refresh)

    def set_compact(self, compact: bool) -> bool:
        """Apply one width mode without rebuilding the search surface."""

        value = bool(compact)
        if value == self._compact:
            return False
        self._compact = value
        self.entry.configure(width=(14 if value else self._regular_width))
        return True

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
            self._chrome.request(focused)
        except tk.TclError:
            return

    def _destroyed(self, event: tk.Event[Any]) -> None:
        if event.widget is not self:
            return
        try:
            self.variable.trace_remove("write", self._variable_trace)
        except tk.TclError:
            pass

    def apply_theme(self) -> None:
        self._search_icon = _tinted_ui_icon(
            "search", size=(16, 16), color=THEME["muted"]
        )
        self._placeholder.configure(image=self._search_icon or "")
        self._refresh()


class LibraryCategoryFilter(ChoiceDropdown):
    """Own the category-filter choices derived from immutable Library rows."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        variable: tk.StringVar,
        width: int = 17,
    ) -> None:
        self.variable = variable
        self._categories: tuple[str, ...] = ()
        self._regular_width = max(10, int(width))
        self._compact = False
        variable.set(variable.get().strip() or LIBRARY_ALL_CATEGORIES)
        super().__init__(
            master,
            textvariable=variable,
            values=(LIBRARY_ALL_CATEGORIES,),
            state="readonly",
            width=width,
        )

    def set_compact(self, compact: bool) -> bool:
        """Apply one width mode without rebuilding the filter surface."""

        value = bool(compact)
        if value == self._compact:
            return False
        self._compact = value
        self.configure(width=(12 if value else self._regular_width))
        return True

    def replace_categories(self, categories: Sequence[str]) -> bool:
        """Atomically replace choices and no-op when the snapshot is unchanged."""

        snapshot = tuple(
            sorted(
                {str(value).strip() for value in categories if str(value).strip()},
                key=str.casefold,
            )
        )
        if snapshot == self._categories:
            return False
        self._categories = snapshot
        values = (LIBRARY_ALL_CATEGORIES, *snapshot)
        self.configure(values=values)
        if self.variable.get() not in values:
            self.variable.set(LIBRARY_ALL_CATEGORIES)
        return True
