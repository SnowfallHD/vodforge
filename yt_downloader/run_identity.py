from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .history import sanitize_durable_url
from .models import DownloadJob, ExportMode, OutputType

ATTEMPT_SIGNATURE_KEY = "vodforge_attempt_signature"
OUTPUT_PROFILE_KEY = "vodforge_output_profile"
OUTPUT_PROFILE_DETAILS_KEY = "vodforge_output_profile_details"


def _normalized_path(path: Path | str) -> str:
    expanded = Path(path).expanduser()
    try:
        expanded = expanded.resolve(strict=False)
    except OSError:
        expanded = Path(os.path.abspath(str(expanded)))
    return os.path.normcase(str(expanded))


def _source_identity(job: DownloadJob) -> tuple[str, ...]:
    preview_id = str((job.preview_info or {}).get("id") or "").strip()
    playlist_id = str((job.preview_info or {}).get("playlist_id") or "").strip()
    safe_urls = tuple(
        safe
        for raw in (job.urls or [job.url])
        if (safe := sanitize_durable_url(raw, preserve_youtube_context=True))
    )
    normalized_sources: list[str] = []
    for safe_url in safe_urls:
        parsed = urllib.parse.urlsplit(safe_url)
        query = urllib.parse.parse_qs(parsed.query)
        video_id = str((query.get("v") or [""])[0]).strip()
        url_playlist_id = str((query.get("list") or [""])[0]).strip()
        if video_id:
            organization = "" if job.single_video_only else url_playlist_id
            normalized_sources.append(f"youtube:{video_id}:{organization}")
        else:
            normalized_sources.append(safe_url)
    if not normalized_sources and preview_id:
        organization = "" if job.single_video_only else playlist_id
        normalized_sources.append(f"youtube:{preview_id}:{organization}")
    return tuple(normalized_sources)


def job_output_settings(job: DownloadJob) -> dict[str, Any]:
    """Return the canonical requested-output contract for duplicate decisions."""

    common: dict[str, Any] = {
        "output_type": job.output_type.value,
        "single_video_only": job.single_video_only,
        "batch_mode": job.batch_mode,
        "tags": sorted({str(tag).strip() for tag in job.tags if str(tag).strip()}),
    }
    if job.output_type is OutputType.MP3:
        common["mp3"] = {
            "bitrate_kbps": job.mp3_settings.bitrate_kbps,
            "sample_rate": job.mp3_settings.sample_rate,
            "channels": job.mp3_settings.channels,
            "embed_metadata": job.mp3_settings.embed_metadata,
            "embed_cover_art": job.mp3_settings.embed_cover_art,
            "custom_cover_art_path": (
                _normalized_path(job.mp3_settings.custom_cover_art_path)
                if job.mp3_settings.custom_cover_art_path is not None
                else None
            ),
        }
        return common

    common["mp4"] = {
        "quality_label": job.quality_label,
        "export_mode": job.export_mode.value,
        "use_nvenc": job.use_nvenc,
        "embed_thumbnail": job.embed_thumbnail,
        "write_thumbnail": job.write_thumbnail,
        "embed_metadata": job.embed_metadata,
        "write_info_json": job.write_info_json,
    }
    if job.export_mode is ExportMode.MANUAL_OVERRIDE:
        common["mp4"]["manual"] = {
            "video_bitrate_kbps": job.manual_settings.video_bitrate_kbps,
            "audio_bitrate_kbps": job.manual_settings.audio_bitrate_kbps,
            "audio_sample_rate": job.manual_settings.audio_sample_rate,
            "audio_channels": job.manual_settings.audio_channels,
            "audio_codec": job.manual_settings.audio_codec.value,
            "x264_preset": job.manual_settings.x264_preset,
        }
    return common


def job_attempt_signature(job: DownloadJob) -> str:
    """Identify one source, output destination, organization, and settings intent."""

    payload = {
        "source": _source_identity(job),
        "output_root": _normalized_path(job.output_dir),
        "settings": job_output_settings(job),
    }
    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def matching_attempt(
    job: DownloadJob, candidates: Iterable[DownloadJob]
) -> DownloadJob | None:
    signature = job_attempt_signature(job)
    return next(
        (
            candidate
            for candidate in candidates
            if job_attempt_signature(candidate) == signature
        ),
        None,
    )


