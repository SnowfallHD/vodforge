"""One native context-menu session per window, with surface-owned commands."""

from __future__ import annotations

import tkinter as tk
from typing import Any

from .ui_theme import THEME


class ContextMenu(tk.Menu):
    """Retain queued platform callbacks only until replacement or owner hiding."""

    def __init__(self, master: tk.Misc, **options: Any) -> None:
        self._retired = False
        self._anchor: tk.Misc | None = None
        self._context_window: tk.Misc | None = None
        self._owner_binding: str | None = None
        options.update(
            bg=THEME["surface"],
            fg=THEME["text"],
            activebackground=THEME["accent_surface"],
            activeforeground=THEME["text"],
            disabledforeground=THEME["subtle"],
            relief="flat",
            borderwidth=1,
        )
        super().__init__(master, **options)
        if isinstance(master, ContextMenu):
            return  # Cascades share their parent menu's lifetime.
        self._anchor = master
        window = master.winfo_toplevel()
        previous = window.__dict__.get("_vodforge_context_menu")
        if previous is not None:
            previous.destroy()
        self._context_window = window
        window.__dict__["_vodforge_context_menu"] = self
        self._owner_binding = master.bind("<Unmap>", self._owner_hidden, add="+")

    def apply_theme(self) -> None:
        self.configure(
            bg=THEME["surface"],
            fg=THEME["text"],
            activebackground=THEME["accent_surface"],
            activeforeground=THEME["text"],
            disabledforeground=THEME["subtle"],
        )

    def _owner_hidden(self, event: tk.Event[Any]) -> None:
        if event.widget is self._anchor:
            self.destroy()

    def add(self, itemType: str, cnf: dict[str, Any] | None = None, **kw: Any) -> None:
        options = {**(cnf or {}), **kw}
        command = options.get("command")
        if callable(command):

            def invoke() -> Any:
                if not self._retired:
                    return command()
                return None

            options["command"] = invoke
        super().add(itemType, **options)

    def unpost(self) -> None:
        if not self._retired:
            super().unpost()

    def grab_release(self) -> None:
        if not self._retired:
            super().grab_release()

    def destroy(self) -> None:
        if self._retired:
            return
        self._retired = True
        if (
            self._context_window is not None
            and self._context_window.__dict__.get("_vodforge_context_menu") is self
        ):
            self._context_window.__dict__.pop("_vodforge_context_menu", None)
        if self._anchor is not None and self._owner_binding is not None:
            if self._anchor.winfo_exists():
                self._anchor.unbind("<Unmap>", self._owner_binding)
            self._owner_binding = None
        try:
            super().unpost()
        except tk.TclError:
            pass
        super().destroy()
