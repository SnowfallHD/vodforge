from __future__ import annotations

from pathlib import Path

import pytest

from yt_downloader.app import video_output_dir
from yt_downloader.history import (
    RETRY_JOB_METADATA_KEY,
    history_identity,
    upsert_history,
)
from yt_downloader.library_media_recovery import LibraryMediaRecoveryOwner
from yt_downloader.models import (
    DownloadJob,
    ExportMode,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)
from yt_downloader.run_identity import annotate_job_metadata, job_attempt_signature
from yt_downloader.run_state import serialize_download_job


def _job(tmp_path: Path) -> DownloadJob:
    return DownloadJob(
        url="https://www.youtube.com/watch?v=missing",
        urls=["https://www.youtube.com/watch?v=missing"],
        output_dir=tmp_path / "downloads",
        output_type=OutputType.MP3,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(
            bitrate_kbps=256,
            sample_rate="48000",
            channels="2",
            embed_metadata=True,
            embed_cover_art=True,
            custom_cover_art_path=tmp_path / "art.jpg",
        ),
        single_video_only=True,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=False,
        tags=["saved-tag"],
        run_id="completed-run",
    )


def _missing_record(job: DownloadJob) -> dict[str, object]:
    record = annotate_job_metadata(
        job,
        {
            "id": "missing",
            "title": "Missing media",
            "webpage_url": job.url,
            "vodforge_output_type": job.output_type.value,
            "vodforge_output_dir": str(job.output_dir),
            "vodforge_output_path": str(job.output_dir / "Missing media.mp3"),
            "vodforge_run_id": job.run_id,
        },
    )
    record[RETRY_JOB_METADATA_KEY] = serialize_download_job(job)
    record["vodforge_annotation_owner"] = f"run:{job.run_id}"
    return record


@pytest.mark.parametrize("playlist", [False, True])
def test_legacy_generated_location_restores_root_without_rewriting_history(
    tmp_path, playlist
):
    original = _job(tmp_path)
    record = _missing_record(original)
    record.pop(RETRY_JOB_METADATA_KEY)
    record.update(channel="Channel", title="Video", id="missing")
    if playlist:
        record.update(playlist_title="Playlist", playlist_id="PL-example")
    location = video_output_dir(original.output_dir, record)
    record["vodforge_output_dir"] = str(location)
    record["vodforge_output_path"] = str(location / "Video.mp3")
    before = dict(record)
    owner = LibraryMediaRecoveryOwner(artifact_directory=video_output_dir)
    for _ in range(2):
        plan = owner.plan(record)
        assert plan.destination == original.output_dir
        assert not plan.requires_destination_choice
        assert not plan.can_redownload  # Missing profile still requires review.
        assert record == before


@pytest.mark.parametrize("saved_job", [False, True])
def test_nested_legacy_root_requires_choice_even_after_new_retry_record(
    tmp_path, saved_job
):
    original = _job(tmp_path)
    metadata = {"channel": "Channel", "title": "Video", "id": "missing"}
    original.output_dir = video_output_dir(original.output_dir, metadata)
    record = _missing_record(original)
    record.update(metadata)
    nested = video_output_dir(original.output_dir, record)
    record["vodforge_output_dir"] = str(nested)
    record["vodforge_output_path"] = str(nested / "Video.mp3")
    if not saved_job:
        record.pop(RETRY_JOB_METADATA_KEY)
    plan = LibraryMediaRecoveryOwner(artifact_directory=video_output_dir).plan(record)
    assert plan.requires_destination_choice
    assert plan.destination is None
    assert not plan.can_redownload


def test_unrecognized_legacy_path_does_not_guess_parent(tmp_path):
    record = _missing_record(_job(tmp_path))
    record.pop(RETRY_JOB_METADATA_KEY)
    plan = LibraryMediaRecoveryOwner(artifact_directory=video_output_dir).plan(record)
    assert plan.destination is None
    assert plan.requires_destination_choice


