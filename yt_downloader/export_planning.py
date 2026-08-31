from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .models import (
    STRICT_AUDIO_BITRATE_KBPS,
    STRICT_VIDEO_BITRATE_KBPS,
    AudioExportPlan,
    ExportMode,
    ExportPlan,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)

DEFAULT_MAX_HEIGHT = 1080
CLEAN_BITRATE_STEPS = [
    1000,
    1200,
    1500,
    2000,
    2500,
    3000,
    4000,
    5000,
    6000,
    8000,
    10000,
    12000,
    14000,
    24000,
    45000,
    68000,
]
VIDEO_MINIMUMS_KBPS = {
    480: 1000,
    720: 1500,
    1080: 2000,
    1440: 6000,
    2160: 12000,
}
VIDEO_CAPS_KBPS = {
    (480, 30): 2500,
    (720, 30): 5000,
    (1080, 30): 10000,
    (1080, 60): 14000,
    (1440, 30): 24000,
    (2160, 30): 45000,
    (2160, 60): 68000,
}


def _format_selector(max_height: int) -> str:
    # Always request video + best available audio. Do not fall back to video-only
    # unless a future explicit video-only mode is added.
    return (
        f"bestvideo[height<={max_height}][ext=mp4]+bestaudio/"
        f"bestvideo[height<={max_height}]+bestaudio/"
        f"best[height<={max_height}][ext=mp4][acodec!=none]/"
        f"best[height<={max_height}][acodec!=none]"
    )


QUALITY_OPTIONS = {
    "Best available up to 4K": _format_selector(2160),
    "2160p / 4K": _format_selector(2160),
    "1440p / 2K": _format_selector(1440),
    "1080p Full HD": _format_selector(1080),
    "720p HD": _format_selector(720),
    "480p": _format_selector(480),
    "360p": _format_selector(360),
}


def export_mode_display_name(mode: ExportMode | str) -> str:
    """Return the user-facing selector label without changing stored mode values."""
    parsed = mode if isinstance(mode, ExportMode) else ExportMode(mode)
    if parsed == ExportMode.AUTO_CBR:
        return "Auto CBR (Recommended)"
    return parsed.value


def export_mode_from_display_name(value: ExportMode | str) -> ExportMode:
    """Resolve a selector label back to the canonical persisted export mode."""
    if isinstance(value, ExportMode):
        return value
    text = str(value).strip()
    for mode in ExportMode:
        if text in {mode.value, export_mode_display_name(mode)}:
            return mode
    raise ValueError(f"Unsupported MP4 output mode: {value!r}")


def export_mode_description(mode: ExportMode | str) -> str:
    """Explain each MP4 rate-control choice in direct, source-aware language."""
    parsed = export_mode_from_display_name(mode)
    if parsed == ExportMode.AUTO_CBR:
        return (
            "Recommended. Chooses a bitrate for each video from its source quality and resolution, "
            "so a larger file is not created when a higher bitrate would not help."
        )
    if parsed == ExportMode.STRICT_COMPLIANCE:
        return (
            "Uses the same 10 Mbps video and 320 kbps audio delivery profile for every MP4. "
            "It cannot add detail missing from the YouTube source."
        )
    return "Uses the exact video bitrate, audio codec, audio bitrate, and encoding speed you choose below."


EXPORT_MODES = [export_mode_display_name(mode) for mode in ExportMode]


