"""First-session welcome and permission UI; never owns analytics events."""

from __future__ import annotations

import secrets
import threading
import time
import tkinter as tk
import webbrowser
from collections.abc import Callable

from .analytics_consent import AnalyticsConsentOwner
from .analytics_consent_ui import AnalyticsConsentPanel
from .cloud_funnel import (
    load_or_create_installation_state,
    mark_attribution_claim_issued,
    mark_attribution_claim_opened,
)
from .install_attribution import cancel_claim, issue_claim
from .platform_services import request_window_foreground
from .telemetry_policy import telemetry_collection_allowed, telemetry_site_origin


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
        self.welcome_finished = threading.Event()
        self.welcome_opened = False
        self.consent_focus_requested = False
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
        if self.closed or self.attempts or not telemetry_collection_allowed():
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
            saved_mode = self.owner.saved_region_mode
            if saved_mode is not None:
                self.mode = saved_mode
            else:
                for _ in range(2):
                    self.mode = self.owner.resolve(deadline=self.region_deadline)
                    if (
                        self.mode != "unknown"
                        or time.monotonic() >= self.region_deadline
                    ):
                        break
                self.owner.update(region_checked=True)
            self._authorize_ticket()
        except (OSError, ValueError):
            self.mode = "unknown"
        finally:
            self._open_welcome()
            self.done.set()

    def _open_welcome(self) -> None:
        if (
            self.closed
            or not telemetry_collection_allowed()
            or not self.owner.take_welcome()
        ):
            return
        try:
            path = self.owner.path.parent / "installation.json"
            state = load_or_create_installation_state(path)
            if state.attribution_claim_opened or state.first_launch_confirmed:
                return
            mark_attribution_claim_opened(path, state.install_id)
            url = f"{telemetry_site_origin()}/claim/#ticket={self.ticket}"
            self.welcome_opened = bool(webbrowser.open(url, new=2, autoraise=False))
        except Exception:  # noqa: BLE001 - browser adapters differ; welcome is best effort
            return
        finally:
            self.welcome_finished.set()

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
        # Persist the bounded unknown fallback too; never repeat region lookup
        # merely because the first session was offline or resolution timed out.
        self.owner.update(region_checked=True)
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
        self.permission_panel = AnalyticsConsentPanel(
            self.root,
            self.variable.set,
            lambda: webbrowser.open(f"{telemetry_site_origin()}/privacy/"),
        )
        self.root.after(50, self._restore_consent_focus)

    def _restore_consent_focus(self, remaining: int = 30) -> None:
        """One bounded focus request after browser handoff, never a focus loop."""
        panel = getattr(self, "permission_panel", None)
        if self.closed or self.consent_focus_requested or panel is None or panel.closed:
            return
        if not self.welcome_finished.is_set():
            if remaining > 0:
                self.root.after(50, lambda: self._restore_consent_focus(remaining - 1))
            return
        self.consent_focus_requested = True
        if not self.welcome_opened:
            return
        # Browser adapters return before the new tab necessarily becomes visible.
        # Give that handoff one short grace period, then request focus exactly once.
        self.root.after(100, self._focus_pending_consent)

    def _focus_pending_consent(self) -> None:
        panel = getattr(self, "permission_panel", None)
        if self.closed or panel is None or panel.closed:
            return
        try:
            request_window_foreground(self.root.winfo_toplevel())
            panel.frame.focus_force()
        except tk.TclError:
            pass
