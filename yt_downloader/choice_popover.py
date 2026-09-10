"""Lifetime of an app-contained choice surface, independent of focus-taking clicks."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from typing import Any


class ChoicePopover(tk.Frame):
    """A child surface cannot outlive or float above its native owner window."""

    def __init__(
        self,
        anchor: tk.Widget,
        close: Callable[[], None],
        *,
        gap: int = 4,
        align_right: bool = False,
        **options: Any,
    ) -> None:
        self._anchor = anchor
        self.gap, self.align_right = gap, align_right
        self.owner = anchor.winfo_toplevel()
        self._interpreter_root: tk.Misc = self.owner
        while self._interpreter_root.master is not None:
            self._interpreter_root = self._interpreter_root.master
        self.close = close
        self._tag = f"choice-popover-{id(self)}"
        self._tagged: list[tk.Misc] = []
        self._bindings: list[tuple[str, str]] = []
        self._pending: str | None = None
        self._tracking: str | None = None
        self._placement: tuple[int, int, int, int] | None = None
        self._click_binding: str | None = None
        # A modal frame's grab excludes sibling popovers from pointer delivery.
        # Keep the menu inside that grab subtree without stealing the grab.
        host = self.owner
        grabbed = anchor.grab_current()
        if grabbed is not None and (
            anchor is grabbed or str(anchor).startswith(str(grabbed) + ".")
        ):
            host = grabbed
        super().__init__(host, bd=0, highlightthickness=0, **options)

    def reposition(self) -> bool:
        """Keep the complete menu attached within the anchor's visible viewport."""
        anchor, host = self._anchor, self.master
        if not anchor.winfo_ismapped():
            self.close()
            return False
        left, top = host.winfo_rootx(), host.winfo_rooty()
        right, bottom = left + host.winfo_width(), top + host.winfo_height()
        ancestor = anchor.master
        while ancestor is not None and ancestor is not host:
            if isinstance(ancestor, tk.Canvas):
                left = max(left, ancestor.winfo_rootx())
                top = max(top, ancestor.winfo_rooty())
                right = min(right, ancestor.winfo_rootx() + ancestor.winfo_width())
                bottom = min(bottom, ancestor.winfo_rooty() + ancestor.winfo_height())
            ancestor = ancestor.master
        ax, ay = anchor.winfo_rootx(), anchor.winfo_rooty()
        aw, ah = anchor.winfo_width(), anchor.winfo_height()
        width = max(aw, self.winfo_reqwidth())
        height = self.winfo_reqheight()
        if ax < left or ax + aw > right or ay < top or ay + ah > bottom:
            self.close()
            return False
        below, above = ay + ah + self.gap, ay - height - self.gap
        if below + height <= bottom - 8:
            y = below
        elif above >= top + 8:
            y = above
        else:
            self.close()
            return False
        if width > right - left:
            self.close()
            return False
        x = max(left, min(ax + aw - width if self.align_right else ax, right - width))
        placement = (x - host.winfo_rootx(), y - host.winfo_rooty(), width, height)
        if placement != self._placement:
            self.place(x=placement[0], y=placement[1], width=width, height=height)
            self._placement = placement
        return True

    def _track_anchor(self) -> None:
        self._tracking = None
        if self.reposition():
            # Canvas scrolling may move only an ancestor, without configuring
            # the anchor itself. Track actual coordinates while the menu lives.
            self._tracking = self.after(16, self._track_anchor)

    def watch(self) -> None:
        self._tracking = self.after(16, self._track_anchor)

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
        if self._tracking is not None:
            self.after_cancel(self._tracking)
            self._tracking = None
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
