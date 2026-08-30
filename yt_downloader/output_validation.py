from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import AudioExportPlan, ExportPlan, ManualAudioCodec, OutputType


@dataclass(frozen=True)
class _ProbeView:
    fmt: dict[str, Any]
    streams: tuple[dict[str, Any], ...]
    video: dict[str, Any]
    audio: dict[str, Any]
    video_streams: tuple[dict[str, Any], ...]
    audio_streams: tuple[dict[str, Any], ...]
    container_tokens: frozenset[str]


def _probe_view(probe_data: dict[str, Any]) -> _ProbeView:
    streams = tuple(
        stream for stream in probe_data.get("streams") or [] if isinstance(stream, dict)
    )
    raw_format = probe_data.get("format")
    fmt: dict[str, Any] = raw_format if isinstance(raw_format, dict) else {}
    video_streams = tuple(
        stream for stream in streams if stream.get("codec_type") == "video"
    )
    audio_streams = tuple(
        stream for stream in streams if stream.get("codec_type") == "audio"
    )
    video = next(
        (
            stream
            for stream in video_streams
            if not int((stream.get("disposition") or {}).get("attached_pic") or 0)
        ),
        {},
    )
    audio = audio_streams[0] if audio_streams else {}
    container_tokens = frozenset(
        token.strip().lower()
        for token in str(fmt.get("format_name") or "").split(",")
        if token.strip()
    )
    return _ProbeView(
        fmt=fmt,
        streams=streams,
        video=video,
        audio=audio,
        video_streams=video_streams,
        audio_streams=audio_streams,
        container_tokens=container_tokens,
    )


def _close_numeric(
    actual: Any,
    expected: Any,
    *,
    relative: float = 0.10,
) -> bool:
    try:
        actual_number = float(actual)
        expected_number = float(expected)
    except (TypeError, ValueError):
        return False
    return abs(actual_number - expected_number) <= max(
        1.0,
        abs(expected_number) * relative,
    )


def _exact_numeric(actual: Any, expected: Any) -> bool:
    try:
        return float(actual) == float(expected)
    except (TypeError, ValueError):
        return False


def _stream_kbps(
    view: _ProbeView,
    stream: dict[str, Any],
    *,
    allow_format_fallback: bool = False,
) -> float | None:
    value = stream.get("bit_rate")
    if (value is None or value == "") and allow_format_fallback:
        value = view.fmt.get("bit_rate")
    if value is None or value == "":
        return None
    try:
        return float(value) / 1000.0
    except (TypeError, ValueError):
        return None


def _normalized_format_tags(view: _ProbeView) -> dict[str, str]:
    raw_tags = view.fmt.get("tags")
    tags = raw_tags if isinstance(raw_tags, dict) else {}
    return {str(key).casefold(): str(value) for key, value in tags.items()}


def _artwork_contract_mismatches(
    view: _ProbeView,
    *,
    embed_cover_art: bool | None,
) -> list[str]:
    attached_art = any(
        int((stream.get("disposition") or {}).get("attached_pic") or 0)
        for stream in view.video_streams
    )
    if embed_cover_art is None or attached_art == embed_cover_art:
        return []
    if embed_cover_art:
        return ["the requested embedded artwork is missing"]
    return ["the output contains unexpected embedded artwork"]


def _metadata_presence_mismatches(
    normalized_tags: dict[str, str],
    *,
    embed_metadata: bool | None,
) -> list[str]:
    user_metadata_keys = {
        "title",
        "artist",
        "album",
        "album_artist",
        "comment",
        "description",
        "synopsis",
        "keywords",
    }
    has_user_metadata = any(
        key in user_metadata_keys and value.strip()
        for key, value in normalized_tags.items()
    )
    if embed_metadata is True and not has_user_metadata:
        return ["the requested embedded metadata is missing"]
    if embed_metadata is False and has_user_metadata:
        return ["the output contains unexpected embedded metadata"]
    return []


