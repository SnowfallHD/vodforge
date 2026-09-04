from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from .library_annotations import LibraryAnnotation
from .ui_layout import centered_toplevel_geometry
from .ui_theme import THEME
from .ui_widgets import (
    ActionDialogSurface,
    ChoiceDropdown,
    ProductEntry,
    bind_focus_ring,
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
        popup = tk.Toplevel(owner)
        popup.withdraw()
        popup.title("VODForge Library details")
        popup.transient(owner)
        popup.configure(bg=THEME["bg"])
        popup.resizable(True, True)
        popup.minsize(520, 430)
        self.popup = popup

        surface = ActionDialogSurface(popup, padx=24, pady=22)
        self.dialog_surface = surface
        root = surface.body
        root.columnconfigure(0, weight=1)
        root.rowconfigure(9, weight=1)

        ttk.Label(root, text="Organize this item", style="FocusTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            root,
            text=title,
            style="Muted.TLabel",
            wraplength=620,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 18))

        ttk.Label(root, text="CATEGORY", style="FocusEyebrow.TLabel").grid(
            row=2, column=0, sticky="w", pady=(0, 5)
        )
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
            wraplength=620,
            justify="left",
        ).grid(row=4, column=0, sticky="w", pady=(4, 14))

        ttk.Label(root, text="YOUR TAGS", style="FocusEyebrow.TLabel").grid(
            row=5, column=0, sticky="w", pady=(0, 5)
        )
        self.tags_var = tk.StringVar(value=", ".join(annotation.tags))
        ProductEntry(root, textvariable=self.tags_var).grid(
            row=6, column=0, sticky="ew"
        )
        ttk.Label(
            root,
            text="Separate tags with commas. YouTube’s original tags stay unchanged.",
            style="Muted.TLabel",
        ).grid(row=7, column=0, sticky="w", pady=(4, 14))

        ttk.Label(root, text="NOTES", style="FocusEyebrow.TLabel").grid(
            row=8, column=0, sticky="nw", pady=(0, 5)
        )
        note_shell = tk.Frame(root, bg=THEME["surface"], bd=0)
        note_shell.grid(row=9, column=0, sticky="nsew")
        note_shell.columnconfigure(0, weight=1)
        note_shell.rowconfigure(0, weight=1)
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
            padx=12,
            pady=10,
        )
        self.note.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        self.note.insert("1.0", annotation.note)
        bind_focus_ring(self.note, note_shell)

        actions = surface.footer
        actions.columnconfigure(0, weight=1)
        ttk.Button(
            actions,
            text="Cancel",
            command=popup.destroy,
            style="FocusQuiet.TButton",
        ).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(
            actions,
            text="Save details",
            command=self._save,
            style="Accent.TButton",
        ).grid(row=0, column=2)

        popup.protocol("WM_DELETE_WINDOW", popup.destroy)
        popup.bind("<Escape>", lambda _event: popup.destroy())

    def _save(self) -> None:
        saved = self.on_save(
            LibraryAnnotation(
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
            centered_toplevel_geometry(self.owner, width=620, height=520),
        )
        self.popup.grab_set()
        self.popup.focus_force()
