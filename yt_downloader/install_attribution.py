from __future__ import annotations

import json
import secrets
import time
import urllib.parse
import urllib.request
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .analytics_consent import analytics_allowed
from .cloud_funnel import (
    CLAIM_TOKEN_PATTERN,
    InstallationState,
    clear_attribution_claim,
    installation_platform,
    load_or_create_installation_state,
    mark_attribution_claim_confirmed,
    mark_attribution_claim_issued,
    mark_attribution_claim_opened,
    mark_first_launch_confirmed,
    mark_heycatch_first_launch_confirmed,
)
from .heycatch_telemetry import record_first_launch as record_heycatch_first_launch
from .telemetry_credentials import TelemetryCredentialOwner
from .telemetry_policy import telemetry_collection_allowed, telemetry_site_origin
from .telemetry_transport import telemetry_urlopen

ATTRIBUTION_CLAIM_ISSUE_ENDPOINT = "https://getvodforge.com/api/attribution/claim/issue"
ATTRIBUTION_CLAIM_STATUS_ENDPOINT = (
    "https://getvodforge.com/api/attribution/claim/status"
)
ATTRIBUTION_CLAIM_PAGE_ORIGIN = "https://getvodforge.com"
NETWORK_TIMEOUT_SECONDS = 4.0
POLL_ATTEMPTS = 45
POLL_INTERVAL_SECONDS = 1.0
ClaimState = Literal["claimed", "expired", "pending", "unavailable", "unknown"]


@dataclass(frozen=True)
class ClaimIssueResult:
    claim_url: str


def _post_json_object(
    url: str,
    payload: dict[str, str],
    *,
    opener: Callable[..., Any] = telemetry_urlopen,
) -> dict[str, Any] | None:
    if not telemetry_collection_allowed() or not analytics_allowed():
        return None
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "VODForge-Attribution-Claim/1",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
            status = int(getattr(response, "status", 200))
            body = response.read(4097)
        if status < 200 or status >= 300 or len(body) > 4096:
            return None
        decoded = json.loads(body.decode("utf-8"))
        return decoded if isinstance(decoded, dict) else None
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return None


def _validated_claim_url(value: Any, claim_token: str) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.netloc != "getvodforge.com"
        or parsed.path != "/claim"
        or parsed.query
        or parsed.username
        or parsed.password
        or parsed.fragment != f"token={claim_token}"
    ):
        return None
    return f"{telemetry_site_origin()}/claim#token={claim_token}"


