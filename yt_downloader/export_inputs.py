"""UI-independent validation for Forge's manual and MP3 export choices."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .models import (
    AUDIO_SAMPLE_RATE,
    STRICT_AUDIO_BITRATE_KBPS,
    STRICT_VIDEO_BITRATE_KBPS,
    ManualAudioCodec,
    ManualExportSettings,
    Mp3ExportSettings,
)

MP3_IN_MP4_BITRATES_KBPS = (
    32,
    40,
    48,
    56,
    64,
    80,
    96,
    112,
    128,
    160,
    192,
    224,
    256,
    320,
)
MP3_QUALITY_OPTIONS = {
    "Maximum — 320 kbps CBR": 320,
    "High — 256 kbps CBR": 256,
    "Standard — 192 kbps CBR": 192,
    "Compact — 128 kbps CBR": 128,
}
MP3_SAMPLE_RATE_OPTIONS = {
    "Preserve source": None,
    "48 kHz — video / DAW": "48000",
    "44.1 kHz — music": "44100",
}
MP3_CHANNEL_OPTIONS = {"Preserve source": None, "Stereo": "2", "Mono": "1"}
MP3_COVER_ART_OPTIONS = ("No Art", "YouTube art", "Custom art")


def _choice(values: Mapping[str, Any], key: str, default: str) -> str:
    value = values.get(key)
    return str(value).strip() if value is not None else default


def _positive_int(value: Any, label: str, low: int, high: int) -> int:
    try:
        parsed = int(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"{label} must be a whole number.") from exc
    if parsed < low or parsed > high:
        unit = "" if label == "Video quality CRF" else " kbps"
        raise ValueError(f"{label} must be between {low} and {high}{unit}.")
    return parsed


def manual_export_settings(values: Mapping[str, Any]) -> ManualExportSettings:
    """Validate one manual profile before creating a durable DownloadJob."""
    rate_control = _choice(values, "manual_rate_control", "CBR")
    if rate_control not in {"CBR", "Quality"}:
        raise ValueError("Choose CBR or Quality rate control.")
    codec = ManualAudioCodec(_choice(values, "manual_audio_codec", "AAC"))
    bitrate = _positive_int(
        values.get("manual_audio_bitrate", STRICT_AUDIO_BITRATE_KBPS),
        "Manual audio bitrate",
        32,
        1024,
    )
    if codec is ManualAudioCodec.MP3 and bitrate not in MP3_IN_MP4_BITRATES_KBPS:
        choices = ", ".join(str(value) for value in MP3_IN_MP4_BITRATES_KBPS)
        raise ValueError(
            "MP3 audio bitrate must be one of the encoder-supported values: "
            f"{choices} kbps."
        )
    sample_rate = _choice(values, "manual_sample_rate", AUDIO_SAMPLE_RATE)
    if sample_rate not in {"44100", "48000"}:
        raise ValueError("Choose 44.1 or 48 kHz manual audio sample rate.")
    channels = _choice(values, "manual_channels", "Stereo")
    if channels not in {"Mono", "Stereo"}:
        raise ValueError("Choose Mono or Stereo manual audio channels.")
    preset = _choice(values, "manual_preset", "medium")
    if preset not in {"ultrafast", "veryfast", "fast", "medium", "slow"}:
        raise ValueError("Choose a valid x264 encoder preset.")
    return ManualExportSettings(
        video_bitrate_kbps=_positive_int(
            values.get("manual_video_bitrate", STRICT_VIDEO_BITRATE_KBPS),
            "Manual video bitrate",
            100,
            100000,
        )
        if rate_control == "CBR"
        else STRICT_VIDEO_BITRATE_KBPS,
        audio_bitrate_kbps=bitrate,
        audio_sample_rate=sample_rate,
        audio_channels="1" if channels == "Mono" else "2",
        audio_codec=codec,
        x264_preset=preset,
        video_crf=_positive_int(
            values.get("manual_crf", 21), "Video quality CRF", 1, 51
        )
        if rate_control == "Quality"
        else None,
    )


def mp3_export_settings(
    values: Mapping[str, Any],
    *,
    custom_cover_path: Path | None = None,
    validate_cover: Callable[[Path], Path] | None = None,
) -> Mp3ExportSettings:
    """Validate MP3 choices; custom artwork must pass the existing validator."""
    quality = _choice(values, "mp3_quality", "Maximum — 320 kbps CBR")
    sample_rate = _choice(values, "mp3_sample_rate", "Preserve source")
    channels = _choice(values, "mp3_channels", "Preserve source")
    cover_mode = _choice(values, "mp3_cover_art_mode", "No Art")
    if quality not in MP3_QUALITY_OPTIONS:
        raise ValueError("Choose a valid MP3 quality setting.")
    if sample_rate not in MP3_SAMPLE_RATE_OPTIONS:
        raise ValueError("Choose a valid MP3 sample-rate setting.")
    if channels not in MP3_CHANNEL_OPTIONS:
        raise ValueError("Choose a valid MP3 channel setting.")
    if cover_mode not in MP3_COVER_ART_OPTIONS:
        raise ValueError("Choose a valid MP3 cover-art setting.")
    cover: Path | None = None
    if cover_mode == "Custom art":
        if custom_cover_path is None:
            raise ValueError("Choose a custom cover image or select No Art.")
        if validate_cover is None:
            raise ValueError("Custom cover art validation is unavailable.")
        cover = validate_cover(custom_cover_path)
    embed_metadata = values.get("mp3_embed_metadata", True)
    if not isinstance(embed_metadata, bool):
        raise TypeError("Choose a valid MP3 metadata setting.")
    return Mp3ExportSettings(
        bitrate_kbps=MP3_QUALITY_OPTIONS[quality],
        sample_rate=MP3_SAMPLE_RATE_OPTIONS[sample_rate],
        channels=MP3_CHANNEL_OPTIONS[channels],
        embed_metadata=embed_metadata,
        embed_cover_art=cover_mode == "YouTube art",
        custom_cover_art_path=cover,
    )
