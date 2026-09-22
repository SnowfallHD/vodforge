"""Local renderer for a curated, offline, native-child feature carousel."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from functools import partial
from tkinter import ttk

from .modal_backdrop import ModalBackdrop
from .ui_button_contract import ProductButton
from .ui_layout import window_logical_metrics
from .ui_theme import FONT_UI, FONT_UI_FAMILY, THEME
from .ui_widgets import ActionDialogSurface
from .whats_new import FeatureHighlight
from .whats_new_feature_preview import render_native_preview


class WhatsNewPanel:
    def __init__(
        self,
        parent: tk.Misc,
        highlights: tuple[FeatureHighlight, ...],
        dismissed: Callable[[], None],
        *,
        heading: str = "What’s new",
        finish_label: str | None = None,
        on_finish: Callable[[], None] | None = None,
    ) -> None:
        if not highlights:
            raise ValueError("A showcase needs at least one feature")
        self.parent, self.highlights, self.dismissed = parent, highlights, dismissed
        self.metrics = window_logical_metrics(parent)
        self._scroll_content = self.metrics.scale > 1
        self.index = -1
        self.finish_label = finish_label
        self.on_finish = on_finish
        self.activity_demo: tk.Widget | None = None
        self.transition_timer: str | None = None
        self.closed = False
        self.previous_focus = parent.focus_get()
        self.backdrop = ModalBackdrop(parent)
        self.frame = tk.Frame(
            parent,
            bg=THEME["bg"],
            highlightthickness=1,
            highlightbackground=THEME["surface_2"],
            highlightcolor=THEME["surface_2"],
            takefocus=True,
        )
        self.surface = ActionDialogSurface(
            self.frame,
            padx=26,
            pady=20,
            protect_status=not self._scroll_content,
            allow_body_scroll=self._scroll_content,
        )
        body = self.surface.body
        body.rowconfigure(2, weight=1)
        heading_row = ttk.Frame(body, style="FocusShell.TFrame")
        heading_row.grid(row=0, column=0, pady=(0, self.metrics.px(18)))
        self.heading_labels = []
        # Preserve the two-tone brand wherever this heading includes it.
        parts = heading.partition("VODForge")
        segments = (
            [
                (parts[0], "accent"),
                ("VOD", "accent"),
                ("Forge", "text"),
                (parts[2], "accent"),
            ]
            if parts[1]
            else [(heading, "accent")]
        )
        for text, color in segments:
            if not text:
                continue
            label = ttk.Label(
                heading_row,
                text=text,
                font=self.metrics.font((FONT_UI_FAMILY, 14, "bold")),
                foreground=THEME[color],
            )
            label.pack(side="left")
            self.heading_labels.append(label)
        self.preview = tk.Canvas(
            body,
            bg=THEME["bg"],
            width=1,
            height=self.metrics.px(230) if self._scroll_content else 1,
            highlightthickness=0,
        )
        self.preview.grid(row=2, column=0, sticky="nsew")
        self.paint_timer: str | None = None
        self.paint_signature: tuple | None = None
        self.preview.bind("<Configure>", lambda _e: self._schedule_preview())
        # At high density the document scrolls within the existing surface;
        # navigation stays protected even on a small screen.
        caption = self.surface.status
        if caption is None:
            caption = ttk.Frame(body, style="FocusShell.TFrame")
            caption.grid(row=1, column=0, sticky="ew", pady=(0, self.metrics.px(18)))
        caption.configure(height=self.metrics.px(135))
        caption.pack_propagate(False)
        self.title = self._label(caption, style="FocusTitle.TLabel", anchor="center")
        self.title.pack(fill="x")
        self.description = self._label(
            caption, style="Muted.TLabel", anchor="center", justify="center"
        )
        self.description.pack(fill="x", pady=(self.metrics.px(8), 0))
        self.page = self._label(
            self.surface.footer, style="Muted.TLabel", anchor="center"
        )
        self.page.pack(fill="x", pady=(0, self.metrics.px(10)))
        navigation = ttk.Frame(self.surface.footer, style="FocusShell.TFrame")
        self.navigation = navigation
        self._navigation_layout: tuple[bool, bool] | None = None
        navigation.pack(fill="x")
        navigation.columnconfigure(0, weight=1, uniform="flank")
        navigation.columnconfigure(2, weight=1, uniform="flank")
        actions = ttk.Frame(navigation, style="FocusShell.TFrame")
        self.navigation_actions = actions
        actions.grid(row=0, column=1)
        self.dismiss_button = tk.Label(
            self.frame,
            text="×",
            bg=THEME["bg"],
            fg=THEME["text"],
            font=self.metrics.font((FONT_UI_FAMILY, 20)),
            cursor="hand2",
            takefocus=True,
        )
        self.dismiss_button.bind("<Button-1>", lambda _e: self.close())
        self.dismiss_button.bind("<Return>", lambda _e: self.close())
        self.dismiss_button.bind("<space>", lambda _e: self.close())
        self.dismiss_button.place(
            relx=1,
            x=-self.metrics.px(12),
            y=self.metrics.px(8),
            anchor="ne",
            width=self.metrics.px(30),
            height=self.metrics.px(30),
        )
        self.back = ProductButton(
            actions,
            text="Previous",
            style="FocusQuiet.TButton",
            command=lambda: self.render(self.index - 1),
        )
        self.next = ProductButton(
            actions, text="Next", style="FocusQuiet.TButton", command=self.advance
        )
        for control in (self.back, self.next):
            control.pack(side="left", padx=self.metrics.px(5))
        self.finish_button = ProductButton(
            actions,
            text=finish_label or "Done",
            command=self.finish,
            style="Accent.TButton",
        )
        # Balance the Previous action so the final CTA, not the combined group, centers.
        self.finish_balance = ttk.Frame(
            actions,
            width=self.back.winfo_reqwidth() + self.metrics.px(10),
            height=1,
            style="FocusShell.TFrame",
        )
        self.skip_button = tk.Label(
            navigation,
            text="Skip tour",
            bg=THEME["bg"],
            fg=THEME["muted"],
            font=self.metrics.font((FONT_UI_FAMILY, 10)),
            cursor="hand2",
            takefocus=True,
            borderwidth=0,
            highlightthickness=0,
        )
        for sequence in ("<Button-1>", "<Return>", "<space>"):
            self.skip_button.bind(sequence, lambda _e: self.close())
        if finish_label:
            self.skip_button.grid(row=0, column=2, sticky="e")
        navigation.bind("<Configure>", self._arrange_navigation, add="+")
        actions.bind("<Configure>", self._arrange_navigation, add="+")
        self.controls = (self.dismiss_button, self.back, self.next) + (
            (self.skip_button, self.finish_button) if finish_label else ()
        )
        for index, focus_control in enumerate(self.controls):
            focus_control.bind("<Tab>", partial(self._cycle_focus, index, 1))
            focus_control.bind("<Shift-Tab>", partial(self._cycle_focus, index, -1))
            focus_control.bind("<Escape>", lambda _e: self.close())
        self.frame.bind("<Escape>", lambda _e: self.close())
        self.frame.bind("<Tab>", lambda _e: self.focus(2))
        self.binding = parent.bind("<Configure>", self.resize, add="+")
        self.frame.bind("<Configure>", lambda _e: self.backdrop.refresh(self.frame))
        self.frame.bind("<Destroy>", lambda _e: self.backdrop.close())
        self.resize()
        self.render(0)
        self.frame.lift()
        self.frame.grab_set()
        self.focus(2)

    def _arrange_navigation(self, _event=None) -> None:
        final = self.index == len(self.highlights) - 1
        needed = (
            self.navigation_actions.winfo_reqwidth()
            + 2 * self.skip_button.winfo_reqwidth()
            + self.metrics.px(20)
        )
        stacked = needed > self.navigation.winfo_width()
        layout = (stacked, final)
        if layout == self._navigation_layout:
            return
        self._navigation_layout = layout
        if self.finish_label and not final:
            self.skip_button.grid_configure(
                row=1 if stacked else 0,
                column=0 if stacked else 2,
                columnspan=3 if stacked else 1,
                sticky="" if stacked else "e",
                pady=(self.metrics.px(8), 0) if stacked else 0,
            )

    def _label(self, parent: tk.Misc, **options) -> ttk.Label:
        role = ttk.Style(parent).lookup(options.get("style", "TLabel"), "font")
        font = tuple(parent.tk.splitlist(role)) if role else FONT_UI
        return ttk.Label(parent, font=self.metrics.font(font), **options)

    def finish(self) -> None:
        if self.closed:
            return
        self.close()
        if self.on_finish is not None:
            self.on_finish()

    def _cycle_focus(self, index: int, direction: int, _event: tk.Event) -> str:
        for offset in range(1, len(self.controls) + 1):
            candidate = self.controls[(index + direction * offset) % len(self.controls)]
            if candidate.winfo_viewable():
                candidate.focus_set()
                break
        return "break"

    def focus(self, index: int) -> str:
        if index == 2 and self.finish_label and self.index == len(self.highlights) - 1:
            self.finish_button.focus_set()
        else:
            self.controls[index].focus_set()
        return "break"

    def render(self, index: int) -> None:
        index = max(0, min(index, len(self.highlights) - 1))
        if index == self.index:
            return
        self._cancel_transition()
        if self.activity_demo is not None:
            self.activity_demo.destroy()
            self.activity_demo = None
        self.index = index
        self._navigation_layout = None
        feature = self.highlights[index]
        self.title.configure(text=feature.title)
        self.description.configure(text=feature.description)
        self.resize()
        self._schedule_preview()
        self.activity_demo = render_native_preview(self.preview, feature.preview)
        self.page.configure(text=f"{index + 1} of {len(self.highlights)}")
        if self.surface.viewport is not None:
            self.surface.viewport.yview_moveto(0)
        self.back.state(["disabled"] if index == 0 else ["!disabled"])
        self.next.state(
            ["disabled"] if index == len(self.highlights) - 1 else ["!disabled"]
        )
        if self.finish_label:
            if index == len(self.highlights) - 1:
                self.next.pack_forget()
                self.skip_button.grid_remove()
                self.finish_button.pack(side="left", padx=self.metrics.px(8))
                self.finish_balance.pack(side="left", after=self.finish_button)
                if len(self.highlights) == 1:
                    self.page.pack_forget()
                    self.back.pack_forget()
                    self.finish_balance.pack_forget()
            else:
                self.finish_button.pack_forget()
                self.finish_balance.pack_forget()
                self.next.pack(side="left", padx=self.metrics.px(5))
                self.skip_button.grid()
        self._navigation_layout = None
        self.resize()

    def _schedule_preview(self) -> None:
        if not self.closed and self.paint_timer is None:
            self.paint_timer = self.frame.after_idle(self._paint_preview)

    def _paint_preview(self) -> None:
        self.paint_timer = None
        if self.closed:
            return
        if self.preview.winfo_width() <= 22 or self.preview.winfo_height() <= 22:
            return  # Wait for the real allocated viewport, not Tk's initial 1px size.
        size = (
            max(1, self.preview.winfo_width() - self.metrics.px(20)),
            max(1, self.preview.winfo_height() - self.metrics.px(20)),
        )
        signature = (self.index, *size)
        if self.closed or signature == self.paint_signature:
            return
        self.paint_signature = signature
        if self.activity_demo is not None:
            self._cancel_transition()
            self._transition(0)
            return

    def _cancel_transition(self) -> None:
        if self.transition_timer is not None:
            self.frame.after_cancel(self.transition_timer)
            self.transition_timer = None

    def _transition(self, step: int) -> None:
        """Translate content gently; never resize the card or its image viewport."""
        self.transition_timer = None
        if self.closed:
            return
        offset = round(self.metrics.px(18) * (1 - step / 10) ** 3)
        if self.activity_demo is not None:
            self.activity_demo.place(
                relx=0.5,
                rely=0.5,
                anchor="center",
                x=offset,
                width=min(
                    self.metrics.px(
                        getattr(self.activity_demo, "preferred_width", 470)
                    ),
                    max(1, self.preview.winfo_width() - self.metrics.px(38)),
                ),
                height=min(
                    self.metrics.px(
                        getattr(self.activity_demo, "preferred_height", 180)
                    ),
                    max(1, self.preview.winfo_height() - self.metrics.px(12)),
                ),
            )
        if step < 10:
            self.transition_timer = self.frame.after(
                16, lambda: self._transition(step + 1)
            )

    def advance(self) -> None:
        self.render(self.index + 1)

    def resize(self, event: tk.Event | None = None) -> None:
        if event is not None and event.widget is not self.parent:
            return
        width, height = (
            max(
                1,
                min(
                    self.metrics.px(590),
                    self.parent.winfo_width() - self.metrics.px(40),
                ),
            ),
            max(
                1,
                min(
                    self.metrics.px(560),
                    self.parent.winfo_height() - self.metrics.px(40),
                ),
            ),
        )
        self.frame.place(
            relx=0.5, rely=0.5, anchor="center", width=width, height=height
        )
        self.description.configure(wraplength=max(1, width - self.metrics.px(70)))
        self.title.configure(wraplength=max(1, width - self.metrics.px(70)))
        if (
            hasattr(self, "finish_balance")
            and self.finish_label
            and self.index == len(self.highlights) - 1
        ):
            required = (
                self.back.winfo_reqwidth() * 2
                + self.finish_button.winfo_reqwidth()
                + self.metrics.px(46)
            )
            if required > width - self.metrics.px(52):
                self.finish_balance.pack_forget()
            elif (
                len(self.highlights) > 1
                and self.finish_button.winfo_manager() == "pack"
            ):
                self.finish_balance.pack(side="left", after=self.finish_button)
        self._arrange_navigation()
        self.backdrop.refresh(self.frame)

    def close(self, *, acknowledge: bool = True) -> str:
        if self.closed:
            return "break"
        self.closed = True
        self._cancel_transition()
        if self.paint_timer is not None:
            self.frame.after_cancel(self.paint_timer)
            self.paint_timer = None
        self.frame.grab_release()
        self.parent.unbind("<Configure>", self.binding)
        self.frame.destroy()
        if self.previous_focus is not None and self.previous_focus.winfo_exists():
            self.previous_focus.focus_set()
        if acknowledge:
            self.dismissed()
        return "break"
