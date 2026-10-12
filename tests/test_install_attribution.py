from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")
from pathlib import Path
from typing import Any, Self

from yt_downloader.cloud_funnel import (
    installation_state_path,
    load_or_create_installation_state,
    mark_attribution_claim_confirmed,
    mark_first_launch_confirmed,
    update_onboarding,
)
from yt_downloader.install_attribution import (
    ATTRIBUTION_CLAIM_ISSUE_ENDPOINT,
    ATTRIBUTION_CLAIM_STATUS_ENDPOINT,
    ClaimIssueResult,
    InstallationAttributionOwner,
    claim_state,
    issue_claim,
)

INSTALL_ID = "f9c775b1-4c5a-47c4-87bb-81fe51881e54"
CLAIM_TOKEN = "A" * 43
CLAIM_URL = f"https://getvodforge.com/claim#token={CLAIM_TOKEN}"


def test_existing_profile_delivery_never_issues_browser_claim(tmp_path):
    path = tmp_path / "installation.json"
    state = update_onboarding(path, storage_version=1, browser_eligible=False)
    delivered = []

    def forbidden(*args, **kwargs):
        pytest.fail("Existing profile must not create a browser handoff")

    owner = InstallationAttributionOwner(
        path,
        first_party_recorder=lambda *a, **kw: delivered.append(True) or True,
        claim_issuer=forbidden,
        browser_opener=forbidden,
    )
    result = owner.deliver_first_launch(state, app_version="0.1.8")
    assert delivered == [True]
    assert result.first_launch_confirmed
    assert result.attribution_claim_token is None


@pytest.fixture(autouse=True)
def permitted_analytics(tmp_path, monkeypatch):
    from yt_downloader import analytics_consent

    analytics_consent.AnalyticsConsentOwner(tmp_path).choose(True)
    monkeypatch.setattr(analytics_consent, "application_data_dir", lambda: tmp_path)


class PayloadResponse:
    status = 200

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_claim_client_accepts_only_the_expected_https_fragment_url():
    requests: list[tuple[str, dict[str, str]]] = []

    def opener(request: Any, *, timeout: float) -> PayloadResponse:
        assert timeout == 4.0
        requests.append((request.full_url, json.loads(request.data.decode("utf-8"))))
        if request.full_url == ATTRIBUTION_CLAIM_ISSUE_ENDPOINT:
            return PayloadResponse({"ok": True, "claim_url": CLAIM_URL})
        return PayloadResponse({"ok": True, "state": "pending"})

    assert issue_claim(INSTALL_ID, CLAIM_TOKEN, opener=opener) == ClaimIssueResult(
        CLAIM_URL
    )
    assert claim_state(CLAIM_TOKEN, opener=opener) == "pending"
    assert requests == [
        (
            ATTRIBUTION_CLAIM_ISSUE_ENDPOINT,
            {"install_id": INSTALL_ID, "claim_token": CLAIM_TOKEN},
        ),
        (ATTRIBUTION_CLAIM_STATUS_ENDPOINT, {"claim_token": CLAIM_TOKEN}),
    ]

    bad = lambda *_args, **_kwargs: PayloadResponse(
        {"ok": True, "claim_url": f"https://evil.example/claim#token={CLAIM_TOKEN}"}
    )
    assert issue_claim(INSTALL_ID, CLAIM_TOKEN, opener=bad) is None


def test_claim_status_distinguishes_transport_failure_from_an_unknown_token():
    def unavailable(*_args: Any, **_kwargs: Any) -> PayloadResponse:
        raise OSError("offline")

    assert claim_state(CLAIM_TOKEN, opener=unavailable) == "unavailable"


def _state_path(tmp_path: Path) -> Path:
    path = installation_state_path(data_dir=tmp_path)
    state = load_or_create_installation_state(path)
    assert state.install_id
    return path


