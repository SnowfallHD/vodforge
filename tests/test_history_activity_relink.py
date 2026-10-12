from __future__ import annotations

from yt_downloader import history
from yt_downloader.models import (
    DownloadJob,
    ExportMode,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)


def job_for(path, item):
    job = DownloadJob(
        url="https://www.youtube.com/watch?v=fixture",
        output_dir=path,
        output_type=OutputType.MP4,
        quality_label="1080p",
        export_mode=ExportMode.EVERYDAY,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=True,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=True,
        write_info_json=False,
        tags=[],
    )
    job.run_id = "run-one"
    job.history_identities = {history.history_identity(item)}
    job.activity_lines = ["Initial", "Accepted while relinking"]
    return job
