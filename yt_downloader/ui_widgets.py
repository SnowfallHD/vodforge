from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Iterable, Mapping
from functools import partial
from typing import Any, Literal, Protocol, cast

from .models import OutputType
from .ui_layout import (
    accumulated_row_scroll,
    focus_wheel_pixels,
    pixel_scroll_target,
    pixel_table_visible_row_window,
    resized_table_column_width,
    responsive_table_stretch_indices,
    stretched_table_column_widths,
)
from .ui_theme import (
    FONT_UI,
    FONT_UI_SMALL,
    FONT_UI_SMALL_MEDIUM,
    THEME,
)


class _ImageModule(Protocol):
    LANCZOS: Any

    def new(self, mode: str, size: tuple[int, int], color: Any = ...) -> Any: ...


class _ImageDrawModule(Protocol):
    def Draw(self, image: Any) -> Any: ...


class _ImageTkModule(Protocol):
    def PhotoImage(self, image: Any) -> Any: ...


Image: _ImageModule | None
ImageDraw: _ImageDrawModule | None
ImageTk: _ImageTkModule | None
try:
    from PIL import Image as _PILImage
    from PIL import ImageDraw as _PILImageDraw
    from PIL import ImageTk as _PILImageTk
except Exception:  # noqa: BLE001  # pragma: no cover - optional rendering falls back to Tk
    Image = None
    ImageDraw = None
    ImageTk = None
else:
    Image = cast(_ImageModule, _PILImage)
    ImageDraw = cast(_ImageDrawModule, _PILImageDraw)
    ImageTk = cast(_ImageTkModule, _PILImageTk)


class _VerticalScroller(Protocol):
    tk: Any


def touchpad_scroll_deltas(
    widget: tk.Misc | _VerticalScroller,
    packed_delta: float,
) -> tuple[float, float]:
    """Decode Tk 9's packed macOS precision-scroll delta into x/y motion."""
    try:
        raw_x, raw_y = widget.tk.call("tk::PreciseScrollDeltas", packed_delta)
        return float(raw_x), float(raw_y)
    except (AttributeError, TypeError, ValueError, tk.TclError):
        return 0.0, 0.0


def bind_smooth_vertical_wheel(
    scroller: tk.Text | tk.Canvas,
    *targets: tk.Misc,
    mode: str = "pixels",
    row_pixels: int = 30,
) -> None:
    """Preserve trackpad deltas instead of letting Tk amplify them into jumps."""
    if mode not in {"pixels", "increments", "rows"}:
        raise ValueError(f"Unsupported smooth-scroll mode: {mode}")
    wheel_targets = targets or (scroller,)
    remainder = 0.0

    def scroll_pixels(pixels: int) -> str:
        nonlocal remainder
        if not pixels:
            return "break"
        # A live log may append while a precision gesture is still moving.
        # Record the reader's intent before moving the viewport so a writer
        # cannot mistake a near-tail position for permission to snap back.
        if pixels < 0:
            setattr(scroller, "_vodforge_user_scroll_locked", True)  # noqa: B010
        if mode == "rows":
            rows, remainder = accumulated_row_scroll(remainder, pixels, row_pixels)
            if rows:
                scroller.yview_scroll(rows, "units")
            if pixels > 0:
                try:
                    _first, last = scroller.yview()
                    if float(last) >= 0.995:
                        setattr(scroller, "_vodforge_user_scroll_locked", False)  # noqa: B010
                except (AttributeError, TypeError, ValueError, tk.TclError):
                    pass
            return "break"
        if mode == "pixels":
            if isinstance(scroller, tk.Text):
                try:
                    # Native Text pixel scrolling does not depend on yview
                    # fractions that may be stale while wrapped display-line
                    # metrics settle after insertion or a resize.
                    scroller.yview_scroll(pixels, "pixels")
                except tk.TclError:
                    rows, remainder = accumulated_row_scroll(
                        remainder, pixels, row_pixels
                    )
                    if rows:
                        scroller.yview_scroll(rows, "units")
            else:
                viewport_height = max(1, scroller.winfo_height())
                try:
                    first, last = scroller.yview()
                    target = pixel_scroll_target(
                        float(first), float(last), viewport_height, pixels
                    )
                    if target != float(first):
                        scroller.yview_moveto(target)
                except (AttributeError, TypeError, ValueError, tk.TclError):
                    pass
            if pixels > 0:
                try:
                    _first, last = scroller.yview()
                    if float(last) >= 0.995:
                        setattr(scroller, "_vodforge_user_scroll_locked", False)  # noqa: B010
                except (AttributeError, TypeError, ValueError, tk.TclError):
                    pass
            return "break"
        try:
            scroller.yview_scroll(pixels, "units")
        except tk.TclError:
            rows, remainder = accumulated_row_scroll(remainder, pixels, row_pixels)
            if rows:
                scroller.yview_scroll(rows, "units")
        if pixels > 0:
            try:
                _first, last = scroller.yview()
                if float(last) >= 0.995:
                    setattr(scroller, "_vodforge_user_scroll_locked", False)  # noqa: B010
            except (AttributeError, TypeError, ValueError, tk.TclError):
                pass
        return "break"

    def on_wheel(event: tk.Event[Any]) -> str:
        return scroll_pixels(focus_wheel_pixels(getattr(event, "delta", 0)))

    def on_touchpad_scroll(event: tk.Event[Any]) -> str:
        _delta_x, delta_y = touchpad_scroll_deltas(scroller, getattr(event, "delta", 0))
        return scroll_pixels(focus_wheel_pixels(delta_y))

    for target in wheel_targets:
        target.bind("<MouseWheel>", on_wheel, add="+")
        target.bind("<Button-4>", lambda _event: scroll_pixels(-36), add="+")
        target.bind("<Button-5>", lambda _event: scroll_pixels(36), add="+")
        try:
            target.bind("<TouchpadScroll>", on_touchpad_scroll, add="+")
        except tk.TclError:
            pass


def reveal_toplevel(popup: tk.Toplevel, geometry: str) -> None:
    """Place a hidden custom window before mapping it to avoid visible jumps."""
    popup.geometry(geometry)
    popup.deiconify()
    popup.lift()


TOOLTIP_DELAY_MS = 420
TOOLTIP_POINTER_POLL_MS = 40


def pointer_inside_widget_bounds(
    widgets: tuple[tk.Widget, ...], pointer_x: int, pointer_y: int
) -> bool:
    """Return whether a screen-space point is inside one of the exact widget bounds."""
    for widget in widgets:
        try:
            if not widget.winfo_ismapped():
                continue
            left = widget.winfo_rootx()
            top = widget.winfo_rooty()
            width = widget.winfo_width()
            height = widget.winfo_height()
        except tk.TclError:
            continue
        if left <= pointer_x < left + width and top <= pointer_y < top + height:
            return True
    return False


