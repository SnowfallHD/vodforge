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
        brand = ttk.Frame(body, style="FocusShell.TFrame")
        brand.grid(row=0, column=0, pady=(0, 10))
        for word, color in (("VOD", THEME["accent"]), ("Forge", THEME["text"])):
            ttk.Label(
                brand, text=word, foreground=color, font=(FONT_UI_FAMILY, 23, "bold")
            ).pack(side="left")
        ttk.Label(
            body,
            text="What’s new in VODForge",
            style="FocusTitle.TLabel",
            anchor="center",
        ).grid(row=1, column=0, sticky="ew", pady=(0, 18))
        self.preview = tk.Canvas(
            body,
            bg=THEME["bg"],
            width=1,
            height=1,
            highlightthickness=1,
            highlightbackground=THEME["surface_2"],
        )
        self.preview.grid(row=2, column=0, sticky="nsew")
        self.image_item = self.preview.create_image(0, 0, anchor="center")
        self.source_image: Image.Image | None = None
        self.photo: ImageTk.PhotoImage | None = None
        self.paint_timer: str | None = None
        self.paint_signature: tuple | None = None
        self.preview.bind("<Configure>", lambda _e: self._schedule_preview())
        assert self.surface.status is not None
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
        self.skip = ttk.Button(actions, text="Not now", command=self.close)
        self.back = ttk.Button(
            actions, text="Back", command=lambda: self.render(self.index - 1)
        )
        self.next = ttk.Button(
            actions, text="Next", style="Accent.TButton", command=self.advance
        )
        for control in (self.skip, self.back, self.next):
            control.pack(side="left", padx=5)
        self.controls = (self.skip, self.back, self.next)
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
        self._schedule_preview()
        self.page.configure(text=f"{index + 1} of {len(self.highlights)}")
        self.back.state(["disabled"] if index == 0 else ["!disabled"])
        self.next.configure(
            text="Done" if index == len(self.highlights) - 1 else "Next"
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
        self.preview.coords(
            self.image_item,
            self.preview.winfo_width() / 2,
            self.preview.winfo_height() / 2,
        )

    def advance(self) -> None:
        if self.index == len(self.highlights) - 1:
            self.close()
        else:
            self.render(self.index + 1)

    def resize(self, event: tk.Event | None = None) -> None:
        if event is not None and event.widget is not self.parent:
            return
        width, height = (
            min(590, self.parent.winfo_width() - 40),
            min(650, self.parent.winfo_height() - 40),
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
