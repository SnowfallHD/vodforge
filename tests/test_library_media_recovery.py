from __future__ import annotations

from pathlib import Path

from yt_downloader.history import RETRY_JOB_METADATA_KEY, history_identity
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


def test_missing_media_recovery_retires_only_accepted_exact_history_row(
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
    owner = LibraryMediaRecoveryOwner(run_id_factory=lambda: "redownload-run")
    plan = owner.plan(record)

    remaining = owner.history_after_acceptance([record, other], plan)

    assert [history_identity(item) for item in remaining] == [history_identity(other)]


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
