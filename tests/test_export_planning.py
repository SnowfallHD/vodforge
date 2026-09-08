from __future__ import annotations

import math

import pytest

from yt_downloader import app, export_planning
from yt_downloader.models import ExportMode


def test_widescreen_1080_tier_preserves_actual_dimensions_without_warning() -> None:
    # Public format listing for 8mv2Gonsdog: 137/248/399 are labelled 1080p,
    # all at 1920x1012; HLS 270 has those same dimensions.
    info = {
        "formats": [
            {
                "format_id": "270",
                "width": 1920,
                "height": 1012,
                "format_note": "1080p",
                "fps": 25,
                "vcodec": "avc1.640028",
                "acodec": "none",
                "tbr": 2138,
                "ext": "mp4",
            },
            {
                "format_id": "251",
                "vcodec": "none",
                "acodec": "opus",
                "abr": 146,
                "ext": "webm",
            },
        ]
    }
    plan = export_planning.build_auto_export_plan(
        info, mode=ExportMode.AUTO_CBR, max_height=1080
    )
    assert (plan.output_width, plan.output_height) == (1920, 1012)
    assert not plan.warnings


@pytest.mark.parametrize("label", list(export_planning.QUALITY_OPTIONS))
@pytest.mark.parametrize("progressive", [False, True])
def test_every_quality_option_selects_highest_provider_tier(label, progressive):
    ceiling = app._quality_max_height(label)
    formats = [
        {
            "format_id": str(tier),
            "format_note": f"{tier}p",
            "height": round(tier * 1012 / 1080),
            "width": round(tier * 1920 / 1080),
            "vcodec": "avc1",
            "acodec": "aac" if progressive else "none",
            "vbr": 5000,
            "abr": 128,
            "fps": 30,
            "ext": "mp4",
        }
        for tier in [360, 480, 720, 1080, 1440, 2160]
    ]
    choose = (
        export_planning.choose_best_progressive_format
        if progressive
        else export_planning.choose_best_video_format
    )
    selected = choose(formats, max_height=ceiling)
    assert selected is not None
    assert selected["format_id"] == str(ceiling)
    assert selected["height"] == round(ceiling * 1012 / 1080)
    # A missing exact tier falls back below the ceiling, never above it.
    if ceiling > 360:
        selected = choose(
            [fmt for fmt in formats if fmt["format_id"] != str(ceiling)],
            max_height=ceiling,
        )
        assert selected is not None
        assert export_planning.video_quality_tier(selected) == max(
            tier for tier in [360, 480, 720, 1080, 1440, 2160] if tier < ceiling
        )


def test_unlabelled_wide_video_does_not_invent_quality_tier():
    assert export_planning.video_quality_tier({"width": 3840, "height": 720}) == 720


def test_auto_fallback_never_exceeds_ceiling_and_prefers_top_tier():
    formats = [
        {
            "format_id": "low",
            "height": 1080,
            "vcodec": "avc1",
            "acodec": "none",
            "tbr": 4000,
        },
        {"format_id": "high", "height": 2160, "vcodec": "vp9", "acodec": "none"},
    ]
    selected, _ = export_planning._choose_auto_video_source(formats, 2160)
    assert selected["format_id"] == "high"
    selected, _ = export_planning._choose_auto_video_source(formats, 1080)
    assert selected["format_id"] == "low"
    selected, _ = export_planning._choose_auto_video_source(formats, 720)
    assert selected is None


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