def mp3_sample_rate_display(
    sample_rate: str | int | None,
    *,
    source_label: str,
) -> str:
    if sample_rate is None or sample_rate == "":
        return source_label
    try:
        return f"{int(sample_rate) / 1000:g} kHz"
    except (TypeError, ValueError):
        return str(sample_rate)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _source_numeric_text(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return text
    return text if math.isfinite(number) else None


def _is_none_codec(value: Any) -> bool:
    text = str(value or "").lower()
    return not text or text == "none"


def video_codec_multiplier(vcodec: Any) -> float:
    codec = str(vcodec or "").lower()
    if codec.startswith(("avc", "h264")):
        return 1.0
    if codec.startswith(("vp9", "vp09")):
        return 1.5
    if codec.startswith(("av01", "av1")):
        return 1.8
    if codec.startswith(("hev", "h265", "hvc1")):
        return 1.6
    return 1.0


def audio_codec_multiplier(acodec: Any) -> float:
    codec = str(acodec or "").lower()
    if codec.startswith("mp4a") or "aac" in codec:
        return 1.0
    if "opus" in codec:
        return 1.3
    if "vorbis" in codec:
        return 1.0
    if "mp3" in codec:
        return 0.85
    return 1.0


def _format_video_kbps(fmt: dict[str, Any]) -> float:
    return (
        _num(fmt.get("vbr"))
        or _num(fmt.get("tbr"))
        or (_num(fmt.get("filesize")) * 8 / 1000 / max(_num(fmt.get("duration")), 1))
    )


def _format_audio_kbps(fmt: dict[str, Any]) -> float:
    return _num(fmt.get("abr")) or _num(fmt.get("tbr"))


def _resolution_bucket(height: int | None) -> int:
    if not height:
        return 480
    if height <= 480:
        return 480
    if height <= 720:
        return 720
    if height <= 1080:
        return 1080
    if height <= 1440:
        return 1440
    return 2160


def _fps_bucket(fps: float | None) -> int:
    return 60 if (fps or 0) > 30 else 30


def _round_clean_bitrate(value: float) -> int:
    if value <= 0:
        return CLEAN_BITRATE_STEPS[0]
    return min(CLEAN_BITRATE_STEPS, key=lambda step: (abs(step - value), step))


def _clamp(value: float, low: int, high: int) -> float:
    return max(low, min(high, value))


def _resolution_minimum_kbps(height: int | None) -> int:
    return VIDEO_MINIMUMS_KBPS[_resolution_bucket(height)]


def _resolution_cap_kbps(height: int | None, fps: float | None) -> int:
    bucket = _resolution_bucket(height)
    fps_bucket = _fps_bucket(fps)
    return (
        VIDEO_CAPS_KBPS.get((bucket, fps_bucket))
        or VIDEO_CAPS_KBPS.get((bucket, 30))
        or 10000
    )


def _transcode_headroom(vcodec: Any) -> float:
    codec = str(vcodec or "").lower()
    if codec.startswith(("avc", "h264")):
        return 1.25
    if codec.startswith(("vp9", "vp09", "av01", "av1", "hev", "h265", "hvc1")):
        return 1.4
    return 1.3


def _is_hdr_format(fmt: dict[str, Any]) -> bool:
    dynamic_range = str(fmt.get("dynamic_range") or "").upper()
    color_transfer = str(fmt.get("color_transfer") or "").lower()
    return (
        dynamic_range not in {"", "SDR"}
        or "smpte2084" in color_transfer
        or "arib" in color_transfer
    )


def _is_single_file_http_transport(fmt: dict[str, Any]) -> bool:
    return str(fmt.get("protocol") or "").strip().lower() in {"http", "https"}


def choose_best_video_format(
    formats: list[dict[str, Any]], max_height: int = DEFAULT_MAX_HEIGHT
) -> dict[str, Any] | None:
    """Select the best video-only format, with progressively relaxed filters.

    Some YouTube videos only expose a limited set of formats (e.g. when no JS
    runtime is available, the player returns fewer streams).  The original
    strict filter (video-only, SDR, known-bitrate, ≤120fps, ≤max_height)
    would reject every format for those videos and raise "No usable SDR video
    source."  We now try the strict pass first, then relax each constraint
    one at a time so we can still download whatever *is* available.
    """

    def _select(
        *,
        allow_progressive: bool = False,
        allow_hdr: bool = False,
        allow_unknown_bitrate: bool = False,
        allow_high_fps: bool = False,
    ) -> dict[str, Any] | None:
        candidates = []
        for fmt in formats:
            height = fmt.get("height")
            if not isinstance(height, int) or height <= 0 or height > max_height:
                continue
            if _is_none_codec(fmt.get("vcodec")):
                continue
            if not allow_progressive and not _is_none_codec(fmt.get("acodec")):
                continue
            if not allow_hdr and _is_hdr_format(fmt):
                continue
            kbps = _format_video_kbps(fmt)
            if not allow_unknown_bitrate and kbps <= 0:
                continue
            fps = _num(fmt.get("fps"), 30.0)
            if not allow_high_fps and (fps <= 0 or fps > 120):
                continue
            effective = (
                kbps * video_codec_multiplier(fmt.get("vcodec")) if kbps > 0 else 1.0
            )
            # Prefer direct https downloads over HLS/m3u8 streams (which download
            # as hundreds of fragments and are much slower for large videos).
            is_direct = _is_single_file_http_transport(fmt)
            candidates.append(
                (
                    height,
                    effective,
                    kbps or 1.0,
                    fmt.get("ext") == "mp4",
                    str(fmt.get("vcodec") or "").startswith("avc"),
                    is_direct,
                    fmt,
                )
            )
        if not candidates:
            return None
        target_height = (
            1080
            if any(item[0] == 1080 for item in candidates) and max_height >= 1080
            else max(item[0] for item in candidates)
        )
        same_res = [item for item in candidates if item[0] == target_height]
        best_effective = max(item[1] for item in same_res)
        close = [item for item in same_res if item[1] >= best_effective * 0.85]
        # Prefer a single-file HTTP source only inside the quality-equivalent
        # window the selector already permits. Never trade a materially better
        # HLS source for throughput.
        direct_close = [item for item in close if item[5]]
        if direct_close:
            close = direct_close
        # Sort: avc codec first, then effective bitrate, then raw, then ext
        return max(close, key=lambda item: (item[4], item[1], item[2], item[3]))[6]

    # Pass 1: strict (video-only, SDR, known-bitrate, ≤120fps)
    result = _select()
    if result:
        return result
    # Pass 2: allow unknown bitrate
    result = _select(allow_unknown_bitrate=True)
    if result:
        return result
    # Pass 3: allow HDR
    result = _select(allow_unknown_bitrate=True, allow_hdr=True)
    if result:
        return result
    # Pass 4: allow high fps (>120, some streams report odd values)
    result = _select(allow_unknown_bitrate=True, allow_hdr=True, allow_high_fps=True)
    return result


def choose_best_progressive_format(
    formats: list[dict[str, Any]], max_height: int = DEFAULT_MAX_HEIGHT
) -> dict[str, Any] | None:
    candidates = []
    for fmt in formats:
        height = fmt.get("height")
        if not isinstance(height, int) or height <= 0 or height > max_height:
            continue
        if _is_none_codec(fmt.get("vcodec")) or _is_none_codec(fmt.get("acodec")):
            continue
        if _is_hdr_format(fmt):
            continue
        kbps = _format_video_kbps(fmt)
        if kbps <= 0:
            continue
        fps = _num(fmt.get("fps"), 30.0)
        if fps <= 0 or fps > 120:
            continue
        audio_kbps = _format_audio_kbps(fmt)
        if audio_kbps <= 0:
            continue
        effective = kbps * video_codec_multiplier(fmt.get("vcodec"))
        candidates.append(
            (
                height,
                effective,
                kbps,
                fmt.get("ext") == "mp4",
                str(fmt.get("vcodec") or "").startswith("avc"),
                fmt,
            )
        )
    if not candidates:
        return None
    target_height = (
        1080
        if any(item[0] == 1080 for item in candidates) and max_height >= 1080
        else max(item[0] for item in candidates)
    )
    same_res = [item for item in candidates if item[0] == target_height]
    best_effective = max(item[1] for item in same_res)
    close = [item for item in same_res if item[1] >= best_effective * 0.85]
    return max(close, key=lambda item: (item[4], item[1], item[2], item[3]))[5]


def choose_best_audio_format(
    formats: list[dict[str, Any]], *, prefer_quality: bool = False
) -> dict[str, Any] | None:
    def _select(allow_unknown_bitrate: bool = False) -> dict[str, Any] | None:
        candidates = []
        for fmt in formats:
            if not _is_none_codec(fmt.get("vcodec")):
                continue
            if _is_none_codec(fmt.get("acodec")):
                continue
            kbps = _format_audio_kbps(fmt)
            if not allow_unknown_bitrate and kbps <= 0:
                continue
            channels = int(_num(fmt.get("audio_channels") or fmt.get("channels"), 2))
            sample_rate = int(_num(fmt.get("asr"), 0))
            effective = (kbps or 1.0) * audio_codec_multiplier(fmt.get("acodec"))
            is_direct = _is_single_file_http_transport(fmt)
            candidates.append(
                (
                    effective,
                    channels >= 2,
                    sample_rate >= 48000,
                    fmt.get("ext") in {"m4a", "mp4", "webm"},
                    is_direct,
                    fmt,
                )
            )
        if not candidates:
            return None
        if prefer_quality:
            return max(
                candidates,
                key=lambda item: (item[0], item[1], item[2], item[4], item[3]),
            )[5]
        best_effective = max(item[0] for item in candidates)
        close = [item for item in candidates if item[0] >= best_effective * 0.85]
        direct_close = [item for item in close if item[4]]
        if direct_close:
            close = direct_close
        return max(close, key=lambda item: (item[0], item[1], item[2], item[3]))[5]

    result = _select()
    if result:
        return result
    return _select(allow_unknown_bitrate=True)


def choose_audio_bitrate_kbps(effective_audio_kbps: float) -> int:
    if effective_audio_kbps < 96:
        return 128
    if effective_audio_kbps < 140:
        return 160
    if effective_audio_kbps < 200:
        return 192
    if effective_audio_kbps < 260:
        return 256
    return 320


def build_mp3_export_plan(
    info: dict[str, Any], settings: Mp3ExportSettings | None = None
) -> AudioExportPlan:
    """Select the best audio source and describe a deliberate MP3 encode."""
    settings = settings or Mp3ExportSettings()
    formats = [fmt for fmt in info.get("formats") or [] if isinstance(fmt, dict)]
    audio = choose_best_audio_format(formats, prefer_quality=True)
    if audio is None:
        candidates = [fmt for fmt in formats if not _is_none_codec(fmt.get("acodec"))]
        if candidates:
            audio = max(
                candidates,
                key=lambda fmt: (
                    _format_audio_kbps(fmt) * audio_codec_multiplier(fmt.get("acodec")),
                    int(_num(fmt.get("audio_channels") or fmt.get("channels"), 0)),
                    int(_num(fmt.get("asr"), 0)),
                    str(fmt.get("protocol") or "").startswith("http"),
                ),
            )
    if audio is None:
        raise RuntimeError(
            "No usable audio source was found for this URL. The video may be private, region-restricted, "
            "or temporarily limited by YouTube. Check the diagnostics log or retry with cookies."
        )
    audio_id = str(audio.get("format_id") or "").strip()
    if not audio_id:
        raise RuntimeError(
            "VODForge could not identify the selected YouTube audio format."
        )
    source_audio_kbps = _format_audio_kbps(audio)
    effective_audio_kbps = source_audio_kbps * audio_codec_multiplier(
        audio.get("acodec")
    )
    source_sample_rate = _source_numeric_text(audio.get("asr"))
    source_channels_value = audio.get("audio_channels") or audio.get("channels")
    source_channels = _source_numeric_text(source_channels_value)
    quality_note = (
        "The 320 kbps setting minimizes additional MP3 encoding loss"
        if settings.bitrate_kbps == 320
        else f"The {settings.bitrate_kbps} kbps setting trades fidelity for a smaller file"
    )
    warnings = [
        f"YouTube audio is already compressed. {quality_note} but cannot restore detail absent from the source."
    ]
    return AudioExportPlan(
        output_type=OutputType.MP3,
        audio_format_id=audio_id,
        format_selector=audio_id,
        source_audio_kbps=source_audio_kbps,
        effective_audio_kbps=effective_audio_kbps,
        audio_bitrate_kbps=settings.bitrate_kbps,
        source_sample_rate=source_sample_rate,
        output_sample_rate=settings.sample_rate,
        source_channels=source_channels,
        output_channels=settings.channels,
        audio_codec=str(audio.get("acodec") or "unknown"),
        embed_metadata=settings.embed_metadata,
        embed_cover_art=bool(
            settings.custom_cover_art_path or settings.embed_cover_art
        ),
        cover_art_source=(
            "Custom image"
            if settings.custom_cover_art_path is not None
            else "YouTube thumbnail"
            if settings.embed_cover_art
            else "None (no art)"
        ),
        warnings=warnings,
        summary=(
            f"Selected the highest-quality available audio source and will create a {settings.bitrate_kbps} kbps CBR MP3"
            f" at {settings.sample_rate or 'the source sample rate'} with {settings.channels or 'the source channel layout'}."
        ),
    )


def calculate_auto_video_bitrate_kbps(video_fmt: dict[str, Any]) -> int:
    height = (
        video_fmt.get("height") if isinstance(video_fmt.get("height"), int) else None
    )
    fps = _num(video_fmt.get("fps"), 30.0)
    source_kbps = _format_video_kbps(video_fmt)
    effective = source_kbps * video_codec_multiplier(video_fmt.get("vcodec"))
    estimate = effective * _transcode_headroom(video_fmt.get("vcodec"))
    value = _clamp(
        estimate, _resolution_minimum_kbps(height), _resolution_cap_kbps(height, fps)
    )
    rounded = _round_clean_bitrate(value)
    return int(
        _clamp(
            rounded, _resolution_minimum_kbps(height), _resolution_cap_kbps(height, fps)
        )
    )


def _bitrate_warning(target_kbps: float, effective_source_kbps: float) -> str | None:
    if effective_source_kbps <= 0:
        return "Selected source has no reliable bitrate metadata. Output is source-limited until verified."
    ratio = target_kbps / effective_source_kbps
    if ratio <= 1.25:
        return "Target bitrate is close to the selected source."
    if ratio <= 2:
        return "Target bitrate is higher than the source. This can reduce additional encoding loss or satisfy platform requirements, but it will not create new source detail."
    if ratio <= 5:
        return "Target bitrate is much higher than the source. Output may be platform-compatible, but quality is source-limited."
    return "Source-limited encode. The output bitrate is far above the selected source quality. The file may satisfy platform requirements, but it will not become true high-bitrate quality."


@dataclass(frozen=True)
class _AutoSourceSelection:
    video: dict[str, Any]
    audio: dict[str, Any] | None
    video_id: str | None
    audio_id: str | None
    selector: str


@dataclass(frozen=True)
class _AutoQualityEvidence:
    height: int | None
    effective_video_kbps: float
    effective_audio_kbps: float


@dataclass(frozen=True)
class _AutoEncodeTargets:
    video_bitrate_kbps: int
    audio_bitrate_kbps: int
    warnings: tuple[str, ...]


def _choose_auto_video_source(
    formats: list[dict[str, Any]], max_height: int
) -> tuple[dict[str, Any] | None, bool]:
    video = choose_best_video_format(formats, max_height=max_height)
    if video is not None:
        return video, False

    video = choose_best_progressive_format(formats, max_height=max_height)
    if video is not None:
        return video, True

    # Last resort: pick *any* format with a video codec, ignoring all quality filters.
    video = next(
        (fmt for fmt in formats if not _is_none_codec(fmt.get("vcodec"))),
        None,
    )
    progressive = bool(video and not _is_none_codec(video.get("acodec")))
    return video, progressive


def _choose_auto_audio_source(
    formats: list[dict[str, Any]],
    video: dict[str, Any],
    using_progressive_av: bool,
) -> dict[str, Any] | None:
    if using_progressive_av:
        return video

    audio = choose_best_audio_format(formats)
    if audio is not None:
        return audio

    # Last resort: pick any audio-only format, ignoring bitrate filters.
    return next(
        (
            fmt
            for fmt in formats
            if _is_none_codec(fmt.get("vcodec"))
            and not _is_none_codec(fmt.get("acodec"))
        ),
        None,
    )


def _auto_format_selector(
    video_id: str | None,
    audio_id: str | None,
    using_progressive_av: bool,
) -> str:
    if using_progressive_av and video_id:
        return video_id
    if video_id and audio_id:
        return f"{video_id}+{audio_id}"
    raise RuntimeError(
        "VODForge could not build a safe video+audio selector from yt-dlp formats."
    )


def _select_auto_sources(
    formats: list[dict[str, Any]], max_height: int
) -> _AutoSourceSelection:
    video, using_progressive_av = _choose_auto_video_source(formats, max_height)
    if video is None:
        raise RuntimeError(
            "No usable video source was found for this URL. This can happen when:\n"
            "• The video is private, members-only, or region-restricted.\n"
            "• No JavaScript runtime (Deno 2.x) is installed, limiting available formats.\n"
            "• YouTube is rate-limiting the connection (retry later or use cookies).\n"
            "Check the diagnostics log for yt-dlp's detailed format list."
        )

    audio = _choose_auto_audio_source(formats, video, using_progressive_av)
    if audio is None and not using_progressive_av:
        raise RuntimeError(
            "No usable audio source was found for this URL. This can happen when "
            "yt-dlp returns limited formats without a JavaScript runtime (Deno 2.x). "
            "Check the diagnostics log for details."
        )

    video_id = str(video.get("format_id") or "") or None
    audio_id = str(audio.get("format_id") or "") if audio else None
    selector = _auto_format_selector(video_id, audio_id, using_progressive_av)
    return _AutoSourceSelection(
        video=video,
        audio=audio,
        video_id=video_id,
        audio_id=audio_id,
        selector=selector,
    )


def _auto_target_bitrates(
    mode: ExportMode,
    video: dict[str, Any],
    audio: dict[str, Any] | None,
    effective_audio_kbps: float,
) -> tuple[int, int]:
    if mode in {ExportMode.STRICT_COMPLIANCE, ExportMode.MANUAL_OVERRIDE}:
        return STRICT_VIDEO_BITRATE_KBPS, STRICT_AUDIO_BITRATE_KBPS
    return (
        calculate_auto_video_bitrate_kbps(video),
        choose_audio_bitrate_kbps(effective_audio_kbps) if audio else 160,
    )


def _derive_auto_encode_targets(
    *,
    mode: ExportMode,
    selection: _AutoSourceSelection,
    max_height: int,
    evidence: _AutoQualityEvidence,
) -> _AutoEncodeTargets:
    video_bitrate, audio_bitrate = _auto_target_bitrates(
        mode,
        selection.video,
        selection.audio,
        evidence.effective_audio_kbps,
    )
    warnings: list[str] = []
    if max_height >= 1080 and evidence.height != 1080:
        warnings.append(
            "This video is not available in 1080p. VODForge will export the best available lower-resolution version."
        )
    if mode == ExportMode.STRICT_COMPLIANCE:
        if evidence.height and evidence.height < 1080:
            warnings.append(
                "Strict Compliance uses high-bitrate output settings, but the selected source is below 1080p. This will not create true 1080p detail."
            )
        if (
            evidence.effective_video_kbps
            and video_bitrate / evidence.effective_video_kbps > 2
        ):
            warnings.append(
                "Strict Compliance target is far above the selected source quality. The output may satisfy platform requirements, but it will not become true high-bitrate quality."
            )
    warn = _bitrate_warning(video_bitrate, evidence.effective_video_kbps)
    if warn and warn not in warnings:
        warnings.append(warn)
    if (
        evidence.effective_audio_kbps
        and audio_bitrate / evidence.effective_audio_kbps > 2
    ):
        warnings.append(
            "Audio target is much higher than the source. This may satisfy the output profile, but it will not restore lost audio quality."
        )
    return _AutoEncodeTargets(
        video_bitrate_kbps=video_bitrate,
        audio_bitrate_kbps=audio_bitrate,
        warnings=tuple(warnings),
    )


def _auto_plan_summary(
    mode: ExportMode,
    height: int | None,
    video_bitrate_kbps: int,
    audio_bitrate_kbps: int,
) -> str:
    if mode == ExportMode.STRICT_COMPLIANCE:
        return f"Strict Compliance selected the best practical {height or 'unknown'}p source and will export fixed H.264 CBR {video_bitrate_kbps / 1000:g} Mbps + AAC {audio_bitrate_kbps} kbps."
    if mode == ExportMode.MANUAL_OVERRIDE:
        return f"Manual Override selected the best practical {height or 'unknown'}p source; user-selected encode settings will be applied before transcode."
    if height == 1080:
        return f"Auto mode selected a true 1080p source and recommends {video_bitrate_kbps / 1000:g} Mbps CBR based on source quality and the platform's 1080p minimum."
    return f"Auto mode selected the best available {height or 'unknown'}p source and will export at that truthful resolution."


def build_auto_export_plan(
    info: dict[str, Any],
    mode: ExportMode | str = ExportMode.AUTO_CBR,
    max_height: int = DEFAULT_MAX_HEIGHT,
) -> ExportPlan:
    mode = ExportMode(mode)
    formats = [fmt for fmt in info.get("formats") or [] if isinstance(fmt, dict)]
    selection = _select_auto_sources(formats, max_height)
    video = selection.video
    audio = selection.audio
    source_video_kbps = _format_video_kbps(video)
    effective_video_kbps = source_video_kbps * video_codec_multiplier(
        video.get("vcodec")
    )
    source_audio_kbps = _format_audio_kbps(audio or {})
    effective_audio_kbps = source_audio_kbps * audio_codec_multiplier(
        (audio or {}).get("acodec")
    )
    height = video.get("height") if isinstance(video.get("height"), int) else None
    width = video.get("width") if isinstance(video.get("width"), int) else None
    fps = _num(video.get("fps"), 30.0)
    evidence = _AutoQualityEvidence(
        height=height,
        effective_video_kbps=effective_video_kbps,
        effective_audio_kbps=effective_audio_kbps,
    )
    targets = _derive_auto_encode_targets(
        mode=mode,
        selection=selection,
        max_height=max_height,
        evidence=evidence,
    )
    summary = _auto_plan_summary(
        mode,
        height,
        targets.video_bitrate_kbps,
        targets.audio_bitrate_kbps,
    )
    return ExportPlan(
        mode=mode,
        video_format_id=selection.video_id,
        audio_format_id=selection.audio_id,
        format_selector=selection.selector,
        output_width=width,
        output_height=height,
        source_video_kbps=source_video_kbps,
        effective_video_kbps=effective_video_kbps,
        video_bitrate_kbps=targets.video_bitrate_kbps,
        source_audio_kbps=source_audio_kbps,
        effective_audio_kbps=effective_audio_kbps,
        audio_bitrate_kbps=targets.audio_bitrate_kbps,
        fps=fps,
        video_codec=str(video.get("vcodec") or "unknown"),
        audio_codec=str((audio or {}).get("acodec") or "unknown"),
        warnings=list(targets.warnings),
        summary=summary,
    )


def apply_manual_export_settings(
    plan: ExportPlan, settings: ManualExportSettings
) -> ExportPlan:
    """Return a source-selection plan with explicit user-selected encode settings."""
    return ExportPlan(
        mode=ExportMode.MANUAL_OVERRIDE,
        video_format_id=plan.video_format_id,
        audio_format_id=plan.audio_format_id,
        format_selector=plan.format_selector,
        output_width=plan.output_width,
        output_height=plan.output_height,
        source_video_kbps=plan.source_video_kbps,
        effective_video_kbps=plan.effective_video_kbps,
        video_bitrate_kbps=settings.video_bitrate_kbps,
        source_audio_kbps=plan.source_audio_kbps,
        effective_audio_kbps=plan.effective_audio_kbps,
        audio_bitrate_kbps=settings.audio_bitrate_kbps,
        audio_sample_rate=settings.audio_sample_rate,
        audio_channels=settings.audio_channels,
        output_audio_codec=settings.audio_codec,
        x264_preset=settings.x264_preset,
        fps=plan.fps,
        video_codec=plan.video_codec,
        audio_codec=plan.audio_codec,
        warnings=list(plan.warnings),
        summary=(
            f"Manual Override will export H.264 CBR {settings.video_bitrate_kbps / 1000:g} Mbps "
            f"+ {settings.audio_codec.value} {settings.audio_bitrate_kbps} kbps, {settings.audio_sample_rate} Hz, "
            f"{settings.audio_channels} channel(s)."
        ),
    )
