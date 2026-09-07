import json

import pytest

from yt_downloader import analytics_consent as consent
from yt_downloader.analytics_consent import AnalyticsConsentOwner


@pytest.mark.parametrize(
    "mode,allowed", [("default-on", True), ("opt-in", False), ("unknown", False)]
)
def test_policy_defaults_and_durable_opt_out(tmp_path, monkeypatch, mode, allowed):
    monkeypatch.setattr(consent, "production_telemetry_allowed", lambda: True)
    owner = AnalyticsConsentOwner(tmp_path)
    owner.update(mode=mode)
    assert owner.allowed is allowed
    owner.choose(False)
    owner.update(mode="default-on")
    assert not AnalyticsConsentOwner(tmp_path).allowed
    owner.choose(True)
    assert owner.allowed


def test_region_request_has_no_identity_and_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(consent, "production_telemetry_allowed", lambda: True)

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, size):
            return json.dumps({"mode": "default-on"}).encode()

    def opener(request, timeout):
        assert request.data is None
        assert "?" not in request.full_url
        assert set(request.headers) == {"Accept"}
        assert timeout == 1.5
        return Response()

    owner = AnalyticsConsentOwner(tmp_path)
    assert owner.resolve(opener=opener) == "default-on"
    assert owner.allowed

    def offline(*args, **kwargs):
        raise OSError()

    assert owner.resolve(opener=offline) == "unknown"
    assert not owner.allowed


def test_welcome_opportunity_is_once_and_builds_fail_closed(tmp_path, monkeypatch):
    owner = AnalyticsConsentOwner(tmp_path)
    assert owner.take_welcome()
    assert not AnalyticsConsentOwner(tmp_path).take_welcome()
    owner.choose(True)
    monkeypatch.setattr(consent, "production_telemetry_allowed", lambda: False)
    assert not consent.analytics_allowed(tmp_path)


def test_legacy_opt_out_is_preserved(tmp_path):
    assert not AnalyticsConsentOwner(tmp_path, legacy_disabled=True).allowed
    assert AnalyticsConsentOwner(tmp_path).snapshot()["choice"] == "denied"
