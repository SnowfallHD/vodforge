"""Shared action-button metrics; rendering adapters keep native input ownership."""

from __future__ import annotations

from dataclasses import dataclass
from tkinter import font as tkfont
from tkinter import ttk
from typing import Literal

from .ui_theme import FONT_UI_FAMILY

ButtonSize = Literal["default", "compact", "inline"]


@dataclass(frozen=True)
class ButtonMetrics:
    height: int
    font_pixels: int
    horizontal_padding: int = 16
    icon_pixels: int = 18

    @property
    def font(self) -> tuple[str, int, Literal["normal"]]:
        return FONT_UI_FAMILY, -self.font_pixels, "normal"


# Resolve at render/style-application time; adapters must not copy these values.
BUTTON_METRICS: dict[ButtonSize, ButtonMetrics] = {
    "default": ButtonMetrics(height=44, font_pixels=15),
    "compact": ButtonMetrics(height=40, font_pixels=14),
    "inline": ButtonMetrics(height=32, font_pixels=14),
}


def button_metrics(size: ButtonSize = "default") -> ButtonMetrics:
    return BUTTON_METRICS[size]


# Existing names are compatibility aliases, not independent size definitions.
BUTTON_STYLE_SIZES: dict[str, ButtonSize] = {
    "TButton": "default",
    "Accent.TButton": "default",
    "FocusQuiet.TButton": "default",
    "Media.Accent.TButton": "default",
    "Media.FocusQuiet.TButton": "default",
    "Streaming.Media.FocusQuiet.TButton": "default",
    "Player.Media.Accent.TButton": "default",
    "Player.Media.FocusQuiet.TButton": "default",
    "Compact.TButton": "compact",
}


def apply_button_metrics(root, style: ttk.Style) -> None:
    """Apply metrics after chrome and legacy styles so aliases cannot override them.

    ProductChromeOwner uses a nine-pixel border on each side. The remaining
    vertical space belongs to the label and padding, with an asymmetric pixel
    allowed when the font line height is odd.
    """
    for name, size in BUTTON_STYLE_SIZES.items():
        spec = button_metrics(size)
        font = tkfont.Font(
            root=root, family=spec.font[0], size=spec.font[1], weight=spec.font[2]
        )
        remainder = max(0, spec.height - 18 - font.metrics("linespace"))
        vertical = remainder // 2
        horizontal = max(0, spec.horizontal_padding - 9)
        style.configure(
            name,
            font=spec.font,
            padding=(horizontal, vertical, horizontal, remainder - vertical),
        )


class ProductButton(ttk.Button):
    """Native ttk rendering/keys with per-instance pointer admission and retirement."""

    def __init__(self, master=None, **kwargs):
        if master is not None:
            from .ui_chrome import prototype_button_style

            kwargs["style"] = prototype_button_style(
                master, kwargs.get("style", "TButton")
            )
        super().__init__(master, **kwargs)
        self._pressed_command = None
        self.bind("<ButtonPress-1>", self._admit_pointer, add="+")
        self.bind("<ButtonRelease-1>", self._release_pointer, add="+")
        self.bind("<Unmap>", self._retire_pointer, add="+")
        self.bind("<<ViewInputRetired>>", self._retire_pointer, add="+")

    def _retire_pointer(self, _event=None):
        self._pressed_command = None
        super().state(["!pressed"])

    def _admit_pointer(self, event):
        self._pressed_command = (
            str(self.cget("command")) if not self.instate(["disabled"]) else None
        )

    def _release_pointer(self, event):
        admitted, self._pressed_command = self._pressed_command, None
        if (
            admitted is None
            or admitted != str(self.cget("command"))
            or self.instate(["disabled"])
            or not self.winfo_viewable()
            or not (
                0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
            )
        ):
            # The Tk 9 ttk release binding can invoke a pressed button even
            # outside its bounds. Retire its native pressed state before stopping
            # that class binding; keyboard activation remains native.
            super().state(["!pressed"])
            return "break"
        return None

    def state(self, statespec=None):
        if statespec is not None and "disabled" in statespec:
            self._pressed_command = None
        return super().state(statespec)

    def configure(self, cnf=None, **kwargs):
        if isinstance(cnf, dict) and "style" in cnf:
            from .ui_chrome import prototype_button_style

            cnf = {**cnf, "style": prototype_button_style(self, cnf["style"])}
        if "style" in kwargs:
            from .ui_chrome import prototype_button_style

            kwargs["style"] = prototype_button_style(self, kwargs["style"])
        if kwargs.get("state") == "disabled" or (
            isinstance(cnf, dict) and cnf.get("state") == "disabled"
        ):
            self._pressed_command = None
        return super().configure(cnf, **kwargs)

    config = configure
