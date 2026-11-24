"""Coarse counts carry no identity and are sent only while analytics are on."""

import json
from unittest.mock import Mock

import pytest

from yt_downloader import analytics_consent as consent
from yt_downloader import product_telemetry as product
from yt_downloader.analytics_consent import AnalyticsConsentOwner
from yt_downloader.cloud_funnel import load_or_create_installation_state


class Policy:
    status = 200

    def __init__(self, fields):
        self.fields = fields

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, size):
        return json.dumps(self.fields).encode()


def resolve(owner, user_requested=False, **overrides):
    fields = {
        "mode": "default-on",
        "resolved": True,
        "native_baseline_version": 1,
        "native_baseline_mode": "enabled",
        **overrides,
    }
    return owner.resolve(
        opener=lambda *a, **k: Policy(fields), user_requested=user_requested
    )


@pytest.fixture(autouse=True)
def allowed_build(monkeypatch):
    monkeypatch.setattr(consent, "telemetry_collection_allowed", lambda: True)
    monkeypatch.setattr(product, "telemetry_collection_allowed", lambda: True)


@pytest.mark.parametrize("choice", ["default_on", "granted"])
def test_eligible_baseline_same_closed_payload_while_analytics_are_on(tmp_path, choice):
    owner = AnalyticsConsentOwner(tmp_path)
    if choice == "granted":
        owner.choose_data_sharing(True)
    resolve(owner)
    assert owner.allowed
    before = load_or_create_installation_state(
        tmp_path / "installation.json"
    ).install_id
    sent = []
    optional = []
    telemetry = product.ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=tmp_path / "installation.json",
        app_version="0.2.6",
        enabled=False,
        baseline_permitted=lambda: owner.native_baseline_allowed,
        baseline_recorder=lambda row: sent.append(row) or False,
        d1_recorder=lambda event: optional.append(event) or True,
    )
    assert telemetry.record_baseline("app_started")
    assert telemetry.shutdown(2)
    # This owner's rich path is off; the coarse count is still made.
    assert not telemetry.record("run_completed")
    assert telemetry.shutdown(2)
    assert [row["metric"] for row in sent] == ["app_started", "run_completed"]
    assert all(
        set(row) == {"schema_version", "platform", "app_version", "metric", "count"}
        for row in sent
    )
    assert all(row["count"] == 1 for row in sent)
    assert optional == [] and not (tmp_path / "events.json").exists()
    assert (
        load_or_create_installation_state(tmp_path / "installation.json").install_id
        == before
    )
    telemetry.flush_async()
    assert telemetry.shutdown(2)
    assert len(sent) == 2  # Failed/ambiguous requests have no automatic replay.


@pytest.mark.parametrize(
    "fields",
    [
        {"native_baseline_mode": None},
        {"native_baseline_version": None},
        {"native_baseline_version": True},
        {"native_baseline_mode": "off"},
        {"resolved": False},
        {"mode": "unknown"},
    ],
)
def test_missing_or_unsupported_policy_never_inherits_generic_default(tmp_path, fields):
    owner = AnalyticsConsentOwner(tmp_path)
    owner.choose_data_sharing(True)  # analytics on; only the count policy is missing
    resolve(owner, **fields)
    assert owner.allowed
    assert not owner.native_baseline_allowed


@pytest.mark.parametrize("refusal", ["choice", "posthog_choice"])
def test_any_refusal_stops_the_counts_however_it_was_recorded(tmp_path, refusal):
    owner = AnalyticsConsentOwner(tmp_path)
    consent.update_analytics_settings(owner.path, {refusal: "denied"})
    owner.migrate_data_sharing_choice()
    # Even a server that says counts are enabled cannot restart them.
    resolve(owner, user_requested=True)
    assert not owner.native_baseline_allowed
    owner.choose_data_sharing(False)  # Off again, through the current Settings control.
    resolve(owner, user_requested=True)
    assert not owner.native_baseline_allowed
    assert not owner.allowed and not owner.posthog_allowed


