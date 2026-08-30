from __future__ import annotations

from typing import Final

from .platform_services import platform_font_families

THEME: Final[dict[str, str]] = {
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

FONT_UI_FAMILY, FONT_MONO_FAMILY = platform_font_families()
FONT_UI = (FONT_UI_FAMILY, 10)
FONT_UI_SMALL = (FONT_UI_FAMILY, 9)
FONT_UI_MEDIUM = (FONT_UI_FAMILY, 10, "bold")
FONT_UI_SMALL_MEDIUM = (FONT_UI_FAMILY, 9, "bold")
FONT_TITLE = (FONT_UI_FAMILY, 22, "bold")
FONT_MONO = (FONT_MONO_FAMILY, 9)
