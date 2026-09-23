from __future__ import annotations

import time

import pytest

from yt_downloader.qt_quick.support import QtSupportSession
from yt_downloader.support_diagnostics import FailureContext
from yt_downloader.support_payload import feedback_payload, review_payload
from yt_downloader.support_transport import SubmissionError


def test_explicit_feedback_consent_controls_private_diagnostics_and_url():
    context = FailureContext("bounded diagnostic", "https://example.com/private")
    ordinary = feedback_payload(reason="Other", message="  Hello  ", context=context)
    assert ordinary["message"] == "Hello"
    assert ordinary["diagnostics"] == ordinary["video_url"] == ""
    included = feedback_payload(
        reason="Download problem",
        message="Report",
        include_diagnostics=True,
        include_video_url=True,
        context=context,
    )
    assert included["diagnostics"] == "bounded diagnostic"
    assert included["video_url"] == "https://example.com/private"


def test_support_payload_rejects_invalid_input_before_delivery():
    with pytest.raises(ValueError, match="select a reason"):
        feedback_payload(reason="Other private text", message="Report")
    with pytest.raises(ValueError, match="enter a message"):
        feedback_payload(reason="Other", message="  ")
    with pytest.raises(ValueError, match="reply email"):
        feedback_payload(reason="Other", message="Report", reply=True, email="broken")
    with pytest.raises(ValueError, match="rating"):
        review_payload(stars=0, comment="")
    with pytest.raises(ValueError, match="display name"):
        review_payload(stars=5, comment="", display_name="x" * 81)
    public = review_payload(stars=5, comment="Thanks", display_name="")
    assert public["publication_consent"] is True
    assert public["display_name"] == "Anonymous"


def test_qt_support_preserves_input_identity_and_requires_explicit_submission(tmp_path):
    class Transport:
        def __init__(self):
            self.calls = []

        def submit(self, kind, payload, request_id):
            self.calls.append((kind, payload, request_id))
            if len(self.calls) == 1:
                raise SubmissionError("Injected failure")
            return request_id

    transport = Transport()
    owner = QtSupportSession(tmp_path, transport=transport)
    assert owner.open("feedback")
    assert not owner.submit({"reason": "Other", "message": ""})
    assert transport.calls == []
    assert owner.submit({"reason": "Other", "message": "Report"})
    assert owner.busy
    assert not owner.close()
    deadline = time.monotonic() + 2
    while not owner.poll() and time.monotonic() < deadline:
        time.sleep(0.005)
    assert not owner.busy and not owner.sent
    assert owner.submit({"reason": "Other", "message": "Report"})
    deadline = time.monotonic() + 2
    while not owner.poll() and time.monotonic() < deadline:
        time.sleep(0.005)
    assert owner.sent
    assert len(transport.calls) == 2
    assert transport.calls[0][2] == transport.calls[1][2]
    assert not owner.submit({"reason": "Other", "message": "Report"})
    assert owner.close()
