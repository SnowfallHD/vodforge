"""Task presets must carry their intent through planning, encoding and recovery."""

from dataclasses import replace
from pathlib import Path

import pytest

from yt_downloader.app import _planned_output_summary, build_vod_ffmpeg_command
from yt_downloader.export_planning import (
    EXPORT_MODES,
    QUALITY_PRESETS,
    apply_manual_export_settings,
    build_auto_export_plan,
    export_mode_from_display_name,
    migrate_export_preferences,
)
from yt_downloader.models import ExportMode, ManualExportSettings
from yt_downloader.output_validation import output_artifact_plan_mismatches


def source_info(bitrate=3000, height=1080, width=1920, fps=30):
    return {
        "formats": [
            {
                "format_id": "v",
                "vcodec": "avc1",
                "acodec": "none",
                "height": height,
                "width": width,
                "fps": fps,
                "vbr": bitrate,
                "ext": "mp4",
            },
            {
                "format_id": "a",
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "abr": 130,
                "ext": "m4a",
            },
        ]
    }


def matching_probe(plan, video_rate=1000):
    return {
        "format": {"format_name": "mov,mp4", "duration": "6"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "profile": "High",
                "pix_fmt": "yuv420p",
                "width": plan.output_width,
                "height": plan.output_height,
                "bit_rate": str(video_rate * 1000),
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
                "bit_rate": "2274",
            },
        ],
    }


@pytest.mark.parametrize("mode", list(QUALITY_PRESETS))
def test_quality_intent_reaches_encoder_without_cbr_or_gpu_substitution(mode):
    plan = build_auto_export_plan(source_info(), mode=mode)
    command = build_vod_ffmpeg_command(
        "ffmpeg",
        Path("in.mp4"),
        Path("out.mp4"),
        video_bitrate_kbps=plan.video_bitrate_kbps,
        video_crf=plan.video_crf,
        keyframe_seconds=plan.keyframe_seconds,
        fps=plan.fps,
        constant_frame_rate=plan.constant_frame_rate,
        use_nvenc=True,
        preserve_attached_picture=True,
        video_maxrate_kbps=plan.video_maxrate_kbps,
    )
    assert "libx264" in command
    assert "h264_nvenc" not in command
    assert "-b:v:0" not in command and "-minrate:v:0" not in command
    assert command[command.index("-crf:v:0") + 1] == str(plan.video_crf)
    assert "-c:v:1" in command  # Embedded artwork remains a copied stream.
    assert output_artifact_plan_mismatches(matching_probe(plan), plan) == []
    assert "CRF" in _planned_output_summary(plan)["Target video bitrate"]
    assert output_artifact_plan_mismatches(matching_probe(plan, video_rate=0), plan)
    wrong = matching_probe(plan)
    wrong["streams"][0]["width"] = 640
    assert any("width" in m for m in output_artifact_plan_mismatches(wrong, plan))


def test_ctv_floor_is_measured_and_preserves_widescreen_tier():
    info = source_info(bitrate=100, height=1012)
    info["formats"][0]["format_note"] = "1080p"
    plan = build_auto_export_plan(info, mode=ExportMode.AUTO_CBR)
    assert plan.output_height == 1012
    assert plan.video_bitrate_kbps == 2500
    assert plan.video_crf is None
    assert plan.keyframe_seconds == 2
    assert any(
        "at least 2000" in m
        for m in output_artifact_plan_mismatches(matching_probe(plan, 1999), plan)
    )
    assert output_artifact_plan_mismatches(matching_probe(plan, 2500), plan) == []


def test_quality_targets_do_not_use_source_bitrate_as_a_quality_cap():
    for mode in QUALITY_PRESETS:
        low = build_auto_export_plan(source_info(500), mode)
        high = build_auto_export_plan(source_info(15000), mode)
        assert low.video_crf == high.video_crf
    low = build_auto_export_plan(source_info(500), ExportMode.AUTO_CBR)
    high = build_auto_export_plan(source_info(15000), ExportMode.AUTO_CBR)
    assert low.video_bitrate_kbps < high.video_bitrate_kbps <= 10000


def test_custom_quality_and_cbr_have_separate_validation_contracts():
    base = build_auto_export_plan(source_info())
    cbr = apply_manual_export_settings(
        base, ManualExportSettings(video_bitrate_kbps=6000)
    )
    quality = apply_manual_export_settings(base, ManualExportSettings(video_crf=19))
    assert output_artifact_plan_mismatches(matching_probe(cbr, 100), cbr)
    assert output_artifact_plan_mismatches(matching_probe(quality, 100), quality) == []
    assert "CRF 19" in quality.summary


def test_legacy_preferences_preserve_delivery_and_custom_choices():
    assert EXPORT_MODES == [
        "Everyday",
        "Streaming",
        "Editing",
        "Sharing",
        "CTV",
        "Custom",
    ]
    old = {"export_mode": "Auto CBR", "manual_video_bitrate": 8300}
    assert migrate_export_preferences(old) == old
    assert export_mode_from_display_name("CTV") is ExportMode.AUTO_CBR
    assert (
        export_mode_from_display_name("Auto CBR (Recommended)") is ExportMode.AUTO_CBR
    )
    fixed = migrate_export_preferences(
        {"export_mode": "Strict Compliance", "manual_video_bitrate": 8300}
    )
    assert fixed["export_mode"] == "Manual Override"
    assert fixed["manual_video_bitrate"] == 10000
    assert fixed["manual_audio_bitrate"] == 320
    assert fixed["manual_rate_control"] == "CBR"


