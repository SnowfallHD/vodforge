import json
import os
import time
import urllib.error
from email.message import Message

import pytest

from yt_downloader.support_transport import SubmissionError, SupportTransport


def test_identity_is_lazy_private_and_not_telemetry(tmp_path):
    transport = SupportTransport(tmp_path)
    assert not list(tmp_path.iterdir())
    credential = transport._credential()
    assert SupportTransport(tmp_path)._credential() == credential
    assert [p.name for p in tmp_path.iterdir()] == ["support-credential.json"]
    # Windows stat mode bits do not represent NTFS access-control entries.
    if os.name != "nt":
        assert transport.path.stat().st_mode & 0o077 == 0


@pytest.mark.parametrize(
    "value", [{}, {"credential_id": None}, {"credential_id": "bad", "secret": 12}]
)
def test_invalid_credentials_fail_closed_without_replacing(tmp_path, value):
    transport = SupportTransport(tmp_path)
    transport.path.write_text(json.dumps(value))
    with pytest.raises(SubmissionError):
        transport._credential()
    assert json.loads(transport.path.read_text()) == value


def test_only_exact_server_receipt_is_success_and_retry_keeps_id(tmp_path, monkeypatch):
    transport = SupportTransport(tmp_path)
    calls = []

    def post(action, body, credential):
        calls.append((action, body))
        return {"ok": True, "reference": body.get("request_id")}

    monkeypatch.setattr(transport, "_post", post)
    for _ in range(2):
        assert transport.submit("feedback", {"message": "hi"}, "same-id") == "same-id"
    assert calls[1][1] == calls[3][1]
    monkeypatch.setattr(
        transport, "_post", lambda *args: {"ok": True, "reference": "wrong"}
    )
    with pytest.raises(SubmissionError):
        transport.submit("review", {}, "same-id")


def test_rate_limit_stops_immediate_retry(tmp_path, monkeypatch):
    transport = SupportTransport(tmp_path)
    headers = Message()
    headers["Retry-After"] = "120"

    class Opener:
        def open(self, *args, **kwargs):
            raise urllib.error.HTTPError(
                "https://getvodforge.com", 429, "limited", headers, None
            )

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    with pytest.raises(SubmissionError):
        transport.submit("feedback", {}, "id")
    assert transport.retry_after > time.monotonic() + 100
    monkeypatch.setattr(
        transport, "_post", lambda *args: pytest.fail("retry reached network")
    )
    with pytest.raises(SubmissionError):
        transport.submit("feedback", {}, "id")


def test_browser_challenge_is_trusted_explicit_and_never_delivery(
    tmp_path, monkeypatch
):
    from yt_downloader.support_transport import VerificationRequired

    transport = SupportTransport(tmp_path)
    opened = []
    monkeypatch.setattr("webbrowser.open", opened.append)
    target = "https://getvodforge.com/support/verify/#" + "a" * 43
    monkeypatch.setattr(
        transport, "_post", lambda *args: {"ok": True, "verification_url": target}
    )
    with pytest.raises(VerificationRequired):
        transport.submit("feedback", {}, "id")
    assert opened == [target]
    monkeypatch.setattr(
        transport,
        "_post",
        lambda *args: {"ok": True, "verification_url": "https://attacker.invalid"},
    )
    with pytest.raises(SubmissionError):
        transport.submit("feedback", {}, "id")
    assert opened == [target]
