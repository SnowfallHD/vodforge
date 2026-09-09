"""Sequence first-run/help/review surfaces without taking domain ownership from jobs."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .engagement_state import WELCOME_SLIDES, EngagementState
from .support_diagnostics import FailureContext, failure_context
from .support_transport import SupportTransport
from .support_ui import SupportPanel
from .whats_new_ui import WhatsNewPanel


class EngagementUI:
    def __init__(
        self,
        root: tk.Misc,
        path: Path,
        *,
        ready: Callable[[], bool],
        suppress_showcase: Callable[[], None],
    ):
        self.root, self.ready, self.suppress_showcase = root, ready, suppress_showcase
        self.state = EngagementState(path)
        self.transport = SupportTransport(path.parent)
        self.panel: WhatsNewPanel | SupportPanel | None = None
        self.latest_failure: FailureContext | None = None
        self.closed = False
        self.timer: str | None = None

    @property
    def blocks_announcements(self) -> bool:
        return self.panel is not None or self.state.welcome_pending

    def start(self) -> None:
        if not self.closed and self.timer is None:
            self.timer = self.root.after(700, self._poll)

    def _poll(self) -> None:
        self.timer = None
        if self.closed:
            return
        try:
            if (
                self.panel is None
                and self.ready()
                and self.root.grab_current() is None
                and not any(
                    isinstance(child, tk.Toplevel) and child.winfo_viewable()
                    for child in self.root.winfo_children()
                )
                and self.root.focus_displayof() is not None
            ):
                if self.state.welcome_pending:
                    self.welcome()
                elif self.state.rating_pending:
                    self.review()
        except (OSError, ValueError, tk.TclError):
            pass  # Optional prompts must never break ordinary app use.
        self.start()

    def _closed(self) -> None:
        self.panel = None

    def welcome(self) -> None:
        if self.panel is not None or self.root.grab_current() is not None:
            return
        self.panel = WhatsNewPanel(
            self.root,
            WELCOME_SLIDES,
            self._closed,
            heading="Welcome to VODForge",
            finish_label="Start using VODForge",
        )
        self.state.presented_welcome()
        self.suppress_showcase()

    def feedback(self) -> None:
        if self.panel is not None or self.root.grab_current() is not None:
            return
        self.panel = SupportPanel(
            self.root,
            kind="feedback",
            transport=self.transport,
            closed=self._closed,
            context=self.latest_failure,
        )

    def review(self) -> None:
        if self.panel is not None or self.root.grab_current() is not None:
            return
        self.panel = SupportPanel(
            self.root, kind="review", transport=self.transport, closed=self._closed
        )
        self.state.presented_rating()

    def finished(self, job: Any, status: str, message: str) -> None:
        if job is None:
            return
        try:
            if status == "Completed":
                self.state.completed_download(job.run_id)
            elif status in {"Failed", "Partial"}:
                self.latest_failure = failure_context(job, message)
        except (OSError, ValueError):
            pass

    def menu(self, anchor: tk.Misc) -> None:
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(
            label="Report a problem / Send feedback",
            command=lambda: self.root.after_idle(self.feedback),
        )
        menu.add_command(
            label="Rate VODForge", command=lambda: self.root.after_idle(self.review)
        )
        menu.add_separator()
        menu.add_command(
            label="Welcome tour", command=lambda: self.root.after_idle(self.welcome)
        )
        try:
            menu.tk_popup(
                anchor.winfo_rootx(), anchor.winfo_rooty() + anchor.winfo_height()
            )
        finally:
            menu.grab_release()
            menu.destroy()

    def close(self) -> None:
        self.closed = True
        if self.timer:
            self.root.after_cancel(self.timer)
        if isinstance(self.panel, SupportPanel):
            self.panel.close(force=True)
        elif self.panel is not None:
            self.panel.close(acknowledge=False)
        self.panel = None
