"""Shared action-button metrics; rendering adapters keep native input ownership."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .product_theme import FONT_UI_FAMILY

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


BUTTON_METRICS: dict[ButtonSize, ButtonMetrics] = {
    "default": ButtonMetrics(height=44, font_pixels=15),
    "compact": ButtonMetrics(height=40, font_pixels=14),
    "inline": ButtonMetrics(height=32, font_pixels=14),
}


def button_metrics(size: ButtonSize = "default") -> ButtonMetrics:
    return BUTTON_METRICS[size]


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
