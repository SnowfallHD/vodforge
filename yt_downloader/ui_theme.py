from __future__ import annotations

import re
import tkinter as tk
from collections.abc import Callable
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
    "accent_surface": "#20213a",
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


ThemePaletteSnapshot = tuple[tuple[str, str], ...]


def theme_palette_snapshot() -> ThemePaletteSnapshot:
    """Return the shared palette as an immutable render-comparison value."""

    return tuple(sorted(THEME.items()))


class ThemeRenderOwner:
    """Own live theme change detection and the single render decision."""

    def __init__(
        self,
        render: Callable[[ThemePaletteSnapshot, ThemePaletteSnapshot], None],
    ) -> None:
        self._render = render
        self._committed = theme_palette_snapshot()

    def request(self, name: object, custom_accent: object) -> bool:
        """Apply and render a changed palette; make repeated requests a no-op."""

        if str(name or "").strip() == CUSTOM_THEME_NAME and not re.fullmatch(
            r"#[0-9a-fA-F]{6}", str(custom_accent or "").strip()
        ):
            return False
        apply_theme_selection(name, custom_accent)
        incoming = theme_palette_snapshot()
        if incoming == self._committed:
            return False
        previous = self._committed
        self._committed = incoming
        self._render(previous, incoming)
        return True


def patch_tk_surface_palette(
    root: tk.Misc,
    previous: ThemePaletteSnapshot,
    incoming: ThemePaletteSnapshot,
) -> None:
    """Patch classic Tk colors within one surface; ttk remains style-owned."""

    before = dict(previous)
    after = dict(incoming)
    replacements = {
        color: after[key]
        for key, color in before.items()
        if key in after and after[key] != color
    }
    if not replacements:
        return
    pending: list[tk.Misc] = [root]
    color_options = (
        "background",
        "foreground",
        "activebackground",
        "activeforeground",
        "highlightbackground",
        "highlightcolor",
        "insertbackground",
        "selectbackground",
        "selectforeground",
        "troughcolor",
    )
    while pending:
        widget = pending.pop()
        for option in color_options:
            try:
                current = str(widget.cget(option))
                replacement = replacements.get(current)
                if replacement is not None:
                    widget.configure({option: replacement})
            except (AttributeError, tk.TclError):
                continue
        if isinstance(widget, tk.Canvas):
            try:
                for item in widget.find_all():
                    for option in ("fill", "outline"):
                        current = str(widget.itemcget(item, option))
                        replacement = replacements.get(current)
                        if replacement is not None:
                            widget.itemconfigure(item, {option: replacement})
            except tk.TclError:
                pass
        try:
            pending.extend(widget.winfo_children())
        except (AttributeError, tk.TclError):
            continue


def normalize_hex_color(value: object, fallback: str = "#7170ff") -> str:
    text = str(value or "").strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        return fallback
    return text.lower()


def _darken(color: str, factor: float = 0.78) -> str:
    channels = [int(color[index : index + 2], 16) for index in (1, 3, 5)]
    return "#" + "".join(f"{round(channel * factor):02x}" for channel in channels)


def _mix_hex(background: str, foreground: str, amount: float) -> str:
    """Blend one opaque UI color without introducing platform alpha behavior."""

    ratio = max(0.0, min(1.0, float(amount)))
    background_channels = [
        int(background[index : index + 2], 16) for index in (1, 3, 5)
    ]
    foreground_channels = [
        int(foreground[index : index + 2], 16) for index in (1, 3, 5)
    ]
    return "#" + "".join(
        f"{round(base + ((top - base) * ratio)):02x}"
        for base, top in zip(background_channels, foreground_channels, strict=True)
    )


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
    palette["accent_surface"] = _mix_hex(palette["surface"], palette["accent"], 0.18)
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
