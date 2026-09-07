"""Durable analytics permission, separate from browser attribution and build policy."""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from .history import application_data_dir
from .private_files import write_private_bytes
from .telemetry_policy import production_telemetry_allowed

POLICY_URL = "https://getvodforge.com/api/analytics/policy"
_LOCK = threading.RLock()


class AnalyticsConsentOwner:
    def __init__(self, directory: Path, *, legacy_disabled: bool = False) -> None:
        self.path = directory / "analytics-consent.json"
        if legacy_disabled and not self.path.exists():
            self.update(choice="denied")

    def snapshot(self) -> dict[str, Any]:
        with _LOCK:
            try:
                if self.path.stat().st_size > 4096:
                    return {}
                value = json.loads(self.path.read_text())
                return value if isinstance(value, dict) else {}
            except (OSError, ValueError):
                return {}

    def update(self, **changes: Any) -> None:
        with _LOCK:
            value = self.snapshot()
            value.update(changes)
            write_private_bytes(self.path, json.dumps(value).encode())

    @property
    def allowed(self) -> bool:
        state = self.snapshot()
        return state.get("choice") == "granted" or (
            state.get("choice") != "denied" and state.get("mode") == "default-on"
        )

    def choose(self, enabled: bool) -> None:
        self.update(choice="granted" if enabled else "denied", prompted=True)

    def take_welcome(self) -> bool:
        with _LOCK:
            if self.snapshot().get("welcome_attempted"):
                return False
            self.update(welcome_attempted=True)
            return True

    def resolve(
        self, *, opener: Any = urllib.request.urlopen, deadline: float | None = None
    ) -> str:
        """No install ID, cookie, credential or analytics payload in this request."""
        if not production_telemetry_allowed():
            return "unknown"
        self.update(mode="unknown")
        remaining = 1.5 if deadline is None else deadline - time.monotonic()
        if remaining <= 0:
            return "unknown"
        request = urllib.request.Request(
            POLICY_URL, headers={"Accept": "application/json"}
        )
        try:
            with opener(request, timeout=min(1.5, remaining)) as response:
                raw = response.read(1025)
                if response.status != 200 or len(raw) > 1024:
                    return "unknown"
            value = json.loads(raw)
            if isinstance(value, dict) and value.get("resolved") is False:
                return "unknown"
            mode = value.get("mode") if isinstance(value, dict) else None
            if mode not in {"default-on", "opt-in"}:
                return "unknown"
            # Socket timeouts do not bound DNS or a slowly streaming response.
            # A late response must not enable analytics after the fallback prompt.
            if deadline is not None and time.monotonic() >= deadline:
                return "unknown"
            self.update(mode=mode)
            return mode
        except (OSError, ValueError):
            return "unknown"


def analytics_allowed(directory: Path | None = None) -> bool:
    return (
        production_telemetry_allowed()
        and AnalyticsConsentOwner(
            directory if directory is not None else application_data_dir()
        ).allowed
    )
