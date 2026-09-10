"""Transient Run Deck hover navigation, backed by the existing run projection."""

import tkinter as tk
from collections.abc import Callable
from typing import Any

from .choice_popover import ChoicePopover
from .ui_theme import THEME
from .ui_widgets import ChoiceMenu, SleekScrollbar


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
        menu = ChoiceMenu(popup, labels)
        menu.rows = min(5, len(labels))
        menu.configure(width=400, height=menu.rows * menu.row_height + 12)
        menu.pack(side="left", fill="both", expand=True)
        scrollbar = None

        def scroll(action: str, value: str, units: str = "units") -> None:
            if action == "moveto":
                top = round(float(value) * len(labels))
            else:
                top = menu.top + int(value) * (menu.rows if units == "pages" else 1)
            menu.top = max(0, min(len(labels) - menu.rows, top))
            menu.selected = max(menu.top, min(menu.selected, menu.top + menu.rows - 1))
            menu._paint()
            if scrollbar is not None:
                scrollbar.set(
                    menu.top / len(labels), (menu.top + menu.rows) / len(labels)
                )

        if len(labels) > menu.rows:
            scrollbar = SleekScrollbar(popup, command=scroll)
            scrollbar.pack(side="right", fill="y")
            scroll("moveto", "0")

        def wheel(event: tk.Event) -> str:
            direction = -1 if event.num == 4 or event.delta > 0 else 1
            scroll("scroll", str(direction))
            return "break"

        for widget in (menu, scrollbar):
            if widget is not None:
                for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                    widget.bind(sequence, wheel)

        def choose(_event: object) -> None:
            index = menu.selected
            self.close()
            if records:
                self.select(records[index])

        menu.bind("<ButtonRelease-1>", choose)
        menu.bind("<Return>", choose)
        menu.bind("<Escape>", lambda _e: self.close())
        for widget in (popup, menu, *([scrollbar] if scrollbar is not None else [])):
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