def test_recovery_destination_is_session_only_and_expires_with_source(tmp_path):
    owner = LibraryMediaRecoveryOwner()
    default = str(tmp_path / "default")
    chosen = tmp_path / "one-download"
    owner.prepare_destination("source", chosen)
    assert owner.destination_for("source", default) == str(chosen)
    assert owner.destination_for("source", default) == str(chosen)
    assert owner.destination_for("", default) == default
    assert owner.destination_for("source", default) == default
    owner.prepare_destination("source", chosen)
    owner.clear_destination()
    assert owner.destination_for("source", default) == default


def test_cancelling_unknown_root_does_not_change_forge():
    from types import SimpleNamespace
    from unittest.mock import Mock

    from yt_downloader.app import DownloaderApp
    from yt_downloader.library_media_recovery import LibraryMediaRecoveryPlan

    app = SimpleNamespace(
        _pick_output_directory=Mock(return_value=None),
        url_var=Mock(),
        output_var=Mock(),
        output_type_var=Mock(),
        _select_focus_view=Mock(),
    )
    DownloaderApp._open_missing_media_in_forge(
        app,
        {},
        LibraryMediaRecoveryPlan("legacy", None, requires_destination_choice=True),
    )
    app.url_var.set.assert_not_called()
    app.output_var.set.assert_not_called()
    app._select_focus_view.assert_not_called()


def test_missing_media_rebuilds_exact_saved_job_with_fresh_run_identity(
    tmp_path: Path,
) -> None:
    original = _job(tmp_path)
    record = _missing_record(original)
    owner = LibraryMediaRecoveryOwner(run_id_factory=lambda: "redownload-run")

    plan = owner.plan(record)

    assert plan.can_redownload is True
    assert plan.job is not None
    assert plan.job.run_id == "redownload-run"
    assert plan.job.origin_run_id == "completed-run"
    assert plan.job.output_dir == original.output_dir
    assert plan.job.mp3_settings == original.mp3_settings
    assert plan.job.tags == ["saved-tag"]
    assert job_attempt_signature(plan.job) == job_attempt_signature(original)
    assert plan.previous_annotation_owner == "run:completed-run"


def test_missing_nested_artifact_rebuilds_from_user_selected_base(
    tmp_path: Path,
) -> None:
    original = _job(tmp_path)
    record = _missing_record(original)
    nested = original.output_dir / "Channel" / "Playlist" / "Video"
    record["vodforge_output_dir"] = str(nested)
    record["vodforge_output_path"] = str(nested / "Missing media.mp3")
    owner = LibraryMediaRecoveryOwner(run_id_factory=lambda: "redownload-run")

    plan = owner.plan(record)

    assert plan.can_redownload is True
    assert plan.destination == original.output_dir
    assert plan.job is not None
    assert plan.job.output_dir == original.output_dir


def test_missing_artifact_outside_saved_base_is_rejected(tmp_path: Path) -> None:
    original = _job(tmp_path)
    record = _missing_record(original)
    outside = tmp_path / "other" / "Channel" / "Video"
    record["vodforge_output_dir"] = str(outside)
    record["vodforge_output_path"] = str(outside / "Missing media.mp3")

    plan = LibraryMediaRecoveryOwner().plan(record)

    assert plan.kind == "invalid"
    assert plan.can_redownload is False


def test_missing_media_recovery_retires_only_committed_exact_history_row(
    tmp_path: Path,
) -> None:
    original = _job(tmp_path)
    record = _missing_record(original)
    other = {
        **record,
        "id": "other",
        "title": "Other",
        "vodforge_output_path": str(original.output_dir / "Other.mp3"),
    }
    replacement = {
        **record,
        "vodforge_output_path": str(original.output_dir / "replacement.mp3"),
    }
    (original.output_dir).mkdir(parents=True, exist_ok=True)
    Path(replacement["vodforge_output_path"]).write_bytes(b"committed")

    remaining = upsert_history(
        [record, other], replacement, original.output_dir, replace_missing_media=True
    )

    assert [history_identity(item) for item in remaining] == [
        history_identity(replacement),
        history_identity(other),
    ]


