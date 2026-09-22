"""Readable Library facts projected from recorded metadata, never inferred files."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from .encoding_summary import SUMMARY_COMPARISON_ROWS


def saved_file_path(row: Mapping[str, Any]) -> str:
    summary = row.get("vodforge_encoding_summary") or {}
    output = summary.get("output") or {}
    return str(row.get("vodforge_output_path") or output.get("Output file path") or "")


def readable_date(value: Any) -> str:
    from datetime import datetime, timezone

    text = str(value or "")
    for pattern in ("%Y%m%d", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return (
                datetime.strptime(text[:19] if "T" in pattern else text, pattern)
                .replace(tzinfo=timezone.utc)
                .strftime("%b %d, %Y")
            )
        except ValueError:
            pass
    return text or "Not recorded"


def library_detail_facts(
    row: Mapping[str, Any],
) -> tuple[tuple[tuple[str, str, str], ...], tuple[tuple[str, str, str], ...]]:
    summary = row.get("vodforge_encoding_summary") or {}
    source, output = summary.get("source") or {}, summary.get("output") or {}
    path = saved_file_path(row)
    filename = (
        (PureWindowsPath(path) if "\\" in path else PurePosixPath(path)).name
        if path
        else "Not recorded"
    )
    output_type = str(
        row.get("vodforge_output_type")
        or output.get("Output container")
        or "Not recorded"
    )
    source_resolution = source.get("Source resolution")
    if not source_resolution and row.get("width") and row.get("height"):
        source_resolution = f"{row['width']} × {row['height']}"
    source_fields = (
        (
            "Channel",
            str(row.get("channel") or row.get("uploader") or "Local media"),
            "channels",
        ),
        ("Playlist", str(row.get("playlist_title") or "No playlist"), "list"),
        (
            "Source URL",
            str(
                row.get("webpage_url")
                or row.get("original_url")
                or "Imported local file"
            ),
            "link",
        ),
        ("Original Title", str(row.get("title") or "Untitled media"), "file"),
        ("Source Resolution", str(source_resolution or "Not recorded"), "monitor"),
        ("Upload Date", readable_date(row.get("upload_date")), "calendar"),
    )
    output_fields = (
        ("Saved Filename", filename, "file"),
        ("File Format", output_type, "film"),
        (
            "Output Resolution",
            str(
                output.get("Output resolution")
                or (
                    "Audio only"
                    if output_type.casefold()
                    in {"mp3", "m4a", "opus", "original audio"}
                    else "Not recorded"
                )
            ),
            "monitor",
        ),
        (
            "File Size",
            str(
                output.get("Output file size")
                or output.get("File size")
                or "Not recorded"
            ),
            "drive",
        ),
        (
            "Saved Location",
            str(row.get("vodforge_output_dir") or "Not recorded"),
            "folder",
        ),
    )
    source_extra = []
    output_extra = []
    # The same authoritative comparison schema as Forge and Activity. Output
    # measured rates never fall back to a requested target or provider bitrate.
    for label, source_key, output_key in SUMMARY_COMPARISON_ROWS:
        icon = "audio" if "audio" in label.lower() else "film"
        if label not in {"Resolution"}:
            source_label = {
                "HDR/SDR or pixel format": "Dynamic range",
                "Effective/target video bitrate": "Effective video bitrate",
                "Effective/target audio bitrate": "Effective audio bitrate",
                "Selection/status": "Selection reason",
            }.get(label, label)
            source_value = source.get(source_key)
            if (
                source_key == "Effective AAC-equivalent audio bitrate"
                and output_type.casefold() == "mp3"
            ):
                source_value = (
                    source.get("Effective MP3-equivalent audio bitrate") or source_value
                )
            source_extra.append(
                (source_label, str(source_value or "Not recorded"), icon)
            )
        if output_key and label not in {"Resolution", "File size", "Container/ext"}:
            output_label = {
                "HDR/SDR or pixel format": "Pixel format",
                "Selection/status": "Validation",
            }.get(label, label)
            if output_key in {"Target audio bitrate", "Target video bitrate"}:
                output_label = output_key
            value = output.get(output_key)
            if not value and output_key in {
                "Measured video bitrate",
                "Measured audio bitrate",
            }:
                value = output.get(output_key.replace("Measured", "Output"))
            output_extra.append((output_label, str(value or "Not recorded"), icon))
    for label, key in (
        ("Output status", "Output status"),
        ("File path", "Output file path"),
        ("Rate control", "Output rate-control mode"),
        ("Duration", "Output duration"),
        ("H.264 profile", "H.264 profile"),
        ("Embedded metadata", "Embedded ID3 metadata"),
        ("Cover art", "Embedded cover art"),
        ("Failure reason", "Failure reason"),
    ):
        value = output.get(key)
        if value or key in {"Output status", "Output duration", "Output file path"}:
            output_extra.append((label, str(value or "Not recorded"), "file"))
    warnings = summary.get("warnings")
    if isinstance(warnings, (list, tuple)) and warnings:
        output_extra.append(("Warnings", ", ".join(str(v) for v in warnings), "file"))
    return source_fields + tuple(source_extra), output_fields + tuple(output_extra)
