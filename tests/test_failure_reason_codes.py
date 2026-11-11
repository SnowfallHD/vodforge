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


def test_reuse_mismatch_without_an_error_is_a_validation_outcome():
    """An existing file that doesn't match the new settings was sent as unknown."""
    from yt_downloader.download_service import _report_reuse_rejection

    reported = []
    _report_reuse_rejection(
        lambda reason, detail: reported.append((reason, detail)), "plan_mismatch"
    )
    ((reason, detail),) = reported
    assert reason == "plan_mismatch"
    assert (detail.reason, detail.stage) == ("validation", "reuse")


@pytest.mark.parametrize(
    ("error", "staged", "reason", "stage"),
    [
        # A refused input while preparing: the user's file, not a fault.
        (
            "The selected audio is not a valid, playable MP3 file.",
            "preparation",
            "invalid_input",
            "preparation",
        ),
        # The owner knows where it failed; the stage used to be "processing".
        ("encoder said no", "transcode", "unknown", "transcode"),
    ],
)
def test_local_conversion_reports_the_owners_stage_and_known_reason(
    monkeypatch, error, staged, reason, stage
):
    from yt_downloader.failure_diagnostics import FailureDiagnostic
    from yt_downloader.local_audio_video import LocalAudioVideoError
    from yt_downloader.qt_quick import local_conversion

    runtime = local_conversion.LocalConversionRuntime.__new__(
        local_conversion.LocalConversionRuntime
    )
    runtime.events = __import__("queue").Queue()
    observed = []
    runtime._observe = lambda *_a, failure_detail=None, **_k: observed.append(
        failure_detail
    )
    runtime._report_failure(
        "run", LocalAudioVideoError(error), [FailureDiagnostic(stage=staged)]
    )
    assert (observed[0].reason, observed[0].stage) == (reason, stage)


def test_local_conversion_missing_runtime_is_a_dependency_failure():
    from yt_downloader.local_audio_video import LocalAudioVideoError
    from yt_downloader.qt_quick import local_conversion

    runtime = local_conversion.LocalConversionRuntime.__new__(
        local_conversion.LocalConversionRuntime
    )
    runtime.events = __import__("queue").Queue()
    observed = []
    runtime._observe = lambda *_a, failure_detail=None, **_k: observed.append(
        failure_detail
    )
    runtime._report_failure(
        "run",
        LocalAudioVideoError(
            "FFmpeg runtime is unavailable.", reason="dependency_missing"
        ),
    )
    assert observed[0].reason == "dependency_missing"


@pytest.mark.parametrize(
    ("message", "reason"),
    [
        (
            "The release update failed SHA-256 verification and was not opened.",
            "validation",
        ),
        ("Windows rejected the update's Authenticode signature.", "validation"),
        ("The app folder is not writable.", "permission_denied"),
        (
            "This release does not include an update for this computer.",
            "source_unavailable",
        ),
    ],
)
def test_update_failures_carry_their_reason_without_reading_the_message(
    message, reason
):
    """Update errors are captured without their text, so nearly all were
    reported as unknown."""
    from yt_downloader import updates

    source = __import__("inspect").getsource(updates)
    assert message in source  # the real message, raised as an UpdateError
    error = updates.UpdateError(message, reason=reason)
    detail = capture_failure(
        error, stage="download", inspect_text=False, context="updater"
    )
    assert detail.reason == reason
