import pytest

from yt_downloader.download_error_presentation import download_error_message


@pytest.mark.parametrize(
    "raw",
    [
        "No usable video source was found for this URL.",
        "Video unavailable",
        "Sign in to confirm your age",
        "Sign in to confirm you're not a bot",
        "HTTP Error 503",
        "Requested format is not available",
        "unexpected failure",
    ],
)
def test_provider_text_cannot_expand_user_summary(raw):
    message = download_error_message(raw + "\nprivate diagnostics " * 10000)
    assert len(message) < 320
    assert "\n" not in message
    assert "private diagnostics" not in message
    assert "yt-dlp" not in message


def test_no_formats_does_not_guess_age_or_missing_runtime():
    message = download_error_message("No usable video source was found")
    assert "age verification" not in message
    assert "component" not in message
    assert "You can try Settings → YouTube access → Browser" in message
    assert "select your browser" in message


def test_explicit_age_restriction_has_specific_issue():
    assert download_error_message("Sign in to confirm your age").startswith(
        "YouTube requires age verification"
    )


def test_technical_cause_is_bounded_and_redacts_sensitive_lines():
    from yt_downloader.download_error_presentation import technical_download_error

    detail = technical_download_error(
        RuntimeError(
            "Validation failed\nAuthorization: Bearer private-secret\nhttps://example.com/private?token=hidden\n"
            + "x" * 5000
        )
    )
    assert "Validation failed" in detail
    assert "private-secret" not in detail
    assert "hidden" not in detail
    assert len(detail) < 4000
