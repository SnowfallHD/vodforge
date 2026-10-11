"""Pure pixel generation for Qt controls and artwork."""

from __future__ import annotations

import colorsys

from PIL import (
    Image,
    ImageChops,
    ImageColor,
    ImageDraw,
    ImageFilter,
    ImageOps,
)

from .product_theme import THEME


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


def _matte_lighting(
    mask: Image.Image,
    *,
    recessed: bool,
    depth: float,
    density: int,
    lighting_colors: tuple[str, str] = ("#000000", "#ffffff"),
):
    """Shared diffuse material bands; no semantic-color state perimeter."""
    dark, light = lighting_colors
    for dx, dy, color, strength in (
        (3, 3, dark if recessed else light, 0.70 if recessed else 0.10),
        (-3, -3, light if recessed else dark, 0.13 if recessed else 0.24),
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
    lighting_colors: tuple[str, str] = ("#000000", "#ffffff"),
    lip_color: str = "",
) -> Image.Image:
    """Diffuse inner light and occlusion, rather than concentric bevel lines."""
    width, height = image.size
    if edge == THEME["focus"]:
        fill = THEME["focus_surface"]
        image = Image.new("RGBA", image.size, fill)
        recessed, depth = True, 0.9
    mask = rounded_alpha(width, height, radius)
    if lip_color:
        inner = Image.new("L", image.size)
        inner.paste(
            rounded_alpha(
                width - 2 * density, height - 2 * density, max(0, radius - density)
            ),
            (density, density),
        )
        lip = ImageChops.subtract(mask, inner)
        image = Image.composite(Image.new("RGBA", image.size, lip_color), image, lip)
    for color, band in _matte_lighting(
        mask,
        recessed=recessed,
        depth=depth,
        density=density,
        lighting_colors=lighting_colors,
    ):
        image = Image.composite(Image.new("RGBA", image.size, color), image, band)
    image.putalpha(mask)
    return image


def control_surface_image(
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
    lighting_colors: tuple[str, str] = ("#000000", "#ffffff"),
    lip_color: str = "",
) -> Image.Image:
    """Crisp face, contour contact shadow and separate diffuse ambient light."""
    if edge == THEME["focus"]:
        fill, recessed, depth = THEME["focus_surface"], True, 0.9
    dark, light = lighting_colors
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
                (2, 3, 3.2, dark, 0.24),
                (-2, -2, 3.0, light, 0.075),
                (1, 2, 0.65, dark, 0.38),
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
            lighting_colors=lighting_colors,
            lip_color=lip_color,
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
            lighting_colors=lighting_colors,
            lip_color=lip_color,
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


def popup_shadow_image(width: int, height: int) -> Image.Image:
    """Soft rounded elevation outside the shared popup face, with 24px support."""
    extent = 24
    size = (width + extent * 2, height + extent * 2)
    mask = Image.new("L", size)
    ImageDraw.Draw(mask).rounded_rectangle(
        (extent, extent, extent + width - 1, extent + height - 1),
        radius=min(9, width // 2, height // 2),
        fill=255,
    )
    image = Image.new("RGBA", size)
    for offset, blur, opacity in ((5, 8, 0.34), (2, 2, 0.22)):
        shadow = Image.new("RGBA", size, "#000000")
        shadow.putalpha(
            _shift_mask(mask, 0, offset)
            .filter(ImageFilter.GaussianBlur(blur))
            .point(lambda alpha, opacity=opacity: round(alpha * opacity))
        )
        image = Image.alpha_composite(image, shadow)
    return image


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
    """Shared inset field surface for Qt controls and canvas-owned controls."""
    return control_surface_image(
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
    """Return the shared control face and contour colors for interaction states.

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


def _theme_button_lighting() -> tuple[str, str]:
    """Keep both sides of the original bevel in the accent's hue family."""
    red, green, blue = ImageColor.getrgb(THEME["accent"])
    hue, lightness, saturation = colorsys.rgb_to_hls(red / 255, green / 255, blue / 255)
    saturation = min(1.0, max(0.35, saturation * 1.4))

    def shade(level: float) -> str:
        return "#" + "".join(
            f"{round(channel * 255):02x}"
            for channel in colorsys.hls_to_rgb(hue, level, saturation)
        )

    return shade(max(0.05, lightness * 0.32)), shade(0.88)


def action_button_image(
    width: int,
    height: int,
    *,
    accent: bool,
    state: str = "normal",
    density: int = 1,
    focused: bool = False,
    unit_scale: int = 1,
    primary: bool = False,
    outlined: bool = False,
) -> Image.Image:
    """Shared raised and inset interaction faces for scene actions.

    Hover communicates affordance through an inward material contour, never a
    brighter accent border.  Keyboard focus remains the distinct, high-contrast
    state and pressed retains the deeper version of the same contour.
    """
    # Preserve the original contour, with colored lighting for the accent material.
    lighting = _theme_button_lighting() if primary else ("#000000", "#ffffff")
    fill = (
        THEME["accent"]
        if primary
        else primary_action_color()
        if accent
        else THEME["surface"]
    )
    if state == "pressed":
        fill = _blend_color(fill, lighting[0] if primary else THEME["bg"], 0.18)
    if state == "disabled":
        fill = _blend_color(fill, THEME["bg"], 0.65)
    edge = (
        THEME["focus"]
        if focused or state == "focus"
        else _blend_color(fill, THEME["accent"], 0.28 if accent else 0.14)
    )
    return control_surface_image(
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
        lighting_colors=lighting,
        lip_color=THEME["accent"] if outlined else "",
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
    image = control_surface_image(
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
