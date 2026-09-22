"""Library scenes render canonical records and route actions to their owners."""

from __future__ import annotations

import tkinter as tk
from collections import OrderedDict
from collections.abc import Callable, Sequence
from functools import partial
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any

from .archive_artwork import ArchiveArtworkMixin
from .archive_browser import archive_row_owner
from .library_scene_layout import LibrarySceneLayout
from .library_search_ui import LibrarySearchField
from .scene_components import scene_font
from .ui_canvas_actions import CanvasActions
from .ui_chrome import CanvasSurfaceCache, draw_scene_focus_material
from .ui_context_menu import ContextMenu
from .ui_editable_text import EditableTextSection
from .ui_layout import ellipsize_wrapped_text, window_logical_metrics
from .ui_materials import draw_matte_backdrop
from .ui_scrolling import bind_smooth_scroll
from .ui_theme import THEME
from .ui_transition import cancel_view_transition
from .ui_widgets import ChoiceDropdown, KeyboardScope, SleekScrollbar
from .volume_storage import StorageCapacityOwner, StorageSnapshot, StorageVolume
from .watch_library import watch_channels, watch_media_kind, watch_rails


def _bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1000 or unit == "TB":
            return f"{size:.0f} {unit}" if size >= 100 else f"{size:.1f} {unit}"
        size /= 1000
    return str(value)


def _projection(owner: Any, key: tuple[Any, ...], build: Callable[[], Any]) -> Any:
    """Bound derived query variants to the current authoritative snapshot."""
    if owner.__dict__.get("_projection_snapshot") is not owner._records:
        owner._projection_snapshot = owner._records
        owner._projection_cache = OrderedDict()
    cache = owner._projection_cache
    if key not in cache:
        cache[key] = build()
        while len(cache) > 12:
            cache.popitem(last=False)
    cache.move_to_end(key)
    return cache[key]