def _keyword_contract_mismatches(
    normalized_tags: dict[str, str],
    *,
    embed_metadata: bool | None,
    expected_tags: list[str] | None,
) -> list[str]:
    requested_tags = [
        tag.strip().casefold()
        for tag in (expected_tags or [])
        if embed_metadata is True and tag.strip()
    ]
    if not requested_tags:
        return []
    stored_keywords = {
        tag.strip().casefold()
        for tag in normalized_tags.get("keywords", "").split(",")
        if tag.strip()
    }
    missing_tags = [tag for tag in requested_tags if tag not in stored_keywords]
    if not missing_tags:
        return []
    return [
        "the embedded keywords are missing requested tags: " + ", ".join(missing_tags)
    ]


def _embedding_contract_mismatches(
    view: _ProbeView,
    *,
    embed_metadata: bool | None,
    embed_cover_art: bool | None,
    expected_tags: list[str] | None,
) -> list[str]:
    normalized_tags = _normalized_format_tags(view)
    return [
        *_artwork_contract_mismatches(
            view,
            embed_cover_art=embed_cover_art,
        ),
        *_metadata_presence_mismatches(
            normalized_tags,
            embed_metadata=embed_metadata,
        ),
        *_keyword_contract_mismatches(
            normalized_tags,
            embed_metadata=embed_metadata,
            expected_tags=expected_tags,
        ),
    ]


def _audio_plan_mismatches(
    view: _ProbeView,
    plan: AudioExportPlan,
    summary: dict[str, Any],
    *,
    require_sidecar: bool,
) -> list[str]:
    mismatches: list[str] = []
    if require_sidecar and str(summary.get("Output rate-control mode") or "") != "CBR":
        mismatches.append("the saved audio rate-control mode is not CBR")
    if (
        require_sidecar
        and str(summary.get("Target audio bitrate") or "")
        != f"{plan.audio_bitrate_kbps} kbps"
    ):
        mismatches.append("the saved target audio bitrate does not match")
    if str(view.audio.get("codec_name") or "").lower() != "mp3":
        mismatches.append("the output audio codec is not MP3")
    measured_kbps = _stream_kbps(
        view,
        view.audio,
        allow_format_fallback=True,
    )
    if measured_kbps is None or not _close_numeric(
        measured_kbps,
        plan.audio_bitrate_kbps,
        relative=0.12,
    ):
        mismatches.append(
            f"the measured audio bitrate does not match {plan.audio_bitrate_kbps} kbps"
        )
    if plan.output_sample_rate and not _exact_numeric(
        view.audio.get("sample_rate"),
        plan.output_sample_rate,
    ):
        mismatches.append(
            f"the audio sample rate does not match {plan.output_sample_rate} Hz"
        )
    if plan.output_channels and not _exact_numeric(
        view.audio.get("channels"),
        plan.output_channels,
    ):
        mismatches.append(
            f"the audio channel count does not match {plan.output_channels}"
        )
    return mismatches


def _mp4_audio_bitrate_matches(
    measured_audio_kbps: float | None,
    plan: ExportPlan,
) -> bool:
    if measured_audio_kbps is None:
        return False
    if plan.output_audio_codec is ManualAudioCodec.MP3:
        return _close_numeric(
            measured_audio_kbps,
            plan.audio_bitrate_kbps,
            relative=0.18,
        )
    # FFmpeg's native AAC encoder treats -b:a as a target rather than a
    # constant-rate guarantee. Low-complexity audio can legitimately measure
    # near half that target, while a grossly wrong encode still fails closed.
    target_kbps = float(plan.audio_bitrate_kbps)
    return target_kbps * 0.40 <= measured_audio_kbps <= target_kbps * 1.25


