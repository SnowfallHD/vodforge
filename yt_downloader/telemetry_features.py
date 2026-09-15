"""Bounded product vocabulary. Never pass user content to this module.

Feature owners report facts; ProductTelemetryOwner owns consent, identity and
transport. This vocabulary is shared by producers, validation and QA inventories.
"""

from __future__ import annotations

import platform
import uuid
from collections.abc import Mapping
from urllib.parse import parse_qs, urlsplit

from .failure_diagnostics import FAILURE_CODES

FEATURE_ACTIONS: dict[str, frozenset[str]] = {
    "settings": frozenset({"snapshot"}),
    "library": frozenset({"opened", "searched", "filtered", "selected", "removed"}),
    "organization": frozenset({"notes_saved", "tags_saved", "category_saved"}),
    "player": frozenset(
        {"completed", "failed", "seek", "chapter", "heatmap", "preview"}
    ),
    "missing_media": frozenset({"offered", "accepted", "completed"}),
    "announcement": frozenset({"shown", "try_it"}),
    "guidance": frozenset({"technical_opened", "recovery_selected"}),
    "appearance": frozenset({"changed"}),
    "updater": frozenset(
        {
            "download_started",
            "download_completed",
            "handoff",
            "relaunched",
            "failed",
            "repair_started",
            "repair_completed",
        }
    ),
}
DIMENSION_CHOICES: dict[str, frozenset[str]] = {
    "failure_code": FAILURE_CODES,
    "cookie_access": frozenset({"disabled", "browser", "file", "unconfigured"}),
    "provider": frozenset({"youtube", "other"}),
    "encoder_preference": frozenset({"cpu", "nvidia"}),
    "architecture": frozenset({"arm64", "x64", "other"}),
    "update_stage": frozenset(
        {
            "check",
            "download",
            "handoff",
            "waiting_for_exit",
            "downloading_repair",
            "backing_up",
            "verifying",
            "installing",
            "verifying_install",
            "checking_data",
            "relaunching",
            "unknown",
        }
    ),
    "preset": frozenset(
        {"everyday", "streaming", "editing", "sharing", "ctv", "custom", "legacy"}
    ),
    "encoder": frozenset({"cpu", "nvidia", "copy"}),
    "rate_control": frozenset({"cbr", "quality", "copy"}),
    "input_kind": frozenset({"single", "playlist", "url_list", "local"}),
    "resolution": frozenset(
        {"audio", "sd", "720p", "1080p", "1440p", "2160p", "above_2160p"}
    ),
    "source_resolution": frozenset(
        {"audio", "sd", "720p", "1080p", "1440p", "2160p", "above_2160p"}
    ),
    "artwork": frozenset({"none", "thumbnail", "custom"}),
    "metadata": frozenset({"enabled", "disabled"}),
    "outcome": frozenset({"complete", "partial", "failed", "stopped", "skipped"}),
    "duration_bucket": frozenset(
        {"under_10s", "under_1m", "under_5m", "under_30m", "under_2h", "2h_plus"}
    ),
    "processing_bucket": frozenset(
        {"under_10s", "under_1m", "under_5m", "under_30m", "under_2h", "2h_plus"}
    ),
    "wait_bucket": frozenset(
        {"under_10s", "under_1m", "under_5m", "under_30m", "under_2h", "2h_plus"}
    ),
    "size_bucket": frozenset(
        {"under_1mb", "under_10mb", "under_100mb", "under_1gb", "1gb_plus"}
    ),
    "item_count_bucket": frozenset({"1", "2_5", "6_20", "21_100", "101_plus"}),
    "theme": frozenset({"violet", "cobalt", "jade", "ember", "rose", "custom"}),
}


