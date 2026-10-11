"""Shared production-worker fixtures without importing UI test modules."""

import queue
from pathlib import Path

from yt_downloader.download_service import DownloadWorkerCore
from yt_downloader.models import (
    DownloadJob,
    ExportMode,
    ExportPlan,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)


def _worker_test_app() -> DownloadWorkerCore:
    app = DownloadWorkerCore.__new__(DownloadWorkerCore)
    app.events = queue.Queue()
    app.cancel_requested = False
    app.skip_video_requested = False
    app.skip_url_requested = False
    app._active_progress_context = None
    app._last_progress_event_at = 0.0
    return app


def _worker_test_job(
    tmp_path: Path,
    *,
    url: str = "https://www.youtube.com/playlist?list=playlist",
    urls: list[str] | None = None,
) -> DownloadJob:
    return DownloadJob(
        url=url,
        urls=list(urls or []),
        output_dir=tmp_path,
        output_type=OutputType.MP4,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=False,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=False,
        tags=[],
    )


def _worker_test_export_plan() -> ExportPlan:
    return ExportPlan(
        mode=ExportMode.AUTO_CBR,
        video_format_id="137",
        audio_format_id="140",
        format_selector="137+140",
        output_width=1920,
        output_height=1080,
        source_video_kbps=4_000.0,
        effective_video_kbps=4_000.0,
        video_bitrate_kbps=4_000,
        source_audio_kbps=128.0,
        effective_audio_kbps=128.0,
        audio_bitrate_kbps=192,
    )