def test_hdr_only_is_rejected_with_an_explanation_instead_of_wrong_colors():
    info = source_info()
    info["formats"][0]["dynamic_range"] = "HDR10"
    with pytest.raises(RuntimeError, match="SDR version"):
        build_auto_export_plan(info, mode=ExportMode.EVERYDAY)


@pytest.mark.parametrize("use_nvenc", [False, True])
@pytest.mark.parametrize("label", EXPORT_MODES)
@pytest.mark.parametrize("tier", [360, 480, 720, 1080, 1440, 2160])
def test_each_task_respects_source_ceiling_and_dimensions(label, tier, use_nvenc):
    info = source_info(height=tier, width=round(tier * 16 / 9))
    info["formats"].insert(
        0, {**info["formats"][0], "format_id": "larger", "height": 4320, "width": 7680}
    )
    plan = build_auto_export_plan(
        info, mode=label, max_height=tier, use_nvenc=use_nvenc
    )
    assert plan.video_format_id == "v"
    assert plan.output_height == tier
    assert plan.output_width == round(tier * 16 / 9)


def test_custom_disallows_lossless_crf_with_fixed_high_profile():
    with pytest.raises(ValueError, match="High profile"):
        build_vod_ffmpeg_command(
            "ffmpeg", Path("source.mp4"), Path("output.mp4"), video_crf=0
        )


def test_custom_quality_survives_restart_and_changes_duplicate_identity(tmp_path):
    from yt_downloader.models import DownloadJob, Mp3ExportSettings, OutputType
    from yt_downloader.run_identity import job_attempt_signature
    from yt_downloader.run_state import deserialize_download_job, serialize_download_job

    first = DownloadJob(
        url="https://www.youtube.com/watch?v=abc123",
        output_dir=tmp_path,
        output_type=OutputType.MP4,
        quality_label="1080p Full HD",
        export_mode=ExportMode.MANUAL_OVERRIDE,
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
    first.export_mode = ExportMode.MANUAL_OVERRIDE
    first.manual_settings = replace(first.manual_settings, video_crf=19)
    restored = deserialize_download_job(serialize_download_job(first))
    assert restored.manual_settings.video_crf == 19
    assert job_attempt_signature(restored) == job_attempt_signature(first)
    second = replace(
        restored, manual_settings=replace(restored.manual_settings, video_crf=25)
    )
    assert job_attempt_signature(second) != job_attempt_signature(first)


@pytest.mark.parametrize("mode", list(QUALITY_PRESETS))
def test_nvenc_preset_preserves_task_contract_and_uses_distinct_quality(mode):
    cpu = build_auto_export_plan(source_info(), mode=mode)
    gpu = build_auto_export_plan(source_info(), mode=mode, use_nvenc=True)
    assert gpu.nvenc_cq is not None
    assert gpu.format_selector == cpu.format_selector
    assert gpu.keyframe_seconds == cpu.keyframe_seconds
    assert gpu.audio_bitrate_kbps == cpu.audio_bitrate_kbps
    command = build_vod_ffmpeg_command(
        "ffmpeg",
        Path("in.mp4"),
        Path("out.mp4"),
        video_crf=gpu.video_crf,
        nvenc_cq=gpu.nvenc_cq,
        use_nvenc=True,
        video_maxrate_kbps=gpu.video_maxrate_kbps,
        preserve_attached_picture=True,
    )
    assert "h264_nvenc" in command and "libx264" not in command
    assert "-crf:v:0" not in command and "-minrate:v:0" not in command
    assert command[command.index("-cq:v:0") + 1] == str(gpu.nvenc_cq)
    assert "-c:v:1" in command
    assert "NVENC CQ" in gpu.video_target_label and "NVENC CQ" in gpu.summary
    assert output_artifact_plan_mismatches(matching_probe(gpu), gpu) == []


@pytest.mark.parametrize("mode", list(QUALITY_PRESETS))
def test_selected_gpu_reaches_worker_plan_and_changes_reuse_identity(tmp_path, mode):
    from yt_downloader.app import _build_download_item_plan
    from yt_downloader.models import DownloadJob, Mp3ExportSettings, OutputType
    from yt_downloader.run_identity import job_attempt_signature

    job = DownloadJob(
        url="https://www.youtube.com/watch?v=abc123",
        output_dir=tmp_path,
        output_type=OutputType.MP4,
        quality_label="1080p Full HD",
        export_mode=mode,
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
    gpu_job = replace(job, use_nvenc=True)
    plan = _build_download_item_plan(gpu_job, source_info(), max_height=1080)
    assert plan.nvenc_cq is not None
    assert job_attempt_signature(job) != job_attempt_signature(gpu_job)
    # Repeating the same intent must still reuse rather than re-encode.
    assert job_attempt_signature(gpu_job) == job_attempt_signature(replace(gpu_job))
