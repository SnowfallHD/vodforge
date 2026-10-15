"""Browser-owned attribution does not enroll app usage or repeat browser opens."""

import threading
import time
from unittest.mock import Mock

import pytest

from yt_downloader.analytics_consent import AnalyticsConsentOwner
from yt_downloader.cloud_funnel import load_or_create_installation_state
from yt_downloader.install_attribution import (
    ClaimIssueResult,
    InstallationAttributionOwner,
)
from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox
from yt_downloader.qt_quick import analytics

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


@pytest.mark.parametrize("allowed", [False, True])
@pytest.mark.parametrize("response", ["claimed", "pending"])
def test_automatic_browser_claim_preserves_independent_usage_choice(
    tmp_path, monkeypatch, allowed, response
):
    monkeypatch.setattr(analytics, "telemetry_collection_allowed", lambda: True)
    path = tmp_path / "installation.json"
    load_or_create_installation_state(path)  # A genuinely new eligible profile.
    consent = AnalyticsConsentOwner(tmp_path)
    consent.choose(allowed)
    consent.choose_posthog(False)
    monkeypatch.setattr(
        analytics,
        "ProductTelemetryOwner",
        lambda **kwargs: ProductTelemetryOwner(
            **kwargs, d1_recorder=lambda e: pytest.fail("Handshake sent usage")
        ),
    )
    opened = []
    issued = []
    gui = threading.get_ident()

    def opener(url):
        assert threading.get_ident() == gui
        opened.append(url)
        return True

    def issuer(install, token):
        issued.append(token)
        return ClaimIssueResult(f"https://getvodforge.com/claim#token={token}")

    for _ in range(2):
        session = analytics.QtAnalyticsSession(tmp_path, "0.2.6", Mock())
        session._automatic_browser_opener = opener
        session._started = True
        session._attribution = InstallationAttributionOwner(
            path,
            first_party_recorder=lambda *a, **kw: pytest.fail(
                "Handshake enrolled usage"
            ),
            claim_issuer=issuer,
            claim_reader=lambda token: response,
            browser_opener=lambda *a, **kw: pytest.fail("Worker opened browser"),
            poll_attempts=1,
        )
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            session.poll_first_launch_delivery()
            state = load_or_create_installation_state(path)
            if state.attribution_claim_opened and session._attribution_work is None:
                break
            time.sleep(0.005)
        assert len(opened) == 1
        assert len(issued) == 1
        assert state.attribution_claim_opened
        assert state.attribution_claim_confirmed is (response == "claimed")
        assert not state.first_launch_confirmed
        assert not state.product_telemetry_allowed
        # The historical provider refusal conservatively migrates the unified choice.
        assert not consent.allowed
        assert consent.snapshot()["posthog_choice"] == "denied"
        assert not _load_outbox(tmp_path / "product-telemetry.json")
        session.close()


@pytest.mark.parametrize(
    "boundary", ["closed", "build_disabled", "browser_failed", "migrated"]
)
def test_automatic_handoff_is_once_only_and_respects_operational_boundaries(
    tmp_path, monkeypatch, boundary
):
    from yt_downloader.cloud_funnel import update_onboarding

    enabled = [True]
    monkeypatch.setattr(analytics, "telemetry_collection_allowed", lambda: enabled[0])
    path = tmp_path / "installation.json"
    load_or_create_installation_state(path)
    consent = AnalyticsConsentOwner(tmp_path)
    consent.choose(False)
    if boundary == "migrated":
        update_onboarding(path, browser_eligible=False)
    opened = []
    session = analytics.QtAnalyticsSession(tmp_path, "0.2.6", Mock())
    session._started = True
    session._automatic_browser_opener = lambda url: opened.append(url) or False
    entered = threading.Event()
    release = threading.Event()

    def issuer(install, token):
        entered.set()
        assert release.wait(2)
        return ClaimIssueResult(f"https://getvodforge.com/claim#token={token}")

    session._attribution = InstallationAttributionOwner(path, claim_issuer=issuer)
    session.poll_first_launch_delivery()
    if boundary == "migrated":
        assert not entered.is_set()
    else:
        assert entered.wait(1)
        if boundary == "closed":
            # Set the close fence before releasing the bounded worker.
            session._closed = True
        elif boundary == "build_disabled":
            enabled[0] = False
        release.set()
        deadline = time.monotonic() + 2
        while session._attribution_work is not None and time.monotonic() < deadline:
            if session._closed:
                session.close()
                break
            session.poll_first_launch_delivery()
            time.sleep(0.005)
    state = load_or_create_installation_state(path)
    assert len(opened) == (1 if boundary == "browser_failed" else 0)
    assert not state.attribution_claim_opened and not state.attribution_claim_confirmed
    assert not state.first_launch_confirmed and not consent.allowed
    session.close()
    enabled[0] = True
    # Failed dispatch does not trigger another automatic opening on restart.
    again = analytics.QtAnalyticsSession(tmp_path, "0.2.6", Mock())
    again._started = True
    again._automatic_browser_opener = lambda url: pytest.fail("Repeated automatic open")
    again.poll_first_launch_delivery()
    assert again._attribution_work is None
    again.close()


@pytest.mark.parametrize("boundary", ["cancelled", "replacement", "no_match"])
def test_browser_poll_does_not_invent_confirmation_or_usage(tmp_path, boundary):
    from yt_downloader.cloud_funnel import (
        mark_attribution_claim_issued,
        mark_attribution_claim_opened,
    )

    consent = AnalyticsConsentOwner(tmp_path)
    consent.choose(False)
    path = tmp_path / "installation.json"
    state = load_or_create_installation_state(path)
    token = "x" * 43
    mark_attribution_claim_issued(path, state.install_id, token)
    mark_attribution_claim_opened(path, state.install_id, claim_token=token)
    cancelled = [False]

    def reader(actual):
        assert actual == token
        if boundary == "cancelled":
            cancelled[0] = True
        elif boundary == "replacement":
            mark_attribution_claim_issued(path, state.install_id, "y" * 43)
        return "pending" if boundary == "no_match" else "claimed"

    owner = InstallationAttributionOwner(path, claim_reader=reader, poll_attempts=1)
    assert not owner.poll_browser_attribution(cancelled=lambda: cancelled[0])
    saved = load_or_create_installation_state(path)
    assert not saved.attribution_claim_confirmed
    assert not saved.first_launch_confirmed and not saved.product_telemetry_allowed
    assert not consent.allowed


def test_only_one_owner_takes_automatic_attempt_and_completed_profiles_are_inert(
    tmp_path,
):
    from concurrent.futures import ThreadPoolExecutor

    from yt_downloader.cloud_funnel import take_automatic_browser_claim_attempt

    path = tmp_path / "installation.json"
    load_or_create_installation_state(path)
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(
            workers.map(lambda _: take_automatic_browser_claim_attempt(path), range(8))
        )
    assert results.count(True) == 1
    assert (load_or_create_installation_state(path).onboarding or {})[
        "browser_claim_auto_attempted"
    ]