# Explicit projection: unknown/future preferences are excluded until reviewed.
SETTINGS_CHOICES = {
    "local_video_profile": {
        "1080p Standard (Recommended)",
        "2160p 4K",
        "1080p Strict 2 Mbps CBR",
        "720p Compact",
    },
    "manual_crf": {str(value) for value in range(52)},
    "output_type": {"MP4", "MP3", "Original audio"},
    "quality": {
        "Best available up to 4K",
        "2160p / 4K",
        "1440p / 2K",
        "1080p Full HD",
        "720p HD",
        "480p",
        "360p",
    },
    "export_mode": {
        "Everyday",
        "Streaming",
        "Editing",
        "Sharing",
        "Auto CBR",
        "Strict Compliance",
        "Manual Override",
    },
    "manual_audio_codec": {"AAC", "MP3"},
    "manual_sample_rate": {"44100", "48000"},
    "manual_channels": {"Mono", "Stereo"},
    "manual_preset": {"ultrafast", "veryfast", "fast", "medium", "slow"},
    "manual_rate_control": {"CBR", "Quality"},
    "mp3_quality": {
        "Maximum — 320 kbps CBR",
        "High — 256 kbps CBR",
        "Standard — 192 kbps CBR",
        "Compact — 128 kbps CBR",
    },
    "mp3_sample_rate": {"Preserve source", "48 kHz — video / DAW", "44.1 kHz — music"},
    "mp3_channels": {"Preserve source", "Stereo", "Mono"},
    "mp3_cover_art_mode": {"No Art", "YouTube art", "Custom art"},
    "appearance_theme": {
        "Violet",
        "Cobalt",
        "Jade",
        "Ember",
        "Rose",
        "Custom",
        "violet",
        "cobalt",
        "jade",
        "ember",
        "rose",
        "custom",
    },
}
SETTINGS_BOOLEANS = {
    "single_video_only",
    "use_nvenc",
    "embed_thumbnail",
    "write_thumbnail",
    "embed_metadata",
    "write_info_json",
    "mp3_embed_metadata",
}
for _key, _choices in SETTINGS_CHOICES.items():
    DIMENSION_CHOICES["setting_" + _key] = frozenset(_choices)
for _key in SETTINGS_BOOLEANS:
    DIMENSION_CHOICES["setting_" + _key] = frozenset({"enabled", "disabled"})
for _key in ("manual_video_bitrate", "manual_audio_bitrate"):
    DIMENSION_CHOICES["setting_" + _key] = frozenset(
        {
            "under_32",
            "32_127",
            "128_319",
            "320_999",
            "1000_1999",
            "2000_4999",
            "5000_9999",
            "10000_plus",
        }
    )


def settings_dimensions(values: Mapping) -> dict[str, str]:
    result = {}
    for key, choices in SETTINGS_CHOICES.items():
        value = values.get(key)
        if isinstance(value, str) and value in choices:
            result["setting_" + key] = value
    for key in SETTINGS_BOOLEANS:
        value = values.get(key)
        if type(value) is bool:
            result["setting_" + key] = "enabled" if value else "disabled"
    for key in ("manual_video_bitrate", "manual_audio_bitrate"):
        value = values.get(key)
        if type(value) not in (str, int) or not str(value).isdigit():
            continue
        number = int(str(value))
        if not 0 <= number <= 100000:
            continue
        for upper, label in (
            (32, "under_32"),
            (128, "32_127"),
            (320, "128_319"),
            (1000, "320_999"),
            (2000, "1000_1999"),
            (5000, "2000_4999"),
            (10000, "5000_9999"),
            (100001, "10000_plus"),
        ):
            if number < upper:
                result["setting_" + key] = label
                break
    return result


def validate_dimensions(value: Mapping[str, str] | None) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("telemetry dimensions must be an object")
    result = dict(value)
    for key, item in result.items():
        if (
            key not in DIMENSION_CHOICES
            or not isinstance(item, str)
            or item not in DIMENSION_CHOICES[key]
        ):
            raise ValueError("unsupported telemetry dimension")
    return result


def attempt_identifier(install_id: str, run_id: str) -> str:
    """Installation-scoped opaque correlation; never emit the local run key."""
    return str(uuid.uuid5(uuid.UUID(install_id), "vodforge:attempt:" + run_id))


def time_bucket(seconds: float) -> str:
    for upper, label in (
        (10, "under_10s"),
        (60, "under_1m"),
        (300, "under_5m"),
        (1800, "under_30m"),
        (7200, "under_2h"),
    ):
        if seconds < upper:
            return label
    return "2h_plus"


