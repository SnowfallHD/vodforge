"""Responsive item detail view with facts, personal annotations and file actions."""

from __future__ import annotations

from functools import partial
from typing import Any

from .archive_browser import archive_row_owner
from .library_scene_facts import library_detail_facts
from .library_state import format_duration
from .scene_components import ScenePainter, scene_font
from .ui_button_contract import button_metrics
from .ui_layout import window_logical_metrics
from .ui_theme import THEME


class LibraryDetailLayout:
    def _detail_panel(
        self: Any,
        p: ScenePainter,
        x: int,
        y: int,
        width: int,
        title: str,
        icon: str,
        fields: Any,
        index: int,
    ) -> int:
        # Text is drawn first so its actual wrapped height determines each row.
        # Every continuation retains value_x; labels never become wrap anchors.
        metrics = window_logical_metrics(self)
        px, scale = metrics.px, metrics.scale
        panel_items = set(self.canvas.find_all())
        p.icon(icon, x + px(18), y + px(18), px(20), stroke_width=1.4 * scale)
        p.text(
            x + px(54),
            y + px(17),
            title,
            size=20,
            width=width - px(72),
            font_scale=scale,
        )
        self.canvas.create_line(
            x + px(17), y + px(51), x + width - px(17), y + px(51), fill=THEME["border"]
        )
        yy = y + px(69)
        for label, value, item_icon in fields:
            # Labels and trailing actions each own space; long text cannot paint
            # beneath a copy button or steal its click target.
            label_width = min(px(138), width * 29 // 100)
            icon_x = x + label_width + px(18)
            value_x = icon_x + px(30)
            trailing = (
                px(button_metrics("inline").height) + px(12)
                if label == "Saved Location"
                else px(17)
            )
            value_width = max(1, x + width - trailing - px(12) - value_x)
            label_item = p.text(
                x + px(17),
                yy,
                label,
                size=14,
                color=THEME["muted"],
                width=label_width - px(5),
                lines=None,
                font_scale=scale,
            )
            p.icon(
                item_icon, icon_x, yy, px(16), THEME["muted"], stroke_width=1.4 * scale
            )
            color = (
                THEME["accent"]
                if label in {"Playlist", "Source URL", "Saved Location"}
                else THEME["text"]
            )
            item = p.text(
                value_x,
                yy,
                value,
                size=14,
                color=color,
                width=value_width,
                lines=None,
                font_scale=scale,
            )
            bounds = self.canvas.bbox(item)
            label_bounds = self.canvas.bbox(label_item)
            row_bottom = max(
                yy + px(24),
                bounds[3] + px(8) if bounds else yy + px(24),
                label_bounds[3] + px(8) if label_bounds else yy + px(24),
            )
            callback = partial(self._copy_value, value)
            if label == "Source URL" and value.startswith(("https://", "http://")):
                callback = partial(self._action, "source_url", index)
            if label == "Saved Location":
                callback = partial(self._action, "folder", index)
            self._targets.append(
                ((value_x - 4, yy - px(5), value_x + value_width, row_bottom), callback)
            )
            if label == "Saved Location":
                p.button(
                    x + width - px(12) - px(button_metrics("inline").height),
                    yy - px(7),
                    None,
                    "",
                    partial(self._copy_value, value),
                    icon="copy",
                    variant="inline",
                    unit_scale=scale,
                )
            yy = row_bottom + px(8)
        bottom = yy + px(8)
        # Place the surface below only the content painted by this panel.
        content = set(self.canvas.find_all()) - panel_items
        self._depth.draw(
            (x, y, x + width, bottom), role="detail", unit_scale=scale, radius=px(10)
        )
        for item in content:
            self.canvas.tag_raise(item)
        return bottom - y

    def _detail_notes(
        self: Any,
        p: ScenePainter,
        row: dict,
        index: int,
        x: int,
        y: int,
        width: int,
        *,
        tags: bool = False,
    ) -> int:
        metrics = window_logical_metrics(self)
        px, scale = metrics.px, metrics.scale
        owner = archive_row_owner(row)
        if not tags:
            local = "vodforge_user_description" in row
            value = str(
                row.get("vodforge_user_description")
                if local
                else row.get("description") or ""
            )
            section = self._description_section
            section.present(
                owner, value, "Your description" if local else "Source description"
            )
            height = section.height_for_width(width - px(32)) + px(24)
            self._depth.draw(
                (x, y, x + width, y + height),
                role="detail",
                unit_scale=scale,
                radius=px(10),
            )
            self.canvas.create_window(
                x + px(8),
                y + px(8),
                window=section,
                anchor="nw",
                width=width - px(16),
                height=height - px(16),
            )
            return height
        values = tuple(str(tag) for tag in row.get("vodforge_user_tags") or ())
        content = set(self.canvas.find_all())
        p.icon("tag", x + px(20), y + px(18), px(22), stroke_width=1.4 * scale)
        p.text(x + px(56), y + px(18), "Tags", size=20, font_scale=scale)
        p.button(
            x + width - px(16) - px(button_metrics("inline").height),
            y + px(10),
            None,
            "",
            partial(self._copy_value, ", ".join(values)),
            icon="copy",
            variant="inline",
            unit_scale=scale,
        )
        tx, ty = x + px(20), y + px(62)
        for tag in values:
            tw = min(
                width - px(40), max(px(64), min(px(200), len(tag) * px(7) + px(48)))
            )
            if tx + tw > x + width - px(20):
                tx, ty = x + px(20), ty + px(38)
            self._surface(
                tx,
                ty,
                tw,
                px(30),
                fill=THEME["accent_surface"],
                edge=THEME["border"],
                radius=px(15),
                unit_scale=scale,
            )
            p.text(
                tx + px(11),
                ty + px(7),
                tag,
                size=12,
                width=tw - px(42),
                font_scale=scale,
            )
            # Text and hit box use the same center, independent of font metrics.
            center = tx + tw - px(16)
            self.canvas.create_text(
                center,
                ty + px(15),
                text="\u00d7",
                font=scene_font(16, font_scale=scale),
                fill=THEME["muted"],
            )
            self._targets.append(
                (
                    (center - px(13), ty, center + px(13), ty + px(30)),
                    partial(self._remove_tag, owner, tag),
                )
            )
            tx += tw + px(8)
        if not values:
            p.text(
                tx + 4,
                ty + px(7),
                "Add your own tags",
                size=13,
                color=THEME["muted"],
                font_scale=scale,
            )
        input_y = ty + px(46)
        self._surface(
            x + px(20),
            input_y,
            width - px(40),
            px(40),
            fill=THEME["bg"],
            unit_scale=scale,
        )
        self.canvas.create_window(
            x + px(30),
            input_y + px(6),
            window=self._tag_entry,
            anchor="nw",
            width=max(px(80), width - px(94)),
            height=max(px(28), self._tag_entry.winfo_reqheight()),
        )
        self._refresh_tag_hint()
        p.button(
            x + width - px(24) - px(button_metrics("inline").height),
            input_y + (px(40) - px(button_metrics("inline").height)) // 2,
            None,
            "",
            partial(self._submit_tag, index),
            icon="plus",
            variant="inline",
            unit_scale=scale,
        )
        p.text(
            x + px(20),
            input_y + px(53),
            "Press return to add a tag",
            size=11,
            color=THEME["muted"],
            font_scale=scale,
        )
        height = input_y + px(80) - y
        painted = set(self.canvas.find_all()) - content
        self._depth.draw(
            (x, y, x + width, y + height),
            role="detail",
            unit_scale=scale,
            radius=px(10),
        )
        for item in painted:
            self.canvas.tag_raise(item)
        return height

    def _details(self: Any, p: ScenePainter, width: int) -> int:
        metrics = window_logical_metrics(self)
        px, scale = metrics.px, metrics.scale
        found = next(
            (
                (i, row)
                for i, row in enumerate(self._records)
                if archive_row_owner(row) == self._detail_owner
            ),
            None,
        )
        if found is None:
            self._route = "home"
            return self._browse(p, width)
        index, row = found
        self._context_targets.append(((0, 0, width, px(5000)), archive_row_owner(row)))
        compact = width < px(1020)
        p.button(
            0,
            0,
            px(180),
            "Back to folders"
            if self.__dict__.get("_detail_return_callback")
            else "Back to Library",
            self.return_from_detail,
            icon="back",
            unit_scale=scale,
        )
        left = width if compact else min(px(475), width * 43 // 100)
        image_height = min(px(360), left * 9 // 16) if compact else px(246)
        top = px(43)
        self._depth.draw(
            (0, top, left, top + image_height), unit_scale=scale, radius=px(10)
        )
        image = self._artwork_image(row, tile_size=(left, image_height))
        if image:
            self.canvas.create_image(
                0, top, image=image, anchor="nw", tags="presentation-artwork"
            )
        center_y = top + image_height // 2
        self._surface(
            left // 2 - px(32),
            center_y - px(32),
            px(64),
            px(64),
            fill=THEME["surface"],
            edge=THEME["muted"],
            radius=px(32),
            unit_scale=scale,
        )
        p.icon(
            "play",
            left // 2 - px(10),
            center_y - px(11),
            px(23),
            stroke_width=2 * scale,
        )
        self._targets.append(
            ((0, top, left, top + image_height), partial(self._action, "play", index))
        )
        self._duration(
            p, row, left - px(9), top + image_height - px(34), unit_scale=scale
        )
        x = 0 if compact else left + px(27)
        title_y = top + image_height + px(22) if compact else px(48)
        rw = width - x
        title_item = p.text(
            x,
            title_y,
            str(row.get("title") or "Saved media"),
            size=32,
            bold=True,
            width=rw,
            lines=2,
            font_scale=scale,
        )
        chip = str(
            row.get("vodforge_user_category")
            or (row.get("vodforge_user_tags") or ["Saved media"])[0]
        )
        title_bounds = self.canvas.bbox(title_item)
        chip_y = max(
            title_y + (px(70) if compact else px(62)),
            title_bounds[3] + px(12) if title_bounds else title_y,
        )
        chipwidth = self._pill(p, x, chip_y, chip, maximum=px(140), unit_scale=scale)
        output = (row.get("vodforge_encoding_summary") or {}).get("output") or {}
        p.text(
            x + chipwidth + px(14),
            chip_y + px(7),
            "  ·  ".join(
                str(v)
                for v in (
                    format_duration(row.get("duration")),
                    row.get("vodforge_output_type"),
                    output.get("Output resolution"),
                )
                if v
            ),
            size=15,
            color=THEME["muted"],
            width=max(px(80), rw - chipwidth - px(14)),
            font_scale=scale,
        )
        p.text(
            x,
            chip_y + px(52),
            str(
                row.get("vodforge_user_description", row.get("description"))
                or "Saved in your Library."
            ),
            size=17,
            color=THEME["muted"],
            width=rw,
            lines=3,
            prose=True,
            font_scale=scale,
        )
        actions_y = chip_y + px(125)
        widths = [px(100), px(166), px(button_metrics().height)]
        bx = x
        bottom = actions_y + px(40)
        for n, (label, icon, action) in enumerate(
            (
                ("Play", "play", "play"),
                ("Show in Folder", "folder", "folder"),
                ("", "more", "more"),
            )
        ):
            bw = widths[n]
            if bx > x and bx + bw > x + rw:
                bx = x
                actions_y += px(56)
            by = actions_y
            p.button(
                bx,
                by,
                bw,
                label,
                partial(self._open_item_menu, archive_row_owner(row))
                if action == "more"
                else partial(self._action, action, index),
                icon=icon,
                primary=action == "play",
                unit_scale=scale,
            )
            bx += bw + px(12)
            bottom = max(bottom, by + px(40))
        note_y = max(top + image_height, bottom) + px(22)
        versions = tuple(
            (owner, label)
            for owner, label in self.__dict__.get("_detail_versions", ())
            if any(archive_row_owner(item) == owner for item in self._records)
        )
        if len(versions) > 1:
            p.text(
                0,
                note_y,
                "Saved version",
                size=13,
                color=THEME["muted"],
                font_scale=scale,
            )
            self._version_choice.configure(
                values=tuple(label for _owner, label in versions)
            )
            self._version_var.set(
                next(
                    (label for owner, label in versions if owner == self._detail_owner),
                    "",
                )
            )
            version_height = max(px(38), self._version_choice.winfo_reqheight())
            self.canvas.create_window(
                0,
                note_y + px(26),
                window=self._version_choice,
                anchor="nw",
                width=min(px(380), width),
                height=version_height,
            )
            note_y += px(44) + version_height
        description_width = width if compact else round(width * 0.62)
        description_height = self._detail_notes(
            p, row, index, 0, note_y, description_width
        )
        tags_height = self._detail_notes(
            p,
            row,
            index,
            0 if compact else description_width + px(16),
            note_y + description_height + px(16) if compact else note_y,
            width if compact else width - description_width - px(16),
            tags=True,
        )
        panel_y = note_y + (
            description_height + tags_height + px(32)
            if compact
            else max(description_height, tags_height) + px(16)
        )
        source_fields, output_fields = library_detail_facts(row)
        panel = width if compact else (width - px(16)) // 2
        source_height = self._detail_panel(
            p, 0, panel_y, panel, "Source Details", "link", source_fields, index
        )
        output_height = self._detail_panel(
            p,
            0 if compact else panel + px(16),
            panel_y + source_height + px(16) if compact else panel_y,
            panel,
            "Output Details",
            "document",
            output_fields,
            index,
        )
        self._rendered_count = 1
        self._matching_count = 1
        return panel_y + (
            source_height + output_height + px(32)
            if compact
            else max(source_height, output_height) + px(16)
        )
