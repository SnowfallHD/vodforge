from __future__ import annotations

from unittest.mock import Mock

import pytest

from yt_downloader.analytics_consent import AnalyticsConsentOwner
from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox
from yt_downloader.qt_quick import analytics

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


@pytest.mark.parametrize("allowed", [False, True])
@pytest.mark.parametrize("claim", ["confirmed", "pending", "absent"])
@pytest.mark.parametrize("transport_allowed", [False, True])
def test_cold_link_display_preserves_durable_fact_without_authorizing_delivery(
    tmp_path, monkeypatch, allowed, claim, transport_allowed
):
    from yt_downloader.cloud_funnel import (
        load_or_create_installation_state,
        mark_attribution_claim_confirmed,
        mark_attribution_claim_issued,
        mark_attribution_claim_opened,
    )

    monkeypatch.setattr(
        analytics, "telemetry_collection_allowed", lambda: transport_allowed
    )
    path = tmp_path / "installation.json"
    state = load_or_create_installation_state(path)
    if claim != "absent":
        token = "a" * 43
        mark_attribution_claim_issued(path, state.install_id, token)
        mark_attribution_claim_opened(path, state.install_id, claim_token=token)
        if claim == "confirmed":
            mark_attribution_claim_confirmed(path, state.install_id, claim_token=token)
    consent = AnalyticsConsentOwner(tmp_path)
    consent.choose(allowed)
    before = path.read_bytes()
    monkeypatch.setattr(
        analytics,
        "ProductTelemetryOwner",
        lambda **kwargs: ProductTelemetryOwner(
            **kwargs, d1_recorder=lambda e: pytest.fail("Display sent telemetry")
        ),
    )
    expected = (
        "linked"
        if claim == "confirmed"
        else "waiting"
        if claim == "pending"
        else "unavailable"
    )
    for _ in range(2):
        session = analytics.QtAnalyticsSession(tmp_path, "0.2.6", Mock())
        assert session.installation_link_status == expected
        assert session.allowed is (allowed and transport_allowed)
        assert session._attribution_work is None
        assert session._automatic_browser_opener is None
        assert path.read_bytes() == before
        session.close()


@pytest.mark.parametrize("kind", ["app_opened", "feature_used"])
@pytest.mark.parametrize("interruption", [None, "denied", "closed"])
def test_idle_session_retries_same_pending_event_without_user_input(
    tmp_path, monkeypatch, kind, interruption
):
    clock = [100.0]
    monkeypatch.setattr(analytics, "telemetry_collection_allowed", lambda: True)
    monkeypatch.setattr(analytics.time, "monotonic", lambda: clock[0])
    AnalyticsConsentOwner(tmp_path).choose(True)
    attempts = []

    def deliver(event):
        attempts.append(event.public_payload())
        return len(attempts) > 1

    def telemetry_factory(**kwargs):
        return ProductTelemetryOwner(
            **kwargs,
            d1_recorder=deliver,
        )

    monkeypatch.setattr(analytics, "ProductTelemetryOwner", telemetry_factory)
    session = analytics.QtAnalyticsSession(tmp_path, "0.2.3-dev.4", Mock())
    owner = session.telemetry
    assert owner is not None
    record = (
        owner.record_app_opened
        if kind == "app_opened"
        else lambda: owner.record_feature("library", "opened")
    )
    assert record()
    assert owner.shutdown(2)
    assert len(attempts) == 1
    queued = _load_outbox(tmp_path / "product-telemetry.json")
    assert len(queued) == 1

    if interruption == "denied":
        assert session.choose(False)
    elif interruption == "closed":
        session.close()

    session.poll_first_launch_delivery()
    assert owner.shutdown(2)
    assert len(attempts) == 1
    clock[0] += 31
    session.poll_first_launch_delivery()
    assert owner.shutdown(2)
    if interruption is None:
        assert len(attempts) == 2
        assert attempts[0] == attempts[1]
        assert not _load_outbox(tmp_path / "product-telemetry.json")
        session.poll_first_launch_delivery()
        assert owner.shutdown(2)
        assert len(attempts) == 2
    else:
        assert len(attempts) == 1
    session.close()