class _TooltipController:
    """One authoritative tooltip surface per window.

    Tk can miss a widget ``<Leave>`` when a pointer moves quickly across child
    widgets or when an override-redirect tooltip appears under the pointer. A
    single controller prevents competing tooltip windows, delays transient
    flyovers, and verifies the real pointer position while a tooltip is open.
    """

    def __init__(self, host: tk.Misc) -> None:
        self.host = host
        self.tip: tk.Toplevel | None = None
        self.pending_after_id: str | None = None
        self.pointer_poll_after_id: str | None = None
        self.pending: ToolTip | None = None
        self.active: ToolTip | None = None
        host.bind("<Unmap>", lambda _event: self.hide(), add="+")
        host.bind(
            "<Destroy>",
            lambda event: self.hide() if event.widget is host else None,
            add="+",
        )

    def request_show(self, tooltip: ToolTip) -> None:
        if not tooltip.text:
            return
        if self.active is tooltip:
            return
        self._cancel_pending()
        if self.active is not None and self.active is not tooltip:
            self._destroy_tip()
        self.pending = tooltip
        try:
            self.pending_after_id = self.host.after(
                TOOLTIP_DELAY_MS, lambda: self._show_if_owned(tooltip)
            )
        except tk.TclError:
            self.pending = None

    def request_hide(self, tooltip: ToolTip) -> None:
        try:
            self.host.after_idle(lambda: self._hide_if_pointer_left(tooltip))
        except tk.TclError:
            self.hide()

    def _hide_if_pointer_left(self, tooltip: ToolTip) -> None:
        if (
            self.pending is tooltip or self.active is tooltip
        ) and not tooltip.contains_pointer():
            self.hide()

    def _show_if_owned(self, tooltip: ToolTip) -> None:
        self.pending_after_id = None
        if self.pending is not tooltip or not tooltip.contains_pointer():
            if self.pending is tooltip:
                self.pending = None
            return
        self._destroy_tip()
        try:
            left, top, _right, bottom = tooltip.anchor_bounds()
            tip = tk.Toplevel(self.host)
            tip.withdraw()
            tip.wm_overrideredirect(True)
            label = tk.Label(
                tip,
                text=tooltip.text,
                justify="left",
                wraplength=320,
                bg="#111214",
                fg=THEME["text"],
                relief="solid",
                borderwidth=1,
                padx=8,
                pady=6,
                font=FONT_UI_SMALL,
            )
            label.pack()
            tip.update_idletasks()
            screen_width = tip.winfo_screenwidth()
            screen_height = tip.winfo_screenheight()
            tip_width = tip.winfo_reqwidth()
            tip_height = tip.winfo_reqheight()
            x = min(max(8, left), max(8, screen_width - tip_width - 8))
            y = bottom + 8
            if y + tip_height > screen_height - 8:
                y = max(8, top - tip_height - 8)
            self.tip = tip
            self.pending = None
            self.active = tooltip
            reveal_toplevel(tip, f"+{x}+{y}")
            self._schedule_pointer_poll()
        except (tk.TclError, ValueError):
            self._destroy_tip()

    def _schedule_pointer_poll(self) -> None:
        self._cancel_pointer_poll()
        try:
            self.pointer_poll_after_id = self.host.after(
                TOOLTIP_POINTER_POLL_MS, self._poll_pointer
            )
        except tk.TclError:
            self.pointer_poll_after_id = None

    def _poll_pointer(self) -> None:
        self.pointer_poll_after_id = None
        tooltip = self.active
        if tooltip is None or not tooltip.contains_pointer():
            self.hide()
            return
        self._schedule_pointer_poll()

    def _cancel_pending(self) -> None:
        if self.pending_after_id is not None:
            try:
                self.host.after_cancel(self.pending_after_id)
            except tk.TclError:
                pass
        self.pending_after_id = None
        self.pending = None

    def _cancel_pointer_poll(self) -> None:
        if self.pointer_poll_after_id is not None:
            try:
                self.host.after_cancel(self.pointer_poll_after_id)
            except tk.TclError:
                pass
        self.pointer_poll_after_id = None

    def _destroy_tip(self) -> None:
        self._cancel_pointer_poll()
        if self.tip is not None:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
        self.tip = None
        self.active = None

    def hide(self) -> None:
        self._cancel_pending()
        self._cancel_pointer_poll()
        self._destroy_tip()


class ToolTip:
    """Precise, delayed hover tooltip coordinated within its containing window."""

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        targets_provider = getattr(widget, "tooltip_targets", None)
        targets = tuple(targets_provider()) if callable(targets_provider) else (widget,)
        self.targets = targets or (widget,)
        host = widget.winfo_toplevel()
        controller = getattr(host, "_vodforge_tooltip_controller", None)
        if controller is None:
            controller = _TooltipController(host)
            # The controller is intentionally cached on this exact Tk host.
            setattr(host, "_vodforge_tooltip_controller", controller)  # noqa: B010
        self.controller: _TooltipController = controller
        for target in self.targets:
            target.bind(
                "<Enter>",
                lambda _event, tooltip=self: tooltip.controller.request_show(tooltip),
                add="+",
            )
            target.bind(
                "<Leave>",
                lambda _event, tooltip=self: tooltip.controller.request_hide(tooltip),
                add="+",
            )
            target.bind("<ButtonPress>", self._hide_from_event, add="+")
            target.bind("<Destroy>", self._hide_from_event, add="+")

    def _hide_from_event(self, _event: tk.Event[tk.Widget]) -> None:
        self.controller.hide()

    def contains_pointer(self) -> bool:
        try:
            pointer_x, pointer_y = self.widget.winfo_pointerxy()
        except tk.TclError:
            return False
        return pointer_inside_widget_bounds(self.targets, pointer_x, pointer_y)

    def anchor_bounds(self) -> tuple[int, int, int, int]:
        bounds: list[tuple[int, int, int, int]] = []
        for target in self.targets:
            try:
                if target.winfo_ismapped():
                    left = target.winfo_rootx()
                    top = target.winfo_rooty()
                    bounds.append(
                        (
                            left,
                            top,
                            left + target.winfo_width(),
                            top + target.winfo_height(),
                        )
                    )
            except tk.TclError:
                continue
        if not bounds:
            raise ValueError("tooltip target is not visible")
        return (
            min(item[0] for item in bounds),
            min(item[1] for item in bounds),
            max(item[2] for item in bounds),
            max(item[3] for item in bounds),
        )


