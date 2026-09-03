from __future__ import annotations

from pathlib import Path

from yt_downloader.library_media_recovery import LibraryMediaRecoveryPlan
from yt_downloader.library_media_recovery_ui import library_media_recovery_prompt
from yt_downloader.models import (
    DownloadJob,
    ExportMode,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)


def _job(tmp_path: Path) -> DownloadJob:
    return DownloadJob(
        url="https://www.youtube.com/watch?v=missing",
        output_dir=tmp_path / "saved",
        output_type=OutputType.MP3,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(bitrate_kbps=256),
        single_video_only=True,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=True,
        write_info_json=False,
        tags=[],
    )


def test_missing_media_prompt_exposes_exact_profile_and_redownload_action(
    tmp_path: Path,
) -> None:
    job = _job(tmp_path)
    prompt = library_media_recovery_prompt(
        LibraryMediaRecoveryPlan("missing", job.output_dir, job=job)
    )

    assert prompt.primary_action == "redownload"
    assert prompt.primary_label == "Redownload"
    assert "MP3 • 256 kbps" in prompt.detail
    assert str(job.output_dir) in prompt.detail
    assert "exact saved output profile" in prompt.message


def test_legacy_and_unavailable_prompts_fail_closed(tmp_path: Path) -> None:
    legacy = library_media_recovery_prompt(
        LibraryMediaRecoveryPlan("legacy", tmp_path / "saved")
    )
    unavailable = library_media_recovery_prompt(
        LibraryMediaRecoveryPlan("unavailable", tmp_path / "drive")
    )

    assert (legacy.primary_action, legacy.primary_label) == (
        "open_forge",
        "Open in Forge",
    )
    assert unavailable.primary_action == "none"
    assert "Reconnect" in unavailable.heading