def export_dimensions(job: object) -> dict[str, str]:
    """Configured intent only; actual encoder/output facts belong to completion."""
    mode = getattr(getattr(job, "export_mode", None), "value", "")
    preset = {
        "Auto CBR": "ctv",
        "Manual Override": "custom",
        "Strict Compliance": "legacy",
    }.get(mode, mode.lower())
    result = (
        {"preset": preset}
        if preset in DIMENSION_CHOICES["preset"]
        and getattr(getattr(job, "output_type", None), "value", "") == "MP4"
        else {}
    )
    result["cookie_access"] = (
        "disabled"
        if not getattr(job, "use_cookies", False)
        else "file"
        if getattr(job, "cookie_file", None)
        else "browser"
        if getattr(job, "cookie_browser", None)
        else "unconfigured"
    )
    host = (urlsplit(getattr(job, "url", "")).hostname or "").lower()
    result["provider"] = (
        "youtube"
        if host
        in {
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "youtu.be",
            "music.youtube.com",
        }
        else "other"
    )
    result["encoder_preference"] = (
        "nvidia" if getattr(job, "use_nvenc", False) else "cpu"
    )
    machine = platform.machine().lower()
    result["architecture"] = (
        "arm64"
        if machine in {"arm64", "aarch64"}
        else "x64"
        if machine in {"amd64", "x86_64"}
        else "other"
    )
    result["input_kind"] = (
        "url_list"
        if getattr(job, "batch_mode", False)
        else "single"
        if getattr(job, "single_video_only", True)
        or not parse_qs(urlsplit(getattr(job, "url", "")).query).get("list")
        else "playlist"
    )
    count = max(1, len(getattr(job, "urls", [])))
    result["item_count_bucket"] = (
        "1"
        if count == 1
        else "2_5"
        if count <= 5
        else "6_20"
        if count <= 20
        else "21_100"
        if count <= 100
        else "101_plus"
    )
    if result["input_kind"] == "playlist":
        result.pop("item_count_bucket", None)
    result["metadata"] = (
        "enabled" if getattr(job, "embed_metadata", False) else "disabled"
    )
    mp3 = getattr(job, "mp3_settings", None)
    if (
        getattr(getattr(job, "output_type", None), "value", "") == "MP3"
        and mp3 is not None
    ):
        result["artwork"] = (
            "none"
            if not mp3.embed_cover_art
            else "custom"
            if mp3.custom_cover_art_path
            else "thumbnail"
        )
        result["metadata"] = "enabled" if mp3.embed_metadata else "disabled"
    return result


def resolution_bucket(height: float) -> str:
    for maximum, label in (
        (0, "audio"),
        (576, "sd"),
        (720, "720p"),
        (1080, "1080p"),
        (1440, "1440p"),
        (2160, "2160p"),
    ):
        if height <= maximum:
            return label
    return "above_2160p"


def measured_dimensions(
    probe: Mapping, *, source_height: float | None = None
) -> dict[str, str]:
    """Extract bucketed media facts only from an independently validated probe."""
    result: dict[str, str] = {}
    streams = probe.get("streams", [])
    videos = [
        stream
        for stream in streams
        if stream.get("codec_type") == "video"
        and not stream.get("disposition", {}).get("attached_pic")
    ]
    result["resolution"] = (
        resolution_bucket(float(videos[0].get("height", 0))) if videos else "audio"
    )
    if source_height is not None:
        result["source_resolution"] = resolution_bucket(source_height)
    fmt = probe.get("format", {})
    try:
        result["duration_bucket"] = time_bucket(float(fmt["duration"]))
    except (KeyError, ValueError, TypeError):
        pass
    try:
        size = float(fmt["size"])
        result["size_bucket"] = next(
            (
                label
                for maximum, label in (
                    (1048576, "under_1mb"),
                    (10485760, "under_10mb"),
                    (104857600, "under_100mb"),
                    (1073741824, "under_1gb"),
                )
                if size < maximum
            ),
            "1gb_plus",
        )
    except (KeyError, ValueError, TypeError):
        pass
    return result


def committed_export_dimensions(
    job, plan, probe, *, source_height=None
) -> dict[str, str]:
    """Successful command selection and probe facts; no media labels or paths."""
    from .models import ExportPlan, OutputType

    result = {
        **export_dimensions(job),
        **measured_dimensions(probe, source_height=source_height),
    }
    result.pop("item_count_bucket", None)
    result["encoder"] = (
        "nvidia"
        if isinstance(plan, ExportPlan)
        and job.use_nvenc
        and (plan.video_crf is None or plan.nvenc_cq is not None)
        else "cpu"
    )
    result["rate_control"] = (
        "quality"
        if isinstance(plan, ExportPlan) and plan.video_crf is not None
        else "cbr"
    )
    if job.output_type == OutputType.ORIGINAL:
        result.update(encoder="copy", rate_control="copy")
    return result