class SleekProgressbar(tk.Canvas):
    """A thin, borderless progress track with ttk-compatible controls."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        variable: tk.Variable | None = None,
        maximum: float = 100.0,
        value: float = 0.0,
        mode: str = "determinate",
        height: int = 5,
        track_color: str = THEME["surface_2"],
        bar_color: str = THEME["accent"],
        **kwargs: Any,
    ) -> None:
        kwargs.pop("style", None)
        super().__init__(
            parent, height=height, bg=THEME["bg"], bd=0, highlightthickness=0, **kwargs
        )
        self._maximum = max(1.0, float(maximum))
        self._mode = mode
        self._track_color = track_color
        self._bar_color = bar_color
        self._phase = 0.0
        self._after_id: str | None = None
        self._variable = (
            variable if variable is not None else tk.DoubleVar(master=self, value=value)
        )
        if variable is not None and value:
            self._variable.set(value)
        self._variable.trace_add("write", lambda *_args: self._redraw())
        self.bind("<Configure>", lambda _event: self._redraw(), add="+")
        self.after_idle(self._redraw)

    def configure(self, cnf: Any | None = None, **kwargs: Any) -> Any:
        if cnf:
            kwargs.update(cnf)
        if "mode" in kwargs:
            self._mode = str(kwargs.pop("mode"))
        if "maximum" in kwargs:
            self._maximum = max(1.0, float(kwargs.pop("maximum")))
        if "value" in kwargs:
            self._variable.set(float(kwargs.pop("value")))
        if "track_color" in kwargs:
            self._track_color = str(kwargs.pop("track_color"))
        if "bar_color" in kwargs:
            self._bar_color = str(kwargs.pop("bar_color"))
        result = super().configure(**kwargs) if kwargs else None
        self._redraw()
        return result

    config = configure

    def start(self, interval: int = 50) -> None:
        self.stop()
        self._mode = "indeterminate"

        def tick() -> None:
            self._phase = (self._phase + 0.035) % 1.0
            self._redraw()
            self._after_id = self.after(interval, tick)

        tick()

    def stop(self) -> None:
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _redraw(self) -> None:
        try:
            width = max(1, self.winfo_width())
            height = max(3, self.winfo_height())
        except tk.TclError:
            return
        self.delete("all")
        y1 = max(0, (height - 3) // 2)
        y2 = min(height, y1 + 3)
        self.create_rectangle(0, y1, width, y2, fill=self._track_color, outline="")
        if self._mode == "indeterminate":
            segment = max(24, int(width * 0.24))
            start = max(0, int((width + segment) * self._phase) - segment)
            end = min(width, start + segment)
        else:
            try:
                fraction = max(
                    0.0, min(1.0, float(self._variable.get()) / self._maximum)
                )
            except (TypeError, ValueError, tk.TclError):
                fraction = 0.0
            start, end = 0, int(width * fraction)
        if end > start:
            self.create_rectangle(start, y1, end, y2, fill=self._bar_color, outline="")
            if y1 > 0:
                self.create_line(start, y1, end, y1, fill=self._bar_color)


class PixelScrollTable(tk.Frame):
    """Small Treeview-compatible table with true pixel scrolling."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        columns: tuple[str, ...],
        selectmode: str = "browse",
        row_height: int = 30,
        header_height: int = 28,
    ) -> None:
        del selectmode
        super().__init__(
            parent,
            bg=THEME["border"],
            bd=0,
            highlightthickness=1,
            highlightbackground=THEME["subtle"],
        )
        self._columns = tuple(columns)
        self._headings = {column: column for column in columns}
        self._heading_anchors: dict[str, str | None] = {
            column: None for column in columns
        }
        self._column_options: dict[str, dict[str, Any]] = {
            column: {"width": 100, "minwidth": 40, "stretch": False, "anchor": "w"}
            for column in columns
        }
        self._items: dict[str, tuple[Any, ...]] = {}
        self._order: list[str] = []
        self._selection: str | None = None
        self._focus_item: str | None = None
        self._row_height = max(20, int(row_height))
        self._header_height = max(20, int(header_height))
        self._yscrollcommand: Callable[[float, float], Any] | None = None
        self._xscrollcommand: Callable[[float, float], Any] | None = None
        self._font = tkfont.Font(font=FONT_UI)
        self._header_font = tkfont.Font(font=FONT_UI_SMALL_MEDIUM)
        self._manually_resized_columns: set[str] = set()
        self._last_manually_resized_column: str | None = None
        self._resize_column: str | None = None
        self._resize_origin_x = 0.0
        self._resize_origin_width = 0
        self._resize_hover_column: str | None = None
        self._redraw_after_id: str | None = None
        self._redrawing = False
        # Keep the divider itself quiet while giving trackpads and high-DPI
        # pointers a forgiving target on either side of the hairline.
        self._resize_margin = 8

        self._header = tk.Canvas(
            self,
            height=self._header_height,
            bg=THEME["surface"],
            bd=0,
            highlightthickness=0,
            xscrollincrement=1,
        )
        self._body = tk.Canvas(
            self,
            bg=THEME["surface"],
            bd=0,
            highlightthickness=0,
            takefocus=True,
            xscrollincrement=1,
            yscrollincrement=1,
        )
        self._header.pack(fill="x")
        self._body.pack(fill="both", expand=True)
        self._body.configure(
            yscrollcommand=self._report_yview, xscrollcommand=self._report_xview
        )
        self._body.bind("<Configure>", lambda _event: self._schedule_redraw(), add="+")
        self._body.bind("<Button-1>", self._select_from_pointer, add="+")
        self._body.bind("<Up>", lambda _event: self._move_selection(-1), add="+")
        self._body.bind("<Down>", lambda _event: self._move_selection(1), add="+")
        self._body.bind(
            "<Prior>",
            lambda _event: self._move_selection(-max(1, self._visible_rows() - 1)),
            add="+",
        )
        self._body.bind(
            "<Next>",
            lambda _event: self._move_selection(max(1, self._visible_rows() - 1)),
            add="+",
        )
        self._header.bind("<Motion>", self._update_resize_cursor, add="+")
        self._header.bind("<Leave>", self._clear_resize_cursor, add="+")
        self._header.bind("<ButtonPress-1>", self._begin_column_resize, add="+")
        self._header.bind("<B1-Motion>", self._drag_column_resize, add="+")
        self._header.bind("<ButtonRelease-1>", self._end_column_resize, add="+")
        self._bind_precision_scroll(self._body)
        self._bind_precision_scroll(self._header, horizontal_only=True)

    def __getitem__(self, key: str) -> Any:
        if key == "columns":
            return self._columns
        return super().__getitem__(key)

    def configure(self, cnf: Any | None = None, **kwargs: Any) -> Any:
        if cnf:
            kwargs.update(cnf)
        if "yscrollcommand" in kwargs:
            self._yscrollcommand = kwargs.pop("yscrollcommand")
        if "xscrollcommand" in kwargs:
            self._xscrollcommand = kwargs.pop("xscrollcommand")
        result = super().configure(**kwargs) if kwargs else None
        self._report_yview(*self._body.yview())
        self._report_xview(*self._body.xview())
        return result

    config = configure

    def bind_body_event(
        self,
        sequence: str,
        func: Callable[[tk.Event[Any]], object],
        add: Literal["", "+"] | bool | None = None,
    ) -> str:
        """Bind one table-content event to the inner scrolling Canvas."""
        return self._body.bind(sequence, func, add)

    def heading(
        self, column: str, *, text: str = "", anchor: str | None = None
    ) -> None:
        self._headings[column] = text
        if anchor is not None:
            self._heading_anchors[column] = anchor
        self._redraw()

    def column(self, column: str, **kwargs: Any) -> dict[str, Any]:
        options = self._column_options[column]
        options.update(kwargs)
        options["width"] = max(
            int(options.get("minwidth", 1)), int(options.get("width", 100))
        )
        self._redraw()
        return dict(options)

    def layout_column(self, column: str, **kwargs: Any) -> dict[str, Any]:
        """Apply responsive defaults while retaining widths dragged this session."""
        if column in self._manually_resized_columns:
            kwargs.pop("width", None)
        return self.column(column, **kwargs)

    def insert(
        self, _parent: str, index: str | int, *, iid: str, values: tuple[Any, ...]
    ) -> str:
        item_id = str(iid)
        if item_id in self._items:
            self.delete(item_id)
        self._order.append(item_id) if index == "end" else self._order.insert(
            max(0, int(index)), item_id
        )
        self._items[item_id] = tuple(values)
        self._redraw()
        return item_id

    def replace_rows(
        self,
        rows: Iterable[tuple[str, tuple[Any, ...]]],
        *,
        selected: str | None = None,
    ) -> tuple[str, ...]:
        """Replace the complete model with one Canvas redraw.

        Treeview-compatible callers historically deleted and inserted every
        row separately. On a Canvas table that rebuilt the whole surface for
        every mutation, making a large Library effectively quadratic. Keep the
        model update atomic and let the virtualized renderer paint once.
        """
        items: dict[str, tuple[Any, ...]] = {}
        order: list[str] = []
        for raw_item, values in rows:
            item = str(raw_item)
            if item in items:
                order.remove(item)
            order.append(item)
            items[item] = tuple(values)
        self._items = items
        self._order = order
        preferred = str(selected) if selected is not None else self._selection
        self._selection = preferred if preferred in items else None
        self._focus_item = self._selection
        self._redraw()
        return tuple(order)

    def delete(self, *items: str) -> None:
        for raw_item in items:
            item = str(raw_item)
            self._items.pop(item, None)
            if item in self._order:
                self._order.remove(item)
            if self._selection == item:
                self._selection = None
            if self._focus_item == item:
                self._focus_item = None
        self._redraw()

    def get_children(self, _item: str | None = None) -> tuple[str, ...]:
        return tuple(self._order)

    def selection(self) -> tuple[str, ...]:
        return (self._selection,) if self._selection in self._items else ()

    def selection_set(self, item: str) -> None:
        item_id = str(item)
        if item_id not in self._items:
            return
        changed = item_id != self._selection
        self._selection = item_id
        self._focus_item = item_id
        self._redraw()
        self._see(item_id)
        if changed:
            self._body.event_generate("<<TreeviewSelect>>", when="tail")

    def focus_item(self, item: str | None = None) -> str:
        """Get or set the logical row focus without shadowing Tk widget focus."""
        if item is None:
            return self._focus_item or ""
        if str(item) in self._items:
            self._focus_item = str(item)
        return self._focus_item or ""

    def identify_row(self, y: float) -> str:
        index = int(float(self._body.canvasy(y)) // self._row_height)
        return self._order[index] if 0 <= index < len(self._order) else ""

    def identify_column(self, x: float) -> str:
        position = float(self._body.canvasx(x))
        cursor = 0.0
        for index, (_column, width, _anchor) in enumerate(
            self._layout_columns(), start=1
        ):
            cursor += width
            if position < cursor:
                return f"#{index}"
        return ""

    def yview(self, *args: Any) -> tuple[float, float] | None:
        if not args:
            return self._body.yview()
        self._body.yview(*args)
        self._schedule_redraw()
        return None

    def xview(self, *args: Any) -> tuple[float, float] | None:
        if not args:
            return self._body.xview()
        self._body.xview(*args)
        self._header.xview(*args)
        return None

    def _report_yview(self, first: str | float, last: str | float) -> None:
        if self._yscrollcommand is not None:
            self._yscrollcommand(float(first), float(last))
        # Every supported scroll entry point already schedules a redraw. Canvas
        # can report yview again after a scrollregion update; scheduling from
        # that callback creates a self-sustaining idle redraw loop on Aqua and
        # makes initial mapping and native resize needlessly expensive.

    def _report_xview(self, first: str | float, last: str | float) -> None:
        self._header.xview_moveto(float(first))
        if self._xscrollcommand is not None:
            self._xscrollcommand(float(first), float(last))

    def _visible_rows(self) -> int:
        return max(1, self._body.winfo_height() // self._row_height)

    def _layout_columns(self) -> list[tuple[str, int, str]]:
        widths = [
            max(
                int(self._column_options[column].get("minwidth", 1)),
                int(self._column_options[column].get("width", 100)),
            )
            for column in self._columns
        ]
        stretch_columns = {
            column
            for column in self._columns
            if self._column_options[column].get("stretch")
        }
        stretch_limits: dict[int, int | None] = {}
        for index in responsive_table_stretch_indices(
            self._columns,
            stretch_columns,
            self._manually_resized_columns,
            resizing_column=self._resize_column,
            last_resized_column=self._last_manually_resized_column,
        ):
            column = self._columns[index]
            raw_limit = self._column_options[column].get("stretchmax")
            stretch_limits[index] = int(raw_limit) if raw_limit is not None else None
        widths = stretched_table_column_widths(
            widths, max(1, self._body.winfo_width()), stretch_limits
        )
        return [
            (
                column,
                widths[index],
                str(self._column_options[column].get("anchor", "w")),
            )
            for index, column in enumerate(self._columns)
        ]

    def _column_divider_at(self, x: float) -> str | None:
        position = float(self._header.canvasx(x))
        cursor = 0.0
        layout = self._layout_columns()
        for column, width, _anchor in layout[:-1]:
            cursor += width
            if abs(position - cursor) <= self._resize_margin:
                return column
        return None

    def _set_header_cursor(self, cursor: str) -> None:
        try:
            self._header.configure(cursor=cursor)
        except tk.TclError:
            self._header.configure(
                cursor="arrow" if not cursor else "sb_h_double_arrow"
            )

    def _update_resize_cursor(self, event: tk.Event[Any]) -> None:
        if self._resize_column is not None:
            return
        hovered = self._column_divider_at(event.x)
        if hovered != self._resize_hover_column:
            self._resize_hover_column = hovered
            self._redraw()
        self._set_header_cursor("sb_h_double_arrow" if hovered is not None else "")

    def _clear_resize_cursor(self, _event: tk.Event[Any] | None = None) -> None:
        if self._resize_column is not None:
            return
        if self._resize_hover_column is not None:
            self._resize_hover_column = None
            self._redraw()
        self._set_header_cursor("")

    def _begin_column_resize(self, event: tk.Event[Any]) -> str | None:
        column = self._column_divider_at(event.x)
        if column is None:
            return None
        rendered_width = next(
            width
            for rendered_column, width, _anchor in self._layout_columns()
            if rendered_column == column
        )
        self._resize_column = column
        self._resize_hover_column = column
        self._resize_origin_x = float(event.x)
        self._resize_origin_width = int(rendered_width)
        self._column_options[column]["width"] = int(rendered_width)
        try:
            self._header.grab_set()
        except tk.TclError:
            pass
        self._set_header_cursor("sb_h_double_arrow")
        return "break"

    def _drag_column_resize(self, event: tk.Event[Any]) -> str | None:
        column = self._resize_column
        if column is None:
            return None
        current_x = float(event.x)
        options = self._column_options[column]
        options["width"] = resized_table_column_width(
            self._resize_origin_width,
            round(current_x - self._resize_origin_x),
            int(options.get("minwidth", 1)),
        )
        self._manually_resized_columns.add(column)
        self._last_manually_resized_column = column
        self._redraw()
        return "break"

    def _end_column_resize(self, event: tk.Event[Any]) -> str | None:
        column = self._resize_column
        if column is None:
            return None
        self._drag_column_resize(event)

        self._resize_column = None
        try:
            if self._header.grab_current() is self._header:
                self._header.grab_release()
        except tk.TclError:
            pass
        self._resize_hover_column = self._column_divider_at(event.x)
        self._set_header_cursor(
            "sb_h_double_arrow" if self._resize_hover_column is not None else ""
        )
        self._redraw()
        return "break"

    def _ellipsize(self, value: Any, width: int, *, font: tkfont.Font) -> str:
        text = str(value or "")
        available = max(0, width - 16)
        if font.measure(text) <= available:
            return text
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if font.measure(text[:middle] + "…") <= available:
                low = middle
            else:
                high = middle - 1
        return text[:low] + "…"

    def _redraw(self) -> None:
        if self._redraw_after_id is not None:
            try:
                self.after_cancel(self._redraw_after_id)
            except tk.TclError:
                pass
            self._redraw_after_id = None
        try:
            y_offset = max(0.0, float(self._body.canvasy(0)))
            x_offset = max(0.0, float(self._body.canvasx(0)))
        except tk.TclError:
            return
        self._redrawing = True
        layout = self._layout_columns()
        content_width = max(1, sum(width for _column, width, _anchor in layout))
        content_height = max(self._row_height, len(self._order) * self._row_height)
        try:
            self._header.delete("all")
            self._body.delete("all")
            cursor = 0
            for column, width, anchor in layout:
                heading_anchor = self._heading_anchors.get(column) or anchor
                self._header.create_rectangle(
                    cursor,
                    0,
                    cursor + width,
                    self._header_height,
                    fill=THEME["surface"],
                    outline="",
                )
                self._header.create_text(
                    cursor
                    + (
                        width / 2
                        if heading_anchor == "center"
                        else width - 10
                        if heading_anchor == "e"
                        else 10
                    ),
                    self._header_height / 2,
                    text=self._ellipsize(
                        self._headings.get(column, column),
                        width,
                        font=self._header_font,
                    ),
                    anchor="center"
                    if heading_anchor == "center"
                    else "e"
                    if heading_anchor == "e"
                    else "w",
                    fill=THEME["muted"],
                    font=self._header_font,
                )
                cursor += width
                if column != layout[-1][0]:
                    self._header.create_line(
                        cursor,
                        5,
                        cursor,
                        self._header_height - 5,
                        fill=THEME["accent"]
                        if column in {self._resize_column, self._resize_hover_column}
                        else THEME["subtle"],
                        width=2
                        if column in {self._resize_column, self._resize_hover_column}
                        else 1,
                    )
            self._header.create_line(
                0,
                self._header_height - 1,
                content_width,
                self._header_height - 1,
                fill=THEME["border"],
            )

            viewport_height = max(self._row_height, self._body.winfo_height())
            y_offset, first_row, last_row = pixel_table_visible_row_window(
                len(self._order),
                self._row_height,
                viewport_height,
                y_offset,
            )
            for row_index in range(first_row, last_row):
                item_id = self._order[row_index]
                top = row_index * self._row_height
                selected = item_id == self._selection
                self._body.create_rectangle(
                    0,
                    top,
                    content_width,
                    top + self._row_height,
                    fill=THEME["accent_dark"] if selected else THEME["surface"],
                    outline="",
                )
                values = self._items.get(item_id, ())
                cursor = 0
                for value_index, (_column, width, anchor) in enumerate(layout):
                    value = values[value_index] if value_index < len(values) else ""
                    text_x = cursor + (
                        width / 2
                        if anchor == "center"
                        else width - 10
                        if anchor == "e"
                        else 10
                    )
                    self._body.create_text(
                        text_x,
                        top + (self._row_height / 2),
                        text=self._ellipsize(value, width, font=self._font),
                        anchor="center"
                        if anchor == "center"
                        else "e"
                        if anchor == "e"
                        else "w",
                        fill="#ffffff" if selected else THEME["text"],
                        font=self._font,
                    )
                    cursor += width
            self._header.configure(
                scrollregion=(0, 0, content_width, self._header_height)
            )
            self._body.configure(scrollregion=(0, 0, content_width, content_height))
            self._body.xview_moveto(min(1.0, x_offset / max(1, content_width)))
            self._header.xview_moveto(min(1.0, x_offset / max(1, content_width)))
            self._body.yview_moveto(min(1.0, y_offset / max(1, content_height)))
        finally:
            self._redrawing = False

    def _schedule_redraw(self) -> None:
        """Coalesce resize/scroll storms into one redraw at the next idle turn."""
        if self._redraw_after_id is not None:
            return

        def redraw() -> None:
            self._redraw_after_id = None
            self._redraw()

        try:
            self._redraw_after_id = self.after_idle(redraw)
        except tk.TclError:
            self._redraw_after_id = None

    def _select_from_pointer(self, event: tk.Event[Any]) -> None:
        row = self.identify_row(event.y)
        if row:
            self.selection_set(row)
            self._body.focus_set()

    def _move_selection(self, amount: int) -> str:
        if not self._order:
            return "break"
        try:
            current = self._order.index(self._selection or "")
        except ValueError:
            current = 0 if amount >= 0 else len(self._order) - 1
        self.selection_set(
            self._order[max(0, min(len(self._order) - 1, current + amount))]
        )
        return "break"

    def _see(self, item: str) -> None:
        try:
            index = self._order.index(item)
        except ValueError:
            return
        content_height = max(1, len(self._order) * self._row_height)
        viewport = max(1, self._body.winfo_height())
        top, bottom = index * self._row_height, (index + 1) * self._row_height
        visible_top = self._body.canvasy(0)
        if top < visible_top:
            self._body.yview_moveto(top / content_height)
        elif bottom > visible_top + viewport:
            self._body.yview_moveto(max(0.0, (bottom - viewport) / content_height))
        self._schedule_redraw()

    def _scroll_pixels(self, dx: int, dy: int) -> str:
        if dy:
            content_height = max(
                self._body.winfo_height(), len(self._order) * self._row_height
            )
            self._body.yview_moveto(
                max(
                    0.0, min(1.0, self._body.yview()[0] + (dy / max(1, content_height)))
                )
            )
            self._schedule_redraw()
        if dx:
            content_width = max(
                self._body.winfo_width(),
                sum(width for _column, width, _anchor in self._layout_columns()),
            )
            scroll_target = max(
                0.0,
                min(1.0, self._body.xview()[0] + (dx / max(1, content_width))),
            )
            self.xview("moveto", scroll_target)
        return "break"

    def _bind_precision_scroll(
        self, target: tk.Misc, *, horizontal_only: bool = False
    ) -> None:
        def on_wheel(event: tk.Event[Any]) -> str:
            pixels = focus_wheel_pixels(getattr(event, "delta", 0))
            horizontal = horizontal_only or bool(getattr(event, "state", 0) & 0x0001)
            return self._scroll_pixels(
                pixels if horizontal else 0, 0 if horizontal else pixels
            )

        def on_touchpad(event: tk.Event[Any]) -> str:
            delta_x, delta_y = touchpad_scroll_deltas(self, getattr(event, "delta", 0))
            return self._scroll_pixels(
                focus_wheel_pixels(delta_x),
                0 if horizontal_only else focus_wheel_pixels(delta_y),
            )

        target.bind("<MouseWheel>", on_wheel, add="+")
        target.bind("<Shift-MouseWheel>", on_wheel, add="+")
        target.bind("<Button-4>", lambda _event: self._scroll_pixels(0, -36), add="+")
        target.bind("<Button-5>", lambda _event: self._scroll_pixels(0, 36), add="+")
        try:
            target.bind("<TouchpadScroll>", on_touchpad, add="+")
        except tk.TclError:
            pass


def _focus_library_table_item(
    table: PixelScrollTable,
    item: str,
) -> None:
    """Set logical row focus through the Library table contract."""
    table.focus_item(item)


class SleekScrollbar(tk.Canvas):
    """A narrow auto-hiding scrollbar without platform arrow chrome."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        command: Callable[..., Any],
        orient: str = "vertical",
        width: int = 8,
        thumb_color: str = THEME["border"],
        hover_color: str = THEME["subtle"],
    ) -> None:
        if orient not in {"vertical", "horizontal"}:
            raise ValueError(f"Unsupported scrollbar orientation: {orient}")
        self._orient = orient
        super().__init__(
            parent,
            width=width if orient == "vertical" else 1,
            height=width if orient == "horizontal" else 1,
            bg=THEME["bg"],
            bd=0,
            highlightthickness=0,
            takefocus=0,
            cursor="arrow",
        )
        self._command = command
        self._thumb_color = thumb_color
        self._hover_color = hover_color
        self._first = 0.0
        self._last = 1.0
        self._hovered = False
        self._drag_offset: float | None = None
        self.bind("<Configure>", lambda _event: self._redraw(), add="+")
        self.bind("<Enter>", self._set_hovered, add="+")
        self.bind("<Leave>", self._set_unhovered, add="+")
        self.bind("<Button-1>", self._begin_drag, add="+")
        self.bind("<B1-Motion>", self._drag, add="+")
        self.bind("<ButtonRelease-1>", self._end_drag, add="+")

    def set(self, first: str | float, last: str | float) -> None:
        try:
            self._first = max(0.0, min(1.0, float(first)))
            self._last = max(self._first, min(1.0, float(last)))
        except (TypeError, ValueError):
            self._first, self._last = 0.0, 1.0
        self._redraw()

    def _thumb_bounds(self) -> tuple[float, float] | None:
        length = max(
            1, self.winfo_height() if self._orient == "vertical" else self.winfo_width()
        )
        visible = max(0.0, min(1.0, self._last - self._first))
        if visible >= 0.999:
            return None
        thumb_length = min(float(length), max(28.0, length * visible))
        travel = max(1.0, length - thumb_length)
        scrollable = max(0.001, 1.0 - visible)
        start = travel * min(1.0, self._first / scrollable)
        return start, start + thumb_length

    def _redraw(self) -> None:
        try:
            self.delete("all")
            bounds = self._thumb_bounds()
            if bounds is None:
                return
            start, end = bounds
            color = self._hover_color if self._hovered else self._thumb_color
            if self._orient == "vertical":
                cross = max(2, self.winfo_width() // 2)
                self.create_line(
                    cross,
                    start + 3,
                    cross,
                    max(start + 3, end - 3),
                    fill=color,
                    width=4,
                    capstyle=tk.ROUND,
                )
            else:
                cross = max(2, self.winfo_height() // 2)
                self.create_line(
                    start + 3,
                    cross,
                    max(start + 3, end - 3),
                    cross,
                    fill=color,
                    width=4,
                    capstyle=tk.ROUND,
                )
        except tk.TclError:
            return

    def _set_hovered(self, _event: tk.Event[Any]) -> None:
        self._hovered = True
        self._redraw()

    def _set_unhovered(self, _event: tk.Event[Any]) -> None:
        self._hovered = False
        self._drag_offset = None
        self._redraw()

    def _begin_drag(self, event: tk.Event[Any]) -> None:
        bounds = self._thumb_bounds()
        if bounds is None:
            return
        start, end = bounds
        pointer = event.y if self._orient == "vertical" else event.x
        if start <= pointer <= end:
            self._drag_offset = pointer - start
            return
        self._drag_offset = (end - start) / 2
        self._move_thumb(pointer - self._drag_offset)

    def _drag(self, event: tk.Event[Any]) -> None:
        if self._drag_offset is not None:
            pointer = event.y if self._orient == "vertical" else event.x
            self._move_thumb(pointer - self._drag_offset)

    def _end_drag(self, _event: tk.Event[Any]) -> None:
        self._drag_offset = None

    def _move_thumb(self, top: float) -> None:
        bounds = self._thumb_bounds()
        if bounds is None:
            return
        length = max(
            1.0,
            float(
                self.winfo_height()
                if self._orient == "vertical"
                else self.winfo_width()
            ),
        )
        thumb_length = bounds[1] - bounds[0]
        travel = max(1.0, length - thumb_length)
        visible = max(0.0, min(1.0, self._last - self._first))
        first = max(
            0.0,
            min(1.0 - visible, (max(0.0, min(travel, top)) / travel) * (1.0 - visible)),
        )
        self._command("moveto", first)


class PillAction(tk.Canvas):
    """A compact rounded action surface for header utilities."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        textvariable: tk.StringVar,
        command: Callable[[], None],
        image: Any | None = None,
        width: int = 240,
        height: int = 34,
    ) -> None:
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=THEME["bg"],
            bd=0,
            highlightthickness=0,
            cursor="hand2",
            takefocus=1,
        )
        self._textvariable = textvariable
        self._command = command
        self._icon = image
        self._hovered = False
        self._background_image: Any | None = None
        self._background_item = self.create_image(0, 0, anchor="nw")
        self._icon_item = (
            self.create_image(15, height // 2, image=image, anchor="w")
            if image is not None
            else None
        )
        self._text_item = self.create_text(
            18 if image is None else 38,
            height // 2,
            text=textvariable.get(),
            fill=THEME["muted"],
            font=FONT_UI_SMALL,
            anchor="w",
        )
        textvariable.trace_add("write", lambda *_args: self._sync_text())
        self.bind("<Configure>", lambda _event: self._redraw(), add="+")
        self.bind("<Enter>", lambda _event: self._set_hover(True), add="+")
        self.bind("<Leave>", lambda _event: self._set_hover(False), add="+")
        self.bind("<Button-1>", lambda _event: self._command(), add="+")
        self.bind("<Return>", lambda _event: self._command(), add="+")
        self.bind("<space>", lambda _event: self._command(), add="+")
        self.after_idle(self._redraw)

    def _sync_text(self) -> None:
        try:
            self.itemconfigure(self._text_item, text=self._textvariable.get())
        except tk.TclError:
            pass

    def _set_hover(self, hovered: bool) -> None:
        self._hovered = hovered
        try:
            self.itemconfigure(
                self._text_item, fill=THEME["text"] if hovered else THEME["muted"]
            )
            self._redraw()
        except tk.TclError:
            pass

    def _redraw(self) -> None:
        try:
            width = max(1, self.winfo_width())
            height = max(1, self.winfo_height())
        except tk.TclError:
            return
        if Image is not None and ImageDraw is not None and ImageTk is not None:
            surface = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            ImageDraw.Draw(surface).rounded_rectangle(
                (0, 0, width - 1, height - 1),
                radius=min(17, height // 2),
                fill=THEME["surface_2"] if self._hovered else THEME["surface"],
                outline=THEME["border"],
                width=1,
            )
            self._background_image = ImageTk.PhotoImage(surface)
            self.itemconfigure(self._background_item, image=self._background_image)
            self.coords(self._background_item, 0, 0)
            self.tag_lower(self._background_item)
        if self._icon_item is not None:
            self.coords(self._icon_item, 15, height // 2)
        self.coords(self._text_item, 18 if self._icon is None else 38, height // 2)


class RoundedIconButton(tk.Canvas):
    """A Retina-friendly rounded icon control drawn with native canvas shapes."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        image: Any | None,
        text: str,
        command: Callable[[], None],
        primary: bool = False,
        width: int = 40,
        height: int = 40,
        radius: int = 8,
    ) -> None:
        resolved_width = width if image is not None else max(width, 76)
        super().__init__(
            parent,
            width=resolved_width,
            height=height,
            bg=THEME["bg"],
            bd=0,
            highlightthickness=0,
            takefocus=1,
            cursor="hand2",
        )
        self._button_image = image
        self._button_text = text
        self._command = command
        self._primary = primary
        self._radius = radius
        self._state = "normal"
        self._hovered = False
        self._pressed = False
        self._background_image: Any | None = None
        self._background_item = self.create_image(0, 0, anchor="nw")
        if image is not None:
            self._content_item = self.create_image(
                resolved_width // 2, height // 2, image=image, anchor="center"
            )
        else:
            self._content_item = self.create_text(
                resolved_width // 2,
                height // 2,
                text=text,
                fill="#ffffff" if primary else THEME["muted"],
                font=FONT_UI_SMALL_MEDIUM,
                anchor="center",
            )
        self.bind("<Configure>", lambda _event: self._redraw(), add="+")
        self.bind("<Enter>", lambda _event: self._set_hovered(True), add="+")
        self.bind("<Leave>", lambda _event: self._set_hovered(False), add="+")
        self.bind("<ButtonPress-1>", self._press, add="+")
        self.bind("<ButtonRelease-1>", self._release, add="+")
        self.bind("<Return>", lambda _event: self._invoke(), add="+")
        self.bind("<space>", lambda _event: self._invoke(), add="+")
        self.after_idle(self._redraw)

    def _custom_option_descriptor(
        self,
        option: str,
    ) -> tuple[str, str, str, str, str] | None:
        if option == "state":
            return ("state", "state", "State", "normal", self._state)
        if option == "text":
            return ("text", "text", "Text", "", self._button_text)
        return None

    def configure(
        self,
        cnf: str | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        if isinstance(cnf, str) and not kwargs:
            custom_descriptor = self._custom_option_descriptor(cnf)
            return (
                custom_descriptor
                if custom_descriptor is not None
                else super().configure(cnf)
            )
        if isinstance(cnf, str):
            return super().configure(cnf, **kwargs)
        if cnf is None and not kwargs:
            configured = super().configure()
            if not isinstance(configured, dict):
                return configured
            configured = dict(configured)
            state_descriptor = self._custom_option_descriptor("state")
            text_descriptor = self._custom_option_descriptor("text")
            if state_descriptor is not None:
                configured["state"] = state_descriptor
            if text_descriptor is not None:
                configured["text"] = text_descriptor
            return configured
        options = dict(cnf or {})
        options.update(kwargs)
        state = options.pop("state", None)
        if state is not None:
            self._state = str(state)
            if self._state == "disabled":
                self._hovered = False
                self._pressed = False
            super().configure(cursor="arrow" if self._state == "disabled" else "hand2")
        text = options.pop("text", None)
        if text is not None:
            self._button_text = str(text)
            if self._button_image is None:
                self.itemconfigure(self._content_item, text=self._button_text)
        result = super().configure(**options) if options else None
        self._redraw()
        return result

    config = configure

    def cget(self, key: str) -> Any:
        if key == "state":
            return self._state
        if key == "text":
            return self._button_text
        return super().cget(key)

    __getitem__ = cget

    def _set_hovered(self, hovered: bool) -> None:
        self._hovered = hovered and self._state != "disabled"
        if not hovered:
            self._pressed = False
        self._redraw()

    def _press(self, _event: tk.Event[Any]) -> None:
        if self._state != "disabled":
            self._pressed = True
            self._redraw()

    def _release(self, event: tk.Event[Any]) -> None:
        should_invoke = (
            self._state != "disabled"
            and self._pressed
            and 0 <= event.x < self.winfo_width()
            and 0 <= event.y < self.winfo_height()
        )
        self._pressed = False
        self._redraw()
        if should_invoke:
            self._command()

    def _invoke(self) -> None:
        if self._state != "disabled":
            self._command()

    def _redraw(self) -> None:
        try:
            disabled = self._state == "disabled"
            if self._primary:
                border = THEME["panel"] if disabled else THEME["accent"]
                if disabled:
                    fill = THEME["panel"]
                elif self._pressed:
                    fill = THEME["accent_dark"]
                elif self._hovered:
                    fill = "#8584ff"
                else:
                    fill = THEME["accent"]
            else:
                border = THEME["border"]
                fill = (
                    THEME["panel"]
                    if self._pressed
                    else THEME["surface_2"]
                    if self._hovered
                    else THEME["surface"]
                )
            width = max(1, self.winfo_width())
            height = max(1, self.winfo_height())
            if width <= 2 or height <= 2:
                return
            if Image is not None and ImageDraw is not None and ImageTk is not None:
                scale = 4
                surface = Image.new(
                    "RGBA", (width * scale, height * scale), THEME["bg"]
                )
                draw = ImageDraw.Draw(surface)
                radius = min(self._radius, height // 2) * scale
                draw.rounded_rectangle(
                    (0, 0, width * scale - 1, height * scale - 1),
                    radius=radius,
                    fill=border,
                )
                draw.rounded_rectangle(
                    (
                        scale,
                        scale,
                        width * scale - scale - 1,
                        height * scale - scale - 1,
                    ),
                    radius=max(0, radius - scale),
                    fill=fill,
                )
                resampling = getattr(Image, "Resampling", Image)
                surface = surface.resize((width, height), resampling.LANCZOS)
                self._background_image = ImageTk.PhotoImage(surface)
                self.itemconfigure(self._background_item, image=self._background_image)
                self.coords(self._background_item, 0, 0)
            else:
                self.itemconfigure(self._background_item, image="")
                self.delete("button-fallback")
                self.create_rectangle(
                    0,
                    0,
                    width - 1,
                    height - 1,
                    fill=fill,
                    outline=border,
                    tags="button-fallback",
                )
                self.tag_lower("button-fallback")
            self.tag_lower(self._background_item)
            self.coords(self._content_item, width // 2, height // 2)
        except tk.TclError:
            return


class SegmentedSelector(tk.Frame):
    """Small two-state selector with consistent rendering across Tk platforms."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        variable: tk.StringVar,
        values: tuple[str, ...] = (OutputType.MP4.value, OutputType.MP3.value),
        background: str = THEME["surface"],
        compact: bool = False,
    ) -> None:
        super().__init__(
            parent, bg=THEME["border"], bd=0, highlightthickness=0, padx=1, pady=1
        )
        self._variable = variable
        self._background = background
        self._labels: dict[str, tk.Label] = {}
        horizontal_padding = 7 if compact else 10
        vertical_padding = 3 if compact else 4
        for value in values:
            label = tk.Label(
                self,
                text=value,
                bg=background,
                fg=THEME["muted"],
                bd=0,
                highlightthickness=0,
                padx=horizontal_padding,
                pady=vertical_padding,
                font=FONT_UI_SMALL_MEDIUM,
                cursor="hand2",
                takefocus=1,
            )
            label.pack(side="left")
            label.bind("<Button-1>", partial(self._select_from_event, value))
            label.bind("<Return>", partial(self._select_from_event, value))
            label.bind("<space>", partial(self._select_from_event, value))
            label.bind(
                "<Enter>", partial(self._set_hover_from_event, value, True), add="+"
            )
            label.bind(
                "<Leave>", partial(self._set_hover_from_event, value, False), add="+"
            )
            self._labels[value] = label
        self._trace_id = variable.trace_add("write", lambda *_args: self._sync())
        self._sync()

    def tooltip_targets(self) -> tuple[tk.Label, ...]:
        """Use only the visible segments as tooltip hit zones, not the frame."""
        return tuple(self._labels.values())

    def _select_from_event(self, value: str, _event: tk.Event[tk.Label]) -> None:
        self._variable.set(value)

    def _set_hover_from_event(
        self,
        value: str,
        hovered: bool,
        _event: tk.Event[tk.Label],
    ) -> None:
        self._set_hover(value, hovered)

    def _set_hover(self, value: str, hovered: bool) -> None:
        if self._variable.get() == value:
            return
        label = self._labels.get(value)
        if label is not None:
            label.configure(
                bg=THEME["surface_2"] if hovered else self._background,
                fg=THEME["text"] if hovered else THEME["muted"],
            )

    def _sync(self) -> None:
        selected = self._variable.get()
        for value, label in self._labels.items():
            active = value == selected
            label.configure(
                bg=THEME["accent_dark"] if active else self._background,
                fg="#ffffff" if active else THEME["muted"],
            )

    def destroy(self) -> None:
        try:
            self._variable.trace_remove("write", self._trace_id)
        except (tk.TclError, AttributeError, ValueError):
            pass
        super().destroy()
