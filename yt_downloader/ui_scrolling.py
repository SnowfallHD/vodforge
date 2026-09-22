"""Owned pixel scrolling, precision accumulation and nested boundary routing.

Views supply their scrollable widget. A binding owns only its callbacks and
fractional motion; it never owns records, selections, or application actions.
"""

from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Callable
from typing import Any

from .platform_services import present_scrolled_canvas, supports_tk_event
from .ui_layout import accumulated_row_scroll, pixel_scroll_target


def touchpad_scroll_deltas(widget: Any, packed_delta: float) -> tuple[float, float]:
    try:
        x, y = widget.tk.call("tk::PreciseScrollDeltas", packed_delta)
        return float(x), float(y)
    except (AttributeError, TypeError, ValueError, tk.TclError):
        return 0.0, 0.0


def wheel_motion(delta: float, *, precise: bool = False) -> float:
    value = float(delta)
    if not math.isfinite(value):
        return 0.0
    pixels = -value
    if not precise and abs(value) >= 120:
        pixels = -round(value / 120) * 36
    return max(-72.0, min(72.0, pixels))


def nearest_scroll_binding(widget: Any) -> ScrollBinding | None:
    while widget is not None:
        binding = getattr(widget, "_vodforge_scroll_binding", None)
        if binding is not None and not binding.closed:
            return binding
        widget = getattr(widget, "master", None)
    return None


def event_scroll_binding(widget: Any) -> ScrollBinding | None:
    """Explicit sibling inputs route to their owner even through an older bindtag."""
    for name in ("_vodforge_scroll_binding", "_vodforge_scroll_input_binding"):
        binding = getattr(widget, name, None)
        if binding is not None and not binding.closed:
            return binding
    return nearest_scroll_binding(widget)


