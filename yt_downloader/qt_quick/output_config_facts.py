"""Chosen output configuration, distinct from measured encoder/output facts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from yt_downloader.export_planning import export_mode_display_name
from yt_downloader.models import DownloadJob, ExportMode, OutputType
from yt_downloader.youtube_access import COOKIE_BROWSER_VALUES


def job_config(job: DownloadJob) -> dict[str, Any]:
    manual, mp3 = job.manual_settings, job.mp3_settings
    return {
        "format": job.output_type.value,
        "mode": job.export_mode.value,
        "quality": job.quality_label,
        "folder": str(job.output_dir),
        "single_video_only": job.single_video_only,
        "use_nvenc": job.use_nvenc,
        "embed_thumbnail": job.embed_thumbnail,
        "write_thumbnail": job.write_thumbnail,
        "embed_metadata": job.embed_metadata,
        "write_info_json": job.write_info_json,
        "tags": list(job.tags),
        "batch_count": len(job.urls) if job.batch_mode else 0,
        "access": "Public"
        if not job.use_cookies
        else "Browser"
        if job.cookie_browser
        else "cookies.txt",
        "browser": job.cookie_browser or "",
        "manual": {
            "manual_rate_control": "Quality" if manual.video_crf is not None else "CBR",
            "manual_crf": str(manual.video_crf),
            "manual_video_bitrate": str(manual.video_bitrate_kbps),
            "manual_audio_codec": manual.audio_codec.value,
            "manual_audio_bitrate": str(manual.audio_bitrate_kbps),
            "manual_sample_rate": manual.audio_sample_rate,
            "manual_channels": "Mono" if manual.audio_channels == "1" else "Stereo",
            "manual_preset": manual.x264_preset,
        },
        "mp3": {
            "mp3_quality": f"{mp3.bitrate_kbps} kbps",
            "mp3_sample_rate": mp3.sample_rate or "Preserve source",
            "mp3_channels": {"1": "Mono", "2": "Stereo"}.get(
                mp3.channels or "", mp3.channels or "Preserve source"
            ),
            "mp3_cover_art_mode": "Custom art"
            if mp3.custom_cover_art_path
            else "Source thumbnail"
            if mp3.embed_cover_art
            else "No Art",
            "mp3_embed_metadata": mp3.embed_metadata,
        },
    }


def chosen_config_facts(
    config: Mapping[str, Any], *, nvenc_available: bool | None
) -> list[dict[str, str]]:
    """Only user-facing choices; never cookie files, source URLs or credentials."""
    rows: list[dict[str, str]] = []

    def add(label: str, value: object) -> None:
        rows.append({"label": label, "value": str(value)})

    def toggle(key: str) -> str:
        return "On" if config.get(key) else "Off"

    output = str(config["format"])
    mp4 = output == OutputType.MP4.value
    mp3 = output == OutputType.MP3.value
    mode = str(config["mode"])
    add("Format", output)
    if mp4:
        add("Output mode", export_mode_display_name(ExportMode(mode)))
        add("Quality ceiling", config["quality"])
    add("Save to", config["folder"])
    access = config.get("access", "Public")
    raw_browser = str(config.get("browser") or "")
    browser = next(
        (
            name
            for name, value in COOKIE_BROWSER_VALUES.items()
            if raw_browser.casefold() in {name.casefold(), value}
        ),
        "Not selected",
    )
    # Browser names come from the existing closed browser selector, not profile paths.
    add(
        "YouTube access",
        "Public (no cookies)"
        if access == "Public"
        else f"Browser ({browser})"
        if access == "Browser"
        else "Not recorded"
        if access == "Not recorded"
        else "cookies.txt",
    )
    add(
        "NVENC requested",
        (toggle("use_nvenc") + " (capability not recorded)")
        if mp4 and nvenc_available is None
        else toggle("use_nvenc")
        if mp4 and nvenc_available
        else "N/A (not available)"
        if mp4
        else "N/A (audio only)",
    )
    if mp4:
        add("Video", "H.264")
        manual = config.get("manual") or {}
        if mode == ExportMode.MANUAL_OVERRIDE.value:
            rate = manual["manual_rate_control"]
            add("Rate control", rate)
            add(
                "Video quality" if rate == "Quality" else "Video bitrate",
                f"CRF {manual['manual_crf']}"
                if rate == "Quality"
                else f"{manual['manual_video_bitrate']} kbps",
            )
            add(
                "x264 preset",
                manual["manual_preset"]
                if not config.get("use_nvenc") or not nvenc_available
                else "N/A (NVENC requested)",
            )
            add("Audio", manual["manual_audio_codec"])
            add("Audio bitrate", f"{manual['manual_audio_bitrate']} kbps")
            add("Sample rate", f"{manual['manual_sample_rate']} Hz")
            add("Channels", manual["manual_channels"])
        else:
            add("Audio", "AAC")
        add("Embed thumbnail", toggle("embed_thumbnail"))
        add("Embed metadata", toggle("embed_metadata"))
    elif mp3:
        audio = config.get("mp3") or {}
        add("Audio quality", audio["mp3_quality"])
        add("Sample rate", audio["mp3_sample_rate"])
        add("Channels", audio["mp3_channels"])
        add("Cover art", audio["mp3_cover_art_mode"])
        add("Embed metadata", "On" if audio["mp3_embed_metadata"] else "Off")
    else:
        add("Encoding", "Stream copy (best available Opus or AAC)")
    add("Thumbnail file", toggle("write_thumbnail") if mp4 else "N/A (audio only)")
    add("Info JSON file", toggle("write_info_json") if mp4 else "N/A (audio only)")
    add("Ignore playlists", toggle("single_video_only"))
    if config.get("batch_count"):
        add("URL list", f"{config['batch_count']} URLs")
    add("Extra tags", ", ".join(config.get("tags") or []) or "None")
    return rows


def recorded_config(record: Mapping[str, Any]) -> dict[str, Any] | None:
    """Legacy retry snapshots retain non-access choices, never authentication."""
    from yt_downloader.history import RETRY_JOB_METADATA_KEY
    from yt_downloader.run_state import RunStateError, deserialize_download_job

    payload = record.get(RETRY_JOB_METADATA_KEY)
    if not isinstance(payload, Mapping):
        return None
    try:
        job = deserialize_download_job(payload, allow_missing_retry_url=True)
    except (RunStateError, TypeError, ValueError):
        return None
    if not record.get("vodforge_run_id") or job.run_id != record["vodforge_run_id"]:
        return None
    config = job_config(job)
    config["access"] = "Not recorded"
    config["browser"] = ""
    from yt_downloader.output_config_snapshot import (
        OUTPUT_CONFIG_DISPLAY_KEY,
        sanitize_output_config_display,
    )

    display = sanitize_output_config_display(record.get(OUTPUT_CONFIG_DISPLAY_KEY))
    if display is not None:
        config.update(display)
    return config
