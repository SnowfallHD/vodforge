from __future__ import annotations

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
