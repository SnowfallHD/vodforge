from __future__ import annotations

import json
from pathlib import Path

import pytest

from yt_downloader.history import (
    HistoryError,
    MAX_RUN_ACTIVITY_CHARS,
    MAX_RUN_ACTIVITY_LINES,
    application_data_dir,
    history_identity,
    history_output_dir,
    history_output_type,
    load_history,
    save_history,
    sanitize_history_record,
    upsert_history,
)


def test_application_data_dir_uses_platform_conventions(tmp_path: Path):
    assert application_data_dir(platform_name="darwin", home=tmp_path) == tmp_path / "Library" / "Application Support" / "VODForge"
    assert application_data_dir(platform_name="win32", home=tmp_path, local_app_data="C:/Users/Test/AppData/Local") == Path(
        "C:/Users/Test/AppData/Local/VODForge"
    )
    assert application_data_dir(platform_name="linux", home=tmp_path, xdg_data_home=None) == tmp_path / ".local" / "share" / "vodforge"


def test_sanitize_history_record_allowlists_metadata_and_excludes_secrets(tmp_path: Path):
    record = sanitize_history_record(
        {
            "id": "abc123",
            "title": "Example",
            "description": "Description",
            "duration": 42,
            "uploader": "Creator",
            "tags": ["one", "one", "two"],
            "cookiefile": "/private/cookies.txt",
            "http_headers": {"Authorization": "secret"},
            "password": "secret",
        },
        tmp_path / "downloads" / "Example",
        recorded_at="2026-08-05T12:00:00+00:00",
    )

    assert record["id"] == "abc123"
    assert record["tags"] == ["one", "two"]
    assert history_output_dir(record) == (tmp_path / "downloads" / "Example").resolve()
    assert record["vodforge_recorded_at"] == "2026-08-05T12:00:00+00:00"
    assert history_output_type(record) == "MP4"
    assert "cookiefile" not in record
    assert "http_headers" not in record
    assert "password" not in record


def test_history_round_trip_and_redownload_deduplication(tmp_path: Path):
    location = tmp_path / "downloads" / "Example"
    history = upsert_history([], {"id": "abc123", "title": "Original"}, location, recorded_at="2026-08-05T12:00:00+00:00")
    history = upsert_history(history, {"id": "abc123", "title": "Updated"}, location, recorded_at="2026-08-05T13:00:00+00:00")
    history = upsert_history(history, {"id": "xyz789", "title": "Second"}, tmp_path / "other", recorded_at="2026-08-05T14:00:00+00:00")

    assert [item["id"] for item in history] == ["xyz789", "abc123"]
    assert history[1]["title"] == "Updated"

    path = tmp_path / "state" / "download-history.json"
    save_history(path, history)
    loaded = load_history(path)

    assert loaded == history
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 1
    assert history_identity(loaded[0]) == history_identity(history[0])


def test_history_round_trip_preserves_bounded_per_run_activity(tmp_path: Path):
    activity = [f"line {index}" for index in range(MAX_RUN_ACTIVITY_LINES + 20)]
    history = upsert_history(
        [],
        {
            "id": "abc123",
            "title": "Example",
            "vodforge_run_id": "run-authority-123",
            "vodforge_run_activity": activity,
        },
        tmp_path / "downloads" / "Example",
    )
    path = tmp_path / "state" / "download-history.json"

    save_history(path, history)
    loaded = load_history(path)

    assert loaded[0]["vodforge_run_id"] == "run-authority-123"
    assert loaded[0]["vodforge_run_activity"] == activity[:MAX_RUN_ACTIVITY_LINES]
    assert sum(len(line) for line in loaded[0]["vodforge_run_activity"]) <= MAX_RUN_ACTIVITY_CHARS


def test_history_keeps_same_video_downloaded_to_two_locations(tmp_path: Path):
    first = upsert_history([], {"id": "abc123", "title": "Example"}, tmp_path / "one")
    second = upsert_history(first, {"id": "abc123", "title": "Example"}, tmp_path / "two")

    assert len(second) == 2
    assert history_output_dir(second[0]) != history_output_dir(second[1])


def test_history_keeps_mp4_and_mp3_for_same_video_and_location(tmp_path: Path):
    location = tmp_path / "downloads" / "Example"
    mp4 = upsert_history(
        [],
        {"id": "abc123", "title": "Example", "vodforge_output_type": "MP4"},
        location,
    )
    both = upsert_history(
        mp4,
        {"id": "abc123", "title": "Example", "vodforge_output_type": "MP3"},
        location,
    )

    assert len(both) == 2
    assert [history_output_type(item) for item in both] == ["MP3", "MP4"]
    assert history_identity(both[0]) != history_identity(both[1])


def test_invalid_history_is_reported_without_overwriting_source(tmp_path: Path):
    path = tmp_path / "download-history.json"
    path.write_text("not json", encoding="utf-8")

    with pytest.raises(HistoryError, match="could not read"):
        load_history(path)

    assert path.read_text(encoding="utf-8") == "not json"