def _video_sidecar_target_mismatches(
    plan: ExportPlan,
    summary: dict[str, Any],
    *,
    require_sidecar: bool,
) -> list[str]:
    mismatches: list[str] = []
    if (
        require_sidecar
        and str(summary.get("Output rate-control mode") or "") != plan.mode.value
    ):
        mismatches.append("the saved video rate-control mode does not match")
    if (
        require_sidecar
        and str(summary.get("Target video bitrate") or "")
        != f"{plan.video_bitrate_kbps} kbps"
    ):
        mismatches.append("the saved target video bitrate does not match")
    if (
        require_sidecar
        and str(summary.get("Target audio bitrate") or "")
        != f"{plan.audio_bitrate_kbps} kbps"
    ):
        mismatches.append("the saved target audio bitrate does not match")
    return mismatches


def _video_codec_profile_mismatches(
    view: _ProbeView,
    plan: ExportPlan,
    summary: dict[str, Any],
    *,
    require_sidecar: bool,
) -> list[str]:
    mismatches: list[str] = []
    if str(view.video.get("codec_name") or "").lower() != "h264":
        mismatches.append("the output video codec is not H.264")
    if (
        str(view.audio.get("codec_name") or "").lower()
        != plan.output_audio_codec.ffprobe_codec
    ):
        mismatches.append(
            f"the output audio codec is not {plan.output_audio_codec.ffprobe_codec.upper()}"
        )
    if require_sidecar:
        expected_audio_label = (
            "AAC"
            if plan.output_audio_codec is ManualAudioCodec.AAC
            else "MP3 (libmp3lame)"
        )
        saved_audio_label = str(summary.get("Output audio codec") or "")
        if saved_audio_label and saved_audio_label.casefold() not in {
            expected_audio_label.casefold(),
            plan.output_audio_codec.ffprobe_codec.casefold(),
        }:
            mismatches.append("the saved output audio codec does not match")
    if str(view.video.get("pix_fmt") or "").lower() != "yuv420p":
        mismatches.append("the output pixel format is not yuv420p")
    if str(view.video.get("profile") or "").casefold() != "high":
        mismatches.append("the output H.264 profile is not High")
    return mismatches


def _video_geometry_mismatches(
    view: _ProbeView,
    plan: ExportPlan,
) -> list[str]:
    mismatches: list[str] = []
    if plan.output_width and int(view.video.get("width") or 0) != int(
        plan.output_width
    ):
        mismatches.append(f"the output width does not match {plan.output_width}")
    if plan.output_height and int(view.video.get("height") or 0) != int(
        plan.output_height
    ):
        mismatches.append(f"the output height does not match {plan.output_height}")
    return mismatches


def _video_rate_and_audio_shape_mismatches(
    view: _ProbeView,
    plan: ExportPlan,
) -> list[str]:
    mismatches: list[str] = []
    measured_video_kbps = _stream_kbps(view, view.video)
    if measured_video_kbps is None or not _close_numeric(
        measured_video_kbps,
        plan.video_bitrate_kbps,
        relative=0.18,
    ):
        mismatches.append(
            f"the measured video bitrate does not match {plan.video_bitrate_kbps} kbps"
        )
    measured_audio_kbps = _stream_kbps(view, view.audio)
    if not _mp4_audio_bitrate_matches(measured_audio_kbps, plan):
        mismatches.append(
            f"the measured audio bitrate does not match {plan.audio_bitrate_kbps} kbps"
        )
    if plan.audio_sample_rate and not _exact_numeric(
        view.audio.get("sample_rate"),
        plan.audio_sample_rate,
    ):
        mismatches.append(
            f"the audio sample rate does not match {plan.audio_sample_rate} Hz"
        )
    if plan.audio_channels and not _exact_numeric(
        view.audio.get("channels"),
        plan.audio_channels,
    ):
        mismatches.append(
            f"the audio channel count does not match {plan.audio_channels}"
        )
    return mismatches


