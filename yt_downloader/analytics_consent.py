"""Durable analytics permission, separate from browser attribution and build policy."""

from __future__ import annotations

import json
import threading
import time
import urllib.request
import uuid
from collections.abc import Callable
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
_ONBOARDING_KEYS = (
    "mode",
    "region_checked",
    "prompted",
    "welcome_attempted",
    "posthog_mode",
    "posthog_region_resolved",
)
REGION_POLICY_VERSION = 2
ANALYTICS_BENEFITS = (
    ("shield-check", "No content or credentials"),
    ("activity", "Fix errors without support"),
    ("trending-up", "Improve the platform"),
    ("sliders", "Optional sharing in Settings"),
)
ANALYTICS_DESCRIPTION = (
    "Share optional reports and referral association. Off stops new requests. "
    "Regional basic counts and service records may continue. "
    "No media links, paths or credentials. See Privacy details."
)


class AnalyticsConsentOwner:
    def __init__(self, directory: Path) -> None:
        self.path = directory / "settings.json"
        self._native_baseline_until = 0.0
        self._attribution_until = 0.0
        self._attribution_generation = 0
        self._privacy_requests_until = 0.0
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
            if (
                isinstance(current, dict)
                and current.get("choice") == "denied"
                and "collection_epoch" not in current
            ):
                update_analytics_settings(
                    self.path, {"collection_epoch": str(uuid.uuid4())}
                )
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
                if preference.get("choice") == "denied":
                    # Persist revocation with the choice, even if an outbox is locked.
                    preference["collection_epoch"] = str(uuid.uuid4())
                update_analytics_settings(self.path, preference)
            if onboarding:
                if onboarding.get("region_checked") is True:
                    onboarding["region_policy_version"] = REGION_POLICY_VERSION
                update_onboarding(self.path.parent / "installation.json", **onboarding)
                current = self.snapshot()
                if (
                    current.get("posthog_region_resolved") is True
                    and current.get("mode") == "default-on"
                    and current.get("posthog_mode") == "default-on"
                    and current.get("posthog_choice") not in {"granted", "denied"}
                    and not current.get("posthog_epoch")
                ):
                    update_analytics_settings(
                        self.path, {"posthog_epoch": str(uuid.uuid4())}
                    )

    @property
    def allowed(self) -> bool:
        state = self.snapshot()
        return state.get("choice") == "granted" or (
            state.get("choice") != "denied" and state.get("mode") == "default-on"
        )

    def choose(self, enabled: bool) -> None:
        self.update(choice="granted" if enabled else "denied", prompted=True)

    def migrate_data_sharing_choice(self) -> None:
        """Collapse any explicit prior refusal without granting another sink."""
        with _LOCK:
            state = self.snapshot()
            if "denied" in {state.get("choice"), state.get("posthog_choice")} and (
                state.get("choice") != "denied"
                or state.get("posthog_choice") != "denied"
            ):
                self.choose_data_sharing(False, acknowledge_scope=False)

    def choose_data_sharing(
        self, enabled: bool, *, acknowledge_scope: bool = True
    ) -> None:
        """Persist one explicit user choice for all optional app analytics."""
        with _LOCK:
            changes: dict[str, Any] = {
                "choice": "granted" if enabled else "denied",
                "posthog_choice": "granted" if enabled else "denied",
                "posthog_epoch": str(uuid.uuid4()),
            }
            if acknowledge_scope:
                changes["usage_scope_version"] = 1
                changes["attribution_permission_version"] = 1
            if not enabled:
                changes["collection_epoch"] = str(uuid.uuid4())
            # Finish onboarding metadata before the atomic preference commit.
            self.update(prompted=True)
            update_analytics_settings(self.path, changes)

    @property
    def attribution_allowed(self) -> bool:
        """Identity transmission needs its own fresh default or current grant."""
        if not telemetry_collection_allowed():
            return False
        state = self.snapshot()
        if not state or "denied" in {state.get("choice"), state.get("posthog_choice")}:
            return False
        if state.get("choice") == "granted":
            return (
                type(state.get("attribution_permission_version")) is int
                and state.get("attribution_permission_version") == 1
            )
        return time.monotonic() < self._attribution_until

    def attribution_permission(self) -> Callable[[], bool]:
        """Fence a bounded operation against Off/regrant and policy replacement."""
        state = self.snapshot()
        epochs = (state.get("collection_epoch"), state.get("posthog_epoch"))
        generation = self._attribution_generation

        def permitted() -> bool:
            current = self.snapshot()
            return (
                self.attribution_allowed
                and generation == self._attribution_generation
                and epochs
                == (current.get("collection_epoch"), current.get("posthog_epoch"))
            )

        return permitted

    @property
    def privacy_requests_available(self) -> bool:
        """Deployment capability only, never a grant for analytics or erasure."""
        return (
            telemetry_collection_allowed()
            and time.monotonic() < self._privacy_requests_until
        )

    @property
    def native_baseline_allowed(self) -> bool:
        """Fresh feature-specific policy only; never reuse the generic default."""
        if (
            not telemetry_collection_allowed()
            or time.monotonic() >= self._native_baseline_until
        ):
            return False
        state = self.snapshot()
        if not state:
            return False
        legacy_refusal = "denied" in {
            state.get("choice"),
            state.get("posthog_choice"),
        } and (
            type(state.get("usage_scope_version")) is not int
            or state.get("usage_scope_version") != 1
        )
        return not legacy_refusal

    @property
    def posthog_allowed(self) -> bool:
        """Preserve choices; only fresh explicit provider policy can default on."""
        state = self.snapshot()
        choice = state.get("posthog_choice")
        return self.allowed and (
            choice == "granted"
            or (
                choice != "denied"
                and state.get("posthog_region_resolved") is True
                and state.get("region_policy_version") == REGION_POLICY_VERSION
                and state.get("region_checked") is True
                and state.get("mode") == "default-on"
                and state.get("posthog_mode") == "default-on"
            )
        )

    def choose_posthog(self, enabled: bool) -> None:
        with _LOCK:
            update_analytics_settings(
                self.path,
                {
                    "posthog_choice": "granted" if enabled else "denied",
                    "posthog_epoch": str(uuid.uuid4()),
                },
            )

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
        self._native_baseline_until = 0.0
        self._attribution_until = 0.0
        self._attribution_generation += 1
        self._privacy_requests_until = 0.0
        if not telemetry_collection_allowed():
            return "unknown"
        self.update(
            mode="unknown", posthog_mode="opt-in", posthog_region_resolved=False
        )
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
            self.update(
                mode=mode,
                posthog_mode=(
                    "default-on"
                    if value.get("resolved") is True
                    and mode == "default-on"
                    and value.get("posthog_mode") == "default-on"
                    else "opt-in"
                ),
                posthog_region_resolved=value.get("resolved") is True,
            )
            self._native_baseline_until = (
                time.monotonic() + 24 * 3600
                if value.get("resolved") is True
                and type(value.get("native_baseline_version")) is int
                and value.get("native_baseline_version") == 1
                and value.get("native_baseline_mode") == "enabled"
                else 0.0
            )
            self._attribution_until = (
                time.monotonic() + 24 * 3600
                if value.get("resolved") is True
                and type(value.get("attribution_policy_version")) is int
                and value.get("attribution_policy_version") == 1
                and value.get("attribution_mode") == "default-on"
                else 0.0
            )
            self._privacy_requests_until = (
                time.monotonic() + 24 * 3600
                if type(value.get("privacy_requests_version")) is int
                and value.get("privacy_requests_version") == 1
                else 0.0
            )
            return mode
        except (OSError, ValueError, RuntimeError):
            self._native_baseline_until = 0.0
            self._attribution_until = 0.0
            self._privacy_requests_until = 0.0
            return "unknown"


def analytics_allowed(directory: Path | None = None) -> bool:
    return (
        telemetry_collection_allowed()
        and AnalyticsConsentOwner(
            directory if directory is not None else application_data_dir()
        ).allowed
    )
