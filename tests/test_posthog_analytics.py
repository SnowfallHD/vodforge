import json
from dataclasses import replace
from uuid import uuid4

import pytest

from yt_downloader.analytics_consent import AnalyticsConsentOwner
from yt_downloader.cloud_funnel import (
    load_or_create_installation_state,
    mark_attribution_claim_confirmed,
)
from yt_downloader.posthog_analytics import (
    PosthogConfig,
    PosthogEventSink,
    capture_payload,
)
from yt_downloader.product_telemetry import (
    ProductTelemetryEvent,
    ProductTelemetryOwner,
    _load_outbox,
    _parse_event,
)

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


def event():
    return ProductTelemetryEvent(
        event_id=str(uuid4()),
        install_id=str(uuid4()),
        event_name="app_opened",
        occurred_at="2026-10-14T10:00:00Z",
        app_version="0.2.6",
        platform="windows",
        release_channel="production",
    )


def test_release_provider_is_available_but_environment_can_disable_it():
    assert PosthogConfig.from_environment({}).enabled
    assert not PosthogConfig.from_environment(
        {"VODFORGE_POSTHOG_ENABLED": "false"}
    ).enabled
    assert not PosthogConfig.from_environment(
        {"VODFORGE_POSTHOG_PUBLIC_KEY": "phc_otherproject12345"}
    ).enabled
    assert not PosthogEventSink(
        PosthogConfig(True, "phc_abcdefghijkl", "https://private.invalid")
    ).enabled
    assert not PosthogEventSink(
        PosthogConfig(True, "phc_abcdefghijkl", "https://eu.i.posthog.com")
    ).enabled


@pytest.mark.parametrize(
    "field",
    ["event_id", "install_id", "occurred_at", "app_version", "event_name", "feature"],
)
def test_injected_private_identifiers_and_vocabulary_are_rejected(field):
    assert (
        capture_payload(replace(event(), **{field: "private/path?email=secret"}))
        is None
    )


def test_projection_excludes_private_context_and_raw_identity():
    e = replace(
        event(),
        dimensions={"path": "PRIVATE", "email": "PRIVATE"},
        failure_reason="PRIVATE",
    )
    p = capture_payload(e)
    assert p and "PRIVATE" not in json.dumps(p)
    assert e.install_id not in json.dumps(p)
    assert p["properties"]["$insert_id"] == e.event_id
    assert p["uuid"] == e.event_id
    assert p["properties"]["$ip"] == "0.0.0.0"
    assert "posthog_epoch" not in e.public_payload()


def test_projection_retains_bounded_performance_and_failure_facts():
    from yt_downloader.failure_diagnostics import FailureDiagnostic

    e = replace(
        event(),
        event_name="run_failed",
        dimensions={
            "processing_bucket": "under_1m",
            "wait_bucket": "under_10s",
            "preset": "editing",
            "encoder": "cpu",
            "path": "PRIVATE",
            "stage": "PRIVATE",
        },
        failure_detail=FailureDiagnostic(stage="transcode"),
    )
    p = capture_payload(e)
    assert p
    assert p["properties"]["processing_bucket"] == "under_1m"
    assert p["properties"]["wait_bucket"] == "under_10s"
    assert p["properties"]["preset"] == "editing"
    assert p["properties"]["encoder"] == "cpu"
    assert p["properties"]["failure_stage"] == "transcode"
    assert "PRIVATE" not in json.dumps(p)


@pytest.mark.parametrize("value", ["PRIVATE/path", None, 42, ["under_1m"]])
def test_projection_rejects_injected_performance_values(value):
    p = capture_payload(replace(event(), dimensions={"processing_bucket": value}))
    assert p and "processing_bucket" not in p["properties"]


def test_optional_corruption_does_not_break_primary_event():
    e = event()
    value = {**e.public_payload(), "posthog_epoch": "invalid"}
    parsed = _parse_event(value)
    assert parsed.event_id == e.event_id and parsed.posthog_epoch is None


class Sink:
    enabled = True

    def __init__(self, result=False):
        self.events = []
        self.result = result

    def __call__(self, e):
        self.events.append(e)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def permitted(tmp_path):
    consent = AnalyticsConsentOwner(tmp_path)
    consent.choose(True)
    state = load_or_create_installation_state(tmp_path / "installation.json")
    mark_attribution_claim_confirmed(tmp_path / "installation.json", state.install_id)
    return consent


