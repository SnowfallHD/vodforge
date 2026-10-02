from dataclasses import replace

import pytest

from tests.test_run_identity import make_job
from yt_downloader.app import (
    _build_item_preflight_options,
    apply_original_caption_options,
    require_selected_subtitle_streams,
    sanitized_subtitle_tracks,
)
from yt_downloader.caption_languages import translated_subtitle_language
from yt_downloader.models import OutputType
from yt_downloader.run_identity import job_attempt_signature
from yt_downloader.run_state import deserialize_download_job, serialize_download_job


def source_info():
    return {
        "subtitles": {
            "ru": [{"ext": "vtt", "url": "https://example.invalid/?lang=ru"}]
        },
        "automatic_captions": {
            "ru-orig": [{"ext": "vtt", "url": "https://example.invalid/?lang=ru"}],
            "en-ru": [
                {"ext": "vtt", "url": "https://example.invalid/?lang=ru&tlang=en"}
            ],
            "fr": [{"ext": "vtt", "url": "https://example.invalid/?lang=ru&tlang=fr"}],
        },
    }


@pytest.mark.parametrize("uploaded", [True, False])
def test_exact_original_plus_one_explicit_translation(uploaded):
    info = source_info()
    if uploaded:
        info["subtitles"]["en"] = [
            {"ext": "vtt", "url": "https://example.invalid/uploaded"}
        ]
    opts = {"postprocessors": []}
    prepared = apply_original_caption_options(opts, info, "en")
    assert opts["subtitleslangs"] == ["ru", "en"]
    assert set(prepared["subtitles"]) | set(prepared["automatic_captions"]) == {
        "ru",
        "en",
    }
    assert "fr" not in prepared["automatic_captions"]
    assert prepared["vodforge_subtitle_tracks"][1] == {
        "language": "en",
        "source_kind": "manual" if uploaded else "automatic_translation",
        "role": "translated",
    }
    assert "url" not in str(
        sanitized_subtitle_tracks(prepared["vodforge_subtitle_tracks"])
    )
    assert "en-ru" in info["automatic_captions"]


@pytest.mark.parametrize("target", [None, "ru", "de"])
def test_off_same_or_unavailable_does_not_invent_translation(target):
    opts = {"postprocessors": []}
    prepared = apply_original_caption_options(opts, source_info(), target)
    assert opts["subtitleslangs"] == ["ru"]
    assert len(prepared["vodforge_subtitle_tracks"]) == 1


def test_generated_translation_must_match_original_source():
    info = source_info()
    info["automatic_captions"]["en-ru"][0]["url"] = (
        "https://example.invalid/?lang=es&tlang=en"
    )
    prepared = apply_original_caption_options({"postprocessors": []}, info, "en")
    assert len(prepared["vodforge_subtitle_tracks"]) == 1


@pytest.mark.parametrize("invalid", ["all", "en.*", "xx", "https://secret", 1])
def test_closed_language_selector_rejects_arbitrary_authority(invalid):
    with pytest.raises(ValueError):
        translated_subtitle_language(invalid)


def test_optin_retry_identity_and_backcompat(tmp_path):
    ordinary = make_job(tmp_path)
    translated = replace(ordinary, translated_subtitle_language="en")
    assert job_attempt_signature(translated) != job_attempt_signature(ordinary)
    payload = serialize_download_job(translated)
    assert deserialize_download_job(payload).translated_subtitle_language == "en"
    payload.pop("translated_subtitle_language")
    assert deserialize_download_job(payload).translated_subtitle_language is None
    assert job_attempt_signature(
        deserialize_download_job(payload)
    ) == job_attempt_signature(ordinary)
    for output in (OutputType.MP3, OutputType.ORIGINAL):
        audio = replace(ordinary, output_type=output)
        assert job_attempt_signature(audio) == job_attempt_signature(
            replace(audio, translated_subtitle_language="en")
        )


def test_translation_discovery_only_for_opted_in_mp4(tmp_path):
    job = make_job(tmp_path)

    def options(j):
        return _build_item_preflight_options(
            j, cookie_source_loaded=False, ffmpeg=None, deno_path=None
        )

    assert not options(job).get("writeautomaticsub")
    assert options(replace(job, translated_subtitle_language="en"))["writeautomaticsub"]
    assert not options(
        replace(job, translated_subtitle_language="en", output_type=OutputType.MP3)
    ).get("writeautomaticsub")


def test_language_and_count_required_before_commit():
    expected = [
        {"language": "ru", "source_kind": "manual", "role": "original"},
        {
            "language": "en",
            "source_kind": "automatic_translation",
            "role": "translated",
        },
    ]
    valid = {
        "streams": [
            {"codec_type": "subtitle", "tags": {"language": code}}
            for code in ("rus", "eng")
        ]
    }
    require_selected_subtitle_streams(valid, expected)
    for languages in [("rus",), ("rus", "fra"), ("rus", "eng", "fra")]:
        with pytest.raises(RuntimeError, match="no output was committed"):
            require_selected_subtitle_streams(
                {
                    "streams": [
                        {"codec_type": "subtitle", "tags": {"language": code}}
                        for code in languages
                    ]
                },
                expected,
            )