def job_output_profile(job: DownloadJob) -> str:
    if job.output_type is OutputType.MP3:
        return f"MP3 • {job.mp3_settings.bitrate_kbps} kbps"
    return f"MP4 • {job.quality_label} • {job.export_mode.value}"


def job_output_profile_details(job: DownloadJob) -> str:
    settings = job_output_settings(job)
    lines = [job_output_profile(job), f"Destination: {job.output_dir}"]
    if job.output_type is OutputType.MP3:
        mp3 = settings["mp3"]
        lines.extend(
            (
                f"Sample rate: {mp3['sample_rate'] or 'Preserve source'}",
                f"Channels: {mp3['channels'] or 'Preserve source'}",
                f"Metadata: {'Embedded' if mp3['embed_metadata'] else 'Not embedded'}",
                f"Cover art: {'Embedded' if mp3['embed_cover_art'] else 'Not embedded'}",
            )
        )
    else:
        mp4 = settings["mp4"]
        if manual := mp4.get("manual"):
            lines.extend(
                (
                    f"Video bitrate: {manual['video_bitrate_kbps']} kbps",
                    f"Audio: {manual['audio_codec']} • {manual['audio_bitrate_kbps']} kbps",
                    f"Sample rate/channels: {manual['audio_sample_rate']} Hz • {manual['audio_channels']}",
                )
            )
        lines.extend(
            (
                f"Embedded metadata: {'Yes' if mp4['embed_metadata'] else 'No'}",
                f"Embedded thumbnail: {'Yes' if mp4['embed_thumbnail'] else 'No'}",
                f"Separate thumbnail: {'Yes' if mp4['write_thumbnail'] else 'No'}",
                f"Metadata file: {'Yes' if mp4['write_info_json'] else 'No'}",
            )
        )
    if job.tags:
        lines.append(f"Tags: {', '.join(job.tags)}")
    return "\n".join(lines)


def annotate_job_metadata(job: DownloadJob, info: dict[str, Any]) -> dict[str, Any]:
    annotated = dict(info)
    annotated[ATTEMPT_SIGNATURE_KEY] = job_attempt_signature(job)
    annotated[OUTPUT_PROFILE_KEY] = job_output_profile(job)
    annotated[OUTPUT_PROFILE_DETAILS_KEY] = job_output_profile_details(job)
    return annotated


def metadata_attempt_signature(info: dict[str, Any]) -> str:
    return str(info.get(ATTEMPT_SIGNATURE_KEY) or "").strip()


def metadata_output_profile(info: dict[str, Any]) -> str:
    stored = str(info.get(OUTPUT_PROFILE_KEY) or "").strip()
    if stored:
        return stored
    output_type = str(info.get("vodforge_output_type") or "MP4").upper()
    summary = info.get("vodforge_encoding_summary")
    output = summary.get("output") if isinstance(summary, dict) else None
    output = output if isinstance(output, dict) else {}
    if output_type == "MP3":
        bitrate = str(output.get("Target audio bitrate") or "").strip()
        return f"MP3 • {bitrate}" if bitrate else "MP3"
    resolution = str(output.get("Output resolution") or "").strip()
    mode = str(output.get("Output rate-control mode") or "").strip()
    details = " • ".join(value for value in (resolution, mode) if value)
    return f"MP4 • {details}" if details else "MP4"


def metadata_output_profile_details(info: dict[str, Any]) -> str:
    stored = str(info.get(OUTPUT_PROFILE_DETAILS_KEY) or "").strip()
    if stored:
        return stored
    profile = metadata_output_profile(info)
    summary = info.get("vodforge_encoding_summary")
    output = summary.get("output") if isinstance(summary, dict) else None
    if not isinstance(output, dict):
        return profile
    detail_keys = (
        "Output video codec",
        "Target video bitrate",
        "Output audio codec",
        "Target audio bitrate",
        "Audio sample rate",
        "Audio channels",
        "Output file path",
    )
    lines = [profile]
    lines.extend(
        f"{key}: {output[key]}"
        for key in detail_keys
        if str(output.get(key) or "").strip() not in {"", "Pending", "Not produced"}
    )
    return "\n".join(lines)
