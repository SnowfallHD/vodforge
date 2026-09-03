from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Self

from yt_downloader.cloud_funnel import (
    installation_state_path,
    load_or_create_installation_state,
    mark_attribution_claim_confirmed,
    mark_first_launch_confirmed,
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


def test_owner_delivers_d1_then_alias_claim_then_direct_native_event(tmp_path: Path):
    path = _state_path(tmp_path)
    original = load_or_create_installation_state(path)
    first_party_calls: list[str] = []
    native_calls: list[tuple[str, str, str]] = []
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
        heycatch_recorder=lambda install_id, *, app_version, platform: (
            native_calls.append((install_id, app_version, platform)) is None
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
    assert native_calls == [(original.install_id, "0.1.8-dev", "macos")]
    assert updated.first_launch_confirmed is True
    assert updated.attribution_claim_opened is True
    assert updated.attribution_claim_confirmed is True
    assert updated.attribution_claim_token is None
    assert updated.heycatch_first_launch_confirmed is True
    assert owner.needs_delivery(updated) is False

    assert owner.deliver_first_launch(updated, app_version="0.1.8-dev") == updated
    assert first_party_calls == [original.install_id]
    assert len(native_calls) == 1


def test_owner_does_not_send_native_event_when_browser_claim_expires(
    tmp_path: Path,
):
    path = _state_path(tmp_path)
    original = load_or_create_installation_state(path)
    native_calls: list[str] = []
    owner = InstallationAttributionOwner(
        path,
        first_party_recorder=lambda *_args, **_kwargs: True,
        claim_issuer=lambda _install_id, token: ClaimIssueResult(
            f"https://getvodforge.com/claim#token={token}"
        ),
        claim_reader=lambda _token: "expired",
        browser_opener=lambda *_args, **_kwargs: True,
        heycatch_recorder=lambda install_id, **_kwargs: (
            native_calls.append(install_id) is None
        ),
        poll_attempts=1,
    )

    updated = owner.deliver_first_launch(original, app_version="0.1.8-dev")

    assert updated.first_launch_confirmed is True
    assert updated.attribution_claim_opened is True
    assert updated.attribution_claim_confirmed is False
    assert updated.attribution_claim_token is None
    assert updated.heycatch_first_launch_confirmed is False
    assert native_calls == []
    assert owner.needs_delivery(updated) is False


def test_owner_keeps_pending_claim_retryable_without_sending_native_event(
    tmp_path: Path,
):
    path = _state_path(tmp_path)
    original = load_or_create_installation_state(path)
    native_calls: list[str] = []
    owner = InstallationAttributionOwner(
        path,
        first_party_recorder=lambda *_args, **_kwargs: True,
        claim_issuer=lambda _install_id, token: ClaimIssueResult(
            f"https://getvodforge.com/claim#token={token}"
        ),
        claim_reader=lambda _token: "pending",
        browser_opener=lambda *_args, **_kwargs: True,
        heycatch_recorder=lambda install_id, **_kwargs: (
            native_calls.append(install_id) is None
        ),
        poll_attempts=1,
    )

    updated = owner.deliver_first_launch(original, app_version="0.1.8-dev")

    assert updated.first_launch_confirmed is True
    assert updated.attribution_claim_opened is True
    assert updated.attribution_claim_confirmed is False
    assert updated.attribution_claim_token is not None
    assert updated.heycatch_first_launch_confirmed is False
    assert native_calls == []
    assert owner.needs_delivery(updated) is True


def test_owner_retries_native_delivery_without_reopening_a_confirmed_claim(
    tmp_path: Path,
):
    path = _state_path(tmp_path)
    original = load_or_create_installation_state(path)
    current = mark_first_launch_confirmed(path, original.install_id)
    current = mark_attribution_claim_confirmed(path, original.install_id)
    outcomes = iter([False, True])
    opened: list[str] = []
    owner = InstallationAttributionOwner(
        path,
        heycatch_recorder=lambda *_args, **_kwargs: next(outcomes),
        browser_opener=lambda url, **_kwargs: opened.append(url) is None,
        poll_attempts=0,
    )

    failed = owner.deliver_first_launch(current, app_version="0.1.8-dev")
    delivered = owner.deliver_first_launch(failed, app_version="0.1.8-dev")

    assert failed.heycatch_first_launch_confirmed is False
    assert delivered.heycatch_first_launch_confirmed is True
    assert opened == []


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
        heycatch_recorder=lambda *_args, **_kwargs: True,
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
    assert delivered.heycatch_first_launch_confirmed is True


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
        heycatch_recorder=lambda *_args, **_kwargs: True,
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
    assert delivered.heycatch_first_launch_confirmed is True


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
        heycatch_recorder=lambda *_args, **_kwargs: True,
        poll_attempts=1,
    )

    pending = owner.deliver_first_launch(original, app_version="0.1.8-dev")
    delivered = owner.deliver_first_launch(pending, app_version="0.1.8-dev")

    assert pending.attribution_claim_opened is True
    assert pending.attribution_claim_token is not None
    assert pending.attribution_claim_confirmed is False
    assert len(opened) == 1
    assert delivered.attribution_claim_confirmed is True
    assert delivered.heycatch_first_launch_confirmed is True
