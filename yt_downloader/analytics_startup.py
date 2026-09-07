"""First-session welcome and permission UI; never owns analytics events."""

from __future__ import annotations

import secrets
import threading
import time
import tkinter as tk
import webbrowser
from collections.abc import Callable
from tkinter import ttk

from .analytics_consent import AnalyticsConsentOwner
from .cloud_funnel import (
    load_or_create_installation_state,
    mark_attribution_claim_issued,
    mark_attribution_claim_opened,
)
from .install_attribution import cancel_claim, issue_claim
from .telemetry_policy import production_telemetry_allowed
from .ui_widgets import ActionDialogSurface


class AnalyticsStartup:
    def __init__(
        self,
        root: tk.Misc,
        owner: AnalyticsConsentOwner,
        variable: tk.BooleanVar,
        changed: Callable[[bool], None],
    ) -> None:
        self.root, self.owner, self.variable, self.changed = (
            root,
            owner,
            variable,
            changed,
        )
        self.syncing = False
        self.done = threading.Event()
        self.mode = "unknown"
        self.attempts = 0
        self.region_deadline = float("inf")
        self.permission_presented = False
        self.ticket = secrets.token_urlsafe(32)
        self.ticket_deadline = time.monotonic() + 120
        self.authorizing = threading.Lock()
        self.closed = False
        initial = load_or_create_installation_state(
            owner.path.parent / "installation.json"
        )
        self.link_eligible = not (
            initial.attribution_claim_opened or initial.first_launch_confirmed
        )
        self.variable.trace_add("write", self._choice)
        self._sync()

    def _sync(self) -> None:
        self.syncing = True
        try:
            self.variable.set(self.owner.allowed)
        finally:
            self.syncing = False

    def _choice(self, *_args: object) -> None:
        if not self.syncing:
            self.owner.choose(self.variable.get())
            if self.owner.allowed:
                threading.Thread(target=self._authorize_ticket, daemon=True).start()
            else:
                threading.Thread(
                    target=lambda: cancel_claim(self.ticket), daemon=True
                ).start()
            self.changed(self.owner.allowed)

    def start(self) -> None:
        if self.closed or self.attempts or not production_telemetry_allowed():
            return
        self.attempts += 1
        self.region_deadline = time.monotonic() + 2.5
        self.done.clear()
        if self.attempts == 1:
            timer = threading.Timer(2.5, self._open_welcome)
            timer.daemon = True
            timer.start()
        threading.Thread(
            target=self._prepare, daemon=True, name="vodforge-welcome"
        ).start()
        self.root.after(100, self._poll)

    def _prepare(self) -> None:
        try:
            for _ in range(2):
                self.mode = self.owner.resolve(deadline=self.region_deadline)
                if self.mode != "unknown" or time.monotonic() >= self.region_deadline:
                    break
            self._authorize_ticket()
        except (OSError, ValueError):
            self.mode = "unknown"
        finally:
            self._open_welcome()
            self.done.set()

    def _open_welcome(self) -> None:
        if (
            self.closed
            or not production_telemetry_allowed()
            or not self.owner.take_welcome()
        ):
            return
        try:
            path = self.owner.path.parent / "installation.json"
            state = load_or_create_installation_state(path)
            if state.attribution_claim_opened or state.first_launch_confirmed:
                return
            mark_attribution_claim_opened(path, state.install_id)
            url = f"https://getvodforge.com/claim/#ticket={self.ticket}"
            webbrowser.open(url, new=2, autoraise=False)
        except Exception:  # noqa: BLE001 - browser adapters differ; welcome is best effort
            return

    def _authorize_ticket(self) -> None:
        if not self.authorizing.acquire(blocking=False):
            return
        try:
            if (
                self.closed
                or not self.link_eligible
                or not self.owner.allowed
                or time.monotonic() > self.ticket_deadline
            ):
                return
            path = self.owner.path.parent / "installation.json"
            state = load_or_create_installation_state(path)
            if (
                state.attribution_claim_confirmed
                or state.attribution_claim_token == self.ticket
            ):
                return
            if issue_claim(state.install_id, self.ticket):
                if not self.owner.allowed or self.closed:
                    cancel_claim(self.ticket)
                    return
                mark_attribution_claim_issued(path, state.install_id, self.ticket)
        finally:
            self.authorizing.release()

    def close(self) -> None:
        self.closed = True

    def _poll(self) -> None:
        if self.closed or self.permission_presented:
            return
        if not self.done.is_set() and time.monotonic() < self.region_deadline:
            self.root.after(100, self._poll)
            return
        self.permission_presented = True
        self._sync()
        self.changed(self.owner.allowed)
        state = self.owner.snapshot()
        if (
            self.mode in {"opt-in", "unknown"}
            and not state.get("choice")
            and not state.get("prompted")
        ):
            self.owner.update(prompted=True)
            self._prompt()

    def _prompt(self) -> None:
        popup = tk.Toplevel(self.root)
        popup.title("Help improve VODForge?")
        popup.resizable(False, False)
        surface = ActionDialogSurface(popup)
        body = surface.body
        ttk.Label(body, text="Help improve VODForge?", style="FocusTitle.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            body,
            text="Share anonymous analytics about installations, app versions, feature use, and errors. Your downloads, URLs, filenames, and personal content aren’t included.",
            wraplength=420,
        ).pack(anchor="w", pady=16)
        ttk.Label(body, text="You can change this anytime in Settings.").pack(
            anchor="w"
        )
        actions = surface.footer

        def choose(enabled: bool) -> None:
            self.variable.set(enabled)
            popup.destroy()

        popup.protocol("WM_DELETE_WINDOW", lambda: choose(False))
        ttk.Button(actions, text="Not now", command=lambda: choose(False)).pack(
            side="left"
        )
        ttk.Button(actions, text="Allow analytics", command=lambda: choose(True)).pack(
            side="right"
        )
        ttk.Button(
            body,
            text="Privacy details",
            command=lambda: webbrowser.open("https://getvodforge.com/privacy/"),
        ).pack(anchor="w", pady=(8, 0))
