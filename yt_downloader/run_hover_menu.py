"""Transient Run Deck hover navigation, backed by the existing run projection."""

import tkinter as tk
from collections.abc import Callable
from tkinter import font as tkfont
from typing import Any

from .choice_popover import ChoicePopover
from .ui_chrome import RoundedFieldBorder
from .ui_theme import FONT_UI, THEME
from .ui_widgets import SleekScrollbar, bind_smooth_vertical_wheel


class RunHoverMenu:
    def __init__(
        self,
        button: tk.Widget,
        records: Callable[[], list[dict[str, Any]]],
        select: Callable[[dict[str, Any]], None],
    ) -> None:
        self.button, self.records, self.select = button, records, select
        self.popup: ChoicePopover | None = None
        self.pending: str | None = None
        button.bind("<Enter>", self.show, add="+")
        button.bind("<Leave>", self.schedule_close, add="+")
        button.bind("<ButtonPress-1>", lambda _e: self.close(), add="+")
        button.bind("<Destroy>", lambda _e: self.close(), add="+")

    def show(self, _event: object = None) -> None:
        self.cancel_close()
        if self.popup is not None:
            return
        records = self.records()
        labels = tuple(
            str(record.get("title") or "Untitled run")[:55]
            + " — "
            + str(record.get("status") or "Ready")
            for record in records
        ) or ("No runs yet",)
        popup = ChoicePopover(
            self.button, self.close, gap=0, align_right=True, bg=THEME["bg"]
        )
        self.popup = popup
        self.chrome = RoundedFieldBorder(popup)
        body = tk.Frame(popup, bg=THEME["surface"])
        body.pack(fill="both", expand=True, padx=9, pady=9)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        row_height = 31
        menu = tk.Canvas(
            body,
            width=400,
            height=min(5, len(labels)) * row_height,
            bg=THEME["surface"],
            bd=0,
            highlightthickness=0,
            yscrollincrement=1,
            takefocus=True,
        )
        self.menu = menu
        menu.grid(row=0, column=0, sticky="nsew", padx=(5, 6), pady=3)
        scrollbar = SleekScrollbar(body, command=menu.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=1)
        menu.configure(yscrollcommand=scrollbar.set)
        selected = 0
        font = tkfont.Font(font=FONT_UI)

        def paint(event: Any = None) -> None:
            width = menu.winfo_width()
            menu.delete("all")
            for index, label in enumerate(labels):
                top = index * row_height
                menu.create_rectangle(
                    0,
                    top,
                    width,
                    top + row_height - 1,
                    fill=THEME["surface_2"] if index == selected else THEME["surface"],
                    outline="",
                )
                shortened = label
                while shortened and font.measure(shortened + "…") > width - 20:
                    shortened = shortened[:-1]
                menu.create_text(
                    10,
                    top + row_height / 2,
                    anchor="w",
                    font=FONT_UI,
                    fill=THEME["text"],
                    text=label if shortened == label else shortened + "…",
                )
            menu.configure(scrollregion=(0, 0, width, len(labels) * row_height))

        def hover(event: tk.Event) -> None:
            nonlocal selected
            selected = max(
                0, min(len(labels) - 1, int(menu.canvasy(event.y) // row_height))
            )
            paint()

        def choose(_event: object) -> None:
            self.close()
            if records:
                self.select(records[selected])

        menu.bind("<Configure>", paint)
        menu.bind("<Motion>", hover)
        menu.bind("<ButtonRelease-1>", choose)
        menu.bind("<Return>", choose)
        menu.bind("<Escape>", lambda _e: self.close())
        bind_smooth_vertical_wheel(
            menu, popup, body, menu, scrollbar, mode="increments"
        )
        for widget in (popup, body, menu, scrollbar):
            widget.bind("<Enter>", lambda _e: self.cancel_close(), add="+")
            widget.bind("<Leave>", self.schedule_close, add="+")
        popup.update_idletasks()
        if not popup.reposition():
            return
        popup.lift()
        popup.update_idletasks()
        menu.focus_set()
        popup.watch()

    def cancel_close(self) -> None:
        if self.pending is not None:
            self.button.after_cancel(self.pending)
            self.pending = None

    def schedule_close(self, _event: object = None) -> None:
        self.cancel_close()
        self.pending = self.button.after(80, self.check_pointer)

    def check_pointer(self) -> None:
        self.pending = None
        hovered = self.button.winfo_containing(*self.button.winfo_pointerxy())
        if hovered is self.button:
            return
        if self.popup is not None and (
            hovered is self.popup or str(hovered).startswith(str(self.popup) + ".")
        ):
            return
        self.close()

    def close(self) -> None:
        self.cancel_close()
        popup, self.popup = self.popup, None
        if popup is not None:
            popup.destroy()
