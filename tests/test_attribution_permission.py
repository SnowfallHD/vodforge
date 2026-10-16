"""Identity handoff is gated before transport, independently of rich defaults."""

import json

import pytest

from yt_downloader.analytics_consent import AnalyticsConsentOwner
from yt_downloader.cloud_funnel import load_or_create_installation_state
from yt_downloader.install_attribution import InstallationAttributionOwner

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


class PolicyResponse:
    status = 200

    def __init__(self, **fields):
        self.fields = {"mode": "default-on", **fields}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, limit):
        return json.dumps(self.fields).encode()


@pytest.mark.parametrize("choice", [None, "legacy_on", "off"])
def test_generic_default_or_legacy_grant_never_authorizes_identity(tmp_path, choice):
    consent = AnalyticsConsentOwner(tmp_path)
    consent.update(mode="default-on", region_checked=True)
    if choice:
        consent.choose(choice == "legacy_on")
    calls = []
    owner = InstallationAttributionOwner(
        tmp_path / "installation.json",
        claim_issuer=lambda *args: calls.append(args),
    )
    assert owner.prepare_browser_attribution() is None
    assert calls == []
    assert not load_or_create_installation_state(
        tmp_path / "installation.json"
    ).attribution_claim_token


@pytest.mark.parametrize(
    "mode,version,resolved,expected",
    [
        ("default-on", 1, True, True),
        ("opt-in", 1, True, False),
        ("default-on", True, True, False),
        ("default-on", 2, True, False),
        ("default-on", 1, False, False),
        (None, 1, True, False),
    ],
)
def test_attribution_uses_own_fresh_versioned_policy(
    tmp_path, mode, version, resolved, expected
):
    consent = AnalyticsConsentOwner(tmp_path)
    consent.resolve(
        opener=lambda *a, **kw: PolicyResponse(
            attribution_mode=mode, attribution_policy_version=version, resolved=resolved
        )
    )
    assert consent.attribution_allowed is expected
    # A new process cannot adopt another process's region default.
    assert not AnalyticsConsentOwner(tmp_path).attribution_allowed
    if expected:
        consent.choose_data_sharing(False)
        assert not consent.attribution_allowed


def test_new_explicit_choice_is_durable_but_legacy_grant_is_not_acknowledgment(
    tmp_path,
):
    consent = AnalyticsConsentOwner(tmp_path)
    consent.choose(True)
    assert not consent.attribution_allowed
    consent.choose_data_sharing(True)
    assert consent.attribution_allowed
    assert AnalyticsConsentOwner(tmp_path).attribution_allowed
    consent.choose_data_sharing(False)
    assert not AnalyticsConsentOwner(tmp_path).attribution_allowed


def test_expiry_and_failed_refresh_revoke_default_without_changing_optional_cache(
    tmp_path, monkeypatch
):
    from yt_downloader import analytics_consent

    now = [100.0]
    monkeypatch.setattr(analytics_consent.time, "monotonic", lambda: now[0])
    consent = AnalyticsConsentOwner(tmp_path)

    def positive(*a, **kw):
        return PolicyResponse(
            resolved=True, attribution_mode="default-on", attribution_policy_version=1
        )

    consent.resolve(opener=positive)
    assert consent.attribution_allowed
    now[0] += 86401
    assert not consent.attribution_allowed
    consent.resolve(opener=positive)
    fence = consent.attribution_permission()

    def offline(*a, **kw):
        raise OSError("fixture offline")

    consent.resolve(opener=offline)
    consent.update(mode="default-on", region_checked=True)
    assert consent.allowed and not consent.attribution_allowed and not fence()


@pytest.mark.parametrize("boundary", ["off", "off_on", "policy_replaced"])
def test_inflight_issue_cannot_commit_or_open_after_permission_epoch_changes(
    tmp_path, boundary
):
    from yt_downloader.install_attribution import ClaimIssueResult

    consent = AnalyticsConsentOwner(tmp_path)
    consent.choose_data_sharing(True)

    def issue(install, token):
        if boundary == "policy_replaced":
            consent.resolve(
                opener=lambda *a, **kw: PolicyResponse(
                    resolved=True,
                    attribution_mode="opt-in",
                    attribution_policy_version=1,
                )
            )
        else:
            consent.choose_data_sharing(False)
            if boundary == "off_on":
                consent.choose_data_sharing(True)
        return ClaimIssueResult(f"https://getvodforge.com/claim#token={token}")

    owner = InstallationAttributionOwner(
        tmp_path / "installation.json", consent_owner=consent, claim_issuer=issue
    )
    assert owner.prepare_browser_attribution() is None
    state = load_or_create_installation_state(tmp_path / "installation.json")
    assert state.attribution_claim_token is None and not state.attribution_claim_opened