@pytest.mark.parametrize(
    "interruption", [None, "denied", "reenrolled", "closed", "browser_failed"]
)
@pytest.mark.parametrize("legacy", [False, True])
def test_explicit_link_uses_gui_dispatch_and_only_canonical_claim_ack(
    tmp_path, monkeypatch, interruption, legacy
):
    import threading
    import time

    from yt_downloader.cloud_funnel import load_or_create_installation_state
    from yt_downloader.install_attribution import (
        ClaimIssueResult,
        InstallationAttributionOwner,
    )

    monkeypatch.setattr(analytics, "telemetry_collection_allowed", lambda: True)
    consent = AnalyticsConsentOwner(tmp_path)
    consent.choose_data_sharing(True)
    monkeypatch.setattr(
        analytics,
        "ProductTelemetryOwner",
        lambda **kwargs: ProductTelemetryOwner(**kwargs, d1_recorder=lambda e: True),
    )
    session = analytics.QtAnalyticsSession(tmp_path, "0.2.6", Mock())
    if legacy:
        from yt_downloader.cloud_funnel import update_onboarding

        update_onboarding(
            tmp_path / "installation.json", storage_version=1, browser_eligible=False
        )
    session._attribution = InstallationAttributionOwner(
        tmp_path / "installation.json",
        first_party_recorder=lambda *args, **kwargs: True,
        claim_issuer=lambda install, token: ClaimIssueResult(
            f"https://getvodforge.com/claim#token={token}"
        ),
        claim_reader=lambda token: "claimed",
        browser_opener=lambda *args, **kwargs: pytest.fail(
            "Startup must not open browser"
        ),
    )
    dispatched = []
    gui_thread = threading.get_ident()

    def open_browser(url):
        assert threading.get_ident() == gui_thread
        dispatched.append(url)
        return interruption != "browser_failed"

    assert session.request_installation_link(open_browser)
    assert not session.request_installation_link(open_browser)
    assert not dispatched  # Never opens from preparation's worker thread.
    if interruption in {"denied", "reenrolled"}:
        consent.choose_data_sharing(False)
        if interruption == "reenrolled":
            consent.choose_data_sharing(True)
    elif interruption == "closed":
        session.close()
    deadline = time.monotonic() + 3
    while session._attribution_work is not None and time.monotonic() < deadline:
        session.poll_first_launch_delivery()
        time.sleep(0.005)
    state = load_or_create_installation_state(tmp_path / "installation.json")
    if interruption is None:
        assert len(dispatched) == 1
        assert state.attribution_claim_opened and state.attribution_claim_confirmed
        assert state.attribution_claim_token is None
        assert session.installation_link_status == "linked"
    else:
        assert (
            not state.attribution_claim_opened and not state.attribution_claim_confirmed
        )
        assert len(dispatched) == (1 if interruption == "browser_failed" else 0)
    session.close()
    assert session.telemetry.shutdown(2)


