from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from yt_downloader.models import (
    AudioExportPlan,
    ExportMode,
    ExportPlan,
    OutputType,
)
from yt_downloader.output_validation import (
    output_artifact_plan_mismatches,
    validate_output_artifact,
)


def _audio_plan(
    *,
    embed_metadata: bool = True,
    embed_cover_art: bool = True,
) -> AudioExportPlan:
    return AudioExportPlan(
        output_type=OutputType.MP3,
        audio_format_id="251",
        format_selector="251",
        source_audio_kbps=128,
        effective_audio_kbps=128,
        audio_bitrate_kbps=320,
        source_sample_rate="48000",
        output_sample_rate="48000",
        source_channels="2",
        output_channels="2",
        audio_codec="opus",
        embed_metadata=embed_metadata,
        embed_cover_art=embed_cover_art,
        cover_art_source="YouTube thumbnail" if embed_cover_art else "No Art",
    )


def _mp3_probe(
    *,
    tags: dict[str, str] | None = None,
    attached_art: bool = True,
) -> dict[str, Any]:
    streams: list[dict[str, Any]] = [
        {
            "codec_type": "audio",
            "codec_name": "mp3",
            "bit_rate": "320000",
            "sample_rate": "48000",
            "channels": 2,
        }
    ]
    if attached_art:
        streams.append(
            {
                "codec_type": "video",
                "codec_name": "mjpeg",
                "disposition": {"attached_pic": 1},
            }
        )
    return {
        "format": {
            "format_name": "mp3",
            "duration": "60.0",
            "tags": tags if tags is not None else {"TITLE": "Example"},
        },
        "streams": streams,
    }


def _mp4_plan() -> ExportPlan:
    return ExportPlan(
        mode=ExportMode.AUTO_CBR,
        video_format_id="18",
        audio_format_id="18",
        format_selector="18",
        output_width=640,
        output_height=360,
        source_video_kbps=1200,
        effective_video_kbps=1200,
        video_bitrate_kbps=1500,
        source_audio_kbps=192,
        effective_audio_kbps=192,
        audio_bitrate_kbps=320,
        audio_sample_rate="48000",
        audio_channels="2",
    )


def _mp4_probe(*, tags: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "format": {
            "format_name": "mov,mp4",
            "duration": "60.0",
            "tags": tags if tags is not None else {},
        },
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 640,
                "height": 360,
                "profile": "High",
                "pix_fmt": "yuv420p",
                "bit_rate": "1500000",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
                "bit_rate": "160000",
            },
        ],
    }


def test_audio_plan_derives_metadata_and_attached_artwork_expectations() -> None:
    plan = _audio_plan()
    matching = _mp3_probe(tags={"TITLE": "Example", "KEYWORDS": "Alpha, Beta"})

    assert not output_artifact_plan_mismatches(
        matching,
        plan,
        expected_tags=["alpha", "BETA"],
    )

    no_metadata = _mp3_probe(tags={"encoder": "Lavf"})
    assert "the requested embedded metadata is missing" in (
        output_artifact_plan_mismatches(no_metadata, plan)
    )

    no_artwork = _mp3_probe(attached_art=False)
    assert "the requested embedded artwork is missing" in (
        output_artifact_plan_mismatches(no_artwork, plan)
    )

    missing_tag = output_artifact_plan_mismatches(
        matching,
        plan,
        expected_tags=["alpha", "gamma"],
    )
    assert missing_tag == ["the embedded keywords are missing requested tags: gamma"]

    substring_only = _mp3_probe(
        tags={"TITLE": "Example", "KEYWORDS": "not-alpha, Beta-suffix"}
    )
    assert output_artifact_plan_mismatches(
        substring_only,
        plan,
        expected_tags=["alpha", "beta"],
    ) == ["the embedded keywords are missing requested tags: alpha, beta"]

    empty_metadata = _mp3_probe(tags={"TITLE": "", "COMMENT": "   "})
    assert "the requested embedded metadata is missing" in (
        output_artifact_plan_mismatches(empty_metadata, plan)
    )


