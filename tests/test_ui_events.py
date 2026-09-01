from pathlib import Path

from yt_downloader.models import (
    DownloadJob,
    ExportMode,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)
from yt_downloader.run_identity import annotate_job_metadata
from yt_downloader.ui_events import (
    history_record_event,
    installation_result_event,
    job_info_event,
    job_log_event,
    thumbnail_preview_event,
)


def _job(tmp_path: Path) -> DownloadJob:
    return DownloadJob(
        url="https://example.test/watch?v=fixture",
        output_dir=tmp_path,
        output_type=OutputType.MP4,
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


def test_job_event_constructors_preserve_fifo_wire_shape(tmp_path: Path):
    job = _job(tmp_path)
    info = {"id": "fixture", "title": "Fixture"}
    annotated = annotate_job_metadata(job, info)

    assert job_log_event(job, "started") == (
        "job_log",
        {"job": job, "line": "started"},
    )
    assert job_info_event("job_metadata", job, info) == (
        "job_metadata",
        {"job": job, "info": annotated},
    )
    assert history_record_event(job, info, str(tmp_path)) == (
        "history_record",
        {"job": job, "info": annotated, "output_dir": str(tmp_path)},
    )


def test_thumbnail_event_includes_only_the_available_result(tmp_path: Path):
    job = _job(tmp_path)

    success = thumbnail_preview_event(
        7,
        "https://example.test/thumb.jpg",
        "active",
        job.run_id,
        data=b"image",
    )
    failure = thumbnail_preview_event(
        8,
        "https://example.test/thumb.jpg",
        "library",
        job.run_id,
        error="unavailable",
    )

    assert success[1]["data"] == b"image"
    assert "error" not in success[1]
    assert failure[1]["error"] == "unavailable"
    assert "data" not in failure[1]


def test_installation_result_event_preserves_identity():
    assert installation_result_event("first_launch_result", True, "install-1") == (
        "first_launch_result",
        {"success": True, "install_id": "install-1"},
    )
