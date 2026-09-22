"""Shared restrained scene typography, labeled actions and line icons."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PIL import ImageTk

from .ui_button_contract import ButtonSize, button_metrics
from .ui_chrome import action_button_image, register_action_material
from .ui_layout import prose_excerpt
from .ui_theme import FONT_UI, FONT_UI_EMPHASIS_FAMILY, THEME


def scene_font(size: int = 15, *, bold: bool = False, font_scale: int = 1) -> tuple:
    if bold and size < 32:
        return (FONT_UI_EMPHASIS_FAMILY, -size * font_scale, "normal")
    return (FONT_UI[0], -size * font_scale, "bold" if bold else "normal")


class ScenePainter:
    def __init__(self, view: Any) -> None:
        self.view, self.canvas = view, view.canvas

    def text(
        self,
        x: int,
        y: int,
        text: str,
        *,
        size: int = 15,
        bold: bool = False,
        color: str = "",
        width: int = 0,
        lines: int | None = 1,
        prose: bool = False,
        font_scale: int = 1,
    ) -> int:
        font = scene_font(size, bold=bold, font_scale=font_scale)
        value = (
            self.view._fit(text, width, lines, font)
            if width and lines is not None
            else text
        )
        if prose:
            value = prose_excerpt(text, value)
        return self.canvas.create_text(
            x,
            y,
            text=value,
            font=font,
            fill=color or THEME["text"],
            anchor="nw",
            **({"width": width} if width else {}),
        )

    def icon(
        self,
        name: str,
        x: int,
        y: int,
        size: int = 20,
        color: str = "",
        *,
        stroke_width: float | None = None,
    ) -> None:
        c, color = self.canvas, color or THEME["text"]
        stroke = (2 if size >= 18 else 1.4) if stroke_width is None else stroke_width
        if name == "play":
            c.create_polygon(
                x + size * 0.2,
                y,
                x + size * 0.2,
                y + size,
                x + size * 0.95,
                y + size * 0.5,
                fill=color,
                outline="",
            )
        elif name == "download":
            c.create_line(
                x + size / 2, y, x + size / 2, y + size * 0.7, fill=color, width=stroke
            )
            c.create_line(
                x + size * 0.25,
                y + size * 0.45,
                x + size / 2,
                y + size * 0.7,
                x + size * 0.75,
                y + size * 0.45,
                fill=color,
                width=stroke,
            )
            c.create_line(
                x,
                y + size * 0.65,
                x,
                y + size,
                x + size,
                y + size,
                x + size,
                y + size * 0.65,
                fill=color,
                width=stroke,
            )
        elif name == "folder":
            c.create_line(
                x,
                y + size * 0.22,
                x + size * 0.35,
                y + size * 0.22,
                x + size * 0.48,
                y + size * 0.38,
                x + size,
                y + size * 0.38,
                x + size,
                y + size * 0.94,
                x,
                y + size * 0.94,
                x,
                y + size * 0.22,
                fill=color,
                width=stroke,
                joinstyle="round",
            )
        elif name in {"channels", "people"}:
            for dx, dy, scale in (
                (0.32, 0.08, 0.36),
                (0.02, 0.25, 0.25),
                (0.72, 0.25, 0.25),
            ):
                c.create_oval(
                    x + size * dx,
                    y + size * dy,
                    x + size * (dx + scale),
                    y + size * (dy + scale),
                    outline=color,
                    width=stroke,
                )
            c.create_line(
                x + size * 0.22,
                y + size * 0.94,
                x + size * 0.22,
                y + size * 0.68,
                x + size * 0.35,
                y + size * 0.55,
                x + size * 0.65,
                y + size * 0.55,
                x + size * 0.78,
                y + size * 0.68,
                x + size * 0.78,
                y + size * 0.94,
                fill=color,
                width=stroke,
                smooth=True,
            )
            for a, b in ((0, 0.19), (0.81, 1)):
                c.create_line(
                    x + size * a,
                    y + size * 0.9,
                    x + size * a,
                    y + size * 0.64,
                    x + size * b,
                    y + size * 0.6,
                    fill=color,
                    width=stroke,
                )
        elif name in {"videos", "film"}:
            c.create_rectangle(
                x, y + 1, x + size, y + size - 1, outline=color, width=stroke
            )
            for dx in (0.23, 0.77):
                c.create_line(
                    x + size * dx,
                    y + 1,
                    x + size * dx,
                    y + size - 1,
                    fill=color,
                    width=stroke,
                )
            for dy in (0.28, 0.5, 0.72):
                for a, b in ((0, 0.23), (0.77, 1)):
                    c.create_line(
                        x + size * a,
                        y + size * dy,
                        x + size * b,
                        y + size * dy,
                        fill=color,
                        width=stroke,
                    )
        elif name in {"audio", "music"}:
            c.create_line(
                x + size * 0.35,
                y + size * 0.78,
                x + size * 0.35,
                y + size * 0.18,
                x + size * 0.87,
                y + size * 0.05,
                x + size * 0.87,
                y + size * 0.65,
                fill=color,
                width=stroke,
            )
            c.create_line(
                x + size * 0.35,
                y + size * 0.33,
                x + size * 0.87,
                y + size * 0.2,
                fill=color,
                width=stroke,
            )
            c.create_oval(
                x,
                y + size * 0.67,
                x + size * 0.35,
                y + size * 0.95,
                outline=color,
                width=stroke,
            )
            c.create_oval(
                x + size * 0.53,
                y + size * 0.55,
                x + size * 0.87,
                y + size * 0.83,
                outline=color,
                width=stroke,
            )
        elif name in {"list", "playlists"}:
            dot = max(2, size * 0.09)
            for fraction in (0.20, 0.50, 0.80):
                cy = y + size * fraction
                c.create_oval(
                    x, cy - dot / 2, x + dot, cy + dot / 2, fill=color, outline=""
                )
                c.create_line(
                    x + size * 0.29,
                    cy,
                    x + size,
                    cy,
                    fill=color,
                    width=stroke,
                    capstyle="round",
                )
        elif name == "more":
            for dy in (2, 9, 16):
                c.create_oval(x + 8, y + dy, x + 11, y + dy + 3, fill=color, outline="")
        elif name in {"back", "chevron"}:
            flip = -1 if name == "chevron" else 1
            c.create_line(
                x + 10 + flip * 3,
                y + 3,
                x + 10 - flip * 4,
                y + 10,
                x + 10 + flip * 3,
                y + 17,
                fill=color,
                width=stroke,
            )
        elif name == "drive":
            c.create_polygon(
                x + 3,
                y + 2,
                x + size - 3,
                y + 2,
                x + size,
                y + size * 0.78,
                x,
                y + size * 0.78,
                fill="",
                outline=color,
                width=stroke,
            )
            c.create_line(
                x,
                y + size * 0.78,
                x,
                y + size,
                x + size,
                y + size,
                x + size,
                y + size * 0.78,
                fill=color,
                width=stroke,
            )
            c.create_line(
                x + 3,
                y + size * 0.88,
                x + size * 0.35,
                y + size * 0.88,
                fill=color,
                width=stroke,
            )
        elif name == "filter":
            c.create_line(
                x,
                y + 2,
                x + size,
                y + 2,
                x + size * 0.62,
                y + size * 0.5,
                x + size * 0.62,
                y + size,
                x + size * 0.4,
                y + size * 0.86,
                x + size * 0.4,
                y + size * 0.5,
                x,
                y + 2,
                fill=color,
                width=stroke,
            )
        elif name == "sort":
            c.create_line(
                x + size * 0.3, y + size, x + size * 0.3, y, fill=color, width=stroke
            )
            c.create_line(
                x,
                y + size * 0.3,
                x + size * 0.3,
                y,
                x + size * 0.6,
                y + size * 0.3,
                fill=color,
                width=stroke,
            )
            c.create_line(
                x + size * 0.75, y, x + size * 0.75, y + size, fill=color, width=stroke
            )
            c.create_line(
                x + size * 0.5,
                y + size * 0.7,
                x + size * 0.75,
                y + size,
                x + size,
                y + size * 0.7,
                fill=color,
                width=stroke,
            )
        elif name == "plus":
            c.create_line(
                x, y + size / 2, x + size, y + size / 2, fill=color, width=stroke
            )
            c.create_line(
                x + size / 2, y, x + size / 2, y + size, fill=color, width=stroke
            )
        elif name in {
            "file",
            "document",
            "calendar",
            "monitor",
            "copy",
            "external",
            "edit",
            "wrench",
        }:
            if name in {"file", "document"}:
                c.create_line(
                    x + 2,
                    y,
                    x + size * 0.62,
                    y,
                    x + size - 2,
                    y + size * 0.28,
                    x + size - 2,
                    y + size,
                    x + 2,
                    y + size,
                    x + 2,
                    y,
                    fill=color,
                    width=stroke,
                )
                c.create_line(
                    x + size * 0.62,
                    y,
                    x + size * 0.62,
                    y + size * 0.28,
                    x + size - 2,
                    y + size * 0.28,
                    fill=color,
                    width=stroke,
                )
                for dy in (0.5, 0.7):
                    c.create_line(
                        x + size * 0.25,
                        y + size * dy,
                        x + size * 0.72,
                        y + size * dy,
                        fill=color,
                        width=stroke,
                    )
            elif name == "calendar":
                c.create_rectangle(
                    x + 1,
                    y + size * 0.2,
                    x + size - 1,
                    y + size,
                    outline=color,
                    width=stroke,
                )
                c.create_line(
                    x + 1,
                    y + size * 0.45,
                    x + size - 1,
                    y + size * 0.45,
                    fill=color,
                    width=stroke,
                )
                for dx in (0.28, 0.72):
                    c.create_line(
                        x + size * dx,
                        y,
                        x + size * dx,
                        y + size * 0.3,
                        fill=color,
                        width=stroke,
                    )
            elif name == "monitor":
                c.create_rectangle(
                    x, y, x + size, y + size * 0.7, outline=color, width=stroke
                )
                c.create_line(
                    x + size * 0.5,
                    y + size * 0.7,
                    x + size * 0.5,
                    y + size,
                    fill=color,
                    width=stroke,
                )
                c.create_line(
                    x + size * 0.25,
                    y + size,
                    x + size * 0.75,
                    y + size,
                    fill=color,
                    width=stroke,
                )
            elif name == "edit":
                c.create_polygon(
                    x,
                    y + size,
                    x + size * 0.1,
                    y + size * 0.65,
                    x + size * 0.75,
                    y,
                    x + size,
                    y + size * 0.25,
                    x + size * 0.35,
                    y + size * 0.9,
                    fill="",
                    outline=color,
                    width=stroke,
                )
            elif name == "wrench":
                c.create_line(
                    x + size * 0.3,
                    y + size * 0.2,
                    x + size * 0.1,
                    y,
                    x,
                    y + size * 0.3,
                    x + size * 0.25,
                    y + size * 0.55,
                    x + size * 0.5,
                    y + size * 0.5,
                    x + size * 0.86,
                    y + size * 0.97,
                    x + size,
                    y + size * 0.83,
                    x + size * 0.56,
                    y + size * 0.42,
                    x + size * 0.59,
                    y + size * 0.2,
                    x + size * 0.4,
                    y,
                    fill=color,
                    width=stroke,
                )
            else:
                if name == "copy":
                    c.create_line(
                        x,
                        y + size * 0.75,
                        x,
                        y,
                        x + size * 0.72,
                        y,
                        fill=color,
                        width=stroke,
                    )
                c.create_line(
                    x + size * 0.2,
                    y + size * 0.2,
                    x + size * 0.62,
                    y + size * 0.2,
                    fill=color,
                    width=stroke,
                )
                c.create_line(
                    x + size * 0.2,
                    y + size * 0.2,
                    x + size * 0.2,
                    y + size * 0.98,
                    x + size * 0.95,
                    y + size * 0.98,
                    x + size * 0.95,
                    y + size * 0.5,
                    fill=color,
                    width=stroke,
                )
                if name == "external":
                    c.create_line(
                        x + size * 0.4,
                        y + size * 0.6,
                        x + size,
                        y,
                        x + size,
                        y + size * 0.35,
                        fill=color,
                        width=stroke,
                    )
                    c.create_line(
                        x + size * 0.65, y, x + size, y, fill=color, width=stroke
                    )
                else:
                    c.create_line(
                        x + size * 0.62,
                        y + size * 0.2,
                        x + size * 0.95,
                        y + size * 0.2,
                        x + size * 0.95,
                        y + size * 0.5,
                        fill=color,
                        width=stroke,
                    )
        elif name == "link":
            c.create_oval(
                x, y + size * 0.4, x + size * 0.6, y + size, outline=color, width=stroke
            )
            c.create_oval(
                x + size * 0.4, y, x + size, y + size * 0.6, outline=color, width=stroke
            )
            c.create_line(
                x + size * 0.3,
                y + size * 0.7,
                x + size * 0.7,
                y + size * 0.3,
                fill=color,
                width=stroke,
            )
        elif name == "tag":
            c.create_polygon(
                x,
                y,
                x + size * 0.55,
                y,
                x + size,
                y + size * 0.45,
                x + size * 0.45,
                y + size,
                x,
                y + size * 0.55,
                fill="",
                outline=color,
                width=stroke,
            )
            c.create_oval(
                x + size * 0.17,
                y + size * 0.17,
                x + size * 0.3,
                y + size * 0.3,
                outline=color,
                width=stroke,
            )
        elif name == "shuffle":
            for start, finish in ((0.2, 0.8), (0.8, 0.2)):
                c.create_line(
                    x,
                    y + size * start,
                    x + size * 0.22,
                    y + size * start,
                    x + size * 0.76,
                    y + size * finish,
                    x + size,
                    y + size * finish,
                    fill=color,
                    width=stroke,
                    capstyle="round",
                    joinstyle="round",
                )
                c.create_line(
                    x + size * 0.79,
                    y + size * (finish - 0.16),
                    x + size,
                    y + size * finish,
                    x + size * 0.79,
                    y + size * (finish + 0.16),
                    fill=color,
                    width=stroke,
                    capstyle="round",
                    joinstyle="round",
                )
        else:
            c.create_rectangle(
                x + 2, y + 2, x + size - 2, y + size - 2, outline=color, width=stroke
            )

    def button(
        self,
        x: int,
        y: int,
        width: int | None,
        label: str,
        action: Callable[[], None],
        *,
        primary: bool = False,
        icon: str = "",
        variant: ButtonSize = "default",
        quiet: bool = False,
        unit_scale: int = 1,
    ) -> None:
        spec = button_metrics(variant)
        height, size = spec.height * unit_scale, spec.font_pixels
        if width is None:
            if label or not icon:
                raise ValueError("Automatic square width requires an icon-only action")
            width = height
        bounds = (x, y, x + width, y + height)
        if not quiet:
            depth = getattr(self.view, "_depth", None)
            if depth is not None:
                depth.draw(
                    bounds,
                    role="action-primary" if primary else "action-secondary",
                    unit_scale=unit_scale,
                )
            else:
                image = ImageTk.PhotoImage(
                    action_button_image(
                        width, height, accent=primary, unit_scale=unit_scale
                    ),
                    master=self.canvas,
                )
                self.view._button_images.append(image)
                item = self.canvas.create_image(
                    x, y, image=image, anchor="nw", tags="presentation-control"
                )
                register_action_material(
                    self.canvas, item, bounds, primary, image, unit_scale=unit_scale
                )
        if icon:
            self.icon(
                icon,
                x
                + (
                    spec.horizontal_padding * unit_scale
                    if label
                    else (width - spec.icon_pixels * unit_scale) // 2
                ),
                y + (height - spec.icon_pixels * unit_scale) // 2,
                spec.icon_pixels * unit_scale,
                THEME["icon"],
                stroke_width=(2 if spec.icon_pixels >= 23 else 1.4) * unit_scale,
            )
        label_id = self.canvas.create_text(
            x + (width + (24 * unit_scale if icon else 0)) / 2,
            y + height / 2,
            # Action names are instructions, not user content. Let native
            # text layout wrap within the reserved label area; never elide them.
            text=label,
            width=max(1, width - ((56 if icon and label else 20) * unit_scale)),
            justify="center",
            font=scene_font(size, font_scale=unit_scale),
            fill=THEME["action"] if primary else THEME["text"],
        )
        self.view._button_labels.append(
            (bounds, label_id, THEME["action"] if primary else THEME["text"], True)
        )
        self.view._targets.append((bounds, action))

    def chips(
        self,
        x: int,
        y: int,
        labels: list[str],
        maximum_width: int,
        *,
        reserve_tail: int = 0,
    ) -> None:
        from tkinter import font as tkfont

        from .ui_chrome import layered_surface_image

        font = tkfont.Font(root=self.view, font=scene_font(14))
        labels = [label for label in labels if label]
        natural_widths = [font.measure(label) + 20 for label in labels]
        tail = min(len(labels), max(0, reserve_tail))
        prefix = len(labels) - tail
        free = max(
            0,
            maximum_width - sum(natural_widths[prefix:]) - 10 * max(0, len(labels) - 1),
        )
        allocations = []
        for index, natural in enumerate(natural_widths):
            if tail and index < prefix:
                allocation = min(natural, free // (prefix - index))
                free -= allocation
            else:
                allocation = natural
            allocations.append(allocation)
        origin_x = x
        for index, (label, allocation) in enumerate(
            zip(labels, allocations, strict=True)
        ):
            remaining = maximum_width - (x - origin_x)
            if tail:
                remaining = min(remaining, allocation)
            if remaining < 32:
                if tail and index < prefix:
                    continue
                break
            fitted = self.view._fit(label, remaining - 20, 1, scene_font(14))
            width = min(remaining, font.measure(fitted) + 20)
            image = ImageTk.PhotoImage(
                layered_surface_image(
                    width, 25, fill=THEME["panel"], edge=THEME["border"], radius=12
                ),
                master=self.canvas,
            )
            self.view._button_images.append(image)
            self.canvas.create_image(x, y, image=image, anchor="nw")
            self.canvas.create_text(
                x + width / 2,
                y + 12,
                text=fitted,
                font=scene_font(14),
                fill=THEME["text"],
            )
            x += width + 10

    def link(
        self,
        x: int,
        y: int,
        label: str,
        action: Callable[[], None],
        *,
        width: int = 60,
        unit_scale: int = 1,
    ) -> None:
        label_id = self.text(
            x,
            y,
            label,
            size=14,
            color=THEME["action"],
            width=width,
            font_scale=unit_scale,
        )
        bounds = (
            x - 4 * unit_scale,
            y - 6 * unit_scale,
            x + width,
            y + 24 * unit_scale,
        )
        self.view._button_labels.append((bounds, label_id, THEME["action"], True))
        self.view._targets.append((bounds, action))