class ScrollBinding:
    """One widget's input lifetime, including its nested non-scrolling children."""

    def __init__(
        self,
        scroller: Any,
        *targets: Any,
        axis: str = "vertical",
        mode: str = "pixels",
        row_pixels: int = 30,
        horizontal_targets: tuple[Any, ...] = (),
        on_scroll: Callable[[], None] | None = None,
    ) -> None:
        if axis not in {"vertical", "horizontal", "both"}:
            raise ValueError(f"Unsupported scroll axis: {axis}")
        if mode not in {"pixels", "increments", "rows"}:
            raise ValueError(f"Unsupported smooth-scroll mode: {mode}")
        previous = getattr(scroller, "_vodforge_scroll_binding", None)
        if previous is not None:
            previous.close()
        self.scroller, self.axis, self.mode = scroller, axis, mode
        self.row_pixels = max(1, row_pixels)
        self.closed = False
        self._horizontal_targets = horizontal_targets
        self._on_scroll = on_scroll
        self._fraction = {"x": 0.0, "y": 0.0}
        self._rows = {"x": 0.0, "y": 0.0}
        self._bindings: list[tuple[Any, str, str]] = []
        self._targets: set[Any] = set()
        scroller._vodforge_scroll_binding = self
        for target in (scroller, *targets):
            if target is not scroller:
                previous_input = getattr(target, "_vodforge_scroll_input_binding", None)
                if previous_input is not None and previous_input is not self:
                    previous_input._forget_target(target)
                target._vodforge_scroll_input_binding = self
            self._attach(target)
        self._attach_children(scroller)
        self._bind(scroller, "<Destroy>", self._destroyed)
        # Toplevel Map events include newly-created text/buttons inside a viewport.
        # This avoids application-wide bind_all and covers widgets created later.
        top = scroller.winfo_toplevel()
        self._bind(top, "<Map>", self._mapped)

    def _bind(self, target: Any, sequence: str, callback: Any) -> None:
        try:
            token = target.bind(sequence, callback, add="+")
            if token:
                self._bindings.append((target, sequence, token))
        except tk.TclError:
            pass

    def _attach(self, target: Any) -> None:
        if target in self._targets:
            return
        self._targets.add(target)
        if target is not self.scroller:
            self._bind(
                target, "<Destroy>", lambda event: self._forget_target(event.widget)
            )
        self._bind(target, "<MouseWheel>", self._wheel)
        self._bind(target, "<Shift-MouseWheel>", self._wheel)
        if supports_tk_event(target, "<TouchpadScroll>"):
            self._bind(target, "<TouchpadScroll>", self._touchpad)
        self._bind(target, "<Button-4>", lambda event: self._dispatch(event, 0, -36))
        self._bind(target, "<Button-5>", lambda event: self._dispatch(event, 0, 36))

    def _forget_target(self, target: Any) -> None:
        self._targets.discard(target)
        if getattr(target, "_vodforge_scroll_input_binding", None) is self:
            target._vodforge_scroll_input_binding = None
        retained = []
        for widget, sequence, token in self._bindings:
            if widget is target:
                try:
                    widget.unbind(sequence, token)
                except tk.TclError:
                    pass
            else:
                retained.append((widget, sequence, token))
        self._bindings = retained

    def _attach_children(self, parent: Any) -> None:
        for child in parent.winfo_children():
            if nearest_scroll_binding(child) is self:
                self._attach(child)
                self._attach_children(child)

    def _mapped(self, event: Any) -> None:
        if not self.closed and nearest_scroll_binding(event.widget) is self:
            self._attach(event.widget)

    def _destroyed(self, event: Any) -> None:
        if event.widget is self.scroller:
            self.close()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if getattr(self.scroller, "_vodforge_scroll_binding", None) is self:
            self.scroller._vodforge_scroll_binding = None
        for widget, sequence, token in self._bindings:
            try:
                widget.unbind(sequence, token)
            except tk.TclError:
                pass
        self._bindings.clear()
        for target in self._targets:
            if getattr(target, "_vodforge_scroll_input_binding", None) is self:
                target._vodforge_scroll_input_binding = None
        self._targets.clear()

    def _wheel(self, event: Any) -> str:
        pixels = wheel_motion(getattr(event, "delta", 0))
        binding = event_scroll_binding(getattr(event, "widget", self.scroller)) or self
        horizontal = (
            binding.axis == "horizontal"
            or event.widget in binding._horizontal_targets
            or bool(getattr(event, "state", 0) & 1)
        )
        return self._dispatch(
            event, pixels if horizontal else 0, 0 if horizontal else pixels
        )

    def _touchpad(self, event: Any) -> str:
        binding = event_scroll_binding(getattr(event, "widget", self.scroller)) or self
        x, y = touchpad_scroll_deltas(binding.scroller, getattr(event, "delta", 0))
        if event.widget in binding._horizontal_targets:
            y = 0
        return self._dispatch(
            event, wheel_motion(x, precise=True), wheel_motion(y, precise=True)
        )

    def _dispatch(self, event: Any, dx: float, dy: float) -> str:
        if self.closed:
            return "break"
        binding = event_scroll_binding(getattr(event, "widget", self.scroller))
        (binding or self).scroll(dx, dy)
        return "break"

    def _can_scroll(self, axis: str, pixels: float) -> bool:
        if self.axis == "vertical" and axis == "x":
            return False
        if self.axis == "horizontal" and axis == "y":
            return False
        try:
            first, last = (
                self.scroller.xview() if axis == "x" else self.scroller.yview()
            )
            return float(first) > 0.000001 if pixels < 0 else float(last) < 0.999999
        except (AttributeError, TypeError, ValueError, tk.TclError):
            return False

    def scroll(
        self, dx: float, dy: float, *, _batch: list[ScrollBinding] | None = None
    ) -> None:
        if self.closed:
            return
        outer = _batch is None
        batch = [] if _batch is None else _batch
        unused = {"x": 0.0, "y": 0.0}
        for axis, motion in (("x", dx), ("y", dy)):
            if not motion:
                continue
            if axis == "y" and self.axis != "horizontal":
                if motion < 0:
                    self.scroller._vodforge_user_scroll_locked = True
                else:
                    try:
                        if float(self.scroller.yview()[1]) >= 0.995:
                            self.scroller._vodforge_user_scroll_locked = False
                    except (AttributeError, TypeError, ValueError, tk.TclError):
                        pass
            if not self._can_scroll(axis, motion):
                unused[axis] = motion
                self._fraction[axis] = 0.0
                self._rows[axis] = 0.0
                continue
            if axis == "y" and motion < 0:
                self.scroller._vodforge_user_scroll_locked = True
            total = self._fraction[axis] + motion
            # Avoid losing the tenth 0.1-pixel event to binary rounding.
            pixels = math.trunc(total + math.copysign(1e-9, total))
            self._fraction[axis] = total - pixels
            if pixels:
                self._move(axis, pixels)
                if self not in batch:
                    batch.append(self)
        parent = nearest_scroll_binding(getattr(self.scroller, "master", None))
        if parent is not None and any(unused.values()):
            parent.scroll(unused["x"], unused["y"], _batch=batch)
        if outer:
            # One interpreter idle batch covers both axes and routed ancestors.
            for owner in batch:
                if not owner.closed and isinstance(owner.scroller, tk.Canvas):
                    try:
                        if (
                            owner.scroller.winfo_exists()
                            and owner.scroller.winfo_children()
                        ):
                            present_scrolled_canvas(owner.scroller)
                            break
                    except tk.TclError:
                        continue
            # Idle callbacks may navigate or destroy views. No target is used
            # after the drain; the next input resolves its current owner afresh.

    def _move(self, axis: str, pixels: int) -> None:
        scroller = self.scroller
        if axis == "y" and pixels < 0:
            scroller._vodforge_user_scroll_locked = True
        view = scroller.xview if axis == "x" else scroller.yview
        try:
            if self.mode == "rows" or isinstance(scroller, tk.Listbox):
                rows, self._rows[axis] = accumulated_row_scroll(
                    self._rows[axis], pixels, self.row_pixels
                )
                if rows:
                    getattr(scroller, axis + "view_scroll")(rows, "units")
            elif self.mode == "increments":
                getattr(scroller, axis + "view_scroll")(pixels, "units")
            elif isinstance(scroller, tk.Text) and axis == "y":
                try:
                    scroller.yview_scroll(pixels, "pixels")
                except tk.TclError:
                    rows, self._rows[axis] = accumulated_row_scroll(
                        self._rows[axis], pixels, self.row_pixels
                    )
                    if rows:
                        scroller.yview_scroll(rows, "units")
            else:
                first, last = view()
                extent = (
                    scroller.winfo_width() if axis == "x" else scroller.winfo_height()
                )
                target = pixel_scroll_target(
                    float(first), float(last), max(1, extent), pixels
                )
                getattr(scroller, axis + "view_moveto")(target)
            if axis == "y" and pixels > 0 and float(view()[1]) >= 0.995:
                scroller._vodforge_user_scroll_locked = False
            if self._on_scroll is not None:
                self._on_scroll()
        except (AttributeError, TypeError, ValueError, tk.TclError):
            return


def bind_smooth_scroll(
    scroller: Any,
    *targets: Any,
    axis: str = "vertical",
    mode: str = "pixels",
    row_pixels: int = 30,
    horizontal_targets: tuple[Any, ...] = (),
    on_scroll: Callable[[], None] | None = None,
) -> ScrollBinding:
    return ScrollBinding(
        scroller,
        *targets,
        axis=axis,
        mode=mode,
        row_pixels=row_pixels,
        horizontal_targets=horizontal_targets,
        on_scroll=on_scroll,
    )
