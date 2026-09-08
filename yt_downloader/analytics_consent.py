"""Durable analytics permission, separate from browser attribution and build policy."""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from .cloud_funnel import (
    InstallationIdentityError,
    load_or_create_installation_state,
    update_onboarding,
)
from .history import application_data_dir
from .settings_store import SettingsError, load_settings, update_analytics_settings
from .telemetry_policy import telemetry_collection_allowed
from .telemetry_transport import telemetry_urlopen

POLICY_URL = "https://getvodforge.com/api/analytics/policy"
_LOCK = threading.RLock()
_ONBOARDING_KEYS = ("mode", "region_checked", "prompted", "welcome_attempted")
REGION_POLICY_VERSION = 1


class AnalyticsConsentOwner:
    def __init__(self, directory: Path) -> None:
        self.path = directory / "settings.json"
        legacy = directory / "analytics-consent.json"
        with _LOCK:
            try:
                values = load_settings(self.path)
            except SettingsError:
                return  # Preserve malformed config; permission reads fail closed.
            if "analytics_consent" not in values and legacy.exists():
                try:
                    if legacy.stat().st_size <= 4096:
                        old = json.loads(legacy.read_text())
                        if isinstance(old, dict):
                            update_analytics_settings(self.path, old)
                except (OSError, ValueError):
                    pass
            installation = directory / "installation.json"
            try:
                state = load_or_create_installation_state(installation)
            except (InstallationIdentityError, OSError):
                return  # Do not replace damaged installation identity or consent.
            onboarding = state.onboarding or {}
            if "anonymous_usage_analytics" in values:
                update_analytics_settings(self.path, {}, migrate_legacy=True)
            if onboarding.get("storage_version") != 1:
                old = load_settings(self.path).get("analytics_consent", {})
                old = old if isinstance(old, dict) else {}
                eligible = onboarding.get("browser_eligible") is True
                update_onboarding(
                    installation,
                    storage_version=1,
                    browser_eligible=eligible,
                    welcome_attempted=not eligible
                    or old.get("welcome_attempted") is True,
                    # Evaluate every pre-migration installation once under this
                    # policy. Old defaults are not an explicit user choice.
                    mode="unknown",
                    region_checked=False,
                    region_policy_version=0,
                    prompted=old.get("choice") in {"granted", "denied"},
                )
            current = load_settings(self.path).get("analytics_consent", {})
            if isinstance(current, dict) and any(
                key in current for key in _ONBOARDING_KEYS
            ):
                update_analytics_settings(self.path, {}, remove=_ONBOARDING_KEYS)

    def snapshot(self) -> dict[str, Any]:
        with _LOCK:
            try:
                value = load_settings(self.path).get("analytics_consent", {})
                settings = value if isinstance(value, dict) else {}
                state = load_or_create_installation_state(
                    self.path.parent / "installation.json"
                )
                return {**settings, **(state.onboarding or {})}
            except (OSError, ValueError, SettingsError, InstallationIdentityError):
                return {}

    def update(self, **changes: Any) -> None:
        with _LOCK:
            preference = {
                key: value for key, value in changes.items() if key == "choice"
            }
            onboarding = {
                key: value for key, value in changes.items() if key in _ONBOARDING_KEYS
            }
            if preference:
                update_analytics_settings(self.path, preference)
            if onboarding:
                if onboarding.get("region_checked") is True:
                    onboarding["region_policy_version"] = REGION_POLICY_VERSION
                update_onboarding(self.path.parent / "installation.json", **onboarding)

    @property
    def allowed(self) -> bool:
        state = self.snapshot()
        return state.get("choice") == "granted" or (
            state.get("choice") != "denied" and state.get("mode") == "default-on"
        )

    def choose(self, enabled: bool) -> None:
        self.update(choice="granted" if enabled else "denied", prompted=True)

    @property
    def saved_region_mode(self) -> str | None:
        """Reuse completed policy decisions, including pre-marker installations."""
        state = self.snapshot()
        if (
            state.get("region_policy_version") == REGION_POLICY_VERSION
            and state.get("region_checked") is True
        ):
            mode = state.get("mode")
            return mode if mode in {"default-on", "opt-in"} else "unknown"
        return None

    def take_welcome(self) -> bool:
        with _LOCK:
            if self.snapshot().get("welcome_attempted"):
                return False
            self.update(welcome_attempted=True)
            return True

    def resolve(
        self, *, opener: Any = telemetry_urlopen, deadline: float | None = None
    ) -> str:
        """No install ID, cookie, credential or analytics payload in this request."""
        if not telemetry_collection_allowed():
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
        telemetry_collection_allowed()
        and AnalyticsConsentOwner(
            directory if directory is not None else application_data_dir()
        ).allowed
    )
