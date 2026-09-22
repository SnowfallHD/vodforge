"""A bounded horizontal canvas viewport with owned input and rendering targets.

The caller supplies items, drawing, and actions. This component owns no media,
selection, persistence, or navigation outside its own viewport.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from typing import Any

from .scene_paging import visible_scene_rows
from .ui_canvas_actions import CanvasActions
from .ui_chrome import CanvasSurfaceCache, draw_scene_focus_material
from .ui_layout import window_logical_metrics
from .ui_scrolling import bind_smooth_scroll
from .ui_theme import THEME
from .ui_widgets import SleekScrollbar


class SceneRail(tk.Frame):
    def __init__(
        self,
        parent: tk.Canvas,
        *,
        changed: Callable[[], None],
        used: Callable[[], None],
    ) -> None:
        super().__init__(parent, bg=THEME["bg"], bd=0)
        self._metrics = window_logical_metrics(self)
        self._gap = self._metrics.px(14)
        self.canvas = tk.Canvas(
            self, bg=THEME["bg"], bd=0, highlightthickness=0, takefocus=True
        )
        self.canvas.pack(fill="both", expand=True)
        self._parent_canvas = parent
        self._bar = SleekScrollbar(self, command=self._scroll, orient="horizontal")
        self._bar.pack(fill="x", pady=(self._metrics.px(4), 0))
        self._changed, self._used = changed, used
        self._depth = CanvasSurfaceCache(self.canvas)
        self._targets: list[Any] = []
        self._button_images: list[Any] = []
        self._button_labels: list[Any] = []
        self._play_regions: list[Any] = []
        self._card_actions: list[Any] = []
        self._images: list[Any] = []
        self._items: Sequence[Any] = ()
        self._span = (0, 0)
        self._stride = 1
        self._focus_index = 0
        self._focus_detail = False
        self._item_targets: dict[int, list[Any]] = {}
        self._active = False
        self._closed = False
        self._y = self._height = 0
        self.canvas.configure(xscrollcommand=self._scrolled)
        self._pointer = CanvasActions(self.canvas, lambda: self._targets)
        self._scroll_binding = bind_smooth_scroll(
            self.canvas,
            self._bar,
            axis="both",
            horizontal_targets=(self._bar,),
            on_scroll=used,
        )
        self.canvas.bind("<Left>", lambda event: self._focus(-1))
        self.canvas.bind("<Right>", lambda event: self._focus(1))
        self.canvas.bind("<Home>", lambda event: self._focus(-len(self._items)))
        self.canvas.bind("<End>", lambda event: self._focus(len(self._items)))
        self.canvas.bind("<Return>", self._activate)
        self.canvas.bind("<space>", self._activate)
        self.canvas.bind("<Down>", self._details)
        self.canvas.bind("<Up>", self._details)
        self.canvas.bind("<FocusIn>", lambda event: self._paint_focus())
        self.canvas.bind(
            "<FocusOut>",
            lambda event: self.canvas.delete("keyboard-focus", "focus-play"),
        )
        self.bind("<Destroy>", self._destroyed, add="+")

    def visible(self) -> bool:
        top = self._parent_canvas.canvasy(0)
        return (
            self._y + self._height >= top
            and self._y <= top + self._parent_canvas.winfo_height()
        )

    def _visible_span(self) -> tuple[int, int]:
        return visible_scene_rows(
            len(self._items),
            1,
            self._stride,
            0,
            self.canvas.canvasx(0),
            self.canvas.winfo_width(),
        )

    def _scrolled(self, first: float, last: float) -> None:
        self._bar.set(first, last)
        if self._active and self._visible_span() != self._span:
            self.retire()
            self._changed()

    def _scroll(self, *args: Any) -> None:
        before = self.canvas.xview()
        self.canvas.xview(*args)
        if self.canvas.xview() != before:
            self._used()

    def retire(self) -> None:
        self._targets.clear()
        self._item_targets.clear()
        if self.canvas.winfo_exists():
            self.canvas.delete("keyboard-focus", "hover-play", "focus-play")

    def present(
        self,
        items: Sequence[Any],
        *,
        y: int,
        width: int,
        height: int,
        stride: int,
        draw: Callable[[Any, int], None],
    ) -> None:
        """Use measured caller allocations; reserve this owner's scaled chrome."""
        old_key = (
            getattr(self._items[self._focus_index], "key", None)
            if self._items and self._focus_index < len(self._items)
            else None
        )
        old_left = self.canvas.canvasx(0)
        anchor_index = min(len(self._items) - 1, max(0, int(old_left // self._stride)))
        anchor_key = self._items[anchor_index].key if self._items else None
        anchor_offset = old_left - max(0, anchor_index) * self._stride
        restore = None
        if self._items and (items is not self._items or stride != self._stride):
            index = next(
                (i for i, item in enumerate(items) if item.key == anchor_key),
                min(anchor_index, max(0, len(items) - 1)),
            )
            restore = max(0, index * stride + min(anchor_offset, stride - 1))
        self._items = items
        self._focus_index = next(
            (i for i, item in enumerate(items) if item.key == old_key),
            min(self._focus_index, max(0, len(items) - 1)),
        )
        self._y, self._height, self._stride = y, height, stride
        self.configure(width=width, height=height)
        viewport_height = max(
            1, height - self._bar.winfo_reqheight() - self._metrics.px(4)
        )
        self.canvas.configure(
            width=width,
            height=viewport_height,
            scrollregion=(
                0,
                0,
                max(width, len(items) * stride - self._gap),
                viewport_height,
            ),
        )
        if restore is not None:
            extent = max(width, len(items) * stride - self._gap)
            self.canvas.xview_moveto(min(restore, max(0, extent - width)) / extent)
        self._parent_canvas.create_window(
            0, y, window=self, anchor="nw", width=width, height=height
        )
        self._active = self.visible()
        self.retire()
        self.canvas.delete("all")
        self._button_images.clear()
        self._button_labels.clear()
        self._images.clear()
        self._play_regions.clear()
        self._card_actions.clear()
        self._span = self._visible_span()
        if self._active:
            for index in range(*self._span):
                start = len(self._targets)
                draw(items[index], index * stride)
                self._item_targets[index] = self._targets[start:]
        self._paint_focus()

    def _focus(self, delta: int) -> str:
        self._focus_index = max(0, min(len(self._items) - 1, self._focus_index + delta))
        self._focus_detail = False
        left = self._focus_index * self._stride
        right = left + self._stride - self._gap
        viewport = self.canvas.canvasx(0)
        extent = max(
            self.canvas.winfo_width(), len(self._items) * self._stride - self._gap
        )
        if left < viewport:
            self.canvas.xview_moveto(left / extent)
        elif right > viewport + self.canvas.winfo_width():
            self.canvas.xview_moveto((right - self.canvas.winfo_width()) / extent)
        self._used()
        self._paint_focus()
        return "break"

    def _details(self, event: Any) -> str:
        self._focus_detail = event.keysym == "Down"
        self._paint_focus()
        return "break"

    def _focused(self) -> Any:
        targets = self._item_targets.get(self._focus_index, ())
        return (
            targets[min(int(self._focus_detail), len(targets) - 1)] if targets else None
        )

    def _paint_focus(self) -> None:
        self.canvas.delete("keyboard-focus", "focus-play")
        target = self._focused()
        if target and self.canvas.focus_get() is self.canvas:
            draw_scene_focus_material(self.canvas, target[0])
            card = next(
                (
                    cover
                    for cover, detail in self._card_actions
                    if target[0] in (cover, detail)
                ),
                None,
            )
            if card is not None:
                paint = getattr(self, "_paint_play_affordance", None)
                if paint is not None:
                    paint(card, "focus-play")
                    self.canvas.tag_raise("keyboard-focus")

    def _activate(self, event: Any = None) -> str:
        target = self._focused()
        if target:
            target[1]()
        return "break"

    def _destroyed(self, event: Any) -> None:
        if event.widget is self:
            self._closed = True
            self.retire()
            self._scroll_binding.close()
            self._depth.clear()
            self._items = ()
            self._images.clear()
