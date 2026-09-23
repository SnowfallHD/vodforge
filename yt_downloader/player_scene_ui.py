"""The embedded player composition; playback and metadata owners stay separate."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from functools import partial
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any

from PIL import ImageTk

from .library_state import format_duration
from .player_related import player_related_plan
from .scene_components import ScenePainter, scene_font
from .scene_paging import scene_page
from .ui_button_contract import ProductButton
from .ui_chrome import layered_surface_image
from .ui_layout import ellipsize_wrapped_text, prose_excerpt
from .ui_theme import THEME
from .ui_widgets import SleekScrollbar, _tinted_ui_icon, bind_smooth_vertical_wheel
from .watch_ui import WatchView


class PlayerRelatedView(WatchView):
    """Reuse the actual Watch cards/artwork and bounded browsing in the player."""

    _thumbnail_aspect = (9, 16)

    def __init__(
        self,
        master: tk.Misc,
        *,
        current: dict[str, Any],
        on_presented: Callable[[], None],
        on_avatar: Callable[[Any], None],
        queue_keys: Sequence[str] | None = None,
        section_kind: str = "recent",
        **kwargs: Any,
    ):
        self._section_kind = section_kind
        self._on_presented = on_presented
        self._on_avatar = on_avatar
        self._related_visible = False
        self._current = current
        self._queue_keys = tuple(queue_keys) if queue_keys is not None else None
        self._related_section = ""
        self._related_plan = player_related_plan((), current)
        super().__init__(master, **kwargs)
        self.canvas.grid_configure(pady=0)

    def set_records(self, records: Sequence[dict[str, Any]]) -> None:
        self._related_plan = player_related_plan(
            records, self._current, self._queue_keys
        )
        super().set_records(records)

    def _open_related(self, section: str) -> None:
        self._targets.clear()
        for rail in self.__dict__.get("_scene_rails", {}).values():
            rail.retire()
        self._related_section, self._page = section, 0
        self.canvas.yview_moveto(0)
        self._presentation_change("navigation")
        self._queue_render()

    def _render_streaming_scene(self, width: int, columns: int) -> None:
        self._browse_heading.grid_remove()
        self._browse_footer.grid_remove()
        p = ScenePainter(self)
        self._scene_used_rails: set[str] = set()
        self._scene_window = None
        self._on_avatar(
            self._artwork_image(self._current, tile_size=(44, 44), role="avatar")
        )
        sections = (
            (
                (
                    "Up Next" if self._queue_keys is not None else "More to watch",
                    self._related_plan.up_next,
                ),
            )
            if self._section_kind == "side"
            else (("Recently Added", self._related_plan.recent),)
        )
        self._presentation_matching = len(self._related_plan.recent)
        self._presentation_mode_eligible = self._presentation_matching
        y = 0
        for label, videos in sections:
            if not videos or (self._related_section and label != self._related_section):
                continue
            if self._section_kind == "side":
                y = self._scene_heading(p, label, y, width)
                page = scene_page(videos, self._page, 6)
                self._page = page.index
                for index, video in enumerate(page.items):
                    self._scene_media(p, video, 0, y + index * (self._card_height + 56))
                y += len(page.items) * (self._card_height + 56)
                y = self._scene_pager(p, y, page)
            elif self._related_section:
                p.button(
                    0,
                    y,
                    180,
                    "Back to suggestions",
                    partial(self._open_related, ""),
                    icon="back",
                )
                y += 58
                y = self._scene_heading(p, label, y, width)
                y = self._scene_media_window(p, videos, y, columns)
            else:
                y = self._scene_heading(
                    p,
                    label,
                    y,
                    width,
                    partial(self._open_related, label),
                )
                y = self._scene_strip("recent", videos, "media", y, width)
        strips = self.__dict__.get("_scene_rails", {})
        for key in tuple(strips):
            if key not in self._scene_used_rails:
                strips.pop(key).destroy()
        self._presentation_extra_canvases = tuple(
            rail.canvas for rail in strips.values() if rail._active and not rail._closed
        )
        self.canvas.configure(scrollregion=(0, 0, width, max(1, y)))
        self._paint_focus()
        self._artwork_request()
        self._presentation_settle()
        self._observe_related_presentation(bool(y))

    def _observe_related_presentation(self, visible: bool) -> None:
        if visible and not self._related_visible:
            self._on_presented()
        self._related_visible = visible


class PlayerSceneMixin:
    def _build_streaming_identity(self: Any, root: ttk.Frame) -> None:
        header = ttk.Frame(root, style="FocusShell.TFrame")
        header.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(16, 10))
        header.columnconfigure(0, weight=1)
        title_value = str(self.info.get("title") or "Saved media")
        title = ttk.Label(
            header,
            text=title_value,
            font=scene_font(32, bold=True),
            style="TLabel",
            justify="left",
        )
        title.grid(row=0, column=0, sticky="w")
        creator = str(self.info.get("channel") or self.info.get("uploader") or "")
        category = str(
            self.info.get("playlist_title")
            or self.info.get("vodforge_user_category")
            or ""
        ).strip()
        if category.casefold() == creator.casefold():
            category = ""
        metadata_value = "  \u00b7  ".join(
            str(value)
            for value in (
                creator,
                category,
            )
            if value
        )
        identity = ttk.Frame(header, style="FocusShell.TFrame")
        identity.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(9, 0))
        avatar = tk.Canvas(
            identity, width=44, height=44, bg=THEME["bg"], bd=0, highlightthickness=0
        )
        avatar.pack(side="left", anchor="n", padx=(0, 12))
        avatar.create_oval(0, 0, 44, 44, fill=THEME["accent_surface"], outline="")
        avatar.create_text(
            22,
            22,
            text=(creator[:1] or "V").upper(),
            fill=THEME["text"],
            font=scene_font(20, bold=True),
        )
        self._creator_avatar = avatar
        copy = ttk.Frame(identity, style="FocusShell.TFrame")
        copy.pack(side="left", fill="x", expand=True)
        metadata_row = ttk.Frame(copy, style="FocusShell.TFrame")
        metadata_row.pack(anchor="w", fill="x")
        metadata = ttk.Label(
            metadata_row, text=metadata_value, font=scene_font(15), style="TLabel"
        )
        metadata.pack(side="left")
        duration = format_duration(self.info.get("duration"))
        facts = ("  \u00b7  " if metadata_value else "") + duration
        facts_label = ttk.Label(
            metadata_row, text=facts, font=scene_font(15), style="Muted.TLabel"
        )
        facts_label.pack(side="left")
        format_value = str(self.info.get("vodforge_output_type") or "")
        format_width = 0
        if format_value:
            badge_font = tkfont.Font(root=root, font=scene_font(13))
            format_value = ellipsize_wrapped_text(
                format_value,
                maximum_width=100,
                maximum_lines=1,
                measure_width=badge_font.measure,
            )
            format_width = badge_font.measure(format_value) + 20
            badge = tk.Canvas(
                metadata_row,
                width=format_width,
                height=24,
                bg=THEME["bg"],
                bd=0,
                highlightthickness=0,
            )
            badge.pack(side="left", padx=(12, 0))
            self._format_badge_image = ImageTk.PhotoImage(
                layered_surface_image(
                    format_width,
                    24,
                    fill=THEME["panel"],
                    edge=THEME["border"],
                    radius=12,
                )
            )
            badge.create_image(0, 0, anchor="nw", image=self._format_badge_image)
            badge.create_text(
                format_width / 2,
                12,
                text=format_value,
                font=scene_font(13),
                fill=THEME["muted"],
            )
            format_width += 12
        description_value = str(self.info.get("description") or "")
        description = ttk.Label(
            copy,
            text=description_value,
            font=scene_font(15),
            style="Muted.TLabel",
            justify="left",
        )
        description.pack(anchor="w", pady=(8, 0))
        description_more = ProductButton(
            copy,
            text="Read more",
            width=0,
            command=self._read_description,
            style="Media.FocusQuiet.TButton",
            takefocus=True,
        )
        self._description_excerpt = description
        self._description_more = description_more
        self._description_expanded = False
        description_panel = ttk.Frame(copy, style="FocusShell.TFrame")
        description_panel.columnconfigure(0, weight=1)
        description_body = tk.Text(
            description_panel,
            height=4,
            width=1,
            wrap="word",
            font=scene_font(15),
            bg=THEME["bg"],
            fg=THEME["muted"],
            bd=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            takefocus=True,
        )
        description_body.insert("1.0", description_value)
        description_body.configure(state="disabled")
        description_body.grid(row=0, column=0, sticky="ew")
        description_scroll = SleekScrollbar(
            description_panel, command=description_body.yview
        )
        description_scroll.configure(bg=THEME["bg"])
        description_scroll.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        description_body.configure(yscrollcommand=description_scroll.set)
        bind_smooth_vertical_wheel(description_body, description_scroll, mode="pixels")
        self._description_panel = description_panel
        self._description_body = description_body
        actions = ttk.Frame(header, style="FocusShell.TFrame")
        actions.grid(row=0, column=1, sticky="ne", padx=(20, 0))
        self._identity_action_images = [
            _tinted_ui_icon("arrow-left", size=(18, 18), color=THEME["icon"]),
            _tinted_ui_icon("folder", size=(18, 18), color=THEME["icon"]),
        ]
        ProductButton(
            actions,
            text="Back to Library"
            if self._entry_origin == "library"
            else "Back to Watch",
            command=self.close,
            width=0,
            compound="left",
            image=self._identity_action_images[0] or "",
            style="Streaming.Media.FocusQuiet.TButton",
        ).pack(side="left", padx=(0, 10))
        if self._on_details is not None:
            ProductButton(
                actions,
                text="View in Library",
                command=self._on_details,
                image=self._identity_action_images[1] or "",
                compound="left",
                width=0,
                style="Streaming.Media.FocusQuiet.TButton",
            ).pack(side="left", padx=(0, 10))
        fonts = [
            tkfont.Font(root=root, font=scene_font(size, bold=size == 32))
            for size in (32, 15, 15)
        ]

        def fit(event: Any) -> None:
            compact = event.width < 960
            title.grid_configure(columnspan=2 if compact else 1)
            actions.grid_configure(
                row=1 if compact else 0,
                column=0 if compact else 1,
                columnspan=2 if compact else 1,
                sticky="w" if compact else "ne",
                padx=0 if compact else (20, 0),
                pady=(8, 0) if compact else 0,
            )
            identity.grid_configure(row=2 if compact else 1)
            text_width = max(
                220,
                event.width if compact else event.width - actions.winfo_reqwidth() - 28,
            )
            for widget, value, font, width, lines in (
                (title, title_value, fonts[0], text_width, 2),
                (
                    metadata,
                    metadata_value,
                    fonts[1],
                    max(
                        100,
                        event.width - 60 - facts_label.winfo_reqwidth() - format_width,
                    ),
                    1,
                ),
                (
                    description,
                    description_value,
                    fonts[2],
                    max(220, event.width - 60),
                    1,
                ),
            ):
                fitted = ellipsize_wrapped_text(
                    value,
                    maximum_width=width,
                    maximum_lines=lines,
                    measure_width=font.measure,
                )
                if widget is description:
                    fitted = prose_excerpt(value, fitted)
                    if (
                        fitted != value or self._description_expanded
                    ) and value.strip():
                        description_more.pack(anchor="w", pady=(3, 0))
                    else:
                        description_more.pack_forget()
                widget.configure(wraplength=width, text=fitted)

        header.bind("<Configure>", fit, add="+")
        self._identity_header = header

    def _read_description(self: Any) -> None:
        if self._closed or not str(self.info.get("description") or "").strip():
            return
        self._description_expanded = not self._description_expanded
        if self._description_expanded:
            self._description_excerpt.pack_forget()
            self._description_panel.pack(
                before=self._description_more, fill="x", pady=(8, 0)
            )
            self._description_more.configure(text="Show less")
            self._description_body.focus_set()
        else:
            self._description_panel.pack_forget()
            self._description_excerpt.pack(
                before=self._description_more, anchor="w", pady=(8, 0)
            )
            self._description_more.configure(text="Read more")
        self._on_feature(
            "description_opened" if self._description_expanded else "description_closed"
        )

    def _present_creator_avatar(self: Any, image: Any) -> None:
        if image is not None and not self._closed:
            self._creator_avatar_image = image
            self._creator_avatar.delete("artwork")
            self._creator_avatar.create_image(
                0, 0, image=image, anchor="nw", tags="artwork"
            )

    def _build_streaming_related(self: Any) -> None:
        for kind, attribute in (
            ("side", "_related_view"),
            ("recent", "_related_recent_view"),
        ):
            related = PlayerRelatedView(
                self._content_root,
                current=self.info,
                section_kind=kind,
                queue_keys=self.__dict__.get("_queue_keys"),
                on_presented=self._related_presented,
                on_avatar=self._present_creator_avatar,
                on_play=self._play_related_index,
                on_details=self._details_related_index,
                thumbnail_path=self._related_thumbnail_path,
                artwork_source=self._related_artwork_source,
            )
            related.grid_propagate(False)
            related.set_records(self._library_records)
            setattr(self, attribute, related)
        for row in range(6):
            self._content_root.rowconfigure(row, weight=0, minsize=0)
        self.stage_shell.grid_configure(row=0, column=0, sticky="n", padx=0)
        self.transport.grid_configure(row=1, column=0, sticky="ew", padx=0)
        self._content_root.bind("<Configure>", self._streaming_resize, add="+")
        self._page_surface.viewport.bind(
            "<Configure>", lambda _event: self._streaming_resize(None), add="+"
        )

    def _information_section(self: Any, title: str) -> ttk.Frame:
        section = ttk.Frame(self._details_shell, style="FocusShell.TFrame")
        section.pack(fill="x", pady=(0, 22))
        ttk.Label(section, text=title, font=scene_font(20, bold=True)).pack(
            anchor="w", pady=(0, 10)
        )
        body = ttk.Frame(section, style="FocusShell.TFrame")
        body.pack(fill="x")
        body.columnconfigure(0, weight=1)
        target = {
            "Chapters": "chapters",
            "Your details": "notes",
            "Source details": "source",
            "Output details": "output",
            "Moments": "moments",
        }[title]
        self._information_sections[str(body)] = body
        self._detail_targets[str(body)] = target
        return body

    def _observe_information(self: Any) -> None:
        if self._closed or not self.popup.winfo_ismapped():
            return
        viewport = self._page_surface.viewport
        if viewport is None:
            return
        top, bottom = (
            viewport.winfo_rooty(),
            viewport.winfo_rooty() + viewport.winfo_height(),
        )
        for key, section in self._information_sections.items():
            target = self._detail_targets[key]
            y = section.winfo_rooty()
            visible = min(bottom, y + section.winfo_height()) - max(top, y)
            if visible >= 24 and target not in self._information_seen:
                self._information_seen.add(target)
                self._on_feature("detail_viewed", dimensions={"detail_target": target})

    def _build_streaming_information(self: Any, root: ttk.Frame) -> None:
        from .detail_ui import FactsText
        from .media_player_ui import ChapterList
        from .ui_widgets import bind_smooth_vertical_wheel

        self._details_shell = ttk.Frame(root, style="FocusShell.TFrame")
        self._details_visible = True
        self._information_sections = {str(self._identity_header): self._identity_header}
        self._detail_targets[str(self._identity_header)] = "info"
        self._information_seen: set[str] = set()
        chapters = self._information_section("Chapters")
        self.chapter_list: Any = None
        if self._chapters:
            self.chapter_list = ChapterList(chapters, self._chapters)
            self.chapter_list.grid(row=0, column=0, sticky="ew")
            self.chapter_list.bind("<<ListboxSelect>>", self._chapter_selected)
            self.chapter_list.bind("<<TreeviewSelect>>", self._chapter_selected)
            scroll = SleekScrollbar(chapters, command=self.chapter_list.yview)
            scroll.grid(row=0, column=1, sticky="ns")
            self.chapter_list.configure(yscrollcommand=scroll.set)
        else:
            ttk.Label(
                chapters, text="No chapters in this media.", style="Muted.TLabel"
            ).grid(row=0, column=0, sticky="w")
        note = str(self.info.get("vodforge_user_note") or "")
        tags = ", ".join(str(tag) for tag in self.info.get("vodforge_user_tags") or ())
        category = str(self.info.get("vodforge_user_category") or "")
        details = "\n".join(
            value
            for value in (
                "Collection: " + category if category else "",
                "Tags: " + tags if tags else "",
                "Note: " + note if note else "",
            )
            if value
        )
        source_tags = ", ".join(str(tag) for tag in self.info.get("tags") or ())
        source = self._source_details + "\nSource ID: " + str(self.info.get("id") or "")
        if source_tags:
            source += "\nSource tags: " + source_tags
        for title, content in (
            ("Your details", details or "Add a note or tags in Library."),
            ("Source details", source),
            ("Output details", self._output_details),
        ):
            body = self._information_section(title)
            document = FactsText(
                body,
                height=min(12, max(3, len(content.splitlines()))),
                bg=THEME["bg"],
                font=scene_font(14),
            )
            document.grid(row=0, column=0, sticky="ew")
            document.request(content or "No saved details.")
            scroll = SleekScrollbar(body, command=document.yview)
            scroll.grid(row=0, column=1, sticky="ns")
            document.configure(yscrollcommand=scroll.set)
            bind_smooth_vertical_wheel(document, scroll, mode="pixels")
            if title == "Your details" and self._on_edit_notes is not None:
                ProductButton(
                    body,
                    text="Edit your details",
                    command=self._on_edit_notes,
                    style="Compact.TButton",
                ).grid(row=1, column=0, sticky="w", pady=(8, 0))

    def _related_presented(self: Any) -> None:
        if not self._closed:
            self._on_feature("related_shown")

    def _play_related_index(self: Any, index: int) -> None:
        self._related_index(index, details=False)

    def _details_related_index(self: Any, index: int) -> None:
        self._related_index(index, details=True)

    def _related_index(self: Any, index: int, *, details: bool) -> None:
        related = self.__dict__.get("_related_view")
        if related is not None and 0 <= index < len(related._records):
            self._select_related_record(related._records[index], details=details)

    def _select_related_record(
        self: Any, record: dict[str, Any], *, details: bool
    ) -> None:
        if self._closed:
            return
        callback = self._on_record_details if details else self._on_related_play
        if callback is not None:
            self._on_feature("related_details" if details else "related_selected")
            callback(record)

    def _streaming_resize(self: Any, event: Any) -> None:
        width = getattr(event, "width", None) or self._content_root.winfo_width()
        wide = width >= 1080
        side_width = 310 if wide else 0
        viewport_width = max(320, width - side_width - (24 if wide else 0))
        # Keep transport visible in short windows without cropping the video.
        page_height = self._page_surface.viewport.winfo_height()
        if page_height > 1:
            available_height = max(
                180, page_height - self.transport.winfo_reqheight() - 24
            )
            viewport_width = min(viewport_width, round(available_height * 16 / 9))
        self.stage_shell.configure(
            width=viewport_width, height=round(viewport_width * 9 / 16)
        )
        self._content_root.columnconfigure(1, minsize=side_width, weight=0)
        self.stage_shell.grid_configure(columnspan=1 if wide else 2)
        if self._native_overlay is None:
            self.transport.grid_configure(columnspan=1 if wide else 2)
        else:
            self.transport.grid_remove()
        self._identity_header.grid_configure(columnspan=1 if wide else 2)
        self._related_view.configure(
            width=side_width or width,
            height=round(viewport_width * 9 / 16) + 230 if wide else 360,
        )
        self._related_view.grid(
            row=0 if wide else 3,
            column=1 if wide else 0,
            rowspan=3 if wide else 1,
            columnspan=1 if wide else 2,
            sticky="nsew",
            padx=(24, 0) if wide else 0,
            pady=0 if wide else (16, 0),
        )
        columns = max(1, min(5, (width + 14) // 244))
        self._related_recent_view.configure(height=(width // columns) * 9 // 16 + 110)
        self._related_recent_view.grid(
            row=3 if wide else 4, column=0, columnspan=2, sticky="ew", pady=(18, 12)
        )
        self._details_shell.grid(
            row=4 if wide else 5, column=0, columnspan=2, sticky="ew", pady=(16, 0)
        )

    def set_library_records(self: Any, records: Sequence[dict[str, Any]]) -> None:
        self._library_records = tuple(records)
        for name in ("_related_view", "_related_recent_view"):
            related = self.__dict__.get(name)
            if related is not None and not self._closed:
                related.set_records(records)

    def set_queue_keys(self: Any, keys: Sequence[str] | None) -> None:
        self._queue_keys = tuple(keys) if keys is not None else None
        related = self.__dict__.get("_related_view")
        if related is not None and not self._closed:
            related._queue_keys = self._queue_keys
            related._related_section = ""
            related.set_records(self._library_records)
