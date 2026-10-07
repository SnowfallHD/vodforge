"""Read-only, bounded saved subtitle catalog and plain-text timed cues."""

from __future__ import annotations

import bisect
import html
import json
import re
import shutil
import subprocess  # nosec B404 - local decoder argv, no shell; call is bounded.
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yt_dlp.utils import ISO639Utils  # type: ignore[import-untyped]

from .platform_services import hidden_window_subprocess_kwargs

MAX_BYTES = 4 * 1024 * 1024
MAX_CUES = 50_000
TEXT_CODECS = {"mov_text", "subrip", "srt", "webvtt", "ass", "ssa", "text"}


def language_code(value: Any) -> str:
    value = str(value or "").strip().lower().split("-")[0]
    if not re.fullmatch(r"[a-z]{2,3}", value) or value in {"und", "zxx"}:
        return ""
    return ISO639Utils.long2short(value) or value


def sanitize_caption_summary(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    language = language_code(value.get("language"))
    kind = value.get("source_kind")
    if (
        not language
        or kind not in {"manual", "automatic"}
        or value.get("role") != "original"
    ):
        return None
    return {"language": language, "source_kind": kind, "role": "original"}


def sanitize_subtitle_tracks(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > 2:
        return []
    result = []
    for row in value:
        if not isinstance(row, dict):
            return []
        language = language_code(row.get("language"))
        role, kind = row.get("role"), row.get("source_kind")
        if (
            not language
            or role not in {"original", "translated"}
            or kind not in {"manual", "automatic", "automatic_translation"}
        ):
            return []
        if role == "original" and kind == "automatic_translation":
            return []
        result.append({"language": language, "role": role, "source_kind": kind})
    if len({row["role"] for row in result}) != len(result):
        return []
    return result


def saved_subtitle_catalog(data: dict[str, Any], summary: Any = None) -> dict[str, Any]:
    """Never classify an unlabeled track as original merely by its position."""
    streams = data.get("streams", [])
    if not isinstance(streams, list) or len(streams) > 128:
        return {"original": None, "translations": []}
    proven = sanitize_caption_summary(summary)
    rows: list[dict[str, Any]] = []
    for stream in streams:
        if not isinstance(stream, dict) or stream.get("codec_type") != "subtitle":
            continue
        if stream.get("codec_name") not in TEXT_CODECS:
            continue
        index = stream.get("index")
        tags = stream.get("tags", {})
        if not isinstance(index, int) or index < 0 or not isinstance(tags, dict):
            continue
        language = language_code(tags.get("language"))
        if not language:
            continue
        title = str(tags.get("handler_name") or tags.get("title") or "")
        role = title in {"Original captions (manual)", "Original captions (automatic)"}
        # Durable provenance corroborates the saved stream, never invents one.
        if proven and language != proven["language"]:
            role = False
        rows.append({"index": index, "language": language, "original": role})
    originals = [row for row in rows if row["original"]]
    original = originals[0] if len(originals) == 1 else None
    translations = []
    if original:
        translations = [
            {
                "index": row["index"],
                "language": row["language"],
                "label": f"{row['language'].upper()} · Track {row['index'] + 1}",
            }
            for row in rows
            if not row["original"] and row["language"] != original["language"]
        ][:16]
    return {"original": original, "translations": translations}


@dataclass(frozen=True)
class Cue:
    start_ms: int
    end_ms: int
    text: str


def parse_srt(data: str) -> tuple[Cue, ...]:
    if len(data.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Subtitle text exceeds the read limit")
    cues = []
    pattern = re.compile(r"(\d{1,3}):(\d{2}):(\d{2})[,.](\d{3})")
    for block in re.split(r"\n\s*\n", data.replace("\r\n", "\n").lstrip("\ufeff")):
        lines = block.splitlines()
        timing = next((i for i, line in enumerate(lines[:2]) if "-->" in line), -1)
        if timing < 0:
            continue
        parts = pattern.findall(lines[timing])
        if len(parts) != 2:
            continue
        times = [
            ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms)
            for h, m, s, ms in parts
        ]
        if times[1] <= times[0] or any(
            int(p[1]) >= 60 or int(p[2]) >= 60 for p in parts
        ):
            continue
        text = html.unescape(
            re.sub(r"<[^>]*>|\{\\[^}]*\}", "", "\n".join(lines[timing + 1 :]))
        )
        text = "".join(c for c in text if c in "\n\t" or ord(c) >= 32)[:4000].strip()
        if text:
            cues.append(Cue(times[0], times[1], text))
        if len(cues) > MAX_CUES:
            raise ValueError("Subtitle cue count exceeds the read limit")
    return tuple(sorted(cues, key=lambda cue: cue.start_ms))


class CueTimeline:
    """Indexed interval lookup; repeated clock ticks do not scan the whole file."""

    def __init__(self, cues: tuple[Cue, ...] = ()):
        self.cues = cues
        self.starts = tuple(cue.start_ms for cue in cues)
        running = 0
        ends = []
        for cue in cues:
            running = max(running, cue.end_ms)
            ends.append(running)
        self.ends = tuple(ends)

    def text_at(self, position_ms: int) -> str:
        first = bisect.bisect_right(self.ends, position_ms)
        last = bisect.bisect_right(self.starts, position_ms)
        return "\n".join(
            cue.text for cue in self.cues[first:last] if position_ms < cue.end_ms
        )[:8000]


def cue_text(cues: tuple[Cue, ...], position_ms: int) -> str:
    return CueTimeline(cues).text_at(position_ms)


def file_identity(path: Path) -> tuple[int, int, int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def bounded_capture(
    command: list[str], cancel: threading.Event, *, limit: int = MAX_BYTES
) -> bytes:
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(  # nosec B603 - local executable, argv, no shell
            command,
            stdout=output,
            stderr=subprocess.DEVNULL,
            **hidden_window_subprocess_kwargs(),
        )
        deadline = time.monotonic() + 30
        try:
            while process.poll() is None:
                if (
                    cancel.wait(0.025)
                    or time.monotonic() > deadline
                    or output.tell() > limit
                ):
                    raise ValueError("Subtitle reading stopped or exceeded its limit")
            if cancel.is_set() or process.returncode or output.tell() > limit:
                raise ValueError("Saved subtitle stream could not be read")
            output.seek(0)
            return output.read(limit + 1)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()


def probe_saved_subtitles(
    ffmpeg: str, path: Path, cancel: threading.Event, summary: Any
) -> dict[str, Any]:
    ffprobe = str(
        Path(ffmpeg).with_name(
            "ffprobe.exe" if Path(ffmpeg).suffix == ".exe" else "ffprobe"
        )
    )
    if not Path(ffprobe).is_file():
        ffprobe = shutil.which("ffprobe") or ""
    if not ffprobe:
        raise ValueError("Saved subtitle inspection is unavailable")
    raw = bounded_capture(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=index,codec_type,codec_name:stream_tags=language,title,handler_name",
            "-of",
            "json",
            str(path),
        ],
        cancel,
        limit=1024 * 1024,
    )
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise TypeError("Invalid saved subtitle catalog")
    return saved_subtitle_catalog(data, summary)


def extract_saved_cues(
    ffmpeg: str, path: Path, index: int, cancel: threading.Event
) -> tuple[Cue, ...]:
    raw = bounded_capture(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            f"0:{index}",
            "-vn",
            "-an",
            "-c:s",
            "srt",
            "-f",
            "srt",
            "pipe:1",
        ],
        cancel,
    )
    return parse_srt(raw.decode("utf-8", errors="replace"))
