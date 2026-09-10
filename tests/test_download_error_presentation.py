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