def test_single_item_recovery_reuses_exact_saved_source_without_watch_url(
    tmp_path: Path,
) -> None:
    original = _job(tmp_path)
    original.url = "https://example.com/video-page"
    original.urls = [original.url]
    original.preview_info = {"id": "missing"}
    record = _missing_record(original)
    record["original_url"] = original.url

    plan = LibraryMediaRecoveryOwner().plan(record)

    assert plan.can_redownload and plan.job is not None
    assert plan.job.url == original.url
    assert plan.job.urls == [original.url]

    original.preview_info = {"id": "different"}
    mismatched = _missing_record(original)
    mismatched["original_url"] = original.url
    fallback = LibraryMediaRecoveryOwner().plan(mismatched)
    assert fallback.can_redownload and fallback.job is not None
    assert fallback.job.url == "https://www.youtube.com/watch?v=missing"


def test_tk_recovery_review_prepares_the_same_saved_source(tmp_path: Path) -> None:
    from types import SimpleNamespace
    from unittest.mock import Mock

    from yt_downloader.app import DownloaderApp

    original = _job(tmp_path)
    original.url = "https://example.com/video-page"
    original.urls = [original.url]
    original.preview_info = {"id": "missing"}
    record = _missing_record(original)
    record["original_url"] = original.url
    owner = LibraryMediaRecoveryOwner()
    plan = owner.plan(record)
    assert plan.can_redownload
    app = SimpleNamespace(
        _pick_output_directory=Mock(),
        _reset_source_input_after_send=Mock(),
        url_var=Mock(),
        library_media_recovery=owner,
        _sync_focus_destination=Mock(),
        output_type_var=Mock(),
        _select_focus_view=Mock(),
        status_var=Mock(),
    )

    DownloaderApp._open_missing_media_in_forge(app, record, plan)

    app.url_var.set.assert_called_once_with(original.url)
    assert owner.is_draft_for(original.url)


def test_legacy_or_tampered_missing_media_never_guesses_saved_settings(
    tmp_path: Path,
) -> None:
    original = _job(tmp_path)
    legacy = _missing_record(original)
    legacy.pop(RETRY_JOB_METADATA_KEY)
    owner = LibraryMediaRecoveryOwner(run_id_factory=lambda: "redownload-run")

    assert owner.plan(legacy).kind == "legacy"

    tampered = _missing_record(original)
    tampered_payload = dict(tampered[RETRY_JOB_METADATA_KEY])
    tampered_payload["output_dir"] = str(tmp_path / "different")
    tampered[RETRY_JOB_METADATA_KEY] = tampered_payload
    assert owner.plan(tampered).kind == "invalid"


@pytest.mark.parametrize("new_base", ["archive", "renamed-export"])
def test_relinked_missing_media_keeps_saved_settings_and_requires_new_base(
    tmp_path, new_base
):
    from copy import deepcopy

    original = _job(tmp_path)
    record = _missing_record(original)
    record.update(
        vodforge_relinked=True,
        vodforge_archive_id="stable-relocated-owner",
        vodforge_archive_annotation_owner="run:completed-run",
        vodforge_output_dir=str(tmp_path / new_base),
        vodforge_output_path=str(tmp_path / new_base / "renamed.mp3"),
    )
    before = deepcopy(record)
    owner = LibraryMediaRecoveryOwner(run_id_factory=lambda: "recovered")
    plan = owner.plan(record)
    assert plan.can_redownload and plan.requires_destination_choice
    assert plan.destination is None
    assert plan.job.mp3_settings == original.mp3_settings
    assert plan.job.tags == original.tags
    chosen = tmp_path / "chosen-base"
    accepted = owner.with_destination(plan, chosen)
    assert accepted.destination == chosen and not accepted.requires_destination_choice
    assert accepted.job.output_dir == chosen
    assert accepted.job.mp3_settings == original.mp3_settings
    assert plan.job.output_dir == original.output_dir
    assert "vodforge_archive_id" not in accepted.job.preview_info
    assert "vodforge_relinked" not in accepted.job.preview_info
    assert accepted.previous_annotation_owner == "run:completed-run"
    assert record == before
    assert not chosen.exists()


