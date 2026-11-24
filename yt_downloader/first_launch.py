"""Tells VODForge that an installation was opened: once as its first launch,
then once per session. Sent only while analytics are on."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .analytics_consent import AnalyticsConsentOwner, analytics_allowed
from .cloud_funnel import (
    InstallationState,
    installation_platform,
    load_or_create_installation_state,
    mark_first_launch_confirmed,
)
from .telemetry_credentials import TelemetryCredentialOwner
from .telemetry_policy import telemetry_collection_allowed


class FirstLaunchDelivery:
    def __init__(
        self,
        state_path: Path,
        *,
        recorder: Callable[..., bool] | None = None,
    ) -> None:
        self._state_path = state_path
        self._credentials = TelemetryCredentialOwner(state_path.parent)
        # The real recorder also observes every later session, so it has work
        # to do after the first launch is confirmed. A substitute does not.
        self._observes_sessions = recorder is None
        self._recorder = recorder or (
            lambda _state, *, app_version, platform_name: (
                self._credentials.observe_session(
                    app_version, installation_platform(platform_name)
                )
            )
        )

    def needs_delivery(self, state: InstallationState) -> bool:
        if self._observes_sessions and not self._credentials.session_observed():
            return True
        return not state.first_launch_confirmed

    def deliver(
        self,
        state: InstallationState,
        *,
        app_version: str,
        platform_name: str | None = None,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> InstallationState:
        if cancelled() or not telemetry_collection_allowed():
            return state
        consent = AnalyticsConsentOwner(self._state_path.parent)
        epoch = consent.snapshot().get("collection_epoch")

        def permitted() -> bool:
            return (
                not cancelled()
                and telemetry_collection_allowed()
                and analytics_allowed(self._state_path.parent)
                and consent.snapshot().get("collection_epoch") == epoch
            )

        if not permitted():
            return state
        current = load_or_create_installation_state(self._state_path)
        if (
            not current.first_launch_confirmed
            or (
                self._observes_sessions
                and not self._credentials.session_observed(app_version)
            )
        ) and self._recorder(
            current,
            app_version=app_version,
            platform_name=platform_name,
        ):
            if not permitted():
                return load_or_create_installation_state(self._state_path)
            current = mark_first_launch_confirmed(self._state_path, current.install_id)
        return current
