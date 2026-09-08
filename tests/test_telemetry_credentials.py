import json

import pytest

from yt_downloader import telemetry_credentials as module


@pytest.fixture(autouse=True)
def permitted_analytics(tmp_path, monkeypatch):
    from yt_downloader import analytics_consent

    monkeypatch.setattr(analytics_consent, "telemetry_collection_allowed", lambda: True)
    analytics_consent.AnalyticsConsentOwner(tmp_path).choose(True)


class Response:
    status = 200

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, _size):
        return json.dumps(self.body).encode()


def test_version_observation_is_browserless_and_only_repeats_on_version_change(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(module, "telemetry_collection_allowed", lambda: True)
    calls = []

    def opener(request, **_kwargs):
        body = json.loads(request.data)
        calls.append((request.full_url, body))
        return Response(
            {
                "ok": True,
                "enrolled": True,
                "launched": True,
                "credential_id": body["credential_id"],
                "install_id": module.load_or_create_installation_state(
                    tmp_path / "installation.json"
                ).install_id,
                "app_version": body["app_version"],
            }
        )

    owner = module.TelemetryCredentialOwner(tmp_path, opener=opener)
    assert owner.first_launch("0.1.8", "macos")
    assert owner.first_launch("0.1.8", "macos")
    assert len(calls) == 2
    assert owner.first_launch("0.1.9", "macos")
    assert len(calls) == 4
    assert calls[0][1]["install_id"] == calls[2][1]["install_id"]
    assert owner.launch_confirmed("0.1.9")
    assert not owner.launch_confirmed("0.1.8")


def test_unacknowledged_version_is_retried_without_regenerating_identity(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(module, "telemetry_collection_allowed", lambda: True)
    owner = module.TelemetryCredentialOwner(
        tmp_path, opener=lambda *_a, **_k: Response({"ok": False})
    )
    assert not owner.first_launch("0.1.8", "macos")
    original = owner.path.read_bytes()
    assert not owner.first_launch("0.1.8", "macos")
    assert original == owner.path.read_bytes()
    assert not owner.receipt.exists()


def test_suppressed_build_creates_no_credential_or_request(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "telemetry_collection_allowed", lambda: False)

    def forbidden(*_a, **_k):
        raise AssertionError("network must be suppressed")

    owner = module.TelemetryCredentialOwner(tmp_path, opener=forbidden)
    assert not owner.first_launch("0.1.8", "macos")
    assert {path.name for path in tmp_path.iterdir()} == {"analytics-consent.json"}


def test_rate_limit_backoff_survives_owner_recreation(tmp_path, monkeypatch):
    from urllib.error import HTTPError

    monkeypatch.setattr(module, "telemetry_collection_allowed", lambda: True)
    calls = []

    def failing(request, **_kwargs):
        calls.append(request)
        raise HTTPError(request.full_url, 429, "limited", {"Retry-After": "3600"}, None)

    assert not module.TelemetryCredentialOwner(tmp_path, opener=failing).first_launch(
        "0.1.8", "macos"
    )
    assert not module.TelemetryCredentialOwner(tmp_path, opener=failing).first_launch(
        "0.1.8", "macos"
    )
    assert len(calls) == 1
    assert not (tmp_path / "telemetry-launch-receipt.json").exists()
