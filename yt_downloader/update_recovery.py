"""Actionable update recovery copy and native dialogs; no application state owner."""

from __future__ import annotations

import sys
import tkinter as tk
import webbrowser
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk

from .modal_backdrop import ModalBackdrop
from .ui_theme import THEME
from .ui_widgets import ActionDialogSurface, ProductEntry
from .updates import RELEASES_PAGE


def show_update_recovery(
    parent: tk.Misc, detail: str, repair: Callable[[], None]
) -> None:
    """Keep the app available; retry only after an explicit user action."""
    backdrop = ModalBackdrop(parent)
    popup = tk.Frame(
        parent,
        name="update_recovery",
        bg=THEME["bg"],
        highlightthickness=1,
        highlightbackground=THEME["surface_2"],
    )
    expanded = False

    def resize(event=None) -> None:
        if event is not None and event.widget is not parent:
            return
        popup.place(
            relx=0.5,
            rely=0.5,
            anchor="center",
            width=min(620, max(340, parent.winfo_width() - 36)),
            height=min(550 if expanded else 405, max(350, parent.winfo_height() - 36)),
        )
        backdrop.refresh(popup)

    binding = parent.bind("<Configure>", resize, add="+")

    def close() -> None:
        if binding:
            parent.unbind("<Configure>", binding)
        backdrop.close()
        popup.destroy()

    surface = ActionDialogSurface(popup)
    ttk.Label(
        surface.body, text="VODForge update needs attention", style="FocusTitle.TLabel"
    ).pack(anchor="w", pady=(0, 12))
    message = ttk.Label(
        surface.body,
        text=(
            "The update could not start. VODForge is still open.\n\n"
            "Select Repair VODForge to download a fresh copy of the latest update and try again. "
            "If repair is blocked, select Open download page for installation steps. Do not uninstall first."
        ),
        wraplength=560,
        justify="left",
    )
    message.pack(anchor="w")
    if sys.platform == "win32":
        ttk.Label(surface.body, text="Current app folder").pack(
            anchor="w", pady=(10, 4)
        )
        folder = tk.StringVar(popup, str(Path(sys.executable).parent))
        ProductEntry(surface.body, textvariable=folder, state="readonly").pack(fill="x")
    details = tk.Text(
        surface.body,
        height=5,
        wrap="word",
        bg=THEME["surface"],
        fg=THEME["text"],
        relief="flat",
        padx=8,
        pady=8,
    )
    details.insert("1.0", detail)
    details.configure(state="disabled")

    def toggle() -> None:
        nonlocal expanded
        expanded = not expanded
        if details.winfo_manager():
            details.pack_forget()
        else:
            details.pack(fill="both", expand=True, pady=8)
        resize()

    ttk.Button(surface.body, text="Technical details", command=toggle).pack(
        anchor="w", pady=10
    )

    def retry() -> None:
        close()
        repair()

    ttk.Button(
        surface.footer, text="Repair VODForge", style="Accent.TButton", command=retry
    ).pack(side="right")

    def open_download_page() -> None:
        message.configure(
            text=(
                "Download the installer for your computer. Close VODForge, then open the downloaded file. "
                "On Windows, select the current app folder below and click Install. "
                "On Mac, replace VODForge in your Applications folder. Do not uninstall first."
            )
        )
        if not webbrowser.open(RELEASES_PAGE):
            message.configure(
                text="Open your browser and go to "
                + RELEASES_PAGE
                + ". Download the installer, close VODForge, and open that file. Do not uninstall first."
            )

    ttk.Button(
        surface.footer,
        text="Open download page",
        command=open_download_page,
    ).pack(side="right", padx=8)
    ttk.Button(surface.footer, text="Later", command=close).pack(side="left")
    resize()
    popup.bind("<Configure>", lambda _e: backdrop.refresh(popup))
    popup.bind("<Destroy>", lambda _e: backdrop.close())

    def bind_escape(widget: tk.Misc) -> None:
        widget.bind("<Escape>", lambda _e: close(), add="+")
        for child in widget.winfo_children():
            bind_escape(child)

    bind_escape(popup)
    popup.lift()
    popup.grab_set()
    popup.focus_set()
    popup.wait_window()
