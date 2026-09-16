from pathlib import Path

import pytest

from yt_downloader.history import HISTORY_MEDIA_MISSING, history_media_file_state
from yt_downloader.media_player import resolve_library_media_path
from yt_downloader.models import OutputType
from yt_downloader.original_audio import (
    build_original_audio_plan,
    original_audio_options,
)


def audio_format(codec, identifier, bitrate=160):
    return {
        "format_id": identifier,
        "acodec": codec,
        "vcodec": "none",
        "abr": bitrate,
        "asr": 48000,
        "audio_channels": 2,
        "protocol": "https",
    }


@pytest.mark.parametrize("codec,extension", [("opus", ".opus"), ("mp4a.40.2", ".m4a")])
def test_original_preserves_source_plan(codec, extension):
    plan = build_original_audio_plan({"formats": [audio_format(codec, "251")]})
    assert plan.output_type is OutputType.ORIGINAL
    assert plan.output_extension == extension
    assert plan.output_sample_rate is None and plan.output_channels is None
    assert not plan.embed_metadata and not plan.embed_cover_art and not plan.warnings
    options = original_audio_options(plan.format_selector)
    assert options["format"] == "251"
    assert options["postprocessors"] == [
        {"key": "FFmpegExtractAudio", "preferredcodec": "best"}
    ]
    assert options["postprocessor_args"] == {}


def test_original_does_not_force_opus_when_aac_is_better():
    plan = build_original_audio_plan(
        {
            "formats": [
                audio_format("opus", "251", 64),
                audio_format("mp4a.40.2", "140", 256),
            ]
        }
    )
    assert plan.audio_format_id == "140"


@pytest.mark.parametrize("formats", [None, [], [audio_format("mp3", "1")]])
def test_original_fails_closed_without_supported_source(formats):
    with pytest.raises(RuntimeError):
        build_original_audio_plan({"formats": formats})


def test_original_requires_analyzed_selector():
    with pytest.raises(RuntimeError):
        original_audio_options(None)
    assert OutputType("ORIGINAL AUDIO") is OutputType.ORIGINAL


def test_original_missing_exact_path_never_borrows_mp4(tmp_path: Path):
    (tmp_path / "unrelated.mp4").write_bytes(b"unrelated")
    record = {
        "vodforge_output_type": "Original audio",
        "vodforge_output_dir": str(tmp_path),
    }
    assert resolve_library_media_path(record) is None
    assert history_media_file_state(record) == HISTORY_MEDIA_MISSING


def original_probe(codec):
    return {
        "format": {
            "format_name": "ogg" if codec == "opus" else "mov,mp4,m4a,3gp,3g2,mj2",
            "duration": "6",
            "tags": {"title": "source metadata is preserved"},
        },
        "streams": [
            {
                "codec_type": "audio",
                "codec_name": codec,
                "sample_rate": "48000",
                "channels": 2,
                "bit_rate": "126225",
            }
        ],
    }


@pytest.mark.parametrize(
    "codec,source_codec,extension",
    [
        ("aac", "mp4a.40.2", ".m4a"),
        ("opus", "opus", ".opus"),
    ],
)
def test_original_validated_artifact_reuses_with_its_preservation_plan(
    tmp_path, monkeypatch, codec, source_codec, extension
):
    from yt_downloader import app

    path = tmp_path / ("original" + extension)
    path.write_bytes(b"controlled valid probe fixture")
    plan = build_original_audio_plan(
        {"formats": [audio_format(source_codec, "audio", 200)]}
    )
    probe = original_probe(codec)
    monkeypatch.setattr(app, "run_ffprobe_json", lambda *_args, **_kwargs: probe)
    requirements = app.ExistingOutputRequirements(
        output_type=OutputType.ORIGINAL,
        plan=plan,
        expected_duration_seconds=6,
        embed_metadata=False,
        embed_cover_art=False,
    )
    assert (
        app._validate_existing_output_candidate(
            path, "trusted-probe", requirements, control_check=None
        )
        == probe
    )


