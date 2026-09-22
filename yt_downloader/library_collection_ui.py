"""A focused collection editor using the existing annotation membership owner."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk
from typing import cast

from .ui_button_contract import ProductButton
from .ui_chrome import RoundedFieldBorder
from .ui_layout import (
    bounded_window_size,
    centered_toplevel_geometry,
    window_logical_metrics,
)
from .ui_theme import FONT_UI, THEME
from .ui_widgets import (
    ActionDialogSurface,
    PlaceholderEntry,
    SleekScrollbar,
    bind_smooth_vertical_wheel,
)


class LibraryCollectionDialog:
    def __init__(
        self,
        master: tk.Misc,
        items: Sequence[tuple[str, str]],
        save: Callable[[str, tuple[str, ...]], None],
        *,
        selected: Sequence[str] = (),
    ) -> None:
        self._items = tuple(items)
        self._save = save
        self.popup = tk.Toplevel(master)
        metrics = window_logical_metrics(self.popup)
        px = metrics.px
        owner = master.winfo_toplevel()
        self.popup.title("New collection")
        screen_width, screen_height = (
            self.popup.winfo_screenwidth(),
            self.popup.winfo_screenheight(),
        )
        limit_width, limit_height = bounded_window_size(screen_width, screen_height)
        width = min(px(540), limit_width)
        self.popup.geometry(
            centered_toplevel_geometry(owner, 540, 480, target=self.popup)
        )
        self.popup.configure(bg=THEME["bg"])
        self.popup.transient(cast(tk.Wm, owner))
        self.popup.minsize(min(px(500), limit_width), min(px(400), limit_height))
        self.dialog_surface = ActionDialogSurface(
            self.popup, padx=24, pady=22, modal=True
        )
        body = self.dialog_surface.body
        actions = self.dialog_surface.footer
        ttk.Label(
            body,
            text="Create a collection",
            font=metrics.font((FONT_UI[0], 20, "bold")),
        ).pack(anchor="w")
        description = ttk.Label(
            body,
            text="Choose a name, then click the media you want to include.",
            style="Muted.TLabel",
            font=metrics.font(FONT_UI),
            wraplength=max(px(80), width - px(48)),
        )
        description.pack(fill="x", anchor="w", pady=(px(8), px(20)))
        self.name = tk.StringVar(self.popup, "")
        entry = PlaceholderEntry(
            body,
            textvariable=self.name,
            placeholder="Type your collection name",
        )
        self.name_entry = entry
        entry.pack(fill="x", pady=(0, px(16)))
        holder = tk.Frame(body, bg=THEME["bg"])
        holder.pack(fill="both", expand=True)
        self._field_chrome = RoundedFieldBorder(holder)
        self.items = tk.Listbox(
            holder,
            selectmode="multiple",
            exportselection=False,
            bg=THEME["panel"],
            fg=THEME["text"],
            selectbackground=THEME["accent_surface"],
            selectforeground=THEME["text"],
            bd=0,
            activestyle="none",
            highlightthickness=0,
            highlightcolor=THEME["accent"],
            highlightbackground=THEME["border"],
            font=metrics.font(FONT_UI),
        )
        self.items.pack(side="left", fill="both", expand=True, padx=px(5), pady=px(5))
        self.items.bind("<FocusIn>", self._sync_focus_material, add="+")
        self.items.bind("<FocusOut>", self._sync_focus_material, add="+")
        scroll = SleekScrollbar(holder, command=self.items.yview)
        scroll.pack(side="right", fill="y")
        self.items.configure(yscrollcommand=scroll.set)
        bind_smooth_vertical_wheel(
            self.items, self.items, scroll, mode="rows", row_pixels=px(24)
        )
        for index, (item_owner, title) in enumerate(self._items):
            self.items.insert("end", title)
            if item_owner in selected:
                self.items.selection_set(index)
        self.error = tk.StringVar(self.popup, "")
        error_label = ttk.Label(
            actions,
            textvariable=self.error,
            style="Muted.TLabel",
            font=metrics.font(FONT_UI),
            wraplength=max(px(80), width - px(48)),
        )
        error_label.pack(fill="x", anchor="w", pady=px(8))

        def fit_label(event: tk.Event) -> None:
            available = max(1, event.width)
            label = event.widget
            if (
                isinstance(label, ttk.Label)
                and int(label.cget("wraplength")) != available
            ):
                label.configure(wraplength=available)

        for label in (description, error_label):
            label.bind("<Configure>", fit_label, add="+")
        self.save_button = ProductButton(
            actions,
            text="Save",
            width=10,
            style="Accent.TButton",
            command=self._commit,
        )
        self.save_button.pack(side="right")
        ProductButton(actions, text="Cancel", command=self.popup.destroy).pack(
            side="right", padx=px(8)
        )
        self.dialog_surface.bind_keys(
            {"<Return>": self._commit, "<Escape>": self.popup.destroy},
            editing=("<Return>", "<Escape>"),
        )
        self._sync_focus_material()
        entry.focus_set()

    def _sync_focus_material(self, _event: object = None) -> None:
        focused = self.items.focus_get() is self.items
        self.items.configure(bg=THEME["focus_surface"] if focused else THEME["surface"])
        self._field_chrome.request(focused)

    def _commit(self) -> None:
        name = self.name.get().strip()
        chosen = tuple(self._items[int(i)][0] for i in self.items.curselection())
        if not name or len(name) > 120:
            self.error.set("Enter a collection name of up to 120 characters.")
            return
        if not chosen:
            self.error.set("Choose at least one saved item.")
            return
        try:
            self._save(name, chosen)
        except (ValueError, OSError, RuntimeError) as exc:
            self.error.set(str(exc))
            return
        self.popup.destroy()