def _video_plan_mismatches(
    view: _ProbeView,
    plan: ExportPlan,
    summary: dict[str, Any],
    *,
    require_sidecar: bool,
) -> list[str]:
    return [
        *_video_sidecar_target_mismatches(
            plan,
            summary,
            require_sidecar=require_sidecar,
        ),
        *_video_codec_profile_mismatches(
            view,
            plan,
            summary,
            require_sidecar=require_sidecar,
        ),
        *_video_geometry_mismatches(view, plan),
        *_video_rate_and_audio_shape_mismatches(view, plan),
    ]


def output_artifact_plan_mismatches(
    probe_data: dict[str, Any],
    plan: ExportPlan | AudioExportPlan,
    *,
    embed_metadata: bool | None = None,
    embed_cover_art: bool | None = None,
    expected_tags: list[str] | None = None,
    sidecar_summary: dict[str, Any] | None = None,
    require_sidecar: bool = False,
) -> list[str]:
    """Return concrete reasons an artifact does not satisfy its export contract.

    The resolved plan contains source-selected dimensions and encoder targets,
    so comparing against it enforces the actual encoder contract without
    assuming every source can reach the quality ceiling requested in the UI.
    Audio plans also own their metadata and cover-art choices. MP4 plans do not,
    so callers provide those optional expectations from the corresponding job.
    """
    view = _probe_view(probe_data)
    if isinstance(plan, AudioExportPlan):
        embed_metadata = plan.embed_metadata
        embed_cover_art = plan.embed_cover_art

    mismatches = _embedding_contract_mismatches(
        view,
        embed_metadata=embed_metadata,
        embed_cover_art=embed_cover_art,
        expected_tags=expected_tags,
    )
    if require_sidecar and not isinstance(sidecar_summary, dict):
        mismatches.append("the VODForge output contract is missing")
    summary = sidecar_summary if isinstance(sidecar_summary, dict) else {}
    if isinstance(plan, AudioExportPlan):
        mismatches.extend(
            _audio_plan_mismatches(
                view,
                plan,
                summary,
                require_sidecar=require_sidecar,
            )
        )
    else:
        mismatches.extend(
            _video_plan_mismatches(
                view,
                plan,
                summary,
                require_sidecar=require_sidecar,
            )
        )
    return mismatches


def _load_probe_data(
    path: Path,
    ffprobe: str,
    *,
    probe_reader: Callable[..., dict[str, Any]],
    ffprobe_data: dict[str, Any] | None,
    control_check: Any | None,
) -> dict[str, Any]:
    try:
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError("the output file is missing or empty")
    except OSError as exc:
        raise RuntimeError(f"the output file could not be read: {exc}") from exc

    try:
        data = (
            ffprobe_data
            if ffprobe_data is not None
            else probe_reader(ffprobe, path, control_check=control_check)
        )
    except Exception as exc:
        raise RuntimeError(f"ffprobe could not validate the output: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(  # noqa: TRY004 - artifact validation has one failure API
            "ffprobe returned malformed output metadata"
        )
    return data


def _validate_duration(
    view: _ProbeView,
    expected_duration_seconds: float | None,
) -> None:
    try:
        duration = float(view.fmt.get("duration") or 0)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("the output duration is missing or invalid") from exc
    if duration <= 0:
        raise RuntimeError("the output duration is missing or zero")
    if expected_duration_seconds and expected_duration_seconds > 0:
        tolerance = max(2.0, expected_duration_seconds * 0.02)
        if duration + tolerance < expected_duration_seconds:
            raise RuntimeError(
                f"the output is truncated ({duration:.2f}s versus "
                f"{expected_duration_seconds:.2f}s expected)"
            )


