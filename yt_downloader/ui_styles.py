"""Application ttk chrome. Styling authority lives outside the coordinator."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .ui_button_contract import apply_button_metrics
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
        foreground=THEME["action"],
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
        foreground=THEME["action"],
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
        bordercolor=[("focus", THEME["focus"])],
        lightcolor=[("focus", THEME["focus"])],
        darkcolor=[("focus", THEME["focus"])],
    )
    style.configure(
        "TCombobox",
        fieldbackground=THEME["surface"],
        foreground=THEME["text"],
        background=THEME["surface"],
        arrowcolor=THEME["icon"],
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
        foreground=THEME["action"],
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
        background=THEME["progress"],
        troughcolor=THEME["surface"],
        bordercolor=THEME["border"],
        lightcolor=THEME["progress"],
        darkcolor=THEME["progress"],
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
        foreground=[("selected", THEME["on_accent"]), ("active", THEME["text"])],
        expand=[("selected", (0, 0, 0, 0))],
    )
    style.configure(
        "Archive.TNotebook",
        background=THEME["bg"],
        borderwidth=0,
        bordercolor=THEME["bg"],
        lightcolor=THEME["bg"],
        darkcolor=THEME["bg"],
        tabmargins=(0, 0, 0, 6),
    )
    readonly_list_selection: dict[str, list[tuple[str, ...]]] = {
        "background": [
            ("selected", "focus", THEME["accent_dark"]),
            ("selected", THEME["accent_surface"]),
        ],
        "foreground": [
            ("selected", "focus", THEME["on_accent"]),
            ("selected", THEME["text"]),
        ],
    }
    style.configure(
        "ArchiveLocations.Treeview",
        background=THEME["panel"],
        fieldbackground=THEME["panel"],
        foreground=THEME["muted"],
        rowheight=52,
        borderwidth=0,
        font=FONT_UI_SMALL,
    )
    style.layout(
        "ArchiveLocations.Treeview", [("Treeview.treearea", {"sticky": "nswe"})]
    )
    # Tk accepts state tuples with both one and two state selectors.
    style.map("ArchiveLocations.Treeview", **readonly_list_selection)  # type: ignore[call-overload]
    style.configure("Archive.FocusNav.TButton", anchor="w")
    style.configure("Archive.FocusNavActive.TButton", anchor="w")
    style.map(
        "Archive.TNotebook.Tab",
        expand=[("selected", (0, 0, 0, 0))],
        # Clam inherits a smaller selected-state padding in physical points.
        # Explicit symmetric padding keeps every text tab on one baseline.
        padding=[("selected", (8, 8)), ("!selected", (8, 8))],
    )
    style.configure(
        "Archive.TNotebook.Tab",
        background=THEME["bg"],
        foreground=THEME["muted"],
        padding=(8, 8),
        font=FONT_UI_SMALL,
        borderwidth=0,
        bordercolor=THEME["bg"],
        lightcolor=THEME["bg"],
        darkcolor=THEME["bg"],
        focuscolor=THEME["focus"],
    )
    style.map(
        "Archive.TNotebook.Tab",
        background=[
            ("selected", THEME["bg"]),
            ("active", THEME["bg"]),
        ],
        foreground=[("selected", THEME["selection"]), ("active", THEME["text"])],
        lightcolor=[("selected", THEME["bg"]), ("!selected", THEME["bg"])],
        darkcolor=[("selected", THEME["bg"]), ("!selected", THEME["bg"])],
        bordercolor=[("selected", THEME["bg"]), ("!selected", THEME["bg"])],
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
        foreground=[("selected", THEME["on_accent"])],
    )
    style.configure("FocusShell.TFrame", background=THEME["bg"])
    style.configure("FocusSurface.TFrame", background=THEME["surface"])
    style.configure("FocusPanel.TFrame", background=THEME["panel"])
    style.configure(
        "Sidebar.FocusEyebrow.TLabel", background=THEME["panel"], font=FONT_UI_SMALL
    )
    style.configure("Archive.FocusNav.TButton", background=THEME["panel"])
    style.configure("Archive.FocusNavActive.TButton", background=THEME["panel"])
    style.configure(
        "FocusBrand.TLabel",
        background=THEME["bg"],
        foreground=THEME["text"],
        font=(FONT_UI_FAMILY, -24, "bold"),
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
        foreground=THEME["muted"],
        font=FONT_UI_SMALL,
    )
    style.configure(
        "FocusPercent.TLabel",
        background=THEME["bg"],
        foreground=THEME["progress"],
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
        foreground=THEME["text"],
        bordercolor=THEME["bg"],
        focusthickness=0,
        focuscolor=THEME["bg"],
        padding=(10, 1),
        font=FONT_UI,
    )
    style.map(
        "FocusNav.TButton",
        # The shared chrome image supplies the concise inset hover contour.
        # Do not add a full-control fill or border highlight on top of it.
        background=[("active", THEME["bg"])],
        foreground=[("active", THEME["text"])],
    )
    style.map(
        "FocusNavActive.TButton",
        background=[("active", THEME["bg"])],
        foreground=[("active", THEME["selection"])],
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
        bordercolor=[("focus", THEME["focus"])],
        lightcolor=[("focus", THEME["focus"])],
        darkcolor=[("focus", THEME["focus"])],
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
        background=THEME["progress"],
        troughcolor=THEME["surface_2"],
        bordercolor=THEME["bg"],
        lightcolor=THEME["progress"],
        darkcolor=THEME["progress"],
        thickness=4,
        borderwidth=0,
    )
    style.configure(
        "FocusDeck.Horizontal.TProgressbar",
        background=THEME["progress"],
        troughcolor=THEME["border"],
        bordercolor=THEME["surface"],
        lightcolor=THEME["progress"],
        darkcolor=THEME["progress"],
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
    style.configure("Violet.FocusBrand.TLabel", foreground=THEME["action"])
    apply_product_chrome(root, style)
    for tab_style in ("TNotebook.Tab", "Archive.TNotebook.Tab"):
        style.layout(
            tab_style,
            [
                (
                    "Product.tab",
                    {
                        "sticky": "nsew",
                        "children": [
                            (
                                "Notebook.padding",
                                {
                                    "sticky": "nsew",
                                    "children": [
                                        ("Notebook.label", {"sticky": "nsew"})
                                    ],
                                },
                            )
                        ],
                    },
                )
            ],
        )
        style.map(
            tab_style,
            background=[("selected", THEME["bg"]), ("active", THEME["bg"])],
            foreground=[("selected", THEME["selection"]), ("active", THEME["text"])],
        )
    style.layout(
        "FocusNavActive.TButton",
        [
            (
                "Product.nav_selected",
                {
                    "sticky": "nsew",
                    "children": [
                        (
                            "Button.padding",
                            {
                                "sticky": "nsew",
                                "children": [("Button.label", {"sticky": "nsew"})],
                            },
                        )
                    ],
                },
            )
        ],
    )

    for role in ("Media.Accent.TButton", "Media.FocusQuiet.TButton"):
        style.configure(role, font=FONT_UI, padding=(5, 0), foreground=THEME["text"])
    style.configure("Media.Accent.TButton", foreground=THEME["action"])
    style.configure("Media.FocusNav.TButton", font=FONT_UI, padding=(8, 5))
    style.configure(
        "Streaming.Media.FocusQuiet.TButton",
        font=(FONT_UI_FAMILY, -15, "normal"),
        padding=(15, 7),
    )

    style.map(
        "Media.FocusNav.TButton",
        foreground=[
            ("disabled", THEME["subtle"]),
            ("focus", THEME["focus"]),
            ("active", THEME["text"]),
        ],
    )
    # Media content uses one quiet outlined action role and one primary role.
    # Parent-surface variants retain transparent rounded corners in every state.
    style.configure(
        "Archive.Folders.Treeview",
        background=THEME["bg"],
        fieldbackground=THEME["bg"],
        foreground=THEME["text"],
        rowheight=34,
        borderwidth=0,
        font=FONT_UI_SMALL,
    )
    style.layout(
        "Archive.Folders.Treeview", [("Treeview.treearea", {"sticky": "nswe"})]
    )
    style.map("Archive.Folders.Treeview", **readonly_list_selection)  # type: ignore[call-overload]
    style.configure("MediaPanel.TFrame", background=THEME["panel"])
    style.configure(
        "Player.Archive.TNotebook",
        background=THEME["panel"],
        bordercolor=THEME["panel"],
        lightcolor=THEME["panel"],
        darkcolor=THEME["panel"],
        borderwidth=0,
        padding=0,
    )
    style.configure(
        "Player.Chapters.Treeview",
        background=THEME["panel"],
        fieldbackground=THEME["panel"],
        foreground=THEME["text"],
        rowheight=38,
        borderwidth=0,
        font=FONT_UI_SMALL,
    )
    style.layout(
        "Player.Chapters.Treeview", [("Treeview.treearea", {"sticky": "nswe"})]
    )
    style.map("Player.Chapters.Treeview", **readonly_list_selection)  # type: ignore[call-overload]

    style.configure("Material.TFrame", background=THEME["bg"])
    style.configure(
        "Player.Transport.TLabel",
        background=THEME["panel"],
        foreground=THEME["muted"],
        font=FONT_UI_SMALL,
    )
    style.configure("Player.Media.Accent.TButton", background=THEME["panel"])
    style.map(
        "Player.Media.Accent.TButton",
        background=[("active", THEME["panel"]), ("disabled", THEME["panel"])],
    )
    style.configure("Sidebar.FocusEyebrow.TLabel", font=(FONT_UI_FAMILY, 9))
    style.configure("Archive.FocusNav.TButton", font=FONT_UI_SMALL)
    style.configure("Archive.FocusNavActive.TButton", font=FONT_UI_SMALL)

    style.configure("Transport.TButton", background=THEME["panel"])
    style.map(
        "Transport.TButton",
        background=[
            (state, THEME["panel"])
            for state in ("active", "pressed", "focus", "disabled")
        ],
    )
    for role in ("Player.Media.FocusQuiet.TButton", "Player.Media.FocusNav.TButton"):
        style.configure(role, background=THEME["panel"])
        style.map(
            role,
            background=[
                (state, THEME["panel"])
                for state in ("active", "pressed", "focus", "disabled")
            ],
        )
    style.configure(
        "Player.Media.FocusNav.TButton",
        font=(FONT_UI_FAMILY, 13, "bold"),
        foreground=THEME["text"],
        anchor="w",
        padding=(2, 4),
    )
    style.configure(
        "Player.PanelMuted.TLabel",
        background=THEME["panel"],
        foreground=THEME["muted"],
        font=FONT_UI_SMALL,
    )

    # Resolve shared action metrics last; surface aliases only choose backgrounds.
    apply_button_metrics(root, style)
