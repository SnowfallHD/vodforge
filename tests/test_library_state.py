from __future__ import annotations

from pathlib import Path

from yt_downloader.history import history_identity, upsert_history
from yt_downloader.library_state import (
    ACTIVE_METADATA_RUN_ID_KEY,
    claim_active_metadata_row,
    is_metadata_preview,
    merge_library_metadata_items,
    metadata_output_type,
    metadata_run_key,
    persisted_run_deck_records,
)
from yt_downloader.models import (
    DownloadJob,
    ExportMode,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)


def _job(
    tmp_path: Path, *, video_id: str, output_type: OutputType = OutputType.MP4
) -> DownloadJob:
    return DownloadJob(
        url=f"https://www.youtube.com/watch?v={video_id}",
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


def test_merge_updates_existing_row_and_list_in_place() -> None:
    row = {
        "id": "same",
        "title": "Old title",
        "vodforge_output_type": "MP4",
        "vodforge_preview_complete": True,
        "vodforge_preview_run_id": "preview:old",
    }
    items = [row]

    result = merge_library_metadata_items(
        items,
        [{"id": "same", "title": "Fresh title", "vodforge_output_type": "MP4"}],
    )

    assert result.items is items
    assert result.items[0] is row
    assert row["title"] == "Fresh title"
    assert "vodforge_preview_complete" not in row
    assert "vodforge_preview_run_id" not in row


def test_merge_prepends_new_rows_and_collapses_incoming_duplicates() -> None:
    existing_row = {"id": "older", "title": "Older", "vodforge_output_type": "MP4"}
    items = [existing_row]

    result = merge_library_metadata_items(
        items,
        [
            {"id": "new", "title": "First title", "vodforge_output_type": "MP4"},
            {"id": "new", "title": "Final title", "vodforge_output_type": "MP4"},
        ],
    )

    assert result.items is not items
    assert [item["id"] for item in result.items] == ["new", "older"]
    assert result.items[0]["title"] == "Final title"
    assert result.items[1] is existing_row


def test_active_merge_claims_ephemeral_row_without_overwriting_saved_row(
    tmp_path: Path,
) -> None:
    saved = upsert_history(
        [],
        {"id": "same", "title": "Saved copy", "vodforge_output_type": "MP4"},
        tmp_path,
    )[0]
    ephemeral = {
        "id": "same",
        "title": "Old failure",
        "vodforge_output_type": "MP4",
        "vodforge_terminal_status": "Failed",
        "vodforge_terminal_run_id": "failed:old",
    }
    items = [saved, ephemeral]

    result = merge_library_metadata_items(
        items,
        [{"id": "same", "title": "Fresh active", "vodforge_output_type": "MP4"}],
        active_run_id="active:new",
    )

    assert result.items is items
    assert saved["title"] == "Saved copy"
    assert ephemeral["title"] == "Fresh active"
    assert ephemeral[ACTIVE_METADATA_RUN_ID_KEY] == "active:new"
    assert "vodforge_terminal_status" not in ephemeral
    assert "vodforge_terminal_run_id" not in ephemeral


def test_merge_keeps_mp3_and_mp4_rows_separate_for_one_provider_item() -> None:
    mp4 = {"id": "same", "title": "Video", "vodforge_output_type": "MP4"}

    result = merge_library_metadata_items(
        [mp4],
        [{"id": "same", "title": "Audio", "vodforge_output_type": "MP3"}],
    )

    assert [metadata_output_type(item) for item in result.items] == [
        OutputType.MP3,
        OutputType.MP4,
    ]
    assert metadata_run_key(result.items[0]) == ("same", "MP3")
    assert metadata_run_key(result.items[1]) == ("same", "MP4")


def test_preview_merge_retains_exact_preview_run_identity() -> None:
    result = merge_library_metadata_items(
        [],
        [{"id": "preview", "title": "Preview", "vodforge_output_type": "MP3"}],
        preview_complete=True,
        preview_run_id="preview:request-7",
    )

    assert result.items[0]["vodforge_preview_run_id"] == "preview:request-7"
    assert is_metadata_preview(result.items[0])
    assert (
        claim_active_metadata_row(
            result.items[0],
            {"id": "preview", "vodforge_output_type": "MP3"},
            "active:8",
        )[ACTIVE_METADATA_RUN_ID_KEY]
        == "active:8"
    )
    assert not is_metadata_preview(result.items[0])


def test_persisted_records_filter_live_owners_and_keep_saved_output_separate(
    tmp_path: Path,
) -> None:
    active_preview = {
        "id": "active",
        "title": "Active metadata",
        "vodforge_output_type": "MP4",
        "vodforge_preview_complete": True,
    }
    terminal_preview = {
        "id": "terminal",
        "title": "Terminal metadata",
        "vodforge_output_type": "MP3",
        "vodforge_preview_complete": True,
    }
    saved = upsert_history(
        [],
        {"id": "active", "title": "Saved MP4", "vodforge_output_type": "MP4"},
        tmp_path,
    )[0]
    independent_preview = {
        "id": "independent",
        "title": "Independent MP3",
        "vodforge_output_type": "MP3",
        "vodforge_preview_complete": True,
        "vodforge_preview_run_id": "preview:independent",
    }

    records = persisted_run_deck_records(
        [active_preview, terminal_preview, saved, independent_preview],
        active_metadata_keys={("active", "MP4")},
        terminal_metadata_keys={("terminal", "MP3")},
        active_history_identities=set(),
        completed_jobs=[],
    )

    assert [
        (record["kind"], record["title"], record["output_type"]) for record in records
    ] == [
        ("completed", "Saved MP4", "MP4"),
        ("preview", "Independent MP3", "MP3"),
    ]
    assert records[1]["run_id"] == "preview:independent"


def test_persisted_record_uses_newest_completed_owner(tmp_path: Path) -> None:
    saved = upsert_history(
        [],
        {"id": "same", "title": "Same item", "vodforge_output_type": "MP4"},
        tmp_path,
    )[0]
    identity = history_identity(saved)
    newest = _job(tmp_path, video_id="same")
    oldest = _job(tmp_path, video_id="same")
    newest.history_identities.add(identity)
    oldest.history_identities.add(identity)

    records = persisted_run_deck_records(
        [saved],
        active_metadata_keys=set(),
        terminal_metadata_keys=set(),
        active_history_identities=set(),
        completed_jobs=[newest, oldest],
    )

    assert len(records) == 1
    assert records[0]["job"] is newest
    assert records[0]["run_id"] == newest.run_id


def test_active_saved_identity_is_hidden_until_commit_finishes(tmp_path: Path) -> None:
    saved = upsert_history(
        [],
        {"id": "active", "title": "Committed", "vodforge_output_type": "MP4"},
        tmp_path,
    )[0]

    records = persisted_run_deck_records(
        [saved],
        active_metadata_keys=set(),
        terminal_metadata_keys=set(),
        active_history_identities={history_identity(saved)},
        completed_jobs=[],
    )

    assert records == []
