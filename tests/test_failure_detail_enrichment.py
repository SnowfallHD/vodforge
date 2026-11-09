"""Failure reports carry enough closed facts to debug production failures in D1.

Production D1 (Oct-Nov 2026) had failures too vague to act on: YouTube items
with zero formats and no reason, extractor errors classified "unknown", and
chains ending in "other". Every fact here is a closed vocabulary or a number;
no message text, URL or path is sent.
"""

from __future__ import annotations

import http.client
import json
import re
import urllib.error
from pathlib import Path

import pytest

from yt_downloader import failure_diagnostics as fd
from yt_downloader.download_service import QueueLogger, _build_download_item_plan
from yt_downloader.models import (
    DownloadJob,
    ExportMode,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)

SITE_VALIDATOR = (
    Path(__file__).resolve().parents[2] / "vodforge-site/src/lib/product-telemetry.ts"
)


@pytest.mark.parametrize(
    "message,code",
    [
        (
            "Sign in to confirm your age. This video may be inappropriate for some users.",
            "age_restricted",
        ),
        ("Sign in to confirm you're not a bot", "bot_challenge"),
        ("Video unavailable", "video_unavailable"),
        ("This video has been removed by the uploader", "video_unavailable"),
        ("Private video. Sign in if you've been granted access", "private_video"),
        ("Join this channel to get access to members-only content", "members_only"),
        (
            "The uploader has not made this video available in your country",
            "geo_restricted",
        ),
        ("Premieres in 3 hours", "live_not_started"),
        ("This live event will begin in a few moments.", "live_not_started"),
        ("Unsupported URL: https://example.invalid/x", "unsupported_url"),
    ],
)
def test_provider_messages_get_a_failure_code(message, code):
    error = RuntimeError(f"ERROR: [youtube] abc: {message}")
    assert fd.failure_code(error) == code
    payload = fd.capture_failure(error, stage="analysis").payload()
    assert payload["failure_code"] == code
    fd.validate_failure_detail(payload)  # the app's own sending boundary


def test_logger_records_warning_codes_and_failure_reports_the_most_telling():
    seen: set[str] = set()
    logger = QueueLogger(None, warnings=seen)
    logger.warning("[youtube] abc: Some formats may be missing")
    logger.warning("[youtube] abc: Signature solving failed: n challenge")
    logger.warning("[youtube] abc: some unrelated note")
    assert seen == {"formats_missing", "challenge_solving_failed"}
    payload = fd.capture_failure(
        RuntimeError("no formats"), stage="analysis", extractor_warnings=seen
    ).payload()
    assert payload["extractor_warning"] == "challenge_solving_failed"
    fd.validate_failure_detail(payload)


@pytest.mark.parametrize(
    "output_type", [OutputType.MP4, OutputType.MP3, OutputType.ORIGINAL]
)
def test_zero_formats_report_live_status_and_availability(tmp_path, output_type):
    job = DownloadJob(
        url="https://www.youtube.com/watch?v=abc",
        output_dir=tmp_path,
        output_type=output_type,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=True,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=False,
        tags=[],
    )
    info = {"formats": [], "live_status": "is_upcoming", "availability": "public"}
    with pytest.raises(fd.SourceSelectionError) as raised:
        _build_download_item_plan(job, info, max_height=1080)
    payload = fd.capture_failure(raised.value, stage="analysis").payload()
    assert payload["format_count"] == 0
    assert payload["live_status"] == "is_upcoming"
    assert payload["availability"] == "public"
    fd.validate_failure_detail(payload)


def test_unknown_live_status_is_dropped():
    error = fd.SourceSelectionError("no formats", [])
    error.live_status = "something new"
    error.availability = "private"
    payload = fd.capture_failure(error, stage="analysis").payload()
    assert "live_status" not in payload and payload["availability"] == "private"


def test_network_leaf_cause_is_named_instead_of_other():
    inner = urllib.error.URLError(http.client.RemoteDisconnected("closed"))
    outer = RuntimeError("update check failed")
    outer.__cause__ = inner
    payload = fd.capture_failure(outer, stage="analysis", context="updater").payload()
    assert payload["error_chain"] == "RuntimeError>URLError>RemoteDisconnected"
    fd.validate_failure_detail(payload)


def _server_vocabulary():
    if not SITE_VALIDATOR.is_file():
        pytest.skip("the vodforge-site checkout is not next to this one")
    text = SITE_VALIDATOR.read_text("utf-8")
    body = text[
        text.index("function failureDetail") : text.index("function optionalChoice")
    ]
    choices = {
        name: set(re.findall(r"[\"']([^\"']+)[\"']", values))
        for name, values in re.findall(r"(\w+): new Set\(\[(.*?)\]\)", body)
    }
    reasons = re.search(r"const FAILURE_REASONS = new Set\(\[(.*?)\]\)", text).group(1)
    choices["reason"] = set(re.findall(r"\"([a-z_]+)\"", reasons))
    ranges = set(
        re.findall(
            r"(\w+):\[", re.search(r"const ranges[^=]*=\s*\{(.*?)\};", body).group(1)
        )
    )
    return choices, set(choices) | ranges | {"error_chain", "source_trace"}


def test_every_value_the_app_can_send_is_accepted_by_the_website():
    """The server rejects a whole event for one unknown detail value, and the
    app then discards it. 0.2.6's http_forbidden was missing from production."""
    choices, keys = _server_vocabulary()
    fields = set(fd.FailureDiagnostic.__dataclass_fields__)
    assert fields - keys == set()
    for name, values in {
        "failure_code": fd.FAILURE_CODES,
        "error_type": fd.ERROR_TYPES,
        "source_module": fd.FIRST_PARTY_MODULES,
        "stage": fd.FAILURE_STAGES,
        "reason": fd.FAILURE_REASONS,
        "cookie_failure": fd.COOKIE_FAILURES,
        "extractor_warning": fd.EXTRACTOR_WARNING_CODES,
        "live_status": fd.LIVE_STATUSES,
        "availability": fd.AVAILABILITIES,
    }.items():
        assert set(values) - choices.get(name, set()) == set(), name
    json.dumps(sorted(keys))
