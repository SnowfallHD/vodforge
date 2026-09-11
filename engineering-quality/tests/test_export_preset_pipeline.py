"""Offline provider boundary, real production transcode/validation/commit/reuse."""

import os
import queue
import shutil
import subprocess

import pytest
from quality_harness.fixtures import find_ffmpeg, find_ffprobe

from yt_downloader import app as app_module
from yt_downloader.export_planning import EXPORT_MODES, export_mode_from_display_name
from yt_downloader.models import (
    DownloadJob,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    ffmpeg = find_ffmpeg()
    path = tmp_path_factory.mktemp("preset-media") / "source.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=523:sample_rate=48000",
            "-t",
            "3",
            "-c:v",
            "libx264",
            "-crf",
            "16",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return path, ffmpeg, find_ffprobe(ffmpeg)


@pytest.mark.parametrize(
    "use_nvenc",
    [
        False,
        pytest.param(
            True,
            marks=pytest.mark.skipif(
                os.environ.get("VODFORGE_NVENC_TESTS") != "1",
                reason="requires an explicitly enabled NVIDIA hardware run",
            ),
        ),
    ],
)
@pytest.mark.parametrize("preset", [*EXPORT_MODES, "Custom quality"])
def test_preset_commits_and_reuses_real_valid_media(
    monkeypatch, tmp_path, source, preset, use_nvenc
):
    path, ffmpeg, ffprobe = source
    info = {
        "id": "abc123",
        "title": "Preset fixture",
        "uploader": "QA",
        "duration": 3,
        "webpage_url": "https://www.youtube.com/watch?v=abc123",
        "formats": [
            {
                "format_id": "v",
                "vcodec": "avc1",
                "acodec": "none",
                "height": 360,
                "width": 640,
                "fps": 30,
                "vbr": 1500,
                "ext": "mp4",
            },
            {
                "format_id": "a",
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "abr": 130,
                "ext": "m4a",
            },
        ],
    }
    downloads = []

    class Provider:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, *, download):
            assert not download
            return dict(info)

        def process_ie_result(self, selected, *, download):
            from pathlib import Path

            assert download
            target = Path(self.options["paths"]["home"]) / self.options[
                "outtmpl"
            ].replace("%(id)s", "abc123").replace("%(ext)s", "mp4")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            downloads.append(target)
            return dict(selected)

    from types import SimpleNamespace

    monkeypatch.setattr(
        app_module, "load_yt_dlp", lambda: SimpleNamespace(YoutubeDL=Provider)
    )
    monkeypatch.setattr(app_module, "write_diagnostic", lambda *_args: None)
    application = app_module.DownloaderApp.__new__(app_module.DownloaderApp)
    application.events = queue.Queue()
    application.cancel_requested = application.skip_video_requested = (
        application.skip_url_requested
    ) = False
    application._active_progress_context = None
    application._last_progress_event_at = 0.0
    application._find_ffmpeg = lambda: ffmpeg
    application._find_ffprobe = lambda: ffprobe
    application._find_deno = lambda: None
    job = DownloadJob(
        url=info["webpage_url"],
        output_dir=tmp_path,
        output_type=OutputType.MP4,
        quality_label="360p",
        export_mode=export_mode_from_display_name(
            "Custom" if preset == "Custom quality" else preset
        ),
        manual_settings=ManualExportSettings(
            video_bitrate_kbps=2500,
            video_crf=19 if preset == "Custom quality" else None,
        ),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=True,
        use_nvenc=use_nvenc,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=True,
        tags=[],
    )
    outcome = application._download_worker_single(job)
    assert outcome.success_count == 1
    assert outcome.failure_count == 0
    if use_nvenc and preset != "Custom quality":
        events = list(application.events.queue)
        assert any("NVIDIA NVENC GPU" in str(event) for event in events)
    media = list(tmp_path.rglob("*.mp4"))
    assert len(media) == 1
    subprocess.run(
        [ffmpeg, "-v", "error", "-xerror", "-i", str(media[0]), "-f", "null", "-"],
        check=True,
        capture_output=True,
        timeout=30,
    )
    outcome = application._download_worker_single(job)
    assert outcome.success_count == 1
    assert len(downloads) == 1
    assert list(tmp_path.rglob("*.mp4")) == media


def test_quality_presets_have_measurable_size_and_detail_tradeoffs(source, tmp_path):
    import re

    from yt_downloader.app import build_vod_ffmpeg_command
    from yt_downloader.export_planning import build_auto_export_plan

    path, ffmpeg, _ffprobe = source
    info = {
        "formats": [
            {
                "format_id": "v",
                "vcodec": "avc1",
                "acodec": "none",
                "width": 640,
                "height": 360,
                "fps": 30,
                "vbr": 1500,
            },
            {"format_id": "a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 130},
        ]
    }
    metrics = {}
    for preset in ("Everyday", "Streaming", "Editing", "Sharing"):
        plan = build_auto_export_plan(info, mode=preset)
        output = tmp_path / f"{preset}.mp4"
        command = build_vod_ffmpeg_command(
            ffmpeg,
            path,
            output,
            video_crf=plan.video_crf,
            audio_bitrate_kbps=plan.audio_bitrate_kbps,
            keyframe_seconds=plan.keyframe_seconds,
            fps=plan.fps,
            constant_frame_rate=plan.constant_frame_rate,
            video_maxrate_kbps=plan.video_maxrate_kbps,
        )
        subprocess.run(command, check=True, capture_output=True, timeout=60)
        comparison = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-i",
                str(output),
                "-i",
                str(path),
                "-lavfi",
                "[0:v]settb=AVTB,setpts=N/(30*TB)[d];[1:v]settb=AVTB,setpts=N/(30*TB)[r];[d][r]ssim",
                "-an",
                "-f",
                "null",
                "-",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        match = re.search(r"All:([0-9.]+)", comparison.stderr)
        assert match, comparison.stderr
        metrics[preset] = (output.stat().st_size, float(match.group(1)))
    assert metrics["Sharing"][0] < metrics["Everyday"][0] < metrics["Editing"][0]
    assert metrics["Sharing"][1] < metrics["Everyday"][1] < metrics["Editing"][1]
    assert metrics["Streaming"][1] > metrics["Sharing"][1]
