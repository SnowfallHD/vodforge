from __future__ import annotations

import math

import pytest

from yt_downloader import app, export_planning
from yt_downloader.models import ExportMode


def test_app_preserves_export_planning_compatibility_exports() -> None:
    assert app.QUALITY_OPTIONS is export_planning.QUALITY_OPTIONS
    assert app.EXPORT_MODES is export_planning.EXPORT_MODES
    assert app.build_auto_export_plan is export_planning.build_auto_export_plan
    assert app.build_mp3_export_plan is export_planning.build_mp3_export_plan
    assert (
        app.apply_manual_export_settings is export_planning.apply_manual_export_settings
    )
    assert app.choose_best_video_format is export_planning.choose_best_video_format
    assert app.choose_best_audio_format is export_planning.choose_best_audio_format
    assert app.choose_audio_bitrate_kbps is export_planning.choose_audio_bitrate_kbps


@pytest.mark.parametrize(
    ("sample_rate", "expected"),
    [
        (None, "Preserve source"),
        ("", "Preserve source"),
        ("44100", "44.1 kHz"),
        (48000, "48 kHz"),
        ("automatic", "automatic"),
    ],
)
def test_mp3_sample_rate_display_handles_preserved_numeric_and_unknown_values(
    sample_rate: str | int | None,
    expected: str,
) -> None:
    assert (
        export_planning.mp3_sample_rate_display(
            sample_rate,
            source_label="Preserve source",
        )
        == expected
    )


@pytest.mark.parametrize(
    "nonfinite",
    [float("nan"), float("inf"), float("-inf")],
    ids=["nan", "positive-infinity", "negative-infinity"],
)
def test_export_plans_treat_nonfinite_extractor_numbers_as_unknown(
    nonfinite: float,
) -> None:
    info = {
        "formats": [
            {
                "format_id": "video-nonfinite-bitrate",
                "height": 1080,
                "width": 1920,
                "fps": 30,
                "vcodec": "avc1.640028",
                "acodec": "none",
                "tbr": nonfinite,
                "ext": "mp4",
                "protocol": "https",
            },
            {
                "format_id": "video-valid",
                "height": 1080,
                "width": 1920,
                "fps": nonfinite,
                "vcodec": "avc1.640028",
                "acodec": "none",
                "tbr": 1500,
                "ext": "mp4",
                "protocol": "https",
            },
            {
                "format_id": "audio-valid",
                "vcodec": "none",
                "acodec": "opus",
                "abr": 128,
                "asr": nonfinite,
                "audio_channels": nonfinite,
                "ext": "webm",
                "protocol": "https",
            },
        ]
    }

    video_plan = export_planning.build_auto_export_plan(
        info,
        mode=ExportMode.AUTO_CBR,
        max_height=1080,
    )
    audio_plan = export_planning.build_mp3_export_plan(info)
    summary = app.build_encoding_summary_metadata(info, video_plan)

    assert video_plan.video_format_id == "video-valid"
    assert video_plan.fps == 30.0
    assert math.isfinite(video_plan.source_video_kbps)
    assert math.isfinite(video_plan.source_audio_kbps)
    assert audio_plan.source_sample_rate is None
    assert audio_plan.source_channels is None
    assert (
        summary["vodforge_encoding_summary"]["source"]["Source frame rate"] == "Unknown"
    )


def test_source_limited_plan_keeps_truthful_lower_resolution() -> None:
    info = {
        "formats": [
            {
                "format_id": "video-720",
                "height": 720,
                "width": 1280,
                "fps": 30,
                "vcodec": "avc1.64001f",
                "acodec": "none",
                "vbr": 1200,
                "ext": "mp4",
                "protocol": "https",
            },
            {
                "format_id": "audio-opus",
                "vcodec": "none",
                "acodec": "opus",
                "abr": 128,
                "asr": 48000,
                "audio_channels": 2,
                "ext": "webm",
                "protocol": "https",
            },
        ]
    }

    plan = export_planning.build_auto_export_plan(
        info,
        mode=ExportMode.AUTO_CBR,
        max_height=1080,
    )

    assert plan.format_selector == "video-720+audio-opus"
    assert (plan.output_width, plan.output_height) == (1280, 720)
    assert plan.video_bitrate_kbps == 1500
    assert any("not available in 1080p" in warning for warning in plan.warnings)