def test_relinked_marker_never_bypasses_saved_profile_signature_validation(tmp_path):
    record = _missing_record(_job(tmp_path))
    record["vodforge_relinked"] = True
    record["vodforge_output_dir"] = str(tmp_path / "elsewhere")
    record["vodforge_output_path"] = str(tmp_path / "elsewhere" / "clip.mp3")
    record[RETRY_JOB_METADATA_KEY]["output_dir"] = str(tmp_path / "tampered")
    assert LibraryMediaRecoveryOwner().plan(record).kind == "invalid"


@pytest.mark.parametrize(
    ("mode", "saved_label", "expected"),
    [
        (ExportMode.AUTO_CBR, "Auto CBR", ExportMode.EVERYDAY),
        (ExportMode.AUTO_CBR, "Auto CBR (Recommended)", ExportMode.EVERYDAY),
        (ExportMode.AUTO_CBR, None, ExportMode.EVERYDAY),
        (ExportMode.AUTO_CBR, "CTV", ExportMode.AUTO_CBR),
        (ExportMode.STRICT_COMPLIANCE, "Strict Compliance", ExportMode.EVERYDAY),
        (
            ExportMode.STRICT_COMPLIANCE,
            "CTV (legacy fixed bitrate)",
            ExportMode.EVERYDAY,
        ),
        (ExportMode.EVERYDAY, "Everyday", ExportMode.EVERYDAY),
        (ExportMode.STREAMING, "Streaming", ExportMode.STREAMING),
        (ExportMode.EDITING, "Editing", ExportMode.EDITING),
        (ExportMode.SHARING, "Sharing", ExportMode.SHARING),
        (ExportMode.MANUAL_OVERRIDE, "Custom", ExportMode.MANUAL_OVERRIDE),
        (ExportMode.MANUAL_OVERRIDE, "Manual Override", ExportMode.MANUAL_OVERRIDE),
    ],
)
def test_redownload_migrates_only_retired_presets_after_authority_validation(
    tmp_path, mode, saved_label, expected
):
    from copy import deepcopy

    from yt_downloader.run_identity import (
        ATTEMPT_SIGNATURE_KEY,
        OUTPUT_PROFILE_KEY,
        OUTPUT_VARIANT_KEY,
        job_output_profile,
        job_output_variant,
    )

    original = _job(tmp_path)
    original.output_type = OutputType.MP4
    original.export_mode = mode
    row = _missing_record(original)
    row["vodforge_output_path"] = str(original.output_dir / "Missing media.mp4")
    if saved_label is None:
        row.pop(OUTPUT_PROFILE_KEY)
    else:
        row[OUTPUT_PROFILE_KEY] = f"MP4 • {original.quality_label} • {saved_label}"
    before_row = deepcopy(row)
    before_job = serialize_download_job(original)

    plan = LibraryMediaRecoveryOwner().plan(row)
    assert plan.can_redownload and plan.job is not None
    assert plan.job.export_mode is expected
    assert getattr(plan, "preset_migrated", False) is (expected != mode)
    assert plan.job.preview_info[ATTEMPT_SIGNATURE_KEY] == job_attempt_signature(
        plan.job
    )
    assert plan.job.preview_info[OUTPUT_PROFILE_KEY] == job_output_profile(plan.job)
    assert plan.job.preview_info[OUTPUT_VARIANT_KEY] == job_output_variant(plan.job)
    assert plan.job.output_dir == original.output_dir
    assert plan.job.manual_settings == original.manual_settings
    assert plan.job.tags == original.tags
    assert row == before_row
    assert serialize_download_job(original) == before_job

    # Changing the original signed intent cannot be hidden by mapping both to Everyday.
    tampered = deepcopy(row)
    tampered[RETRY_JOB_METADATA_KEY]["quality_label"] = "720p HD"
    assert LibraryMediaRecoveryOwner().plan(tampered).kind == "invalid"


