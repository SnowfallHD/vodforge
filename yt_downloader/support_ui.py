"""Native explicit-submission forms. Own layout, consent snapshot and delivery feedback."""

from __future__ import annotations

import json
import platform
import queue
import threading
import tkinter as tk
import uuid
from collections.abc import Callable
from functools import partial
from tkinter import ttk
from typing import Any

from .modal_backdrop import ModalBackdrop
from .support_diagnostics import FailureContext
from .support_transport import SubmissionError, SupportTransport, VerificationRequired
from .ui_chrome import RoundedFieldBorder
from .ui_theme import FONT_UI, THEME
from .ui_widgets import (
    ActionDialogSurface,
    ChoiceDropdown,
    ModernCheckbox,
    ProductEntry,
)
from .version import __version__

REASONS = (
    "Download problem",
    "Playback problem",
    "Interface problem",
    "Suggestion",
    "Other",
)


class SupportPanel:
    def __init__(
        self,
        parent: tk.Misc,
        *,
        kind: str,
        transport: SupportTransport,
        closed: Callable[[], None],
        context: FailureContext | None = None,
    ):
        self.parent, self.kind, self.transport = parent, kind, transport
        self.on_closed, self.context = closed, context
        self.closed = False
        self.busy = False
        self.sent = False
        self.receipts: queue.Queue[tuple[bool, str]] = queue.Queue()
        self.request_id = str(uuid.uuid4())
        self.last_payload = ""
        self._disabled_inputs: list[tuple[Any, str]] = []
        self.timer: str | None = None
        self.previous_focus = parent.focus_get()
        self.backdrop = ModalBackdrop(parent)
        self.frame = tk.Frame(
            parent,
            bg=THEME["bg"],
            highlightthickness=1,
            highlightbackground=THEME["surface_2"],
            highlightcolor=THEME["surface_2"],
        )
        self.surface = ActionDialogSurface(
            self.frame, protect_status=True, padx=24, pady=18
        )
        body = self.surface.body
        body.rowconfigure(4, weight=1)
        ttk.Label(
            body,
            text="Help & feedback"
            if kind == "feedback"
            else "How’s VODForge working for you?",
            style="FocusTitle.TLabel",
            wraplength=500,
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Label(
            body,
            text="Send a focused report directly to VODForge. This does not enable analytics."
            if kind == "feedback"
            else "Your honest rating helps us improve VODForge.",
            style="Muted.TLabel",
            wraplength=490,
        ).grid(row=1, column=0, sticky="w", pady=(0, 12))
        self.reason = tk.StringVar(parent, REASONS[0] if context else REASONS[-1])
        self.stars = tk.IntVar(parent, 0)
        self.name = tk.StringVar(parent, "")
        self.email = tk.StringVar(parent, "")
        self.reply = tk.BooleanVar(parent, False)
        self.diagnostics = tk.BooleanVar(parent, False)
        self.video_url = tk.BooleanVar(parent, False)
        self.publish = tk.BooleanVar(parent, False)
        if kind == "feedback":
            ChoiceDropdown(
                body, textvariable=self.reason, values=REASONS, state="readonly"
            ).grid(row=2, column=0, sticky="ew", pady=(0, 10))
        else:
            star_row = ttk.Frame(body, style="FocusShell.TFrame")
            star_row.grid(row=2, column=0, sticky="w", pady=(0, 8))
            self.star_buttons = []
            for n in range(1, 6):
                button = ttk.Button(
                    star_row,
                    text="☆",
                    width=3,
                    command=partial(self._stars, n),
                )
                button.pack(side="left", padx=3)
                self.star_buttons.append(button)
        ttk.Label(
            body,
            text="Message" if kind == "feedback" else "Comment (optional)",
            style="FocusEyebrow.TLabel",
        ).grid(row=3, column=0, sticky="w")
        shell = tk.Frame(body, bg=THEME["surface"], bd=0)
        shell.grid(row=4, column=0, sticky="nsew", pady=(5, 3))
        shell.rowconfigure(0, weight=1)
        shell.columnconfigure(0, weight=1)
        self.chrome = RoundedFieldBorder(shell)
        self.message = tk.Text(
            shell,
            height=4,
            width=1,
            wrap="word",
            bg=THEME["surface"],
            fg=THEME["text"],
            insertbackground=THEME["text"],
            bd=0,
            highlightthickness=0,
            font=FONT_UI,
        )
        self.message.grid(row=0, column=0, sticky="nsew", padx=12, pady=9)
        self.counter = ttk.Label(body, style="Muted.TLabel")
        self.counter.grid(row=5, column=0, sticky="e")
        self.message.bind("<<Modified>>", self._count)
        self._count()
        options = ttk.Frame(body, style="FocusShell.TFrame")
        options.grid(row=6, column=0, sticky="ew", pady=(6, 0))
        options.columnconfigure(0, weight=1)
        if kind == "feedback":
            ModernCheckbox(
                options,
                text="I’d like a reply",
                variable=self.reply,
                command=self._reply_changed,
            ).grid(row=0, column=0, sticky="w")
            self.email_entry = ProductEntry(options, textvariable=self.email)
            self.email_hint = ttk.Label(
                options, text="Reply email (optional)", style="Muted.TLabel"
            )
            if context:
                ModernCheckbox(
                    options,
                    text="Include recent diagnostics",
                    variable=self.diagnostics,
                ).grid(row=3, column=0, sticky="w", pady=(6, 0))
                ttk.Button(
                    options, text="Review diagnostics", command=self._review_diagnostics
                ).grid(row=3, column=1, sticky="e")
                if context.video_url:
                    ModernCheckbox(
                        options,
                        text="Include the public video URL",
                        variable=self.video_url,
                    ).grid(row=4, column=0, columnspan=2, sticky="w", pady=3)
            else:
                ttk.Label(
                    options,
                    text="No recent failed-run diagnostics available.",
                    style="Muted.TLabel",
                ).grid(row=3, column=0, sticky="w", pady=6)
        else:
            ttk.Label(
                options,
                text="Display name (optional; otherwise Anonymous)",
                style="Muted.TLabel",
            ).grid(row=0, column=0, sticky="w")
            ProductEntry(options, textvariable=self.name).grid(
                row=1, column=0, sticky="ew", pady=5
            )
            ModernCheckbox(
                options,
                text="You may publish my review and display name as a testimonial.",
                variable=self.publish,
            ).grid(row=2, column=0, sticky="w", pady=5)
        if self.surface.status is None:
            raise RuntimeError("Support forms require protected status.")
        self.status = ttk.Label(
            self.surface.status,
            text="No logs, cookies, or credentials are sent automatically."
            if kind == "feedback"
            else "Your review stays private unless you permit publication.",
            style="Muted.TLabel",
            wraplength=490,
        )
        self.status.pack(fill="x")
        footer = self.surface.footer
        self.cancel = ttk.Button(
            footer,
            text="Cancel" if kind == "feedback" else "No thanks",
            command=self.close,
        )
        self.cancel.pack(side="left")
        self.send = ttk.Button(
            footer,
            text="Send feedback" if kind == "feedback" else "Submit rating",
            style="Accent.TButton",
            command=self._submit,
        )
        self.send.pack(side="right")
        self.frame.bind("<Escape>", lambda _e: self.close())
        for widget in self._descendants(self.frame):
            widget.bind("<Escape>", lambda _e: self.close(), add="+")
        self.resize_binding = parent.bind("<Configure>", self._resize, add="+")
        self.frame.bind("<Configure>", lambda _e: self.backdrop.refresh(self.frame))
        self.frame.bind("<Destroy>", lambda _e: self.backdrop.close())
        self._resize()
        self.frame.lift()
        self.frame.grab_set()
        self.message.focus_set()

    @staticmethod
    def _descendants(widget: tk.Misc) -> Any:
        for child in widget.winfo_children():
            yield child
            yield from SupportPanel._descendants(child)

    def _resize(self, event: tk.Event | None = None) -> None:
        if event is not None and event.widget is not self.parent:
            return
        self.frame.place(
            relx=0.5,
            rely=0.5,
            anchor="center",
            width=min(580, max(340, self.parent.winfo_width() - 36)),
            height=min(
                510 if self.kind == "feedback" else 460,
                max(400, self.parent.winfo_height() - 36),
            ),
        )
        self.backdrop.refresh(self.frame)

    def _count(self, _event: tk.Event | None = None) -> None:
        limit = 2000 if self.kind == "feedback" else 1000
        value = self.message.get("1.0", "end-1c")
        if len(value) > limit:
            self.message.delete(f"1.0+{limit}c", "end-1c")
        self.counter.configure(text=f"{min(len(value), limit):,} / {limit:,}")
        self.message.edit_modified(False)

    def _stars(self, value: int) -> None:
        self.stars.set(value)
        for n, button in enumerate(self.star_buttons, 1):
            button.configure(text="★" if n <= value else "☆")

    def _reply_changed(self) -> None:
        if self.reply.get():
            self.email_hint.grid(row=1, column=0, sticky="w")
            self.email_entry.grid(row=2, column=0, columnspan=2, sticky="ew", pady=3)
        else:
            self.email_hint.grid_remove()
            self.email_entry.grid_remove()

    def _review_diagnostics(self) -> None:
        if not self.context:
            return
        # Document surface, not an expanding form: fixed actions and scrollable text.
        popup = tk.Toplevel(self.parent)
        popup.title("Review diagnostics")
        popup.transient(self.parent.winfo_toplevel())
        surface = ActionDialogSurface(popup)
        text = tk.Text(
            surface.body,
            wrap="word",
            width=65,
            height=18,
            bg=THEME["surface"],
            fg=THEME["text"],
            bd=0,
            highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(surface.body, orient="vertical", command=text.yview)
        scrollbar.pack(side="right", fill="y")
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(fill="both", expand=True)
        text.insert(
            "1.0",
            self.context.diagnostics
            + (
                "\n\nOptional video URL: " + self.context.video_url
                if self.context.video_url
                else ""
            ),
        )
        text.configure(state="disabled")

        def close() -> None:
            popup.destroy()
            if not self.closed:
                self.frame.grab_set()
                self.message.focus_set()

        ttk.Button(surface.footer, text="Done", command=close).pack(side="right")
        popup.protocol("WM_DELETE_WINDOW", close)
        popup.bind("<Escape>", lambda _e: close())
        popup.grab_set()

    def payload(self) -> dict[str, Any]:
        common = {"app_version": __version__, "platform": platform.system()}
        message = self.message.get("1.0", "end-1c").strip()
        if self.kind == "feedback":
            email = self.email.get().strip() if self.reply.get() else ""
            if not message:
                raise ValueError("Please enter a message.")
            if len(email) > 254 or (
                email and ("@" not in email or any(c.isspace() for c in email))
            ):
                raise ValueError("Please check your reply email.")
            return {
                **common,
                "reason": self.reason.get(),
                "message": message,
                "reply_email": email,
                "include_diagnostics": self.diagnostics.get(),
                "diagnostics": self.context.diagnostics
                if self.context and self.diagnostics.get()
                else "",
                "include_video_url": self.video_url.get(),
                "video_url": self.context.video_url
                if self.context and self.video_url.get()
                else "",
            }
        if not 1 <= self.stars.get() <= 5:
            raise ValueError("Choose a rating from 1 to 5 stars.")
        if len(self.name.get()) > 80:
            raise ValueError("Please keep your display name to 80 characters.")
        return {
            **common,
            "stars": self.stars.get(),
            "comment": message,
            "display_name": self.name.get().strip() or "Anonymous",
            "publication_consent": self.publish.get(),
        }

    def _submit(self) -> None:
        if self.busy or self.sent:
            return
        try:
            payload = self.payload()
        except ValueError as exc:
            self.status.configure(text=str(exc))
            return
        encoded = json.dumps(payload, sort_keys=True)
        if self.last_payload and encoded != self.last_payload:
            self.request_id = str(uuid.uuid4())
        self.last_payload = encoded
        self.busy = True
        for widget in self._descendants(self.surface.body):
            if isinstance(
                widget, (ttk.Entry, ttk.Button, tk.Text, ModernCheckbox, ChoiceDropdown)
            ):
                try:
                    old = (
                        widget.configure("state")
                        if isinstance(widget, (ModernCheckbox, ChoiceDropdown))
                        else widget.cget("state")
                    )
                    if isinstance(old, tuple):
                        old = old[-1]
                    self._disabled_inputs.append((widget, str(old)))
                    widget.configure(state="disabled")
                except tk.TclError:
                    pass
        self.send.state(["disabled"])
        self.cancel.state(["disabled"])
        self.status.configure(text="Sending…")
        request_id = self.request_id

        def deliver() -> None:
            try:
                self.receipts.put(
                    (True, self.transport.submit(self.kind, payload, request_id))
                )
            except VerificationRequired as exc:
                self.receipts.put((False, str(exc)))
            except (SubmissionError, OSError, ValueError, TypeError, KeyError):
                self.receipts.put(
                    (
                        False,
                        "Could not confirm delivery. Your text is preserved; please try again later.",
                    )
                )

        threading.Thread(
            target=deliver, daemon=True, name="vodforge-user-submission"
        ).start()
        self.timer = self.parent.after(100, self._poll)

    def _poll(self) -> None:
        self.timer = None
        if self.closed:
            return
        try:
            ok, result = self.receipts.get_nowait()
        except queue.Empty:
            self.timer = self.parent.after(100, self._poll)
            return
        self.busy = False
        for widget, state in self._disabled_inputs:
            if widget.winfo_exists():
                widget.configure(state=state)
        self._disabled_inputs.clear()
        self.cancel.state(["!disabled"])
        if ok:
            self.sent = True
            self.status.configure(text=f"Thank you. Received as {result}.")
            self.cancel.configure(text="Done")
        else:
            self.status.configure(text=result)
            self.send.state(["!disabled"])

    def close(self, *, force: bool = False) -> None:
        if self.closed or (self.busy and not force):
            return
        self.closed = True
        if self.timer:
            self.parent.after_cancel(self.timer)
        self.parent.unbind("<Configure>", self.resize_binding)
        self.frame.grab_release()
        self.frame.destroy()
        self.backdrop.close()
        if self.previous_focus is not None and self.previous_focus.winfo_exists():
            self.previous_focus.focus_set()
        self.on_closed()
