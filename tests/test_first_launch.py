"""The first-launch report: sent once, retried until it arrives, then one
session report per launch. Nothing here contacts or opens a browser."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Self

import pytest

from yt_downloader import first_launch
from yt_downloader.analytics_consent import AnalyticsConsentOwner
from yt_downloader.cloud_funnel import (
    load_or_create_installation_state,
    mark_first_launch_confirmed,
)
from yt_downloader.first_launch import FirstLaunchDelivery

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


@pytest.fixture(autouse=True)
def permitted_analytics(tmp_path, monkeypatch):
    from yt_downloader import analytics_consent

    analytics_consent.AnalyticsConsentOwner(tmp_path).choose_data_sharing(True)
    monkeypatch.setattr(analytics_consent, "application_data_dir", lambda: tmp_path)


class PayloadResponse:
    status = 200

    def __init__(self, payload: dict[str, Any]) -> None:
        self._body = json.dumps(payload).encode()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self._body


def test_first_launch_is_reported_once(tmp_path: Path):
    path = tmp_path / "installation.json"
    original = load_or_create_installation_state(path)
    reported: list[tuple[str, str, str | None]] = []
    delivery = FirstLaunchDelivery(
        path,
        recorder=lambda state, *, app_version, platform_name: (
            reported.append((state.install_id, app_version, platform_name)) is None
        ),
    )
    assert delivery.needs_delivery(original)

    updated = delivery.deliver(original, app_version="0.3.0", platform_name="darwin")

    assert reported == [(original.install_id, "0.3.0", "darwin")]
    assert updated.first_launch_confirmed
    assert load_or_create_installation_state(path).first_launch_confirmed
    assert not delivery.needs_delivery(updated)
    assert delivery.deliver(updated, app_version="0.3.0") == updated
    assert len(reported) == 1


def test_a_failed_report_is_retried_on_a_later_launch(tmp_path: Path):
    path = tmp_path / "installation.json"
    original = load_or_create_installation_state(path)
    answers = [False, True]
    delivery = FirstLaunchDelivery(path, recorder=lambda *_a, **_k: answers.pop(0))

    unavailable = delivery.deliver(original, app_version="0.3.0")
    assert not unavailable.first_launch_confirmed
    assert delivery.needs_delivery(unavailable)

    delivered = delivery.deliver(unavailable, app_version="0.3.0")
    assert delivered.first_launch_confirmed
    assert answers == []


def test_nothing_is_reported_with_analytics_off(tmp_path: Path):
    path = tmp_path / "installation.json"
    original = load_or_create_installation_state(path)
    AnalyticsConsentOwner(tmp_path).choose_data_sharing(False)
    delivery = FirstLaunchDelivery(
        path, recorder=lambda *_a, **_k: pytest.fail("analytics are off")
    )
    assert delivery.deliver(original, app_version="0.3.0") == original
    assert not load_or_create_installation_state(path).first_launch_confirmed


def test_a_cancelled_or_test_build_run_reports_nothing(tmp_path: Path, monkeypatch):
    path = tmp_path / "installation.json"
    original = load_or_create_installation_state(path)
    delivery = FirstLaunchDelivery(
        path, recorder=lambda *_a, **_k: pytest.fail("must not report")
    )
    assert delivery.deliver(original, app_version="0.3.0", cancelled=lambda: True) == (
        original
    )
    monkeypatch.setattr(first_launch, "telemetry_collection_allowed", lambda: False)
    assert delivery.deliver(original, app_version="0.3.0") == original


def test_turning_analytics_off_during_the_report_leaves_it_unconfirmed(tmp_path: Path):
    path = tmp_path / "installation.json"
    original = load_or_create_installation_state(path)

    def report_then_withdraw(*_args, **_kwargs):
        AnalyticsConsentOwner(tmp_path).choose_data_sharing(False)
        return True

    FirstLaunchDelivery(path, recorder=report_then_withdraw).deliver(
        original, app_version="0.3.0"
    )
    assert not load_or_create_installation_state(path).first_launch_confirmed


def test_each_later_session_is_observed_once(tmp_path, monkeypatch):
    from yt_downloader import telemetry_credentials
    from yt_downloader.version import __version__

    monkeypatch.setattr(
        telemetry_credentials, "telemetry_collection_allowed", lambda: True
    )
    path = tmp_path / "installation.json"
    state = load_or_create_installation_state(path)
    state = mark_first_launch_confirmed(path, state.install_id)
    calls = []

    def opener(request, **_kwargs):
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

    for count in (2, 3):
        delivery = FirstLaunchDelivery(path)
        delivery._credentials.opener = opener
        assert delivery.needs_delivery(state)
        state = delivery.deliver(state, app_version=__version__)
        assert not delivery.needs_delivery(state)
        assert len(calls) == count
    assert calls == ["enroll", "launch", "launch"]
    assert all("attribution" not in call and "claim" not in call for call in calls)