def test_counts_need_a_fresh_policy_each_session(tmp_path):
    owner = AnalyticsConsentOwner(tmp_path)
    resolve(owner)
    assert owner.native_baseline_allowed
    restarted = AnalyticsConsentOwner(tmp_path)
    assert restarted.allowed  # the saved region default still applies
    assert not restarted.native_baseline_allowed  # a saved policy is not a fresh one
    resolve(restarted)
    assert restarted.native_baseline_allowed


def test_new_baseline_preserves_build_disabled_and_no_replay_boundaries(
    tmp_path, monkeypatch
):
    owner = AnalyticsConsentOwner(tmp_path)
    resolve(owner)
    sink = Mock()
    telemetry = product.ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=tmp_path / "installation.json",
        app_version="0.2.6",
        enabled=False,
        baseline_permitted=lambda: owner.native_baseline_allowed,
        baseline_recorder=sink,
    )
    assert not telemetry.record_baseline("private_source_or_unknown")
    monkeypatch.setattr(product, "telemetry_collection_allowed", lambda: False)
    assert not telemetry.record_baseline("app_started")
    assert telemetry.shutdown(2)
    sink.assert_not_called()


def test_counter_exception_does_not_block_optional_delivery(tmp_path):
    owner = AnalyticsConsentOwner(tmp_path)
    owner.choose_data_sharing(True)
    resolve(owner)
    optional = []
    telemetry = product.ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=tmp_path / "installation.json",
        app_version="0.2.6",
        enabled=True,
        baseline_permitted=lambda: owner.native_baseline_allowed,
        baseline_recorder=Mock(side_effect=OSError("Controlled counter failure")),
        d1_recorder=lambda event: optional.append(event.event_name) or True,
        posthog_recorder=lambda event: True,
    )
    assert telemetry.record("run_completed")
    assert telemetry.shutdown(2)
    assert optional == ["run_completed"]


def test_baseline_http_request_contains_no_identifier_or_credential(
    tmp_path, monkeypatch
):
    owner = AnalyticsConsentOwner(tmp_path)
    resolve(owner)  # a default-on region, no explicit choice
    requests = []

    class Accepted:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def send(request, **kwargs):
        requests.append(request)
        return Accepted()

    monkeypatch.setattr(product, "telemetry_urlopen", send)
    telemetry = product.ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=tmp_path / "installation.json",
        app_version="0.2.6",
        enabled=False,
        baseline_permitted=lambda: owner.native_baseline_allowed,
    )
    assert telemetry.record_baseline("app_started")
    assert telemetry.shutdown(2)
    assert len(requests) == 1
    request = requests[0]
    assert request.full_url == "https://getvodforge.com/api/telemetry/baseline"
    assert set(json.loads(request.data)) == {
        "schema_version",
        "platform",
        "app_version",
        "metric",
        "count",
    }
    assert set(dict(request.header_items())) == {"Accept", "Content-type"}
    assert not (tmp_path / "telemetry-credential.json").exists()


@pytest.mark.parametrize(
    "version", ["private-canary", "0.2.6-dev.1", "0.2.6?token=private"]
)
def test_baseline_version_cannot_carry_private_or_unregistered_shape(tmp_path, version):
    sink = Mock()
    telemetry = product.ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=tmp_path / "installation.json",
        app_version=version,
        enabled=False,
        baseline_permitted=lambda: True,
        baseline_recorder=sink,
    )
    assert not telemetry.record_baseline("app_started")
    sink.assert_not_called()


def test_expired_policy_drops_pending_counts_without_retry(tmp_path, monkeypatch):
    owner = AnalyticsConsentOwner(tmp_path)
    resolve(owner)
    sink = Mock()
    telemetry = product.ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=tmp_path / "installation.json",
        app_version="0.2.6",
        enabled=False,
        baseline_permitted=lambda: owner.native_baseline_allowed,
        baseline_recorder=sink,
    )
    monkeypatch.setattr(telemetry, "flush_async", lambda: None)
    assert telemetry.record_baseline("app_started")
    owner._native_baseline_until = 0
    telemetry._flush_baseline()
    resolve(owner)
    telemetry._flush_baseline()
    sink.assert_not_called()
