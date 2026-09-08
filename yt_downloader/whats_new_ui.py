"""Local renderer for a curated, offline, native-child feature carousel."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageOps, ImageTk

from .modal_backdrop import ModalBackdrop
from .ui_theme import FONT_UI_FAMILY, THEME
from .ui_widgets import ActionDialogSurface
from .whats_new import FeatureHighlight
from .whats_new_activity_demo import ActivityDemo


class _ArrowButton(tk.Canvas):
    """Compact circular navigation owned by the showcase surface."""

    def __init__(self, parent: tk.Misc, direction: int, command: Callable[[], None]):
        super().__init__(
            parent,
            width=34,
            height=34,
            bg=THEME["bg"],
            highlightthickness=0,
            takefocus=True,
            cursor="hand2",
        )
        self.command = command
        self.disabled = False
        self.hover = False
        self.circle = self.create_oval(1, 1, 33, 33, width=1)
        points = (19, 12, 14, 17, 19, 22) if direction < 0 else (15, 12, 20, 17, 15, 22)
        self.arrow = self.create_line(
            *points, width=2, capstyle="round", joinstyle="round"
        )
        self.bind("<Button-1>", self.invoke)
        self.bind("<Return>", self.invoke)
        self.bind("<space>", self.invoke)
        self.bind("<Enter>", lambda _e: self._hover(True))
        self.bind("<Leave>", lambda _e: self._hover(False))
        self.bind("<FocusIn>", lambda _e: self.paint())
        self.bind("<FocusOut>", lambda _e: self.paint())
        self.paint()

    def _hover(self, value: bool) -> None:
        self.hover = value
        self.paint()

    def invoke(self, _event=None):
        if not self.disabled:
            self.command()
        return "break"

    def state(self, states):
        self.disabled = "disabled" in states
        self.configure(
            takefocus=not self.disabled, cursor="" if self.disabled else "hand2"
        )
        self.paint()

    def instate(self, states):
        return self.disabled if "disabled" in states else not self.disabled

    def paint(self):
        active = not self.disabled and (self.hover or self.focus_get() is self)
        self.itemconfigure(
            self.circle,
            fill=THEME["surface_2"] if active else THEME["bg"],
            outline=THEME["accent"] if active else THEME["surface_2"],
        )
        self.itemconfigure(
            self.arrow, fill=THEME["surface_2"] if self.disabled else THEME["text"]
        )


class WhatsNewPanel:
    def __init__(
        self,
        parent: tk.Misc,
        highlights: tuple[FeatureHighlight, ...],
        dismissed: Callable[[], None],
    ) -> None:
        if not highlights:
            raise ValueError("A showcase needs at least one feature")
        self.parent, self.highlights, self.dismissed = parent, highlights, dismissed
        self.index = -1
        self.activity_demo: ActivityDemo | None = None
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
            self.frame, padx=26, pady=20, protect_status=True
        )
        body = self.surface.body
        body.rowconfigure(2, weight=1)
        ttk.Label(
            body,
            text="What’s new",
            font=(FONT_UI_FAMILY, 14, "bold"),
            foreground=THEME["accent"],
            anchor="center",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 18))
        self.preview = tk.Canvas(
            body,
            bg=THEME["bg"],
            width=1,
            height=1,
            highlightthickness=0,
        )
        self.preview.grid(row=2, column=0, sticky="nsew")
        self.image_item = self.preview.create_image(0, 0, anchor="center")
        self.source_image: Image.Image | None = None
        self.photo: ImageTk.PhotoImage | None = None
        self.paint_timer: str | None = None
        self.paint_signature: tuple | None = None
        self.preview.bind("<Configure>", lambda _e: self._schedule_preview())
        assert self.surface.status is not None
        # Reserve the same caption space for every slide, including wrapped copy.
        self.surface.status.configure(height=135)
        self.surface.status.pack_propagate(False)
        self.title = ttk.Label(
            self.surface.status, style="FocusTitle.TLabel", anchor="center"
        )
        self.title.pack(fill="x")
        self.description = ttk.Label(
            self.surface.status, style="Muted.TLabel", anchor="center", justify="center"
        )
        self.description.pack(fill="x", pady=(8, 0))
        self.page = ttk.Label(
            self.surface.footer, style="Muted.TLabel", anchor="center"
        )
        self.page.pack(fill="x", pady=(0, 10))
        actions = ttk.Frame(self.surface.footer, style="FocusShell.TFrame")
        actions.pack()
        self.dismiss_button = tk.Label(
            self.frame,
            text="×",
            bg=THEME["bg"],
            fg=THEME["text"],
            font=(FONT_UI_FAMILY, 20),
            cursor="hand2",
            takefocus=True,
        )
        self.dismiss_button.bind("<Button-1>", lambda _e: self.close())
        self.dismiss_button.bind("<Return>", lambda _e: self.close())
        self.dismiss_button.bind("<space>", lambda _e: self.close())
        self.dismiss_button.place(relx=1, x=-12, y=8, anchor="ne", width=30, height=30)
        self.back = _ArrowButton(actions, -1, lambda: self.render(self.index - 1))
        self.next = _ArrowButton(actions, 1, self.advance)
        for control in (self.back, self.next):
            control.pack(side="left", padx=5)
        self.controls = (self.dismiss_button, self.back, self.next)
        for index, control in enumerate(self.controls):
            control.bind("<Tab>", lambda _e, i=index: self.focus((i + 1) % 3))
            control.bind("<Shift-Tab>", lambda _e, i=index: self.focus((i - 1) % 3))
            control.bind("<Escape>", lambda _e: self.close())
        self.frame.bind("<Escape>", lambda _e: self.close())
        self.frame.bind("<Tab>", lambda _e: self.focus(2))
        self.binding = parent.bind("<Configure>", self.resize, add="+")
        self.frame.bind("<Configure>", lambda _e: self.backdrop.refresh(self.frame))
        self.frame.bind("<Destroy>", lambda _e: self.backdrop.close())
        self.resize()
        self.render(0)
        self.frame.lift()
        self.frame.grab_set()
        self.next.focus_set()

    def focus(self, index: int) -> str:
        self.controls[index].focus_set()
        return "break"

    def render(self, index: int) -> None:
        index = max(0, min(index, len(self.highlights) - 1))
        if index == self.index:
            return
        self._cancel_transition()
        self.preview.itemconfigure(self.image_item, image="")
        if self.activity_demo is not None:
            self.activity_demo.destroy()
            self.activity_demo = None
        self.index = index
        feature = self.highlights[index]
        self.title.configure(text=feature.title)
        self.description.configure(text=feature.description)
        path = (
            Path(__file__).resolve().parents[1]
            / "assets"
            / "whats-new"
            / feature.artwork
        )
        try:
            with Image.open(path) as source:
                w, h = source.size
                x1, y1, x2, y2 = feature.crop
                self.source_image = source.crop(
                    (x1 * w, y1 * h, x2 * w, y2 * h)
                ).convert("RGB")
        except OSError:
            self.source_image = None
        self.resize()
        self._schedule_preview()
        if feature.key == "activity-mode":
            self.activity_demo = ActivityDemo(self.preview)
        self.page.configure(text=f"{index + 1} of {len(self.highlights)}")
        self.back.state(["disabled"] if index == 0 else ["!disabled"])
        self.next.state(
            ["disabled"] if index == len(self.highlights) - 1 else ["!disabled"]
        )

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
            max(1, self.preview.winfo_width() - 20),
            max(1, self.preview.winfo_height() - 20),
        )
        signature = (self.index, *size)
        if self.closed or signature == self.paint_signature:
            return
        self.paint_signature = signature
        if self.source_image is None:
            self.preview.itemconfigure(self.image_item, image="")
            return
        self.photo = ImageTk.PhotoImage(
            ImageOps.contain(self.source_image, size), master=self.frame
        )
        self.preview.itemconfigure(self.image_item, image=self.photo)
        self._cancel_transition()
        self._transition(0)

    def _cancel_transition(self) -> None:
        if self.transition_timer is not None:
            self.frame.after_cancel(self.transition_timer)
            self.transition_timer = None

    def _transition(self, step: int) -> None:
        """Translate content gently; never resize the card or its image viewport."""
        self.transition_timer = None
        if self.closed:
            return
        offset = round(18 * (1 - step / 10) ** 3)
        self.preview.coords(
            self.image_item,
            self.preview.winfo_width() / 2 + offset,
            self.preview.winfo_height() / 2,
        )
        if self.activity_demo is not None:
            self.activity_demo.place(
                x=10 + offset, y=0, relwidth=1, width=-38, relheight=1
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
            min(590, self.parent.winfo_width() - 40),
            min(560, self.parent.winfo_height() - 40),
        )
        self.frame.place(
            relx=0.5, rely=0.5, anchor="center", width=width, height=height
        )
        self.description.configure(wraplength=max(180, width - 60))
        self.title.configure(wraplength=max(180, width - 60))
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