def _validate_mp3_structure(
    view: _ProbeView,
    plan: ExportPlan | AudioExportPlan | None,
) -> None:
    if isinstance(plan, ExportPlan):
        raise RuntimeError(  # noqa: TRY004 - artifact validation has one failure API
            "the MP3 output was validated against an incompatible MP4 export plan"
        )
    if "mp3" not in view.container_tokens:
        container = ",".join(sorted(view.container_tokens)) or "unknown"
        raise RuntimeError(f"the output container is not MP3 ({container})")
    if not any(
        str(stream.get("codec_name") or "").lower() == "mp3"
        for stream in view.audio_streams
    ):
        raise RuntimeError("the MP3 output does not contain a valid MP3 audio stream")


def _validate_mp4_structure(
    view: _ProbeView,
    plan: ExportPlan | AudioExportPlan | None,
    *,
    require_audio: bool,
    expected_audio_codec: str,
) -> None:
    if isinstance(plan, AudioExportPlan):
        raise RuntimeError(  # noqa: TRY004 - artifact validation has one failure API
            "the MP4 output was validated against an incompatible audio export plan"
        )
    if not ({"mp4", "mov"} & view.container_tokens):
        container = ",".join(sorted(view.container_tokens)) or "unknown"
        raise RuntimeError(f"the output container is not MP4 ({container})")
    if not any(
        str(stream.get("codec_name") or "").lower() == "h264"
        for stream in view.video_streams
    ):
        raise RuntimeError(
            "the MP4 output does not contain the required H.264 video stream"
        )
    expected_codec = (
        plan.output_audio_codec.ffprobe_codec
        if isinstance(plan, ExportPlan)
        else str(expected_audio_codec or "aac").strip().lower()
    )
    if require_audio and not any(
        str(stream.get("codec_name") or "").lower() == expected_codec
        for stream in view.audio_streams
    ):
        raise RuntimeError(
            f"the MP4 output does not contain the required {expected_codec.upper()} audio stream"
        )


def _raise_plan_mismatches(
    label: str,
    data: dict[str, Any],
    plan: ExportPlan | AudioExportPlan,
    *,
    embed_metadata: bool | None,
    embed_cover_art: bool | None,
    expected_tags: list[str] | None,
) -> None:
    mismatches = output_artifact_plan_mismatches(
        data,
        plan,
        embed_metadata=embed_metadata,
        embed_cover_art=embed_cover_art,
        expected_tags=expected_tags,
    )
    if mismatches:
        raise RuntimeError(
            f"the {label} output does not match its export plan: "
            + "; ".join(mismatches)
        )


def validate_output_artifact(
    path: Path,
    output_type: OutputType,
    ffprobe: str,
    *,
    probe_reader: Callable[..., dict[str, Any]],
    expected_duration_seconds: float | None = None,
    require_audio: bool = True,
    expected_audio_codec: str = "aac",
    plan: ExportPlan | AudioExportPlan | None = None,
    embed_metadata: bool | None = None,
    embed_cover_art: bool | None = None,
    expected_tags: list[str] | None = None,
    ffprobe_data: dict[str, Any] | None = None,
    control_check: Any | None = None,
) -> dict[str, Any]:
    """Fail closed unless a final artifact has the required streams and duration."""
    data = _load_probe_data(
        path,
        ffprobe,
        probe_reader=probe_reader,
        ffprobe_data=ffprobe_data,
        control_check=control_check,
    )
    view = _probe_view(data)
    _validate_duration(view, expected_duration_seconds)

    if output_type == OutputType.MP3:
        _validate_mp3_structure(view, plan)
        if plan is not None:
            _raise_plan_mismatches(
                "MP3",
                data,
                plan,
                embed_metadata=embed_metadata,
                embed_cover_art=embed_cover_art,
                expected_tags=expected_tags,
            )
        return data

    _validate_mp4_structure(
        view,
        plan,
        require_audio=require_audio,
        expected_audio_codec=expected_audio_codec,
    )
    if plan is not None:
        _raise_plan_mismatches(
            "MP4",
            data,
            plan,
            embed_metadata=embed_metadata,
            embed_cover_art=embed_cover_art,
            expected_tags=expected_tags,
        )
    return data