class LibraryScene(LibrarySceneLayout, ArchiveArtworkMixin, ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        thumbnail_path: Callable[..., Any],
        action: Callable[[str, int | None], None],
        on_usage: Callable[..., None],
        telemetry: Any = None,
        artwork_source: Callable[..., Any] | None = None,
        add_tag: Callable[[str, str, bool], bool] | None = None,
        save_description: Callable[[str, str], bool] | None = None,
        storage_changed: Callable[[tuple[StorageVolume, ...]], None] | None = None,
    ) -> None:
        super().__init__(master, style="FocusShell.TFrame")
        self._records: tuple[dict[str, Any], ...] = ()
        self._action = action
        self._on_usage = on_usage
        self._add_tag = add_tag
        self._selected: set[str] = set()
        self._selection_mode = False
        self._filter = ""
        self._rendered_count = 0
        self._matching_count = 0
        self._route = "home"
        self._detail_owner = ""
        self._detail_origin: dict[str, Any] | None = None
        self._pending_scroll: float | None = None
        self._page = 0
        self._query = ""
        self._sort = "recent"
        self._category = ""
        self._group_key = ""
        self._group_kind = ""
        self._render_after: str | None = None
        self._closed = False
        self._text_fonts: dict[tuple[Any, ...], tkfont.Font] = {}
        self._targets = []
        self._context_targets = []
        self._button_images = []
        self._button_labels = []
        self._keyboard_target = 0
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        px = window_logical_metrics(self).px
        self.sidebar = tk.Canvas(
            self, width=px(226), bg=THEME["bg"], highlightthickness=0
        )
        self.sidebar.grid(row=0, column=0, sticky="ns", padx=(0, px(20)))
        bind_smooth_scroll(self.sidebar, mode="pixels")
        self._sidebar_size: tuple[int, int] | None = None
        self.sidebar.bind("<Configure>", self._sidebar_configured)
        self._sidebar_pointer_actions = CanvasActions(
            self.sidebar, lambda: self._sidebar_targets
        )
        self._sidebar_targets = []
        self._sidebar_images = []
        self._sidebar_depth = CanvasSurfaceCache(self.sidebar)
        self.canvas = tk.Canvas(
            self, bg=THEME["bg"], highlightthickness=0, takefocus=True
        )
        self.canvas.grid(row=0, column=1, sticky="nsew", pady=(24, 18))
        scrollbar = SleekScrollbar(self, command=self._catalog_scroll_command)
        scrollbar.grid(row=0, column=2, sticky="ns")
        self._catalog_scrollbar = scrollbar
        self.canvas.configure(yscrollcommand=self._catalog_scroll_changed)
        self._depth = CanvasSurfaceCache(self.canvas)
        self._search_var = tk.StringVar(self, "")
        self._search_field = LibrarySearchField(
            self.canvas,
            variable=self._search_var,
            width=18,
            placeholder="Search media…",
        )
        self._search_window: int | None = None
        search_canvas = self._search_field._chrome.canvas
        draw_matte_backdrop(search_canvas)
        # Canvas windows and scene artwork share canvas coordinates, including
        # scroll displacement. Keep the existing chrome's transparent corners
        # aligned without a second artwork source or a root-coordinate guess.
        search_canvas.bind("<Configure>", self._project_search_backdrop, add="+")
        self._search_field.bind("<Configure>", self._project_search_backdrop, add="+")
        self._search_field.bind("<Map>", self._project_search_backdrop, add="+")
        self._search_var.trace_add(
            "write", lambda *_: self.set_query(self._search_var.get())
        )
        self._description_section = EditableTextSection(
            self.canvas,
            title="Description",
            save=save_description or (lambda _owner, _value: False),
            changed=self._queue_render,
        )
        self._detail_versions: tuple[tuple[str, str], ...] = ()
        self._version_var = tk.StringVar(self, "")
        self._version_choice = ChoiceDropdown(
            self.canvas,
            textvariable=self._version_var,
            values=(),
            state="readonly",
            width=1,
        )
        self._version_choice.bind("<<ComboboxSelected>>", self._choose_detail_version)
        self._tag_var = tk.StringVar(self, "")
        self._tag_entry = tk.Entry(
            self.canvas,
            textvariable=self._tag_var,
            bg=THEME["panel"],
            fg=THEME["text"],
            insertbackground=THEME["text"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=scene_font(14, font_scale=window_logical_metrics(self).scale),
        )
        self._tag_entry.bind("<Return>", self._tag_return)
        self._tag_entry.insert(0, "")
        self._tag_hint = tk.Label(
            self.canvas,
            text="Add a tag…",
            font=scene_font(14, font_scale=window_logical_metrics(self).scale),
            bg=THEME["panel"],
            fg=THEME["muted"],
            bd=0,
        )
        self._tag_hint.bind("<Button-1>", lambda _: self._tag_entry.focus_set())
        self._tag_entry.bind("<FocusIn>", lambda _: self._tag_hint.place_forget())
        self._tag_entry.bind("<FocusOut>", lambda _: self._refresh_tag_hint())
        self._tag_var.trace_add("write", lambda *_: self._refresh_tag_hint())

        self.canvas.bind("<Configure>", self._queue_render)
        self._pointer_actions = CanvasActions(self.canvas, lambda: self._targets)
        self.canvas.bind("<Button-3>", self._context_menu)
        self.canvas.bind("<Control-Button-1>", self._context_menu)
        self.canvas.bind("<Motion>", self._hover, add="+")
        self.canvas.bind("<FocusIn>", partial(self._focus, 0))
        self.canvas.bind(
            "<FocusOut>", lambda _event: self.canvas.delete("keyboard-focus")
        )
        self.canvas.bind("<Return>", self._activate)
        self.canvas.bind("<space>", self._activate)
        self.canvas.bind("<Next>", lambda _event: self._change_page(1))
        self.canvas.bind("<Prior>", lambda _event: self._change_page(-1))
        for key, delta in (("<Right>", 1), ("<Down>", 1), ("<Left>", -1), ("<Up>", -1)):
            self.canvas.bind(key, partial(self._focus, delta))
        self._keyboard_scope = KeyboardScope(
            self, {"<Escape>": self.return_from_detail}
        )
        bind_smooth_scroll(
            self.canvas, mode="pixels", on_scroll=self._catalog_scroll_used
        )
        self._storage_changed = storage_changed
        self._storage = StorageCapacityOwner()
        self._storage_snapshot: StorageSnapshot | None = None
        self._storage_after = self.after(100, self._poll_storage)
        self._artwork_setup(
            thumbnail_path, (212, 120), "archive", source_path=artwork_source
        )
        self._presentation_setup(telemetry, "library")
        self.bind("<Destroy>", self._destroyed, add="+")

    def set_records(
        self, records: Sequence[dict[str, Any]], *_args: Any, **_kwargs: Any
    ) -> None:
        self._targets = []
        self._context_targets = []
        if self.__dict__.get("_catalog_window"):
            self._remember_catalog_anchor()
            self._catalog_pending_anchor = self.__dict__.get("_catalog_anchor")
        self._catalog_window = None
        self._records = tuple(records)
        self.__dict__.pop("_projection_snapshot", None)
        self.__dict__.pop("_projection_cache", None)
        self._selected.intersection_update(
            archive_row_owner(row) for row in self._records
        )
        self._presentation_change("data")
        self._queue_render()
        self._draw_sidebar()

    def _project_search_backdrop(self, _event: Any = None) -> None:
        if self._closed or self._search_window is None:
            return
        try:
            if (
                not self._search_field.winfo_ismapped()
                or self.canvas.type(self._search_window) != "window"
            ):
                return
            scene = getattr(self.canvas, "_matte_backdrop", None)
            if scene is None or not self.canvas.type(scene.item):
                return
            texture_x, texture_y = self.canvas.coords(scene.item)
            search_window = self._search_window
            if search_window is None:
                return
            window_x, window_y = self.canvas.coords(search_window)
            canvas = self._search_field._chrome.canvas
            backdrop = draw_matte_backdrop(canvas)
            if backdrop.item is None:
                return
            canvas.coords(backdrop.item, texture_x - window_x, texture_y - window_y)
        except tk.TclError:
            # A geometry notification can coincide with this scene retiring.
            return

    def _reset_catalog_viewport(self) -> None:
        self._catalog_window = None
        for key in (
            "_catalog_pending_anchor",
            "_catalog_restore_top",
            "_catalog_scroll_seen",
        ):
            self.__dict__.pop(key, None)
        self.canvas.yview_moveto(0)

    def set_query(self, value: str) -> None:
        cancel_view_transition(self)
        self._targets = []
        self._context_targets = []
        self._pending_scroll = None
        self._query = value
        self._page = 0
        if value and self._route in {"home", "detail"}:
            self._route = "all"
        if self._search_var.get() != value:
            self._search_var.set(value)
        self._on_usage("library", "searched")
        self._reset_catalog_viewport()
        self._presentation_change("filter")
        self._queue_render()

    def show_details(
        self,
        index: int | None,
        *,
        on_return: Callable[[], None] | None = None,
        versions: tuple[tuple[str, str], ...] = (),
    ) -> None:
        cancel_view_transition(self)
        if index is None or not 0 <= index < len(self._records):
            return
        self._detail_return_callback = on_return
        self._detail_versions = versions
        if self._route != "detail":
            self._detail_origin = {
                name: getattr(self, name)
                for name in (
                    "_route",
                    "_page",
                    "_query",
                    "_sort",
                    "_filter",
                    "_category",
                    "_group_key",
                    "_group_kind",
                )
            }
            self._detail_origin["scroll"] = self.canvas.yview()[0]
        self._targets = []
        self._context_targets = []
        self._presentation_change("navigation")
        self._detail_owner = archive_row_owner(self._records[index])
        self._tag_var.set("")
        self._on_usage("archive", "inspector_opened")
        self._route = "detail"
        self._page = 0
        self.canvas.yview_moveto(0)
        self._queue_render()

    def _choose_detail_version(self, _event: Any = None) -> None:
        if self._route != "detail":
            return
        choices = tuple(
            (owner, label)
            for owner, label in self._detail_versions
            if any(archive_row_owner(row) == owner for row in self._records)
        )
        selected = self._version_var.get()
        owner = next((owner for owner, label in choices if label == selected), None)
        found = next(
            (
                i
                for i, row in enumerate(self._records)
                if archive_row_owner(row) == owner
            ),
            None,
        )
        if found is None:
            self._queue_render()
            return
        self._detail_owner = str(owner)
        self._targets.clear()
        self._context_targets.clear()
        self._action("select_version", found)
        self._presentation_change("navigation")
        self._queue_render()

    def return_from_detail(self) -> None:
        """Restore the precise catalog which opened this item, once per key."""
        if self._route != "detail":
            return
        self._targets = []
        self._context_targets = []
        self._presentation_change("navigation")
        callback = self.__dict__.pop("_detail_return_callback", None)
        origin = self._detail_origin
        self._detail_origin = None
        if origin is None:
            self.navigate("home")
            if callback is not None:
                callback()
            return
        for name, value in origin.items():
            if name != "scroll":
                setattr(self, name, value)
        self._pending_scroll = origin["scroll"]
        self._queue_render()
        self._draw_sidebar()
        if callback is not None:
            callback()

    def navigate(self, route: str) -> None:
        cancel_view_transition(self)
        self._catalog_window = None
        self.__dict__.pop("_catalog_pending_anchor", None)
        self.__dict__.pop("_catalog_scroll_seen", None)
        self._targets = []
        self._context_targets = []
        self._pending_scroll = None
        self._clear_selection()
        self._route, self._page = route, 0
        self._category = ""
        self._group_key = ""
        self._group_kind = ""
        self._on_usage("archive", "scene_navigated", scene_route=route)
        self._presentation_change("navigation")
        self.canvas.yview_moveto(0)
        self._queue_render()
        self._draw_sidebar()

    def _fit(self, value: str, width: int, lines: int, font: Any) -> str:
        key = tuple(font)
        if key not in self._text_fonts:
            self._text_fonts[key] = tkfont.Font(
                root=self,
                family=key[0],
                size=key[1],
                weight=key[2] if len(key) > 2 else "normal",
            )
        return ellipsize_wrapped_text(
            str(value)[:2000],
            maximum_width=max(1, width),
            maximum_lines=lines,
            measure_width=self._text_fonts[key].measure,
        )

    def _sidebar_configured(self, event: Any) -> None:
        size = (event.width, event.height)
        previous = self._sidebar_size
        if size == previous:
            return
        self._sidebar_size = size
        if (
            previous is not None
            and previous[0] == event.width
            and self.sidebar.find_withtag("sidebar-storage")
        ):
            # Height changes only relocate the storage section. Retain the
            # navigation pixels and targets rather than repainting every row.
            px = window_logical_metrics(self).px
            y = max(px(343), event.height - px(141))
            delta = y - self._sidebar_storage_y
            self.sidebar.move("sidebar-storage", 0, delta)
            self._sidebar_storage_y = y
            self.sidebar.coords(
                "sidebar-divider",
                event.width - px(1),
                0,
                event.width - px(1),
                max(event.height, y + px(141)),
            )
            self.sidebar.configure(
                scrollregion=(0, 0, event.width, max(event.height, y + px(141)))
            )
            bounds, action = self._sidebar_targets[-1]
            left, top, right, bottom = bounds
            self._sidebar_targets[-1] = (
                (left, top + delta, right, bottom + delta),
                action,
            )
        else:
            self._draw_sidebar()

    def apply_theme(self) -> None:
        self.sidebar.configure(bg=THEME["panel"])
        self.canvas.configure(bg=THEME["bg"])
        self._draw_sidebar()
        self._queue_render()

    def _queue_render(self, event: Any = None) -> None:
        self._queue_scene_render(event)

    def _poll_storage(self) -> None:
        if self._closed:
            return
        snapshot = self._storage.poll()
        if snapshot != self._storage_snapshot:
            self._storage_snapshot = snapshot
            if self._storage_changed is not None:
                self._storage_changed(snapshot.choices)
            self._draw_sidebar()
        self._storage_after = self.after(250, self._poll_storage)

    def _choose_volume(self) -> None:
        menu = ContextMenu(self, tearoff=False)
        snapshot = self._storage.snapshot
        for volume in snapshot.choices:
            menu.add_command(
                label=volume.label, command=partial(self._select_volume, volume.path)
            )
        menu.add_separator()
        menu.add_command(label="Refresh storage", command=self._storage.refresh)
        menu.add_command(
            label="Folders and storage…", command=partial(self._action, "folders", None)
        )
        menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def _select_volume(self, path: str) -> None:
        self._storage.select(path)
        self._on_usage("archive", "volume_selected")

    def _saved(self) -> list[tuple[int, dict[str, Any]]]:
        return _projection(self, ("saved",), lambda: LibraryScene._build_saved(self))

    def _build_saved(self) -> list[tuple[int, dict[str, Any]]]:
        return [
            (i, row)
            for i, row in enumerate(self._records)
            if row.get("vodforge_output_dir")
        ]

    def _counts(self) -> dict[str, int]:
        return _projection(self, ("counts",), lambda: LibraryScene._build_counts(self))

    def _build_counts(self) -> dict[str, int]:
        saved = self._saved()
        audio = sum(
            str(row.get("vodforge_output_type", "")).lower()
            in {"mp3", "original audio", "m4a"}
            for _, row in saved
        )
        return {
            "all": len(saved),
            "channels": len(watch_channels(self._records)),
            "playlists": len(watch_rails(self._records)),
            "videos": len(saved) - audio,
            "audio": audio,
        }

    def _open_item_menu(self, owner: str) -> None:
        index = next(
            (
                i
                for i, row in enumerate(self._records)
                if archive_row_owner(row) == owner
            ),
            None,
        )
        if index is not None:
            self._action("more", index)

    def _context_menu(self, event: Any) -> str:
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        for box, owner in reversed(self._context_targets):
            if box[0] <= x <= box[2] and box[1] <= y <= box[3]:
                self._open_item_menu(owner)
                break
        return "break"

    def _hover(self, event: Any) -> None:
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        active = any(
            box[0] <= x <= box[2] and box[1] <= y <= box[3] for box, _ in self._targets
        )
        self.canvas.configure(cursor="hand2" if active else "")

    def _focus(self, delta: int, _event: Any) -> str:
        if self._targets:
            self._keyboard_target = max(
                0, min(len(self._targets) - 1, self._keyboard_target + delta)
            )
            self.canvas.delete("keyboard-focus")
            draw_scene_focus_material(
                self.canvas, self._targets[self._keyboard_target][0]
            )
        return "break"

    def _activate(self, _event: Any) -> str:
        if self._targets:
            self._targets[min(self._keyboard_target, len(self._targets) - 1)][1]()
        return "break"

    @staticmethod
    def _is_audio(row: dict[str, Any]) -> bool:
        return watch_media_kind(row) == "audio"

    @property
    def selected_owners(self) -> tuple[str, ...]:
        return tuple(
            archive_row_owner(row)
            for row in self._records
            if archive_row_owner(row) in self._selected
        )

    @property
    def selected_indices(self) -> tuple[int, ...]:
        return tuple(
            index
            for index, row in enumerate(self._records)
            if archive_row_owner(row) in self._selected
        )

    def _start_selection(self) -> None:
        if not self._selection_mode:
            self._selection_mode = True
            self._on_usage("library", "selection_started")
            self._queue_render()

    def _toggle_selection(self, owners: tuple[str, ...]) -> None:
        current = {archive_row_owner(row) for row in self._records}
        owners = tuple(owner for owner in owners if owner in current)
        if not owners:
            return
        self._start_selection()
        if all(owner in self._selected for owner in owners):
            self._selected.difference_update(owners)
        else:
            self._selected.update(owners)
        self._on_usage("library", "selected")
        self._queue_render()

    def _clear_selection(self) -> None:
        active = self._selection_mode
        self._selected.clear()
        self._selection_mode = False
        if active:
            self._on_usage("library", "selection_finished")
        self._queue_render()

    def _groups(self, kind: str) -> tuple[Any, ...]:
        return _projection(
            self,
            ("groups", kind, self._query),
            lambda: (
                watch_channels(self._records, query=self._query)
                if kind == "channels"
                else watch_rails(
                    self._records,
                    collection_mode=kind == "collections",
                    query=self._query,
                )
            ),
        )

    def _matching_media(self) -> list[tuple[int, dict[str, Any]]]:
        return _projection(
            self,
            (
                "media",
                self._query,
                self._group_kind,
                self._group_key,
                self._route,
                self._filter,
                self._sort,
            ),
            lambda: LibraryScene._build_matching_media(self),
        )

    def _build_matching_media(self) -> list[tuple[int, dict[str, Any]]]:
        saved = list(self._saved())
        if self._query:
            terms = self._query.casefold().split()
            saved = [
                (i, row)
                for i, row in saved
                if all(
                    term
                    in " ".join(
                        str(row.get(k) or "")
                        for k in (
                            "title",
                            "channel",
                            "uploader",
                            "description",
                            "vodforge_user_note",
                            "vodforge_user_tags",
                            "vodforge_user_category",
                        )
                    ).casefold()
                    for term in terms
                )
            ]
        if self._group_key:
            group = next(
                (
                    item
                    for item in self._groups(self._group_kind)
                    if item.key == self._group_key
                ),
                None,
            )
            members = (
                {index for video in group.videos for index in video.indices}
                if group
                else set()
            )
            saved = [(index, row) for index, row in saved if index in members]
        if self._route in {"videos", "audio"}:
            saved = [
                (i, row)
                for i, row in saved
                if self._is_audio(row) == (self._route == "audio")
            ]
        if self._filter:
            saved = [
                (i, row)
                for i, row in saved
                if str(row.get("vodforge_user_category") or "") == self._filter
            ]
        if self._sort == "title":
            saved.sort(key=lambda pair: str(pair[1].get("title") or "").casefold())
        return saved

    def _filter_menu(self) -> None:
        menu = ContextMenu(self, tearoff=False)
        menu.add_command(label="All categories", command=partial(self._set_filter, ""))
        for value in sorted(
            {str(row.get("vodforge_user_category") or "") for _, row in self._saved()}
            - {""},
            key=str.casefold,
        ):
            menu.add_command(label=value, command=partial(self._set_filter, value))
        menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def _set_filter(self, value: str) -> None:
        self._targets = []
        self._context_targets = []
        self._pending_scroll = None
        self._filter = value
        self._page = 0
        if self._route in {"home", "channels", "playlists", "collections"}:
            self._route = "all"
        self._on_usage("library", "filtered")
        self._reset_catalog_viewport()
        self._presentation_change("filter")
        self._queue_render()

    def _clear_filters(self) -> None:
        self._filter = ""
        self._group_key = ""
        self._category = ""
        self.set_query("")

    def _group_menu(
        self, kind: str, key: str, label: str, indices: tuple[int, ...]
    ) -> None:
        menu = ContextMenu(self, tearoff=False)
        menu.add_command(
            label="Open "
            + (
                "channel"
                if kind == "channels"
                else "collection"
                if kind == "collections"
                else "playlist"
            ),
            command=partial(self._group_open, kind, key, label),
        )
        owners = tuple(archive_row_owner(self._records[index]) for index in indices)
        menu.add_command(
            label="Select media", command=partial(self._toggle_selection, owners)
        )
        menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def _submit_tag(self, index: int) -> None:
        if not 0 <= index < len(self._records) or not self._add_tag:
            return
        row = self._records[index]
        if archive_row_owner(row) != self._detail_owner:
            return
        if self._add_tag(self._detail_owner, self._tag_var.get(), False):
            self._tag_var.set("")

    def _refresh_tag_hint(self) -> None:
        if self._tag_var.get() or self._tag_entry.focus_get() is self._tag_entry:
            self._tag_hint.place_forget()
        else:
            self._tag_hint.place(in_=self._tag_entry, x=0, rely=0.5, anchor="w")

    def _remove_tag(self, owner: str, tag: str) -> None:
        if (
            self._add_tag
            and owner == self._detail_owner
            and any(archive_row_owner(row) == owner for row in self._records)
        ):
            self._add_tag(owner, tag, True)

    def _tag_return(self, _event: Any) -> str:
        index = next(
            (
                i
                for i, row in enumerate(self._records)
                if archive_row_owner(row) == self._detail_owner
            ),
            None,
        )
        if index is not None:
            self._submit_tag(index)
        return "break"

    def _group_open(self, kind: str, key: str, label: str) -> None:
        cancel_view_transition(self)
        self._targets = []
        self._context_targets = []
        self._pending_scroll = None
        self._group_kind, self._group_key, self._category = kind, key, label
        self._route = "all"
        self._page = 0
        self._reset_catalog_viewport()
        self._queue_render()

    def _copy_value(self, value: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(value)

    def _change_page(self, delta: int) -> None:
        if self.__dict__.get("_catalog_window"):
            self._catalog_scroll_command("scroll", delta, "pages")
            return
        self._targets = []
        self._context_targets = []
        self._pending_scroll = None
        self._on_usage("archive", "scene_paged", scene_route=self._route)
        self._presentation_change("navigation")
        self._page = max(0, self._page + delta)
        self.canvas.yview_moveto(0)
        self._queue_render()

    def _sort_menu(self) -> None:
        menu = ContextMenu(self, tearoff=False)
        for value, label in (("recent", "Recently Added"), ("title", "Title")):
            menu.add_command(label=label, command=partial(self._set_sort, value))
        menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def _set_sort(self, value: str) -> None:
        self._targets = []
        self._context_targets = []
        self._pending_scroll = None
        self._on_usage("archive", "scene_sorted", scene_route=self._route)
        self._reset_catalog_viewport()
        self._presentation_change("filter")
        self._sort = value
        self._page = 0
        self._queue_render()

    def _presentation_dimensions(self) -> dict[str, str]:
        from .presentation_diagnostics import count_bucket

        count = len(self._saved())
        return {
            "presentation_mode": "all",
            "mode_origin": "default",
            "presentation_population": "saved_media",
            "eligible_bucket": count_bucket(count),
            "mode_eligible_bucket": count_bucket(count),
            "matching_bucket": count_bucket(self._matching_count),
            "rendered_bucket": count_bucket(self._rendered_count),
            "query_state": "active" if self._query else "inactive",
            "filter_state": "active" if self._filter or self._group_key else "inactive",
        }

    def _destroyed(self, event: Any) -> None:
        if event.widget is not self:
            return
        self._closed = True
        if self._render_after:
            self.after_cancel(self._render_after)
        if self._storage_after:
            self.after_cancel(self._storage_after)
        self._storage.close()
        self._artwork_close()
        self._depth.clear()
        self._sidebar_depth.clear()