def test_actual_two_track_roundtrip(tmp_path):
    import json
    import shutil
    import subprocess

    from yt_downloader.app import build_vod_ffmpeg_command

    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("local fixture tools unavailable")
    captions = []
    for language in ("ru", "en"):
        path = tmp_path / f"{language}.srt"
        path.write_text(f"1\n00:00:00,000 --> 00:00:00,800\n{language} fixture\n")
        captions.append(path)
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
            str(captions[0]),
            "-i",
            str(captions[1]),
            "-map",
            "0:v",
            "-map",
            "1:0",
            "-map",
            "2:0",
            "-c:v",
            "libx264",
            "-c:s",
            "mov_text",
            "-metadata:s:s:0",
            "language=rus",
            "-metadata:s:s:0",
            "handler_name=Original captions (manual)",
            "-metadata:s:s:1",
            "language=eng",
            "-metadata:s:s:1",
            "handler_name=Translated subtitles (automatic translation)",
            str(source),
        ],
        check=True,
    )
    output = tmp_path / "output.mp4"
    subprocess.run(
        build_vod_ffmpeg_command(
            ffmpeg,
            source,
            output,
            x264_preset="ultrafast",
            preserve_metadata=False,
            preserve_caption_metadata=2,
        ),
        check=True,
        capture_output=True,
    )
    data = json.loads(
        subprocess.run(
            [ffprobe, "-v", "error", "-show_streams", "-of", "json", str(output)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    tracks = [
        stream for stream in data["streams"] if stream["codec_type"] == "subtitle"
    ]
    assert [stream["tags"]["language"] for stream in tracks] == ["rus", "eng"]
    assert all(stream["codec_name"] == "mov_text" for stream in tracks)
    assert tracks[0]["tags"]["handler_name"].startswith("Original captions")
    assert tracks[1]["tags"]["handler_name"].startswith("Translated subtitles")


def test_installed_ytdlp_embedding_then_production_transcode(tmp_path):
    import json
    import shutil
    import subprocess

    from yt_dlp import YoutubeDL
    from yt_dlp.postprocessor.ffmpeg import FFmpegEmbedSubtitlePP

    from yt_downloader.app import build_vod_ffmpeg_command

    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("local fixture tools unavailable")
    source = tmp_path / "staged.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=size=64x64:rate=10:duration=1",
            "-c:v",
            "libx264",
            str(source),
        ],
        check=True,
    )
    options = {"postprocessors": []}
    prepared = apply_original_caption_options(options, source_info(), "en")
    requested = {}
    for code, role in [("ru", "subtitles"), ("en", "automatic_captions")]:
        subtitle = tmp_path / f"{code}.srt"
        subtitle.write_text(f"1\n00:00:00,000 --> 00:00:00,800\n{code} fixture\n")
        requested[code] = {
            **prepared[role][code][0],
            "ext": "srt",
            "filepath": str(subtitle),
        }
    with YoutubeDL({"quiet": True, "ffmpeg_location": ffmpeg}) as ydl:
        pp = FFmpegEmbedSubtitlePP(ydl)
        deletes, info = pp.run(
            {"filepath": str(source), "ext": "mp4", "requested_subtitles": requested}
        )
        assert set(deletes) == {track["filepath"] for track in requested.values()}
        assert info["filepath"] == str(source)
    output = tmp_path / "export.mp4"
    subprocess.run(
        build_vod_ffmpeg_command(
            ffmpeg,
            source,
            output,
            x264_preset="ultrafast",
            preserve_metadata=False,
            preserve_caption_metadata=2,
        ),
        check=True,
        capture_output=True,
    )
    data = json.loads(
        subprocess.run(
            [ffprobe, "-v", "error", "-show_streams", "-of", "json", str(output)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    tracks = [track for track in data["streams"] if track["codec_type"] == "subtitle"]
    assert [track["tags"]["language"] for track in tracks] == ["rus", "eng"]
    assert tracks[0]["tags"]["handler_name"] == "Original captions (manual)"
    assert (
        tracks[1]["tags"]["handler_name"]
        == "Translated subtitles (automatic translation)"
    )
    require_selected_subtitle_streams(data, prepared["vodforge_subtitle_tracks"])


def test_automatic_original_and_translation_both_requested():
    info = source_info()
    info["subtitles"] = {}
    options = {"postprocessors": []}
    prepared = apply_original_caption_options(options, info, "en")
    assert options["writesubtitles"] is False
    assert options["writeautomaticsub"] is True
    assert options["subtitleslangs"] == ["ru", "en"]
    assert set(prepared["automatic_captions"]) == {"ru", "en"}