def test_disabled_session_display_does_not_create_identity_or_open_browser(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(analytics, "telemetry_collection_allowed", lambda: False)
    session = analytics.QtAnalyticsSession(tmp_path, "0.2.6", Mock())
    assert session.installation_link_status == "unavailable"
    assert session.owner is None and session.telemetry is None
    assert not (tmp_path / "installation.json").exists()
    assert not session.request_installation_link(
        lambda url: pytest.fail("Disabled session opened a browser")
    )
    session.close()


def test_unified_failed_choice_disables_session_and_reports_off(tmp_path, monkeypatch):
    monkeypatch.setattr(analytics, "telemetry_collection_allowed", lambda: True)
    owner = AnalyticsConsentOwner(tmp_path)
    owner.choose_data_sharing(True)
    session = analytics.QtAnalyticsSession(tmp_path, "0.2.6", Mock())
    telemetry = session.telemetry
    session.telemetry = Mock()
    assert session.allowed
    monkeypatch.setattr(session.owner, "choose_data_sharing", Mock(side_effect=OSError))
    assert not session.choose(False)
    assert not session.allowed
    session.telemetry.set_enabled.assert_called_once_with(False)
    session.telemetry = telemetry
    session.close()


@pytest.mark.parametrize("manual", [False, True])
def test_default_off_and_manual_off_have_same_optional_collection_boundary(
    tmp_path, monkeypatch, manual
):
    from yt_downloader.cloud_funnel import load_or_create_installation_state

    monkeypatch.setattr(analytics, "telemetry_collection_allowed", lambda: True)
    consent = AnalyticsConsentOwner(tmp_path)
    consent.update(mode="opt-in", region_checked=True)
    if manual:
        consent.choose_data_sharing(False)
    install_id = load_or_create_installation_state(
        tmp_path / "installation.json"
    ).install_id
    sinks = []
    monkeypatch.setattr(
        analytics,
        "ProductTelemetryOwner",
        lambda **kwargs: ProductTelemetryOwner(
            **kwargs,
            d1_recorder=lambda event: sinks.append(event) or True,
            posthog_recorder=lambda event: pytest.fail("Off sent provider analytics"),
        ),
    )
    session = analytics.QtAnalyticsSession(tmp_path, "0.2.6", Mock())
    try:
        assert not session.allowed and not session.owner.posthog_allowed
        for event in (
            "app_opened",
            "run_started",
            "run_completed",
            "media_exported",
            "playback_started",
        ):
            assert not session.telemetry.record(event)
        session.lifecycle.ready()
        session.lifecycle.foreground(True)
        session.lifecycle.viewed("library")
        session.lifecycle.report_exception(ValueError, "sys")
        session.lifecycle.tick()
        session.poll_first_launch_delivery()
        assert session.telemetry.shutdown(2)
        assert sinks == []
        assert not _load_outbox(tmp_path / "product-telemetry.json")
        assert not (tmp_path / "analytics-sessions").exists()
        assert (
            load_or_create_installation_state(tmp_path / "installation.json").install_id
            == install_id
        )
    finally:
        session.close()


def test_fresh_native_policy_outage_preserves_existing_rich_policy_cache(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(analytics, "telemetry_collection_allowed", lambda: True)
    owner = AnalyticsConsentOwner(tmp_path)
    owner.update(
        mode="default-on",
        region_checked=True,
        posthog_mode="default-on",
        posthog_region_resolved=True,
    )

    def unavailable(self, **kwargs):
        self.update(
            mode="unknown", posthog_mode="opt-in", posthog_region_resolved=False
        )
        return "unknown"

    monkeypatch.setattr(AnalyticsConsentOwner, "resolve", unavailable)
    session = analytics.QtAnalyticsSession(tmp_path, "0.2.6", Mock())
    try:
        session.start()
        assert session._resolved.wait(2)
        assert session._mode == "default-on"
        assert session.owner.allowed and session.owner.posthog_allowed
        assert not session.owner.native_baseline_allowed
    finally:
        session.close()


# --- A refusal sends nothing -------------------------------------------------
#
# Off in Settings, "No thanks" at the consent question, or quitting while the
# question is open: from then on the app makes no analytics request of any
# kind. Each case below drives every path that can send, with the real
# transports, against a server that answers "everything is enabled", and counts
# the requests that reach the network layer.

EVERYTHING_ENABLED = {
    "ok": True,
    "mode": "default-on",
    "resolved": True,
    "native_baseline_version": 1,
    "native_baseline_mode": "enabled",
    "attribution_mode": "default-on",
    "attribution_policy_version": 1,
    "posthog_mode": "default-on",
    "privacy_requests_version": 1,
}


def _off_in_settings(owner):
    owner.update(mode="default-on", region_checked=True)
    owner.choose_data_sharing(False)


def _declined_at_the_question(owner):
    owner.update(mode="opt-in", region_checked=True, prompted=True)
    owner.choose_data_sharing(False)


def _quit_with_the_question_open(owner):
    owner.update(mode="opt-in", region_checked=True, prompted=True)


def _quit_with_the_question_open_in_a_default_on_region(owner):
    # The region answer arrived late, so the question was shown; a later launch
    # resolves the region as default-on. The unanswered question still wins.
    owner.update(mode="default-on", region_checked=True, prompted=True)


def _off_saved_by_an_older_version(owner):
    from yt_downloader.settings_store import update_analytics_settings

    owner.update(mode="default-on", region_checked=True)
    update_analytics_settings(owner.path, {"choice": "denied"})


REFUSALS = [
    _off_in_settings,
    _declined_at_the_question,
    _quit_with_the_question_open,
    _quit_with_the_question_open_in_a_default_on_region,
    _off_saved_by_an_older_version,
]


@pytest.fixture
def release_build(tmp_path, monkeypatch):
    """A release build whose every network request is recorded, none real."""
    import io
    import json
    import urllib.request

    from yt_downloader import analytics_consent, cloud_funnel, telemetry_policy

    monkeypatch.setattr(telemetry_policy, "production_telemetry_allowed", lambda: True)
    for name in (
        "VODFORGE_QUALITY_E2E",
        "VODFORGE_DISABLE_TELEMETRY",
        "VODFORGE_QA_PREVIEW_TELEMETRY",
        "VODFORGE_QA_PROFILE",
    ):
        monkeypatch.delenv(name, raising=False)
    for module in (analytics_consent, cloud_funnel):
        monkeypatch.setattr(module, "application_data_dir", lambda **_kwargs: tmp_path)
    requests: list[str] = []

    class Answer(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def open_(_self, fullurl, data=None, timeout=None):
        requests.append(getattr(fullurl, "full_url", fullurl))
        return Answer(json.dumps(EVERYTHING_ENABLED).encode())

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", open_)
    return requests


def _use_every_sending_path(tmp_path):
    """Launch, use and quit the app; return what it tried to open in a browser."""
    import time

    from yt_downloader import cloud_funnel
    from yt_downloader.cloud_funnel import load_or_create_installation_state
    from yt_downloader.telemetry_credentials import TelemetryCredentialOwner

    opened: list[str] = []
    session = analytics.QtAnalyticsSession(
        tmp_path,
        "0.2.9",
        Mock(),
        browser_opener=lambda url: opened.append(url) or True,
    )
    owner = session.owner
    session.start()
    assert session._resolved.wait(5)
    asked = [session.poll() for _ in range(3)]

    def settle():
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            session.poll_first_launch_delivery()
            if session._attribution_work is None and session._privacy_work is None:
                break
            time.sleep(0.01)

    telemetry = session.telemetry
    telemetry.record_app_opened()
    telemetry.record("run_completed")
    telemetry.record("run_failed")
    telemetry.record_feature("library", "opened")
    telemetry.record_baseline("app_started")
    telemetry.flush_async()
    assert telemetry.shutdown(5)
    session.start_first_launch_delivery()
    settle()
    session.request_installation_link(lambda url: opened.append(url) or True)
    settle()
    state = load_or_create_installation_state(tmp_path / "installation.json")
    pro_page = cloud_funnel.cloud_page_url(state.install_id)
    cloud_funnel.record_cloud_seen(state, app_version="0.2.9")
    cloud_funnel.record_cloud_click(state)
    credentials = TelemetryCredentialOwner(tmp_path)
    credentials.observe_session("0.2.9", "macos")
    credentials.first_launch("0.2.9", "macos")
    credentials.event({"platform": "macos", "event_name": "app_opened"})
    session.close()
    assert telemetry.shutdown(5)
    return owner, asked, opened, pro_page


@pytest.mark.parametrize("refuse", REFUSALS, ids=lambda f: f.__name__.strip("_"))
def test_a_refusal_sends_nothing_at_all(tmp_path, release_build, refuse):
    from yt_downloader import cloud_funnel

    refuse(AnalyticsConsentOwner(tmp_path))
    owner, asked, opened, pro_page = _use_every_sending_path(tmp_path)
    assert release_build == []  # not even the launch policy check
    assert opened == []
    assert asked == [False, False, False]  # and no second consent question
    assert pro_page == cloud_funnel.CLOUD_PAGE_URL  # no installation ID in the link
    assert not owner.allowed and owner.declined
    assert not owner.native_baseline_allowed
    assert not owner.attribution_allowed and not owner.posthog_allowed
    assert not _load_outbox(tmp_path / "product-telemetry.json")
    assert not (tmp_path / "telemetry-credential.json").exists()


def test_the_same_use_does_send_for_a_default_on_user(tmp_path, release_build):
    # The control for the test above: the spy sees real traffic, and a region
    # default with no refusal still works as before.
    AnalyticsConsentOwner(tmp_path).update(mode="default-on", region_checked=True)
    owner, asked, _opened, pro_page = _use_every_sending_path(tmp_path)
    assert owner.allowed and not owner.declined
    assert asked == [False, False, False]
    assert "https://getvodforge.com/api/analytics/policy" in release_build
    assert "https://getvodforge.com/api/telemetry/baseline" in release_build
    assert any("/api/telemetry/v2/" in url for url in release_build)
    assert "iid=" in pro_page


def test_turning_analytics_off_mid_session_stops_everything_held(
    tmp_path, release_build
):
    AnalyticsConsentOwner(tmp_path).update(mode="default-on", region_checked=True)
    session = analytics.QtAnalyticsSession(tmp_path, "0.2.9", Mock())
    session.start()
    assert session._resolved.wait(5)
    session.poll()
    telemetry = session.telemetry
    assert telemetry.shutdown(5)
    assert session.choose(False)
    assert telemetry.shutdown(5)
    del release_build[:]
    assert not telemetry.record_app_opened()
    assert not telemetry.record("run_completed")
    assert not telemetry.record_feature("library", "opened")
    assert not telemetry.record_baseline("app_started")
    telemetry.flush_async()
    assert telemetry.shutdown(5)
    session.close()
    assert release_build == []
    assert not _load_outbox(tmp_path / "product-telemetry.json")


def test_turning_analytics_back_on_sends_again(tmp_path, release_build):
    _off_in_settings(AnalyticsConsentOwner(tmp_path))
    session = analytics.QtAnalyticsSession(tmp_path, "0.2.9", Mock())
    session.start()
    assert session._resolved.wait(5)
    session.poll()
    assert release_build == []
    assert session.choose(True)
    assert session.telemetry.record_feature("library", "opened")
    assert session.telemetry.shutdown(5)
    session.close()
    assert any("/api/telemetry/v2/" in url for url in release_build)


def test_a_privacy_request_after_a_refusal_asks_only_what_it_needs(
    tmp_path, release_build
):
    # The launch policy check is skipped after a refusal, so the app learns
    # whether the service takes privacy requests only when the user asks.
    import json
    import time
    import uuid

    from yt_downloader.private_files import write_private_bytes

    _off_in_settings(AnalyticsConsentOwner(tmp_path))
    write_private_bytes(
        tmp_path / "telemetry-credential.json",
        json.dumps({"credential_id": str(uuid.uuid4()), "secret": "s" * 43}).encode(),
    )
    session = analytics.QtAnalyticsSession(tmp_path, "0.2.9", Mock())
    session.start()
    assert session._resolved.wait(5)
    session.poll()
    assert release_build == []
    pages: list[str] = []
    assert session.request_privacy_action(
        "deletion", lambda url: pages.append(url) or True
    )
    deadline = time.monotonic() + 5
    while session._privacy_work is not None and time.monotonic() < deadline:
        session.poll_first_launch_delivery()
        time.sleep(0.01)
    assert release_build == [
        "https://getvodforge.com/api/analytics/policy",
        "https://getvodforge.com/api/privacy/requests/issue",
    ]
    assert len(pages) == 1  # the request page, or the privacy page as a fallback
    # The answer said everything is enabled; the refusal still stands.
    owner = session.owner
    assert not owner.allowed and not owner.native_baseline_allowed
    assert not owner.attribution_allowed
    assert not session.telemetry.record_baseline("app_started")
    session.close()
    assert len(release_build) == 2