def test_owner_delivers_first_party_and_confirms_browser_claim(tmp_path: Path):
    path = _state_path(tmp_path)
    original = load_or_create_installation_state(path)
    first_party_calls: list[str] = []
    opened: list[tuple[str, int, bool]] = []

    owner = InstallationAttributionOwner(
        path,
        first_party_recorder=lambda state, **_kwargs: (
            first_party_calls.append(state.install_id) is None
        ),
        claim_issuer=lambda install_id, token: ClaimIssueResult(
            f"https://getvodforge.com/claim#token={token}"
        ),
        claim_reader=lambda _token: "claimed",
        browser_opener=lambda url, new, autoraise: (
            opened.append((url, new, autoraise)) is None
        ),
        poll_attempts=1,
    )

    updated = owner.deliver_first_launch(
        original,
        app_version="0.1.8-dev",
        platform_name="darwin",
    )

    assert first_party_calls == [original.install_id]
    assert len(opened) == 1
    assert opened[0][1:] == (2, False)
    assert opened[0][0].startswith("https://getvodforge.com/claim#token=")
    assert updated.first_launch_confirmed is True
    assert updated.attribution_claim_opened is True
    assert updated.attribution_claim_confirmed is True
    assert updated.attribution_claim_token is None
    assert owner.needs_delivery(updated) is False

    assert owner.deliver_first_launch(updated, app_version="0.1.8-dev") == updated
    assert first_party_calls == [original.install_id]


def test_first_party_delivery_survives_expired_browser_claim(
    tmp_path: Path,
):
    path = _state_path(tmp_path)
    original = load_or_create_installation_state(path)
    owner = InstallationAttributionOwner(
        path,
        first_party_recorder=lambda *_args, **_kwargs: True,
        claim_issuer=lambda _install_id, token: ClaimIssueResult(
            f"https://getvodforge.com/claim#token={token}"
        ),
        claim_reader=lambda _token: "expired",
        browser_opener=lambda *_args, **_kwargs: True,
        poll_attempts=1,
    )

    updated = owner.deliver_first_launch(original, app_version="0.1.8-dev")

    assert updated.first_launch_confirmed is True
    assert updated.attribution_claim_opened is True
    assert updated.attribution_claim_confirmed is False
    assert updated.attribution_claim_token is None
    assert owner.needs_delivery(updated) is False


def test_first_party_delivery_preserves_pending_browser_claim(
    tmp_path: Path,
):
    path = _state_path(tmp_path)
    original = load_or_create_installation_state(path)
    owner = InstallationAttributionOwner(
        path,
        first_party_recorder=lambda *_args, **_kwargs: True,
        claim_issuer=lambda _install_id, token: ClaimIssueResult(
            f"https://getvodforge.com/claim#token={token}"
        ),
        claim_reader=lambda _token: "pending",
        browser_opener=lambda *_args, **_kwargs: True,
        poll_attempts=1,
    )

    updated = owner.deliver_first_launch(original, app_version="0.1.8-dev")

    assert updated.first_launch_confirmed is True
    assert updated.attribution_claim_opened is True
    assert updated.attribution_claim_confirmed is False
    assert updated.attribution_claim_token is not None
    assert owner.needs_delivery(updated) is True


def test_completed_browser_claim_never_reopens_or_calls_removed_provider(tmp_path):
    path = _state_path(tmp_path)
    original = load_or_create_installation_state(path)
    current = mark_first_launch_confirmed(path, original.install_id)
    current = mark_attribution_claim_confirmed(path, original.install_id)
    owner = InstallationAttributionOwner(
        path,
        first_party_recorder=lambda *_a, **_kw: pytest.fail("already delivered"),
        browser_opener=lambda *_a, **_kw: pytest.fail("already confirmed"),
    )
    assert not owner.needs_delivery(current)
    assert owner.deliver_first_launch(current, app_version="0.2.6") == current


def test_owner_retries_after_first_launch_network_is_unavailable(tmp_path: Path):
    path = _state_path(tmp_path)
    original = load_or_create_installation_state(path)
    issue_attempts = 0
    opened: list[str] = []

    def issue(_install_id: str, token: str) -> ClaimIssueResult | None:
        nonlocal issue_attempts
        issue_attempts += 1
        if issue_attempts == 1:
            return None
        return ClaimIssueResult(f"https://getvodforge.com/claim#token={token}")

    owner = InstallationAttributionOwner(
        path,
        first_party_recorder=lambda *_args, **_kwargs: False,
        claim_issuer=issue,
        claim_reader=lambda _token: "claimed",
        browser_opener=lambda url, **_kwargs: opened.append(url) is None or True,
        poll_attempts=1,
    )

    unavailable = owner.deliver_first_launch(original, app_version="0.1.8-dev")
    delivered = owner.deliver_first_launch(unavailable, app_version="0.1.8-dev")

    assert unavailable.attribution_claim_token is None
    assert unavailable.attribution_claim_opened is False
    assert owner.needs_delivery(unavailable) is True
    assert issue_attempts == 2
    assert len(opened) == 1
    assert delivered.attribution_claim_confirmed is True


