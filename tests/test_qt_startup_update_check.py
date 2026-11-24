"""The update check at launch is recorded for users who never chose explicitly.

Production 0.2.6: 5 launches, no automatic update check recorded (0.2.5: 69
checks from 56 launches). At every launch the analytics region is re-checked in
the background, and until it answers a default-on user counts as not sharing.
The launch check started in that window, ran, and recorded nothing, so there
was no evidence that 0.2.6 checks for updates by itself. The saved answer now
stays in effect during the re-check (tests/test_qt_policy_refresh.py), and the
check must still start at once.
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
from yt_downloader.cloud_funnel import load_or_create_installation_state
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
    load_or_create_installation_state(path)
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


def _new_install(tmp_path, monkeypatch, *, mode: str, delay: float):
    """A new install whose region answers `mode` after `delay` seconds."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.delenv("VODFORGE_DISABLE_TELEMETRY", raising=False)
    monkeypatch.setattr(qt_analytics, "telemetry_collection_allowed", lambda: True)
    monkeypatch.setattr(
        product_telemetry.ProductTelemetryOwner, "flush_async", lambda _self: None
    )
    checks: list[float] = []

    def fetch_latest_release():
        checks.append(time.monotonic())
        raise RuntimeError("offline")

    monkeypatch.setattr(update_session, "fetch_latest_release", fetch_latest_release)
    original = AnalyticsConsentOwner.resolve

    def resolve(self, *, opener=None, deadline=None):
        def policy(_request, timeout):
            time.sleep(delay)
            body = {"mode": mode, "resolved": True}
            return Response(json.dumps(body).encode())

        return original(self, opener=policy, deadline=deadline)

    monkeypatch.setattr(AnalyticsConsentOwner, "resolve", resolve)
    # No saved analytics answer.
    path = cloud_funnel.installation_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    load_or_create_installation_state(path)
    app = QGuiApplication.instance() or QGuiApplication([])
    bridge = qt_main.Bridge(None)
    return app, bridge, checks


def _run(app, bridge, seconds: float, until=lambda: False) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and not until():
        app.processEvents()
        bridge._pump()
        time.sleep(0.02)


def _updater_actions(bridge) -> list[str]:
    return [
        event.public_payload()["action"]
        for event in _load_outbox(bridge._analytics.telemetry._state_path)
        if event.public_payload().get("feature") == "updater_operation"
    ]


def test_new_install_checks_at_once_and_again_once_analytics_answers(
    tmp_path, monkeypatch
):
    """Production 0.2.9: no new Mac reported its launch check. That check runs
    before the region answers, so it can't be recorded; it must still run at
    once, and one more check after the answer is recorded."""
    app, bridge, checks = _new_install(
        tmp_path, monkeypatch, mode="default-on", delay=0.6
    )
    try:
        bridge.startSession()
        started = time.monotonic()
        QTimer.singleShot(0, bridge._auto_check_updates)
        _run(app, bridge, 6, until=lambda: len(_updater_actions(bridge)) >= 2)
        assert checks and checks[0] - started < 0.3  # updates never wait
        assert len(checks) == 2
        assert checks[1] - started >= 0.5  # the second check followed the answer
        assert _updater_actions(bridge)[:2] == ["check_started", "failed"]
    finally:
        bridge.close()


@pytest.mark.parametrize("allow", [True, False])
def test_opt_in_install_rechecks_only_after_the_person_allows(
    tmp_path, monkeypatch, allow
):
    app, bridge, checks = _new_install(tmp_path, monkeypatch, mode="opt-in", delay=0)
    try:
        bridge.startSession()
        QTimer.singleShot(0, bridge._auto_check_updates)
        _run(app, bridge, 3.5)  # the region answers and the popup is shown
        assert len(checks) == 1
        assert _updater_actions(bridge) == []  # nothing before the answer
        bridge.chooseAnalytics(allow)
        _run(app, bridge, 3, until=lambda: len(_updater_actions(bridge)) >= 2)
        if allow:
            assert len(checks) == 2
            assert _updater_actions(bridge)[:2] == ["check_started", "failed"]
        else:
            assert len(checks) == 1
            assert _updater_actions(bridge) == []
    finally:
        bridge.close()
