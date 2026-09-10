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


@pytest.mark.parametrize(
    "raw,category,action",
    [
        ("connection timed out", "network", "Check your internet"),
        ("HTTP Error 429", "rate_limited", "Wait before retrying"),
        ("login required", "authentication_required", "select your browser"),
        ("video unavailable", "source_unavailable", "Open the link"),
        ("no space left on device", "disk_full", "Free space"),
        ("permission denied", "permission_denied", "Check its permissions"),
        ("ffmpeg exited with status 1", "transcoding", "retry once"),
        (
            "the MP4 output does not match its export plan",
            "validation",
            "same settings",
        ),
        ("unrecognized problem", "unknown", "Check Library"),
        ("ffprobe is required", "dependency_missing", "reinstall VODForge"),
        ("unsupported codec", "unsupported_format", "Choose another format"),
        ("invalid url", "invalid_input", "Check the source"),
        ("output conflict", "output_conflict", "Choose another output folder"),
        (
            "not available in your country",
            "source_restricted",
            "otherwise use another source",
        ),
        ("unable to extract media", "provider_extraction", "Update VODForge"),
        ("no such file or directory", "filesystem", "drive is connected"),
        ("out of memory", "resource_exhausted", "Close other demanding apps"),
    ],
)
def test_failure_category_has_action_and_technical_cause(raw, category, action):
    from yt_downloader.download_error_presentation import technical_download_error
    from yt_downloader.failure_diagnostics import capture_failure

    error = RuntimeError(raw)
    assert capture_failure(error).reason == category
    assert action in download_error_message(error)
    technical = technical_download_error(error)
    assert raw in technical
    assert action in technical


def test_guidance_covers_every_existing_failure_category():
    from yt_downloader.download_error_presentation import FAILURE_GUIDANCE
    from yt_downloader.failure_diagnostics import FAILURE_REASONS

    assert set(FAILURE_GUIDANCE) == FAILURE_REASONS
    assert all(0 < len(value) < 320 for value in FAILURE_GUIDANCE.values())


def test_wrapped_machine_cause_overrides_network_prose():
    import errno

    from yt_downloader.download_error_presentation import technical_download_error

    error = RuntimeError("network wrapper failed")
    error.__cause__ = OSError(errno.ENOSPC, "No space left on device")
    assert "Free space" in download_error_message(error)
    assert "No space left on device" in technical_download_error(error)


def test_process_stderr_and_empty_cause_are_explained_without_command_secrets():
    import subprocess

    from yt_downloader.download_error_presentation import technical_download_error

    error = subprocess.CalledProcessError(
        1,
        ["ffmpeg", "secret-command-argument"],
        stderr=b"Encoder initialization failed",
    )
    technical = technical_download_error(error)
    assert "status 1" in technical
    assert "Encoder initialization failed" in technical
    assert "secret-command-argument" not in technical
    assert "No further error detail was provided" in technical_download_error(
        RuntimeError()
    )
    error.__cause__ = error
    assert len(technical_download_error(error)) < 4000


def test_validation_does_not_invent_a_lower_bitrate_workaround():
    message = download_error_message(
        RuntimeError(
            "the MP4 output does not match its export plan: the measured audio bitrate (2.274 kbps) does not match 160 kbps"
        )
    )
    assert "same settings" in message
    assert "lower" not in message
    assert "Manual" not in message


def test_preview_keeps_friendly_message_separate_from_technical(monkeypatch):
    from types import SimpleNamespace

    from yt_downloader import ui_events
    from yt_downloader.download_error_presentation import technical_download_error

    error = RuntimeError("HTTP Error 503")
    message = download_error_message(error)
    details = technical_download_error(error)
    shown = []
    logged = []
    request = {"run_id": "preview", "output_type": "MP4"}
    host = SimpleNamespace(
        _metadata_preview_request=request,
        _focus_selected_run_id="preview",
        _refresh_focus_run_deck=lambda: None,
        _display_metadata_preview_request=shown.append,
        status_var=SimpleNamespace(set=lambda _value: None),
        _append_log=logged.append,
        _event_app_name="VODForge",
    )
    popups = []
    monkeypatch.setattr(
        ui_events.messagebox, "showerror", lambda _title, text: popups.append(text)
    )
    ui_events.UiEventHandlersMixin._handle_metadata_error(
        host, {"message": message, "details": details}
    )
    assert popups == [message]
    assert shown[0]["details"] == details
    assert "HTTP Error 503" in details
    assert "HTTP Error 503" not in message
    assert details in logged


def test_nested_http_code_overrides_sign_in_wording():
    from urllib.error import HTTPError

    error = RuntimeError("Sign in to confirm")
    error.__cause__ = HTTPError(
        "https://example.com", 429, "Too many requests", None, None
    )
    assert "Wait before retrying" in download_error_message(error)
    assert "Browser" not in download_error_message(error)
