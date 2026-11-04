from pathlib import Path

from yt_downloader.models import (
    DownloadJob,
    ExportMode,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)
from yt_downloader.run_identity import annotate_job_metadata
from yt_downloader.worker_events import (
    history_record_event,
    job_info_event,
    job_log_event,
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
