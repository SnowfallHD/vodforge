"""Bounded product vocabulary. Never pass user content to this module.

Feature owners report facts; ProductTelemetryOwner owns consent, identity and
transport. This vocabulary is shared by producers, validation and QA inventories.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from urllib.parse import parse_qs, urlsplit

FEATURE_ACTIONS: dict[str, frozenset[str]] = {
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