@pytest.mark.parametrize("output_type", list(OutputType))
@pytest.mark.parametrize(
    "source_kind", ["single", "watch_playlist", "playlist", "batch"]
)
def test_missing_item_recovery_downloads_only_captured_video(
    tmp_path, output_type, source_kind
):
    from copy import deepcopy
    from urllib.parse import parse_qs, urlsplit

    original = _job(tmp_path)
    original.output_type = output_type
    original.export_mode = ExportMode.SHARING
    original.url = {
        "single": "https://www.youtube.com/watch?v=selected",
        "watch_playlist": "https://www.youtube.com/watch?v=first&list=PL-saved",
        "playlist": "https://www.youtube.com/playlist?list=PL-saved",
        "batch": "https://www.youtube.com/watch?v=first",
    }[source_kind]
    original.urls = [original.url]
    original.single_video_only = source_kind == "single"
    original.batch_mode = source_kind == "batch"
    if original.batch_mode:
        original.urls.append("https://www.youtube.com/watch?v=other")
    row = _missing_record(original)
    row.update(id="selected", title="Selected missing video")
    if source_kind != "single":
        row.update(playlist_id="PL-saved", playlist_title="Saved playlist")
    before = deepcopy(row)
    original_job = serialize_download_job(original)
    plan = LibraryMediaRecoveryOwner(run_id_factory=lambda: "new-recovery").plan(row)
    assert plan.can_redownload and plan.job is not None
    job = plan.job
    query = parse_qs(urlsplit(job.url).query)
    assert query.get("v") == ["selected"], "Recovery must address the captured video"
    assert job.urls == [job.url]
    assert job.single_video_only and not job.batch_mode
    assert job.output_type is output_type
    assert job.export_mode is original.export_mode
    assert job.mp3_settings == original.mp3_settings
    assert job.output_dir == original.output_dir
    assert job.preview_info["id"] == "selected"
    assert job.preview_info.get("playlist_title") == row.get("playlist_title")
    assert query.get("list") == (["PL-saved"] if source_kind != "single" else None)
    assert plan.previous_annotation_owner == "run:completed-run"
    assert row == before
    assert serialize_download_job(original) == original_job
    sibling = {
        **row,
        "id": "other",
        "vodforge_output_path": str(original.output_dir / "Other.mp4"),
    }
    assert history_identity(row) != history_identity(sibling)


@pytest.mark.parametrize("video_id", ["", "../other", "bad&list=other"])
def test_missing_identity_never_replays_original_playlist(tmp_path, video_id):
    original = _job(tmp_path)
    original.single_video_only = False
    original.url = "https://www.youtube.com/playlist?list=PL-saved"
    original.urls = [original.url]
    row = _missing_record(original)
    row["id"] = video_id
    assert LibraryMediaRecoveryOwner().plan(row).kind == "invalid"


@pytest.mark.parametrize("output_type", [OutputType.MP3, OutputType.ORIGINAL])
def test_audio_recovery_ignores_retired_inactive_mp4_preset(tmp_path, output_type):
    original = _job(tmp_path)
    original.output_type = output_type
    original.export_mode = ExportMode.STRICT_COMPLIANCE
    plan = LibraryMediaRecoveryOwner().plan(_missing_record(original))
    assert plan.job.export_mode is ExportMode.STRICT_COMPLIANCE
    assert not getattr(plan, "preset_migrated", False)
    assert plan.job.mp3_settings == original.mp3_settings