def test_audio_plan_embed_contract_cannot_be_weakened_by_caller_overrides() -> None:
    mismatches = output_artifact_plan_mismatches(
        _mp3_probe(tags={"encoder": "Lavf"}, attached_art=False),
        _audio_plan(),
        embed_metadata=False,
        embed_cover_art=False,
    )

    assert "the requested embedded metadata is missing" in mismatches
    assert "the requested embedded artwork is missing" in mismatches


def test_disabled_audio_embedding_rejects_unexpected_metadata_and_artwork() -> None:
    mismatches = output_artifact_plan_mismatches(
        _mp3_probe(),
        _audio_plan(embed_metadata=False, embed_cover_art=False),
    )

    assert "the output contains unexpected embedded metadata" in mismatches
    assert "the output contains unexpected embedded artwork" in mismatches


def test_fresh_mp3_validation_enforces_derived_full_audio_contract(
    tmp_path: Path,
) -> None:
    output = tmp_path / "audio.mp3"
    output.write_bytes(b"candidate")

    with pytest.raises(RuntimeError, match="requested embedded artwork is missing"):
        validate_output_artifact(
            output,
            OutputType.MP3,
            "ffprobe",
            probe_reader=lambda *_args, **_kwargs: {},
            plan=_audio_plan(),
            ffprobe_data=_mp3_probe(attached_art=False),
        )


def test_fresh_mp4_validation_accepts_optional_job_embedding_expectations(
    tmp_path: Path,
) -> None:
    output = tmp_path / "video.mp4"
    output.write_bytes(b"candidate")
    probe = _mp4_probe(tags={"title": "Example", "keywords": "alpha,beta"})

    assert (
        validate_output_artifact(
            output,
            OutputType.MP4,
            "ffprobe",
            probe_reader=lambda *_args, **_kwargs: {},
            plan=_mp4_plan(),
            embed_metadata=True,
            embed_cover_art=False,
            expected_tags=["Alpha", "beta"],
            ffprobe_data=probe,
        )
        is probe
    )

    with pytest.raises(RuntimeError, match="missing requested tags: gamma"):
        validate_output_artifact(
            output,
            OutputType.MP4,
            "ffprobe",
            probe_reader=lambda *_args, **_kwargs: {},
            plan=_mp4_plan(),
            embed_metadata=True,
            embed_cover_art=False,
            expected_tags=["gamma"],
            ffprobe_data=probe,
        )

    with pytest.raises(RuntimeError, match="requested embedded artwork is missing"):
        validate_output_artifact(
            output,
            OutputType.MP4,
            "ffprobe",
            probe_reader=lambda *_args, **_kwargs: {},
            plan=_mp4_plan(),
            embed_metadata=True,
            embed_cover_art=True,
            expected_tags=["alpha"],
            ffprobe_data=probe,
        )


def test_tags_are_not_required_when_metadata_embedding_is_disabled() -> None:
    assert not output_artifact_plan_mismatches(
        _mp4_probe(),
        _mp4_plan(),
        embed_metadata=False,
        embed_cover_art=False,
        expected_tags=["not-requested-without-metadata"],
    )


def test_sidecar_contract_remains_opt_in_for_fresh_validation(tmp_path: Path) -> None:
    output = tmp_path / "video.mp4"
    output.write_bytes(b"candidate")
    plan = _mp4_plan()
    probe = _mp4_probe()

    assert not output_artifact_plan_mismatches(probe, plan)
    assert "the VODForge output contract is missing" in output_artifact_plan_mismatches(
        probe,
        plan,
        require_sidecar=True,
    )
    assert (
        validate_output_artifact(
            output,
            OutputType.MP4,
            "ffprobe",
            probe_reader=lambda *_args, **_kwargs: {},
            plan=plan,
            ffprobe_data=probe,
        )
        is probe
    )
