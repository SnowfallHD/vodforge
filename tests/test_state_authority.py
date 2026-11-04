"""Cross-surface state authority contracts for the VODForge desktop UI.

These tests intentionally guard ownership boundaries rather than individual
widget arrangements. A Forge run owns Forge identity and progress; Library
selection owns Library inspection; worker events may enrich only their run ID;
and each thumbnail surface owns its own asynchronous request generation.
"""

from dataclasses import replace
from pathlib import Path

from yt_downloader.download_service import DownloadJob, ExportMode, OutputType
from yt_downloader.models import ManualExportSettings, Mp3ExportSettings


class Control:
    def __init__(self):
        self.raised = False
        self.configured: list[dict[str, object]] = []

    def config(self, **kwargs):
        self.configured.append(dict(kwargs))

    configure = config

    def tkraise(self):
        self.raised = True


def make_job(tmp_path: Path, *, video_id: str = "authority-id") -> DownloadJob:
    return DownloadJob(
        url=f"https://www.youtube.com/watch?v={video_id}",
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


def test_playlist_completed_artwork_is_item_scoped(tmp_path):
    from yt_downloader.thumbnail_state import matching_thumbnail_image

    job = make_job(tmp_path)
    job.preview_info = {"id": "second"}
    image = object()
    job.preview_thumbnail_image = image
    assert matching_thumbnail_image(job, {"id": "first"}) is None
    assert matching_thumbnail_image(job, {"id": "second"}) is image


def test_download_jobs_receive_unique_ids_and_replace_preserves_one_run(tmp_path: Path):
    first = make_job(tmp_path, video_id="first")
    second = make_job(tmp_path, video_id="second")
    normalized_worker_copy = replace(first, url="https://youtu.be/first")

    assert first.run_id != second.run_id
    assert normalized_worker_copy.run_id == first.run_id
