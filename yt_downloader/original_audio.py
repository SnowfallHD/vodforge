"""Original audio selection and stream-copy contract, without encode controls."""

from dataclasses import replace
from typing import Any

from .export_planning import build_mp3_export_plan
from .models import AudioExportPlan, Mp3ExportSettings, OutputType


def original_audio_extension(codec: str) -> str:
    if codec.lower() == "opus":
        return ".opus"
    if codec.lower().startswith(("mp4a", "aac")):
        return ".m4a"
    raise RuntimeError("No supported original Opus or AAC audio stream is available.")


def build_original_audio_plan(info: dict[str, Any]) -> AudioExportPlan:
    formats = [
        fmt
        for fmt in info.get("formats") or []
        if isinstance(fmt, dict)
        and str(fmt.get("acodec", "")).lower().startswith(("opus", "mp4a", "aac"))
        and fmt.get("vcodec") == "none"
    ]
    plan = build_mp3_export_plan(
        {**info, "formats": formats},
        Mp3ExportSettings(embed_metadata=False, embed_cover_art=False),
    )
    return replace(
        plan,
        output_type=OutputType.ORIGINAL,
        output_extension=original_audio_extension(plan.audio_codec),
        audio_bitrate_kbps=round(plan.source_audio_kbps),
        warnings=[],
        summary="Preserve the original audio stream without re-encoding.",
    )


def original_audio_options(selector: str | None) -> dict[str, Any]:
    if not selector:
        raise RuntimeError("Original audio requires an analyzed source format.")
    return {
        "format": selector,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "best"}],
        "postprocessor_args": {},
        "writethumbnail": False,
    }
