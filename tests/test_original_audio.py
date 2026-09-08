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
