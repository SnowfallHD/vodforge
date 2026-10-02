"""Saved stream provenance, bounded parsing, exact clocks and read-only extraction."""

import shutil
import subprocess
import threading

import pytest

from yt_downloader.history import sanitize_history_record
from yt_downloader.subtitle_cues import (
    MAX_BYTES,
    Cue,
    CueTimeline,
    bounded_capture,
    extract_saved_cues,
    file_identity,
    parse_srt,
    probe_saved_subtitles,
    sanitize_caption_summary,
    saved_subtitle_catalog,
)


def stream(index, language="eng", title="", codec="mov_text"):
    return {
        "index": index,
        "codec_type": "subtitle",
        "codec_name": codec,
        "tags": {"language": language, "handler_name": title},
    }


def test_catalog_uses_actual_stream_index_and_known_original_not_order():
    data = {
        "streams": [
            stream(7, "spa"),
            stream(3, "eng", "Original captions (manual)"),
            stream(9, "und"),
        ]
    }
    catalog = saved_subtitle_catalog(data)
    assert catalog["original"]["index"] == 3
    assert catalog["translations"] == [
        {"index": 7, "language": "es", "label": "ES · Track 8"}
    ]


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [stream(0)],
        [stream(0, "und", "Original captions (manual)")],
        [
            stream(0, title="Original captions (manual)"),
            stream(2, title="Original captions (automatic)"),
        ],
        [stream(0, title="Original captions (manual)", codec="hdmv_pgs_subtitle")],
    ],
)
def test_no_guessed_original_or_translation_for_ambiguous_saved_streams(rows):
    result = saved_subtitle_catalog(
        {"streams": rows},
        {"language": "en", "source_kind": "manual", "role": "original"},
    )
    assert result == {"original": None, "translations": []}


def test_summary_is_closed_and_corroborates_but_cannot_invent_stream():
    summary = {
        "language": "ru",
        "source_kind": "automatic",
        "role": "original",
        "url": "SECRET",
        "cookies": "SECRET",
    }
    assert sanitize_caption_summary(summary) == {
        "language": "ru",
        "source_kind": "automatic",
        "role": "original",
    }
    result = saved_subtitle_catalog(
        {"streams": [stream(1, title="Original captions (manual)")]}, summary
    )
    assert result["original"] is None
    record = sanitize_history_record(
        {"vodforge_caption_summary": summary}, "/tmp/fictional"
    )
    assert record["vodforge_caption_summary"] == sanitize_caption_summary(summary)
    assert "SECRET" not in str(record)


@pytest.mark.parametrize(
    "bad",
    [
        {"language": "en", "role": "translated", "source_kind": "manual"},
        {"language": "und", "role": "original", "source_kind": "manual"},
        None,
    ],
)
def test_bad_provenance_rejected(bad):
    assert sanitize_caption_summary(bad) is None


def test_plaintext_parser_overlap_seek_pause_and_end_exclusive():
    cues = parse_srt(
        "1\n00:00:01,000 --> 00:00:03,000\n<i>A &amp; B</i>\n\n2\n00:00:02,000 --> 00:00:04,000\n{\\an8}Second\n"
    )
    timeline = CueTimeline(cues)
    assert timeline.text_at(2500) == "A & B\nSecond"
    assert timeline.text_at(1000) == "A & B"
    assert timeline.text_at(3000) == "Second"
    assert timeline.text_at(4000) == ""
    assert timeline.text_at(2500) == "A & B\nSecond"
    assert timeline.text_at(0) == ""


def test_read_limits_and_invalid_timing():
    with pytest.raises(ValueError, match="read limit"):
        parse_srt("x" * (MAX_BYTES + 1))
    assert not parse_srt("1\n00:99:00,000 --> 00:99:01,000\nBad\n")
    assert not parse_srt("1\n00:00:02,000 --> 00:00:01,000\nBackwards\n")


def test_indexed_timeline_handles_many_expired_cues():
    timeline = CueTimeline(
        tuple(Cue(n * 1000, n * 1000 + 500, str(n)) for n in range(50000))
    )
    assert timeline.text_at(49000000) == "49000"
    assert timeline.text_at(49000500) == ""


def test_bounded_child_cancelled_and_reaped():
    import sys

    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(ValueError):
        bounded_capture(
            [sys.executable, "-c", "import time; time.sleep(20)"], cancelled
        )


def test_actual_two_saved_tracks_extract_readonly(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("Existing FFmpeg unavailable")
    original = tmp_path / "original.srt"
    translated = tmp_path / "translated.srt"
    original.write_text("1\n00:00:00,000 --> 00:00:01,500\nOriginal\n")
    translated.write_text("1\n00:00:00,000 --> 00:00:01,500\nTraducido\n")
    media = tmp_path / "fictional.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=s=32x32:d=2",
            "-i",
            str(original),
            "-i",
            str(translated),
            "-map",
            "0:v",
            "-map",
            "1:s",
            "-map",
            "2:s",
            "-c:v",
            "libx264",
            "-c:s",
            "mov_text",
            "-metadata:s:s:0",
            "language=eng",
            "-metadata:s:s:0",
            "handler_name=Original captions (manual)",
            "-metadata:s:s:1",
            "language=spa",
            str(media),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    identity = file_identity(media)
    cancel = threading.Event()
    catalog = probe_saved_subtitles(ffmpeg, media, cancel, None)
    assert catalog["original"]["index"] == 1
    assert catalog["translations"][0]["index"] == 2
    assert (
        CueTimeline(extract_saved_cues(ffmpeg, media, 1, cancel)).text_at(500)
        == "Original"
    )
    assert (
        CueTimeline(extract_saved_cues(ffmpeg, media, 2, cancel)).text_at(500)
        == "Traducido"
    )
    assert file_identity(media) == identity


def test_subtitle_track_summary_closed_backcompatible_and_no_secrets():
    from yt_downloader.subtitle_cues import sanitize_subtitle_tracks

    rows = [
        {
            "language": "rus",
            "role": "original",
            "source_kind": "manual",
            "url": "SECRET",
        },
        {
            "language": "eng",
            "role": "translated",
            "source_kind": "automatic_translation",
            "provider": "SECRET",
        },
    ]
    clean = sanitize_subtitle_tracks(rows)
    assert clean == [
        {"language": "ru", "role": "original", "source_kind": "manual"},
        {
            "language": "en",
            "role": "translated",
            "source_kind": "automatic_translation",
        },
    ]
    assert (
        sanitize_history_record({"vodforge_subtitle_tracks": rows}, "/tmp/fictional")[
            "vodforge_subtitle_tracks"
        ]
        == clean
    )
    assert not sanitize_subtitle_tracks(rows * 2)
    assert not sanitize_subtitle_tracks([rows[0], rows[0]])
    assert not sanitize_subtitle_tracks(
        [{**rows[0], "source_kind": "automatic_translation"}]
    )
