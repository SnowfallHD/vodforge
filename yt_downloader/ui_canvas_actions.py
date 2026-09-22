"""Scoped pointer gestures for the existing canvas scene renderers.

Targets belong to one render. A release may dispatch only the identical target
pressed in that render; repaint, data replacement, navigation and modal grabs
retire the gesture. Views retain their own actions and keyboard semantics.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from typing import Any

from .ui_chrome import paint_action_material

Target = tuple[tuple[int, int, int, int], Callable[[], None]]


class CanvasActions:
    def __init__(
        self, canvas: tk.Canvas, targets: Callable[[], Sequence[Target]]
    ) -> None:
        self.canvas = canvas
        self.targets = targets
        self._pressed: Target | None = None
        self._bindings = []
        for sequence, callback in (
            ("<Button-1>", self.press),
            ("<ButtonRelease-1>", self.release),
            ("<Motion>", self.motion),
            ("<Leave>", self.leave),
            ("<Unmap>", self.unmap),
            ("<<ViewInputRetired>>", self.unmap),
            ("<Destroy>", self.destroy),
        ):
            self._bindings.append((sequence, canvas.bind(sequence, callback, add="+")))

    def hit(self, event: Any) -> Target | None:
        try:
            grab = self.canvas.grab_current()
            if grab is not None and grab is not self.canvas:
                return None
            x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
            return next(
                (
                    target
                    for target in reversed(self.targets())
                    if target[0][0] <= x <= target[0][2]
                    and target[0][1] <= y <= target[0][3]
                ),
                None,
            )
        except tk.TclError:
            return None

    def paint(self, target: Target | None, *, pressed: bool = False) -> None:
        paint_action_material(self.canvas, target[0] if target else None, pressed)
        self.canvas.delete("pointer-state")
        self.canvas.configure(cursor="hand2" if target else "")

    def press(self, event: Any) -> str:
        self._pressed = self.hit(event)
        self.canvas.focus_set()
        self.paint(self._pressed, pressed=True)
        return "break"

    def release(self, event: Any) -> str:
        pressed, self._pressed = self._pressed, None
        current = self.hit(event)
        self.paint(current)
        if pressed is not None and current is pressed:
            # Retire before dispatch: nested menus/dialogs cannot reuse this click.
            pressed[1]()
        return "break"

    def motion(self, event: Any) -> None:
        target = self.hit(event)
        self.paint(target, pressed=target is self._pressed and target is not None)

    def leave(self, _event: Any) -> None:
        self.paint(None)

    def unmap(self, event: Any) -> None:
        if event.widget is self.canvas:
            self._pressed = None
            try:
                self.paint(None)
            except tk.TclError:
                # Destruction may already have retired the native canvas.
                pass

    def destroy(self, event: Any) -> None:
        if event.widget is self.canvas:
            self._pressed = None
            self._bindings.clear()
