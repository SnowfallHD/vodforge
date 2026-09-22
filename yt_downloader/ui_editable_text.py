"""A full, scrollable text section whose editing controls appear on demand."""

from __future__ import annotations

import math
import sys
import tkinter as tk
from collections.abc import Callable
from tkinter import font as tkfont

from .scene_components import scene_font
from .ui_button_contract import ProductButton
from .ui_chrome import RoundedFieldBorder
from .ui_layout import window_logical_metrics
from .ui_theme import THEME
from .ui_widgets import (
    KeyboardScope,
    SleekScrollbar,
    ToolTip,
    _tinted_ui_icon,
    bind_smooth_vertical_wheel,
)


class EditableTextSection(tk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        title: str,
        save: Callable[[str, str], bool],
        changed: Callable[[], None],
    ) -> None:
        super().__init__(master, bg=THEME["panel"], bd=0)
        self._metrics = window_logical_metrics(self)
        px = self._metrics.px
        self._save, self._changed = save, changed
        self._owner, self._value, self._caption = "", "", ""
        self._editing = False
        font = self._metrics.font(scene_font(15))
        self._font = tkfont.Font(root=self, family=font[0], size=font[1])
        header = self.header = tk.Frame(self, bg=THEME["panel"])
        header.pack(fill="x", padx=px(16), pady=(px(12), px(8)))
        tk.Label(
            header,
            text=title,
            bg=THEME["panel"],
            fg=THEME["text"],
            font=self._metrics.font(scene_font(20)),
        ).pack(side="left")
        self._copy_icon = _tinted_ui_icon(
            "copy", size=(px(16), px(16)), color=THEME["muted"], widget=self
        )
        copy = self.copy_button = ProductButton(
            header,
            text="" if self._copy_icon else "Copy",
            image=self._copy_icon or "",
            width=3 if self._copy_icon else 6,
            style="Compact.TButton",
            command=self.copy,
        )
        copy.pack(side="right")
        ToolTip(copy, "Copy full " + title.lower())
        self.edit_button = ProductButton(
            header, text="Edit", width=5, style="Compact.TButton", command=self.begin
        )
        self.edit_button.pack(side="right", padx=(0, px(8)))
        body = tk.Frame(self, bg=THEME["panel"])
        body.pack(fill="both", expand=True, padx=px(16))
        self._field_chrome = RoundedFieldBorder(body)
        self.text = tk.Text(
            body,
            width=1,
            height=3,
            wrap="word",
            bd=0,
            padx=px(10),
            pady=px(8),
            highlightthickness=0,
            highlightbackground=THEME["border"],
            highlightcolor=THEME["accent"],
            bg=THEME["bg"],
            fg=THEME["muted"],
            insertbackground=THEME["text"],
            font=self._font,
            state="disabled",
        )
        self.text.pack(side="left", fill="both", expand=True, padx=px(5), pady=px(5))
        self.text.bind("<FocusIn>", self._sync_focus_material, add="+")
        self.text.bind("<FocusOut>", self._sync_focus_material, add="+")
        scroll = SleekScrollbar(body, command=self.text.yview)
        self.scrollbar = scroll
        scroll.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=scroll.set)
        bind_smooth_vertical_wheel(self.text, scroll, mode="pixels")
        self.caption = tk.Label(
            self,
            bg=THEME["panel"],
            fg=THEME["subtle"],
            font=self._metrics.font(scene_font(11)),
            anchor="w",
        )
        self.caption.pack(fill="x", padx=px(16), pady=(px(6), px(10)))
        self.actions = tk.Frame(self, bg=THEME["panel"])
        ProductButton(
            self.actions,
            text="Save",
            width=7,
            style="Accent.TButton",
            command=self.commit,
        ).pack(side="right")
        ProductButton(
            self.actions,
            text="Cancel",
            width=7,
            style="Compact.TButton",
            command=self.cancel,
        ).pack(side="right", padx=px(8))
        self._keys: KeyboardScope | None = None
        self._sync_focus_material()

    def _sync_focus_material(self, _event: object = None) -> None:
        focused = self._editing and self.text.focus_get() is self.text
        self.text.configure(bg=THEME["focus_surface"] if focused else THEME["surface"])
        self._field_chrome.request(focused)

    def apply_theme(self) -> None:
        self._sync_focus_material()

    def present(self, owner: str, value: str, caption: str) -> None:
        if owner == self._owner and self._editing:
            return
        if (owner, value, caption) == (self._owner, self._value, self._caption):
            return
        if self._editing:
            self._finish()
        self._owner, self._value, self._caption = owner, value, caption
        self._display(value)
        self.caption.configure(text=caption)

    def _display(self, value: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        self.text.configure(state="normal" if self._editing else "disabled")

    def height_for_width(self, width: int) -> int:
        px = self._metrics.px
        available = max(px(80), width - px(64))
        lines = (
            sum(
                max(1, math.ceil(self._font.measure(line) / available))
                for line in self._value.splitlines()
            )
            or 1
        )
        # Measure styled header/footer allocations; a fixed estimate clipped
        # the provenance caption when Compact buttons acquired shared chrome.
        self.caption.configure(wraplength=max(px(80), width - px(32)))
        fixed = (
            self.header.winfo_reqheight()
            + px(20)
            + self.caption.winfo_reqheight()
            + px(16)
            + px(18)
        )
        actions = self.actions.winfo_reqheight() + px(12) if self._editing else 0
        return fixed + max(3, min(8, lines)) * self._font.metrics("linespace") + actions

    def begin(self) -> None:
        if self._editing or not self._owner:
            return
        self._editing = True
        self.text.configure(state="normal", fg=THEME["text"])
        self.edit_button.configure(state="disabled")
        self.actions.pack(
            fill="x", padx=self._metrics.px(16), pady=(0, self._metrics.px(12))
        )
        keys = {"<Escape>": self.cancel, "<Control-Return>": self.commit}
        if sys.platform == "darwin":
            keys["<Command-Return>"] = self.commit
        self._keys = KeyboardScope(self, keys, editing=tuple(keys))
        self.text.focus_set()
        self._changed()

    def _finish(self) -> None:
        self._editing = False
        if self._keys is not None:
            self._keys.close()
            self._keys = None
        self.actions.pack_forget()
        self.edit_button.configure(state="normal")
        self.text.configure(state="disabled", fg=THEME["muted"])
        self._sync_focus_material()

    def cancel(self) -> None:
        self._finish()
        self._display(self._value)
        self.caption.configure(text=self._caption)
        self._changed()

    def commit(self) -> None:
        if not self._editing:
            return
        value = self.text.get("1.0", "end-1c")
        if not self._save(self._owner, value):
            self.caption.configure(text="Could not save. Your edit is still here.")
            return
        self._value = value
        self._finish()
        self._changed()

    def copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.text.get("1.0", "end-1c"))
