from __future__ import annotations

from unittest.mock import Mock

import pytest

from yt_downloader.analytics_consent import AnalyticsConsentOwner
from yt_downloader.product_telemetry import ProductTelemetryOwner, _load_outbox
from yt_downloader.qt_quick import analytics

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


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
            heycatch_recorder=lambda *_args, **_kwargs: True,
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
