"""Provider track preference precedes encoding quality, without language guesses."""

import pytest

from yt_downloader.export_planning import (
    _select_auto_sources,
    build_mp3_export_plan,
    choose_best_audio_format,
)
from yt_downloader.original_audio import build_original_audio_plan


def audio(key, bitrate, preference=None, language="en"):
    return {
        "format_id": key,
        "abr": bitrate,
        "language_preference": preference,
        "language": language,
        "vcodec": "none",
        "acodec": "opus",
        "ext": "webm",
        "protocol": "https",
        "audio_channels": 2,
        "asr": 48000,
    }


@pytest.mark.parametrize("quality", [False, True])
@pytest.mark.parametrize("language", ["en", "ja"])
def test_original_track_wins_higher_bitrate_dub(quality, language):
    original = audio("original", 128, 10, language)
    dubbed = audio("dubbed", 160, -1, "en" if language == "ja" else "yue")
    assert (
        choose_best_audio_format([dubbed, original], prefer_quality=quality) is original
    )


def test_encoding_quality_still_orders_within_original_tier():
    formats = [
        audio("low-original", 128, 10),
        audio("high-original", 160, 10),
        audio("dubbed", 256, -1),
    ]
    assert choose_best_audio_format(formats)["format_id"] == "high-original"


@pytest.mark.parametrize("invalid", [None, "10", True, float("nan"), float("inf")])
def test_absent_or_invalid_metadata_retains_quality_order(invalid):
    assert (
        choose_best_audio_format(
            [audio("low", 128, invalid), audio("high", 160, invalid)]
        )["format_id"]
        == "high"
    )


def test_unknown_bitrate_original_is_not_displaced_by_known_bitrate_dub():
    assert (
        choose_best_audio_format([audio("original", None, 10), audio("dub", 160, -1)])[
            "format_id"
        ]
        == "original"
    )


def test_restricted_explicit_candidates_and_unusable_original():
    dub = audio("chosen-dub", 160, -1, "yue")
    unusable = {**audio("original", 128, 10), "acodec": "none"}
    assert choose_best_audio_format([dub]) is dub
    assert choose_best_audio_format([unusable, dub]) is dub


def test_mp3_original_audio_and_mp4_use_preferred_track():
    formats = [
        audio("original", 128, 10),
        audio("dub", 160, -1),
        {
            "format_id": "video",
            "height": 1080,
            "vcodec": "avc1",
            "acodec": "none",
            "vbr": 2000,
            "fps": 30,
            "ext": "mp4",
            "protocol": "https",
        },
    ]
    assert build_mp3_export_plan({"formats": formats}).audio_format_id == "original"
    assert build_original_audio_plan({"formats": formats}).audio_format_id == "original"
    assert _select_auto_sources(formats, 1080).selector == "video+original"


def test_progressive_fallback_prefers_original_at_same_video_tier():
    original = {
        **audio("original-av", 128, 10),
        "vcodec": "avc1",
        "height": 720,
        "vbr": 1200,
        "fps": 30,
        "ext": "mp4",
    }
    dubbed = {
        **original,
        "format_id": "dub-av",
        "language_preference": -1,
        "vbr": 1800,
        "abr": 160,
    }
    assert _select_auto_sources([dubbed, original], 720).selector == "original-av"


def test_mp3_progressive_fallback_prefers_original():
    original = {**audio("original-av", 128, 10), "vcodec": "avc1"}
    dubbed = {**original, "format_id": "dub-av", "language_preference": -1, "abr": 160}
    assert (
        build_mp3_export_plan({"formats": [dubbed, original]}).audio_format_id
        == "original-av"
    )
