"""Failure reasons agree with the specific failure code.

In production telemetry an age-restricted video was reported with reason
authentication_required, members-only and geo-blocked videos as
provider_extraction, and a video ID containing "429" as rate limiting. The code
was right; the reason was guessed from other words in the message.
"""

from __future__ import annotations

import pytest

from yt_downloader.failure_diagnostics import capture_failure

CASES = [
    (
        (
            "[youtube] abc123def45: Sign in to confirm your age. "
            "This video may be inappropriate for some users."
        ),
        "age_restricted",
        "source_restricted",
    ),
    (
        (
            "[youtube] abc123def45: Join this channel to get access to members-only "
            "content like this video"
        ),
        "members_only",
        "source_restricted",
    ),
    (
        (
            "[youtube] abc123def45: The uploader has not made this video available "
            "in your country"
        ),
        "geo_restricted",
        "source_restricted",
    ),
    (
        (
            "Could not copy Chrome cookie database. "
            "See https://github.com/yt-dlp/yt-dlp/issues/7271"
        ),
        "cookies_unavailable",
        "authentication_required",
    ),
    (
        "[youtube] ab4291xyzQQ: Video unavailable",  # "429" inside the video ID
        "video_unavailable",
        "source_unavailable",
    ),
    (
        "Unable to download webpage: HTTP Error 429: Too Many Requests",
        None,
        "rate_limited",
    ),
]


@pytest.mark.parametrize(("message", "code", "reason"), CASES)
def test_reason_follows_the_failure_code(message, code, reason):
    detail = capture_failure(RuntimeError("ERROR: " + message), stage="analysis")
    assert (detail.failure_code, detail.reason) == (code, reason)


def test_bare_status_numbers_in_ids_are_not_http_errors():
    for text in ("[youtube] x404abcdefg: something odd", "ab4291xyzQQ failed"):
        detail = capture_failure(RuntimeError(text), stage="analysis")
        assert detail.reason not in {"rate_limited", "source_unavailable"}
