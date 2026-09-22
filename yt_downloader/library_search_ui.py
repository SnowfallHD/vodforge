from __future__ import annotations

import tkinter as tk
from collections.abc import Sequence
from typing import Any

from .library_search import LIBRARY_ALL_CATEGORIES
from .ui_chrome import RoundedFieldBorder
from .ui_layout import window_logical_metrics
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
        placeholder: str = "Search library",
        shortcut_hint: str = "",
    ) -> None:
        self._metrics = window_logical_metrics(master)
        super().__init__(
            master,
            bg=THEME["surface"],
            bd=0,
            highlightthickness=self._metrics.px(1),
            highlightbackground=THEME["border"],
            highlightcolor=THEME["border"],
        )
        self._disposed = False
        self.variable = variable
        self._regular_width = max(10, int(width))
        self._compact = False
        self.entry = tk.Entry(
            self,
            textvariable=variable,
            width=max(1, width - 3),
            bg=THEME["surface"],
            fg=THEME["text"],
            insertbackground=THEME["text"],
            selectbackground=THEME["accent_dark"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=self._metrics.font(FONT_UI),
        )
        # External spacing protects the rounded chrome; internal padding expands
        # the opaque native Entry and can paint over the shell's corner stroke.
        self._search_icon = _tinted_ui_icon(
            "search",
            size=(self._metrics.px(16),) * 2,
            color=THEME["muted"],
            widget=self,
        )
        self._icon_label = tk.Label(
            self,
            image=self._search_icon or "",
            text="" if self._search_icon else "⌕",
            bg=THEME["surface"],
            fg=THEME["muted"],
            bd=0,
            cursor="xterm",
            font=self._metrics.font(FONT_UI),
        )
        self._icon_label.pack(
            side="left",
            padx=(self._metrics.px(10), self._metrics.px(6)),
            pady=self._metrics.px(8),
        )
        self._icon_label.bind("<Button-1>", self._focus_entry)
        self.entry.pack(
            side="left", padx=(0, self._metrics.px(10)), pady=self._metrics.px(8)
        )
        if shortcut_hint:
            hint = tk.Label(
                self,
                text=shortcut_hint,
                bg=THEME["surface"],
                fg=THEME["subtle"],
                bd=0,
                font=self._metrics.font(FONT_UI),
                cursor="xterm",
            )
            hint.pack(side="right", padx=(0, self._metrics.px(10)))
            hint.bind("<Button-1>", self._focus_entry)
        self._placeholder_text = placeholder
        self._placeholder = tk.Label(
            self,
            text=placeholder,
            bg=THEME["surface"],
            fg=THEME["muted"],
            bd=0,
            font=self._metrics.font(FONT_UI),
            cursor="xterm",
        )
        self._placeholder.bind("<Button-1>", self._focus_entry)
        self.entry.bind("<FocusIn>", self._refresh)
        self.entry.bind("<FocusOut>", self._refresh)
        self._variable_trace = variable.trace_add("write", self._refresh)
        self.bind("<Destroy>", self._destroyed, add="+")
        self._chrome = RoundedFieldBorder(self)
        self.bind("<Button-1>", self._focus_entry)
        self._chrome.canvas.bind("<Button-1>", self._focus_entry)
        self._initial_refresh = self.after_idle(self._refresh)

    def set_compact(self, compact: bool) -> bool:
        """Apply one width mode without rebuilding the search surface."""

        if self._disposed:
            return False
        value = bool(compact)
        if value == self._compact:
            return False
        self._compact = value
        self.entry.configure(width=max(1, (14 if value else self._regular_width) - 3))
        self._placeholder.configure(
            text="Search\u2026" if value else self._placeholder_text
        )
        return True

    def _focus_entry(self, _event: tk.Event[Any]) -> str:
        if self._disposed:
            return "break"
        self.entry.focus_set()
        return "break"

    def _refresh(self, *_args: object) -> None:
        if self._disposed:
            return
        try:
            focused = self.entry.focus_get() is self.entry
            if focused or self.variable.get():
                self._placeholder.place_forget()
            else:
                self._placeholder.place(in_=self.entry, x=0, rely=0.5, anchor="w")
            background = THEME["focus_surface"] if focused else THEME["surface"]
            self.entry.configure(bg=background)
            for child in self.winfo_children():
                if isinstance(child, tk.Label):
                    child.configure(bg=background)
            self._chrome.request(focused)
        except tk.TclError:
            return

    def _destroyed(self, event: tk.Event[Any]) -> None:
        if event.widget is not self or self._disposed:
            return
        self._disposed = True
        try:
            self.after_cancel(self._initial_refresh)
        except tk.TclError:
            pass
        try:
            self.variable.trace_remove("write", self._variable_trace)
        except tk.TclError:
            pass
        self.__dict__.pop("variable", None)
        self._search_icon = None

    def apply_theme(self) -> None:
        if self._disposed:
            return
        self._search_icon = _tinted_ui_icon(
            "search",
            size=(self._metrics.px(16),) * 2,
            color=THEME["muted"],
            widget=self,
        )
        self._icon_label.configure(
            image=self._search_icon or "", text="" if self._search_icon else "⌕"
        )
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
