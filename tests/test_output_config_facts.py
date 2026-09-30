"""Output summary covers applicable choices without exposing access secrets."""

from dataclasses import replace
from pathlib import Path

import pytest

from tests.test_run_identity import make_job
from yt_downloader.models import (
    ExportMode,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)
from yt_downloader.qt_quick.output_config_facts import chosen_config_facts, job_config


def facts(job, available=True):
    return {
        row["label"]: row["value"]
        for row in chosen_config_facts(job_config(job), nvenc_available=available)
    }


@pytest.mark.parametrize("output", list(OutputType))
@pytest.mark.parametrize(
    "available,requested", [(False, False), (False, True), (True, False), (True, True)]
)
def test_nvenc_requested_tristate(tmp_path, output, available, requested):
    job = replace(make_job(tmp_path), output_type=output, use_nvenc=requested)
    value = facts(job, available)["NVENC requested"]
    if output != OutputType.MP4 or not available:
        assert value.startswith("N/A")
    else:
        assert value == ("On" if requested else "Off")


@pytest.mark.parametrize("mode", list(ExportMode))
def test_mp4_chosen_fields(tmp_path, mode):
    job = replace(make_job(tmp_path), export_mode=mode)
    rows = facts(job)
    assert {
        "Format",
        "Output mode",
        "Quality ceiling",
        "Save to",
        "YouTube access",
        "NVENC requested",
        "Video",
        "Audio",
        "Embed thumbnail",
        "Embed metadata",
        "Thumbnail file",
        "Info JSON file",
        "Ignore playlists",
        "Extra tags",
    } <= rows.keys()
    assert rows["Extra tags"] == "alpha, beta"
    if mode == ExportMode.MANUAL_OVERRIDE:
        assert {
            "Rate control",
            "Video bitrate",
            "x264 preset",
            "Audio bitrate",
            "Sample rate",
            "Channels",
        } <= rows.keys()
    else:
        assert "Rate control" not in rows


def test_manual_quality_and_mp3_every_choice(tmp_path):
    job = replace(
        make_job(tmp_path),
        export_mode=ExportMode.MANUAL_OVERRIDE,
        manual_settings=ManualExportSettings(video_crf=18),
    )
    rows = facts(job)
    assert rows["Video quality"] == "CRF 18"
    assert "Video bitrate" not in rows
    job = replace(
        job,
        output_type=OutputType.MP3,
        mp3_settings=Mp3ExportSettings(
            bitrate_kbps=192,
            sample_rate="44100",
            channels="1",
            embed_metadata=False,
            embed_cover_art=True,
            custom_cover_art_path=Path("/private/secret/art.jpg"),
        ),
    )
    rows = facts(job)
    assert rows["Audio quality"] == "192 kbps"
    assert rows["Sample rate"] == "44100"
    assert rows["Channels"] == "Mono"
    assert rows["Cover art"] == "Custom art"
    assert rows["Embed metadata"] == "Off"
    assert "secret" not in str(rows)
    assert "Embed thumbnail" not in rows


@pytest.mark.parametrize(
    "browser,expected",
    [
        (None, "cookies.txt"),
        ("firefox", "Browser (Firefox)"),
        ("Chrome", "Browser (Chrome)"),
        ("/private/profile?token=secret", "Browser (Not selected)"),
    ],
)
def test_access_displays_only_method_and_closed_browser(tmp_path, browser, expected):
    job = replace(
        make_job(tmp_path),
        use_cookies=True,
        cookie_file=Path("/private/secret/cookies.txt"),
        cookie_browser=browser,
    )
    rows = facts(job)
    assert rows["YouTube access"] == expected
    assert "secret" not in str(rows)
    assert (
        facts(replace(job, use_cookies=False))["YouTube access"]
        == "Public (no cookies)"
    )


def test_legacy_saved_retry_keeps_config_but_never_invents_access(tmp_path):
    from yt_downloader.history import RETRY_JOB_METADATA_KEY
    from yt_downloader.qt_quick.output_config_facts import recorded_config
    from yt_downloader.run_state import serialize_download_job

    job = replace(make_job(tmp_path), use_cookies=True, cookie_browser="firefox")
    payload = serialize_download_job(job)
    config = recorded_config(
        {"vodforge_run_id": job.run_id, RETRY_JOB_METADATA_KEY: payload}
    )
    rows = {
        row["label"]: row["value"]
        for row in chosen_config_facts(config, nvenc_available=None)
    }
    assert rows["YouTube access"] == "Not recorded"
    assert rows["NVENC requested"] == "Off (capability not recorded)"
    assert rows["Extra tags"] == "alpha, beta"
    assert (
        recorded_config({"vodforge_run_id": "wrong", RETRY_JOB_METADATA_KEY: payload})
        is None
    )
    assert recorded_config({RETRY_JOB_METADATA_KEY: {}}) is None
