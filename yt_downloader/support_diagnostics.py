"""Bounded, opt-in failure context, never whole-log or credential collection."""

from __future__ import annotations

import platform
import re
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .version import __version__

MAX_DIAGNOSTICS = 6000
_SECRET = re.compile(
    r"authorization|cookie|password|token|secret|api.?key|signature|bearer|set-cookie",
    re.IGNORECASE,
)
_RELEVANT = re.compile(
    r"error|warning|failed|selected format|selected video|selected audio|FFmpeg command started|transcod|validat|HTTP Error|extract",
    re.IGNORECASE,
)


def redact_line(line: str) -> str:
    if _SECRET.search(line):
        return "[Sensitive diagnostic line omitted]"
    line = re.sub(r"https?://\S+", "[URL]", line, flags=re.IGNORECASE)
    line = re.sub(r"[A-Za-z]:[\\/][^\r\n;]+|(?:/|~[/\\])(?:[^\s;]+)", "[path]", line)
    line = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", line)
    line = re.sub(r"(['\"]).*?\1", "[quoted value]", line)
    line = re.sub(r"[A-Za-z0-9_+=-]{32,}", "[identifier]", line)
    return "".join(c for c in line if c in "\n\t" or ord(c) >= 32)[:320]


def public_video_url(value: str) -> str | None:
    """Never attach arbitrary/signed URLs, playlist IDs, or URL credentials."""
    try:
        url = urlsplit(value)
        if url.scheme != "https" or url.username or url.password:
            return None
        if url.hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            video = parse_qs(url.query).get("v", [""])[0]
            if url.path.startswith(("/shorts/", "/live/")):
                video = url.path.split("/")[2]
        elif url.hostname == "youtu.be":
            video = url.path.strip("/")
        else:
            return None
        return (
            f"https://www.youtube.com/watch?v={video}"
            if re.fullmatch(r"[\w-]{11}", video)
            else None
        )
    except ValueError:
        return None


@dataclass(frozen=True)
class FailureContext:
    diagnostics: str
    video_url: str | None = None


def failure_context(job: Any, message: str) -> FailureContext:
    """Snapshot only the finished job; callers cannot accidentally attach other runs."""
    try:
        downloader_version = version("yt-dlp")
    except PackageNotFoundError:
        downloader_version = "bundled (package metadata unavailable)"

    lines = [
        f"VODForge: {__version__}",
        f"OS: {platform.system()} {platform.release()}",
        f"yt-dlp: {downloader_version}",
        f"Output: {job.output_type.value}; {job.quality_label}; {job.export_mode.value}",
        f"Playlist ignored: {job.single_video_only}",
        f"Failure: {redact_line(message)}",
    ]
    if job.failure_diagnostic:
        # Closed machine-valued failure facts already owned by failure classification.
        lines.append(f"Failure facts: {job.failure_diagnostic.payload()}")
    for group, fields in (
        (
            "manual_settings",
            (
                "video_bitrate_kbps",
                "audio_bitrate_kbps",
                "audio_sample_rate",
                "audio_channels",
                "fps",
                "x264_preset",
            ),
        ),
        (
            "mp3_settings",
            (
                "bitrate_kbps",
                "sample_rate",
                "channels",
                "embed_metadata",
                "embed_cover_art",
            ),
        ),
    ):
        settings = getattr(job, group, None)
        if settings is not None:
            lines.extend(
                f"{group}.{key}: {redact_line(str(getattr(settings, key)))}"
                for key in fields
                if hasattr(settings, key)
            )
    recent = [
        redact_line(str(line))
        for line in job.activity_lines[-100:]
        if _RELEVANT.search(str(line))
    ]
    lines.extend(recent[-18:])
    # A playlist's initiating URL is not proof of which child failed. Do not
    # mislabel its first video as the reproducible failing source.
    source = (
        public_video_url(job.url)
        if job.single_video_only and not getattr(job, "batch_mode", False)
        else None
    )
    return FailureContext("\n".join(lines)[:MAX_DIAGNOSTICS], source)
