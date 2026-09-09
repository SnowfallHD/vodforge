"""Lifetime of an app-contained choice surface, independent of focus-taking clicks."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from typing import Any


class ChoicePopover(tk.Frame):
    """A child surface cannot outlive or float above its native owner window."""

    def __init__(
        self, anchor: tk.Widget, close: Callable[[], None], **options: Any
    ) -> None:
        self._anchor = anchor
        self.owner = anchor.winfo_toplevel()
        self._interpreter_root: tk.Misc = self.owner
        while self._interpreter_root.master is not None:
            self._interpreter_root = self._interpreter_root.master
        self.close = close
        self._tag = f"choice-popover-{id(self)}"
        self._tagged: list[tk.Misc] = []
        self._bindings: list[tuple[str, str]] = []
        self._pending: str | None = None
        self._click_binding: str | None = None
        super().__init__(self.owner, bd=0, highlightthickness=0, **options)

    def watch(self) -> None:
        def visit(widget: tk.Misc) -> None:
            if widget is self or widget.winfo_toplevel() is not self.owner:
                return
            widget.bindtags((self._tag, *widget.bindtags()))
            self._tagged.append(widget)
            for child in widget.winfo_children():
                visit(child)

        visit(self.owner)
        self._click_binding = self.owner.bind_class(
            self._tag, "<ButtonPress>", self._outside
        )
        for sequence, callback in (
            ("<FocusOut>", self._focus_out),
            ("<Unmap>", self._unmapped),
            ("<Configure>", self._owner_changed),
        ):
            identifier = self.owner.bind(sequence, callback, add="+")
            self._bindings.append((sequence, identifier))

    def _outside(self, event: tk.Event) -> None:
        # This bindtag runs before a clicked control can return 'break'. Leave
        # the click intact so buttons, tabs and other fields still work.
        if event.widget is not self._anchor and not str(event.widget).startswith(
            str(self._anchor) + "."
        ):
            self.close()

    def _focus_out(self, _event: tk.Event) -> None:
        if self._pending is None:
            self._pending = self.after_idle(self._check_focus)

    def _check_focus(self) -> None:
        self._pending = None
        focused = self.focus_get()
        if focused is None or not str(focused).startswith(str(self) + "."):
            self.close()

    def _unmapped(self, _event: tk.Event) -> None:
        if not self._anchor.winfo_ismapped():
            self.close()

    def _owner_changed(self, event: tk.Event) -> None:
        if event.widget is self.owner:
            self.close()

    def destroy(self) -> None:
        if self._pending is not None:
            self.after_cancel(self._pending)
            self._pending = None
        for widget in self._tagged:
            if widget.winfo_exists():
                widget.bindtags(
                    tuple(tag for tag in widget.bindtags() if tag != self._tag)
                )
        self._tagged.clear()
        self.owner.unbind_class(self._tag, "<ButtonPress>")
        # Tk registers class callbacks on the interpreter root, even when
        # the owning surface is a Settings Toplevel.
        if self._click_binding:
            self._interpreter_root.deletecommand(self._click_binding)
            self._click_binding = None
        for sequence, identifier in self._bindings:
            self.owner.unbind(sequence, identifier)
        self._bindings.clear()
        super().destroy()