def test_blocked_automatic_admission_can_run_after_new_explicit_optin(
    tmp_path, monkeypatch
):
    import time
    from unittest.mock import Mock
    from yt_downloader.qt_quick import analytics
    from yt_downloader.install_attribution import ClaimIssueResult

    monkeypatch.setattr(analytics, "telemetry_collection_allowed", lambda: True)
    path = tmp_path / "installation.json"
    load_or_create_installation_state(path)
    session = analytics.QtAnalyticsSession(
        tmp_path, "0.2.6", Mock(), browser_opener=lambda url: True
    )
    session._started = True
    calls = []
    session._attribution = InstallationAttributionOwner(
        path,
        consent_owner=session.owner,
        claim_issuer=lambda install, token: (
            calls.append("issue")
            or ClaimIssueResult(f"https://getvodforge.com/claim#token={token}")
        ),
        claim_reader=lambda token: "claimed",
        poll_attempts=1,
    )
    for _ in range(3):
        session.poll_first_launch_delivery()
    assert calls == [] and session._attribution_work is None
    assert not (load_or_create_installation_state(path).onboarding or {}).get(
        "browser_claim_auto_attempted"
    )
    session.owner.choose_data_sharing(True)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        session.poll_first_launch_delivery()
        if load_or_create_installation_state(path).attribution_claim_confirmed:
            break
        time.sleep(0.005)
    assert calls == ["issue"]
    assert load_or_create_installation_state(path).attribution_claim_confirmed
    session.close()
    assert session.telemetry.shutdown(2)


def test_low_level_transport_requires_permission_and_does_not_consume_admission(
    tmp_path,
):
    from yt_downloader.install_attribution import issue_claim, claim_state

    calls = []

    def forbidden(*a, **kw):
        pytest.fail("Blocked capability reached network")

    token = "A" * 43
    assert (
        issue_claim("f9c775b1-4c5a-47c4-87bb-81fe51881e54", token, opener=forbidden)
        is None
    )
    assert claim_state(token, opener=forbidden) == "unavailable"
    assert (
        issue_claim(
            "f9c775b1-4c5a-47c4-87bb-81fe51881e54",
            token,
            opener=forbidden,
            permitted=lambda: False,
            admit=lambda: calls.append(True) or True,
        )
        is None
    )
    assert calls == []


def test_final_transport_fence_does_not_take_attempt_when_revoked_before_send():
    from yt_downloader.install_attribution import issue_claim

    checks = iter([True, False])
    taken = []
    assert (
        issue_claim(
            "f9c775b1-4c5a-47c4-87bb-81fe51881e54",
            "A" * 43,
            permitted=lambda: next(checks),
            admit=lambda: taken.append(True) or True,
            opener=lambda *a, **kw: pytest.fail("Revoked request reached transport"),
        )
        is None
    )
    assert taken == []


def test_queued_worker_revocation_preserves_unused_automatic_attempt(
    tmp_path, monkeypatch
):
    import threading
    from unittest.mock import Mock
    from yt_downloader.qt_quick import analytics

    class DeferredWork:
        def submit(self, kind, task):
            self.task = task
            return "owned"

        def close(self):
            pass

    monkeypatch.setattr(analytics, "telemetry_collection_allowed", lambda: True)
    monkeypatch.setattr(analytics, "ArchiveWorkOwner", DeferredWork)
    path = tmp_path / "installation.json"
    load_or_create_installation_state(path)
    session = analytics.QtAnalyticsSession(
        tmp_path, "0.2.6", Mock(), browser_opener=lambda url: True
    )
    session.owner.choose_data_sharing(True)
    session._started = True
    session._attribution = InstallationAttributionOwner(
        path,
        consent_owner=session.owner,
        claim_issuer=lambda *a: pytest.fail("Revoked worker issued identity"),
    )
    session._start_automatic_browser_attribution()
    assert session._attribution_work is not None
    session.owner.choose_data_sharing(False)
    assert session._attribution_work.task(threading.Event()) is None
    assert not (load_or_create_installation_state(path).onboarding or {}).get(
        "browser_claim_auto_attempted"
    )
    session.close()
    assert session.telemetry.shutdown(2)
