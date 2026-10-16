"""Explicit rights admission uses only existing ownership, not analytics opt-in."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from yt_downloader.analytics_consent import AnalyticsConsentOwner
from yt_downloader.private_files import write_private_bytes
from yt_downloader.qt_quick.analytics import QtAnalyticsSession
from yt_downloader.telemetry_credentials import TelemetryCredentialOwner

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")
CREDENTIAL = "f9c775b1-4c5a-47c4-87bb-81fe51881e54"
REQUEST = "adb7526b-116c-413e-82dd-9fd42a89193a"
TOKEN = "x" * 43


def seed(directory):
    write_private_bytes(
        directory / "telemetry-credential.json",
        json.dumps({"credential_id": CREDENTIAL, "secret": "a" * 43}).encode(),
    )


class Response:
    status = 200

    def __init__(self, **changes):
        self.value = {
            "ok": True,
            "schema_version": 1,
            "request_id": REQUEST,
            "request_kind": "deletion",
            "state": "awaiting_confirmation",
            "request_url": f"https://getvodforge.com/privacy/request/#token={TOKEN}",
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(minutes=15)
            ).isoformat(),
            **changes,
        }

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, limit):
        assert limit == 4097
        return json.dumps(self.value).encode()


def test_rights_action_works_with_optional_off_but_never_creates_identity(tmp_path):
    consent = AnalyticsConsentOwner(tmp_path)
    consent.choose_data_sharing(False)
    calls = []

    def opener(request, **kwargs):
        calls.append(json.loads(request.data))
        assert request.full_url == "https://getvodforge.com/api/privacy/requests/issue"
        assert request.get_header("Authorization") == "Bearer " + "a" * 43
        assert kwargs["timeout"] == 4.0
        return Response()

    owner = TelemetryCredentialOwner(tmp_path, opener=opener)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert owner.issue_privacy_request("deletion", permitted=lambda: True) is None
    assert calls == []
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    seed(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert (
        owner.issue_privacy_request("deletion", permitted=lambda: True)
        == f"https://getvodforge.com/privacy/request/#token={TOKEN}"
    )
    assert calls == [
        {"schema_version": 1, "credential_id": CREDENTIAL, "request_kind": "deletion"}
    ]
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert not consent.allowed


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": True},
        {"state": "completed"},
        {"request_kind": "access"},
        {"request_id": "bad"},
        {"request_url": f"https://evil.example/privacy/request/#token={TOKEN}"},
        {
            "request_url": f"https://getvodforge.com/privacy/request/#token={TOKEN}&extra=x"
        },
        {"expires_at": "2000-01-01T00:00:00Z"},
        {"expires_at": "2100-01-01T00:00:00Z"},
        {"expires_at": 123},
    ],
)
def test_rights_response_refuses_wrong_identity_route_completion_or_expiry(
    tmp_path, changes
):
    seed(tmp_path)
    owner = TelemetryCredentialOwner(
        tmp_path, opener=lambda *a, **kw: Response(**changes)
    )
    assert owner.issue_privacy_request("deletion", permitted=lambda: True) is None


def test_rights_response_after_close_does_not_open_capability(tmp_path):
    seed(tmp_path)
    active = [True]

    def opener(*a, **kw):
        active[0] = False
        return Response()

    owner = TelemetryCredentialOwner(tmp_path, opener=opener)
    assert owner.issue_privacy_request("deletion", permitted=lambda: active[0]) is None


def test_help_rights_fallback_does_not_enroll_or_expose_install_id(
    tmp_path, monkeypatch
):
    from yt_downloader.qt_quick import analytics

    monkeypatch.setattr(analytics, "telemetry_collection_allowed", lambda: True)
    session = QtAnalyticsSession(tmp_path, "0.2.6", Mock())
    opened = []
    assert session.request_privacy_action(
        "deletion", lambda url: opened.append(url) or True
    )
    assert opened == ["https://getvodforge.com/privacy/"]
    assert not (tmp_path / "telemetry-credential.json").exists()
    assert not session.request_privacy_action(
        "unsupported", lambda url: pytest.fail("invalid action")
    )
    session.close()
    assert session.telemetry.shutdown(2)


def test_ownership_request_explicitly_disables_redirects(tmp_path, monkeypatch):
    from yt_downloader import telemetry_credentials

    seed(tmp_path)

    def opener(request, **kwargs):
        assert kwargs == {"timeout": 4.0, "follow_redirects": False}
        return Response()

    monkeypatch.setattr(telemetry_credentials, "telemetry_urlopen", opener)
    owner = TelemetryCredentialOwner(tmp_path, opener=opener)
    assert owner.issue_privacy_request("deletion", permitted=lambda: True)


def test_fresh_rights_capability_is_independent_from_usage_choice(
    tmp_path, monkeypatch
):
    from yt_downloader.qt_quick import analytics
    from tests.test_attribution_permission import PolicyResponse
    import threading
    import time

    monkeypatch.setattr(analytics, "telemetry_collection_allowed", lambda: True)
    session = QtAnalyticsSession(tmp_path, "0.2.6", Mock())
    session.owner.choose_data_sharing(False)
    session.owner.resolve(
        opener=lambda *a, **kw: PolicyResponse(
            resolved=True, privacy_requests_version=1
        )
    )
    assert session.owner.privacy_requests_available and not session.allowed
    gui = threading.get_ident()

    def issue(owner, kind, *, permitted):
        assert threading.get_ident() != gui
        assert kind == "deletion" and permitted()
        return f"https://getvodforge.com/privacy/request/#token={TOKEN}"

    monkeypatch.setattr(TelemetryCredentialOwner, "issue_privacy_request", issue)
    opened = []

    def open_browser(url):
        assert threading.get_ident() == gui
        opened.append(url)
        return True

    assert session.request_privacy_action("deletion", open_browser)
    assert not session.request_privacy_action("deletion", open_browser)
    deadline = time.monotonic() + 2
    while session._privacy_work is not None and time.monotonic() < deadline:
        session.poll_first_launch_delivery()
        time.sleep(0.005)
    assert opened == [f"https://getvodforge.com/privacy/request/#token={TOKEN}"]
    assert not session.allowed and not (tmp_path / "telemetry-credential.json").exists()
    session.close()
    assert session.telemetry.shutdown(2)
