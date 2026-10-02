from pathlib import Path

import pytest

from yt_downloader.app import (
    apply_original_caption_options,
    build_vod_ffmpeg_command,
    original_caption_selection,
)


@pytest.mark.parametrize("manual", [True, False])
def test_original_manual_then_automatic_and_no_translation(manual):
    track = [{"ext": "vtt", "url": "https://example.invalid/private"}]
    info = {
        "automatic_captions": {"ru-orig": track, "en": track},
        "subtitles": {"ru": track} if manual else {},
    }
    opts = {"postprocessors": []}
    prepared = apply_original_caption_options(opts, info)
    assert opts["subtitleslangs"] == ["ru"]
    assert opts["writesubtitles"] is manual
    assert opts["writeautomaticsub"] is not manual
    assert opts["postprocessors"] == [{"key": "FFmpegEmbedSubtitle"}]
    assert list(prepared["subtitles" if manual else "automatic_captions"]) == ["ru"]
    assert "ru-orig" in info["automatic_captions"]


@pytest.mark.parametrize(
    "info",
    [
        {"subtitles": {"en": [{}]}},
        {"automatic_captions": {"en": [{}]}},
        {"automatic_captions": {"en-orig": [{}], "ru-orig": [{}]}},
        {"automatic_captions": {"en.*-orig": [{}]}},
        {},
    ],
)
def test_unknown_original_never_guesses_or_fetches(info):
    opts = {"postprocessors": []}
    assert original_caption_selection(info) is None
    assert apply_original_caption_options(opts, info) is info
    assert opts == {"postprocessors": []}


def test_original_audio_metadata_allows_uploaded_original():
    info = {
        "formats": [{"language": "ru", "language_preference": 10, "acodec": "aac"}],
        "subtitles": {"ru": [{}], "en": [{}]},
    }
    assert original_caption_selection(info) == ("ru", "manual")


@pytest.mark.parametrize("nvenc", [True, False])
def test_optional_subtitles_survive_mp4_command(nvenc):
    cmd = build_vod_ffmpeg_command(
        "ffmpeg", Path("input"), Path("output"), use_nvenc=nvenc
    )
    assert "0:s?" in cmd
    assert cmd[cmd.index("-c:s") + 1] == "mov_text"
    assert cmd[cmd.index("-c:v") + 1] == ("h264_nvenc" if nvenc else "libx264")


def test_real_mp4_caption_transcode_roundtrip(tmp_path):
    import json
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("local FFmpeg fixture tools unavailable")
    subtitle = tmp_path / "captions.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:00,800\nFixture captions\n")
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=size=64x64:rate=10:duration=1",
            "-i",
            str(subtitle),
            "-map",
            "0:v",
            "-map",
            "1:0",
            "-c:v",
            "libx264",
            "-c:s",
            "mov_text",
            "-metadata:s:s:0",
            "language=rus",
            "-metadata:s:s:0",
            "handler_name=Original captions (manual)",
            str(source),
        ],
        check=True,
    )
    output = tmp_path / "output.mp4"
    command = build_vod_ffmpeg_command(
        ffmpeg,
        source,
        output,
        x264_preset="ultrafast",
        preserve_metadata=False,
        preserve_caption_metadata=True,
    )
    subprocess.run(command, check=True, capture_output=True)
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_streams", "-of", "json", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    tracks = [
        s for s in json.loads(probe.stdout)["streams"] if s["codec_type"] == "subtitle"
    ]
    assert len(tracks) == 1
    assert tracks[0]["codec_name"] == "mov_text"
    assert tracks[0]["tags"]["language"] == "rus"
    assert tracks[0]["tags"]["handler_name"] == "Original captions (manual)"


def test_caption_failure_does_not_claim_success():
    from yt_downloader.app import require_original_caption_stream

    for probe in ({}, {"streams": [{"codec_type": "video"}, {"codec_type": "audio"}]}):
        with pytest.raises(RuntimeError, match="no output was committed"):
            require_original_caption_stream(probe)
    require_original_caption_stream({"streams": [{"codec_type": "subtitle"}]})


def test_closed_summary_has_no_provider_secrets():
    from yt_downloader.app import compact_video_metadata, sanitized_caption_summary

    value = {
        "language": "ru",
        "source_kind": "manual",
        "role": "original",
        "url": "secret",
        "token": "secret",
    }
    expected = {"language": "ru", "source_kind": "manual", "role": "original"}
    assert sanitized_caption_summary(value) == expected
    assert (
        compact_video_metadata({"vodforge_caption_summary": value}, [])[
            "vodforge_caption_summary"
        ]
        == expected
    )
    for invalid in (
        {**value, "language": "https://secret"},
        {**value, "role": "translation"},
        {**value, "source_kind": "unknown"},
    ):
        assert sanitized_caption_summary(invalid) is None
