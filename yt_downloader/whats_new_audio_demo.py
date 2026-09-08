"""Show the actual shared format field and expanded menu inside the carousel."""

import tkinter as tk

from .models import OutputType
from .ui_theme import THEME
from .ui_widgets import ChoiceDropdown, ChoiceMenu


class _ExpandedDemoField(ChoiceDropdown):
    """Its menu is already embedded; do not create a duplicate floating menu."""

    def open_popover(self) -> None:
        return


class OriginalAudioDemo(tk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, bg=THEME["bg"], width=300, height=210)
        self.pack_propagate(False)
        self.preferred_width = 300
        self.value = tk.StringVar(self, value=OutputType.ORIGINAL.value)
        values = tuple(kind.value for kind in OutputType)
        self.field = _ExpandedDemoField(
            self, textvariable=self.value, values=values, width=22
        )
        self.field.pack(fill="x")
        self.menu = ChoiceMenu(self, values)
        self.menu.selection_set(values.index(OutputType.ORIGINAL.value))
        self.menu.pack(fill="x", pady=(4, 0))
        self.menu.bind(
            "<ButtonRelease-1>",
            lambda _e: self.value.set(self.menu.get(self.menu.selected)),
        )
