from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import replace
from tkinter import ttk

from .library_annotations import LibraryAnnotation
from .ui_button_contract import ProductButton
from .ui_chrome import RoundedFieldBorder
from .ui_layout import (
    bounded_window_size,
    centered_toplevel_geometry,
    window_logical_metrics,
)
from .ui_theme import FONT_UI, FONT_UI_SMALL_MEDIUM, THEME
from .ui_widgets import (
    ActionDialogSurface,
    ChoiceDropdown,
    ProductEntry,
    bind_smooth_vertical_wheel,
    reveal_toplevel,
)


class LibraryAnnotationDialog:
    """Own the compact user-note editor and return one immutable value."""

    def __init__(
        self,
        owner: tk.Tk,
        *,
        title: str,
        annotation: LibraryAnnotation,
        categories: tuple[str, ...],
        on_save: Callable[[LibraryAnnotation], bool],
    ) -> None:
        self.owner = owner
        self.on_save = on_save
        self._annotation = annotation
        popup = tk.Toplevel(owner)
        popup.withdraw()
        popup.title("VODForge Library details")
        popup.transient(owner)
        popup.configure(bg=THEME["bg"])
        popup.resizable(True, True)
        metrics = window_logical_metrics(popup)
        px = metrics.px
        limit = bounded_window_size(
            popup.winfo_screenwidth(), popup.winfo_screenheight()
        )
        popup.minsize(min(px(520), limit[0]), min(px(500), limit[1]))
        self.popup = popup

        # Enlarged content can exceed the measured screen even at the bounded
        # minimum. Reuse the existing document viewport only for this case;
        # ordinary geometry keeps its adaptive note field.
        surface = ActionDialogSurface(
            popup, padx=24, pady=22, allow_body_scroll=metrics.scale > 1
        )
        self.dialog_surface = surface
        root = surface.body
        root.columnconfigure(0, weight=1)
        root.rowconfigure(9, weight=1)

        ttk.Label(
            root,
            text="Organize this item",
            style="FocusTitle.TLabel",
            font=metrics.font((FONT_UI[0], 18, "bold")),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            root,
            text=title,
            style="Muted.TLabel",
            font=metrics.font(FONT_UI),
            wraplength=px(572),
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(px(4), px(18)))

        ttk.Label(
            root,
            text="CATEGORY",
            style="FocusEyebrow.TLabel",
            font=metrics.font(FONT_UI_SMALL_MEDIUM),
        ).grid(row=2, column=0, sticky="w", pady=(0, px(5)))
        self.category_var = tk.StringVar(value=annotation.category)
        category_field: ProductEntry | ChoiceDropdown
        if categories:
            category_field = ChoiceDropdown(
                root,
                textvariable=self.category_var,
                values=categories,
                state="normal",
            )
        else:
            category_field = ProductEntry(root, textvariable=self.category_var)
        category_field.grid(row=3, column=0, sticky="ew")
        ttk.Label(
            root,
            text=(
                "Categories are your custom Library collections. Type one to "
                "create it, then filter Library by it."
            ),
            style="Muted.TLabel",
            font=metrics.font(FONT_UI),
            wraplength=px(572),
            justify="left",
        ).grid(row=4, column=0, sticky="ew", pady=(px(4), px(14)))

        ttk.Label(
            root,
            text="YOUR TAGS",
            style="FocusEyebrow.TLabel",
            font=metrics.font(FONT_UI_SMALL_MEDIUM),
        ).grid(row=5, column=0, sticky="w", pady=(0, px(5)))
        self.tags_var = tk.StringVar(value=", ".join(annotation.tags))
        ProductEntry(root, textvariable=self.tags_var).grid(
            row=6, column=0, sticky="ew"
        )
        ttk.Label(
            root,
            text="Separate tags with commas. YouTube’s original tags stay unchanged.",
            wraplength=px(572),
            justify="left",
            style="Muted.TLabel",
            font=metrics.font(FONT_UI),
        ).grid(row=7, column=0, sticky="ew", pady=(px(4), px(14)))

        ttk.Label(
            root,
            text="NOTES",
            style="FocusEyebrow.TLabel",
            font=metrics.font(FONT_UI_SMALL_MEDIUM),
        ).grid(row=8, column=0, sticky="nw", pady=(0, px(5)))
        note_shell = tk.Frame(root, bg=THEME["surface"], bd=0)
        note_shell.grid(row=9, column=0, sticky="nsew")
        note_shell.columnconfigure(0, weight=1)
        note_shell.rowconfigure(0, weight=1)
        self._note_chrome = RoundedFieldBorder(note_shell)
        self.note = tk.Text(
            note_shell,
            height=8,
            wrap="word",
            bg=THEME["surface"],
            fg=THEME["text"],
            insertbackground=THEME["text"],
            selectbackground=THEME["accent_dark"],
            bd=0,
            highlightthickness=0,
            padx=px(12),
            pady=px(10),
            font=metrics.font(FONT_UI),
        )
        self.note.grid(row=0, column=0, sticky="nsew", padx=px(8), pady=px(8))
        self.note.insert("1.0", annotation.note)
        bind_smooth_vertical_wheel(self.note, mode="pixels")
        self.note.bind("<FocusIn>", lambda _event: self._note_chrome.request(True))
        self.note.bind("<FocusOut>", lambda _event: self._note_chrome.request(False))

        actions = surface.footer
        actions.columnconfigure(0, weight=1)
        ProductButton(
            actions,
            text="Cancel",
            command=popup.destroy,
            style="FocusQuiet.TButton",
        ).grid(row=0, column=1, padx=(0, px(8)))
        ProductButton(
            actions,
            text="Save details",
            command=self._save,
            style="Accent.TButton",
        ).grid(row=0, column=2)

        def fit_label(event: tk.Event) -> None:
            available = max(1, event.width)
            label = event.widget
            if (
                isinstance(label, ttk.Label)
                and int(label.cget("wraplength")) != available
            ):
                label.configure(wraplength=available)

        for label in root.winfo_children():
            if isinstance(label, ttk.Label) and int(label.cget("wraplength") or 0):
                label.bind("<Configure>", fit_label, add="+")

        def reveal_focused_field(event: tk.Event) -> None:
            viewport = surface.viewport
            if viewport is None or not str(event.widget).startswith(str(root) + "."):
                return
            top = event.widget.winfo_rooty() - root.winfo_rooty()
            bottom = top + event.widget.winfo_height()
            visible_top = viewport.canvasy(0)
            visible_height = viewport.winfo_height()
            extent = max(1, root.winfo_height())
            if top < visible_top:
                viewport.yview_moveto(top / extent)
            elif bottom > visible_top + visible_height:
                viewport.yview_moveto(min(top, bottom - visible_height) / extent)

        popup.bind("<FocusIn>", reveal_focused_field, add="+")
        popup.protocol("WM_DELETE_WINDOW", popup.destroy)
        popup.bind("<Escape>", lambda _event: popup.destroy())

    def _save(self) -> None:
        saved = self.on_save(
            replace(
                self._annotation,
                note=self.note.get("1.0", "end-1c"),
                tags=tuple(part for part in self.tags_var.get().split(",")),
                category=self.category_var.get(),
            )
        )
        if saved:
            self.popup.destroy()

    def show(self) -> None:
        reveal_toplevel(
            self.popup,
            centered_toplevel_geometry(self.owner, 620, 520, target=self.popup),
        )
        self.popup.grab_set()
        self.popup.focus_force()
