from __future__ import annotations

import queue
from types import SimpleNamespace

import pytest

import yt_downloader.download_service as app_module
from tests.test_library_media_recovery import _job, _missing_record
from yt_downloader.history import RETRY_JOB_METADATA_KEY
from yt_downloader.library_media_recovery import LibraryMediaRecoveryOwner
from yt_downloader.models import OutputType
from yt_downloader.run_identity import OUTPUT_PROFILE_KEY


@pytest.mark.parametrize(
    ("label", "migrated"),
    [
        ("Auto CBR", True),
        ("Auto CBR (Recommended)", True),
        ("Strict Compliance", True),
        ("CTV (legacy fixed bitrate)", True),
        ("CTV", False),
        ("Custom", False),
        ("Manual Override", False),
        ("Everyday", False),
        ("Streaming", False),
        ("Editing", False),
        ("Sharing", False),
        ("Unknown", False),
        ("", False),
    ],
)
def test_incomplete_profile_only_recognized_legacy_presets_start_everyday(
    tmp_path, label, migrated
):
    original = _job(tmp_path)
    original.output_type = OutputType.MP4
    row = _missing_record(original)
    row.pop(RETRY_JOB_METADATA_KEY)
    row[OUTPUT_PROFILE_KEY] = f"MP4 • 1080p Full HD • {label}"
    plan = LibraryMediaRecoveryOwner().plan(row)
    assert plan.kind == "legacy" and plan.job is None
    assert getattr(plan, "preset_migrated", False) is migrated


@pytest.mark.parametrize("output", list(OutputType))
@pytest.mark.parametrize("playlist", [False, True])
def test_actual_recovery_expansion_uses_one_saved_item_without_playlist_provider_work(
    tmp_path, monkeypatch, output, playlist
):
    job = _job(tmp_path)
    job.output_type = output
    if playlist:
        job.url += "&list=PL_saved"
        job.urls = [job.url]
    row = _missing_record(job)
    if playlist:
        row.update(
            playlist_id="PL_saved", playlist_title="Saved playlist", playlist_index=7
        )
    plan = LibraryMediaRecoveryOwner().plan(row)
    recovered = plan.job
    recovered.recovery_reason = "missing_media"
    monkeypatch.setattr(app_module, "write_diagnostic", lambda _: None)
    monkeypatch.setattr(app_module, "log_options", lambda *args: None)
    app = SimpleNamespace(
        events=queue.Queue(),
        _emit_job_log=lambda *args: None,
        _find_deno=lambda: None,
    )
    provider_calls = []

    class UnexpectedPlaylistLookup(Exception):
        pass

    def provider_started(_):
        provider_calls.append("playlist lookup")
        raise UnexpectedPlaylistLookup

    result = None
    try:
        result = app_module.DownloadWorkerCore._expand_download_source(
            app,
            recovered,
            None,
            SimpleNamespace(begin_primary=provider_started),
            control_check=lambda: None,
            blocking_step_cancelled=lambda: False,
        )
    except UnexpectedPlaylistLookup:
        pass
    assert provider_calls == [], "Selected recovery must not reread its saved playlist"
    assert result is not None
    assert len(result.entries) == 1
    assert result.entries[0]["webpage_url"] == recovered.url
    assert result.playlist_info.get("playlist_title") == (
        "Saved playlist" if playlist else None
    )
    if playlist:
        assert result.entries[0]["playlist_index"] == 7
    assert (
        result.cookie_source_loaded is False
    )  # Item preflight still loads credentials.
    assert app.events.empty()


@pytest.mark.parametrize(
    "invalid",
    ["ordinary", "different_video", "different_playlist", "batch", "multiple_urls"],
)
def test_recovery_fast_path_cannot_bypass_ordinary_or_mismatched_playlist_lookup(
    tmp_path, monkeypatch, invalid
):
    job = _job(tmp_path)
    job.url += "&list=PL_saved"
    job.urls = [job.url]
    job.preview_info = {
        "id": "missing",
        "playlist_id": "PL_saved",
        "playlist_title": "Saved",
    }
    job.recovery_reason = "missing_media"
    if invalid == "ordinary":
        job.recovery_reason = None
    elif invalid == "different_video":
        job.preview_info["id"] = "other"
    elif invalid == "different_playlist":
        job.preview_info["playlist_id"] = "PL_other"
    elif invalid == "batch":
        job.batch_mode = True
    else:
        job.urls.append("https://www.youtube.com/watch?v=other")
    monkeypatch.setattr(app_module, "write_diagnostic", lambda _: None)
    monkeypatch.setattr(app_module, "log_options", lambda *args: None)
    app = SimpleNamespace(
        events=queue.Queue(),
        _emit_job_log=lambda *args: None,
        _find_deno=lambda: None,
    )

    class LookupReached(Exception):
        pass

    def reached(_):
        raise LookupReached

    with pytest.raises(LookupReached):
        app_module.DownloadWorkerCore._expand_download_source(
            app,
            job,
            None,
            SimpleNamespace(begin_primary=reached),
            control_check=lambda: None,
            blocking_step_cancelled=lambda: False,
        )
