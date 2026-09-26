from __future__ import annotations

import colorsys
import re
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from .platform_services import platform_font_families


def _matte_palette(seed: str) -> dict[str, str]:
    """Monochrome materials with a separate, restrained foreground palette."""
    rgb = tuple(int(seed[i : i + 2], 16) / 255 for i in (1, 3, 5))
    hue, _light, saturation = colorsys.rgb_to_hls(*rgb)
    saturation = min(0.30, saturation)

    def tone(light: float, chroma: float = 1.0) -> str:
        channels = colorsys.hls_to_rgb(hue, light, saturation * chroma)
        return "#" + "".join(f"{round(c * 255):02x}" for c in channels)

    return {
        "bg": tone(0.19, 0.40),
        "panel": tone(0.19, 0.40),
        "surface": tone(0.195, 0.40),
        "surface_2": tone(0.22, 0.40),
        "focus_surface": tone(0.145, 0.40),
        "text": tone(0.95, 0.40),
        "muted": tone(0.80, 0.35),
        "subtle": tone(0.51, 0.40),
        "accent": tone(0.70),
        "accent_dark": tone(0.22, 0.40),
        "accent_surface": tone(0.20, 0.40),
        "action": tone(0.70),
        "icon": tone(0.70),
        "selection": "#bda0ff",
        "progress": "#bda0ff",
        "success": "#93d9b2",
        "warning": "#f2c078",
        "danger": "#ffadb7",
        "border": tone(0.29, 0.48),
        "focus": tone(0.82),
        "on_accent": tone(0.98, 0.30),
    }


_THEME_SEEDS = {
    "Violet": "#a895c9",
    "Cobalt": "#8ca8ca",
    "Jade": "#94b7a3",
    "Ember": "#c2a38b",
    "Rose": "#c49bab",
}
MATERIAL_ROLES: Final = (
    "bg",
    "panel",
    "surface",
    "surface_2",
    "focus_surface",
    "accent",
    "accent_dark",
    "accent_surface",
    "border",
)
FOREGROUND_ROLES: Final = (
    "action",
    "icon",
    "selection",
    "progress",
    "success",
    "warning",
    "danger",
)
THEME_PRESETS: Final = MappingProxyType(
    {name: _matte_palette(seed) for name, seed in _THEME_SEEDS.items()}
)
_BASE_THEME: Final[dict[str, str]] = dict(THEME_PRESETS["Violet"])
THEME_MOTIFS: Final = MappingProxyType(
    {
        "Violet": "smoke",
        "Cobalt": "splatter",
        "Jade": "blossoms",
        "Ember": "splatter",
        "Rose": "blossoms",
        "Custom accent": "smoke",
    }
)
_active_theme_name = "Violet"


def theme_motif() -> str:
    return THEME_MOTIFS[_active_theme_name]


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

    return tuple(sorted((*THEME.items(), ("@motif", theme_motif()))))


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
        if isinstance(widget, tk.Text):
            for tag in widget.tag_names():
                for option in ("foreground", "background"):
                    current = str(widget.tag_cget(tag, option))
                    if current in replacements:
                        widget.tag_configure(tag, **{option: replacements[current]})
        if isinstance(widget, tk.Menu):
            last = widget.index("end")
            for index in range((last + 1) if last is not None else 0):
                if widget.type(index) in {"separator", "tearoff"}:
                    continue
                for option in (
                    "foreground",
                    "background",
                    "activeforeground",
                    "activebackground",
                ):
                    current = str(widget.entrycget(index, option))
                    if current in replacements:
                        widget.entryconfigure(index, {option: replacements[current]})
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


def normalize_hex_color(value: object, fallback: str = "#796aff") -> str:
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
    name: object, custom_accent: object = "#796aff"
) -> ThemeSelection:
    """Apply one validated startup palette to the shared widget color contract."""

    global _active_theme_name
    selected = str(name or DEFAULT_THEME_NAME).strip()
    if selected not in THEME_NAMES:
        selected = DEFAULT_THEME_NAME
    accent = normalize_hex_color(custom_accent)
    palette = dict(_BASE_THEME)
    if selected == CUSTOM_THEME_NAME:
        palette.update(_matte_palette(accent))
    else:
        palette.update(THEME_PRESETS[selected])
    _active_theme_name = selected
    THEME.clear()
    THEME.update(palette)
    return ThemeSelection(selected, accent)


THEME: Final[dict[str, str]] = dict(_BASE_THEME)

FONT_UI_FAMILY, FONT_MONO_FAMILY = platform_font_families()
FONT_UI = (FONT_UI_FAMILY, 11)
FONT_UI_SMALL = (FONT_UI_FAMILY, 10)
FONT_UI_EMPHASIS_FAMILY = (
    "Helvetica Neue Medium"
    if FONT_UI_FAMILY == "Helvetica Neue"
    else "Segoe UI Semibold"
    if FONT_UI_FAMILY == "Segoe UI"
    else FONT_UI_FAMILY
)
FONT_UI_MEDIUM = (FONT_UI_EMPHASIS_FAMILY, 11, "normal")
FONT_UI_SMALL_MEDIUM = (FONT_UI_EMPHASIS_FAMILY, 10, "normal")
FONT_TITLE = (FONT_UI_FAMILY, 22, "bold")
FONT_MONO = (FONT_MONO_FAMILY, 9)
