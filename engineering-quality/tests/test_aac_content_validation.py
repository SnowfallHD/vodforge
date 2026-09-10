"""Real encoder coverage: AAC target bitrate is not a content-independent floor."""

import json
import math
import subprocess
from array import array
from dataclasses import replace

import pytest
from quality_harness.fixtures import find_ffmpeg, find_ffprobe

from yt_downloader.app import build_vod_ffmpeg_command, validate_output_artifact
from yt_downloader.export_planning import QUALITY_PRESETS
from yt_downloader.models import ExportMode, ExportPlan, OutputType


@pytest.mark.parametrize(
    "audio",
    [
        "anullsrc=r=48000:cl=stereo",
        "sine=frequency=523.25:sample_rate=48000,volume=0.0001",
        "sine=frequency=523.25:sample_rate=48000",
    ],
)
@pytest.mark.parametrize(
    "mode", [*QUALITY_PRESETS, ExportMode.AUTO_CBR, ExportMode.MANUAL_OVERRIDE]
)
def test_real_aac_content_passes_export_contract(tmp_path, audio, mode):
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
            "pcm_f32le",
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    plan = ExportPlan(
        mode=mode,
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
        video_crf=QUALITY_PRESETS[mode][0] if mode in QUALITY_PRESETS else None,
        keyframe_seconds=QUALITY_PRESETS[mode][1] if mode in QUALITY_PRESETS else 2,
        constant_frame_rate=True,
        fps=30,
    )
    command = build_vod_ffmpeg_command(
        ffmpeg,
        source,
        output,
        video_bitrate_kbps=1000,
        audio_bitrate_kbps=160,
        video_crf=plan.video_crf,
        keyframe_seconds=plan.keyframe_seconds,
        constant_frame_rate=plan.constant_frame_rate,
        fps=plan.fps,
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

    def rms(path):
        decoded = subprocess.check_output(
            [
                ffmpeg,
                "-v",
                "error",
                "-i",
                str(path),
                "-vn",
                "-c:a",
                "pcm_f32le",
                "-f",
                "f32le",
                "-",
            ],
            timeout=30,
        )
        samples = array("f")
        samples.frombytes(decoded)
        return math.sqrt(sum(sample * sample for sample in samples) / len(samples))

    source_rms, output_rms = rms(source), rms(output)
    if source_rms > 0:
        # This would fail if an audible/quiet source were accidentally silenced.
        assert 0.5 <= output_rms / source_rms <= 2
    else:
        assert output_rms < 1e-6
    with pytest.raises(RuntimeError, match="sample rate"):
        validate_output_artifact(
            output,
            OutputType.MP4,
            ffprobe,
            plan=replace(plan, audio_sample_rate="22050"),
            ffprobe_data=probe,
        )
