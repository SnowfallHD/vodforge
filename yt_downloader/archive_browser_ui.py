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
from .ui_layout import ellipsize_wrapped_text
from .ui_theme import FONT_UI, FONT_UI_SMALL, THEME
from .ui_widgets import SleekScrollbar, bind_smooth_vertical_wheel


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
        thumbnail_path: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__(master, style="FocusShell.TFrame")
        self.model = ArchiveBrowserModel()
        self._on_usage = on_usage or (lambda *args, **kwargs: None)
        self._on_select, self._on_activate = on_select, on_activate
        self._on_menu, self._on_folder, self._on_relink = on_menu, on_folder, on_relink
        self._render_after: str | None = None
        self._boxes: list[tuple[tuple[int, int, int, int], ArchiveComponent]] = []
        self._last_row = ""
        self._location_states: dict[tuple[str, ...], str] = {}
        self._selected_folder: ArchiveComponent | None = None
        self._render_signature: Any = None
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        nav = ttk.Frame(self, style="FocusShell.TFrame", width=152)
        nav.grid(row=0, column=0, rowspan=3, sticky="nsew", padx=(0, 16))
        nav.grid_propagate(False)
        nav.columnconfigure(0, weight=1)
        nav.rowconfigure(5, weight=1)
        ttk.Label(nav, text="ARCHIVE", style="FocusEyebrow.TLabel").grid(
            row=0, column=0, sticky="w", pady=(8, 8)
        )
        for row, (title, mode) in enumerate(
            (
                ("Folders", "folders"),
                ("All media", "all"),
                ("Runs & previews", "activity"),
            ),
            start=1,
        ):
            ttk.Button(
                nav,
                text=title,
                command=partial(self.navigate, None, mode=mode),
                style="FocusQuiet.TButton",
            ).grid(row=row, column=0, sticky="ew", pady=2)
        ttk.Label(nav, text="LOCATIONS", style="FocusEyebrow.TLabel").grid(
            row=4, column=0, sticky="w", pady=(24, 8)
        )
        location_shell = ttk.Frame(nav, style="FocusShell.TFrame")
        location_shell.grid(row=5, column=0, sticky="nsew")
        location_shell.columnconfigure(0, weight=1)
        location_shell.rowconfigure(0, weight=1)
        self.location_list = tk.Listbox(
            location_shell,
            width=1,
            bg=THEME["bg"],
            fg=THEME["text"],
            selectbackground=THEME["accent_surface"],
            selectforeground=THEME["text"],
            bd=0,
            highlightthickness=0,
            activestyle="none",
            exportselection=False,
            font=FONT_UI_SMALL,
        )
        self.location_list.grid(row=0, column=0, sticky="nsew")
        location_scroll = SleekScrollbar(
            location_shell, command=self.location_list.yview
        )
        location_scroll.grid(row=0, column=1, sticky="ns")
        self.location_list.configure(yscrollcommand=location_scroll.set)
        self.location_list.bind("<<ListboxSelect>>", self._location_selected)
        toolbar = ttk.Frame(self, style="FocusShell.TFrame")
        toolbar.grid(row=0, column=1, sticky="ew", pady=(0, 10))
        toolbar.columnconfigure(1, weight=1)
        ttk.Button(
            toolbar, text="↑", width=3, command=self._up, style="FocusQuiet.TButton"
        ).grid(row=0, column=0, padx=(0, 5))
        self.path_button = ttk.Button(
            toolbar,
            text="All locations",
            command=self._path_menu,
            style="FocusQuiet.TButton",
        )
        self.path_button.grid(row=0, column=1, sticky="w")
        self.relink_button = ttk.Button(
            toolbar,
            text="Update folder location",
            command=self._relink_folder,
            style="FocusQuiet.TButton",
            state="disabled",
        )
        self.relink_button.grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 0))
        content = ttk.Frame(self, style="FocusShell.TFrame")
        content.grid(row=1, column=1, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(
            content, bg=THEME["bg"], highlightthickness=0, bd=0, takefocus=True
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scroll = SleekScrollbar(content, command=self.canvas.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.bind("<Configure>", self._queue_render)
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Double-1>", self._activate)
        self.canvas.bind("<Button-2>", self._menu)
        self.canvas.bind("<Button-3>", self._menu)
        self.canvas.bind("<Return>", self._keyboard_activate)
        self.canvas.bind("<Down>", lambda event: self._step(1))
        self.canvas.bind("<Up>", lambda event: self._step(-1))
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
        self.previous = ttk.Button(
            footer,
            text="Previous",
            command=lambda: self._page(-1),
            style="FocusQuiet.TButton",
        )
        self.previous.grid(row=0, column=1)
        self.next = ttk.Button(
            footer,
            text="Next",
            command=lambda: self._page(1),
            style="FocusQuiet.TButton",
        )
        self.next.grid(row=0, column=2, padx=(5, 0))
        self._artwork_setup(thumbnail_path or (lambda record: None), (106, 60))
        self.bind("<Destroy>", self._destroyed, add="+")

    def set_records(
        self,
        records: Sequence[dict[str, Any]],
        visible: Sequence[int],
        *,
        select_index: int | None = None,
    ) -> None:
        self.model.replace(records, visible)
        if select_index is not None:
            self.model.reveal(select_index)
        self.location_list.delete(0, "end")
        for location in self.model.locations:
            self.location_list.insert("end", location.title)
        self._refresh()

    def navigate(self, path: ArchivePath | None, *, mode: Any = "folders") -> None:
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
        self.path_button.configure(text=label[:48] + ("…" if len(label) > 48 else ""))
        self.relink_button.configure(
            state="normal" if self.model.path or self._selected_folder else "disabled"
        )
        count = len(self.model.components)
        pages = max(1, (count + PAGE_SIZE - 1) // PAGE_SIZE)
        self.count_var.set(f"{count} items · Page {self.model.page + 1} of {pages}")
        self.previous.configure(state="normal" if self.model.page > 0 else "disabled")
        self.next.configure(
            state="normal" if self.model.page + 1 < pages else "disabled"
        )
        self._render_signature = None
        self._queue_render()

    def _queue_render(self, _event: Any = None) -> None:
        if self._render_after is None:
            self._render_after = self.after(16, self._render)

    def _render(self) -> None:
        from .app import video_list_row_values

        self._render_after = None
        width = max(180, self.canvas.winfo_width())
        components = self.model.page_components
        selected = self.model.selected_index()
        signature = (
            self._artwork_revision,
            width,
            components,
            selected,
            str(self._selected_folder),
            tuple(THEME.items()),
        )
        if signature == self._render_signature:
            return
        self._render_signature = signature
        self._artwork_begin()
        self.canvas.delete("all")
        self._boxes.clear()
        columns = max(1, min(4, width // 240))
        gap, height = 12, 176
        card_width = (width - gap * (columns - 1) - 4) // columns
        title_font = tkfont.Font(root=self, font=FONT_UI)
        detail_font = tkfont.Font(root=self, font=FONT_UI_SMALL)
        for index, component in enumerate(components):
            x, y = (
                (index % columns) * (card_width + gap),
                (index // columns) * (height + gap),
            )
            bounds = (x + 1, y + 1, x + card_width, y + height)
            self._boxes.append((bounds, component))
            active = (
                component == self._selected_folder
                or selected in component.indices
                and component.kind != "folder"
            )
            self.canvas.create_rectangle(
                *bounds,
                fill=THEME["accent_surface"] if active else THEME["surface"],
                outline=THEME["accent"] if active else THEME["border"],
                width=2 if active else 1,
            )
            artwork = (
                self._artwork_image(dict(self.model.records[component.indices[0]]))
                if component.kind == "media"
                else None
            )
            if artwork is not None:
                self.canvas.create_image(x + 16, y + 10, image=artwork, anchor="nw")
                icon_label = ""
            elif component.kind == "folder":
                self.canvas.create_polygon(
                    x + 16,
                    y + 22,
                    x + 43,
                    y + 22,
                    x + 50,
                    y + 30,
                    x + 79,
                    y + 30,
                    x + 79,
                    y + 63,
                    x + 16,
                    y + 63,
                    fill=THEME["warning"],
                    outline="",
                )
                storage = component.path.storage[0] if component.path else "local"
                icon_label = {
                    "local": "Local storage",
                    "network": "Network share",
                    "drive": "Drive",
                    "external": "Mounted storage",
                }[storage]
            else:
                self.canvas.create_rectangle(
                    x + 17, y + 22, x + 75, y + 61, outline=THEME["accent"], width=2
                )
                self.canvas.create_polygon(
                    x + 40,
                    y + 31,
                    x + 40,
                    y + 52,
                    x + 55,
                    y + 42,
                    fill=THEME["accent"],
                    outline="",
                )
                icon_label = "EXPORTS" if component.kind == "media" else "RUN / PREVIEW"
            self.canvas.create_text(
                x + 91,
                y + 41,
                text=icon_label,
                fill=THEME["muted"],
                font=FONT_UI_SMALL,
                anchor="w",
            )
            if component.kind != "folder":
                ordinal, _title, duration, creator, _provider_id = (
                    video_list_row_values(
                        dict(self.model.records[component.indices[0]]),
                        fallback_index=self.model.page * PAGE_SIZE + index + 1,
                    )
                )
                self.canvas.create_text(
                    x + card_width - 16,
                    y + 17,
                    text=f"#{ordinal}\n{duration}",
                    anchor="ne",
                    font=FONT_UI_SMALL,
                    fill=THEME["muted"],
                )
                self.canvas.create_text(
                    x + 16,
                    y + 153,
                    text=ellipsize_wrapped_text(
                        creator,
                        maximum_width=max(100, card_width - 32),
                        maximum_lines=1,
                        measure_width=detail_font.measure,
                    ),
                    anchor="nw",
                    font=FONT_UI_SMALL,
                    fill=THEME["muted"],
                )
            title = ellipsize_wrapped_text(
                component.title[:2000],
                maximum_width=max(100, card_width - 32),
                maximum_lines=2,
                measure_width=title_font.measure,
            )
            self.canvas.create_text(
                x + 16,
                y + 77,
                text=title,
                fill=THEME["text"],
                font=FONT_UI,
                anchor="nw",
                width=max(100, card_width - 32),
            )
            detail = ellipsize_wrapped_text(
                (
                    f"{len(component.indices)} saved exports"
                    if component.kind == "folder"
                    else component.detail
                )[:1000],
                maximum_width=max(100, card_width - 32),
                maximum_lines=1,
                measure_width=detail_font.measure,
            )
            self.canvas.create_text(
                x + 16,
                y + 132,
                text=detail,
                fill=THEME["muted"],
                font=FONT_UI_SMALL,
                anchor="nw",
                width=max(100, card_width - 32),
            )
            if component.kind == "folder" and component.path is not None:
                self.canvas.create_text(
                    x + 16,
                    y + 153,
                    text=self._location_states.get(
                        component.path.key, "Availability not checked"
                    ),
                    fill=THEME["muted"],
                    font=FONT_UI_SMALL,
                    anchor="nw",
                    width=max(100, card_width - 32),
                )
        if not components:
            self.canvas.create_text(
                20,
                30,
                text="No items here.\nTry All media or adjust the search and collection filters.",
                fill=THEME["muted"],
                font=FONT_UI,
                anchor="nw",
                width=width - 40,
            )
        self._artwork_request()
        rows = max(1, (len(components) + columns - 1) // columns)
        self.canvas.configure(scrollregion=(0, 0, width, rows * (height + gap)))

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

    def _click(self, event: Any) -> None:
        self.canvas.focus_set()
        component = self._hit(event)
        if component is None:
            return
        if component.kind == "folder":
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
            index = self.model.selected_index()
            index = index if index in component.indices else component.indices[0]
            self.model.select(index)
            self._on_select()
            self._on_activate(index)

    def _keyboard_activate(self, _event: Any) -> str:
        selected = self.model.selected_index()
        component = self._selected_folder or next(
            (item for item in self.model.page_components if selected in item.indices),
            None,
        )
        if component:
            self._open_component(component)
        return "break"

    def _step(self, direction: int) -> str:
        items = self.model.page_components
        if not items:
            return "break"
        selected = self.model.selected_index()
        current = next(
            (
                index
                for index, item in enumerate(items)
                if item == self._selected_folder or selected in item.indices
            ),
            -1,
        )
        item = items[min(len(items) - 1, max(0, current + direction))]
        if item.kind == "folder":
            self._selected_folder = item
            if item.path:
                self._on_folder(item.path, item.indices)
        else:
            self._selected_folder = None
            self.model.select(item.indices[0])
            self._on_select()
        self._refresh()
        return "break"

    def _menu(self, event: Any) -> str:
        self._click(event)
        component = self._hit(event)
        if component is not None and component.kind != "folder":
            self._last_row = str(self.model.selected_index())
            return str(self._on_menu(event))
        return "break"

    def _location_selected(self, _event: Any) -> None:
        selected = self.location_list.curselection()
        if selected and selected[0] < len(self.model.locations):
            self.navigate(self.model.locations[selected[0]].path)

    def _path_menu(self) -> None:
        if self.model.path is None:
            return
        menu = tk.Menu(self, tearoff=False)
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
            self._step(1)
        self._refresh()

    def _wheel(self, event: Any) -> str:
        delta = int(event.delta)
        self.canvas.yview_scroll(
            -max(1, abs(delta) // 120) if delta > 0 else max(1, abs(delta) // 120),
            "units",
        )
        return "break"

    def selection(self) -> tuple[str, ...]:
        index = self.model.selected_index()
        return (str(index),) if index is not None else ()

    def selection_set(self, item: str) -> None:
        self.model.select(int(item))
        self._refresh()

    def selection_remove(self, *_items: Any) -> None:
        self.model.selected_owner = ""
        self._refresh()

    def focus_item(self, item: str | None = None) -> str:
        if item is not None:
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
            self._artwork_close()
        if event.widget is self and self._render_after is not None:
            self.after_cancel(self._render_after)
            self._render_after = None
