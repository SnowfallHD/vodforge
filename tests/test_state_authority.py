"""Cross-surface state authority contracts for the VODForge desktop UI.

These tests intentionally guard ownership boundaries rather than individual
widget arrangements. A Forge run owns Forge identity and progress; Library
selection owns Library inspection; worker events may enrich only their run ID;
and each thumbnail surface owns its own asynchronous request generation.
"""

import re
from dataclasses import replace
from pathlib import Path

from yt_downloader.download_service import DownloadJob, ExportMode, OutputType
from yt_downloader.models import ManualExportSettings, Mp3ExportSettings
from yt_downloader.platform_services import focus_view_shortcut_bindings
from yt_downloader.ui_layout import WindowLogicalMetrics


class LogicalMetricsProbe:
    _vodforge_logical_metrics = WindowLogicalMetrics()

    def winfo_toplevel(self):
        return self


def contains_code(source: str, snippet: str) -> bool:
    """Compare source-bound contracts across formatter-only line wrapping."""
    return re.sub(r"\s+", "", snippet) in re.sub(r"\s+", "", source)


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class TextBuffer:
    def __init__(self):
        self.value = ""

    def config(self, **_kwargs):
        return None

    def insert(self, _index, value):
        self.value += str(value)

    def delete(self, _start, _end):
        self.value = ""

    def get(self, _start, _end):
        return self.value

    def see(self, _index):
        return None


class ScrollAwareTextBuffer(TextBuffer):
    def __init__(self, *, last: float):
        super().__init__()
        self.last = last
        self.seen: list[str] = []
        self.moved_to: list[float] = []

    def yview(self):
        return (0.0, self.last)

    def see(self, index):
        self.seen.append(str(index))

    def yview_moveto(self, fraction):
        self.moved_to.append(float(fraction))


class LiveWorker:
    def is_alive(self):
        return True


class QueueRecoveryOwner:
    def __init__(self):
        self.snapshots: list[list[str]] = []

    def queue_changed(self, jobs):
        self.snapshots.append([job.run_id for job in jobs])


class Control:
    def __init__(self):
        self.raised = False
        self.configured: list[dict[str, object]] = []

    def config(self, **kwargs):
        self.configured.append(dict(kwargs))

    configure = config

    def tkraise(self):
        self.raised = True


class IdleTextBuffer(ScrollAwareTextBuffer):
    def after_idle(self, callback):
        callback()


class SelectedTree:
    def __init__(self, index: int = 0):
        self.index = index

    def selection(self):
        return (str(self.index),)


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


def test_primary_view_shortcuts_are_stable_across_platforms():
    assert focus_view_shortcut_bindings("darwin") == (
        ("<Command-Key-1>", "forge"),
        ("<Command-Key-2>", "library"),
        ("<Command-Key-3>", "activity"),
    )
    expected_control = (
        ("<Control-Key-1>", "forge"),
        ("<Control-Key-2>", "library"),
        ("<Control-Key-3>", "activity"),
    )
    assert focus_view_shortcut_bindings("win32") == expected_control
    assert focus_view_shortcut_bindings("linux") == expected_control


def test_playlist_completed_artwork_is_item_scoped(tmp_path):
    from yt_downloader.thumbnail_state import (
        advance_thumbnail_item,
        matching_thumbnail_image,
    )

    job = make_job(tmp_path)
    job.preview_info = {"id": "second"}
    image = object()
    job.preview_thumbnail_image = image
    assert matching_thumbnail_image(job, {"id": "first"}) is None
    assert matching_thumbnail_image(job, {"id": "second"}) is image
    assert not advance_thumbnail_item(job, {"id": "second", "title": "Updated"})
    assert job.preview_thumbnail_image is image
    assert advance_thumbnail_item(job, {"id": "third"})
    assert job.preview_thumbnail_image is None


def test_download_jobs_receive_unique_ids_and_replace_preserves_one_run(tmp_path: Path):
    first = make_job(tmp_path, video_id="first")
    second = make_job(tmp_path, video_id="second")
    normalized_worker_copy = replace(first, url="https://youtu.be/first")

    assert first.run_id != second.run_id
    assert normalized_worker_copy.run_id == first.run_id
