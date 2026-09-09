"""Rounded ttk chrome, without replacing native input/button semantics.

Each Tcl interpreter owns one image set. Palette requests update those images
in place; state changes are handled by ttk rather than widget reconstruction.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageTk

from .ui_theme import THEME, theme_palette_snapshot


def pro_wordmark(master: tk.Misc) -> ImageTk.PhotoImage:
    """Fixed brand colors, independent of the user's application accent.

    A transparent image leaves focus, hover, keyboard and invocation with ttk.
    Supersampling keeps the compact lettering crisp on high-density screens.
    """
    font = ImageFont.load_default(size=28)
    parts = (("VOD", "#7167ff"), ("Forge", "#f5f5f7"), (" PRO", "#7167ff"))
    widths = [font.getlength(text) for text, _color in parts]
    width = int(sum(widths) + 2)
    image = Image.new("RGBA", (width, 40))
    draw = ImageDraw.Draw(image)
    x = 0.0
    for (text, color), advance in zip(parts, widths, strict=True):
        draw.text((x, 20), text, font=font, fill=color, anchor="lm")
        x += advance
    return ImageTk.PhotoImage(
        image.resize((width // 2, 20), Image.Resampling.LANCZOS), master=master
    )


def field_border_image(
    width: int, height: int, *, hovered: bool = False
) -> Image.Image:
    """Canonical field chrome for ttk slices and full-size Canvas adapters.

    Focus never changes the border; editing/focus semantics remain widget-owned.
    Transparent corners work against the actual containing surface.
    """
    scale = 3
    image = Image.new("RGBA", (width * scale, height * scale))
    ImageDraw.Draw(image).rounded_rectangle(
        (2, 2, width * scale - 3, height * scale - 3),
        radius=24,
        fill=THEME["surface_2"] if hovered else THEME["surface"],
        outline=THEME["border"],
        width=scale,
    )
    return image.resize((width, height), Image.Resampling.LANCZOS)


def accent_hover_color() -> str:
    """Shared accent interaction color, including custom user themes."""
    return "#" + "".join(
        f"{round(channel + (255 - channel) * 0.22):02x}"
        for channel in ImageColor.getrgb(THEME["accent"])
    )


class RoundedFieldBorder:
    """Chrome only; the existing field retains editing and choice ownership."""

    def __init__(self, field: tk.Frame) -> None:
        self.field = field
        self.focused = False
        self.hovered = False
        self._committed: tuple[object, ...] | None = None
        self._image: ImageTk.PhotoImage | None = None
        tk.Frame.configure(field, highlightthickness=0, padx=1, pady=1)
        self.canvas = tk.Canvas(
            field, bd=0, highlightthickness=0, takefocus=False, bg=THEME["bg"]
        )
        # Chrome covers the entire shell, including its content padding. The
        # default inside mode exposes a square strip of the shell around it.
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1, bordermode="outside")
        field.tk.call("lower", str(self.canvas))
        self.item = self.canvas.create_image(0, 0, anchor="nw")
        field.bind(
            "<Configure>",
            lambda _event: self.request(self.focused, self.hovered),
            add="+",
        )

    def request(self, focused: bool = False, hovered: bool = False) -> None:
        self.focused, self.hovered = focused, hovered
        width, height = self.field.winfo_width(), self.field.winfo_height()
        fill = THEME["surface_2"] if hovered else THEME["surface"]
        outline = THEME["border"]
        snapshot = (width, height, fill, outline, THEME["bg"])
        if snapshot == self._committed or width < 2 or height < 2:
            return
        self.canvas.configure(bg=THEME["bg"])
        image = field_border_image(width, height, hovered=hovered)
        self._image = ImageTk.PhotoImage(image, master=self.field)
        self.canvas.itemconfigure(self.item, image=self._image)
        self._committed = snapshot


class ProductChromeOwner:
    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self.images: dict[str, ImageTk.PhotoImage] = {}
        self._committed: tuple[tuple[str, str], ...] | None = None

    def request(self, style: ttk.Style) -> None:
        snapshot = theme_palette_snapshot()
        if self._committed == snapshot:
            return
        accent_hover = accent_hover_color()
        roles = {
            "button": (THEME["surface_2"], THEME["border"]),
            "hover": (THEME["border"], THEME["muted"]),
            "pressed": (THEME["surface"], THEME["accent"]),
            "focus": (THEME["surface_2"], THEME["border"]),
            "disabled": (THEME["panel"], THEME["border"]),
            "accent": (THEME["accent"], THEME["accent"]),
            "accent_hover": (accent_hover, accent_hover),
            "field": (THEME["surface"], THEME["border"]),
            "field_focus": (THEME["surface"], THEME["border"]),
            "transport": (THEME["bg"], THEME["accent"]),
            "transport_hover": (THEME["surface_2"], THEME["accent"]),
        }
        first = not self.images
        for name, (fill, outline) in roles.items():
            is_transport = name.startswith("transport")
            size = 40 if is_transport else 28
            if name in ("field", "field_focus"):
                image = field_border_image(size, size)
            else:
                pixels = size * 3
                image = Image.new("RGBA", (pixels, pixels))
                ImageDraw.Draw(image).rounded_rectangle(
                    (2, 2, pixels - 3, pixels - 3),
                    radius=60 if is_transport else 24,
                    fill=fill,
                    outline=outline,
                    width=3,
                )
                image = image.resize((size, size), Image.Resampling.LANCZOS)
            if name in self.images:
                self.images[name].paste(image)
            else:
                self.images[name] = ImageTk.PhotoImage(image, master=self.root)
        if first:
            self._install(style)
        self._committed = snapshot

    def _install(self, style: ttk.Style) -> None:
        def element(
            name: str, default: str, states: tuple[tuple[str, str], ...]
        ) -> None:
            style.element_create(
                name,
                "image",
                self.images[default],
                *((state, self.images[image]) for state, image in states),
                border=9,
                sticky="nsew",
            )

        element(
            "Product.button",
            "button",
            (
                ("disabled", "disabled"),
                ("pressed", "pressed"),
                ("focus", "focus"),
                ("active", "hover"),
            ),
        )
        element(
            "Product.accent",
            "accent",
            (
                ("disabled", "disabled"),
                ("pressed", "pressed"),
                ("active", "accent_hover"),
                ("focus", "accent_hover"),
            ),
        )
        element("Product.field", "field", (("focus", "field_focus"),))
        style.element_create(
            "Product.transport",
            "image",
            self.images["transport"],
            ("active", self.images["transport_hover"]),
            ("focus", self.images["transport_hover"]),
            border=0,
        )
        style.layout(
            "Transport.TButton",
            [("Product.transport", {"children": [("Button.label", {"sticky": ""})]})],
        )
        for name, chrome in (
            ("TButton", "Product.button"),
            ("Compact.TButton", "Product.button"),
            ("FocusQuiet.TButton", "Product.button"),
            ("Accent.TButton", "Product.accent"),
        ):
            style.layout(
                name,
                [
                    (
                        chrome,
                        {
                            "sticky": "nsew",
                            "children": [
                                (
                                    "Button.padding",
                                    {
                                        "sticky": "nsew",
                                        "children": [
                                            ("Button.label", {"sticky": "nsew"})
                                        ],
                                    },
                                )
                            ],
                        },
                    )
                ],
            )
        style.layout(
            "Product.TEntry",
            [
                (
                    "Product.field",
                    {
                        "sticky": "nsew",
                        "children": [
                            (
                                "Entry.padding",
                                {
                                    "sticky": "nsew",
                                    "children": [
                                        ("Entry.textarea", {"sticky": "nsew"})
                                    ],
                                },
                            )
                        ],
                    },
                )
            ],
        )


def apply_product_chrome(root: Any, style: ttk.Style) -> None:
    owner = getattr(root, "_product_chrome_owner", None)
    if owner is None:
        owner = ProductChromeOwner(root)
        root._product_chrome_owner = owner
    owner.request(style)
    # ttk paints transparent image corners using the style background. The
    # image owns every state fill; inherited legacy fills must not square it off.
    for role in ("TButton", "Compact.TButton", "FocusQuiet.TButton", "Accent.TButton"):
        style.configure(role, background=THEME["bg"], padding=(9, 1))
        style.map(role, background=[("active", THEME["bg"]), ("disabled", THEME["bg"])])
    # Nine-slice borders already provide inner clearance; do not double it.
    style.configure(
        "Product.TEntry", padding=(4, 0), borderwidth=0, background=THEME["bg"]
    )
    style.configure("Transport.TButton", padding=0, width=0)
    style.map(
        "Product.TEntry",
        background=[
            ("readonly", THEME["bg"]),
            ("focus", THEME["bg"]),
            ("disabled", THEME["bg"]),
        ],
        fieldbackground=[
            ("readonly", THEME["surface"]),
            ("disabled", THEME["surface"]),
        ],
        foreground=[("disabled", THEME["subtle"])],
    )
