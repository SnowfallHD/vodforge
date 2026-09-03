from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from .platform_services import platform_font_families

_BASE_THEME: Final[dict[str, str]] = {
    "bg": "#08090a",
    "panel": "#0d0f12",
    "surface": "#121419",
    "surface_2": "#1a1d24",
    "text": "#f7f8f8",
    "muted": "#9297a3",
    "subtle": "#636874",
    "accent": "#7170ff",
    "accent_dark": "#5e6ad2",
    "success": "#35d07f",
    "warning": "#e8b15e",
    "danger": "#ff7a7a",
    "border": "#2b2e37",
}

THEME_PRESETS: Final = MappingProxyType(
    {
        "Violet": {
            "bg": "#08090a",
            "panel": "#0d0f12",
            "surface": "#121419",
            "surface_2": "#1a1d24",
            "border": "#2b2e37",
            "accent": "#7170ff",
            "accent_dark": "#5e6ad2",
        },
        "Cobalt": {
            "bg": "#070a0f",
            "panel": "#0b1119",
            "surface": "#101821",
            "surface_2": "#182331",
            "border": "#29384a",
            "accent": "#4f9cff",
            "accent_dark": "#3978cc",
        },
        "Jade": {
            "bg": "#070b0a",
            "panel": "#0b1210",
            "surface": "#111a17",
            "surface_2": "#19251f",
            "border": "#2a3a33",
            "accent": "#42d69b",
            "accent_dark": "#2da878",
        },
        "Ember": {
            "bg": "#0c0907",
            "panel": "#140f0b",
            "surface": "#1b1510",
            "surface_2": "#281f18",
            "border": "#403127",
            "accent": "#ff9955",
            "accent_dark": "#cf7034",
        },
        "Rose": {
            "bg": "#0c080b",
            "panel": "#140d12",
            "surface": "#1c1319",
            "surface_2": "#291c25",
            "border": "#412e3b",
            "accent": "#ef75b5",
            "accent_dark": "#bf528b",
        },
    }
)
CUSTOM_THEME_NAME: Final = "Custom accent"
THEME_NAMES: Final[tuple[str, ...]] = (*THEME_PRESETS, CUSTOM_THEME_NAME)
DEFAULT_THEME_NAME: Final = "Violet"


@dataclass(frozen=True, slots=True)
class ThemeSelection:
    name: str
    custom_accent: str


def normalize_hex_color(value: object, fallback: str = "#7170ff") -> str:
    text = str(value or "").strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        return fallback
    return text.lower()


def _darken(color: str, factor: float = 0.78) -> str:
    channels = [int(color[index : index + 2], 16) for index in (1, 3, 5)]
    return "#" + "".join(f"{round(channel * factor):02x}" for channel in channels)


def apply_theme_selection(
    name: object, custom_accent: object = "#7170ff"
) -> ThemeSelection:
    """Apply one validated startup palette to the shared widget color contract."""

    selected = str(name or DEFAULT_THEME_NAME).strip()
    if selected not in THEME_NAMES:
        selected = DEFAULT_THEME_NAME
    accent = normalize_hex_color(custom_accent)
    palette = dict(_BASE_THEME)
    if selected == CUSTOM_THEME_NAME:
        palette.update(THEME_PRESETS[DEFAULT_THEME_NAME])
        palette.update(accent=accent, accent_dark=_darken(accent))
    else:
        palette.update(THEME_PRESETS[selected])
    THEME.clear()
    THEME.update(palette)
    return ThemeSelection(selected, accent)


THEME: Final[dict[str, str]] = dict(_BASE_THEME)

FONT_UI_FAMILY, FONT_MONO_FAMILY = platform_font_families()
FONT_UI = (FONT_UI_FAMILY, 10)
FONT_UI_SMALL = (FONT_UI_FAMILY, 9)
FONT_UI_MEDIUM = (FONT_UI_FAMILY, 10, "bold")
FONT_UI_SMALL_MEDIUM = (FONT_UI_FAMILY, 9, "bold")
FONT_TITLE = (FONT_UI_FAMILY, 22, "bold")
FONT_MONO = (FONT_MONO_FAMILY, 9)
