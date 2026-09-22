"""Application-owned consent surface. No OS popup or telemetry authority."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from functools import partial
from tkinter import ttk
from typing import TypedDict, cast

from .modal_backdrop import ModalBackdrop
from .ui_button_contract import ProductButton
from .ui_layout import window_logical_metrics
from .ui_theme import FONT_UI_FAMILY, FONT_UI_SMALL, THEME
from .ui_widgets import ActionDialogSurface


class _Stroke(TypedDict):
    fill: str
    width: int


class AnalyticsConsentPanel:
    def __init__(
        self,
        parent: tk.Misc,
        choose: Callable[[bool], None],
        privacy: Callable[[], object],
    ) -> None:
        self.parent = parent
        self._metrics = window_logical_metrics(parent)
        px = self._metrics.px
        self.choose = choose
        self.closed = False
        self.previous_focus = parent.focus_get()
        self.backdrop = ModalBackdrop(parent)
        self.frame = tk.Frame(
            parent,
            bg=THEME["bg"],
            highlightbackground=THEME["surface_2"],
            highlightcolor=THEME["surface_2"],
            highlightthickness=px(1),
            takefocus=True,
        )
        surface = ActionDialogSurface(
            self.frame, padx=28, pady=26, allow_body_scroll=self._metrics.scale > 1
        )
        self.surface = surface
        brand = ttk.Frame(surface.body, style="FocusShell.TFrame")
        brand.pack(pady=(0, px(20)))
        ttk.Label(
            brand,
            text="VOD",
            foreground=THEME["accent"],
            font=self._metrics.font((FONT_UI_FAMILY, 26, "bold")),
        ).pack(side="left")
        ttk.Label(
            brand, text="Forge", font=self._metrics.font((FONT_UI_FAMILY, 26, "bold"))
        ).pack(side="left")
        ttk.Label(
            surface.body,
            text="Help improve VODForge",
            style="FocusTitle.TLabel",
            font=self._metrics.font((FONT_UI_FAMILY, 18, "bold")),
            anchor="center",
        ).pack(fill="x", pady=(0, px(10)))
        benefits = ttk.Frame(surface.body, style="FocusShell.TFrame")
        benefits.pack(fill="x", pady=(px(12), px(4)))
        self.benefit_labels = []
        self._benefit_icons = []
        self._benefit_columns = 4
        for index, text in enumerate(
            (
                "No personal information",
                "Fix errors without support",
                "Improve the platform",
                "Turn off anytime in Settings",
            )
        ):
            benefits.columnconfigure(index, weight=1, uniform="benefit")
            icon = tk.Canvas(
                benefits,
                width=px(36),
                height=px(36),
                bg=THEME["bg"],
                highlightthickness=0,
            )
            icon.grid(row=0, column=index, pady=(0, px(10)))
            self._benefit_icons.append(icon)
            stroke: _Stroke = {"fill": THEME["accent"], "width": px(2)}
            if index == 0:
                icon.create_line(
                    [18, 3, 30, 8, 28, 23, 18, 32, 8, 23, 6, 8, 18, 3], **stroke
                )
                icon.create_line([12, 17, 16, 21, 24, 13], **stroke)
            elif index == 1:
                icon.create_line(
                    [3, 19, 10, 19, 14, 8, 21, 29, 26, 17, 33, 17], **stroke
                )
            elif index == 2:
                icon.create_line(6, 29, 6, 22, **stroke)
                icon.create_line(16, 29, 16, 16, **stroke)
                icon.create_line(26, 29, 26, 8, **stroke)
                icon.create_line([5, 14, 26, 3, 26, 8], **stroke)
            else:
                for y, x in ((9, 12), (18, 24), (27, 16)):
                    icon.create_line(4, y, 32, y, **stroke)
                    icon.create_oval(
                        x - 3,
                        y - 3,
                        x + 3,
                        y + 3,
                        fill=THEME["bg"],
                        outline=THEME["accent"],
                        width=px(2),
                    )
            # Existing vector paths are canonical; scale their coordinates once.
            icon.scale("all", 0, 0, self._metrics.scale, self._metrics.scale)
            label = ttk.Label(
                benefits,
                text=text,
                style="Muted.TLabel",
                font=self._metrics.font(FONT_UI_SMALL),
                justify="center",
                anchor="n",
                wraplength=px(80),
            )
            label.grid(row=1, column=index, sticky="new", padx=px(6))
            label.bind("<Configure>", self._fit_benefit_text)
            self.benefit_labels.append(label)
        font = self._metrics.font(FONT_UI_SMALL)
        self._benefit_min_width = max(
            int(self.frame.tk.call("font", "measure", font, word))
            for label in self.benefit_labels
            for word in str(label.cget("text")).split()
        ) + px(24)
        benefits.bind("<Configure>", self._layout_benefits, add="+")
        actions = ttk.Frame(surface.footer, style="FocusShell.TFrame")
        actions.pack(anchor="center")
        self.allow = ProductButton(
            actions,
            text="Share analytics",
            style="Accent.TButton",
            command=lambda: self.finish(True),
        )
        self.deny = ProductButton(
            actions, text="Not now", command=lambda: self.finish(False)
        )
        self.privacy = tk.Label(
            surface.footer,
            text="Privacy details",
            background=THEME["bg"],
            foreground=THEME["muted"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            takefocus=True,
            cursor="hand2",
            font=self._metrics.font((FONT_UI_FAMILY, 11)),
        )
        self.privacy.bind("<Button-1>", lambda _event: privacy())
        self.privacy.bind("<Return>", lambda _event: privacy())
        self.privacy.bind("<space>", lambda _event: privacy())
        self.privacy.bind(
            "<FocusIn>",
            lambda _event: self.privacy.configure(
                foreground=THEME["accent"],
                font=self._metrics.font((FONT_UI_FAMILY, 11, "underline")),
            ),
        )
        self.privacy.bind(
            "<FocusOut>",
            lambda _event: self.privacy.configure(
                foreground=THEME["muted"], font=self._metrics.font((FONT_UI_FAMILY, 11))
            ),
        )
        for index, button in enumerate((self.allow, self.deny)):
            button.grid(row=0, column=index, padx=px(6))
        self.privacy.pack(anchor="center", pady=(px(10), 0))
        self.controls = (self.allow, self.deny, self.privacy)
        for index, control in enumerate(self.controls):
            control.bind("<Tab>", partial(self._focus_event, (index + 1) % 3))
            control.bind("<Shift-Tab>", partial(self._focus_event, (index - 1) % 3))
            control.bind("<Escape>", lambda _e: self.finish(False))
        self.frame.bind("<Escape>", lambda _e: self.finish(False))
        self.frame.bind("<Tab>", lambda _e: self.focus_control(0))
        self.resize_binding = parent.bind("<Configure>", self.resize, add="+")
        self.frame.bind("<Configure>", lambda _event: self.backdrop.refresh(self.frame))
        self.frame.bind("<Destroy>", lambda _event: self.backdrop.close())
        self.resize()
        self.frame.lift()
        self.frame.grab_set()
        self.frame.focus_set()

    def focus_control(self, index: int) -> str:
        self.controls[index].focus_set()
        return "break"

    def _focus_event(self, index: int, _event: tk.Event) -> str:
        return self.focus_control(index)

    def resize(self, event: tk.Event | None = None) -> None:
        if event is not None and event.widget is not self.parent:
            return
        px = self._metrics.px
        width = min(px(620), max(1, self.parent.winfo_width() - px(48)))
        if self._metrics.scale > 1:
            height = max(1, self.parent.winfo_height() - px(48))
            self.frame.place(
                relx=0.5, rely=0.5, anchor="center", width=width, height=height
            )
        else:
            self.frame.place(relx=0.5, rely=0.5, anchor="center", width=width)
        self.backdrop.refresh(self.frame)

    def _layout_benefits(self, event: tk.Event) -> None:
        columns = 4 if event.width >= 4 * self._benefit_min_width else 2
        if columns == self._benefit_columns:
            return
        self._benefit_columns = columns
        for column in range(4):
            event.widget.columnconfigure(
                column,
                weight=int(column < columns),
                uniform="benefit" if column < columns else "",
            )
        for index, (icon, label) in enumerate(
            zip(self._benefit_icons, self.benefit_labels)
        ):
            row, column = divmod(index, columns)
            icon.grid_configure(row=2 * row, column=column)
            label.grid_configure(row=2 * row + 1, column=column)

    def _fit_benefit_text(self, event: tk.Event) -> None:
        # Use actual allocated width, including grid gaps and font edge bearings.
        width = max(1, event.width - self._metrics.px(8))
        if int(float(event.widget.cget("wraplength"))) != width:
            cast(ttk.Label, event.widget).configure(wraplength=width)

    def finish(self, enabled: bool) -> str:
        if self.closed:
            return "break"
        self.closed = True
        self.frame.grab_release()
        self.parent.unbind("<Configure>", self.resize_binding)
        self.frame.destroy()
        if self.previous_focus is not None and self.previous_focus.winfo_exists():
            self.previous_focus.focus_set()
        self.choose(enabled)
        return "break"
