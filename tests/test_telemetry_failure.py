import pytest

from yt_downloader.failure_diagnostics import FAILURE_REASONS, classify_failure


@pytest.mark.parametrize(
    ("message", "reason"),
    [
        ("ERROR: No space left on device /private/person/video.mp4", "disk_full"),
        ("HTTP Error 429: Too Many Requests", "rate_limited"),
        (
            "Sign in to confirm your age https://private.invalid/video",
            "authentication_required",
        ),
        ("Video unavailable", "source_unavailable"),
        ("Connection timed out", "network"),
        ("Permission denied: /Users/person/private", "permission_denied"),
        ("Output validation failed", "validation"),
        ("ffmpeg exited with status 1", "transcoding"),
        ("private title with no recognized error", "unknown"),
    ],
)
def test_failure_reason_is_closed_and_contains_no_diagnostics(message, reason):
    result = classify_failure(message)
    assert result == reason
    assert result in FAILURE_REASONS


def test_structured_tool_failure_never_serializes_command_or_stderr():
    import subprocess

    from yt_downloader.failure_diagnostics import capture_failure

    failure = subprocess.CalledProcessError(
        7, ["ffmpeg", "/Users/private/video.mp4"], stderr="secret video title"
    )
    detail = capture_failure(failure, stage="processing").payload()
    assert detail["tool_exit_code"] == 7
    assert detail["error_type"] == "CalledProcessError"
    assert "private" not in str(detail)
    assert "secret" not in str(detail)


def test_http_failure_preserves_status_not_url_or_message():
    from urllib.error import HTTPError

    from yt_downloader.failure_diagnostics import capture_failure

    error = HTTPError("https://private.invalid/video", 403, "Private title", None, None)
    detail = capture_failure(error).payload()
    assert detail["http_status"] == 403
    assert "private" not in str(detail).lower()


def test_unapproved_detail_is_rejected():
    from yt_downloader.failure_diagnostics import validate_failure_detail

    with pytest.raises(ValueError):
        validate_failure_detail({"message": "private title"})


def test_nested_machine_code_overrides_misleading_outer_message():
    import errno

    from yt_downloader.failure_diagnostics import capture_failure

    error = RuntimeError("network failed for private title")
    error.__cause__ = OSError(errno.ENOSPC, "private filename")
    detail = capture_failure(error).payload()
    assert detail["reason"] == "disk_full"
    assert detail["os_error"] == errno.ENOSPC
    assert "private" not in str(detail)


def test_provider_exc_info_preserves_http_evidence():
    from urllib.error import HTTPError

    from yt_downloader.failure_diagnostics import capture_failure

    error = RuntimeError("conversion failed")
    nested = HTTPError("https://secret.invalid", 429, "secret", None, None)
    error.exc_info = (HTTPError, nested, None)
    detail = capture_failure(error).payload()
    assert detail["http_status"] == 429
    assert detail["reason"] == "rate_limited"
    assert "secret" not in str(detail)
