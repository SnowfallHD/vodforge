"""Real encoder coverage: AAC target bitrate is not a content-independent floor."""

import json
import subprocess
from dataclasses import replace

import pytest
from quality_harness.fixtures import find_ffmpeg, find_ffprobe

from yt_downloader.app import build_vod_ffmpeg_command, validate_output_artifact
from yt_downloader.models import ExportMode, ExportPlan, OutputType


@pytest.mark.parametrize(
    "audio",
    [
        "anullsrc=r=48000:cl=stereo",
        "sine=frequency=523.25:sample_rate=48000,volume=0.0001",
        "sine=frequency=523.25:sample_rate=48000",
    ],
)
def test_real_aac_content_passes_export_contract(tmp_path, audio):
    ffmpeg = find_ffmpeg()
    ffprobe = find_ffprobe(ffmpeg)
    source = tmp_path / "source.mkv"
    output = tmp_path / "output.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=30",
            "-f",
            "lavfi",
            "-i",
            audio,
            "-t",
            "3",
            "-c:v",
            "libx264",
            "-c:a",
            "pcm_s16le",
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    plan = ExportPlan(
        mode=ExportMode.AUTO_CBR,
        video_format_id="test",
        audio_format_id="test",
        format_selector="test",
        output_width=320,
        output_height=180,
        source_video_kbps=1000,
        effective_video_kbps=1000,
        video_bitrate_kbps=1000,
        source_audio_kbps=160,
        effective_audio_kbps=160,
        audio_bitrate_kbps=160,
        audio_sample_rate="48000",
        audio_channels="2",
    )
    command = build_vod_ffmpeg_command(
        ffmpeg, source, output, video_bitrate_kbps=1000, audio_bitrate_kbps=160
    )
    subprocess.run(command, check=True, capture_output=True, timeout=60)
    probe = json.loads(
        subprocess.check_output(
            [
                ffprobe,
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(output),
            ],
            timeout=30,
        )
    )
    validate_output_artifact(
        output,
        OutputType.MP4,
        ffprobe,
        plan=plan,
        expected_duration_seconds=3,
        ffprobe_data=probe,
    )
    subprocess.run(
        [ffmpeg, "-v", "error", "-xerror", "-i", str(output), "-f", "null", "-"],
        check=True,
        capture_output=True,
        timeout=30,
    )
    with pytest.raises(RuntimeError, match="sample rate"):
        validate_output_artifact(
            output,
            OutputType.MP4,
            ffprobe,
            plan=replace(plan, audio_sample_rate="22050"),
            ffprobe_data=probe,
        )
