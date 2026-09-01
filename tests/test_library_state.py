from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import pytest

from yt_downloader.history import history_identity, upsert_history
from yt_downloader.library_state import (
    ACTIVE_METADATA_RUN_ID_KEY,
    PROJECTION_OWNER_KIND_KEY,
    QUEUED_METADATA_RUN_ID_KEY,
    RUN_STATUS_KEY,
    LibraryProjectionOwner,
    is_metadata_preview,
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


def _projection(
    owner: LibraryProjectionOwner,
    *,
    history: list[dict[str, Any]] | None = None,
    active: DownloadJob | None = None,
    queued: list[DownloadJob] | None = None,
    terminal: list[DownloadJob] | None = None,
):
    return owner.reconcile(
        history_items=history or [],
        active_job=active,
        queued_jobs=queued or [],
        terminal_jobs=terminal or [],
    )


def test_projection_rows_are_deeply_immutable_and_snapshot_is_atomic(
    tmp_path: Path,
) -> None:
    owner = LibraryProjectionOwner()
    job = _job(tmp_path, video_id="immutable")
    job.preview_info = {"id": "immutable", "tags": ["one"], "nested": {"x": 1}}

    first = _projection(owner, active=job)
    with pytest.raises(TypeError):
        first.rows[0][RUN_STATUS_KEY] = "Stopped"
    with pytest.raises(TypeError):
        first.rows[0]["tags"].append("two")
    with pytest.raises(TypeError):
        first.rows[0]["nested"]["x"] = 2

    owner.observe_phase(job.run_id, "Downloading")
    second = _projection(owner, active=job)
    assert first is not second
    assert first.rows[0][RUN_STATUS_KEY] == "Preparing"
    assert second.rows[0][RUN_STATUS_KEY] == "Downloading"


def test_queued_preparing_and_terminal_replace_one_run_projection(
    tmp_path: Path,
) -> None:
    owner = LibraryProjectionOwner()
    job = _job(tmp_path, video_id="")

    queued = _projection(owner, queued=[job])
    assert len(queued.rows) == 1
    assert queued.rows[0][QUEUED_METADATA_RUN_ID_KEY] == job.run_id
    assert queued.rows[0][RUN_STATUS_KEY] == "Queued"

    preparing = _projection(owner, active=job)
    assert len(preparing.rows) == 1
    assert preparing.rows[0][ACTIVE_METADATA_RUN_ID_KEY] == job.run_id
    assert preparing.rows[0][RUN_STATUS_KEY] == "Preparing"

    job.terminal_status = "Stopped"
    job.terminal_message = "Download cancelled."
    stopped = _projection(owner, active=job, terminal=[job])
    assert len(stopped.rows) == 1
    assert stopped.rows[0]["vodforge_terminal_run_id"] == job.run_id
    assert stopped.rows[0]["vodforge_terminal_status"] == "Stopped"
    assert stopped.violations == ()
    assert stopped == _projection(owner, active=job, terminal=[job])


def test_same_video_distinct_runs_remain_distinct(tmp_path: Path) -> None:
    owner = LibraryProjectionOwner()
    first = _job(tmp_path, video_id="same")
    second = _job(tmp_path, video_id="same")
    first.preview_info = {"id": "same", "title": "First"}
    second.preview_info = {"id": "same", "title": "Second"}
    first.terminal_status = "Stopped"

    projection = _projection(owner, queued=[second], terminal=[first])
    assert len(projection.rows) == 2
    assert {
        row.get(QUEUED_METADATA_RUN_ID_KEY) or row.get("vodforge_terminal_run_id")
        for row in projection.rows
    } == {first.run_id, second.run_id}


def test_metadata_arriving_after_terminalization_cannot_resurrect_transient(
    tmp_path: Path,
) -> None:
    owner = LibraryProjectionOwner()
    job = _job(tmp_path, video_id="late")
    job.terminal_status = "Stopped"
    terminal = _projection(owner, terminal=[job])
    job.preview_info = {"id": "late", "title": "Late metadata"}
    owner.observe_phase(job.run_id, "Downloading")
    after_late_event = _projection(owner, terminal=[job])

    assert len(terminal.rows) == len(after_late_event.rows) == 1
    assert after_late_event.rows[0]["vodforge_terminal_status"] == "Stopped"
    assert RUN_STATUS_KEY not in after_late_event.rows[0]


def test_preview_owner_is_explicit_and_removable() -> None:
    owner = LibraryProjectionOwner()
    source = {"id": "preview", "title": "Preview", "vodforge_output_type": "MP3"}
    owner.record_preview("preview:request-7", [source])
    projection = _projection(owner)

    assert projection.rows[0]["vodforge_preview_run_id"] == "preview:request-7"
    assert is_metadata_preview(projection.rows[0])
    assert projection.rows[0][PROJECTION_OWNER_KIND_KEY] == "preview"
    owner.remove_preview("preview:request-7")
    assert _projection(owner).rows == ()


def test_seeded_transition_sequences_preserve_projection_invariants(
    tmp_path: Path,
) -> None:
    randomizer = random.Random(381996)
    for _case in range(50):
        owner = LibraryProjectionOwner()
        jobs = [_job(tmp_path, video_id="same") for _ in range(3)]
        queued = list(jobs)
        active: DownloadJob | None = None
        terminal: list[DownloadJob] = []
        for _step in range(30):
            action = randomizer.choice(("start", "phase", "stop", "fail", "complete"))
            if action == "start" and active is None and queued:
                active = queued.pop(0)
            elif action == "phase" and active is not None:
                owner.observe_phase(
                    active.run_id,
                    randomizer.choice(("Preparing", "Downloading", "Transcoding")),
                )
            elif action in {"stop", "fail"} and active is not None:
                active.terminal_status = "Stopped" if action == "stop" else "Failed"
                terminal.append(active)
                active = None
            elif action == "complete" and active is not None:
                active.terminal_status = "Completed"
                terminal.append(active)
                active = None
            projection = _projection(
                owner, active=active, queued=queued, terminal=terminal
            )
            run_ids = [
                str(
                    row.get(ACTIVE_METADATA_RUN_ID_KEY)
                    or row.get(QUEUED_METADATA_RUN_ID_KEY)
                    or row.get("vodforge_terminal_run_id")
                )
                for row in projection.rows
            ]
            assert len(run_ids) == len(set(run_ids))
            assert set(run_ids) == {
                *(job.run_id for job in queued),
                *(job.run_id for job in terminal),
                *((active.run_id,) if active is not None else ()),
            }
            assert projection.violations == ()
            assert projection == _projection(
                owner, active=active, queued=queued, terminal=terminal
            )


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
