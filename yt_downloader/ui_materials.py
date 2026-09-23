"""Shared static matte artwork. No timers, animation or resize-time resampling."""

from __future__ import annotations

import sys
import tkinter as tk
import tkinter.font as tkfont
from functools import lru_cache
from pathlib import Path
from tkinter import ttk
from typing import Any, cast

from PIL import Image, ImageChops, ImageOps, ImageTk

from .ui_theme import THEME, theme_motif, theme_palette_snapshot


def material_asset(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / "assets" / "materials" / (name + "-v2" + ".png")


@lru_cache(maxsize=8)
def backdrop_pixels(motif: str, background: str, tint: str) -> Image.Image:
    """Cache one full composition, with readable quiet zones and soft edges."""
    with Image.open(material_asset(motif)) as source:
        mask = source.convert("L").resize((1200, 800), Image.Resampling.LANCZOS)
    # Full-height composition rather than a decorative heading strip. The
    # source's quiet left zone protects content hierarchy; edge fades eliminate
    # hard bitmap boundaries. Raster work occurs only on theme changes.
    fade = Image.new("L", (1, mask.height))
    fade.putdata(
        [
            round(255 * min(1, y / 90, (mask.height - 1 - y) / 90))
            for y in range(mask.height)
        ]
    )
    mask = ImageChops.multiply(mask, fade.resize(mask.size)).point(
        lambda n: round(n * 0.28)
    )
    return Image.composite(
        Image.new("RGB", mask.size, tint), Image.new("RGB", mask.size, background), mask
    )


def tint_brand(source: Image.Image, *, wordmark: bool = False) -> Image.Image:
    """Preserve approved geometry, alpha and luminance texture; tint app UI only."""
    image = source.convert("RGBA")
    tinted = ImageOps.colorize(
        ImageOps.grayscale(image),
        THEME["bg"],
        THEME["text"] if wordmark else THEME["accent"],
    )
    tinted.putalpha(image.getchannel("A"))
    return tinted


class MatteBackdrop:
    """One decorative canvas item; configure moves it, never rebuilds pixels."""

    def __init__(self, canvas: tk.Canvas) -> None:
        self.canvas = canvas
        self.photo: ImageTk.PhotoImage | None = None
        self.item: int | None = None
        self.identity: tuple | None = None
        self.builds = 0
        self.pending: str | None = None
        self.geometry_bindings: list[tuple[tk.Misc, str, str]] = []
        self._configure = canvas.bind(
            "<Configure>", lambda _event: self.draw(), add="+"
        )
        canvas.bind("<Destroy>", self._destroy, add="+")

    def track_frame_geometry(self, frame: tk.Misc, anchor: tk.Misc) -> None:
        # Moving an ancestor does not resize its child canvas. Reproject once
        # the complete native layout has settled, including first mapping.
        widget: tk.Misc | None = frame
        while widget is not None:
            for sequence in ("<Configure>", "<Map>"):
                token = widget.bind(sequence, self.request, add="+")
                self.geometry_bindings.append((widget, sequence, token))
            if widget is anchor:
                break
            widget = widget.master

    def request(self, *_args: Any) -> None:
        if self.pending is None:
            self.pending = self.canvas.after_idle(self._settled_draw)

    def _settled_draw(self) -> None:
        self.pending = None
        self.draw()

    def _destroy(self, event: tk.Event) -> None:
        if event.widget is self.canvas:
            if self.pending is not None:
                self.canvas.after_cancel(self.pending)
                self.pending = None
            for widget, sequence, token in self.geometry_bindings:
                try:
                    widget.unbind(sequence, token)
                except tk.TclError:
                    pass
            self.geometry_bindings.clear()
            self.photo = None
            self.item = None

    def draw(self) -> None:
        identity = theme_palette_snapshot()
        if identity != self.identity:
            root = self.canvas.winfo_toplevel()
            shared = getattr(root, "_matte_texture", None)
            if shared is None or shared[0] != identity:
                shared = (
                    identity,
                    ImageTk.PhotoImage(
                        backdrop_pixels(theme_motif(), THEME["bg"], THEME["accent"]),
                        master=root,
                    ),
                )
                cast(Any, root)._matte_texture = shared
            self.photo = shared[1]
            self.identity = identity
            self.builds += 1
        try:
            self.canvas.configure(bg=THEME["bg"])
            if self.item is None or not self.canvas.type(self.item):
                self.item = self.canvas.create_image(
                    0, 0, anchor="ne", image=self.photo, tags=("matte-decoration",)
                )
            else:
                self.canvas.itemconfigure(self.item, image=self.photo)
            anchor = getattr(self.canvas, "_matte_anchor", None)
            x = max(1, self.canvas.winfo_width())
            y = 0
            if anchor is not None:
                x = (
                    anchor.winfo_rootx()
                    + anchor.winfo_width()
                    - self.canvas.winfo_rootx()
                )
                y = anchor.winfo_rooty() - self.canvas.winfo_rooty()
            self.canvas.coords(self.item, x, y)
            self.canvas.tag_lower(self.item)
        except tk.TclError:
            return

    def apply_theme(self) -> None:
        self.draw()


def draw_matte_backdrop(canvas: tk.Canvas) -> MatteBackdrop:
    owner = getattr(canvas, "_matte_backdrop", None)
    if owner is None:
        owner = MatteBackdrop(canvas)
        cast(Any, canvas)._matte_backdrop = owner
    owner.draw()
    return owner


def attach_matte_frame(frame: tk.Misc, *, anchor: tk.Misc | None = None) -> tk.Canvas:
    """Project the same scene artwork through nested opaque frame backgrounds."""
    existing = getattr(frame, "_matte_background_canvas", None)
    if existing is not None:
        if anchor is not None:
            cast(Any, existing)._matte_anchor = anchor
        return existing
    canvas = tk.Canvas(
        frame, bd=0, highlightthickness=0, takefocus=False, bg=THEME["bg"]
    )
    cast(Any, canvas)._matte_anchor = anchor if anchor is not None else frame
    canvas.place(x=0, y=0, relwidth=1, relheight=1)
    frame.tk.call("lower", str(canvas))
    owner = draw_matte_backdrop(canvas)
    owner.track_frame_geometry(frame, anchor if anchor is not None else frame)
    cast(Any, canvas).apply_theme = owner.apply_theme
    cast(Any, frame)._matte_background_canvas = canvas
    return canvas


def enroll_matte_backgrounds(frame: tk.Misc) -> list[tk.Canvas]:
    """Shared aligned underlays, no new panels, resampling or input owners."""
    style = ttk.Style(frame)
    pending = [frame]
    frames: list[tk.Misc] = []
    surfaces: list[tk.Canvas] = []
    while pending:
        widget = pending.pop()
        pending.extend(widget.winfo_children())
        if isinstance(widget, tk.Canvas) and getattr(
            widget, "_matte_material_surface", False
        ):
            widget._matte_anchor = frame  # type: ignore[attr-defined]
            draw_matte_backdrop(widget)
            surfaces.append(widget)
        elif isinstance(widget, ttk.Frame):
            original = str(widget.cget("style")) or "TFrame"
            if str(style.lookup(original, "background")) == THEME["bg"]:
                frames.append(widget)
        elif isinstance(widget, tk.Frame) and str(widget.cget("bg")) == THEME["bg"]:
            frames.append(widget)
    return [attach_matte_frame(widget, anchor=frame) for widget in frames] + surfaces


class MatteTextProjection:
    """Paint a native read-only document over the shared scene.

    The original widget continues to own geometry, text, selection, keyboard,
    copy and accessibility. The child canvas is presentation only and forwards
    pointer input in the same coordinate system. No screenshot or text raster
    resampling is involved.
    """

    def __init__(self, widget: tk.Misc, anchor: tk.Misc) -> None:
        self.widget = widget
        self.anchor = anchor
        self.canvas = tk.Canvas(
            widget, bd=0, highlightthickness=0, takefocus=False, bg=THEME["bg"]
        )
        cast(Any, self.canvas)._matte_anchor = anchor
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1, bordermode="outside")
        self.backdrop = draw_matte_backdrop(self.canvas)
        self.pending: str | None = None
        self.retired = False
        self.trace: tuple[str, str] | None = None
        self.control_photo: Any = None
        self.control_identity: tuple | None = None
        self.last_size: tuple[int, int] | None = None
        self.view_callbacks: dict[str, tuple[Any, str]] = {}
        self._configure_original = widget.configure
        if isinstance(widget, tk.Text):
            for option in ("xscrollcommand", "yscrollcommand"):
                callback = widget.cget(option)
                command = widget.register(self._view_handler(option))
                self.view_callbacks[option] = (callback, command)
                self._configure_original(**{option: command})
        widget.configure = self._configure  # type: ignore[method-assign]
        cast(Any, widget).config = self._configure
        self.bindings = []
        for target, event in (
            (widget, "<Map>"),
            (widget, "<KeyRelease>"),
            (widget, "<<Selection>>"),
            (widget, "<FocusIn>"),
            (widget, "<FocusOut>"),
        ):
            self.bindings.append(
                (target, event, target.bind(event, self.request, add="+"))
            )
        self.bindings.append(
            (
                widget,
                "<Configure>",
                widget.bind("<Configure>", self._widget_configured, add="+"),
            )
        )
        # Moving the common scene changes only the projected matte origin.
        # Rebuilding every label/button canvas on each ancestor Configure made
        # Windows live resize repaint those controls one at a time.
        self.bindings.append(
            (
                anchor,
                "<Configure>",
                anchor.bind("<Configure>", self.backdrop.request, add="+"),
            )
        )
        if isinstance(widget, tk.Text):
            self.bindings.append(
                (
                    widget,
                    "<<Modified>>",
                    widget.bind("<<Modified>>", self._modified, add="+"),
                )
            )
        for event in (
            "<ButtonPress-1>",
            "<B1-Motion>",
            "<ButtonRelease-1>",
            "<MouseWheel>",
            "<Button-4>",
            "<Button-5>",
            "<ButtonPress-3>",
            "<Enter>",
            "<Leave>",
        ):
            self.canvas.bind(event, self._pointer_handler(event))
        self.canvas.bind("<Destroy>", self._destroy, add="+")
        self._watch_variable()
        cast(Any, self.canvas).apply_theme = self.request
        self.request()

    def _configure(self, cnf: Any = None, **kwargs: Any) -> Any:
        # Native viewport notifications cover scrollbar, keyboard, see() and
        # layout changes. Preserve the document owner's existing consumers.
        options = dict(cnf) if isinstance(cnf, dict) else {}
        options.update(kwargs)
        for option, (callback, command) in self.view_callbacks.items():
            if option in options:
                self.view_callbacks[option] = (options[option], command)
                options[option] = command
        if isinstance(cnf, dict) or kwargs:
            cnf, kwargs = options, {}
        result = self._configure_original(cnf, **kwargs)
        if kwargs or isinstance(cnf, dict):
            self._watch_variable()
            self.request()
        return result

    def _view_handler(self, option: str) -> Any:
        def changed(*fractions: str) -> None:
            if self.retired:
                return
            callback, _command = self.view_callbacks[option]
            if callable(callback):
                callback(*fractions)
            elif callback:
                self.widget.tk.call(*self.widget.tk.splitlist(callback), *fractions)
            self.request()

        return changed

    def _watch_variable(self) -> None:
        try:
            variable = str(self.widget.cget("textvariable"))
        except tk.TclError:
            variable = ""
        if self.trace and self.trace[0] == variable:
            return
        self._remove_trace()
        if variable:
            command = self.widget.register(self.request)
            self.widget.tk.call("trace", "add", "variable", variable, "write", command)
            self.trace = (variable, command)

    def _remove_trace(self) -> None:
        if self.trace:
            variable, command = self.trace
            try:
                self.widget.tk.call(
                    "trace", "remove", "variable", variable, "write", command
                )
                self.widget.deletecommand(command)
            except tk.TclError:
                pass
            self.trace = None

    def _modified(self, _event: Any = None) -> None:
        if isinstance(self.widget, tk.Text) and self.widget.edit_modified():
            self.widget.edit_modified(False)
            self.request()

    def _pointer_handler(self, sequence: str) -> Any:
        def handler(event: Any) -> str:
            return self._forward(sequence, event)

        return handler

    def _forward(self, sequence: str, event: Any) -> str:
        if not self.retired:
            options = {"x": event.x, "y": event.y, "state": event.state}
            if sequence == "<MouseWheel>":
                options["delta"] = event.delta
            # Tk does not allow synthesized Double/Triple modifiers. Its
            # native click counter derives them from the forwarded press.
            if not sequence.startswith(("<Double", "<Triple")):
                self.widget.event_generate(sequence, **options)
            self.request()
        return "break"

    def request(self, *_args: Any) -> None:
        if not self.retired and self.pending is None:
            self.pending = self.canvas.after_idle(self.draw)

    def _widget_configured(self, event: tk.Event) -> None:
        # A position-only move carries the existing child Canvas and its text.
        # Only the shared scene origin changes; Canvas owns its own Expose paint.
        width_only_label = (
            self.last_size is not None
            and event.height == self.last_size[1]
            and isinstance(self.widget, (tk.Label, ttk.Label))
            and str(self.widget.cget("anchor")) in {"w", "nw", "sw"}
            and not str(self.widget.cget("image"))
        )
        if (event.width, event.height) == self.last_size or width_only_label:
            self.backdrop.request()
        else:
            self.request()

    def draw(self) -> None:
        self.pending = None
        if self.retired or not self.widget.winfo_viewable():
            return
        self.last_size = (self.widget.winfo_width(), self.widget.winfo_height())
        self.backdrop.draw()
        self.canvas.delete("matte-text")
        if isinstance(self.widget, tk.Text):
            self._document()
        else:
            self._label()

    def _label(self) -> None:
        widget = self.widget
        style = ttk.Style(widget)
        name = (
            str(widget.cget("style"))
            if isinstance(widget, (ttk.Label, ttk.Button))
            else ""
        )
        button = isinstance(widget, ttk.Button)
        states = tuple(cast(ttk.Button, widget).state()) if button else ()
        default_style = "TButton" if button else "TLabel"

        def option(key: str, fallback: Any) -> Any:
            try:
                value = widget.cget(key)
                if str(value):
                    return value
            except tk.TclError:
                pass
            return style.lookup(name or default_style, key, state=states) or fallback

        variable = str(option("textvariable", ""))
        text = str(widget.getvar(variable)) if variable else str(option("text", ""))
        width, height = widget.winfo_width(), widget.winfo_height()
        anchor = str(option("anchor", "center" if button else "w"))
        x = (
            width / 2
            if anchor in ("center", "n", "s")
            else width
            if "e" in anchor
            else 0
        )
        y = (
            height / 2
            if anchor in ("center", "w", "e")
            else height
            if "s" in anchor
            else 0
        )
        if button:
            from .platform_services import create_surface_image, surface_backing_scale
            from .ui_chrome import action_button_image

            density = surface_backing_scale(widget)
            state = (
                "disabled"
                if "disabled" in states
                else "pressed"
                if "pressed" in states
                else "hover"
                if "active" in states
                else "normal"
            )
            focused = "focus" in states
            identity = (
                width,
                height,
                name,
                state,
                focused,
                density,
                theme_palette_snapshot(),
            )
            if identity != self.control_identity:
                bitmap = action_button_image(
                    width,
                    height,
                    accent="Accent" in name,
                    state=state,
                    density=density,
                    focused=focused,
                )
                self.control_photo = create_surface_image(
                    self.canvas, bitmap, density, logical_size=(width, height)
                )[0]
                self.control_identity = identity
            self.canvas.create_image(
                0, 0, anchor="nw", image=self.control_photo, tags="matte-text"
            )
        picture = option("image", "")
        if picture:
            # Existing image and alpha remain owned by the original label.
            self.canvas.create_image(
                width / 2,
                height / 2,
                image=widget.tk.splitlist(picture)[0],
                tags="matte-text",
            )
        if text:
            self.canvas.create_text(
                x,
                y,
                text=text,
                anchor=cast(Any, anchor),
                font=option("font", ("TkDefaultFont", 11)),
                fill=option("foreground", THEME["text"]),
                justify=option("justify", "left"),
                width=int(option("wraplength", 0)),
                tags="matte-text",
            )

    def _document(self) -> None:
        widget = cast(tk.Text, self.widget)
        end = widget.index("end-1c")
        height = widget.winfo_height()
        viewport_width = widget.winfo_width()
        fonts: dict[str, tkfont.Font] = {}
        y_position = 0
        # Ask the native layout for each visible display row and its clipped
        # horizontal endpoints. Never walk the hidden tail of a long line.
        while y_position < height:
            index = widget.index(f"@0,{y_position}")
            if not widget.compare(index, "<", end):
                break
            line = widget.dlineinfo(index)
            if line is None:
                break
            row_y = max(y_position, line[1])
            index = widget.index(f"@0,{row_y}")
            last = widget.index(f"@{viewport_width},{row_y}")
            while widget.compare(index, "<=", last) and widget.compare(index, "<", end):
                box = widget.bbox(index)
                if box is None:
                    break
                x, y, width, line_height = box
                char = widget.get(index, index + " +1c")
                if width <= 0:
                    index = widget.index(index + " +1c")
                    continue
                if not char:
                    for kind, value, _position in widget.dump(
                        index, index + " +1c", image=True, window=True
                    ):
                        if kind == "image":
                            self.canvas.create_image(
                                x + width / 2,
                                y + line_height / 2,
                                image=widget.image_cget(value, "image"),
                                tags="matte-text",
                            )
                        elif kind == "window":
                            child = widget.nametowidget(value)
                            if isinstance(child, (tk.Label, ttk.Label)):
                                self.canvas.create_text(
                                    x,
                                    y + line_height / 2,
                                    anchor="w",
                                    text=child.cget("text"),
                                    font=child.cget("font"),
                                    fill=child.cget("foreground"),
                                    tags="matte-text",
                                )
                tags = widget.tag_names(index)
                foreground = str(widget.cget("fg"))
                font: Any = widget.cget("font")
                for tag in tags:
                    foreground = widget.tag_cget(tag, "foreground") or foreground
                    font = widget.tag_cget(tag, "font") or font
                if "sel" in tags:
                    self.canvas.create_rectangle(
                        x,
                        y,
                        x + width,
                        y + line_height,
                        fill=widget.cget("selectbackground"),
                        outline="",
                        tags="matte-text",
                    )
                    foreground = str(widget.cget("selectforeground")) or foreground
                if char not in ("\n", "\t"):
                    font_key = str(font)
                    if font_key not in fonts:
                        fonts[font_key] = tkfont.Font(root=widget, font=font)
                    font_metrics = fonts[font_key]
                    baseline = line[1] + line[4]
                    self.canvas.create_text(
                        x,
                        baseline - font_metrics.metrics("ascent"),
                        text=char,
                        anchor="nw",
                        font=font,
                        fill=foreground,
                        tags="matte-text",
                    )
                index = widget.index(index + " +1c")
            next_y = line[1] + line[3]
            if next_y <= y_position:
                break
            y_position = next_y

    def _destroy(self, event: tk.Event) -> None:
        if event.widget is not self.canvas or self.retired:
            return
        self.retired = True
        if self.pending:
            try:
                self.canvas.after_cancel(self.pending)
            except tk.TclError:
                pass
            self.pending = None
        self._remove_trace()
        for target, sequence, binding in self.bindings:
            try:
                target.unbind(sequence, binding)
            except tk.TclError:
                pass
        self.bindings.clear()
        self.control_photo = None
        for option, (callback, command) in self.view_callbacks.items():
            try:
                if str(self.widget.cget(option)) == command:
                    self._configure_original(**{option: callback})
                self.widget.deletecommand(command)
            except tk.TclError:
                pass
        self.view_callbacks.clear()
        self.widget.configure = self._configure_original  # type: ignore[method-assign]
        cast(Any, self.widget).config = self._configure_original


def enroll_matte_text(frame: tk.Misc) -> list[MatteTextProjection]:
    """Enroll read-only content and native actions, never editable fields."""
    pending = [frame]
    owners = []
    style = ttk.Style(frame)
    while pending:
        widget = pending.pop()
        pending.extend(widget.winfo_children())
        eligible = False
        if isinstance(widget, ttk.Button):
            eligible = True
        elif isinstance(widget, ttk.Label):
            name = str(widget.cget("style")) or "TLabel"
            eligible = str(style.lookup(name, "background")) == THEME["bg"]
        elif isinstance(widget, (tk.Label, tk.Text)):
            eligible = str(widget.cget("bg")) == THEME["bg"]
            if isinstance(widget, tk.Text):
                eligible = eligible and str(widget.cget("state")) == "disabled"
        if eligible and getattr(widget, "_matte_text_projection", None) is None:
            owner = MatteTextProjection(widget, frame)
            cast(Any, widget)._matte_text_projection = owner
            owners.append(owner)
    return owners
