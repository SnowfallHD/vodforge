"""Application ttk chrome. Styling authority lives outside the coordinator."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .ui_chrome import apply_product_chrome
from .ui_theme import (
    FONT_TITLE,
    FONT_UI,
    FONT_UI_FAMILY,
    FONT_UI_MEDIUM,
    FONT_UI_SMALL,
    FONT_UI_SMALL_MEDIUM,
    THEME,
)


def apply_product_styles(root: tk.Tk) -> None:
    root.configure(bg=THEME["bg"])
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(".", background=THEME["bg"], foreground=THEME["text"], font=FONT_UI)
    style.configure("TFrame", background=THEME["bg"])
    style.configure("Panel.TFrame", background=THEME["panel"])
    style.configure("Card.TFrame", background=THEME["surface"], relief="flat")
    style.configure(
        "TLabel", background=THEME["bg"], foreground=THEME["text"], font=FONT_UI
    )
    style.configure(
        "Muted.TLabel",
        background=THEME["bg"],
        foreground=THEME["muted"],
        font=FONT_UI_SMALL,
    )
    style.configure(
        "Hero.TLabel",
        background=THEME["bg"],
        foreground=THEME["text"],
        font=FONT_TITLE,
    )
    style.configure(
        "Accent.TLabel",
        background=THEME["bg"],
        foreground=THEME["accent"],
        font=FONT_UI_MEDIUM,
    )
    style.configure(
        "TLabelframe",
        background=THEME["bg"],
        foreground=THEME["text"],
        bordercolor=THEME["border"],
        relief="solid",
    )
    style.configure(
        "TLabelframe.Label",
        background=THEME["bg"],
        foreground=THEME["accent"],
        font=FONT_UI_MEDIUM,
    )
    style.configure(
        "TEntry",
        fieldbackground=THEME["surface"],
        foreground=THEME["text"],
        insertcolor=THEME["text"],
        bordercolor=THEME["surface"],
        lightcolor=THEME["surface"],
        darkcolor=THEME["surface"],
        padding=(10, 8),
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", THEME["surface"])],
        lightcolor=[("focus", THEME["surface"])],
        darkcolor=[("focus", THEME["surface"])],
    )
    style.configure(
        "TCombobox",
        fieldbackground=THEME["surface"],
        foreground=THEME["text"],
        background=THEME["surface"],
        arrowcolor=THEME["accent"],
        bordercolor=THEME["border"],
        padding=6,
    )
    style.map(
        "TCombobox",
        fieldbackground=[
            ("readonly", THEME["surface"]),
            ("active", THEME["surface_2"]),
        ],
        foreground=[("readonly", THEME["text"])],
    )
    style.configure(
        "TButton",
        background=THEME["surface_2"],
        foreground=THEME["text"],
        bordercolor=THEME["surface_2"],
        lightcolor=THEME["surface_2"],
        darkcolor=THEME["surface_2"],
        focusthickness=0,
        focuscolor=THEME["surface_2"],
        padding=(12, 7),
        font=FONT_UI_MEDIUM,
    )
    style.configure(
        "Compact.TButton",
        background=THEME["surface_2"],
        foreground=THEME["text"],
        bordercolor=THEME["border"],
        focusthickness=0,
        focuscolor=THEME["surface_2"],
        padding=(10, 4),
        font=FONT_UI_MEDIUM,
    )
    style.map(
        "Compact.TButton",
        background=[
            ("active", THEME["surface_2"]),
            ("pressed", THEME["panel"]),
            ("disabled", THEME["panel"]),
        ],
    )
    style.map(
        "TButton",
        background=[
            ("active", THEME["border"]),
            ("pressed", THEME["accent_dark"]),
            ("disabled", THEME["panel"]),
        ],
        foreground=[("disabled", THEME["subtle"])],
        bordercolor=[("focus", THEME["border"])],
        lightcolor=[("focus", THEME["border"])],
        darkcolor=[("focus", THEME["border"])],
    )
    style.configure(
        "Accent.TButton",
        background=THEME["accent_dark"],
        foreground="#ffffff",
        bordercolor=THEME["accent"],
    )
    style.map(
        "Accent.TButton",
        background=[
            ("active", THEME["accent"]),
            ("pressed", THEME["accent_dark"]),
            ("disabled", THEME["panel"]),
        ],
    )
    style.configure(
        "TCheckbutton",
        background=THEME["bg"],
        foreground=THEME["text"],
        indicatorcolor=THEME["surface"],
        font=FONT_UI,
    )
    style.map(
        "TCheckbutton",
        background=[("active", THEME["bg"])],
        foreground=[("disabled", THEME["subtle"])],
    )
    style.configure(
        "TProgressbar",
        background=THEME["accent"],
        troughcolor=THEME["surface"],
        bordercolor=THEME["border"],
        lightcolor=THEME["accent"],
        darkcolor=THEME["accent_dark"],
    )
    style.configure(
        "TNotebook",
        background=THEME["panel"],
        borderwidth=0,
        tabmargins=(8, 6, 8, 0),
    )
    style.configure(
        "TNotebook.Tab",
        background=THEME["surface"],
        foreground=THEME["muted"],
        padding=(18, 9),
        font=FONT_UI_MEDIUM,
        bordercolor=THEME["border"],
    )
    style.map(
        "TNotebook.Tab",
        background=[
            ("selected", THEME["accent_dark"]),
            ("active", THEME["surface_2"]),
        ],
        foreground=[("selected", "#ffffff"), ("active", THEME["text"])],
        expand=[("selected", (0, 0, 0, 0))],
    )
    style.configure(
        "Treeview",
        background=THEME["surface"],
        fieldbackground=THEME["surface"],
        foreground=THEME["text"],
        bordercolor=THEME["border"],
        rowheight=30,
        font=FONT_UI,
    )
    style.configure(
        "Treeview.Heading",
        background=THEME["panel"],
        foreground=THEME["muted"],
        relief="flat",
        font=FONT_UI_SMALL_MEDIUM,
    )
    style.map(
        "Treeview",
        background=[("selected", THEME["accent_dark"])],
        foreground=[("selected", "#ffffff")],
    )
    style.configure("FocusShell.TFrame", background=THEME["bg"])
    style.configure("FocusSurface.TFrame", background=THEME["surface"])
    style.configure(
        "FocusBrand.TLabel",
        background=THEME["bg"],
        foreground=THEME["text"],
        font=(FONT_UI_FAMILY, 18, "bold"),
    )
    style.configure(
        "FocusTitle.TLabel",
        background=THEME["bg"],
        foreground=THEME["text"],
        font=(FONT_UI_FAMILY, 18, "bold"),
    )
    style.configure(
        "FocusActiveTitle.TLabel",
        background=THEME["bg"],
        foreground=THEME["text"],
        font=(FONT_UI_FAMILY, 15, "bold"),
    )
    style.configure(
        "FocusProfile.TLabel",
        background=THEME["bg"],
        foreground=THEME["accent"],
        font=FONT_UI_SMALL,
    )
    style.configure(
        "FocusPercent.TLabel",
        background=THEME["bg"],
        foreground=THEME["accent"],
        font=(FONT_UI_FAMILY, 24),
    )
    style.configure(
        "FocusEyebrow.TLabel",
        background=THEME["bg"],
        foreground=THEME["muted"],
        font=FONT_UI_SMALL_MEDIUM,
    )
    style.configure(
        "FocusSurface.TLabel",
        background=THEME["surface"],
        foreground=THEME["text"],
        font=FONT_UI,
    )
    style.configure(
        "FocusSurfaceMuted.TLabel",
        background=THEME["surface"],
        foreground=THEME["muted"],
        font=FONT_UI_SMALL,
    )
    style.configure(
        "FocusNav.TButton",
        background=THEME["bg"],
        foreground=THEME["muted"],
        bordercolor=THEME["bg"],
        focusthickness=0,
        focuscolor=THEME["bg"],
        padding=(12, 8),
        font=FONT_UI,
    )
    style.configure(
        "FocusNavActive.TButton",
        background=THEME["bg"],
        foreground=THEME["accent"],
        bordercolor=THEME["bg"],
        focusthickness=0,
        focuscolor=THEME["bg"],
        padding=(12, 8),
        font=FONT_UI,
    )
    style.layout(
        "FocusNav.TButton",
        [
            (
                "Button.padding",
                {
                    "sticky": "nswe",
                    "children": [("Button.label", {"sticky": "nswe"})],
                },
            )
        ],
    )
    style.layout(
        "FocusNavActive.TButton",
        [
            (
                "Button.padding",
                {
                    "sticky": "nswe",
                    "children": [("Button.label", {"sticky": "nswe"})],
                },
            )
        ],
    )
    style.map(
        "FocusNav.TButton",
        background=[("active", THEME["surface"])],
        foreground=[("active", THEME["text"])],
    )
    style.map(
        "FocusNavActive.TButton",
        background=[("active", THEME["surface"])],
        foreground=[("active", THEME["accent"])],
    )
    style.configure(
        "FocusQuiet.TButton",
        background=THEME["surface"],
        foreground=THEME["muted"],
        bordercolor=THEME["surface"],
        lightcolor=THEME["surface"],
        darkcolor=THEME["surface"],
        focusthickness=0,
        focuscolor=THEME["surface"],
        relief="flat",
        padding=(11, 6),
        font=FONT_UI_SMALL_MEDIUM,
    )
    style.map(
        "FocusQuiet.TButton",
        background=[("active", THEME["surface_2"]), ("pressed", THEME["panel"])],
        foreground=[("active", THEME["text"])],
        bordercolor=[("focus", THEME["surface"])],
        lightcolor=[("focus", THEME["surface"])],
        darkcolor=[("focus", THEME["surface"])],
    )
    style.configure(
        "CloudDisabled.TButton",
        background=THEME["surface_2"],
        foreground=THEME["subtle"],
        bordercolor=THEME["surface_2"],
        lightcolor=THEME["surface_2"],
        darkcolor=THEME["surface_2"],
        focusthickness=0,
        focuscolor=THEME["surface_2"],
        relief="flat",
        padding=(11, 6),
        font=FONT_UI_SMALL_MEDIUM,
    )
    style.map(
        "CloudDisabled.TButton",
        background=[("disabled", THEME["surface_2"])],
        foreground=[("disabled", THEME["subtle"])],
    )
    style.configure(
        "FocusIcon.TButton",
        background=THEME["bg"],
        foreground=THEME["muted"],
        bordercolor=THEME["bg"],
        lightcolor=THEME["bg"],
        darkcolor=THEME["bg"],
        focusthickness=0,
        focuscolor=THEME["bg"],
        relief="flat",
        padding=(9, 8),
    )
    style.map(
        "FocusIcon.TButton",
        background=[("active", THEME["surface"]), ("pressed", THEME["panel"])],
    )
    style.configure(
        "FocusDestination.TButton",
        background=THEME["surface"],
        foreground=THEME["muted"],
        bordercolor=THEME["border"],
        lightcolor=THEME["border"],
        darkcolor=THEME["border"],
        focusthickness=0,
        focuscolor=THEME["surface"],
        relief="flat",
        padding=(12, 7),
        font=FONT_UI_SMALL,
    )
    style.map(
        "FocusDestination.TButton",
        background=[("active", THEME["surface_2"])],
        foreground=[("active", THEME["text"])],
    )
    style.configure(
        "FocusCommand.TEntry",
        fieldbackground=THEME["surface"],
        foreground=THEME["text"],
        insertcolor=THEME["text"],
        bordercolor=THEME["surface"],
        lightcolor=THEME["surface"],
        darkcolor=THEME["surface"],
        padding=(4, 13),
        font=(FONT_UI_FAMILY, 12),
    )
    style.configure(
        "FocusProgress.Horizontal.TProgressbar",
        background=THEME["accent"],
        troughcolor=THEME["surface_2"],
        bordercolor=THEME["bg"],
        lightcolor=THEME["accent"],
        darkcolor=THEME["accent"],
        thickness=4,
        borderwidth=0,
    )
    style.configure(
        "FocusDeck.Horizontal.TProgressbar",
        background=THEME["accent"],
        troughcolor=THEME["border"],
        bordercolor=THEME["surface"],
        lightcolor=THEME["accent"],
        darkcolor=THEME["accent"],
        thickness=3,
        borderwidth=0,
    )
    style.configure(
        "Focus.TPanedwindow",
        background=THEME["bg"],
        sashwidth=1,
        sashrelief="flat",
        handlesize=0,
        handlepad=0,
    )
    style.configure("Focus.TSizegrip", background=THEME["bg"])
    root.option_add("*TCombobox*Listbox.background", THEME["surface"])
    root.option_add("*TCombobox*Listbox.foreground", THEME["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", THEME["accent_dark"])
    style.configure("Violet.FocusBrand.TLabel", foreground=THEME["accent"])
    apply_product_chrome(root, style)
