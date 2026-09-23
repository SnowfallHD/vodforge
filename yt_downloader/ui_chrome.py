"""Rounded ttk chrome, without replacing native input/button semantics.

Each Tcl interpreter owns one image set. Palette requests update those images
in place; state changes are handled by ttk rather than widget reconstruction.
"""

from __future__ import annotations

import tkinter as tk
from collections import OrderedDict
from contextlib import contextmanager
from tkinter import ttk
from typing import Any, cast
from weakref import ref

from PIL import (
    Image,
    ImageChops,
    ImageColor,
    ImageDraw,
    ImageFilter,
    ImageFont,
    ImageOps,
    ImageTk,
)

from .platform_services import create_surface_image, surface_backing_scale
from .ui_layout import WindowLogicalMetrics, window_logical_metrics
from .ui_materials import tint_brand
from .ui_theme import THEME, theme_palette_snapshot


def brand_mark(master: tk.Misc, size: int = 32) -> Any:
    """Sample approved artwork directly at the display's physical density."""
    from .app import bundled_asset_path

    size = window_logical_metrics(master).px(size)
    scale = surface_backing_scale(master)
    pixels = size * scale
    with Image.open(bundled_asset_path("brand/vf-mark.png")) as source:
        mark = ImageOps.contain(
            tint_brand(source), (pixels, pixels), Image.Resampling.LANCZOS
        )
    image = Image.new("RGBA", (pixels, pixels))
    image.alpha_composite(
        mark, ((pixels - mark.width) // 2, (pixels - mark.height) // 2)
    )
    return create_surface_image(master, image, scale, logical_size=(size, size))[0]


def brand_name(master: tk.Misc, height: int = 22) -> Any:
    """Preserve native-density name artwork without a low-resolution upscale."""
    from .app import bundled_asset_path

    height = window_logical_metrics(master).px(height)
    scale = surface_backing_scale(master)
    with Image.open(bundled_asset_path("brand/vf-name.png")) as source:
        wordmark = tint_brand(source, wordmark=True)
    width = round(wordmark.width * height / wordmark.height)
    pixels = wordmark.resize((width * scale, height * scale), Image.Resampling.LANCZOS)
    return create_surface_image(master, pixels, scale, logical_size=(width, height))[0]


def pro_wordmark(master: tk.Misc) -> Any:
    """Fixed brand colors, independent of the user's application accent.

    A transparent image leaves focus, hover, keyboard and invocation with ttk.
    Supersampling keeps the compact lettering crisp on high-density screens.
    """
    metrics = window_logical_metrics(master)
    density = surface_backing_scale(master)
    sampling = metrics.scale * density
    font = ImageFont.load_default(size=28 * sampling)
    parts = (
        ("VOD", THEME["text"]),
        ("Forge", THEME["text"]),
        (" PRO", THEME["accent"]),
    )
    widths = [font.getlength(text) for text, _color in parts]
    base_font = ImageFont.load_default(size=28)
    logical_width = metrics.px(
        int(sum(base_font.getlength(text) for text, _ in parts) + 2) // 2
    )
    logical_height = metrics.px(20)
    image = Image.new(
        "RGBA", (logical_width * density * 2, logical_height * density * 2)
    )
    draw = ImageDraw.Draw(image)
    x = 0.0
    for (text, color), advance in zip(parts, widths, strict=True):
        draw.text((x, 20 * sampling), text, font=font, fill=color, anchor="lm")
        x += advance
    pixels = image.resize(
        (logical_width * density, logical_height * density), Image.Resampling.LANCZOS
    )
    return create_surface_image(
        master, pixels, density, logical_size=(logical_width, logical_height)
    )[0]


def _blend_color(base: str, light: str, amount: float) -> str:
    return "#" + "".join(
        f"{round(a + (b - a) * amount):02x}"
        for a, b in zip(ImageColor.getrgb(base), ImageColor.getrgb(light), strict=True)
    )


def rounded_alpha(width: int, height: int, radius: int) -> Image.Image:
    """Antialias only the small corners, avoiding a supersized full-scene mask."""
    radius = max(0, min(radius, width // 2, height // 2))
    mask = Image.new("L", (width, height), 255)
    if not radius:
        return mask
    disk = Image.new("L", (radius * 4, radius * 4))
    ImageDraw.Draw(disk).ellipse((0, 0, radius * 4 - 1, radius * 4 - 1), fill=255)
    corner = disk.resize((radius * 2, radius * 2), Image.Resampling.LANCZOS).crop(
        (0, 0, radius, radius)
    )
    for tile, position in (
        (corner, (0, 0)),
        (corner.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (width - radius, 0)),
        (corner.transpose(Image.Transpose.FLIP_TOP_BOTTOM), (0, height - radius)),
        (
            corner.transpose(Image.Transpose.ROTATE_180),
            (width - radius, height - radius),
        ),
    ):
        mask.paste(tile, position)
    return mask


def _shift_mask(mask: Image.Image, x: int, y: int) -> Image.Image:
    shifted = Image.new("L", mask.size)
    shifted.paste(mask, (x, y))
    return shifted


def _matte_lighting(mask: Image.Image, *, recessed: bool, depth: float, density: int):
    """Shared diffuse material bands; no semantic-color state perimeter."""
    for dx, dy, color, strength in (
        (3, 3, "#000000" if recessed else "#ffffff", 0.70 if recessed else 0.10),
        (-3, -3, "#ffffff" if recessed else "#000000", 0.13 if recessed else 0.24),
    ):
        band = ImageChops.subtract(mask, _shift_mask(mask, dx * density, dy * density))
        band = ImageChops.multiply(
            band.filter(ImageFilter.GaussianBlur(2.2 * density)), mask
        )
        band = band.point(lambda n, strength=strength: round(n * strength * depth))
        yield color, band


def _matte_rim(
    image: Image.Image,
    fill: str,
    edge: str,
    radius: int,
    *,
    recessed: bool = False,
    depth: float = 1.0,
    density: int = 1,
) -> Image.Image:
    """Diffuse inner light and occlusion, rather than concentric bevel lines."""
    width, height = image.size
    if edge == THEME["focus"]:
        fill = THEME["focus_surface"]
        image = Image.new("RGBA", image.size, fill)
        recessed, depth = True, 0.9
    mask = rounded_alpha(width, height, radius)
    for color, band in _matte_lighting(
        mask, recessed=recessed, depth=depth, density=density
    ):
        image = Image.composite(Image.new("RGBA", image.size, color), image, band)
    image.putalpha(mask)
    return image


def ttk_surface_image(
    width: int,
    *,
    fill: str,
    edge: str,
    height: int | None = None,
    recessed: bool = False,
    depth: float = 1.0,
    radius: int = 10,
    density: int = 1,
    stretch: bool = True,
    inset_face: bool = False,
    unit_scale: int = 1,
) -> Image.Image:
    """Crisp face, contour contact shadow and separate diffuse ambient light."""
    if edge == THEME["focus"]:
        fill, recessed, depth = THEME["focus_surface"], True, 0.9
    density = max(1, int(density))
    width = max(1, width) * density
    height = max(1, height if height is not None else width // density) * density
    density *= unit_scale
    radius = min(radius, 9) * density if stretch else radius * density
    if (not recessed or inset_face) and min(width, height) >= 16 * density:
        image = Image.new("RGBA", (width, height))
        inset = (3 if stretch else 5) * density
        face_mask = Image.new("L", image.size)
        face_radius = max(
            2 * density, radius - inset if stretch else radius - 3 * density
        )
        face_mask.paste(
            rounded_alpha(width - 2 * inset, height - 2 * inset, face_radius),
            (inset, inset),
        )
        # All three layers derive from the exact same rounded face silhouette.
        shadow_layers = (
            ()
            if recessed
            else (
                (2, 3, 3.2, "#000000", 0.24),
                (-2, -2, 3.0, "#ffffff", 0.075),
                (1, 2, 0.65, "#000000", 0.38),
            )
        )
        for dx, dy, blur, color, opacity in shadow_layers:
            shadow = Image.new("RGBA", image.size, color)
            shadow.putalpha(
                _shift_mask(face_mask, dx * density, dy * density)
                .filter(ImageFilter.GaussianBlur(blur * density))
                .point(lambda n, opacity=opacity: round(n * opacity * depth))
            )
            image = Image.alpha_composite(image, shadow)
        face = _matte_rim(
            Image.new("RGBA", (width - 2 * inset, height - 2 * inset), fill),
            fill,
            edge,
            face_radius,
            recessed=recessed,
            depth=depth if recessed else depth * 0.25,
            density=density,
        )
        image.alpha_composite(face, (inset, inset))
        # Rounded finite support, not a rectangular attenuation envelope.
        fade = Image.new("L", image.size)
        draw = ImageDraw.Draw(fade)
        for offset in range(1, 3 * density + 1):
            t = offset / (3 * density)
            draw.rounded_rectangle(
                (offset, offset, width - 1 - offset, height - 1 - offset),
                radius=max(1, radius + 3 * density - offset),
                fill=round(255 * t * t * (3 - 2 * t)),
            )
        image.putalpha(ImageChops.multiply(image.getchannel("A"), fade))
    else:
        image = _matte_rim(
            Image.new("RGBA", (width, height), fill),
            fill,
            edge,
            radius,
            recessed=recessed,
            depth=depth,
            density=density,
        )
    border = 9 * density
    if stretch and width > 2 * border and height > 2 * border:
        midx, midy = width // 2, height // 2
        horizontal = image.crop((midx, 0, midx + 1, height)).resize(
            (width - 2 * border, height)
        )
        vertical = image.crop((0, midy, width, midy + 1)).resize(
            (width, height - 2 * border)
        )
        image.paste(horizontal, (border, 0))
        image.paste(vertical, (0, border))
        image.paste(
            Image.new(
                "RGBA",
                (width - 2 * border, height - 2 * border),
                image.getpixel((midx, midy)),
            ),
            (border, border),
        )
    return image


def layered_surface_image(
    width: int,
    height: int,
    *,
    fill: str,
    edge: str = "",
    illumination: float = 0.0,
    radius: int = 9,
    ambient: bool = False,
) -> Image.Image:
    """A softly lit product surface; all color comes from the active palette."""
    width, height = max(1, width), max(1, height)
    top = _blend_color(fill, "#ffffff", 0.022 if ambient else 0.025)
    bottom = _blend_color(fill, "#000000", 0.02 if ambient else 0.09)
    ramp = Image.linear_gradient("L").resize((width, height))
    surface = ImageOps.colorize(ramp, top, bottom).convert("RGBA")
    if illumination:
        # Lighting is calculated at a small fixed resolution, then interpolated.
        # Resize and scrolling never run a full-resolution blur.
        light = Image.new("L", (96, 64))
        draw = ImageDraw.Draw(light)
        draw.ellipse((-35, -42, 76, 57), fill=round(255 * illumination))
        light = light.filter(ImageFilter.GaussianBlur(20)).resize(
            (width, height), Image.Resampling.BILINEAR
        )
        tint = Image.new("RGBA", (width, height), THEME["accent"])
        surface = Image.composite(tint, surface, light)
    if ambient:
        # Fade in as well as out so the page never starts with a hard rectangle.
        fade = Image.new("L", (1, 96))
        fade.putdata(
            [round(255 * (4 * (y / 95) * (1 - y / 95)) ** 2) for y in range(96)]
        )
        return Image.composite(
            surface,
            Image.new("RGBA", (width, height), fill),
            fade.resize((width, height)),
        )
    return _matte_rim(surface, fill, edge, radius, depth=0.48)


def field_border_image(
    width: int,
    height: int,
    *,
    hovered: bool = False,
    focused: bool = False,
    stretch: bool = False,
    density: int = 1,
    unit_scale: int = 1,
) -> Image.Image:
    """Shared inset field surface for ttk slices and canvas-owned controls."""
    return ttk_surface_image(
        width,
        height=height,
        fill=THEME["surface"],
        edge=_blend_color(THEME["surface"], THEME["border"], 0.65),
        recessed=True,
        depth=0.72 if focused or hovered else 0.5,
        stretch=stretch,
        density=density,
        unit_scale=unit_scale,
    )


def primary_action_color() -> str:
    return _blend_color(THEME["surface"], THEME["surface_2"], 0.15)


def control_material_roles() -> dict[str, tuple[str, str]]:
    """Return the shared ttk face and contour colors for interaction states.

    Hover keeps the idle colors and uses an inset contour in the image owner.
    Focus remains a separate, high-contrast accessibility state.
    """
    return {
        "button": (
            THEME["surface"],
            _blend_color(THEME["surface"], THEME["border"], 0.58),
        ),
        "hover": (
            THEME["surface"],
            _blend_color(THEME["surface"], THEME["border"], 0.58),
        ),
        "pressed": (THEME["surface"], THEME["accent_dark"]),
        "focus": (THEME["surface"], THEME["focus"]),
        "disabled": (
            THEME["panel"],
            _blend_color(THEME["panel"], THEME["border"], 0.35),
        ),
        "accent": (primary_action_color(), THEME["accent"]),
        "accent_hover": (primary_action_color(), THEME["accent"]),
        "accent_focus": (primary_action_color(), THEME["focus"]),
        "nav_idle": (THEME["bg"], THEME["bg"]),
        "nav_hover": (THEME["bg"], THEME["bg"]),
        "nav_focus": (THEME["bg"], THEME["accent"]),
        "nav_pressed": (THEME["surface"], THEME["accent_dark"]),
        # Selection retains the impressed material and semantic icon/text roles.
        # Keyboard focus deepens the selected well without another perimeter.
        "nav_selected_focus": (THEME["bg"], THEME["focus"]),
        "nav_selected": (THEME["bg"], THEME["bg"]),
        "field": (THEME["surface"], THEME["border"]),
        "field_focus": (THEME["surface"], THEME["focus"]),
        "transport": (
            THEME["accent_dark"],
            _blend_color(THEME["accent"], "#ffffff", 0.14),
        ),
        "transport_hover": (
            THEME["accent_dark"],
            _blend_color(THEME["accent"], "#ffffff", 0.14),
        ),
        "transport_pressed": (THEME["accent_dark"], THEME["border"]),
        "transport_focus": (primary_action_color(), THEME["focus"]),
        "transport_disabled": (THEME["panel"], THEME["border"]),
        "panel": (THEME["panel"], _blend_color(THEME["panel"], THEME["border"], 0.42)),
    }


def action_button_image(
    width: int,
    height: int,
    *,
    accent: bool,
    state: str = "normal",
    density: int = 1,
    focused: bool = False,
    unit_scale: int = 1,
) -> Image.Image:
    """Shared raised and inset interaction faces for scene actions.

    Hover communicates affordance through an inward material contour, never a
    brighter accent border.  Keyboard focus remains the distinct, high-contrast
    state and pressed retains the deeper version of the same contour.
    """
    fill = primary_action_color() if accent else THEME["surface"]
    if state == "pressed":
        fill = _blend_color(fill, THEME["bg"], 0.18)
    if state == "disabled":
        fill = _blend_color(fill, THEME["bg"], 0.65)
    edge = (
        THEME["focus"]
        if focused or state == "focus"
        else _blend_color(fill, THEME["accent"], 0.28 if accent else 0.14)
    )
    return ttk_surface_image(
        width,
        height=height,
        fill=fill,
        edge=edge,
        recessed=state in {"hover", "pressed"},
        depth=0.2 if state == "disabled" else 0.72 if state == "hover" else 1.0,
        density=density,
        stretch=False,
        inset_face=True,
        unit_scale=unit_scale,
    )


def navigation_button_image(
    width: int,
    height: int,
    *,
    background: str,
    selected: bool = False,
    state: str = "normal",
    density: int = 1,
    transparent: bool = True,
    unit_scale: int = 1,
) -> Image.Image:
    """Interactive navigation rests raised and uses the same face when impressed."""
    image = ttk_surface_image(
        width,
        height=height,
        fill=background,
        edge=THEME["focus"] if state == "focus" else "",
        recessed=selected or state in {"hover", "pressed", "focus"},
        depth=0.9
        if state == "focus"
        else 1.0
        if state == "pressed"
        else 0.8
        if selected
        else 0.62
        if state == "hover"
        else 1.0,
        density=density,
        stretch=True,
        inset_face=True,
        unit_scale=unit_scale,
    )
    if not transparent:
        base = Image.new("RGBA", image.size, background)
        base.alpha_composite(image)
        return base
    return image


def watch_welcome_emblem() -> Image.Image:
    """A small decorative media card; no scene-sized bitmap or new UI control."""
    scale = 2
    image = Image.new("RGBA", (256 * scale, 218 * scale))
    clouds = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(clouds)
    tint = ImageColor.getrgb(_blend_color(THEME["bg"], THEME["accent"], 0.42))
    for x, y, radius in ((186, 32, 28), (217, 47, 19), (39, 144, 23), (18, 158, 17)):
        draw.ellipse(
            (
                (x - radius) * scale,
                (y - radius) * scale,
                (x + radius) * scale,
                (y + radius) * scale,
            ),
            fill=(*tint, 125),
        )
    image.alpha_composite(clouds.filter(ImageFilter.GaussianBlur(1.5)))
    glow = Image.new("RGBA", image.size)
    ImageDraw.Draw(glow).rounded_rectangle(
        (29 * scale, 45 * scale, 227 * scale, 204 * scale),
        radius=22 * scale,
        fill=(*ImageColor.getrgb(THEME["accent"]), 36),
    )
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(10 * scale)))
    card = layered_surface_image(
        192 * scale,
        150 * scale,
        fill=_blend_color(THEME["panel"], THEME["accent"], 0.13),
        edge=_blend_color(THEME["panel"], THEME["accent"], 0.62),
        illumination=0.28,
        radius=20 * scale,
    )
    image.alpha_composite(card, (32 * scale, 48 * scale))
    draw = ImageDraw.Draw(image)
    accent = _blend_color(THEME["accent"], "#ffffff", 0.10)
    draw.rounded_rectangle(
        (70 * scale, 157 * scale, 183 * scale, 164 * scale),
        radius=3 * scale,
        fill=THEME["accent_dark"],
    )
    draw.rounded_rectangle(
        (70 * scale, 175 * scale, 153 * scale, 182 * scale),
        radius=3 * scale,
        fill=THEME["accent_dark"],
    )
    draw.polygon(
        (
            (112 * scale, 83 * scale),
            (112 * scale, 130 * scale),
            (151 * scale, 106.5 * scale),
        ),
        fill=accent,
    )
    return image.resize((256, 218), Image.Resampling.LANCZOS)


class CanvasSurfaceCache:
    """Own displayed images for their item lifetime and bound unused reuse.

    A canvas keeps only a Tcl image name, not a Python PhotoImage reference.
    Visible scene ownership is therefore independent from the reuse LRU.
    """

    def __init__(self, canvas: tk.Canvas) -> None:
        self.canvas = canvas
        self._images: OrderedDict[tuple[Any, ...], tuple[Any, int]] = OrderedDict()
        self._displayed: dict[int, tuple[Any, int]] = {}
        self._displayed_keys: dict[int, tuple[Any, ...]] = {}
        self._frame_images: list[dict[tuple[Any, ...], tuple[Any, int]]] = []
        self.cached_bytes = 0
        self.builds = 0

    @property
    def bytes(self) -> int:
        """Conservative distinct backing bytes, including the displayed scene."""
        images = {
            str(photo): size
            for photo, size in (
                *self._images.values(),
                *self._displayed.values(),
                *(entry for frame in self._frame_images for entry in frame.values()),
            )
        }
        return sum(images.values())

    @contextmanager
    def frame(self):
        """Lend current pixels to one synchronous replacement, not unused cache."""
        self._prune_deleted_items()
        images = {
            self._displayed_keys[item]: entry for item, entry in self._displayed.items()
        }
        self._frame_images.append(images)
        try:
            yield
        finally:
            self._frame_images.pop()
            self._prune_deleted_items()

    def _prune_deleted_items(self) -> None:
        try:
            existing = set(self.canvas.find_all())
        except tk.TclError:
            existing = set()  # A replacement frame may end after widget teardown.
        for item in self._displayed.keys() - existing:
            del self._displayed[item]
            self._displayed_keys.pop(item, None)

    def draw(
        self,
        bounds: tuple[int, int, int, int],
        *,
        role: str = "card",
        selected: bool = False,
        fill: str | None = None,
        edge: str | None = None,
        illumination: float | None = None,
        radius: int = 10,
        unit_scale: int = 1,
    ) -> int:
        self._prune_deleted_items()
        left, top, right, bottom = bounds
        width, height = max(1, right - left), max(1, bottom - top)
        scale = surface_backing_scale(self.canvas)
        key = (
            width,
            height,
            role,
            selected,
            scale,
            fill,
            edge,
            illumination,
            radius,
            unit_scale,
            theme_palette_snapshot(),
        )
        cached = self._images.get(key)
        if cached is None:
            cached = next(
                (frame[key] for frame in reversed(self._frame_images) if key in frame),
                None,
            )
        reused = cached is not None
        if cached is None:
            ambient = role == "ambient"
            if role in {"action-primary", "action-secondary"}:
                rendered = action_button_image(
                    width,
                    height,
                    accent=role == "action-primary",
                    density=scale,
                    unit_scale=unit_scale,
                )
            elif role == "navigation":
                rendered = navigation_button_image(
                    width,
                    height,
                    background=fill if fill is not None else THEME["panel"],
                    selected=selected,
                    density=scale,
                    unit_scale=unit_scale,
                )
            else:
                rendered = layered_surface_image(
                    width,
                    height,
                    fill=fill
                    if fill is not None
                    else THEME["bg"]
                    if ambient
                    else THEME["surface_2"]
                    if selected
                    else _blend_color(THEME["bg"], THEME["surface"], 0.55)
                    if role == "media"
                    else THEME["panel"],
                    edge=edge
                    if edge is not None
                    else ""
                    if ambient
                    else THEME["accent_dark"]
                    if selected
                    else _blend_color(THEME["bg"], THEME["border"], 0.45)
                    if role == "media"
                    else THEME["border"],
                    illumination=illumination
                    if illumination is not None
                    else 0.28
                    if selected
                    else 0.22
                    if role == "folder"
                    else 0.07
                    if role in {"media", "detail"}
                    else 0.025,
                    radius=radius,
                    ambient=ambient,
                )
            if role in {"action-primary", "action-secondary", "navigation"}:
                photo, size = create_surface_image(
                    self.canvas, rendered, scale, logical_size=(width, height)
                )
            else:
                photo, size = create_surface_image(self.canvas, rendered, scale)
            cached = (photo, size)
            self.builds += 1
            if self._frame_images:
                self._frame_images[-1][key] = cached
        # Oversized displayed images are borrowed through frame(), never inserted
        # into an LRU whose entire byte budget they would immediately evict.
        if key not in self._images and cached[1] <= 8 * 1024 * 1024:
            self._images[key] = cached
            self.cached_bytes += cached[1]
        if key in self._images:
            self._images.move_to_end(key)
        try:
            item = self.canvas.create_image(
                left,
                top,
                image=cached[0],
                anchor="nw",
                tags=(
                    "presentation-control"
                    if role in {"action", "action-primary", "action-secondary"}
                    else "presentation-surface",
                ),
            )
        except tk.TclError:
            # A retained Python wrapper does not prove its Tcl image still
            # exists. Recover only a reused, actually deleted image; unrelated
            # canvas errors and newly created image failures must propagate.
            if not reused or str(cached[0]) in self.canvas.tk.splitlist(
                self.canvas.tk.call("image", "names")
            ):
                raise
            expired = self._images.pop(key, None)
            if expired is not None:
                self.cached_bytes -= expired[1]
            for frame in self._frame_images:
                frame.pop(key, None)
            return self.draw(
                bounds,
                role=role,
                selected=selected,
                fill=fill,
                edge=edge,
                illumination=illumination,
                radius=radius,
                unit_scale=unit_scale,
            )
        if role in {"action-primary", "action-secondary"}:
            register_action_material(
                self.canvas,
                item,
                bounds,
                role == "action-primary",
                cached[0],
                unit_scale=unit_scale,
            )
        elif role == "navigation":
            register_navigation_material(
                self.canvas,
                item,
                bounds,
                background=fill if fill is not None else THEME["panel"],
                selected=selected,
                photo=cached[0],
                unit_scale=unit_scale,
            )
        self._displayed[item] = cached
        self._displayed_keys[item] = key
        while len(self._images) > 12 or self.cached_bytes > 8 * 1024 * 1024:
            _old, (_image, old_size) = self._images.popitem(last=False)
            self.cached_bytes -= old_size
        return item

    def clear(self) -> None:
        """Remove owned canvas items before releasing their image references."""
        try:
            for item in self._displayed:
                self.canvas.delete(item)
        except tk.TclError:
            pass  # The parent may already have destroyed this canvas.
        self._displayed.clear()
        self._displayed_keys.clear()
        for frame in self._frame_images:
            frame.clear()
        self._images.clear()
        self.cached_bytes = 0


def accent_hover_color() -> str:
    """Shared accent interaction color, including custom user themes."""
    return "#" + "".join(
        f"{round(channel + (255 - channel) * 0.22):02x}"
        for channel in ImageColor.getrgb(THEME["accent"])
    )


class CanvasFieldMaterial:
    """Material adapter for composite canvas fields; editing stays with children."""

    def __init__(self, canvas: tk.Canvas, field: tk.Misc) -> None:
        self.canvas, self.field = canvas, field
        canvas._matte_material_surface = True  # type: ignore[attr-defined]
        self.image: ImageTk.PhotoImage | None = None
        self.snapshot: tuple | None = None
        self.item = canvas.create_image(0, 0, anchor="nw")
        self.focused = False
        canvas.bind("<Configure>", lambda _event: self.draw(), add="+")
        canvas.bind("<Destroy>", self._destroy, add="+")
        field.bind("<FocusIn>", lambda _event: self._focus(True), add="+")
        field.bind("<FocusOut>", lambda _event: self._focus(False), add="+")
        self.draw()

    def _focus(self, focused: bool) -> None:
        self.focused = focused
        self.draw()

    def _destroy(self, event: tk.Event) -> None:
        if event.widget is self.canvas:
            self.image = None
            self.snapshot = None

    def draw(self) -> None:
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        snapshot = (width, height, self.focused, theme_palette_snapshot())
        if width < 2 or height < 2 or snapshot == self.snapshot:
            return
        self.image = ImageTk.PhotoImage(
            field_border_image(width, height, focused=self.focused), master=self.canvas
        )
        self.canvas.itemconfigure(self.item, image=self.image)
        self.canvas.tag_lower(self.item)
        if hasattr(self.canvas, "_matte_anchor"):
            from .ui_materials import draw_matte_backdrop

            draw_matte_backdrop(self.canvas)
        self.snapshot = snapshot

    def apply_theme(self) -> None:
        self.draw()


class RoundedFieldBorder:
    """Chrome only; the existing field retains editing and choice ownership."""

    def __init__(self, field: tk.Frame) -> None:
        self.field = field
        self._disposed = False
        self.focused = False
        self.hovered = False
        self._committed: tuple[object, ...] | None = None
        self._image: Any = None
        padding = window_logical_metrics(field).px(1)
        tk.Frame.configure(field, highlightthickness=0, padx=padding, pady=padding)
        self.canvas = tk.Canvas(
            field, bd=0, highlightthickness=0, takefocus=False, bg=THEME["bg"]
        )
        self.canvas._matte_material_surface = True  # type: ignore[attr-defined]
        # Chrome covers the entire shell, including its content padding. The
        # default inside mode exposes a square strip of the shell around it.
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1, bordermode="outside")
        field.tk.call("lower", str(self.canvas))
        self.item = self.canvas.create_image(0, 0, anchor="nw")
        self._configure_binding = field.bind(
            "<Configure>",
            lambda _event: self.request(self.focused, self.hovered),
            add="+",
        )
        self._destroy_bindings = [
            (owner, owner.bind("<Destroy>", self._dispose, add="+"))
            for owner in (self.field, self.canvas)
        ]

    def _dispose(self, event: tk.Event) -> None:
        if self._disposed or event.widget not in (self.field, self.canvas):
            return
        self._disposed = True
        self._image = None
        self._committed = None
        try:
            self.field.unbind("<Configure>", self._configure_binding)
        except tk.TclError:
            pass
        for owner, binding in self._destroy_bindings:
            try:
                owner.unbind("<Destroy>", binding)
            except tk.TclError:
                pass
        self._destroy_bindings.clear()

    def request(self, focused: bool = False, hovered: bool = False) -> None:
        if self._disposed:
            return
        self.focused, self.hovered = focused, hovered
        width, height = self.field.winfo_width(), self.field.winfo_height()
        scale = surface_backing_scale(self.field)
        snapshot = (width, height, scale, focused, hovered, theme_palette_snapshot())
        if snapshot == self._committed or width < 2 or height < 2:
            return
        self.canvas.configure(bg=THEME["bg"])
        image = field_border_image(
            width,
            height,
            hovered=hovered,
            focused=focused,
            density=scale,
            unit_scale=window_logical_metrics(self.field).scale,
        )
        prior = self._image
        self._image, _ = create_surface_image(
            self.field, image, scale, logical_size=(width, height), existing=prior
        )
        if self._image is not prior:
            self.canvas.itemconfigure(self.item, image=self._image)
        if hasattr(self.canvas, "_matte_anchor"):
            from .ui_materials import draw_matte_backdrop

            draw_matte_backdrop(self.canvas)
        self._committed = snapshot


def prototype_treeview_style(widget: tk.Misc, base: str) -> str:
    """Derive native list font/rows without changing ordinary sibling styles."""
    metrics = window_logical_metrics(widget)
    if not metrics.physical_fonts:
        return base
    style = ttk.Style(widget)
    name = f"Dpi{metrics.scale}.{base}"
    font = tuple(widget.tk.splitlist(style.lookup(base, "font")))
    style.configure(
        name,
        font=metrics.font(font),
        rowheight=metrics.px(int(style.lookup(base, "rowheight"))),
    )
    return name


def prototype_entry_style(widget: tk.Misc) -> str:
    """Interpreter-owned density variants; a destroyed Toplevel cannot retire shared images."""
    metrics = window_logical_metrics(widget)
    if not metrics.physical_fonts:
        return "Product.TEntry"
    top = widget.winfo_toplevel()
    root: tk.Misc = top
    while root.master is not None:
        root = root.master
    owner = getattr(root, "_product_chrome_owner", None)
    if owner is None:
        owner = ProductChromeOwner(root)
        root._product_chrome_owner = owner  # type: ignore[attr-defined]
    name = f"Dpi{metrics.scale}.Product.TEntry"
    element = f"Dpi{metrics.scale}.Product.field"
    style = ttk.Style(root)
    images = owner.entry_variants.setdefault(metrics.scale, {})
    first = not images
    for focused in (False, True):
        image = field_border_image(
            metrics.px(28),
            metrics.px(28),
            focused=focused,
            stretch=True,
            unit_scale=metrics.scale,
        )
        if focused in images:
            images[focused].paste(image)
        else:
            images[focused] = ImageTk.PhotoImage(image, master=root)
    if first:
        style.element_create(
            element,
            "image",
            images[False],
            ("focus", images[True]),
            border=metrics.px(9),
            sticky="nsew",
        )
        style.layout(
            name,
            [
                (
                    element,
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
    style.configure(
        name, padding=(metrics.px(4), 0), borderwidth=0, background=THEME["bg"]
    )
    return name


def prototype_button_style(widget: tk.Misc, name: str) -> str:
    """Opt-in button styles belong to the interpreter, like entry variants."""
    from .ui_button_contract import BUTTON_STYLE_SIZES

    metrics = window_logical_metrics(widget)
    navigation = name.endswith(("FocusNav.TButton", "FocusNavActive.TButton"))
    if not metrics.physical_fonts or (
        name not in BUTTON_STYLE_SIZES and not navigation
    ):
        return name
    root: tk.Misc = widget.winfo_toplevel()
    while root.master is not None:
        root = root.master
    owner = getattr(root, "_product_chrome_owner", None)
    if owner is None:
        owner = ProductChromeOwner(root)
        root._product_chrome_owner = owner  # type: ignore[attr-defined]
    return owner.button_style(name, metrics)


class ProductChromeOwner:
    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self.images: dict[str, Any] = {}
        self.entry_variants: dict[int, dict[bool, Any]] = {}
        self.button_variants: dict[tuple[int, str], dict[str, Any]] = {}
        self._committed: tuple[object, ...] | None = None
        self._disposed = False
        self._destroy_binding = root.bind("<Destroy>", self._dispose, add="+")

    def _dispose(self, event: tk.Event) -> None:
        if event.widget is not self.root or self._disposed:
            return
        self._disposed = True
        self.images.clear()
        self.entry_variants.clear()
        self.button_variants.clear()
        self._committed = None
        try:
            self.root.unbind("<Destroy>", self._destroy_binding)
        except tk.TclError:
            pass

    def button_style(self, base: str, metrics: WindowLogicalMetrics) -> str:
        from .ui_button_contract import BUTTON_STYLE_SIZES, button_metrics

        if base.endswith(("FocusNav.TButton", "FocusNavActive.TButton")):
            return self.navigation_style(base, metrics)
        name = f"Dpi{metrics.scale}.{base}"
        element = f"Dpi{metrics.scale}.{base}.surface"
        images = self.button_variants.setdefault((metrics.scale, base), {})
        first = not images
        roles = control_material_roles()
        primary = "Accent" in base
        for state, role in (
            ("normal", "accent" if primary else "button"),
            ("hover", "accent_hover" if primary else "hover"),
            ("pressed", "pressed"),
            ("focus", "accent_focus" if primary else "focus"),
            ("disabled", "disabled"),
        ):
            fill, edge = roles[role]
            bitmap = ttk_surface_image(
                metrics.px(28),
                fill=fill,
                edge=edge,
                recessed=state in {"hover", "pressed"},
                inset_face=state == "pressed",
                depth=0 if state == "disabled" else 1,
                unit_scale=metrics.scale,
            )
            if state in images:
                images[state].paste(bitmap)
            else:
                images[state] = ImageTk.PhotoImage(bitmap, master=self.root)
        style = ttk.Style(self.root)
        if first:
            style.element_create(
                element,
                "image",
                images["normal"],
                *(
                    (state, images[image])
                    for state, image in (
                        ("disabled", "disabled"),
                        ("pressed", "pressed"),
                        ("focus", "focus"),
                        ("active", "hover"),
                    )
                ),
                border=metrics.px(9),
                sticky="nsew",
            )
            style.layout(
                name,
                [
                    (
                        element,
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
        spec = button_metrics(BUTTON_STYLE_SIZES[base])
        font = metrics.font(spec.font)
        # Measure the exact tuple used by ttk. Font(font=tuple) first resolves
        # it to point-sized actual attributes, then creates another font; that
        # round trip can change native pixel metrics (observed on macOS).
        line = int(self.root.tk.call("font", "metrics", font, "-linespace"))
        remainder = max(0, metrics.px(spec.height - 18) - line)
        horizontal = metrics.px(max(0, spec.horizontal_padding - 9))
        style.configure(
            name,
            font=font,
            background=THEME["bg"],
            padding=(
                horizontal,
                remainder // 2,
                horizontal,
                remainder - remainder // 2,
            ),
        )
        return name

    def navigation_style(self, base: str, metrics: WindowLogicalMetrics) -> str:
        """Scale the existing navigation material without changing its states."""
        name = f"Dpi{metrics.scale}.{base}"
        element = f"{name}.surface"
        images = self.button_variants.setdefault((metrics.scale, base), {})
        first = not images
        selected = base.endswith("FocusNavActive.TButton")
        for state in ("normal", "hover", "pressed", "focus"):
            bitmap = navigation_button_image(
                metrics.px(28),
                metrics.px(28),
                background=THEME["bg"],
                selected=selected,
                state=state,
                transparent=False,
                unit_scale=metrics.scale,
            )
            if state in images:
                images[state].paste(bitmap)
            else:
                images[state] = ImageTk.PhotoImage(bitmap, master=self.root)
        style = ttk.Style(self.root)
        if first:
            style.element_create(
                element,
                "image",
                images["normal"],
                ("disabled", images["normal"]),
                ("pressed", images["pressed"]),
                ("focus", images["focus"]),
                ("active", images["hover"]),
                border=metrics.px(9),
                sticky="nsew",
            )
            style.layout(
                name,
                [
                    (
                        element,
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
        if first:
            # The first control is created after style assembly completes.
            # Palette refresh runs midway through that assembly, when legacy
            # base padding is transient; retain the admitted metric contract.
            font = tuple(self.root.tk.splitlist(style.lookup(base, "font")))
            padding = tuple(
                int(value)
                for value in self.root.tk.splitlist(style.lookup(base, "padding"))
            )
            style.configure(
                name,
                font=metrics.font(font),
                padding=tuple(metrics.px(value) for value in padding),
            )
        style.configure(name, background=THEME["bg"])
        return name

    def request(self, style: ttk.Style) -> None:
        if self._disposed:
            return
        scale = surface_backing_scale(self.root)
        snapshot = (theme_palette_snapshot(), scale)
        if self._committed == snapshot:
            return
        roles = control_material_roles()
        first = not self.images
        for name, (fill, outline) in roles.items():
            is_transport = name.startswith("transport")
            size = 40 if is_transport else 28
            if name in ("field", "field_focus"):
                image = field_border_image(
                    size,
                    size,
                    focused=name == "field_focus",
                    stretch=True,
                    density=scale,
                )
            elif is_transport:
                image = _matte_rim(
                    Image.new("RGBA", (size, size), fill),
                    fill,
                    outline,
                    20,
                    recessed=name in {"transport_hover", "transport_pressed"},
                    depth=(
                        0
                        if name == "transport_disabled"
                        else 0.62
                        if name == "transport_hover"
                        else 1.0
                    ),
                )
            elif name.startswith("nav_"):
                navigation_state = (
                    "pressed"
                    if name == "nav_pressed"
                    else "hover"
                    if name in {"nav_hover", "nav_selected"}
                    else "focus"
                    if name in {"nav_focus", "nav_selected_focus"}
                    else "normal"
                )
                image = navigation_button_image(
                    size,
                    size,
                    background=THEME["bg"],
                    selected=name in {"nav_selected", "nav_selected_focus"},
                    state=navigation_state,
                    density=scale,
                    transparent=False,
                )
            else:
                image = ttk_surface_image(
                    size,
                    fill=fill,
                    edge=outline,
                    recessed=name in {"hover", "accent_hover", "pressed"},
                    inset_face=name == "pressed",
                    depth=0 if name == "disabled" else 1.0,
                )
            if name in ("field", "field_focus") or name.startswith("nav_"):
                self.images[name], _ = create_surface_image(
                    self.root,
                    image,
                    scale,
                    logical_size=(size, size),
                    existing=self.images.get(name),
                )
            elif name in self.images:
                self.images[name].paste(image)
            else:
                self.images[name] = ImageTk.PhotoImage(image, master=self.root)
        if first:
            self._install(style)
        for scale, base in tuple(self.button_variants):
            self.button_style(base, WindowLogicalMetrics(scale, physical_fonts=True))
        self._committed = snapshot

    def _install(self, style: ttk.Style) -> None:
        def element(
            name: str,
            default: str,
            states: tuple[tuple[str, str], ...],
            *,
            border: int = 9,
        ) -> None:
            style.element_create(
                name,
                "image",
                self.images[default],
                *((state, self.images[image]) for state, image in states),
                border=border,
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
                ("focus", "accent_focus"),
                ("active", "accent_hover"),
            ),
        )
        element("Product.field", "field", (("focus", "field_focus"),))
        element("Product.panel", "panel", ())
        style.layout(
            "Material.TFrame",
            [
                (
                    "Product.panel",
                    {
                        "sticky": "nsew",
                        "children": [("Frame.padding", {"sticky": "nsew"})],
                    },
                )
            ],
        )
        element(
            "Product.nav",
            "nav_idle",
            (
                ("disabled", "nav_idle"),
                ("pressed", "nav_pressed"),
                ("focus", "nav_focus"),
                ("active", "nav_hover"),
            ),
            border=9,
        )
        element(
            "Product.nav_selected",
            "nav_selected",
            (
                ("pressed", "nav_pressed"),
                ("focus", "nav_selected_focus"),
                ("active", "nav_selected"),
            ),
            border=9,
        )
        element(
            "Product.tab",
            "nav_idle",
            (
                ("disabled", "nav_idle"),
                ("selected focus", "nav_selected_focus"),
                ("selected", "nav_selected"),
                ("focus", "nav_focus"),
                ("active", "nav_hover"),
            ),
            border=9,
        )
        style.element_create(
            "Product.transport",
            "image",
            self.images["transport"],
            ("disabled", self.images["transport_disabled"]),
            ("pressed", self.images["transport_pressed"]),
            ("focus", self.images["transport_focus"]),
            ("active", self.images["transport_hover"]),
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
            ("FocusNav.TButton", "Product.nav"),
            ("FocusNavActive.TButton", "Product.nav_selected"),
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
    for role in ("FocusNav.TButton", "FocusNavActive.TButton"):
        style.configure(role, background=THEME["bg"], padding=(4, 4))
        style.map(
            role,
            background=[
                ("pressed", THEME["bg"]),
                ("focus", THEME["bg"]),
                ("active", THEME["bg"]),
                ("disabled", THEME["bg"]),
            ],
        )
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
            ("disabled", THEME["surface"]),
            ("focus", THEME["focus_surface"]),
            ("readonly", THEME["surface"]),
        ],
        foreground=[("disabled", THEME["subtle"])],
    )


def draw_scene_focus_material(
    canvas: tk.Canvas,
    bounds: tuple[int, int, int, int],
    *,
    radius: int = 11,
    tag: str = "keyboard-focus",
) -> int:
    """Recess the target edges without outlining or covering its semantic content."""
    owner = getattr(canvas, "_action_material", None)
    if owner is not None:
        owner.focus(bounds if bounds in owner.controls else None)
        if bounds in owner.controls:
            # The action already has an owned base beneath its label. Replace
            # that face instead of adding a second rim around a raised button.
            return owner.controls[bounds][0]
    left, top, right, bottom = bounds
    width, height = max(1, right - left), max(1, bottom - top)
    density = surface_backing_scale(canvas)
    mask = rounded_alpha(width * density, height * density, radius * density)
    image = Image.new("RGBA", mask.size)
    for color, band in _matte_lighting(mask, recessed=True, depth=0.9, density=density):
        layer = Image.new("RGBA", image.size, color)
        layer.putalpha(band)
        image = Image.alpha_composite(image, layer)
    photo, _ = create_surface_image(
        canvas,
        image,
        density,
        logical_size=(width, height),
        existing=getattr(canvas, "_keyboard_focus_image", None),
    )
    cast(Any, canvas)._keyboard_focus_image = photo
    return canvas.create_image(left, top, image=photo, anchor="nw", tags=tag)


class CanvasActionMaterialOwner:
    """State faces for current scene actions; preserve the scene's input owner."""

    def __init__(self, canvas: tk.Canvas) -> None:
        self.canvas = canvas
        self.controls: dict[tuple, tuple] = {}
        self.images: OrderedDict[tuple, ImageTk.PhotoImage] = OrderedDict()
        self.active: tuple | None = None
        self.focused: tuple | None = None
        canvas.bind("<FocusOut>", lambda _event: self.focus(None), add="+")
        canvas.bind("<Destroy>", self._destroy, add="+")

    def _destroy(self, event: tk.Event) -> None:
        if event.widget is self.canvas:
            self.controls.clear()
            self.images.clear()
            self.active = None
            self.focused = None

    def register(
        self,
        item: int,
        bounds: tuple,
        primary: bool,
        photo: Any,
        *,
        unit_scale: int = 1,
    ) -> None:
        existing = set(self.canvas.find_all())
        self.controls = {
            b: value for b, value in self.controls.items() if value[0] in existing
        }
        self.controls[bounds] = (
            item,
            "action",
            primary,
            "",
            False,
            ref(photo),
            unit_scale,
        )
        self.active = None

    def register_navigation(
        self,
        item: int,
        bounds: tuple,
        *,
        background: str,
        selected: bool,
        photo: Any,
        unit_scale: int = 1,
    ) -> None:
        existing = set(self.canvas.find_all())
        self.controls = {
            b: value for b, value in self.controls.items() if value[0] in existing
        }
        self.controls[bounds] = (
            item,
            "navigation",
            False,
            background,
            selected,
            ref(photo),
            unit_scale,
        )
        self.active = None

    def focus(self, bounds: tuple | None) -> None:
        if self.focused == bounds:
            return
        previous = self.active
        self.focused = bounds
        self.active = None
        self.paint(
            previous[0] if previous else None, previous[1] if previous else False
        )

    def paint(self, bounds: tuple | None, pressed: bool) -> None:
        state = (bounds, pressed, theme_palette_snapshot(), self.focused)
        if state == self.active:
            return
        for box, (item, kind, primary, background, selected, base, unit_scale) in list(
            self.controls.items()
        ):
            if not self.canvas.type(item):
                self.controls.pop(box)
                continue
            photo = base()
            if photo is None:
                self.controls.pop(box)
                continue
            if box == bounds or box == self.focused:
                focused = box == self.focused
                button_state = (
                    "pressed"
                    if pressed and box == bounds
                    else "focus"
                    if focused
                    else "hover"
                )
                key = (
                    kind,
                    box[2] - box[0],
                    box[3] - box[1],
                    primary,
                    background,
                    selected,
                    button_state,
                    unit_scale,
                    theme_palette_snapshot(),
                )
                photo = self.images.get(key)
                if photo is None:
                    scale = surface_backing_scale(self.canvas)
                    width, height = box[2] - box[0], box[3] - box[1]
                    if kind == "navigation":
                        bitmap = navigation_button_image(
                            width,
                            height,
                            background=background,
                            selected=selected,
                            state=button_state,
                            density=scale,
                            unit_scale=unit_scale,
                        )
                    else:
                        bitmap = action_button_image(
                            width,
                            height,
                            accent=primary,
                            state=button_state,
                            density=scale,
                            unit_scale=unit_scale,
                        )
                    photo = create_surface_image(
                        self.canvas, bitmap, scale, logical_size=(width, height)
                    )[0]
                    self.images[key] = photo
                self.images.move_to_end(key)
            self.canvas.itemconfigure(item, image=photo)
        while len(self.images) > 24:
            self.images.popitem(last=False)
        self.active = state


def register_action_material(
    canvas: tk.Canvas,
    item: int,
    bounds: tuple,
    primary: bool,
    photo: Any,
    *,
    unit_scale: int = 1,
) -> None:
    owner = getattr(canvas, "_action_material", None)
    if owner is None:
        owner = CanvasActionMaterialOwner(canvas)
        cast(Any, canvas)._action_material = owner
    owner.register(item, bounds, primary, photo, unit_scale=unit_scale)


def register_navigation_material(
    canvas: tk.Canvas,
    item: int,
    bounds: tuple,
    *,
    background: str,
    selected: bool,
    photo: Any,
    unit_scale: int = 1,
) -> None:
    """Register a canvas navigation target with the shared inset face."""
    owner = getattr(canvas, "_action_material", None)
    if owner is None:
        owner = CanvasActionMaterialOwner(canvas)
        cast(Any, canvas)._action_material = owner
    owner.register_navigation(
        item,
        bounds,
        background=background,
        selected=selected,
        photo=photo,
        unit_scale=unit_scale,
    )


def paint_action_material(
    canvas: tk.Canvas, bounds: tuple | None, pressed: bool
) -> None:
    owner = getattr(canvas, "_action_material", None)
    if owner is not None:
        owner.paint(bounds, pressed)


def draw_matte_track(
    canvas: tk.Canvas,
    left: float,
    y: float,
    right: float,
    fraction: float,
    *,
    thickness: int = 4,
    unit_scale: int = 1,
) -> None:
    """One recessed track convention for progress, seek and volume adapters."""
    thickness *= unit_scale
    canvas.create_line(
        left,
        y + unit_scale,
        right,
        y + unit_scale,
        fill=THEME["border"],
        width=thickness + 2 * unit_scale,
        capstyle="round",
    )
    canvas.create_line(
        left,
        y - unit_scale,
        right,
        y - unit_scale,
        fill=THEME["bg"],
        width=thickness + 2 * unit_scale,
        capstyle="round",
    )
    canvas.create_line(
        left, y, right, y, fill=THEME["surface"], width=thickness, capstyle="round"
    )
    if fraction > 0:
        end = left + (right - left) * min(1, max(0, fraction))
        canvas.create_line(
            left, y, end, y, fill=THEME["progress"], width=thickness, capstyle="round"
        )
