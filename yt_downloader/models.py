from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

AUDIO_SAMPLE_RATE = "48000"
AUDIO_CHANNELS = "2"
STRICT_VIDEO_BITRATE_KBPS = 10000
STRICT_AUDIO_BITRATE_KBPS = 320


class OutputType(str, Enum):
    MP4 = "MP4"
    MP3 = "MP3"


class CookieSource(str, Enum):
    PUBLIC = "Public"
    FILE = "cookies.txt"
    BROWSER = "Browser"


class ExportMode(str, Enum):
    AUTO_CBR = "Auto CBR"
    STRICT_COMPLIANCE = "Strict Compliance"
    MANUAL_OVERRIDE = "Manual Override"


class ManualAudioCodec(str, Enum):
    AAC = "AAC"
    MP3 = "MP3"

    @property
    def ffmpeg_encoder(self) -> str:
        return "aac" if self is ManualAudioCodec.AAC else "libmp3lame"

    @property
    def ffprobe_codec(self) -> str:
        return "aac" if self is ManualAudioCodec.AAC else "mp3"


@dataclass(frozen=True)
class ExportPlan:
    mode: ExportMode
    video_format_id: str | None
    audio_format_id: str | None
    format_selector: str
    output_width: int | None
    output_height: int | None
    source_video_kbps: float
    effective_video_kbps: float
    video_bitrate_kbps: int
    source_audio_kbps: float
    effective_audio_kbps: float
    audio_bitrate_kbps: int
    audio_sample_rate: str = AUDIO_SAMPLE_RATE
    audio_channels: str = AUDIO_CHANNELS
    output_audio_codec: ManualAudioCodec = ManualAudioCodec.AAC
    x264_preset: str = "medium"
    fps: float | None = None
    video_codec: str = "unknown"
    audio_codec: str = "unknown"
    warnings: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass(frozen=True)
class Mp3ExportSettings:
    bitrate_kbps: int = 320
    sample_rate: str | None = None
    channels: str | None = None
    embed_metadata: bool = True
    embed_cover_art: bool = False
    custom_cover_art_path: Path | None = None


@dataclass(frozen=True)
class AudioExportPlan:
    output_type: OutputType
    audio_format_id: str
    format_selector: str
    source_audio_kbps: float
    effective_audio_kbps: float
    audio_bitrate_kbps: int
    source_sample_rate: str | None
    output_sample_rate: str | None
    source_channels: str | None
    output_channels: str | None
    audio_codec: str
    embed_metadata: bool
    embed_cover_art: bool
    cover_art_source: str
    warnings: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass(frozen=True)
class ManualExportSettings:
    video_bitrate_kbps: int = STRICT_VIDEO_BITRATE_KBPS
    audio_bitrate_kbps: int = STRICT_AUDIO_BITRATE_KBPS
    audio_sample_rate: str = AUDIO_SAMPLE_RATE
    audio_channels: str = AUDIO_CHANNELS
    audio_codec: ManualAudioCodec = ManualAudioCodec.AAC
    x264_preset: str = "medium"


@dataclass
class DownloadJob:
    url: str
    output_dir: Path
    output_type: OutputType
    quality_label: str
    export_mode: ExportMode
    manual_settings: ManualExportSettings
    mp3_settings: Mp3ExportSettings
    single_video_only: bool
    use_nvenc: bool
    embed_thumbnail: bool
    write_thumbnail: bool
    embed_metadata: bool
    write_info_json: bool
    tags: list[str]
    urls: list[str] = field(default_factory=list)
    use_cookies: bool = False
    cookie_file: Path | None = None
    cookie_browser: str | None = None
    batch_mode: bool = False
    preview_info: dict[str, Any] | None = None
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    origin_run_id: str | None = None
    metadata_keys: set[tuple[str, str]] = field(default_factory=set)
    history_identities: set[tuple[str, str, str]] = field(default_factory=set)
    preview_thumbnail_image: Any | None = field(default=None, repr=False)
    activity_lines: list[str] = field(default_factory=list, repr=False)
    terminal_status: str | None = None
    terminal_message: str = ""
    item_terminal_emitted: bool = False


@dataclass(frozen=True)
class DownloadOutcome:
    success_count: int = 0
    failure_count: int = 0
    skipped_count: int = 0
    sidecar_failure_count: int = 0

    def combined_with(self, other: DownloadOutcome) -> DownloadOutcome:
        return DownloadOutcome(
            success_count=self.success_count + other.success_count,
            failure_count=self.failure_count + other.failure_count,
            skipped_count=self.skipped_count + other.skipped_count,
            sidecar_failure_count=self.sidecar_failure_count
            + other.sidecar_failure_count,
        )
