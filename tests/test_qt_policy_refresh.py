"""The launch policy refresh never drops, wipes or leaks analytics.

At every launch the app asks the server for the region's analytics policy. Until
0.2.6 it first erased the saved answer, then raced a 2.5 s timer:

- events recorded before the answer (the launch update check, resumed downloads,
  anonymous counts) were dropped for users who never chose explicitly;
- on a slow network the timer won: the app wiped unsent events, asked a
  default-on user for consent, and recorded nothing for the rest of the session.

Now the saved answer stays in effect, events are recorded as usual but nothing
is sent until the answer arrives, and an answer that turns analytics off deletes
what was held before it leaves the computer.
"""

from __future__ import annotations

import io
import json
import threading
import time
from unittest.mock import Mock

import pytest

from yt_downloader.analytics_consent import AnalyticsConsentOwner
from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox
from yt_downloader.qt_quick import analytics

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


class Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def start_session(tmp_path, monkeypatch, answer):
    """A returning default-on user; the policy answer waits for `release`."""
    monkeypatch.setattr(analytics, "telemetry_collection_allowed", lambda: True)
    AnalyticsConsentOwner(tmp_path).update(mode="default-on", region_checked=True)
    sent, counts, release = [], [], threading.Event()

    def factory(**kwargs):
        return ProductTelemetryOwner(
            **kwargs,
            d1_recorder=lambda event: sent.append(event.event_name) or True,
            baseline_recorder=lambda payload: counts.append(payload["metric"]) or True,
        )

    monkeypatch.setattr(analytics, "ProductTelemetryOwner", factory)
    original = AnalyticsConsentOwner.resolve

    def resolve(self, *, opener=None, deadline=None):
        def policy(_request, timeout):
            assert release.wait(5)  # the server takes its time
            return Response(json.dumps(answer).encode())

        return original(self, opener=policy, deadline=None)

    monkeypatch.setattr(AnalyticsConsentOwner, "resolve", resolve)
    session = analytics.QtAnalyticsSession(tmp_path, "0.2.7", Mock())
    session.start()
    return session, sent, counts, release


def settle(session, until=lambda: True):
    """Wait for the refresh, then for the app's own send after it."""
    assert session._resolved.wait(5)
    deadline = time.monotonic() + 5
    while not until() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert session.telemetry.shutdown(2)


DEFAULT_ON = {
    "mode": "default-on",
    "resolved": True,
    "native_baseline_version": 1,
    "native_baseline_mode": "enabled",
}


def test_slow_answer_keeps_the_saved_choice_and_sends_held_events(
    tmp_path, monkeypatch
):
    session, sent, counts, release = start_session(tmp_path, monkeypatch, DEFAULT_ON)
    telemetry = session.telemetry
    assert telemetry.record_feature("library", "opened")  # recorded, not sent yet
    assert telemetry.record_baseline("app_started")
    assert telemetry.shutdown(2)
    assert sent == [] and counts == []
    session._deadline = 0  # the 2.5 s timer has run out before the answer
    assert session.poll() is False  # no consent question for a default-on user
    assert telemetry.permitted()
    assert len(_load_outbox(tmp_path / "product-telemetry.json")) >= 1
    release.set()
    settle(session, until=lambda: "feature_used" in sent and counts)
    assert "feature_used" in sent
    assert counts == ["app_started"]
    session.close()


def test_answer_that_turns_analytics_off_sends_nothing_held(tmp_path, monkeypatch):
    # The user moved to a region where sharing needs an explicit yes.
    session, sent, counts, release = start_session(
        tmp_path, monkeypatch, {"mode": "opt-in", "resolved": True}
    )
    telemetry = session.telemetry
    assert telemetry.record_feature("library", "opened")
    telemetry.record_baseline("app_started")
    release.set()
    settle(session)
    deadline = time.monotonic() + 5
    while not session.poll() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert sent == [] and counts == []
    assert not _load_outbox(tmp_path / "product-telemetry.json")
    session.close()


@pytest.mark.parametrize("answer", [DEFAULT_ON, {"resolved": False}])
def test_saved_choice_stays_in_effect_while_and_after_the_refresh(
    tmp_path, monkeypatch, answer
):
    session, _sent, _counts, release = start_session(tmp_path, monkeypatch, answer)
    owner = session.owner
    assert owner.allowed  # during the refresh
    release.set()
    settle(session)
    assert owner.allowed  # a confirming or inconclusive answer keeps it
    session.close()


def test_counts_pending_at_quit_are_sent_before_the_session_closes(
    tmp_path, monkeypatch
):
    """Closing the session stops anonymous counts, and they live only in memory,
    so a count queued by the last download was lost at quit."""
    session, _sent, counts, release = start_session(tmp_path, monkeypatch, DEFAULT_ON)
    release.set()
    settle(session)
    with session.telemetry._lock:
        session.telemetry._baseline_pending["run_completed"] = 1  # not yet sent
    session.close()
    assert counts == ["run_completed"]