def owner(tmp_path, sink, d1):
    return ProductTelemetryOwner(
        state_path=tmp_path / "events.json",
        installation_state_path=tmp_path / "installation.json",
        app_version="0.2.6",
        d1_recorder=d1,
        posthog_recorder=sink,
    )


@pytest.mark.parametrize("result", [False, RuntimeError("PRIVATE")])
def test_provider_failure_never_prevents_primary_ack(tmp_path, result):
    consent = permitted(tmp_path)
    consent.choose_posthog(True)
    sink = Sink(result)
    primary = []
    o = owner(tmp_path, sink, lambda e: primary.append(e.event_id) is None)
    assert o.record_app_opened() and o.shutdown(3)
    assert len(sink.events) == len(primary) == 1
    assert not (tmp_path / "events.json").exists()


def test_primary_retry_never_repeats_secondary_attempt(tmp_path):
    consent = permitted(tmp_path)
    consent.choose_posthog(True)
    sink = Sink(False)
    o = owner(tmp_path, sink, lambda e: False)
    assert o.record_app_opened() and o.shutdown(3)
    assert _load_outbox(tmp_path / "events.json")[0].posthog_attempted
    o.flush_async()
    assert o.shutdown(3)
    assert len(sink.events) == 1


def test_old_custom_consent_does_not_opt_into_new_provider(tmp_path):
    consent = permitted(tmp_path)
    sink = Sink()
    assert not consent.posthog_allowed
    o = owner(tmp_path, sink, lambda e: True)
    assert o.record_app_opened() and o.shutdown(3)
    assert sink.events == []


def test_reenrollment_invalidates_admitted_provider_epoch(tmp_path):
    consent = permitted(tmp_path)
    consent.choose_posthog(True)
    sink = Sink()
    o = owner(tmp_path, sink, lambda e: False)
    e = replace(event(), posthog_epoch=consent.snapshot()["posthog_epoch"])
    consent.choose_posthog(False)
    consent.choose_posthog(True)
    assert o._mirror_posthog(e, 0)
    assert sink.events == []


@pytest.mark.parametrize(
    "ack,already,closed,revoke,expected",
    [
        (True, False, False, False, 1),
        (False, False, False, False, 0),
        (True, True, False, False, 0),
        (True, False, True, False, 0),
        (True, False, False, True, 0),
        (True, False, False, "custom", 0),
    ],
)
def test_first_run_requires_new_ack_current_consent_and_open_owner(
    tmp_path, monkeypatch, ack, already, closed, revoke, expected
):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from yt_downloader.qt_quick import analytics

    consent = permitted(tmp_path)
    consent.choose_posthog(True)
    sink = Sink(True)
    sink.first_run_confirmed = lambda e: sink.events.append(e) is None
    monkeypatch.setattr(
        analytics,
        "ProductTelemetryOwner",
        lambda **kw: ProductTelemetryOwner(
            **kw, d1_recorder=lambda e: True, posthog_recorder=sink
        ),
    )
    monkeypatch.setattr(analytics, "telemetry_collection_allowed", lambda: True)
    session = analytics.QtAnalyticsSession(tmp_path, "0.2.6", Mock())
    state = load_or_create_installation_state(tmp_path / "installation.json")
    monkeypatch.setattr(
        analytics,
        "load_or_create_installation_state",
        lambda p: replace(state, first_launch_confirmed=already),
    )
    session._attribution.needs_delivery = lambda state: True

    def deliver(state, **kw):
        session._closed = closed
        if revoke == "custom":
            consent.choose(False)
            consent.choose(True)
        elif revoke:
            consent.choose_posthog(False)
            consent.choose_posthog(True)
        return SimpleNamespace(first_launch_confirmed=ack)

    session._attribution.deliver_first_launch = deliver
    session.start_first_launch_delivery()
    import time

    for _ in range(100):
        if session._attribution_work.poll() is not None:
            break
        time.sleep(0.01)
    assert len(sink.events) == expected
    session.close()


def test_optional_first_run_admission_error_is_fail_closed(tmp_path, monkeypatch):
    consent = permitted(tmp_path)
    consent.choose_posthog(True)
    o = owner(tmp_path, Sink(), lambda e: True)
    monkeypatch.setattr(
        o, "_consent_epoch", lambda: (_ for _ in ()).throw(ValueError("PRIVATE"))
    )
    assert o.posthog_admission_epoch() is None