@pytest.mark.parametrize("codec,source_codec", [("aac", "mp4a.40.2"), ("opus", "opus")])
def test_original_plan_match_uses_source_preservation_not_mp3_cbr(codec, source_codec):
    from yt_downloader.output_validation import output_artifact_plan_mismatches

    plan = build_original_audio_plan(
        {"formats": [audio_format(source_codec, "audio", 200)]}
    )
    assert (
        output_artifact_plan_mismatches(
            original_probe(codec),
            plan,
            sidecar_summary={
                "Output rate-control mode": "Stream copy",
                "Target audio bitrate": "Preserve source",
            },
            require_sidecar=True,
        )
        == []
    )


@pytest.mark.parametrize("codec,source_codec", [("aac", "mp4a.40.2"), ("opus", "opus")])
@pytest.mark.parametrize(
    "changed",
    ["codec", "container", "channels", "sample_rate", "video", "duration", "corrupt"],
)
def test_original_fresh_and_reuse_reject_the_same_incompatible_artifact(
    tmp_path, monkeypatch, codec, source_codec, changed
):
    import copy

    from yt_downloader import app

    probe = copy.deepcopy(original_probe(codec))
    plan = build_original_audio_plan(
        {"formats": [audio_format(source_codec, "audio", 200)]}
    )
    path = tmp_path / ("original" + plan.output_extension)
    path.write_bytes(b"controlled artifact")
    if changed == "codec":
        probe["streams"][0]["codec_name"] = "mp3"
    elif changed == "container":
        probe["format"]["format_name"] = "mp3"
    elif changed == "channels":
        probe["streams"][0]["channels"] = 1
    elif changed == "sample_rate":
        probe["streams"][0]["sample_rate"] = "44100"
    elif changed == "video":
        probe["streams"].append({"codec_type": "video", "codec_name": "h264"})
    elif changed == "duration":
        probe["format"]["duration"] = "0.2"

    def read_probe(*_args, **_kwargs):
        if changed == "corrupt":
            raise RuntimeError("PRIVATE invalid container")
        return probe

    monkeypatch.setattr(app, "run_ffprobe_json", read_probe)
    with pytest.raises(RuntimeError):
        app.validate_output_artifact(
            path,
            OutputType.ORIGINAL,
            "trusted-probe",
            plan=plan,
            expected_duration_seconds=6,
        )
    requirements = app.ExistingOutputRequirements(
        output_type=OutputType.ORIGINAL, plan=plan, expected_duration_seconds=6
    )
    assert (
        app._validate_existing_output_candidate(
            path, "trusted-probe", requirements, control_check=None
        )
        is None
    )


def test_reuse_validation_rejection_is_bounded_and_observer_cannot_change_result(
    tmp_path, monkeypatch
):
    from yt_downloader import app

    path = tmp_path / "source.m4a"
    path.write_bytes(b"corrupt generated artifact")
    plan = build_original_audio_plan({"formats": [audio_format("aac", "audio")]})

    def corrupt(*_args, **_kwargs):
        raise RuntimeError("PRIVATE filename and diagnostic contents")

    monkeypatch.setattr(app, "run_ffprobe_json", corrupt)
    observed = []
    requirements = app.ExistingOutputRequirements(
        output_type=OutputType.ORIGINAL, plan=plan
    )
    assert (
        app._validate_existing_output_candidate(
            path,
            "trusted-probe",
            requirements,
            control_check=None,
            on_rejection=lambda reason, detail: observed.append((reason, detail)),
        )
        is None
    )
    assert observed[0][0] == "validation_failed"
    assert observed[0][1].stage == "reuse"
    assert "PRIVATE" not in str(observed[0][1].payload())

    def broken_observer(*_args):
        raise ValueError("PRIVATE observer")

    assert (
        app._validate_existing_output_candidate(
            path,
            "trusted-probe",
            requirements,
            control_check=None,
            on_rejection=broken_observer,
        )
        is None
    )