def cancel_claim(claim_token: str) -> None:
    """Privacy withdrawal uses only the capability, even with analytics disabled."""
    if not telemetry_collection_allowed() or not CLAIM_TOKEN_PATTERN.fullmatch(
        claim_token
    ):
        return
    request = urllib.request.Request(
        f"{ATTRIBUTION_CLAIM_PAGE_ORIGIN}/api/attribution/claim/cancel",
        data=json.dumps({"claim_token": claim_token}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        # Fixed HTTPS origin/path; the validated capability is JSON body data,
        # never a caller-controlled URL or scheme.
        with telemetry_urlopen(request, timeout=2) as response:  # nosec B310
            response.read(1024)
    except OSError:
        pass


def issue_claim(
    install_id: str,
    claim_token: str,
    *,
    opener: Callable[..., Any] = telemetry_urlopen,
) -> ClaimIssueResult | None:
    if not CLAIM_TOKEN_PATTERN.fullmatch(claim_token):
        return None
    response = _post_json_object(
        ATTRIBUTION_CLAIM_ISSUE_ENDPOINT,
        {"install_id": install_id, "claim_token": claim_token},
        opener=opener,
    )
    if not response or response.get("ok") is not True:
        return None
    claim_url = _validated_claim_url(response.get("claim_url"), claim_token)
    return ClaimIssueResult(claim_url) if claim_url else None


def claim_state(
    claim_token: str,
    *,
    opener: Callable[..., Any] = telemetry_urlopen,
) -> ClaimState:
    if not CLAIM_TOKEN_PATTERN.fullmatch(claim_token):
        return "unknown"
    response = _post_json_object(
        ATTRIBUTION_CLAIM_STATUS_ENDPOINT,
        {"claim_token": claim_token},
        opener=opener,
    )
    if response is None:
        return "unavailable"
    state = response.get("state") if response.get("ok") is True else None
    return (
        state
        if state in {"claimed", "expired", "pending", "unknown"}
        else "unavailable"
    )


class InstallationAttributionOwner:
    """Owns first-launch delivery and its one-time browser identity handoff."""

    def __init__(
        self,
        state_path: Path,
        *,
        first_party_recorder: Callable[..., bool] | None = None,
        heycatch_recorder: Callable[..., bool] = record_heycatch_first_launch,
        claim_issuer: Callable[..., ClaimIssueResult | None] = issue_claim,
        claim_reader: Callable[..., ClaimState] = claim_state,
        browser_opener: Callable[..., bool] = webbrowser.open,
        sleep: Callable[[float], None] = time.sleep,
        poll_attempts: int = POLL_ATTEMPTS,
    ) -> None:
        self._state_path = state_path
        self._credentials = TelemetryCredentialOwner(state_path.parent)
        self._native_delivery = first_party_recorder is None
        self._first_party_recorder = first_party_recorder or (
            lambda _state, *, app_version, platform_name: (
                self._credentials.first_launch(
                    app_version, installation_platform(platform_name)
                )
            )
        )
        self._heycatch_recorder = heycatch_recorder
        self._claim_issuer = claim_issuer
        self._claim_reader = claim_reader
        self._browser_opener = browser_opener
        self._sleep = sleep
        self._poll_attempts = max(0, int(poll_attempts))

    def needs_delivery(self, state: InstallationState) -> bool:
        if self._native_delivery and not self._credentials.launch_confirmed():
            return True
        if not state.first_launch_confirmed:
            return True
        if state.heycatch_first_launch_confirmed:
            return False
        if state.attribution_claim_confirmed or state.attribution_claim_token:
            return True
        return not state.attribution_claim_opened

    def deliver_first_launch(
        self,
        state: InstallationState,
        *,
        app_version: str,
        platform_name: str | None = None,
    ) -> InstallationState:
        if not telemetry_collection_allowed() or not analytics_allowed(
            self._state_path.parent
        ):
            return state
        current = load_or_create_installation_state(self._state_path)
        platform = installation_platform(platform_name)
        if (
            not current.first_launch_confirmed
            or (
                self._native_delivery
                and not self._credentials.launch_confirmed(app_version)
            )
        ) and self._first_party_recorder(
            current,
            app_version=app_version,
            platform_name=platform_name,
        ):
            current = mark_first_launch_confirmed(self._state_path, current.install_id)

        already_delivered = current.heycatch_first_launch_confirmed
        if (
            not current.heycatch_first_launch_confirmed
            and current.first_launch_confirmed
        ):
            current = self._deliver_native_event(current, app_version, platform)
        if already_delivered and not current.attribution_claim_token:
            return current
        if (
            current.heycatch_first_launch_confirmed
            and current.attribution_claim_confirmed
        ):
            return current
        if current.attribution_claim_confirmed:
            return current

        onboarding = current.onboarding or {}
        # Migrated existing users may retry telemetry delivery, but must
        # never enroll a fresh browser claim as a side effect of that retry.
        if onboarding.get("storage_version") == 1 and not onboarding.get(
            "browser_eligible"
        ):
            return current

        claim_token = current.attribution_claim_token
        if claim_token is None:
            if current.attribution_claim_opened:
                return current
            claim_token = secrets.token_urlsafe(32)
            issued = self._claim_issuer(current.install_id, claim_token)
            if issued is None:
                return current
            current = mark_attribution_claim_issued(
                self._state_path, current.install_id, claim_token
            )
            try:
                opened = bool(
                    self._browser_opener(
                        issued.claim_url,
                        new=2,
                        autoraise=False,
                    )
                )
            except Exception:  # noqa: BLE001 - platform browser adapters vary
                opened = False
            if not opened:
                return current
            current = mark_attribution_claim_opened(
                self._state_path, current.install_id
            )
        elif not current.attribution_claim_opened:
            # A prior process persisted the capability before it could hand it
            # to the browser. Reissue it to recover that narrow interruption.
            claim_url = f"{telemetry_site_origin()}/claim#token={claim_token}"
            try:
                opened = bool(self._browser_opener(claim_url, new=2, autoraise=False))
            except Exception:  # noqa: BLE001 - platform browser adapters vary
                opened = False
            if not opened:
                return current
            current = mark_attribution_claim_opened(
                self._state_path, current.install_id
            )

        for attempt in range(self._poll_attempts):
            if not analytics_allowed(self._state_path.parent):
                return current
            status = self._claim_reader(claim_token)
            if status == "claimed":
                current = mark_attribution_claim_confirmed(
                    self._state_path, current.install_id
                )
                return self._deliver_native_event(current, app_version, platform)
            if status in {"expired", "unknown"}:
                return clear_attribution_claim(self._state_path, current.install_id)
            if attempt + 1 < self._poll_attempts:
                self._sleep(POLL_INTERVAL_SECONDS)
        return current

    def _deliver_native_event(
        self,
        state: InstallationState,
        app_version: str,
        platform: str,
    ) -> InstallationState:
        if state.heycatch_first_launch_confirmed:
            return state
        if analytics_allowed(self._state_path.parent) and self._heycatch_recorder(
            state.install_id,
            app_version=app_version,
            platform=platform,
        ):
            return mark_heycatch_first_launch_confirmed(
                self._state_path, state.install_id
            )
        return state
