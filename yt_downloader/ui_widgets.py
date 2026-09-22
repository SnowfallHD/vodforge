from __future__ import annotations

import sys
import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Iterable, Mapping
from functools import partial
from pathlib import Path
from tkinter import ttk
from typing import Any, Literal, Protocol, cast

from . import ui_scrolling as _scrolling
from .choice_popover import ChoicePopover
from .models import OutputType
from .ui_chrome import (
    RoundedFieldBorder,
    accent_hover_color,
    field_border_image,
    prototype_entry_style,
)
from .ui_layout import (
    compact_destination_path,
    ellipsize_wrapped_text,
    pixel_table_visible_row_window,
    resized_table_column_width,
    responsive_table_stretch_indices,
    stretched_table_column_widths,
    window_logical_metrics,
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

    def open(self, path: str | Path) -> Any: ...


class _ImageDrawModule(Protocol):
    def Draw(self, image: Any) -> Any: ...


class _ImageTkModule(Protocol):
    def PhotoImage(self, image: Any, **kwargs: Any) -> Any: ...


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


def set_user_scroll_locked(scroller: Any, locked: bool) -> None:
    """Record whether a live log reader has taken viewport ownership."""
    scroller._vodforge_user_scroll_locked = locked


touchpad_scroll_deltas = _scrolling.touchpad_scroll_deltas


def bind_smooth_vertical_wheel(
    scroller: Any,
    *targets: tk.Misc,
    mode: str = "pixels",
    row_pixels: int = 30,
) -> None:
    """Compatibility entrance to the shared owned scrolling implementation."""
    _scrolling.bind_smooth_scroll(scroller, *targets, mode=mode, row_pixels=row_pixels)


def reveal_toplevel(popup: tk.Toplevel, geometry: str) -> None:
    """Place a hidden custom window before mapping it to avoid visible jumps."""
    popup.geometry(geometry)
    popup.deiconify()
    popup.lift()


class ProductEntry(ttk.Entry):
    """Native editing semantics with product-owned rounded field chrome."""

    def __init__(self, parent: tk.Misc, **kwargs: Any) -> None:
        super().__init__(
            parent,
            style=prototype_entry_style(parent),
            font=window_logical_metrics(parent).font(FONT_UI),
            **kwargs,
        )

    def apply_theme(self) -> None:
        # The interpreter's ProductChromeOwner updates shared images in place.
        self.configure(style=prototype_entry_style(self))


def _ui_icon_path(name: str) -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    root = Path(frozen_root) if frozen_root else Path(__file__).resolve().parents[1]
    return root / "assets" / "icons" / "lucide" / f"{name}.png"


class _KeyboardRouter:
    """One dispatch per keypress within one real toplevel."""

    def __init__(self, top: Any) -> None:
        self.top = top
        self.scopes: list[KeyboardScope] = []
        self.bindings: dict[str, str] = {}

    def register(self, scope: KeyboardScope) -> None:
        self.scopes.append(scope)
        for sequence in scope.actions:
            if sequence not in self.bindings:
                self.bindings[sequence] = self.top.bind(
                    sequence,
                    lambda event, key=sequence: self.dispatch(key, event),
                    add="+",
                )

    def remove(self, scope: KeyboardScope) -> None:
        if scope in self.scopes:
            self.scopes.remove(scope)
        for sequence, token in tuple(self.bindings.items()):
            if not any(sequence in item.actions for item in self.scopes):
                try:
                    self.top.unbind(sequence, token)
                except tk.TclError:
                    pass
                del self.bindings[sequence]

    def dispatch(self, sequence: str, event: Any) -> str | None:
        candidates = []
        for position, scope in enumerate(tuple(self.scopes)):
            distance = scope.distance(event.widget)
            if sequence in scope.actions and distance is not None:
                candidates.append((distance, -position, scope))
        for _, _, scope in sorted(candidates, key=lambda item: item[:2]):
            try:
                editing = event.widget.winfo_class() in {
                    "Entry",
                    "TEntry",
                    "Text",
                    "Listbox",
                    "TCombobox",
                    "Spinbox",
                    "TSpinbox",
                }
                if editing and sequence not in scope.editing:
                    return None
                # Capture exactly one action before it can destroy/pop another scope.
                action = scope.actions[sequence]
                action()
                return "break"
            except tk.TclError:
                return "break"
        return None


class KeyboardScope:
    """Shortcuts scoped by widget ancestry, visibility and real modal ownership."""

    def __init__(
        self,
        owner: tk.Misc,
        actions: Mapping[str, Callable[[], Any]],
        *,
        editing: Iterable[str] = ("<Escape>",),
        top_level_fallback: bool = False,
    ) -> None:
        self.owner = owner
        self.actions = dict(actions)
        self.editing = frozenset(editing)
        self.top_level_fallback = top_level_fallback
        self.closed = False
        top: Any = owner.winfo_toplevel()
        router = getattr(top, "_vodforge_keyboard_router", None)
        if router is None:
            router = _KeyboardRouter(top)
            top._vodforge_keyboard_router = router
        self.router = router
        router.register(self)
        self.destroy_binding = owner.bind("<Destroy>", self._destroyed, add="+")

    def distance(self, widget: Any) -> int | None:
        if self.closed:
            return None
        try:
            if not self.owner.winfo_ismapped():
                return None
            grab = self.owner.grab_current()
            if (
                grab is not None
                and grab.winfo_toplevel() is not self.owner.winfo_toplevel()
            ):
                return None
        except tk.TclError:
            return None
        distance = 0
        current = widget
        while current is not None:
            if current is self.owner:
                return distance
            current = getattr(current, "master", None)
            distance += 1
        return 10000 if self.top_level_fallback else None

    def _destroyed(self, event: Any) -> None:
        if event.widget is self.owner:
            self.close()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.router.remove(self)
        try:
            self.owner.unbind("<Destroy>", self.destroy_binding)
        except tk.TclError:
            pass


class PlaceholderEntry(ProductEntry):
    """An empty-field hint, never stored as content, with an unobscured caret."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        textvariable: tk.StringVar,
        placeholder: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, textvariable=textvariable, **kwargs)
        self._placeholder_disposed = False
        self._placeholder_variable = textvariable
        self._placeholder = tk.Label(
            self,
            text=placeholder,
            font=self.cget("font"),
            fg=THEME["subtle"],
            bg=THEME["surface"],
            bd=0,
            padx=0,
            pady=0,
            cursor="xterm",
        )
        self._placeholder.bind("<Button-1>", self._focus_placeholder)
        self._placeholder_trace = textvariable.trace_add(
            "write", self._sync_placeholder
        )
        self.bind("<Configure>", self._sync_placeholder, add="+")
        self.bind("<FocusIn>", self._sync_placeholder, add="+")
        self.bind("<FocusOut>", self._sync_placeholder, add="+")
        self.bind("<Destroy>", self._dispose_placeholder, add="+")
        self._sync_placeholder()

    def _focus_placeholder(self, _event: Any) -> str:
        if self._placeholder_disposed:
            return "break"
        self.focus_set()
        self.icursor(0)
        return "break"

    def _sync_placeholder(self, *_args: Any) -> None:
        if self._placeholder_disposed:
            return
        self._placeholder.configure(
            font=self.cget("font"),
            bg=THEME["focus_surface"] if self.focus_get() is self else THEME["surface"],
        )
        if self._placeholder_variable.get():
            self._placeholder.place_forget()
        else:
            self._placeholder.place(
                x=window_logical_metrics(self).px(18), rely=0.5, anchor="w"
            )

    def _dispose_placeholder(self, event: Any) -> None:
        if event.widget is self and not self._placeholder_disposed:
            self._placeholder_disposed = True
            try:
                self._placeholder_variable.trace_remove(
                    "write", self._placeholder_trace
                )
            except tk.TclError:
                pass
            self.__dict__.pop("_placeholder_variable", None)

    def apply_theme(self) -> None:
        if self._placeholder_disposed:
            return
        super().apply_theme()
        self._placeholder.configure(fg=THEME["subtle"])
        self._sync_placeholder()


def _tinted_ui_icon(
    name: str,
    *,
    size: tuple[int, int],
    color: str,
    widget: tk.Misc | None = None,
) -> Any | None:
    """Load one bundled Lucide glyph at its owning window backing density."""

    if Image is None or ImageTk is None:
        return None
    try:
        from .platform_services import create_surface_image, surface_backing_scale

        density = surface_backing_scale(widget) if widget is not None else 1
        physical_size = (size[0] * density, size[1] * density)
        with Image.open(_ui_icon_path(name)) as source:
            alpha = source.convert("RGBA").getchannel("A")
            resampling = getattr(Image, "Resampling", Image)
            alpha = alpha.resize(physical_size, resampling.LANCZOS)
        rendered = Image.new("RGBA", physical_size, color)
        rendered.putalpha(alpha)
        if widget is not None:
            return create_surface_image(widget, rendered, density, logical_size=size)[0]
        return ImageTk.PhotoImage(rendered)
    except (OSError, ValueError, tk.TclError):
        return None


class ChoiceMenu(tk.Canvas):
    """Shared theme-owned menu rows; no platform Listbox rendering."""

    def __init__(self, parent: tk.Misc, values: tuple[str, ...]) -> None:
        self._metrics = window_logical_metrics(parent)
        self._font = self._metrics.font(FONT_UI)
        self.values = values
        self.selected = 0
        self.top = 0
        self.rows = min(8, len(values))
        self.row_height = self._metrics.px(34)
        self._paint_snapshot: tuple[Any, ...] | None = None
        font = tkfont.Font(font=self._font)
        width = max(
            (font.measure(value) for value in values), default=self._metrics.px(80)
        ) + self._metrics.px(52)
        super().__init__(
            parent,
            width=width,
            height=self.rows * self.row_height + self._metrics.px(12),
            bg=THEME["bg"],
            highlightthickness=0,
            bd=0,
            takefocus=True,
        )
        self.bind("<Configure>", lambda _e: self._paint())
        self.bind("<Motion>", self._hover)
        # Pointer entry need not deliver Motion before a click (or touch).
        self.bind("<ButtonPress-1>", self._hover)
        self.bind("<Up>", lambda _e: self._move(-1))
        self.bind("<Down>", lambda _e: self._move(1))
        self.bind("<Home>", lambda _e: self._move(-len(self.values)))
        self.bind("<End>", lambda _e: self._move(len(self.values)))
        self.bind("<MouseWheel>", lambda e: self._move(-1 if e.delta > 0 else 1))
        self.bind("<Button-4>", lambda _e: self._move(-1))
        self.bind("<Button-5>", lambda _e: self._move(1))

    def _move(self, amount: int) -> str:
        self.selection_set(max(0, min(len(self.values) - 1, self.selected + amount)))
        self.see(self.selected)
        return "break"

    def index_at(self, x: int, y: int) -> int | None:
        if not 0 <= x < self.winfo_width():
            return None
        index = self.top + (y - self._metrics.px(6)) // self.row_height
        if self.top <= index < min(len(self.values), self.top + self.rows):
            return index
        return None

    def _hover(self, event: tk.Event) -> None:
        index = self.index_at(event.x, event.y)
        if index is not None:
            self.selection_set(index)

    def selection_set(self, index: int) -> None:
        self.selected = max(0, min(len(self.values) - 1, int(index)))
        self._paint()

    def selection_clear(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def curselection(self) -> tuple[int, ...]:
        return (self.selected,)

    def get(self, index: int) -> str:
        return self.values[index]

    def see(self, index: int) -> None:
        self.top = (
            max(0, min(self.top, index))
            if index < self.top
            else max(self.top, index - self.rows + 1)
        )
        self._paint()

    def _paint(self) -> None:
        from PIL import ImageTk

        width = max(self.winfo_width(), self.winfo_reqwidth())
        height = self.rows * self.row_height + self._metrics.px(12)
        snapshot = (width, height, self.selected, self.top, tuple(THEME.items()))
        if snapshot == self._paint_snapshot:
            return
        self._paint_snapshot = snapshot
        from .ui_chrome import ttk_surface_image

        surface = ttk_surface_image(
            width,
            height=height,
            fill=THEME["surface_2"],
            edge=THEME["border"],
            depth=0.55,
            unit_scale=self._metrics.scale,
        )
        row = self.selected - self.top
        if 0 <= row < self.rows:
            y = self._metrics.px(6) + row * self.row_height
            selected = ttk_surface_image(
                width - self._metrics.px(10),
                height=self.row_height,
                fill=THEME["accent_surface"],
                edge=THEME["border"],
                recessed=True,
                depth=0.6,
                unit_scale=self._metrics.scale,
            )
            surface.alpha_composite(selected, (self._metrics.px(5), y))
        self._menu_image = ImageTk.PhotoImage(surface, master=self)
        self.delete("all")
        self.create_image(0, 0, image=self._menu_image, anchor="nw")
        for row, index in enumerate(
            range(self.top, min(len(self.values), self.top + self.rows))
        ):
            label = self.values[index]
            font = tkfont.Font(font=self._font)
            available = max(0, width - self._metrics.px(36))
            if font.measure(label) > available:
                low, high = 0, len(label)
                while low < high:
                    mid = (low + high + 1) // 2
                    if font.measure(label[:mid] + "…") <= available:
                        low = mid
                    else:
                        high = mid - 1
                label = label[:low] + "…"
            self.create_text(
                self._metrics.px(18),
                self._metrics.px(6) + row * self.row_height + self.row_height / 2,
                text=label,
                anchor="w",
                fill=THEME["text"],
                font=self._font,
            )

    def apply_theme(self) -> None:
        self.configure(bg=THEME["bg"])
        self._paint_snapshot = None
        self._paint()


class ChoiceDropdown(tk.Frame):
    """VODForge-owned choice field with a cohesive, platform-neutral popover."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        textvariable: tk.StringVar,
        values: Iterable[object],
        state: str = "readonly",
        width: int = 20,
        inline: bool = False,
    ) -> None:
        super().__init__(
            parent,
            bg=THEME["surface"],
            bd=0,
            highlightthickness=0,
            highlightbackground=THEME["border"],
            highlightcolor=THEME["border"],
            takefocus=1,
        )
        self._metrics = window_logical_metrics(self)
        self._disposed = False
        self.variable = textvariable
        self._values = tuple(str(value) for value in values)
        self._state = str(state)
        self._width = 0 if inline else max(4, int(width))
        self._inline = inline
        self._hovered = False
        self._popover: ChoicePopover | None = None
        self._chevron_image: Any | None = None

        if self._state == "normal":
            self._field: tk.Label | tk.Entry = tk.Entry(
                self,
                textvariable=textvariable,
                width=self._width,
                bg=THEME["surface"],
                fg=THEME["text"],
                insertbackground=THEME["text"],
                selectbackground=THEME["accent_dark"],
                relief="flat",
                bd=0,
                highlightthickness=0,
                font=self._metrics.font(FONT_UI),
            )
        else:
            self._field = tk.Label(
                self,
                textvariable=textvariable,
                width=self._width,
                anchor="w",
                bg=THEME["surface"],
                fg=THEME["text"],
                bd=0,
                highlightthickness=0,
                font=self._metrics.font(FONT_UI),
            )
        self.columnconfigure(0, weight=1)
        self._field.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(self._metrics.px(10), self._metrics.px(2)),
            pady=self._metrics.px(8),
        )

        self._chevron = tk.Canvas(
            self,
            width=self._metrics.px(18),
            height=self._metrics.px(18),
            bg=THEME["surface"],
            bd=0,
            highlightthickness=0,
            takefocus=False,
        )
        self._chevron.grid(
            row=0, column=1, padx=(self._metrics.px(2), self._metrics.px(8))
        )
        self._chevron_item = self._chevron.create_image(
            self._metrics.px(9), self._metrics.px(9), anchor="center"
        )

        for widget in (self, self._field, self._chevron):
            widget.bind("<Enter>", lambda _event: self._set_hovered(True), add="+")
            widget.bind("<Leave>", lambda _event: self._set_hovered(False), add="+")
        self.bind("<FocusIn>", lambda _event: self._sync_border(), add="+")
        self.bind("<FocusOut>", lambda _event: self._sync_border(), add="+")
        self._field.bind("<FocusIn>", lambda _event: self._sync_border(), add="+")
        self._field.bind("<FocusOut>", lambda _event: self._sync_border(), add="+")
        self.bind("<Return>", self._open_from_event, add="+")
        self.bind("<space>", self._open_from_event, add="+")
        self.bind("<Down>", self._open_from_event, add="+")
        self._chevron.bind("<Button-1>", self._open_from_event, add="+")
        if self._state != "normal":
            self._field.bind("<Button-1>", self._open_from_event, add="+")
        self.bind("<Destroy>", self._destroyed, add="+")
        self._chrome = None if inline else RoundedFieldBorder(self)
        if self._state != "normal":
            self.bind("<Button-1>", self._open_from_event, add="+")
            if self._chrome is not None:
                self._chrome.canvas.bind("<Button-1>", self._open_from_event, add="+")
        self._render_chevron()

    def _custom_option(self, key: str) -> Any:
        if key == "values":
            return self._values
        if key == "state":
            return self._state
        if key == "width":
            return self._width
        if key == "textvariable":
            return self.variable
        raise KeyError(key)

    def configure(
        self,
        cnf: str | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        if isinstance(cnf, str) and not kwargs:
            try:
                return self._custom_option(cnf)
            except KeyError:
                return super().configure(cnf)
        if isinstance(cnf, str):
            return super().configure(cnf, **kwargs)
        if cnf is None and not kwargs:
            return super().configure()
        options = dict(cnf or {})
        options.update(kwargs)
        if "values" in options:
            values = tuple(str(value) for value in options.pop("values"))
            if values != self._values:
                # The menu is a snapshot of these options. Retire it before an
                # already queued selection can commit against a new choice set.
                self._close_popover()
                self._values = values
        if "width" in options:
            self._width = max(4, int(options.pop("width")))
            self._field.configure(width=self._width)
        if "state" in options:
            self._state = str(options.pop("state"))
            if self._state == "disabled":
                self._close_popover()
            if isinstance(self._field, tk.Entry):
                self._field.configure(
                    state="normal" if self._state == "normal" else "disabled"
                )
        result = super().configure(**options) if options else None
        self._sync_palette()
        return result

    config = configure

    def cget(self, key: str) -> Any:
        try:
            return self._custom_option(key)
        except KeyError:
            return super().cget(key)

    __getitem__ = cget

    def get(self) -> str:
        return self.variable.get()

    def set(self, value: object) -> None:
        self.variable.set(str(value))

    def selection_clear(self, **_kwargs: Any) -> None:
        if isinstance(self._field, tk.Entry):
            self._field.selection_clear()

    def state(self, statespec: Iterable[str] | None = None) -> tuple[str, ...]:
        if statespec is None:
            return ("disabled",) if self._state == "disabled" else ()
        requested = tuple(statespec)
        if "disabled" in requested:
            self.configure(state="disabled")
        elif "!disabled" in requested:
            self.configure(state="readonly")
        return self.state()

    def _open_from_event(self, _event: tk.Event[Any]) -> str:
        self.focus_set()
        self.open_popover()
        return "break"

    def open_popover(self) -> None:
        if self._disposed:
            return
        if self._state == "disabled" or not self._values:
            return
        if self._popover is not None:
            self._close_popover()
            return
        popup = ChoicePopover(self, self._close_popover, bg=THEME["bg"])
        listbox = ChoiceMenu(popup, self._values)
        listbox.pack(fill="both", expand=True)
        try:
            selected_index = self._values.index(self.variable.get())
        except ValueError:
            selected_index = 0
        listbox.selection_set(selected_index)
        listbox.see(selected_index)
        listbox.bind(
            "<ButtonRelease-1>",
            lambda event: self._commit_listbox(listbox, event),
            add="+",
        )
        listbox.bind("<Return>", lambda _event: self._commit_listbox(listbox), add="+")
        listbox.bind(
            "<Escape>",
            lambda _event: self._close_popover(restore_focus=True),
            add="+",
        )
        popup.update_idletasks()
        self._popover = popup
        if not popup.reposition():
            return
        popup.lift()
        # Tk cannot focus an unmapped child. Complete layout before handing
        # focus to the menu, or the pending old-field FocusOut closes it again.
        popup.update_idletasks()
        listbox.focus_set()
        popup.watch()
        self._sync_border()

    def _commit_listbox(
        self, listbox: ChoiceMenu, event: tk.Event[Any] | None = None
    ) -> str:
        # A queued callback must still belong to the enabled, current surface.
        if self._state == "disabled" or listbox.master is not self._popover:
            return "break"
        if event is not None:
            index = listbox.index_at(event.x, event.y)
            if index is None:
                self._close_popover(restore_focus=True)
                return "break"
            listbox.selection_set(index)
        selection = listbox.curselection()
        if selection:
            self.variable.set(str(listbox.get(selection[0])))
            self.event_generate("<<ComboboxSelected>>", when="tail")
        self._close_popover(restore_focus=True)
        return "break"

    def _close_popover(self, *, restore_focus: bool = False) -> None:
        popup, self._popover = self._popover, None
        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass
        if restore_focus and self.winfo_viewable() and self._state != "disabled":
            self.focus_set()
        self._sync_border()

    def _set_hovered(self, hovered: bool) -> None:
        self._hovered = bool(hovered)
        self._sync_palette()

    def _sync_border(self) -> None:
        try:
            focused_widget = self.focus_get()
            focused = focused_widget in {self, self._field} or self._popover is not None
            background = (
                THEME["focus_surface"]
                if focused and self._state != "disabled"
                else THEME["surface"]
            )
            super().configure(bg=background)
            self._field.configure(bg=background)
            self._chevron.configure(bg=background)
            if self._chrome is not None:
                self._chrome.request(
                    focused, self._hovered and self._state != "disabled"
                )
        except tk.TclError:
            pass

    def _render_chevron(self) -> None:
        self._chevron_image = _tinted_ui_icon(
            "chevron-down",
            size=(self._metrics.px(14), self._metrics.px(14)),
            color=THEME["subtle"] if self._state == "disabled" else THEME["muted"],
        )
        if self._chevron_image is not None:
            self._chevron.itemconfigure(self._chevron_item, image=self._chevron_image)
        else:  # pragma: no cover - packaged runtime includes Pillow and assets
            self._chevron.delete("fallback")
            self._chevron.create_line(
                [self._metrics.px(n) for n in (4, 7, 9, 12, 14, 7)],
                fill=THEME["muted"],
                width=self._metrics.px(2),
                tags="fallback",
            )

    def _sync_palette(self) -> None:
        try:
            disabled = self._state == "disabled"
            # Hover changes the shared field's inset contour, not its face
            # color. Keyboard focus remains the separately visible state.
            background = THEME["surface"]
            foreground = THEME["subtle"] if disabled else THEME["text"]
            super().configure(bg=background)
            self._field.configure(bg=background, fg=foreground)
            self._chevron.configure(bg=background)
            self._render_chevron()
            self._sync_border()
        except tk.TclError:
            pass

    def apply_theme(self) -> None:
        self._sync_palette()

    def _destroyed(self, event: tk.Event[Any]) -> None:
        if event.widget is self and not self._disposed:
            self._disposed = True
            self._close_popover()
            self._chevron_image = None
            self.__dict__.pop("variable", None)


class ModernCheckbox(tk.Frame):
    """Consistent checkmark control without native X-style platform chrome."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        text: str,
        variable: tk.BooleanVar,
        command: Callable[[], object] | None = None,
    ) -> None:
        self._metrics = window_logical_metrics(parent)
        super().__init__(
            parent,
            bg=THEME["bg"],
            bd=0,
            highlightthickness=self._metrics.px(1),
            highlightbackground=THEME["bg"],
            takefocus=1,
            cursor="hand2",
        )
        self._disposed = False
        self.variable = variable
        self._text = str(text)
        self._command = command
        self._state = "normal"
        self._hovered = False
        self._pointer_admission: tuple[object, object] | None = None
        self._check_image: Any | None = None
        self._last_render_snapshot: tuple[object, ...] | None = None
        self._box = tk.Canvas(
            self,
            width=self._metrics.px(18),
            height=self._metrics.px(18),
            bg=THEME["bg"],
            bd=0,
            highlightthickness=0,
        )
        self._box.pack(side="left", padx=(0, self._metrics.px(7)))
        self._label = tk.Label(
            self,
            text=self._text,
            bg=THEME["bg"],
            fg=THEME["text"],
            font=self._metrics.font(FONT_UI),
            bd=0,
            highlightthickness=0,
        )
        self._label.pack(side="left")
        for widget in (self, self._box, self._label):
            widget.bind("<Button-1>", self._pointer_press, add="+")
            widget.bind("<ButtonRelease-1>", self._pointer_release, add="+")
            widget.bind("<Enter>", lambda _event: self._set_hovered(True), add="+")
            widget.bind("<Leave>", lambda _event: self._set_hovered(False), add="+")
        self.bind("<Return>", self._toggle_from_event, add="+")
        self.bind("<space>", self._toggle_from_event, add="+")
        self.bind("<FocusIn>", lambda _event: self._render(), add="+")
        self.bind("<FocusOut>", lambda _event: self._render(), add="+")
        self._trace_id = variable.trace_add("write", lambda *_args: self._render())
        self.bind("<Destroy>", self._destroyed, add="+")
        self.bind("<Unmap>", self._retire_pointer, add="+")
        self._render()

    def state(self, statespec: Iterable[str] | None = None) -> tuple[str, ...]:
        if statespec is None:
            return ("disabled",) if self._state == "disabled" else ()
        requested = tuple(statespec)
        if "disabled" in requested:
            self._pointer_admission = None
            self._state = "disabled"
        elif "!disabled" in requested:
            self._state = "normal"
        self._render()
        return self.state()

    def configure(
        self,
        cnf: str | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        if isinstance(cnf, str) and not kwargs:
            if cnf == "state":
                return self._state
            if cnf == "text":
                return self._text
            return super().configure(cnf)
        if isinstance(cnf, str):
            return super().configure(cnf, **kwargs)
        if cnf is None and not kwargs:
            return super().configure()
        options = dict(cnf or {})
        options.update(kwargs)
        if "state" in options:
            self._state = str(options.pop("state"))
            if self._state == "disabled":
                self._pointer_admission = None
        if "text" in options:
            self._text = str(options.pop("text"))
            self._label.configure(text=self._text)
        result = super().configure(**options) if options else None
        self._render()
        return result

    config = configure

    def _retire_pointer(self, _event: Any = None) -> None:
        self._pointer_admission = None

    def _pointer_press(self, _event: tk.Event[Any]) -> str:
        if self._disposed:
            return "break"
        self._pointer_admission = (
            (self.variable, self._command) if self._state != "disabled" else None
        )
        self.focus_set()
        return "break"

    def _pointer_release(self, event: tk.Event[Any]) -> str:
        if self._disposed:
            return "break"
        admitted, self._pointer_admission = self._pointer_admission, None
        # Events originate from the frame, checkmark canvas or text label.
        x = event.widget.winfo_rootx() + event.x - self.winfo_rootx()
        y = event.widget.winfo_rooty() + event.y - self.winfo_rooty()
        if (
            admitted == (self.variable, self._command)
            and self._state != "disabled"
            and self.winfo_viewable()
            and 0 <= x < self.winfo_width()
            and 0 <= y < self.winfo_height()
        ):
            self._toggle_from_event(event)
        return "break"

    def _toggle_from_event(self, _event: tk.Event[Any]) -> str:
        if not self._disposed and self._state != "disabled":
            self.variable.set(not bool(self.variable.get()))
            if self._command is not None:
                self._command()
            self.focus_set()
        return "break"

    def _set_hovered(self, hovered: bool) -> None:
        self._hovered = bool(hovered) and self._state != "disabled"
        self._render()

    def _render(self) -> None:
        if self._disposed:
            return
        try:
            selected = bool(self.variable.get())
            disabled = self._state == "disabled"
            focused = self.focus_get() is self
            snapshot = (
                selected,
                disabled,
                focused,
                self._hovered,
                self._text,
                tuple(THEME.items()),
            )
            if snapshot == self._last_render_snapshot:
                return
            background = THEME["bg"]
            border = (
                THEME["subtle"]
                if disabled
                else THEME["selection"]
                if selected
                else THEME["border"]
            )
            fill = (
                THEME["accent_dark"] if selected and not disabled else THEME["surface"]
            )
            super().configure(
                bg=background,
                cursor="arrow" if disabled else "hand2",
                highlightthickness=0,
                highlightbackground=background,
            )
            self._box.configure(bg=background, cursor="arrow" if disabled else "hand2")
            self._label.configure(
                bg=background,
                fg=THEME["subtle"] if disabled else THEME["text"],
                cursor="arrow" if disabled else "hand2",
            )
            self._box.delete("all")
            from .ui_chrome import ttk_surface_image

            if ImageTk is not None:
                from .platform_services import (
                    create_surface_image,
                    surface_backing_scale,
                )

                size = self._metrics.px(16)
                density = surface_backing_scale(self)
                bitmap = ttk_surface_image(
                    size,
                    fill=fill,
                    edge=THEME["focus"] if focused else border,
                    recessed=selected or self._hovered,
                    depth=0.2 if disabled else 0.62 if self._hovered else 0.75,
                    radius=4,
                    density=density,
                    unit_scale=self._metrics.scale,
                )
                self._box_surface, _ = create_surface_image(
                    self,
                    bitmap,
                    density,
                    logical_size=(size, size),
                    existing=getattr(self, "_box_surface", None),
                )
                self._box.create_image(
                    self._metrics.px(1),
                    self._metrics.px(1),
                    image=self._box_surface,
                    anchor="nw",
                )
            else:
                self._box.create_rectangle(
                    *(self._metrics.px(n) for n in (2, 2, 16, 16)),
                    fill=fill,
                    outline=border,
                )
            if selected:
                self._check_image = _tinted_ui_icon(
                    "check",
                    size=(self._metrics.px(12), self._metrics.px(12)),
                    widget=self,
                    color=THEME["selection"] if not disabled else THEME["subtle"],
                )
                if self._check_image is not None:
                    self._box.create_image(
                        self._metrics.px(9),
                        self._metrics.px(9),
                        image=self._check_image,
                    )
            self._last_render_snapshot = snapshot
        except tk.TclError:
            return

    def apply_theme(self) -> None:
        self._render()

    def _destroyed(self, event: tk.Event[Any]) -> None:
        if event.widget is not self or self._disposed:
            return
        self._disposed = True
        try:
            self.variable.trace_remove("write", self._trace_id)
        except (tk.TclError, AttributeError, ValueError):
            pass
        self._pointer_admission = None
        self._command = None
        self._check_image = None
        self.__dict__.pop("variable", None)


class ActionDialogSurface:
    """Keep essential dialog state and actions outside compressible body content.

    The protected status region and footer are siblings of the body, never its
    children. Most dialogs receive a normal adaptive frame. A body scrollbar is
    an explicit exception for feature-dense document surfaces such as Settings.
    """

    def __init__(
        self,
        popup: tk.Misc,
        *,
        padx: int = 24,
        pady: int = 22,
        footer_gap: int = 18,
        allow_body_scroll: bool = False,
        protect_status: bool = False,
        modal: bool = False,
    ) -> None:
        metrics = window_logical_metrics(popup)
        padx, pady, footer_gap = map(metrics.px, (padx, pady, footer_gap))
        self._previous_focus = popup.focus_get() if modal else None
        self._previous_grab = popup.grab_current() if modal else None
        self._modal = modal
        if modal:
            popup.grab_set()
            popup.bind("<Destroy>", self._dialog_destroyed, add="+")
        shell = ttk.Frame(popup, style="FocusShell.TFrame")
        shell.pack(fill="both", expand=True, padx=padx, pady=pady)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)

        viewport: tk.Canvas | None = None
        scrollbar: SleekScrollbar | None = None
        body_window: int | None = None
        if allow_body_scroll:
            viewport = tk.Canvas(
                shell,
                bg=THEME["bg"],
                bd=0,
                highlightthickness=0,
                takefocus=False,
            )
            viewport.grid(row=0, column=0, sticky="nsew")
            scrollbar = SleekScrollbar(
                shell,
                command=viewport.yview,
            )
            scrollbar.grid(row=0, column=1, sticky="ns", padx=(metrics.px(8), 0))
            scrollbar.grid_remove()
            viewport.configure(yscrollcommand=scrollbar.set)
            body = ttk.Frame(viewport, style="FocusShell.TFrame")
            body_window = viewport.create_window((0, 0), window=body, anchor="nw")
            viewport.bind("<Configure>", self._viewport_resized, add="+")
            body.bind("<Configure>", self._body_resized, add="+")
            body.bind("<Map>", self._body_resized, add="+")
            body.bind("<Destroy>", self._body_destroyed, add="+")
            # Descendant controls receive pointer/trackpad events under Tk's
            # toplevel bindtag; binding the popup keeps the scroll owner local
            # while covering the complete Settings document surface.
            bind_smooth_vertical_wheel(viewport, viewport, body, popup, mode="pixels")
        else:
            body = ttk.Frame(shell, style="FocusShell.TFrame")
            body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)

        status: ttk.Frame | None = None
        footer_row = 1
        if protect_status:
            status = ttk.Frame(shell, style="FocusShell.TFrame")
            status.grid(
                row=1, column=0, columnspan=2, sticky="ew", pady=(footer_gap, 0)
            )
            status.columnconfigure(0, weight=1)
            footer_row = 2

        footer = ttk.Frame(shell, style="FocusShell.TFrame")
        footer.grid(
            row=footer_row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(footer_gap, 0),
        )

        self.popup = popup
        self.shell = shell
        self.viewport = viewport
        self.scrollbar = scrollbar
        self.body = body
        self.status = status
        self.footer = footer
        self._body_window = body_window
        self._body_width_pending: str | None = None

    def _dialog_destroyed(self, event: Any) -> None:
        if event.widget is not self.popup or not self._modal:
            return
        previous, self._previous_grab = self._previous_grab, None
        focus, self._previous_focus = self._previous_focus, None
        self._modal = False
        try:
            current = self.popup.grab_current()
            if current is self.popup:
                self.popup.grab_release()
            # A successor modal owns both grab and focus. Closing this older
            # surface must not steal either from it.
            if current in (None, self.popup):
                if previous is not None and previous.winfo_exists():
                    previous.grab_set()
                if (
                    focus is not None
                    and focus.winfo_exists()
                    and focus.winfo_viewable()
                ):
                    focus.focus_set()
        except tk.TclError:
            pass

    def bind_keys(
        self,
        actions: Mapping[str, Callable[[], Any]],
        *,
        editing: Iterable[str] = ("<Escape>",),
    ) -> KeyboardScope:
        previous = getattr(self, "_keyboard_scope", None)
        if previous is not None:
            previous.close()
        self._keyboard_scope = KeyboardScope(self.popup, actions, editing=editing)
        return self._keyboard_scope

    def _viewport_resized(self, event: tk.Event[tk.Canvas]) -> None:
        if self.viewport is None or self._body_window is None:
            return
        try:
            self.viewport.itemconfigure(self._body_window, width=max(1, event.width))
        except tk.TclError:
            return
        self._body_resized(event)

    def _body_resized(self, _event: tk.Event[tk.Misc]) -> None:
        if self._body_width_pending is None:
            self._body_width_pending = self.body.after_idle(self._reconcile_body_width)
        self._sync_overflow()

    def _reconcile_body_width(self) -> None:
        self._body_width_pending = None
        if self.viewport is None or self._body_window is None:
            return
        try:
            width = self.viewport.winfo_width()
            # Windows may finish mapping at the requested width after Configure.
            # Reconcile actual allocation after native layout has settled, even
            # when the canvas item's configured width is already correct.
            if width > 1 and self.body.winfo_width() != width:
                self.viewport.itemconfigure(self._body_window, width=width)
        except tk.TclError:
            return
        self._sync_overflow()

    def _body_destroyed(self, event: tk.Event[ttk.Frame]) -> None:
        if event.widget is self.body and self._body_width_pending is not None:
            self.body.after_cancel(self._body_width_pending)
            self._body_width_pending = None

    def _sync_overflow(self) -> None:
        if self.viewport is None or self.scrollbar is None:
            return
        try:
            bounds = self.viewport.bbox("all")
            self.viewport.configure(scrollregion=bounds or (0, 0, 0, 0))
            overflow = self.body.winfo_reqheight() > self.viewport.winfo_height()
            if overflow:
                self.scrollbar.grid()
            else:
                self.scrollbar.grid_remove()
                self.viewport.yview_moveto(0.0)
        except tk.TclError:
            return

    def apply_theme(self) -> None:
        """Patch this dialog surface without rebuilding its content."""

        if self.viewport is not None:
            try:
                self.viewport.configure(bg=THEME["bg"])
            except tk.TclError:
                pass

    def protected_content_is_visible(self, widget: tk.Misc) -> bool:
        """Return whether protected status or action content is fully visible."""
        try:
            self.popup.update_idletasks()
            popup_left = self.popup.winfo_rootx()
            popup_top = self.popup.winfo_rooty()
            popup_right = popup_left + self.popup.winfo_width()
            popup_bottom = popup_top + self.popup.winfo_height()
            widget_left = widget.winfo_rootx()
            widget_top = widget.winfo_rooty()
            return bool(
                widget.winfo_ismapped()
                and widget_left >= popup_left
                and widget_top >= popup_top
                and widget_left + widget.winfo_width() <= popup_right
                and widget_top + widget.winfo_height() <= popup_bottom
            )
        except tk.TclError:
            return False

    def action_is_visible(self, widget: tk.Misc) -> bool:
        """Return whether a footer action is fully inside the dialog client area."""
        return self.protected_content_is_visible(widget)


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
        if not tooltip.current_text():
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
            metrics = window_logical_metrics(self.host)
            margin = metrics.px(8)
            left, top, _right, bottom = tooltip.anchor_bounds()
            tip = tk.Toplevel(self.host)
            tip.withdraw()
            tip.wm_overrideredirect(True)
            label = tk.Label(
                tip,
                text=tooltip.current_text(),
                justify="left",
                wraplength=metrics.px(320),
                bg=THEME["panel"],
                fg=THEME["text"],
                relief="solid",
                borderwidth=metrics.px(1),
                padx=metrics.px(8),
                pady=metrics.px(6),
                font=metrics.font(FONT_UI_SMALL),
            )
            label.pack()
            tip.update_idletasks()
            screen_width = tip.winfo_screenwidth()
            screen_height = tip.winfo_screenheight()
            tip_width = tip.winfo_reqwidth()
            tip_height = tip.winfo_reqheight()
            x = min(max(margin, left), max(margin, screen_width - tip_width - margin))
            y = bottom + margin
            if y + tip_height > screen_height - margin:
                y = max(margin, top - tip_height - margin)
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

    def __init__(self, widget: tk.Widget, text: str | Callable[[], str]) -> None:
        self.widget = widget
        self.text = text
        self._pointer_text = ""
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
                self._pointer_entered,
                add="+",
            )
            target.bind("<Motion>", self._pointer_moved, add="+")
            target.bind(
                "<Leave>",
                lambda _event, tooltip=self: tooltip.controller.request_hide(tooltip),
                add="+",
            )
            target.bind("<ButtonPress>", self._hide_from_event, add="+")
            target.bind("<Destroy>", self._hide_from_event, add="+")

    def _hide_from_event(self, _event: tk.Event[tk.Widget]) -> None:
        self.controller.hide()

    def current_text(self) -> str:
        value = self.text() if callable(self.text) else self.text
        return str(value or "")

    def _pointer_entered(self, _event: tk.Event[tk.Widget]) -> None:
        self._pointer_text = self.current_text()
        self.controller.request_show(self)

    def _pointer_moved(self, _event: tk.Event[tk.Widget]) -> None:
        current = self.current_text()
        if current == self._pointer_text:
            return
        self._pointer_text = current
        self.controller.hide()
        self.controller.request_show(self)

    def contains_pointer(self) -> bool:
        if not self.current_text():
            return False
        try:
            pointer_x, pointer_y = self.widget.winfo_pointerxy()
        except tk.TclError:
            return False
        return pointer_inside_widget_bounds(self.targets, pointer_x, pointer_y)

    def anchor_bounds(self) -> tuple[int, int, int, int]:
        bounds_provider = getattr(self.widget, "tooltip_anchor_bounds", None)
        if callable(bounds_provider):
            provided = bounds_provider()
            if provided is not None:
                return provided
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
        track_color: str | None = None,
        bar_color: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._metrics = window_logical_metrics(parent)
        track_color = track_color or THEME["surface_2"]
        bar_color = bar_color or THEME["progress"]
        kwargs.pop("style", None)
        super().__init__(
            parent,
            height=self._metrics.px(height),
            bg=THEME["bg"],
            bd=0,
            highlightthickness=0,
            **kwargs,
        )
        self._maximum = max(1.0, float(maximum))
        self._mode = mode
        self._track_color = track_color
        self._bar_color = bar_color
        self._track_uses_theme = track_color == THEME["surface_2"]
        self._bar_uses_theme = bar_color == THEME["progress"]
        self._phase = 0.0
        self._after_id: str | None = None
        self._idle_id: str | None = None
        self._disposed = False
        self._variable = (
            variable if variable is not None else tk.DoubleVar(master=self, value=value)
        )
        self._suspend_variable_redraw = False
        if variable is not None and value:
            self._variable.set(value)
        self._variable_trace: str | None = self._variable.trace_add(
            "write", self._on_variable_changed
        )
        self.bind("<Configure>", lambda _event: self._redraw(), add="+")
        self.bind("<Destroy>", self._dispose, add="+")
        self._idle_id = self.after_idle(self._initial_redraw)

    def _initial_redraw(self) -> None:
        self._idle_id = None
        self._redraw()

    def _dispose(self, event: tk.Event[Any]) -> None:
        if event.widget is not self or self._disposed:
            return
        self._disposed = True
        self.stop()
        if self._idle_id is not None:
            try:
                self.after_cancel(self._idle_id)
            except tk.TclError:
                pass
            self._idle_id = None
        if self._variable_trace is not None:
            try:
                self._variable.trace_remove("write", self._variable_trace)
            except tk.TclError:
                pass
            self._variable_trace = None

    def configure(self, cnf: Any | None = None, **kwargs: Any) -> Any:
        if cnf:
            kwargs.update(cnf)
        changed = False
        if "mode" in kwargs:
            mode = str(kwargs.pop("mode"))
            if mode != self._mode:
                self._mode = mode
                changed = True
        if "maximum" in kwargs:
            maximum = max(1.0, float(kwargs.pop("maximum")))
            if maximum != self._maximum:
                self._maximum = maximum
                changed = True
        if "value" in kwargs:
            value = float(kwargs.pop("value"))
            try:
                current_value = float(self._variable.get())
            except (TypeError, ValueError, tk.TclError):
                current_value = float("nan")
            if value != current_value:
                self._suspend_variable_redraw = True
                try:
                    self._variable.set(value)
                finally:
                    self._suspend_variable_redraw = False
                changed = True
        if "track_color" in kwargs:
            track_color = str(kwargs.pop("track_color"))
            if track_color != self._track_color:
                self._track_color = track_color
                changed = True
        if "bar_color" in kwargs:
            bar_color = str(kwargs.pop("bar_color"))
            if bar_color != self._bar_color:
                self._bar_color = bar_color
                changed = True
        result = super().configure(**kwargs) if kwargs else None
        if changed or kwargs:
            self._redraw()
        return result

    config = configure

    def apply_theme(self) -> None:
        """Patch palette-bound colors without replacing the progress widget."""

        if self._track_uses_theme:
            self._track_color = THEME["surface_2"]
        if self._bar_uses_theme:
            self._bar_color = THEME["progress"]
        super().configure(bg=THEME["bg"])
        self._redraw()

    def _on_variable_changed(self, *_args: Any) -> None:
        if not self._disposed and not self._suspend_variable_redraw:
            self._redraw()

    def start(self, interval: int = 50) -> None:
        if self._disposed:
            return
        self.stop()
        self._mode = "indeterminate"

        def tick() -> None:
            if self._disposed:
                return
            self._after_id = None
            self._phase = (self._phase + 0.035) % 1.0
            self._redraw()
            if not self._disposed:
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
        if self._disposed:
            return
        try:
            width = max(1, self.winfo_width())
            height = max(self._metrics.px(3), self.winfo_height())
        except tk.TclError:
            return
        self.delete("all")
        px = self._metrics.px
        y1 = max(0, (height - px(3)) // 2)
        y2 = min(height, y1 + px(3))
        from .ui_chrome import draw_matte_track

        draw_matte_track(
            self,
            px(1),
            (y1 + y2) / 2,
            width - px(1),
            0,
            thickness=3,
            unit_scale=self._metrics.scale,
        )
        self.create_rectangle(0, y1, width, y2, fill=self._track_color, outline="")
        if self._mode == "indeterminate":
            segment = max(px(24), int(width * 0.24))
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
                self.create_line(start, y1, end, y1, fill=self._bar_color, width=px(1))


class PixelScrollTable(tk.Frame):
    """Small Treeview-compatible table with true pixel scrolling."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        columns: tuple[str, ...],
        selectmode: str = "browse",
        row_height: int = 34,
        header_height: int = 32,
    ) -> None:
        del selectmode
        super().__init__(
            parent,
            bg=THEME["panel"],
            bd=0,
            highlightthickness=1,
            highlightbackground=THEME["border"],
            highlightcolor=THEME["border"],
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
        self._leading_hover_values: dict[str, str] = {}
        self._hovered_row: str | None = None
        self._order: list[str] = []
        self._selection: str | None = None
        self._focus_item: str | None = None
        self._row_height = max(20, int(row_height))
        self._header_height = max(20, int(header_height))
        self._yscrollcommand: Callable[[float, float], Any] | None = None
        self._xscrollcommand: Callable[[float, float], Any] | None = None
        self._font = tkfont.Font(font=FONT_UI)
        self._header_font = tkfont.Font(font=FONT_UI_SMALL)
        self._manually_resized_columns: set[str] = set()
        self._last_manually_resized_column: str | None = None
        self._resize_column: str | None = None
        self._resize_origin_x = 0.0
        self._resize_origin_width = 0
        self._resize_hover_column: str | None = None
        self._redraw_after_id: str | None = None
        self._redrawing = False
        self._visible_row_items: dict[str, tuple[int, int, tuple[int, ...]]] = {}
        # Keep the divider itself quiet while giving trackpads and high-DPI
        # pointers a forgiving target on either side of the hairline.
        self._resize_margin = 8

        self._header = tk.Canvas(
            self,
            height=self._header_height,
            bg=THEME["panel"],
            bd=0,
            highlightthickness=0,
            xscrollincrement=1,
        )
        self._body = tk.Canvas(
            self,
            bg=THEME["panel"],
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
        self._body.bind("<Motion>", self._update_row_hover, add="+")
        self._body.bind("<Leave>", self._clear_row_hover, add="+")
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
        self._scroll_binding = _scrolling.bind_smooth_scroll(
            self._body,
            self._body,
            self._header,
            axis="both",
            horizontal_targets=(self._header,),
            on_scroll=self._schedule_redraw,
        )

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
        if self._manually_resized_columns:
            kwargs.pop("width", None)
        return self.column(column, **kwargs)

    def layout_columns(
        self,
        columns: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Apply one responsive column transaction with at most one redraw.

        A responsive breakpoint changes every Library column together. Calling
        ``layout_column`` for each field rebuilt the complete Canvas once per
        column, which made a single native resize step disproportionately
        expensive. Keep the same session-manual-width contract while committing
        the complete layout atomically.
        """

        changed = False
        for column, requested in columns.items():
            options = self._column_options[column]
            updates = dict(requested)
            if self._manually_resized_columns:
                updates.pop("width", None)
            before = dict(options)
            options.update(updates)
            options["width"] = max(
                int(options.get("minwidth", 1)), int(options.get("width", 100))
            )
            changed = changed or options != before
        if changed:
            self._redraw()
        return {column: dict(self._column_options[column]) for column in columns}

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
        return self.replace_snapshot(
            rows,
            selected=selected,
            leading_hover_values=self._leading_hover_values,
        )

    def replace_snapshot(
        self,
        rows: Iterable[tuple[str, tuple[Any, ...]]],
        *,
        selected: str | None = None,
        leading_hover_values: Mapping[str, str] | None = None,
    ) -> tuple[str, ...]:
        """Atomically commit one immutable table snapshot with minimum rendering."""

        items: dict[str, tuple[Any, ...]] = {}
        order: list[str] = []
        for raw_item, values in rows:
            item = str(raw_item)
            if item in items:
                order.remove(item)
            order.append(item)
            items[item] = tuple(values)
        preferred = str(selected) if selected is not None else self._selection
        next_selection = preferred if preferred in items else None
        raw_hover_values = (
            self._leading_hover_values
            if leading_hover_values is None
            else leading_hover_values
        )
        next_hover_values = {
            str(item): str(value)
            for item, value in raw_hover_values.items()
            if str(item) in items and str(value).strip()
        }
        next_hovered_row = self._hovered_row if self._hovered_row in items else None
        if (
            items == self._items
            and order == self._order
            and next_selection == self._selection
            and next_hover_values == self._leading_hover_values
            and next_hovered_row == self._hovered_row
        ):
            return tuple(order)

        previous_items = self._items
        previous_selection = self._selection
        previous_hovered_row = self._hovered_row
        structure_matches = order == self._order and items.keys() == self._items.keys()
        self._items = items
        self._order = order
        self._selection = next_selection
        self._focus_item = next_selection
        self._leading_hover_values = next_hover_values
        self._hovered_row = next_hovered_row
        if next_hovered_row not in next_hover_values:
            self._body.configure(cursor="")
        if structure_matches:
            self._patch_rows(
                previous_items,
                previous_selection=previous_selection,
                previous_hovered_row=previous_hovered_row,
            )
        else:
            self._redraw()
        return tuple(order)

    def set_leading_hover_values(self, values: dict[str, str]) -> None:
        """Replace the first cell only while its actionable row is hovered."""
        self.replace_snapshot(
            ((item, self._items[item]) for item in self._order),
            selected=self._selection,
            leading_hover_values=values,
        )

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
        previous_selection = self._selection
        self._selection = item_id
        self._focus_item = item_id
        if changed:
            self._patch_rows(
                self._items,
                previous_selection=previous_selection,
                previous_hovered_row=self._hovered_row,
            )
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
        if not self._manually_resized_columns and self._resize_column is None:
            for index in responsive_table_stretch_indices(
                self._columns,
                stretch_columns,
                self._manually_resized_columns,
            ):
                column = self._columns[index]
                raw_limit = self._column_options[column].get("stretchmax")
                stretch_limits[index] = (
                    int(raw_limit) if raw_limit is not None else None
                )
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
        for column, width, _anchor in layout:
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
        rendered_layout = self._layout_columns()
        for rendered_column, width, _anchor in rendered_layout:
            self._column_options[rendered_column]["width"] = int(width)
        rendered_width = next(
            width
            for rendered_column, width, _anchor in rendered_layout
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
        # The cell position already supplies visual padding. Compact identity
        # columns need a smaller reserve so values such as ``001`` remain
        # readable; normal columns retain the roomier table inset.
        reserve = 0 if width <= 64 else 24
        available = max(0, width - reserve)
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

    def _row_fill(self, item: str) -> str:
        if item == self._selection:
            return THEME["accent_surface"]
        if item == self._hovered_row:
            return THEME["surface_2"]
        return THEME["panel"]

    def _cell_color(self, item: str, value_index: int) -> str:
        if (
            value_index == 0
            and item == self._hovered_row
            and item in self._leading_hover_values
        ):
            return THEME["action"]
        return THEME["text"] if value_index == 1 else THEME["muted"]

    def _patch_rows(
        self,
        previous_items: Mapping[str, tuple[Any, ...]],
        *,
        previous_selection: str | None,
        previous_hovered_row: str | None,
    ) -> None:
        """Patch value/selection changes without rebuilding the table Canvas."""

        layout = self._layout_columns()
        changed_rows = {
            item
            for item in self._items
            if previous_items.get(item) != self._items.get(item)
        }
        changed_rows.update(
            item
            for item in {
                previous_selection,
                self._selection,
                previous_hovered_row,
                self._hovered_row,
            }
            if item is not None
        )
        try:
            for item in changed_rows:
                rendered = self._visible_row_items.get(item)
                if rendered is None:
                    continue
                background_item, indicator_item, text_items = rendered
                selected = item == self._selection
                self._body.itemconfigure(
                    background_item,
                    fill=self._row_fill(item),
                )
                self._body.itemconfigure(
                    indicator_item,
                    fill=THEME["selection"],
                    state="normal" if selected else "hidden",
                )
                values = self._items.get(item, ())
                for value_index, text_item in enumerate(text_items):
                    _column, width, _anchor = layout[value_index]
                    value = values[value_index] if value_index < len(values) else ""
                    if value_index == 0 and item == self._hovered_row:
                        value = self._leading_hover_values.get(item, value)
                    self._body.itemconfigure(
                        text_item,
                        text=self._ellipsize(value, width, font=self._font),
                        fill=self._cell_color(item, value_index),
                    )
        except (IndexError, tk.TclError):
            self._redraw()

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
        self._visible_row_items = {}
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
                    fill=THEME["panel"],
                    outline="",
                )
                self._header.create_text(
                    cursor
                    + (
                        width / 2
                        if heading_anchor == "center"
                        else width - 12
                        if heading_anchor == "e"
                        else 12
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
                if column in {self._resize_column, self._resize_hover_column}:
                    divider_x = cursor - 1 if column == layout[-1][0] else cursor
                    self._header.create_line(
                        divider_x,
                        5,
                        divider_x,
                        self._header_height - 5,
                        fill=THEME["selection"],
                        width=2,
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
                background_item = self._body.create_rectangle(
                    0,
                    top,
                    content_width,
                    top + self._row_height,
                    fill=self._row_fill(item_id),
                    outline="",
                )
                indicator_item = self._body.create_rectangle(
                    0,
                    top + 4,
                    3,
                    top + self._row_height - 4,
                    fill=THEME["selection"],
                    outline="",
                    state="normal" if selected else "hidden",
                )
                values = self._items.get(item_id, ())
                cursor = 0
                text_items: list[int] = []
                for value_index, (_column, width, anchor) in enumerate(layout):
                    value = values[value_index] if value_index < len(values) else ""
                    if value_index == 0 and item_id == self._hovered_row:
                        value = self._leading_hover_values.get(item_id, value)
                    text_x = cursor + (
                        width / 2
                        if anchor == "center"
                        else width - 12
                        if anchor == "e"
                        else 12
                    )
                    text_items.append(
                        self._body.create_text(
                            text_x,
                            top + (self._row_height / 2),
                            text=self._ellipsize(value, width, font=self._font),
                            anchor="center"
                            if anchor == "center"
                            else "e"
                            if anchor == "e"
                            else "w",
                            fill=self._cell_color(item_id, value_index),
                            font=self._font,
                        )
                    )
                    cursor += width
                self._visible_row_items[item_id] = (
                    background_item,
                    indicator_item,
                    tuple(text_items),
                )
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
        """Coalesce resize storms to one redraw per display-frame budget."""
        if self._redraw_after_id is not None:
            return

        def redraw() -> None:
            self._redraw_after_id = None
            self._redraw()

        try:
            self._redraw_after_id = self.after(16, redraw)
        except tk.TclError:
            self._redraw_after_id = None

    def apply_theme(self) -> None:
        """Patch the table canvases and redraw their current immutable model."""

        try:
            self.configure(bg=THEME["panel"])
            self._header.configure(bg=THEME["panel"])
            self._body.configure(bg=THEME["panel"])
        except tk.TclError:
            return
        self._redraw()

    def _select_from_pointer(self, event: tk.Event[Any]) -> None:
        row = self.identify_row(event.y)
        if row:
            self.selection_set(row)
            self._body.focus_set()

    def _update_row_hover(self, event: tk.Event[Any]) -> None:
        row = self.identify_row(event.y)
        hovered = row or None
        cursor = (
            "hand2"
            if hovered in self._leading_hover_values
            and self.identify_column(event.x) == "#1"
            else ""
        )
        self._body.configure(cursor=cursor)
        if hovered == self._hovered_row:
            return
        previous_hovered_row = self._hovered_row
        self._hovered_row = hovered
        self._patch_rows(
            self._items,
            previous_selection=self._selection,
            previous_hovered_row=previous_hovered_row,
        )

    def _clear_row_hover(self, _event: tk.Event[Any] | None = None) -> None:
        if self._hovered_row is None:
            return
        previous_hovered_row = self._hovered_row
        self._hovered_row = None
        self._body.configure(cursor="")
        self._patch_rows(
            self._items,
            previous_selection=self._selection,
            previous_hovered_row=previous_hovered_row,
        )

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
        """Compatibility adapter; pixel math and input lifetime have one owner."""
        self._scroll_binding.scroll(dx, dy)
        return "break"


class _LibraryFocusTarget(Protocol):
    def focus_item(self, item: str | None = None) -> str: ...


def _focus_library_table_item(
    table: _LibraryFocusTarget,
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
        thumb_color: str | None = None,
        hover_color: str | None = None,
    ) -> None:
        thumb_color = thumb_color or THEME["border"]
        hover_color = hover_color or THEME["subtle"]
        if orient not in {"vertical", "horizontal"}:
            raise ValueError(f"Unsupported scrollbar orientation: {orient}")
        self._metrics = window_logical_metrics(parent)
        width = self._metrics.px(width)
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
        self._thumb_uses_theme = thumb_color == THEME["border"]
        self._hover_uses_theme = hover_color == THEME["subtle"]
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
        self.bind("<Unmap>", self._end_drag, add="+")

    def set(self, first: str | float, last: str | float) -> None:
        try:
            self._first = max(0.0, min(1.0, float(first)))
            self._last = max(self._first, min(1.0, float(last)))
        except (TypeError, ValueError):
            self._first, self._last = 0.0, 1.0
        if self._thumb_bounds() is None:
            self._drag_offset = None
        self._redraw()

    def _thumb_bounds(self) -> tuple[float, float] | None:
        length = max(
            1, self.winfo_height() if self._orient == "vertical" else self.winfo_width()
        )
        visible = max(0.0, min(1.0, self._last - self._first))
        if visible >= 0.999:
            return None
        thumb_length = min(
            float(length), max(float(self._metrics.px(28)), length * visible)
        )
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
                cross = max(self._metrics.px(2), self.winfo_width() // 2)
                self.create_line(
                    cross,
                    start + self._metrics.px(3),
                    cross,
                    max(start + self._metrics.px(3), end - self._metrics.px(3)),
                    fill=color,
                    width=self._metrics.px(4),
                    capstyle=tk.ROUND,
                )
            else:
                cross = max(self._metrics.px(2), self.winfo_height() // 2)
                self.create_line(
                    start + self._metrics.px(3),
                    cross,
                    max(start + self._metrics.px(3), end - self._metrics.px(3)),
                    cross,
                    fill=color,
                    width=self._metrics.px(4),
                    capstyle=tk.ROUND,
                )
        except tk.TclError:
            return

    def _set_hovered(self, _event: tk.Event[Any]) -> None:
        self._hovered = True
        self._redraw()

    def apply_theme(self) -> None:
        """Patch palette-bound scrollbar colors without changing its position."""

        if self._thumb_uses_theme:
            self._thumb_color = THEME["border"]
        if self._hover_uses_theme:
            self._hover_color = THEME["subtle"]
        self.configure(bg=THEME["bg"])
        self._redraw()

    def _set_unhovered(self, _event: tk.Event[Any]) -> None:
        self._hovered = False
        # The implicit pointer grab keeps a drag active outside this narrow track.
        # Only release, unmapping, or losing scrollable content retires it.
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
    """A compact context action using the shared product field chrome."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        textvariable: tk.StringVar,
        command: Callable[[], None],
        image: Any | None = None,
        width: int = 240,
        height: int = 34,
        path_display: bool = False,
    ) -> None:
        self._metrics = window_logical_metrics(parent)
        width, height = self._metrics.px(width), self._metrics.px(height)
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
        self._matte_material_surface = True
        self._textvariable = textvariable
        self._path_display = path_display
        self._text_font = tkfont.Font(root=self, font=self._metrics.font(FONT_UI_SMALL))
        self._command = command
        self._icon = image
        self._hovered = False
        self._background_image: Any | None = None
        self._background_item = self.create_image(0, 0, anchor="nw")
        self._icon_item = (
            self.create_image(
                self._metrics.px(15), height // 2, image=image, anchor="w"
            )
            if image is not None
            else None
        )
        self._text_item = self.create_text(
            self._metrics.px(18 if image is None else 38),
            height // 2,
            text=textvariable.get(),
            fill=THEME["muted"],
            font=self._metrics.font(FONT_UI_SMALL),
            anchor="w",
        )
        self._text_trace = textvariable.trace_add(
            "write", lambda *_args: self._sync_text()
        )
        self._tooltip = ToolTip(self, lambda: self._textvariable.get())
        self.bind("<Destroy>", self._destroyed, add="+")
        self.bind("<FocusIn>", lambda _event: self._redraw(), add="+")
        self.bind("<FocusOut>", lambda _event: self._redraw(), add="+")
        self.bind("<Configure>", lambda _event: self._redraw(), add="+")
        self.bind("<Enter>", lambda _event: self._set_hover(True), add="+")
        self.bind("<Leave>", lambda _event: self._set_hover(False), add="+")
        self.bind("<Button-1>", lambda _event: self._command(), add="+")
        self.bind("<Return>", lambda _event: self._command(), add="+")
        self.bind("<space>", lambda _event: self._command(), add="+")
        self.after_idle(self._redraw)

    def _sync_text(self) -> None:
        try:
            left = self._metrics.px(18 if self._icon is None else 42)
            width = max(1, self.winfo_width() - left - self._metrics.px(18))
            text = (
                compact_destination_path(
                    self._textvariable.get(), width, self._text_font.measure
                )
                if self._path_display
                else ellipsize_wrapped_text(
                    self._textvariable.get(),
                    maximum_width=width,
                    maximum_lines=1,
                    measure_width=self._text_font.measure,
                )
            )
            self.itemconfigure(self._text_item, text=text)
        except tk.TclError:
            pass

    def _destroyed(self, event: tk.Event[Any]) -> None:
        if event.widget is self:
            self._textvariable.trace_remove("write", self._text_trace)

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
        if width < 2 or height < 2:
            return
        if Image is not None and ImageDraw is not None and ImageTk is not None:
            surface = field_border_image(
                width,
                height,
                hovered=self._hovered,
                focused=self.focus_get() is self,
                unit_scale=self._metrics.scale,
            )
            self._background_image = ImageTk.PhotoImage(surface)
            self.itemconfigure(self._background_item, image=self._background_image)
            self.coords(self._background_item, 0, 0)
            self.tag_lower(self._background_item)
            if hasattr(self, "_matte_anchor"):
                from .ui_materials import draw_matte_backdrop

                draw_matte_backdrop(self)
        if self._icon_item is not None:
            self.coords(self._icon_item, self._metrics.px(15), height // 2)
        self.coords(
            self._text_item,
            self._metrics.px(18 if self._icon is None else 42),
            height // 2,
        )
        self._sync_text()
        self.delete("keyboard-focus")

    def apply_theme(self) -> None:
        """Patch this control's palette while preserving its live binding."""

        self.configure(bg=THEME["bg"])
        self.itemconfigure(
            self._text_item,
            fill=THEME["text"] if self._hovered else THEME["muted"],
        )
        self._redraw()


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
                fill=THEME["on_accent"] if primary else THEME["muted"],
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
                    fill = accent_hover_color()
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
                from .ui_chrome import action_button_image

                surface = action_button_image(
                    width,
                    height,
                    accent=self._primary,
                    state="pressed"
                    if self._pressed
                    else "hover"
                    if self._hovered
                    else "normal",
                )
                if disabled:
                    surface = field_border_image(width, height)
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

    def apply_theme(self) -> None:
        """Patch this control's palette without changing interaction state."""

        super().configure(bg=THEME["bg"])
        if self._button_image is None:
            self.itemconfigure(
                self._content_item,
                fill=THEME["on_accent"] if self._primary else THEME["muted"],
            )
        self._redraw()


class SegmentedSelector(tk.Frame):
    """Small two-state selector with consistent rendering across Tk platforms."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        variable: tk.StringVar,
        values: tuple[str, ...] = (OutputType.MP4.value, OutputType.MP3.value),
        background: str | None = None,
        compact: bool = False,
        separated: bool = False,
    ) -> None:
        self._metrics = window_logical_metrics(parent)
        self._font = self._metrics.font(
            FONT_UI_SMALL if separated else FONT_UI_SMALL_MEDIUM
        )
        background = background or THEME["surface"]
        super().__init__(
            parent, bg=background, bd=0, highlightthickness=0, padx=0, pady=0
        )
        self._separated = separated
        self._disposed = False
        self._variable = variable
        self._background_role = (
            "bg"
            if background == THEME["bg"]
            else "surface"
            if background == THEME["surface"]
            else None
        )
        self._background = background
        self._labels: dict[str, tk.Label] = {}
        self._segment_images: dict[str, Any] = {}
        self._segment_snapshots: dict[str, tuple[object, ...]] = {}
        self._hovered: str | None = None
        self._pressed_segment: tuple[object, ...] | None = None
        horizontal_padding = 11 if separated else 7 if compact else 10
        vertical_padding = 6 if separated else 3 if compact else 4
        horizontal_padding = self._metrics.px(horizontal_padding)
        vertical_padding = self._metrics.px(vertical_padding)
        self._segment_padding = (horizontal_padding, vertical_padding)
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
                font=self._font,
                cursor="hand2",
                takefocus=1,
            )
            label.pack(side="left", padx=(0, self._metrics.px(6)) if separated else 0)
            label.bind("<Button-1>", partial(self._press_segment, value))
            label.bind("<ButtonRelease-1>", partial(self._release_segment, value))
            label.bind("<Unmap>", self._retire_segment, add="+")
            label.bind("<FocusIn>", lambda _event: self._sync(), add="+")
            label.bind("<FocusOut>", lambda _event: self._sync(), add="+")
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

    def _retire_segment(self, _event: Any = None) -> None:
        self._pressed_segment = None

    def _press_segment(self, value: str, event: tk.Event[tk.Label]) -> str:
        if self._disposed:
            return "break"
        self._pressed_segment = (value, event.widget, self._variable)
        event.widget.focus_set()
        return "break"

    def _release_segment(self, value: str, event: tk.Event[tk.Label]) -> str:
        if self._disposed:
            return "break"
        admitted, self._pressed_segment = self._pressed_segment, None
        label = self._labels.get(value)
        if (
            admitted == (value, label, self._variable)
            and event.widget is label
            and label.winfo_viewable()
            and 0 <= event.x < label.winfo_width()
            and 0 <= event.y < label.winfo_height()
        ):
            self._select_from_event(value, event)
        return "break"

    def _select_from_event(self, value: str, _event: tk.Event[tk.Label]) -> None:
        if not self._disposed:
            self._variable.set(value)

    def _set_hover_from_event(
        self,
        value: str,
        hovered: bool,
        _event: tk.Event[tk.Label],
    ) -> None:
        self._set_hover(value, hovered)

    def _set_hover(self, value: str, hovered: bool) -> None:
        self._hovered = value if hovered else None
        self._sync()

    def _sync(self) -> None:
        if self._disposed:
            return
        selected = self._variable.get()
        for value, label in self._labels.items():
            active = value == selected
            hovered = self._hovered == value
            fill = (
                (THEME["accent_surface"] if self._separated else THEME["accent_dark"])
                if active
                else self._background
            )
            foreground = THEME["selection"] if active else THEME["muted"]
            focused = self.focus_get() is label
            snapshot = (
                fill,
                foreground,
                THEME["border"],
                self._background,
                focused,
                hovered,
                THEME["text"],
            )
            if self._segment_snapshots.get(value) == snapshot:
                continue
            if Image is not None and ImageDraw is not None and ImageTk is not None:
                from .platform_services import (
                    create_surface_image,
                    surface_backing_scale,
                )

                px, py = self._segment_padding
                width = int(self.tk.call("font", "measure", self._font, value)) + px * 2
                height = (
                    int(self.tk.call("font", "metrics", self._font, "-linespace"))
                    + py * 2
                )
                density = surface_backing_scale(self)
                from .ui_chrome import ttk_surface_image

                image = ttk_surface_image(
                    width,
                    height=height,
                    fill=fill,
                    edge=THEME["focus"] if focused else THEME["border"],
                    recessed=active or hovered,
                    depth=0.8 if active else 0.62 if hovered else 0.45,
                    density=density,
                    unit_scale=self._metrics.scale,
                )
                self._segment_images[value], _ = create_surface_image(
                    self,
                    image,
                    density,
                    logical_size=(width, height),
                    existing=self._segment_images.get(value),
                )
                label.configure(
                    image=self._segment_images[value], compound="center", padx=0, pady=0
                )
            else:
                # The text-only fallback uses the same semantic focus value.
                label.configure(underline=-1)
            label.configure(
                bg=THEME["focus_surface"]
                if focused and Image is None
                else self._background,
                fg=foreground,
            )
            self._segment_snapshots[value] = snapshot

    def apply_theme(self) -> None:
        """Patch palette-bound colors while preserving selection and bindings."""

        if self._background_role is not None:
            self._background = THEME[self._background_role]
        self.configure(bg=self._background)
        self._sync()

    def destroy(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        try:
            self._variable.trace_remove("write", self._trace_id)
        except (tk.TclError, AttributeError, ValueError):
            pass
        self._pressed_segment = None
        super().destroy()
        self._segment_images.clear()
        self.__dict__.pop("_variable", None)
