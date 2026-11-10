"""The update check at launch is recorded for users who never chose explicitly.

Production 0.2.6: 5 launches, no automatic update check recorded (0.2.5: 69
checks from 56 launches). At every launch the analytics region is re-checked in
the background, and until it answers a default-on user counts as not sharing.
The launch check started in that window, ran, and recorded nothing, so there
was no evidence that 0.2.6 checks for updates by itself. The check must still
start at once, so only its telemetry waits for the answer.
"""

from __future__ import annotations

import io
import json
import time

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication

from yt_downloader import cloud_funnel, product_telemetry
from yt_downloader.analytics_consent import AnalyticsConsentOwner
from yt_downloader.cloud_funnel import (
    load_or_create_installation_state,
    mark_attribution_claim_confirmed,
)
from yt_downloader.product_telemetry import _load_outbox
from yt_downloader.qt_quick import analytics as qt_analytics
from yt_downloader.qt_quick import main as qt_main
from yt_downloader.qt_quick import update_session

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


class Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


@pytest.mark.parametrize("region_delay", [0.0, 0.6])
def test_launch_check_is_recorded_while_region_is_rechecked(
    tmp_path, monkeypatch, region_delay
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.delenv("VODFORGE_DISABLE_TELEMETRY", raising=False)
    monkeypatch.setattr(qt_analytics, "telemetry_collection_allowed", lambda: True)
    # Nothing leaves the machine: delivery is off and the release feed fails.
    monkeypatch.setattr(
        product_telemetry.ProductTelemetryOwner, "flush_async", lambda _self: None
    )
    checks = []

    def fetch_latest_release():
        checks.append(time.monotonic())
        raise RuntimeError("offline")

    monkeypatch.setattr(update_session, "fetch_latest_release", fetch_latest_release)
    original = AnalyticsConsentOwner.resolve

    def resolve(self, *, opener=None, deadline=None):
        def policy(_request, timeout):
            time.sleep(region_delay)
            body = {"mode": "default-on", "resolved": True}
            return Response(json.dumps(body).encode())

        return original(self, opener=policy, deadline=deadline)

    monkeypatch.setattr(AnalyticsConsentOwner, "resolve", resolve)
    # A second launch in a default-on region: no explicit choice was ever made.
    path = cloud_funnel.installation_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    AnalyticsConsentOwner(path.parent).update(mode="default-on", region_checked=True)
    state = load_or_create_installation_state(path)
    mark_attribution_claim_confirmed(path, state.install_id)
    app = QGuiApplication.instance() or QGuiApplication([])
    bridge = qt_main.Bridge(None)
    try:
        telemetry = bridge._analytics.telemetry
        bridge.startSession()
        started = time.monotonic()
        QTimer.singleShot(0, bridge._auto_check_updates)  # as the packaged app does
        deadline = time.monotonic() + 6
        rows: list[dict] = []
        while time.monotonic() < deadline:
            app.processEvents()
            rows = [
                event.public_payload() for event in _load_outbox(telemetry._state_path)
            ]
            if any(
                row.get("action") == "failed"
                for row in rows
                if row.get("feature") == "updater_operation"
            ):
                break
            time.sleep(0.02)
        assert len(checks) == 1
        # The check itself never waits for the analytics answer: an available
        # update has to show as soon as the app opens.
        assert checks[0] - started < 0.3
        updater = [
            (row["action"], row["dimensions"]["update_trigger"])
            for row in rows
            if row.get("feature") == "updater_operation"
        ]
        assert updater[:2] == [("check_started", "automatic"), ("failed", "automatic")]
    finally:
        bridge.close()


@pytest.mark.parametrize("outcome", ["settled", "never_settled"])
def test_held_observations_are_recorded_in_order_or_dropped(tmp_path, outcome):
    from tests.test_presentation_diagnostics import real_owner
    from tests.test_qt_telemetry_coverage import rows

    telemetry = real_owner(tmp_path / "telemetry")
    session = update_session.QtUpdateSession("0.2.6")
    session.telemetry = telemetry
    settled = [False]
    session.consent_settled = lambda: settled[0]
    session._begin_observation("automatic")
    session.observe("check_started")
    session.observe("current")
    session.release_held_observations()  # still unsettled: keep holding
    if outcome == "settled":
        settled[0] = True
    else:
        session._held_until = 0.0  # the hold window has passed
    session.release_held_observations()
    session.observe("shown")  # after release, recorded directly
    actual = [
        (row["action"], row["dimensions"]["operation_step"])
        for row in rows(telemetry, tmp_path, "updater_operation")
    ]
    if outcome == "settled":
        assert actual == [("check_started", "1"), ("current", "2"), ("shown", "3")]
    else:
        assert actual == []
