from dataclasses import replace
from pathlib import Path

from yt_downloader.models import (
    DownloadJob,
    ExportMode,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)
from yt_downloader.run_identity import (
    annotate_job_metadata,
    job_attempt_signature,
    job_output_profile,
    matching_attempt,
)


def make_job(root: Path) -> DownloadJob:
    return DownloadJob(
        url="https://youtu.be/abc123?si=tracking",
        urls=["https://www.youtube.com/watch?v=abc123"],
        output_dir=root,
        output_type=OutputType.MP4,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=True,
        use_nvenc=False,
        embed_thumbnail=True,
        write_thumbnail=False,
        embed_metadata=True,
        write_info_json=True,
        tags=["alpha", "beta"],
    )


def test_attempt_signature_matches_equivalent_source_and_ignores_run_state(
    tmp_path: Path,
) -> None:
    first = make_job(tmp_path)
    second = replace(
        first,
        url="https://www.youtube.com/watch?v=abc123&feature=share",
        urls=["https://youtu.be/abc123"],
        run_id="another-run",
        activity_lines=["prior progress"],
        terminal_status="Stopped",
    )

    assert job_attempt_signature(first) == job_attempt_signature(second)
    assert matching_attempt(first, [second]) is second


def test_attempt_signature_separates_settings_destination_and_organization(
    tmp_path: Path,
) -> None:
    original = make_job(tmp_path / "Downloads")
    different_quality = replace(original, quality_label="720p HD")
    different_destination = replace(original, output_dir=tmp_path / "Desktop")
    playlist_organized = replace(
        original,
        single_video_only=False,
        url="https://www.youtube.com/watch?v=abc123&list=PLsafe",
        urls=["https://www.youtube.com/watch?v=abc123&list=PLsafe"],
    )

    signatures = {
        job_attempt_signature(job)
        for job in (
            original,
            different_quality,
            different_destination,
            playlist_organized,
        )
    }
    assert len(signatures) == 4


def test_job_annotation_persists_profile_without_secret_url_data(
    tmp_path: Path,
) -> None:
    job = make_job(tmp_path)

    annotated = annotate_job_metadata(job, {"id": "abc123", "title": "Example"})

    assert annotated["vodforge_attempt_signature"] == job_attempt_signature(job)
    assert annotated["vodforge_output_profile"] == job_output_profile(job)
    assert annotated["vodforge_output_profile"] == "MP4 • 1080p Full HD • Auto CBR"
    assert "tracking" not in str(annotated)
