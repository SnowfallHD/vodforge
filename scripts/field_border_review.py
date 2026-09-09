"""Isolated native field capture; no app services or persisted user state."""

import os
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import Quartz

from yt_downloader.library_search_ui import LibrarySearchField
from yt_downloader.ui_chrome import RoundedFieldBorder
from yt_downloader.ui_styles import apply_product_styles
from yt_downloader.ui_theme import FONT_UI, THEME
from yt_downloader.ui_widgets import ChoiceDropdown, ProductEntry

root = tk.Tk()
root.title("VODForge — field border verification")
root.configure(bg=THEME["bg"])
apply_product_styles(root)
root.geometry("700x490")
tags = tk.StringVar(root, "mountains, quiet")
for label, field in (
    (
        "Category",
        ChoiceDropdown(
            root,
            textvariable=tk.StringVar(root, "Travel"),
            values=("Travel",),
            state="normal",
        ),
    ),
    ("Tags", ProductEntry(root, textvariable=tags)),
    ("Search", LibrarySearchField(root, variable=tk.StringVar(root, "mountains"))),
):
    ttk.Label(root, text=label).pack(anchor="w", padx=24, pady=(14, 4))
    field.pack(fill="x", padx=24)
ttk.Label(root, text="Notes").pack(anchor="w", padx=24, pady=(14, 4))
shell = tk.Frame(root, bg=THEME["surface"])
shell.pack(fill="both", expand=True, padx=24, pady=(0, 24))
chrome = RoundedFieldBorder(shell)
note = tk.Text(
    shell,
    bg=THEME["surface"],
    fg=THEME["text"],
    bd=0,
    highlightthickness=0,
    height=4,
    font=FONT_UI,
)
note.pack(fill="both", expand=True, padx=8, pady=8)
note.insert("1.0", "A short film about finding peace in the mountains.")


def capture():
    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly, 0
    )
    window = next(
        w
        for w in windows
        if w.get("kCGWindowOwnerPID") == os.getpid() and w.get("kCGWindowLayer") == 0
    )
    output = Path("build/field-border-review.png")
    output.parent.mkdir(exist_ok=True)
    subprocess.run(
        [
            "/usr/sbin/screencapture",
            "-x",
            "-o",
            "-l",
            str(window["kCGWindowNumber"]),
            str(output),
        ],
        check=True,
    )
    root.destroy()


root.after(1000, capture)
root.mainloop()
