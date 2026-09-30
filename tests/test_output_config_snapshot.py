"""Display-only provenance survives history without restoring authentication."""

from dataclasses import replace
from pathlib import Path

import pytest

from tests.test_run_identity import make_job
from yt_downloader.history import (
    RETRY_JOB_METADATA_KEY,
    load_history,
    sanitize_history_record,
    save_history,
)
from yt_downloader.models import OutputType
from yt_downloader.output_config_snapshot import (
    OUTPUT_CONFIG_DISPLAY_KEY,
    output_config_display,
    sanitize_output_config_display,
)
from yt_downloader.qt_quick.output_config_facts import (
    chosen_config_facts,
    recorded_config,
)
from yt_downloader.run_state import deserialize_download_job, serialize_download_job


@pytest.mark.parametrize(
    "output,available,requested,expected",
    [
        (OutputType.MP4, True, True, "On"),
        (OutputType.MP4, True, False, "Off"),
        (OutputType.MP4, False, False, "N/A (not available)"),
        (OutputType.MP3, True, True, "N/A (audio only)"),
        (OutputType.ORIGINAL, False, False, "N/A (audio only)"),
        (OutputType.MP4, None, False, "Off (capability not recorded)"),
    ],
)
def test_saved_configuration_roundtrip(
    tmp_path, output, available, requested, expected
):
    job = replace(
        make_job(tmp_path),
        output_type=output,
        use_nvenc=requested,
        nvenc_applicable=available,
        use_cookies=True,
        cookie_browser="firefox",
        cookie_file=Path("/private/token-secret/cookies.txt"),
    )
    record = sanitize_history_record(
        {
            "id": "example",
            "title": "Example",
            "vodforge_run_id": job.run_id,
            RETRY_JOB_METADATA_KEY: serialize_download_job(job),
            OUTPUT_CONFIG_DISPLAY_KEY: output_config_display(job),
        },
        tmp_path,
    )
    path = tmp_path / "history.json"
    save_history(path, [record])
    stored = load_history(path)[0]
    config = recorded_config(stored)
    rows = {
        row["label"]: row["value"]
        for row in chosen_config_facts(
            config, nvenc_available=config["nvenc_applicable"]
        )
    }
    assert rows["NVENC requested"] == expected
    assert rows["YouTube access"] == "Browser (Firefox)"
    assert "token-secret" not in path.read_text()
    restored = deserialize_download_job(stored[RETRY_JOB_METADATA_KEY])
    assert restored.use_cookies is False
    assert restored.cookie_browser is None
    assert restored.cookie_file is None
    assert restored.nvenc_applicable is None


def test_display_snapshot_allowlist_discards_secrets(tmp_path):
    raw = {
        "access": "Browser",
        "browser": "/private/profile/token-secret",
        "nvenc_applicable": 1,
        "cookie_file": "token-secret",
        "token": "secret",
        "profile_id": "secret",
    }
    assert sanitize_output_config_display(raw) == {
        "access": "Browser",
        "browser": "",
        "nvenc_applicable": None,
    }
    job = replace(
        make_job(tmp_path),
        use_cookies=True,
        cookie_file=Path("/private/secret/cookies.txt"),
    )
    assert output_config_display(job)["access"] == "cookies.txt"
    assert output_config_display(replace(job, use_cookies=False))["access"] == "Public"
    assert sanitize_output_config_display({"access": "arbitrary secret"}) is None


def test_history_event_persists_display_provenance(tmp_path, monkeypatch):
    import yt_downloader.archive_file_operations as operations
    from yt_downloader.qt_quick.runtime import DownloadRuntime

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(
        operations, "reconcile_file_record_delta", lambda record, *args: record
    )
    runtime = DownloadRuntime()
    job = replace(
        make_job(tmp_path),
        use_cookies=True,
        cookie_browser="edge",
        nvenc_applicable=True,
    )
    runtime.active_job = job
    runtime._record_history(
        {
            "job": job,
            "info": {"id": "example", "title": "Example"},
            "output_dir": str(tmp_path),
        }
    )
    assert runtime.history[0][OUTPUT_CONFIG_DISPLAY_KEY] == {
        "access": "Browser",
        "browser": "Edge",
        "nvenc_applicable": True,
    }


def test_admission_captures_existing_capability_without_affecting_encoder(
    tmp_path, monkeypatch
):
    from yt_downloader.qt_quick.runtime import DownloadPreferences, DownloadRuntime

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    runtime = DownloadRuntime()
    for available in (True, False, None):
        job = runtime.prepare_job(
            "https://youtu.be/abc123",
            tmp_path,
            "MP4",
            "Everyday",
            preferences=DownloadPreferences(use_nvenc=False),
            nvenc_applicable=available,
        )
        assert job.nvenc_applicable is available
        assert job.use_nvenc is False
    job = runtime.prepare_job(
        "https://youtu.be/abc123", tmp_path, "MP3", "Everyday", nvenc_applicable=True
    )
    assert job.nvenc_applicable is False
