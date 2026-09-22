from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from functools import partial
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any

from .archive_artwork import ArchiveArtworkMixin
from .archive_browser import PAGE_SIZE, ArchiveBrowserModel, ArchiveComponent
from .archive_paths import ArchivePath
from .archive_presentation import media_badge, rounded_surface
from .presentation_diagnostics import count_bucket
from .storage_labels import LocationLabel, location_labels
from .ui_button_contract import ProductButton
from .ui_chrome import CanvasSurfaceCache, prototype_treeview_style
from .ui_context_menu import ContextMenu
from .ui_layout import ellipsize_wrapped_text, window_logical_metrics
from .ui_theme import FONT_UI, FONT_UI_SMALL, THEME
from .ui_widgets import SleekScrollbar, ToolTip, bind_smooth_vertical_wheel
from .volume_storage import StorageVolume


class ArchiveBrowser(ArchiveArtworkMixin, ttk.Frame):
    """Folder/media navigation with at most one page of Canvas components.

    Compatibility selection methods keep existing Library commands attached to
    the canonical projection. This widget does not own or persist history.
    """

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_select: Callable[[], None],
        on_activate: Callable[[int], None],
        on_menu: Callable[[Any], Any],
        on_folder: Callable[[ArchivePath, tuple[int, ...]], None],
        on_relink: Callable[[ArchivePath, tuple[int, ...]], None],
        on_usage: Callable[..., None] | None = None,
        telemetry: Any = None,
        thumbnail_path: Callable[..., Any] | None = None,
        nav_master: tk.Misc | None = None,
    ) -> None:
        super().__init__(master, style="FocusShell.TFrame")
        self.model = ArchiveBrowserModel()
        self._location_volumes: tuple[StorageVolume, ...] = ()
        self._location_labels: dict[str, LocationLabel] = {}
        self._presentation_mode_origin = "default"
        self._presentation_query_active = False
        self._presentation_filter_active = False
        self._on_usage = on_usage or (lambda *args, **kwargs: None)
        self._on_select, self._on_activate = on_select, on_activate
        self._on_menu, self._on_folder, self._on_relink = on_menu, on_folder, on_relink
        self._render_after: str | None = None
        self._boxes: list[tuple[tuple[int, int, int, int], ArchiveComponent]] = []
        self._last_row = ""
        self._open_boxes: list[tuple[tuple[int, int, int, int], ArchiveComponent]] = []
        self._columns = 1
        self._hovered_component: ArchiveComponent | None = None
        self._location_states: dict[tuple[str, ...], str] = {}
        self._selected_folder: ArchiveComponent | None = None
        self._render_signature: Any = None
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        nav_parent = nav_master or self
        nav_metrics = window_logical_metrics(nav_parent)
        px = nav_metrics.px
        nav = ttk.Frame(
            nav_parent, style="Material.TFrame", width=px(184), padding=(px(12), px(8))
        )
        self.navigation = nav
        self._external_navigation = nav_master is not None
        nav.grid(
            row=0,
            column=0,
            rowspan=2 if nav_master is not None else 3,
            sticky="nsew",
            padx=(0, px(20)),
            pady=(px(20), 0) if nav_master is not None else 0,
        )
        nav.grid_propagate(False)
        nav.columnconfigure(0, weight=1)
        nav.rowconfigure(5, weight=1)
        eyebrow_font = nav_metrics.font(
            tuple(
                nav.tk.splitlist(
                    ttk.Style(nav).lookup("Sidebar.FocusEyebrow.TLabel", "font")
                )
            )
        )
        ttk.Label(
            nav, text="BROWSE", style="Sidebar.FocusEyebrow.TLabel", font=eyebrow_font
        ).grid(row=0, column=0, sticky="w", pady=(px(8), px(8)))
        self._nav_buttons = {}
        for row, (title, mode) in enumerate(
            (
                ("Folders", "folders"),
                ("All media", "all"),
                ("Runs & previews", "activity"),
            ),
            start=1,
        ):
            button = ProductButton(
                nav,
                text=title,
                command=partial(self.navigate, None, mode=mode),
                style="Archive.FocusNav.TButton",
            )
            button.grid(row=row, column=0, sticky="ew", pady=px(3))
            self._nav_buttons[mode] = button
        ttk.Label(
            nav,
            text="Locations",
            style="Sidebar.FocusEyebrow.TLabel",
            font=eyebrow_font,
        ).grid(row=4, column=0, sticky="w", pady=(px(24), px(8)))
        location_shell = ttk.Frame(nav, style="FocusPanel.TFrame")
        location_shell.grid(row=5, column=0, sticky="nsew")
        location_shell.columnconfigure(0, weight=1)
        location_shell.rowconfigure(0, weight=1)
        self.location_list = ttk.Treeview(
            location_shell,
            show="tree",
            selectmode="browse",
            style=prototype_treeview_style(location_shell, "ArchiveLocations.Treeview"),
            height=5,
        )
        metrics = window_logical_metrics(location_shell)
        self.location_list.column(
            "#0", width=metrics.px(150), minwidth=metrics.px(100), stretch=True
        )
        self.location_list.grid(row=0, column=0, sticky="nsew")
        location_scroll = SleekScrollbar(
            location_shell, command=self.location_list.yview
        )
        location_scroll.grid(row=0, column=1, sticky="ns")
        self.location_list.configure(yscrollcommand=location_scroll.set)
        self.location_list.bind("<ButtonRelease-1>", self._location_selected)
        self.location_list.bind("<Return>", self._location_selected)
        ToolTip(self.location_list, self._location_tooltip_text)
        bind_smooth_vertical_wheel(self.location_list, location_scroll)
        toolbar = ttk.Frame(self, style="FocusShell.TFrame")
        self.folder_toolbar = toolbar
        toolbar.grid(row=0, column=1, sticky="ew", pady=(0, 10))
        toolbar.columnconfigure(1, weight=1)
        self.parent_button = ProductButton(
            toolbar, text="Up one folder", command=self._up, style="FocusQuiet.TButton"
        )
        self.parent_button.grid(row=0, column=0, padx=(0, 8))
        self.path_button = ProductButton(
            toolbar,
            text="All locations",
            command=self._path_menu,
            style="FocusQuiet.TButton",
        )
        self.path_button.grid(row=0, column=1, sticky="w")
        self.relink_button = ProductButton(
            toolbar,
            text="Find moved folder…",
            command=self._relink_folder,
            style="FocusQuiet.TButton",
            state="disabled",
        )
        self.relink_button.grid(row=0, column=2, sticky="e", padx=(8, 0))
        content = ttk.Frame(self, style="FocusShell.TFrame")
        content.grid(row=1, column=1, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(
            content, bg=THEME["bg"], highlightthickness=0, bd=0, takefocus=True
        )
        self._depth = CanvasSurfaceCache(self.canvas)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scroll = SleekScrollbar(content, command=self.canvas.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.bind("<Configure>", self._queue_render)
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Motion>", self._hover)
        self.canvas.bind("<Leave>", self._leave_hover)
        self.canvas.bind("<Double-1>", self._activate)
        self.canvas.bind("<Button-2>", self._menu)
        self.canvas.bind("<Button-3>", self._menu)
        self.canvas.bind("<Return>", self._keyboard_activate)
        self.canvas.bind("<Down>", lambda event: self._step(1, vertical=True))
        self.canvas.bind("<Right>", lambda event: self._step(1))
        self.canvas.bind("<Up>", lambda event: self._step(-1, vertical=True))
        self.canvas.bind("<Left>", lambda event: self._step(-1))
        self.canvas.bind("<Next>", lambda event: self._page(1))
        self.canvas.bind("<Prior>", lambda event: self._page(-1))
        bind_smooth_vertical_wheel(self.canvas, mode="pixels")
        footer = ttk.Frame(self, style="FocusShell.TFrame")
        footer.grid(row=2, column=1, sticky="ew", pady=(8, 0))
        footer.columnconfigure(0, weight=1)
        self.count_var = tk.StringVar(self, "")
        ttk.Label(footer, textvariable=self.count_var, style="Muted.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.previous = ProductButton(
            footer,
            text="Previous",
            command=lambda: self._page(-1),
            style="FocusQuiet.TButton",
        )
        self.previous.grid(row=0, column=1)
        self.next = ProductButton(
            footer,
            text="Next",
            command=lambda: self._page(1),
            style="FocusQuiet.TButton",
        )
        self.next.grid(row=0, column=2, padx=(5, 0))
        self._artwork_setup(thumbnail_path or (lambda record: None), (106, 60))
        self._presentation_setup(telemetry, "library")
        self.bind("<Destroy>", self._destroyed, add="+")

    def set_scene_projection_callback(self, callback: Any) -> None:
        self._scene_projection_callback = callback

    def set_records(
        self,
        records: Sequence[dict[str, Any]],
        visible: Sequence[int],
        *,
        select_index: int | None = None,
        query_active: bool = False,
        filters_active: bool = False,
    ) -> None:
        context_changed = (
            query_active != self._presentation_query_active
            or filters_active != self._presentation_filter_active
        )
        self._presentation_query_active = query_active
        self._presentation_filter_active = filters_active
        if tuple(records) != self.model.records:
            self._presentation_change("data")
        elif tuple(visible) != self.model.visible or context_changed:
            self._presentation_change("filter")
        self.model.replace(records, visible)
        callback = getattr(self, "_scene_projection_callback", None)
        if callback is not None:
            callback(records)
        if select_index is not None:
            self._selected_folder = None
            self.model.reveal(select_index)
        elif self._selected_folder is not None:
            self._selected_folder = next(
                (
                    item
                    for item in self.model.page_components
                    if item.kind == "folder" and item.key == self._selected_folder.key
                ),
                None,
            )
            self.model.selected_owner = ""
            self._last_row = ""
        self._render_locations()
        self._refresh()

    def navigate(self, path: ArchivePath | None, *, mode: Any = "folders") -> None:
        self._presentation_mode_origin = "user"
        self._presentation_change("navigation")
        self.model.navigate(path, mode=mode)
        self._on_usage(
            "archive",
            "folder_opened"
            if path
            else {"folders": "folders", "all": "all_media", "activity": "activity"}[
                mode
            ],
            archive_mode=mode,
        )
        self._selected_folder = None
        self.model.selected_owner = ""
        self._last_row = ""
        self.canvas.yview_moveto(0)
        self._refresh()
        if path is not None:
            indices = tuple(
                index
                for index in self.model.visible
                if (directory := self.model._directories.get(index)) is not None
                and directory.relative_to(path) is not None
            )
            self._on_folder(path, indices)
        else:
            self._on_select()

    def set_location_state(self, path: ArchivePath, state: str) -> None:
        self._location_states[path.key] = {
            "opened": "Available",
            "available": "Available",
            "missing": "Folder missing",
            "unavailable": "Storage unavailable",
            "foreign_platform": "Other platform",
            "cancelled": "Not checked",
        }.get(state, "Not checked")
        if len(self._location_states) > 64:
            self._location_states.pop(next(iter(self._location_states)))
        self._refresh()

    def _refresh(self) -> None:
        label = (
            self.model.path.name
            if self.model.path
            else {
                "folders": "All locations",
                "all": "All media",
                "activity": "Runs & previews",
            }[self.model.mode]
        )
        self.path_button.configure(
            text=label[:36]
            + ("…" if len(label) > 36 else "")
            + ("  ▾" if self.model.path else ""),
            state="normal" if self.model.path else "disabled",
        )
        self.parent_button.configure(state="normal" if self.model.path else "disabled")
        for mode, button in self._nav_buttons.items():
            button.configure(
                style="Archive.FocusNavActive.TButton"
                if mode == self.model.mode
                else "Archive.FocusNav.TButton"
            )
        self.relink_button.configure(
            state="normal" if self.model.path or self._selected_folder else "disabled"
        )
        if self.model.path or self._selected_folder:
            self.folder_toolbar.grid()
        else:
            self.folder_toolbar.grid_remove()
        if self.model.path:
            self.parent_button.grid()
            self.path_button.grid()
        else:
            self.parent_button.grid_remove()
            self.path_button.grid_remove()
        location_ids = [
            self._location_id(location.path)
            for location in self.model.locations
            if self.model.path is not None
            and location.path is not None
            and self.model.path.relative_to(location.path) is not None
        ]
        if location_ids:
            self.location_list.selection_set(location_ids[-1])
        else:
            self.location_list.selection_remove(*self.location_list.selection())
        count = len(self.model.components)
        pages = max(1, (count + PAGE_SIZE - 1) // PAGE_SIZE)
        noun = (
            ("location" if count == 1 else "locations")
            if self.model.mode == "folders" and not self.model.path
            else ("item" if count == 1 else "items")
        )
        self.count_var.set(
            f"{count} {noun}"
            + (f" · Page {self.model.page + 1} of {pages}" if pages > 1 else "")
        )
        if pages > 1:
            self.previous.grid()
            self.next.grid()
        else:
            self.previous.grid_remove()
            self.next.grid_remove()
        self.previous.configure(state="normal" if self.model.page > 0 else "disabled")
        self.next.configure(
            state="normal" if self.model.page + 1 < pages else "disabled"
        )
        self._render_signature = None
        self._queue_render()

    def _queue_render(self, _event: Any = None) -> None:
        self._presentation_configured(_event)
        if self._render_after is None:
            self._render_after = self.after(16, self._render)

    def _render(self) -> None:
        from .app import video_list_row_values

        self._render_after = None
        width = max(180, self.canvas.winfo_width())
        components = self.model.page_components
        overview = (
            self.model.mode == "folders"
            and self.model.path is None
            and self.model.page == 0
        )
        folder_count = len(components)
        media_columns = (
            max(1, min(5, (width + 16) // 214))
            if overview
            else max(1, min(4, (width + 16) // 250))
        )
        highlights = (
            self.model.saved_media[: min(media_columns, PAGE_SIZE - folder_count)]
            if overview
            else ()
        )
        selected = self.model.selected_index()
        columns = (
            max(1, min(4, (width + 16) // 250, len(components) or 1))
            if overview
            else media_columns
        )
        gap = 16
        media_card_width = (width - gap * (media_columns - 1) - 4) // media_columns
        cover_width = max(1, media_card_width - 12)
        cover_height = cover_width * 9 // 16
        self._artwork_resize((cover_width, cover_height))
        media_height = cover_height + 88
        folder_height = 148
        height = (
            media_height
            if any(item.kind != "folder" for item in components)
            else folder_height
        )
        primary_height = height
        self._columns = columns
        components = (*components, *highlights)
        signature = (
            self._artwork_revision,
            width,
            components,
            selected,
            str(self._selected_folder),
            str(self._hovered_component),
            tuple(THEME.items()),
        )
        if signature == self._render_signature:
            self._presentation_settle()
            return
        self._render_signature = signature
        self.canvas.delete("all")
        self._artwork_begin()
        self._depth.draw((0, 0, width, 400), role="ambient")
        self._boxes.clear()
        self._open_boxes.clear()
        title_font = tkfont.Font(root=self, font=(FONT_UI[0], 13, "bold"))
        media_title_font = tkfont.Font(root=self, font=FONT_UI)
        detail_font = tkfont.Font(root=self, font=FONT_UI_SMALL)

        def fitted(
            value: str,
            lines: int = 1,
            title: bool = False,
            text_width: int | None = None,
        ) -> str:
            return ellipsize_wrapped_text(
                value[:2000],
                maximum_width=max(
                    1, text_width if text_width is not None else card_width - 28
                ),
                maximum_lines=lines,
                measure_width=(
                    title_font
                    if title and component.kind == "folder"
                    else media_title_font
                    if title
                    else detail_font
                ).measure,
            )

        overview_rows = (folder_count + columns - 1) // columns
        saved_heading = 40 + overview_rows * (folder_height + gap) + 22
        if overview and components:
            self.canvas.create_text(
                0,
                2,
                text="Folders",
                anchor="nw",
                font=(FONT_UI[0], 16, "bold"),
                fill=THEME["text"],
            )
            if highlights:
                self.canvas.create_text(
                    0,
                    saved_heading,
                    text="Saved videos",
                    anchor="nw",
                    font=(FONT_UI[0], 16, "bold"),
                    fill=THEME["text"],
                )
        for index, component in enumerate(components):
            is_highlight = overview and index >= folder_count
            item_columns = media_columns if is_highlight else columns
            card_width = (width - gap * (item_columns - 1) - 4) // item_columns
            height = media_height if is_highlight else primary_height
            position = index - folder_count if is_highlight else index
            x = position % item_columns * (card_width + gap)
            y = (
                saved_heading + 40 if is_highlight else 40 if overview else 0
            ) + position // item_columns * (height + gap)
            bounds = (x + 1, y + 1, x + card_width, y + height)
            self._boxes.append((bounds, component))
            active = (
                component == self._selected_folder
                or selected in component.indices
                and component.kind != "folder"
            )
            self._depth.draw(
                bounds,
                role="folder" if component.kind == "folder" else "media",
                selected=active or component == self._hovered_component,
            )
            title_x, title_width = x + 14, card_width - 28
            title = component.title
            if component.kind == "folder":
                if (
                    component.path is not None
                    and component.path.storage[0] == "network"
                ):
                    title = (
                        str(component.path)
                        .rstrip("\\/")
                        .replace("\\", "/")
                        .rsplit("/", 1)[-1]
                        or title
                    )
                if component.indices:
                    image = self._artwork_image(
                        dict(self.model.records[component.indices[0]]),
                        hero_size=(card_width - 2, height - 2),
                    )
                    if image is not None:
                        self.canvas.create_image(
                            x + 1,
                            y + 1,
                            image=image,
                            anchor="nw",
                            tags=("presentation-artwork",),
                        )
                # A folded-folder silhouette remains recognizable without artwork.
                self.canvas.create_polygon(
                    x + 18,
                    y + 24,
                    x + 32,
                    y + 24,
                    x + 38,
                    y + 31,
                    x + 55,
                    y + 31,
                    x + 55,
                    y + 54,
                    x + 18,
                    y + 54,
                    fill=THEME["accent_surface"],
                    outline=THEME["accent"],
                    width=2,
                )
                title_x, title_y, title_width = x + 70, y + 24, card_width - 86
                count = len(component.indices)
                detail = f"{count} saved file" + ("s" if count != 1 else "")
                if component.path and component.path.key in self._location_states:
                    detail = self._location_states[component.path.key]
                self.canvas.create_text(
                    x + 16,
                    y + 86,
                    text=fitted(
                        detail,
                        text_width=card_width - 120
                        if active or component == self._hovered_component
                        else None,
                    ),
                    fill=THEME["muted"],
                    font=FONT_UI_SMALL,
                    anchor="w",
                )
                storage = component.path.storage[0] if component.path else "local"
                self.canvas.create_text(
                    x + 16,
                    y + height - 24,
                    text={
                        "local": "Stored locally",
                        "network": "Network location",
                        "drive": "Drive folder",
                        "external": "External drive",
                    }[storage],
                    fill=THEME["muted"],
                    font=FONT_UI_SMALL,
                    anchor="w",
                )
                open_bounds = (
                    x + card_width - 111,
                    y + height - 42,
                    x + card_width - 12,
                    y + height - 10,
                )
                label = "Open folder"
            else:
                record = dict(self.model.records[component.indices[0]])
                artwork = self._artwork_image(record)
                rounded_surface(
                    self.canvas,
                    (x + 6, y + 6, x + card_width - 6, y + 6 + cover_height),
                    fill=THEME["surface_2"],
                    outline="",
                )
                if artwork is not None:
                    self.canvas.create_image(
                        x + 6,
                        y + 6,
                        image=artwork,
                        anchor="nw",
                        tags=("presentation-artwork",),
                    )
                else:
                    cx, cy = x + card_width / 2, y + 6 + cover_height / 2
                    self.canvas.create_polygon(
                        cx - 12,
                        cy - 17,
                        cx - 12,
                        cy + 17,
                        cx + 17,
                        cy,
                        fill=THEME["accent"],
                        outline="",
                    )
                ordinal, _title, duration, creator, _provider_id = (
                    video_list_row_values(
                        record, fallback_index=self.model.page * PAGE_SIZE + index + 1
                    )
                )
                media_badge(
                    self.canvas,
                    duration if is_highlight else f"#{ordinal} · {duration}",
                    right=x + card_width - 14,
                    bottom=y + cover_height - 2,
                    maximum_width=cover_width - 16,
                    font=FONT_UI_SMALL,
                    fill=THEME["panel"],
                    foreground=THEME["text"],
                )
                title_y = y + cover_height + 16
                media_detail = (
                    (
                        f"{len(component.indices)} saved versions"
                        if len(component.indices) > 1
                        else str(record.get("vodforge_output_type") or "Video")
                    )
                    if component.kind == "media"
                    else component.detail
                )
                detail_width = min(card_width - 40, detail_font.measure(media_detail))
                self.canvas.create_text(
                    x + 14,
                    y + height - 17,
                    text=fitted(
                        creator, text_width=max(1, card_width - detail_width - 44)
                    ),
                    fill=THEME["muted"],
                    font=FONT_UI_SMALL,
                    anchor="w",
                )
                self.canvas.create_text(
                    x + card_width - 14,
                    y + height - 17,
                    text=fitted(media_detail, text_width=detail_width),
                    fill=THEME["muted"],
                    font=FONT_UI_SMALL,
                    anchor="e",
                )
                open_bounds = (x + 20, y + 20, x + 86, y + 50)
                label = "Play" if component.kind == "media" else "Open"
            self.canvas.create_text(
                title_x,
                title_y,
                text=fitted(title, 2, True, title_width),
                fill=THEME["text"],
                font=(FONT_UI[0], 13, "bold")
                if component.kind == "folder"
                else FONT_UI,
                anchor="nw",
                width=max(80, title_width),
            )
            if active or component == self._hovered_component:
                rounded_surface(
                    self.canvas,
                    open_bounds,
                    radius=6,
                    fill=THEME["panel"],
                    outline=THEME["border"],
                )
                self.canvas.create_text(
                    (open_bounds[0] + open_bounds[2]) / 2,
                    (open_bounds[1] + open_bounds[3]) / 2,
                    text=label,
                    fill=THEME["text"],
                    font=FONT_UI_SMALL,
                )
            self._open_boxes.append((open_bounds, component))
        if not components:
            self.canvas.create_text(
                20,
                30,
                text="No items here.\nTry All media or adjust your search and category.",
                fill=THEME["muted"],
                font=FONT_UI,
                anchor="nw",
                width=width - 40,
            )
        self._artwork_request()
        bottom = max((bounds[3] for bounds, _component in self._boxes), default=180)
        self.canvas.configure(scrollregion=(0, 0, width, bottom + 20))
        self._presentation_settle()

    def _leave_hover(self, _event: Any) -> None:
        self.canvas.configure(cursor="")
        if self._hovered_component is not None:
            self._hovered_component = None
            self._queue_render()

    def _hover(self, event: Any) -> None:
        component = self._hit(event)
        if component != self._hovered_component:
            self._hovered_component = component
            self._queue_render()
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        active = any(
            left <= x <= right and top <= y <= bottom
            for (left, top, right, bottom), _item in self._open_boxes
        )
        self.canvas.configure(cursor="hand2" if active else "")

    def _hit(self, event: Any) -> ArchiveComponent | None:
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        return next(
            (
                component
                for (left, top, right, bottom), component in self._boxes
                if left <= x <= right and top <= y <= bottom
            ),
            None,
        )

    def _click(self, event: Any, *, activate: bool = True) -> None:
        self.canvas.focus_set()
        component = self._hit(event)
        if component is None:
            return
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        if activate and any(
            left <= x <= right and top <= y <= bottom
            for (left, top, right, bottom), item in self._open_boxes
            if item == component
        ):
            self._open_component(component)
            return
        if component.kind == "folder":
            self.model.selected_owner = ""
            self._last_row = ""
            self._selected_folder = component
            if component.path is not None:
                self._on_folder(component.path, component.indices)
        else:
            self._selected_folder = None
            self.model.select(component.indices[0])
            self._last_row = str(component.indices[0])
            self._on_select()
        self._refresh()

    def _activate(self, event: Any) -> str:
        component = self._hit(event)
        if component is not None:
            self._open_component(component)
        return "break"

    def _open_component(self, component: ArchiveComponent) -> None:
        if component.kind == "folder" and component.path is not None:
            self.navigate(component.path)
        else:
            self._selected_folder = None
            index = self.model.selected_index()
            index = index if index in component.indices else component.indices[0]
            self.model.select(index)
            self._last_row = str(index)
            self._on_select()
            self._on_activate(index)

    def _keyboard_activate(self, _event: Any) -> str:
        selected = self.model.selected_index()
        component = self._selected_folder or next(
            (
                item
                for _bounds, item in self._boxes
                if item.kind != "folder" and selected in item.indices
            ),
            None,
        )
        if component:
            self._open_component(component)
        return "break"

    def _presentation_dimensions(self) -> dict[str, str]:
        return {
            "presentation_mode": self.model.mode,
            "mode_origin": self._presentation_mode_origin,
            "presentation_population": "library_projection",
            "eligible_bucket": count_bucket(len(self.model.records)),
            "mode_eligible_bucket": count_bucket(self.model.mode_eligible_count),
            "query_state": "active" if self._presentation_query_active else "inactive",
            "filter_state": "active"
            if self._presentation_filter_active
            else "inactive",
            "matching_bucket": count_bucket(
                len({index for item in self.model.components for index in item.indices})
            ),
            "rendered_bucket": count_bucket(
                len({index for _bounds, item in self._boxes for index in item.indices})
            ),
        }

    def _step(
        self, direction: int, *, fresh_page: bool = False, vertical: bool = False
    ) -> str:
        items = (
            self.model.page_components
            if fresh_page
            else tuple(item for _bounds, item in self._boxes)
        )
        if not items:
            return "break"
        selected = self.model.selected_index()
        current = next(
            (
                index
                for index, item in enumerate(items)
                if (
                    item == self._selected_folder
                    if self._selected_folder is not None
                    else item.kind != "folder" and selected in item.indices
                )
            ),
            -1,
        )
        target = min(len(items) - 1, max(0, current + direction))
        if vertical and current >= 0:
            bounds = self._boxes[current][0]
            center_x, center_y = (
                (bounds[0] + bounds[2]) / 2,
                (bounds[1] + bounds[3]) / 2,
            )
            candidates = [
                (
                    abs((box[1] + box[3]) / 2 - center_y),
                    abs((box[0] + box[2]) / 2 - center_x),
                    index,
                )
                for index, (box, _item) in enumerate(self._boxes)
                if ((box[1] + box[3]) / 2 > center_y) == (direction > 0)
                and (box[1] + box[3]) / 2 != center_y
            ]
            target = min(candidates)[2] if candidates else current
        item = items[target]
        if item.kind == "folder":
            self.model.selected_owner = ""
            self._last_row = ""
            self._selected_folder = item
            if item.path:
                self._on_folder(item.path, item.indices)
        else:
            self._selected_folder = None
            self.model.select(item.indices[0])
            self._last_row = str(item.indices[0])
            self._on_select()
        self._refresh()
        return "break"

    def _menu(self, event: Any) -> str:
        # A secondary pointer action selects its subject without invoking the
        # primary affordance drawn underneath it.
        self._click(event, activate=False)
        component = self._hit(event)
        if component is not None and component.kind != "folder":
            self._last_row = str(self.model.selected_index())
            return str(self._on_menu(event))
        return "break"

    @staticmethod
    def _location_id(path: ArchivePath) -> str:
        import hashlib

        return "location-" + hashlib.sha256(repr(path.key).encode()).hexdigest()

    def set_storage_volumes(self, volumes: tuple[StorageVolume, ...]) -> None:
        if volumes != self._location_volumes:
            self._location_volumes = volumes
            self._render_locations()

    def _render_locations(self) -> None:
        selected = self.location_list.selection()
        paths = tuple(
            item.path for item in self.model.locations if item.path is not None
        )
        labels = location_labels(paths, self._location_volumes)
        self._location_labels = {self._location_id(item.path): item for item in labels}
        self.location_list.delete(*self.location_list.get_children())
        for identity, item in self._location_labels.items():
            self.location_list.insert(
                "", "end", iid=identity, text=f"{item.title}\n{item.subtitle}"
            )
        retained = tuple(item for item in selected if item in self._location_labels)
        if retained:
            self.location_list.selection_set(retained)

    def _location_selected(self, _event: Any) -> None:
        selected = self.location_list.selection()
        location = self._location_labels.get(selected[0]) if selected else None
        if location is not None:
            self.navigate(location.path)

    def _location_tooltip_text(self) -> str:
        y = self.location_list.winfo_pointery() - self.location_list.winfo_rooty()
        identity = self.location_list.identify_row(y)
        location = self._location_labels.get(identity)
        return location.tooltip if location is not None else ""

    def _path_menu(self) -> None:
        if self.model.path is None:
            return
        menu = ContextMenu(self, tearoff=False)
        menu.add_command(label="All locations", command=lambda: self.navigate(None))
        for path in self.model.path.ancestry:
            menu.add_command(label=str(path), command=partial(self.navigate, path))
        try:
            menu.tk_popup(
                self.path_button.winfo_rootx(),
                self.path_button.winfo_rooty() + self.path_button.winfo_height(),
            )
        finally:
            menu.grab_release()

    def _up(self) -> None:
        path = self.model.path
        self.navigate(path.parent if path is not None and path.parent != path else None)

    def _relink_folder(self) -> None:
        component = self._selected_folder
        path = component.path if component else self.model.path
        if path is None:
            return
        indices = (
            component.indices
            if component
            else tuple(
                index
                for index in self.model.visible
                if (directory := self.model._directories.get(index)) is not None
                and directory.relative_to(path) is not None
            )
        )
        self._on_relink(path, indices)

    def _page(self, amount: int) -> None:
        before = self.model.page
        self.model.page += amount
        self.model.reconcile()
        self.canvas.yview_moveto(0)
        if self.model.page != before:
            self._selected_folder = None
            self.model.selected_owner = ""
            self._step(1, fresh_page=True)
        self._refresh()

    def selection(self) -> tuple[str, ...]:
        if self._selected_folder is not None:
            return ()
        index = self.model.selected_index()
        return (str(index),) if index is not None else ()

    def selection_set(self, item: str) -> None:
        self._selected_folder = None
        self._last_row = item
        self.model.select(int(item))
        self._refresh()

    def selection_remove(self, *_items: Any) -> None:
        self._selected_folder = None
        self._last_row = ""
        self.model.selected_owner = ""
        self._refresh()

    def focus_item(self, item: str | None = None) -> str:
        if item is not None:
            self._selected_folder = None
            self._last_row = item
            self.model.select(int(item))
        return self.selection()[0] if self.selection() else ""

    def see(self, item: str) -> None:
        # Explicit navigation from Forge reveals the current owner.
        if not any(
            int(item) in component.indices for component in self.model.page_components
        ):
            self.model.reveal(int(item))
            self._refresh()

    def exists(self, item: str) -> bool:
        return item in self.get_children()

    def get_children(self, _item: str = "") -> tuple[str, ...]:
        return tuple(str(index) for index in self.model.visible)

    def identify_row(self, _y: Any) -> str:
        return self._last_row

    def identify_column(self, _x: Any) -> str:
        return "#2"

    def _destroyed(self, event: Any) -> None:
        if event.widget is self:
            self._depth.clear()
            self._artwork_close()
            if self._external_navigation:
                try:
                    self.navigation.destroy()
                except tk.TclError:
                    pass
        if event.widget is self and self._render_after is not None:
            self.after_cancel(self._render_after)
            self._render_after = None
