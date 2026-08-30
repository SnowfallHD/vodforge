from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

import yt_downloader.history as history_module

from yt_downloader.history import (
    HistoryError,
    MAX_RUN_ACTIVITY_CHARS,
    MAX_RUN_ACTIVITY_LINES,
    application_data_dir,
    history_identity,
    history_media_file_exists,
    history_media_identity,
    history_output_dir,
    history_output_type,
    load_history,
    save_history,
    sanitize_durable_text,
    sanitize_durable_url,
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
            "webpage_url": "https://www.youtube.com/watch?v=abc123&list=PLsafe&token=secret#private",
            "original_url": "https://youtu.be/abc123?si=tracking&auth=secret",
            "thumbnail": "https://i.ytimg.com/vi/abc123/default.jpg?token=secret#private",
            "best_thumbnail": {
                "url": "https://i.ytimg.com/vi/abc123/maxresdefault.jpg?auth=secret",
                "width": 1280,
                "height": 720,
                "http_headers": {"Authorization": "secret"},
            },
            "cookiefile": "/private/cookies.txt",
            "http_headers": {"Authorization": "secret"},
            "password": "secret",
        },
        tmp_path / "downloads" / "Example",
        recorded_at="2026-08-05T12:00:00+00:00",
    )

    assert record["id"] == "abc123"
    assert record["tags"] == ["one", "two"]
    assert record["webpage_url"] == "https://www.youtube.com/watch?v=abc123&list=PLsafe"
    assert record["original_url"] == "https://www.youtube.com/watch?v=abc123"
    assert record["thumbnail"] == "https://i.ytimg.com/vi/abc123/default.jpg"
    assert record["best_thumbnail"] == {
        "url": "https://i.ytimg.com/vi/abc123/maxresdefault.jpg",
        "width": 1280,
        "height": 720,
    }
    assert history_output_dir(record) == (tmp_path / "downloads" / "Example").resolve()
    assert record["vodforge_recorded_at"] == "2026-08-05T12:00:00+00:00"
    assert history_output_type(record) == "MP4"
    assert "cookiefile" not in record
    assert "http_headers" not in record
    assert "password" not in record


def test_durable_url_sanitizer_strips_credentials_query_and_fragment_but_keeps_identity():
    canary = "TOPSECRET"

    assert sanitize_durable_url(
        f"https://user:pass@example.invalid/media?id=1&token={canary}#private",
        preserve_youtube_context=True,
    ) == "https://example.invalid/media"
    assert sanitize_durable_url(
        f"https://user:pass@youtu.be/abc123?list=PLsafe&token={canary}#private",
        preserve_youtube_context=True,
    ) == "https://www.youtube.com/watch?v=abc123&list=PLsafe"
    assert sanitize_durable_url(
        f"https://example.invalid:invalid/media?token={canary}",
        preserve_youtube_context=True,
    ) is None


def test_durable_text_sanitizer_handles_multiple_embedded_and_malformed_urls():
    canary = "TOPSECRET"
    text = sanitize_durable_text(
        "first "
        f"https://user:pass@example.invalid/media?id=1&token={canary}#private, "
        "second https://www.youtube.com/watch?v=abc123&list=PLsafe&auth=hidden. "
        f"bad https://example.invalid:invalid/media?token={canary}"
    )

    assert "first https://example.invalid/media," in text
    assert "second https://www.youtube.com/watch?v=abc123&list=PLsafe." in text
    assert "bad [redacted invalid URL]" in text
    assert canary not in text
    assert "user:pass" not in text


def test_history_sanitizes_embedded_urls_before_bounding_run_activity(tmp_path: Path):
    canary = "TOPSECRET"
    record = sanitize_history_record(
        {
            "id": "abc123",
            "title": "Example",
            "vodforge_run_activity": [
                f"Normalized URL: https://user:pass@example.invalid/media?token={canary}#private"
            ],
        },
        tmp_path / "downloads" / "Example",
    )

    assert record["vodforge_run_activity"] == [
        "Normalized URL: https://example.invalid/media"
    ]


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