def test_owner_retries_same_persisted_claim_when_browser_was_unavailable(
    tmp_path: Path,
):
    path = _state_path(tmp_path)
    original = load_or_create_installation_state(path)
    open_results = iter([False, True])
    issued_tokens: list[str] = []
    read_tokens: list[str] = []

    owner = InstallationAttributionOwner(
        path,
        first_party_recorder=lambda *_args, **_kwargs: True,
        claim_issuer=lambda _install_id, token: (
            issued_tokens.append(token)
            or ClaimIssueResult(f"https://getvodforge.com/claim#token={token}")
        ),
        claim_reader=lambda token: read_tokens.append(token) or "claimed",
        browser_opener=lambda *_args, **_kwargs: next(open_results),
        poll_attempts=1,
    )

    unavailable = owner.deliver_first_launch(original, app_version="0.1.8-dev")
    delivered = owner.deliver_first_launch(unavailable, app_version="0.1.8-dev")

    assert unavailable.attribution_claim_token == issued_tokens[0]
    assert unavailable.attribution_claim_opened is False
    assert read_tokens == [issued_tokens[0]]
    assert len(issued_tokens) == 1
    assert delivered.attribution_claim_opened is True
    assert delivered.attribution_claim_confirmed is True


def test_owner_resumes_status_poll_after_browser_closed_before_claim_completed(
    tmp_path: Path,
):
    path = _state_path(tmp_path)
    original = load_or_create_installation_state(path)
    claim_states = iter(["unavailable", "claimed"])
    opened: list[str] = []

    owner = InstallationAttributionOwner(
        path,
        first_party_recorder=lambda *_args, **_kwargs: True,
        claim_issuer=lambda _install_id, token: ClaimIssueResult(
            f"https://getvodforge.com/claim#token={token}"
        ),
        claim_reader=lambda _token: next(claim_states),
        browser_opener=lambda url, **_kwargs: opened.append(url) is None or True,
        poll_attempts=1,
    )

    pending = owner.deliver_first_launch(original, app_version="0.1.8-dev")
    delivered = owner.deliver_first_launch(pending, app_version="0.1.8-dev")

    assert pending.attribution_claim_opened is True
    assert pending.attribution_claim_token is not None
    assert pending.attribution_claim_confirmed is False
    assert len(opened) == 1
    assert delivered.attribution_claim_confirmed is True


def test_native_owner_observes_each_session_even_with_completed_attribution(
    tmp_path, monkeypatch
):
    from yt_downloader import telemetry_credentials

    monkeypatch.setattr(
        telemetry_credentials, "telemetry_collection_allowed", lambda: True
    )
    from yt_downloader.cloud_funnel import mark_heycatch_first_launch_confirmed
    from yt_downloader.version import __version__

    path = tmp_path / "installation.json"
    state = load_or_create_installation_state(path)
    mark_first_launch_confirmed(path, state.install_id)
    mark_heycatch_first_launch_confirmed(path, state.install_id)
    state = mark_attribution_claim_confirmed(path, state.install_id)
    calls = []

    def opener(request, **kwargs):
        body = json.loads(request.data)
        calls.append(request.full_url.rsplit("/", 1)[-1])
        return PayloadResponse(
            {
                "ok": True,
                "enrolled": True,
                "launched": True,
                "credential_id": body["credential_id"],
                "install_id": state.install_id,
                "app_version": body["app_version"],
            }
        )

    def forbidden(*args, **kwargs):
        pytest.fail("Repeat session must not repeat browser/provider attribution")

    for count in (2, 3):
        owner = InstallationAttributionOwner(
            path,
            claim_issuer=forbidden,
            browser_opener=forbidden,
        )
        owner._credentials.opener = opener
        assert owner.needs_delivery(state)
        state = owner.deliver_first_launch(state, app_version=__version__)
        assert not owner.needs_delivery(state)
        assert len(calls) == count
    assert calls == ["enroll", "launch", "launch"]