def test_redownload_replaces_a_missing_same_item_location(tmp_path: Path):
    missing_location = tmp_path / "moved-away" / "Example"
    replacement_location = tmp_path / "downloads" / "Example"
    original = upsert_history(
        [],
        {
            "id": "abc123",
            "title": "Example",
            "playlist_id": "PLone",
            "vodforge_output_type": "MP4",
        },
        missing_location,
    )

    replaced = upsert_history(
        original,
        {
            "id": "abc123",
            "title": "Example restored",
            "playlist_id": "PLone",
            "vodforge_output_type": "MP4",
        },
        replacement_location,
        replace_missing_media=True,
    )

    assert len(replaced) == 1
    assert history_output_dir(replaced[0]) == replacement_location.resolve()
    assert replaced[0]["title"] == "Example restored"
    assert history_media_identity(replaced[0]) == history_media_identity(original[0])


def test_redownload_preserves_another_location_that_still_has_media(tmp_path: Path):
    first_location = tmp_path / "archive" / "Example"
    second_location = tmp_path / "downloads" / "Example"
    first_location.mkdir(parents=True)
    (first_location / "Example.mp4").write_bytes(b"existing media")
    original = upsert_history(
        [],
        {"id": "abc123", "title": "Example", "vodforge_output_type": "MP4"},
        first_location,
    )

    updated = upsert_history(
        original,
        {"id": "abc123", "title": "Example", "vodforge_output_type": "MP4"},
        second_location,
        replace_missing_media=True,
    )

    assert history_media_file_exists(original[0]) is True
    assert len(updated) == 2
    assert {history_output_dir(item) for item in updated} == {
        first_location.resolve(),
        second_location.resolve(),
    }


def test_redownload_preserves_same_item_history_when_prior_storage_is_unavailable(
    monkeypatch,
    tmp_path: Path,
):
    unavailable_location = tmp_path / "offline-drive" / "Example"
    replacement_location = tmp_path / "downloads" / "Example"
    original = upsert_history(
        [],
        {
            "id": "abc123",
            "title": "Archived example",
            "playlist_id": "PLone",
            "vodforge_output_type": "MP4",
        },
        unavailable_location,
    )
    unavailable_root = tmp_path / "offline-drive"
    monkeypatch.setattr(
        history_module,
        "_external_storage_root",
        lambda _path: str(unavailable_root),
    )

    updated = upsert_history(
        original,
        {
            "id": "abc123",
            "title": "Fresh local copy",
            "playlist_id": "PLone",
            "vodforge_output_type": "MP4",
        },
        replacement_location,
        replace_missing_media=True,
    )

    assert len(updated) == 2
    assert {history_output_dir(item) for item in updated} == {
        unavailable_location.resolve(),
        replacement_location.resolve(),
    }


def test_redownload_preserves_same_item_history_when_prior_folder_cannot_be_read(
    monkeypatch,
    tmp_path: Path,
):
    unavailable_location = tmp_path / "restricted" / "Example"
    unavailable_location.mkdir(parents=True)
    replacement_location = tmp_path / "downloads" / "Example"
    original = upsert_history(
        [],
        {"id": "abc123", "title": "Restricted example", "vodforge_output_type": "MP4"},
        unavailable_location,
    )
    original_iterdir = Path.iterdir

    def restricted_iterdir(path: Path):
        if path == unavailable_location.resolve():
            raise PermissionError("storage is temporarily unavailable")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", restricted_iterdir)

    updated = upsert_history(
        original,
        {"id": "abc123", "title": "Fresh local copy", "vodforge_output_type": "MP4"},
        replacement_location,
        replace_missing_media=True,
    )

    assert len(updated) == 2
    assert {history_output_dir(item) for item in updated} == {
        unavailable_location.resolve(),
        replacement_location.resolve(),
    }


def test_external_storage_roots_are_recognized_cross_platform():
    assert history_module._external_storage_root(
        PurePosixPath("/Volumes/Archive/Videos/Example"),
        platform_name="darwin",
    ) == "/Volumes/Archive"
    assert history_module._external_storage_root(
        PurePosixPath("/mnt/archive/Videos/Example"),
        platform_name="linux",
    ) == "/mnt/archive"
    assert history_module._external_storage_root(
        PureWindowsPath(r"E:\Videos\Example"),
        platform_name="win32",
    ) == "E:\\"


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
