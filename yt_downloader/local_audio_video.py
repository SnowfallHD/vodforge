from __future__ import annotations

import json
import math
import os
import queue
import re
import subprocess  # nosec B404 - fixed local FFmpeg/FFprobe argv only
import threading
import uuid
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from .history import application_data_dir
from .models import OutputType
from .output_validation import validate_output_artifact
from .platform_services import hidden_window_subprocess_kwargs
from .process_lifecycle import (
    ActiveChildProcessRegistry,
    process_command,
    terminate_recorded_children,
)
from .safe_output import (
    cleanup_abandoned_staging_transactions,
    cleanup_private_staging_directory,
    commit_file_beneath,
    create_private_staging_directory,
)

LOCAL_CONVERSION_STATE_SCHEMA = 1
LOCAL_VIDEO_WIDTH = 1920
LOCAL_VIDEO_HEIGHT = 1080
LOCAL_VIDEO_FPS = 30
LOCAL_VIDEO_GOP_SECONDS = 2
LOCAL_VIDEO_GOP_FRAMES = LOCAL_VIDEO_FPS * LOCAL_VIDEO_GOP_SECONDS
LOCAL_AUDIO_BITRATE_KBPS = 192
MAX_LOCAL_IMAGE_BYTES = 50 * 1024 * 1024
MAX_LOCAL_IMAGE_PIXELS = 40_000_000
_WINDOWS_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class LocalAudioVideoError(RuntimeError):
    """Raised when a local audio-to-video transaction cannot finish safely."""


class LocalAudioVideoCancelled(LocalAudioVideoError):
    """Raised when the user or application stops a local conversion."""


class LocalVideoProfile(str, Enum):
    """Stable user-facing profiles for a still-image video transaction."""

    STANDARD = "1080p Standard (Recommended)"
    UHD = "2160p 4K"
    STRICT_CBR = "1080p Strict 2 Mbps CBR"
    COMPACT = "720p Compact"


LOCAL_VIDEO_PROFILE_OPTIONS = tuple(profile.value for profile in LocalVideoProfile)


@dataclass(frozen=True, slots=True)
class LocalVideoProfileSpec:
    width: int
    height: int
    crf: int | None
    video_bitrate_kbps: int | None
    audio_bitrate_kbps: int
    label: str
    description: str

    @property
    def rate_control_label(self) -> str:
        return (
            "Strict CBR" if self.video_bitrate_kbps is not None else "Constant quality"
        )

    @property
    def target_video_bitrate_label(self) -> str:
        if self.video_bitrate_kbps is None:
            return "Still-image optimized"
        return f"{self.video_bitrate_kbps} kbps"


def local_video_profile_spec(profile: LocalVideoProfile | str) -> LocalVideoProfileSpec:
    """Resolve one immutable profile without consulting live application settings."""

    selected = LocalVideoProfile(profile)
    if selected is LocalVideoProfile.UHD:
        return LocalVideoProfileSpec(
            width=3840,
            height=2160,
            crf=18,
            video_bitrate_kbps=None,
            audio_bitrate_kbps=192,
            label="2160p • 4K",
            description=(
                "High-quality 4K output with streaming-friendly two-second "
                "keyframes. Smaller artwork is upscaled but gains no new detail."
            ),
        )
    if selected is LocalVideoProfile.STRICT_CBR:
        return LocalVideoProfileSpec(
            width=1920,
            height=1080,
            crf=None,
            video_bitrate_kbps=2000,
            audio_bitrate_kbps=192,
            label="1080p • Strict 2 Mbps CBR",
            description=(
                "For delivery systems that explicitly require constant bitrate. "
                "This creates a much larger file without improving a still image."
            ),
        )
    if selected is LocalVideoProfile.COMPACT:
        return LocalVideoProfileSpec(
            width=1280,
            height=720,
            crf=20,
            video_bitrate_kbps=None,
            audio_bitrate_kbps=160,
            label="720p • Compact",
            description=(
                "A smaller 720p file for ordinary sharing, with the same "
                "streaming-friendly two-second keyframes."
            ),
        )
    return LocalVideoProfileSpec(
        width=LOCAL_VIDEO_WIDTH,
        height=LOCAL_VIDEO_HEIGHT,
        crf=18,
        video_bitrate_kbps=None,
        audio_bitrate_kbps=LOCAL_AUDIO_BITRATE_KBPS,
        label="1080p • Standard",
        description=(
            "High-quality 1080p with efficient still-image compression and "
            "streaming-friendly two-second keyframes."
        ),
    )


@dataclass(frozen=True)
class LocalAudioVideoRequest:
    audio_path: Path
    image_path: Path
    output_dir: Path
    run_id: str
    profile: LocalVideoProfile = LocalVideoProfile.STANDARD


@dataclass(frozen=True)
class LocalAudioVideoProgress:
    fraction: float
    label: str


@dataclass(frozen=True)
class LocalAudioVideoResult:
    output_path: Path
    image_path: Path
    history_metadata: Mapping[str, Any]


def local_conversion_state_path(**kwargs: Any) -> Path:
    return application_data_dir(**kwargs) / "local-conversion-state.json"


def new_local_audio_video_request(
    audio_path: Path,
    image_path: Path,
    output_dir: Path,
    *,
    profile: LocalVideoProfile | str = LocalVideoProfile.STANDARD,
) -> LocalAudioVideoRequest:
    return LocalAudioVideoRequest(
        audio_path=Path(audio_path),
        image_path=Path(image_path),
        output_dir=Path(output_dir),
        run_id=uuid.uuid4().hex,
        profile=LocalVideoProfile(profile),
    )


def local_video_filename(audio_path: Path) -> str:
    stem = _WINDOWS_UNSAFE_FILENAME.sub("_", Path(audio_path).stem)
    stem = " ".join(stem.strip(" .").split()) or "Audio video"
    if stem.upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }:
        stem = f"{stem}_video"
    return f"{stem[:180].rstrip(' .')}.mp4"


def build_local_audio_video_command(
    ffmpeg: str,
    *,
    audio_path: Path,
    image_path: Path,
    output_path: Path,
    profile: LocalVideoProfile | str = LocalVideoProfile.STANDARD,
) -> list[str]:
    """Build one offline, shell-free static-image MP4 encode."""

    spec = local_video_profile_spec(profile)
    rate_control = (
        ["-crf", str(spec.crf)]
        if spec.crf is not None
        else [
            "-b:v",
            f"{spec.video_bitrate_kbps}k",
            "-minrate",
            f"{spec.video_bitrate_kbps}k",
            "-maxrate",
            f"{spec.video_bitrate_kbps}k",
            "-bufsize",
            f"{int(spec.video_bitrate_kbps or 0) * 2}k",
            "-x264-params",
            "nal-hrd=cbr:force-cfr=1",
        ]
    )
    return [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-loop",
        "1",
        "-framerate",
        str(LOCAL_VIDEO_FPS),
        "-i",
        str(image_path),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-map_metadata",
        "1",
        "-vf",
        (
            f"scale={spec.width}:{spec.height}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={spec.width}:{spec.height}:"
            "(ow-iw)/2:(oh-ih)/2,setsar=1"
        ),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-tune",
        "stillimage",
        *rate_control,
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-r",
        str(LOCAL_VIDEO_FPS),
        "-g",
        str(LOCAL_VIDEO_GOP_FRAMES),
        "-keyint_min",
        str(LOCAL_VIDEO_GOP_FRAMES),
        "-sc_threshold",
        "0",
        "-flags",
        "+cgop",
        "-c:a",
        "aac",
        "-b:a",
        f"{spec.audio_bitrate_kbps}k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-shortest",
        "-movflags",
        "+faststart",
        "-progress",
        "pipe:1",
        "-nostats",
        "-y",
        str(output_path),
    ]


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _stream(probe: Mapping[str, Any], kind: str) -> Mapping[str, Any]:
    streams = probe.get("streams")
    if not isinstance(streams, list):
        return {}
    return next(
        (
            item
            for item in streams
            if isinstance(item, dict) and item.get("codec_type") == kind
        ),
        {},
    )


def _format_kbps(value: Any) -> str:
    number = _finite_number(value)
    return f"{number / 1000:.0f} kbps" if number and number > 0 else "Not available"


def _format_size(value: Any) -> str:
    number = _finite_number(value)
    if number is None or number < 0:
        return "Not available"
    if number >= 1024**3:
        return f"{number / 1024**3:.2f} GB"
    if number >= 1024**2:
        return f"{number / 1024**2:.1f} MB"
    return f"{number / 1024:.1f} KB"


def _clean_metadata_text(value: Any, fallback: str) -> str:
    text = str(value or "").replace("\x00", " ").replace("\r", " ")
    text = " ".join(text.split())[:500]
    return text or fallback


def build_local_audio_video_history_metadata(
    request: LocalAudioVideoRequest,
    *,
    output_path: Path,
    input_probe: Mapping[str, Any],
    output_probe: Mapping[str, Any],
) -> dict[str, Any]:
    spec = local_video_profile_spec(request.profile)
    input_format = input_probe.get("format")
    input_format = input_format if isinstance(input_format, dict) else {}
    output_format = output_probe.get("format")
    output_format = output_format if isinstance(output_format, dict) else {}
    input_tags = input_format.get("tags")
    input_tags = input_tags if isinstance(input_tags, dict) else {}
    source_audio = _stream(input_probe, "audio")
    output_video = _stream(output_probe, "video")
    output_audio = _stream(output_probe, "audio")
    title = _clean_metadata_text(input_tags.get("title"), request.audio_path.stem)
    creator = _clean_metadata_text(
        input_tags.get("artist") or input_tags.get("album_artist"),
        "Local audio",
    )
    duration = _finite_number(output_format.get("duration")) or _finite_number(
        input_format.get("duration")
    )
    output_summary = {
        "Output status": "Final Output",
        "Output file path": str(output_path),
        "Output container": "mp4",
        "Output resolution": (
            f"{output_video.get('width')}x{output_video.get('height')}"
            if output_video.get("width") and output_video.get("height")
            else f"{spec.width}x{spec.height}"
        ),
        "Output frame rate": str(
            output_video.get("avg_frame_rate")
            or output_video.get("r_frame_rate")
            or LOCAL_VIDEO_FPS
        ),
        "Output video codec": str(output_video.get("codec_name") or "h264"),
        "Output rate-control mode": spec.rate_control_label,
        "Target video bitrate": spec.target_video_bitrate_label,
        "Measured video bitrate": _format_kbps(output_video.get("bit_rate")),
        "Pixel format": str(output_video.get("pix_fmt") or "yuv420p"),
        "H.264 profile": str(output_video.get("profile") or "High"),
        "Output audio codec": str(output_audio.get("codec_name") or "aac"),
        "Target audio bitrate": f"{spec.audio_bitrate_kbps} kbps",
        "Measured audio bitrate": _format_kbps(output_audio.get("bit_rate")),
        "Audio sample rate": str(output_audio.get("sample_rate") or "48000"),
        "Audio channels": str(output_audio.get("channels") or "2"),
        "Output file size": _format_size(output_format.get("size")),
        "Output duration": f"{duration:.2f} seconds" if duration else "Not available",
        "Validation status": "Validated",
    }
    profile = f"MP4 • {spec.label} • Static image"
    return {
        "id": f"local_{request.run_id}",
        "title": title,
        "uploader": creator,
        "channel": creator,
        "duration": duration,
        "description": "Created locally from MP3 audio and a still image.",
        "vodforge_output_type": OutputType.MP4.value,
        "vodforge_output_path": str(output_path),
        "vodforge_run_id": request.run_id,
        "vodforge_output_profile": profile,
        "vodforge_output_profile_details": "\n".join(
            (
                profile,
                "Output video codec: H.264",
                f"Output rate control: {spec.rate_control_label}",
                f"Output audio codec: AAC • {spec.audio_bitrate_kbps} kbps",
                f"Output file path: {output_path}",
            )
        ),
        "vodforge_run_activity": [
            "Local MP3 and still image selected.",
            f"Static-image MP4 encoded with {request.profile.value} and validated.",
            f"Committed output file: {output_path.name}",
        ],
        "vodforge_encoding_summary": {
            "source": {
                "Source format selector used": "User-selected local files",
                "Source container/ext": "mp3 + image",
                "Source resolution": "Static image",
                "Source audio codec": str(source_audio.get("codec_name") or "mp3"),
                "Source audio bitrate": _format_kbps(source_audio.get("bit_rate")),
                "Source audio sample rate": str(
                    source_audio.get("sample_rate") or "Not available"
                ),
                "Source audio channels": str(
                    source_audio.get("channels") or "Not available"
                ),
                "Reason selected": "User-selected local MP3 and still image",
            },
            "output": output_summary,
            "warnings": [],
        },
    }


def _default_probe_reader(ffprobe: str, path: Path) -> dict[str, Any]:
    completed = subprocess.run(  # nosec B603 - fixed local FFprobe argv
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_entries",
            (
                "format=format_name,size,duration:format_tags:"
                "stream=codec_type,codec_name,width,height,avg_frame_rate,"
                "r_frame_rate,bit_rate,pix_fmt,profile,sample_rate,channels:"
                "stream_disposition"
            ),
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        **hidden_window_subprocess_kwargs(),
    )
    payload = json.loads(completed.stdout or "{}")
    if not isinstance(payload, dict):
        raise LocalAudioVideoError("FFprobe returned invalid media information.")
    return payload


def load_local_still_image(source_path: Path) -> Image.Image:
    """Decode one bounded local still without trusting its extension."""

    try:
        size = source_path.stat().st_size
    except OSError as exc:
        raise LocalAudioVideoError(f"The still image could not be read: {exc}") from exc
    if size <= 0 or size > MAX_LOCAL_IMAGE_BYTES:
        raise LocalAudioVideoError("Choose an image between 1 byte and 50 MB.")
    try:
        with warnings.catch_warnings():
            decompression_warning = getattr(Image, "DecompressionBombWarning", Warning)
            warnings.simplefilter("error", decompression_warning)
            with Image.open(source_path) as source:
                source.verify()
            with Image.open(source_path) as source:
                width, height = source.size
                if width <= 0 or height <= 0 or width * height > MAX_LOCAL_IMAGE_PIXELS:
                    raise LocalAudioVideoError(
                        "The still image dimensions are too large."
                    )
                return ImageOps.exif_transpose(source).convert("RGB")
    except LocalAudioVideoError:
        raise
    except Exception as exc:
        raise LocalAudioVideoError(
            "The selected still image is not a supported image file."
        ) from exc


def normalize_local_still_image(source_path: Path, destination_path: Path) -> None:
    normalized = load_local_still_image(source_path)
    try:
        normalized.thumbnail((4096, 4096), getattr(Image, "Resampling", Image).LANCZOS)
        normalized.save(destination_path, format="PNG", optimize=True)
    finally:
        normalized.close()


class LocalConversionRecoveryOwner:
    """Own the one durable local-conversion staging transaction."""

    def __init__(
        self,
        path: Path,
        *,
        diagnostic: Callable[[str], None] | None = None,
        owner_command_reader: Callable[[int], str | None] = process_command,
    ) -> None:
        self.path = Path(path)
        self._diagnostic = diagnostic or (lambda _message: None)
        self._owner_command_reader = owner_command_reader
        self._lock = threading.RLock()
        self._available = True

    def _write(self, payload: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            if os.name != "nt":
                temporary.chmod(0o600)
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def _read(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            if self.path.stat().st_size > 1_000_000:
                raise LocalAudioVideoError(
                    "The local-conversion recovery record is unexpectedly large."
                )
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LocalAudioVideoError(
                "The local-conversion recovery record is unreadable."
            ) from exc
        if not isinstance(payload, dict):
            raise LocalAudioVideoError(
                "The local-conversion recovery record is invalid."
            )
        return payload

    @staticmethod
    def _validated_transaction(
        payload: Mapping[str, Any],
    ) -> tuple[int, Path, Path, list[dict[str, Any]]]:
        if payload.get("schema_version") != LOCAL_CONVERSION_STATE_SCHEMA:
            raise LocalAudioVideoError(
                "The local-conversion recovery version is unsupported."
            )
        owner_pid = payload.get("owner_pid")
        output_root_raw = payload.get("output_root")
        staging_raw = payload.get("staging_dir")
        children = payload.get("children", [])
        if (
            not isinstance(owner_pid, int)
            or owner_pid <= 1
            or not isinstance(output_root_raw, str)
            or not output_root_raw
            or not isinstance(staging_raw, str)
            or not staging_raw
            or not isinstance(children, list)
            or not all(isinstance(child, dict) for child in children)
        ):
            raise LocalAudioVideoError(
                "The local-conversion recovery ownership is invalid."
            )
        output_root = Path(os.path.abspath(output_root_raw)).resolve(strict=False)
        staging_dir = Path(os.path.abspath(staging_raw)).resolve(strict=False)
        if staging_dir.parent != output_root / ".vfstage":
            raise LocalAudioVideoError(
                "The local-conversion recovery staging path escaped its output root."
            )
        return owner_pid, output_root, staging_dir, list(children)

    def recover_interrupted(self) -> bool:
        with self._lock:
            try:
                payload = self._read()
                if payload is None:
                    return False
                owner_pid, _root, staging_dir, children = self._validated_transaction(
                    payload
                )
                if owner_pid != os.getpid() and self._owner_command_reader(owner_pid):
                    raise LocalAudioVideoError(
                        "Another VODForge process still owns the local conversion."
                    )
                terminate_recorded_children(children, [staging_dir])
                cleanup_abandoned_staging_transactions([staging_dir])
                self.path.unlink(missing_ok=True)
                self._diagnostic(
                    "recovered interrupted local audio-to-video staging transaction"
                )
                return True
            except (OSError, RuntimeError) as exc:
                self._available = False
                self._diagnostic(
                    "local audio-to-video recovery failed closed: "
                    f"{type(exc).__name__}: {exc}"
                )
                return False

    def begin(self, *, output_root: Path, staging_dir: Path, run_id: str) -> None:
        with self._lock:
            if not self._available:
                raise LocalAudioVideoError(
                    "A previous local conversion could not be recovered safely."
                )
            self._write(
                {
                    "schema_version": LOCAL_CONVERSION_STATE_SCHEMA,
                    "state": "active",
                    "owner_pid": os.getpid(),
                    "run_id": run_id,
                    "output_root": str(Path(output_root).resolve(strict=False)),
                    "staging_dir": str(Path(staging_dir).resolve(strict=False)),
                    "children": [],
                }
            )

    def child_started(self, process: Any) -> None:
        with self._lock:
            payload = self._read()
            if payload is None:
                raise LocalAudioVideoError(
                    "The local-conversion transaction lost its durable owner."
                )
            argv = getattr(process, "args", [])
            executable = str(argv[0]) if isinstance(argv, list) and argv else ""
            payload["children"] = [
                {
                    "pid": int(getattr(process, "pid", 0) or 0),
                    # The executable plus the separately recorded staging path is
                    # sufficient to prove ownership; never persist source paths.
                    "argv": [executable],
                }
            ]
            self._write(payload)

    def child_exited(self) -> None:
        with self._lock:
            payload = self._read()
            if payload is None:
                return
            payload["children"] = []
            self._write(payload)

    def finish(self) -> None:
        with self._lock:
            self.path.unlink(missing_ok=True)


@dataclass(frozen=True)
class LocalAudioVideoRuntime:
    """Injectable local codec and image adapters owned by the converter."""

    popen: Callable[..., Any] = subprocess.Popen
    probe_reader: Callable[[str, Path], dict[str, Any]] = _default_probe_reader
    image_normalizer: Callable[[Path, Path], None] = normalize_local_still_image


@dataclass(frozen=True)
class _PreparedLocalAudioVideo:
    audio_path: Path
    image_path: Path
    output_root: Path
    input_probe: Mapping[str, Any]
    duration: float


class LocalAudioVideoConversionOwner:
    """Own one local MP3 + still-image conversion and its child lifecycle."""

    def __init__(
        self,
        *,
        ffmpeg: str | None,
        ffprobe: str | None,
        recovery: LocalConversionRecoveryOwner,
        diagnostic: Callable[[str], None] | None = None,
        runtime: LocalAudioVideoRuntime | None = None,
    ) -> None:
        runtime = runtime or LocalAudioVideoRuntime()
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.recovery = recovery
        self._diagnostic = diagnostic or (lambda _message: None)
        self._popen = runtime.popen
        self._probe_reader = runtime.probe_reader
        self._image_normalizer = runtime.image_normalizer
        self._registry = ActiveChildProcessRegistry(diagnostic=self._diagnostic)
        self._transaction_lock = threading.Lock()
        self._cancel = threading.Event()
        self._shutdown = threading.Event()
        self._idle = threading.Event()
        self._idle.set()

    @property
    def active(self) -> bool:
        return not self._idle.is_set()

    def recover_interrupted(self) -> bool:
        return self.recovery.recover_interrupted()

    def cancel(self) -> None:
        self._cancel.set()

    def _raise_if_cancelled(self) -> None:
        if self._cancel.is_set():
            raise LocalAudioVideoCancelled("The local conversion was stopped.")

    @staticmethod
    def _validate_input_path(path: Path, extension: str, label: str) -> Path:
        candidate = Path(path).expanduser()
        try:
            candidate = candidate.resolve(strict=True)
            valid = candidate.is_file() and candidate.stat().st_size > 0
        except OSError as exc:
            raise LocalAudioVideoError(f"The {label} could not be read: {exc}") from exc
        if not valid or candidate.suffix.casefold() != extension:
            raise LocalAudioVideoError(
                f"Choose an existing {extension.upper()} {label}."
            )
        return candidate

    @staticmethod
    def _validate_image_path(path: Path) -> Path:
        try:
            candidate = Path(path).expanduser().resolve(strict=True)
        except OSError as exc:
            raise LocalAudioVideoError(
                f"The still image could not be read: {exc}"
            ) from exc
        if candidate.suffix.casefold() not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise LocalAudioVideoError("Choose a JPG, PNG, or WebP still image.")
        return candidate

    def _probe(self, path: Path) -> dict[str, Any]:
        if not self.ffprobe:
            raise LocalAudioVideoError("VODForge's FFprobe runtime is unavailable.")
        try:
            return self._probe_reader(self.ffprobe, path)
        except LocalAudioVideoError:
            raise
        except Exception as exc:
            raise LocalAudioVideoError(
                f"VODForge could not inspect {path.name}."
            ) from exc

    @staticmethod
    def _validate_mp3_probe(probe: Mapping[str, Any]) -> float:
        audio = _stream(probe, "audio")
        fmt = probe.get("format")
        fmt = fmt if isinstance(fmt, dict) else {}
        formats = {
            token.strip().casefold()
            for token in str(fmt.get("format_name") or "").split(",")
        }
        duration = _finite_number(fmt.get("duration"))
        if (
            str(audio.get("codec_name") or "").casefold() != "mp3"
            or "mp3" not in formats
            or duration is None
            or duration <= 0
        ):
            raise LocalAudioVideoError(
                "The selected audio is not a valid, playable MP3 file."
            )
        return duration

    def _start_ffmpeg(self, command: list[str]) -> Any:
        try:
            process = self._popen(  # nosec B603 - fixed FFmpeg argv, no shell
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                **hidden_window_subprocess_kwargs(),
            )
        except (OSError, ValueError) as exc:
            raise LocalAudioVideoError(
                "VODForge could not start its local video encoder."
            ) from exc
        self._registry.register(process, timeout_seconds=2.0)
        try:
            self.recovery.child_started(process)
        except Exception:
            self._registry.finalize(process, timeout_seconds=2.0)
            raise
        return process

    @staticmethod
    def _start_output_reader(
        process: Any,
    ) -> tuple[queue.Queue[str | None], threading.Thread]:
        lines: queue.Queue[str | None] = queue.Queue()

        def read_output() -> None:
            try:
                if process.stdout is not None:
                    for line in process.stdout:
                        lines.put(str(line))
            finally:
                lines.put(None)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        return lines, reader

    @staticmethod
    def _progress_from_line(
        line: str, duration: float
    ) -> LocalAudioVideoProgress | None:
        key, separator, value = line.strip().partition("=")
        if not separator or key not in {"out_time_ms", "out_time_us"}:
            return None
        elapsed = _finite_number(value)
        if elapsed is None:
            return None
        fraction = min(1.0, max(0.0, elapsed / 1_000_000 / duration))
        return LocalAudioVideoProgress(0.12 + fraction * 0.78, "Creating MP4…")

    def _monitor_ffmpeg(
        self,
        process: Any,
        lines: queue.Queue[str | None],
        *,
        duration: float,
        on_progress: Callable[[LocalAudioVideoProgress], None],
    ) -> None:
        while True:
            self._raise_if_cancelled()
            try:
                line = lines.get(timeout=0.10)
            except queue.Empty:
                if process.poll() is not None:
                    break
                continue
            if line is None:
                break
            progress = self._progress_from_line(line, duration)
            if progress is not None:
                on_progress(progress)
        try:
            return_code = process.wait(timeout=5)
        except subprocess.TimeoutExpired as exc:
            raise LocalAudioVideoError(
                "The local video encoder did not finish cleanly."
            ) from exc
        if return_code != 0:
            raise LocalAudioVideoError(
                "FFmpeg could not create the MP4 from those files."
            )

    def _finalize_ffmpeg(
        self,
        process: Any,
        reader: threading.Thread,
        *,
        confirmed_exited: bool,
    ) -> None:
        reader.join(timeout=2.0)
        process_reaped = self._registry.finalize(
            process,
            timeout_seconds=2.0,
            confirmed_exited=confirmed_exited,
        )
        if not process_reaped:
            return
        try:
            self.recovery.child_exited()
        except (OSError, RuntimeError) as exc:
            self._diagnostic(
                "local audio-to-video child-exit persistence failed: "
                f"{type(exc).__name__}: {exc}"
            )

    def _run_ffmpeg(
        self,
        command: list[str],
        *,
        duration: float,
        on_progress: Callable[[LocalAudioVideoProgress], None],
    ) -> None:
        process = self._start_ffmpeg(command)
        lines, reader = self._start_output_reader(process)
        confirmed_exited = False
        try:
            self._monitor_ffmpeg(
                process,
                lines,
                duration=duration,
                on_progress=on_progress,
            )
            confirmed_exited = True
        except LocalAudioVideoCancelled:
            self._registry.terminate_and_reap(process, timeout_seconds=2.0)
            confirmed_exited = True
            raise
        finally:
            self._finalize_ffmpeg(
                process,
                reader,
                confirmed_exited=confirmed_exited,
            )

    def _has_active_child(self) -> bool:
        with self._registry.inspection_lock:
            return bool(self._registry.processes)

    @staticmethod
    def _validate_output_shape(
        probe: Mapping[str, Any], profile: LocalVideoProfile
    ) -> None:
        spec = local_video_profile_spec(profile)
        video = _stream(probe, "video")
        audio = _stream(probe, "audio")
        if (
            int(video.get("width") or 0) != spec.width
            or int(video.get("height") or 0) != spec.height
            or str(video.get("pix_fmt") or "").casefold() != "yuv420p"
            or str(audio.get("codec_name") or "").casefold() != "aac"
        ):
            raise LocalAudioVideoError(
                "The rendered MP4 did not match VODForge's playback profile."
            )

    def _commit_distinct_output(
        self,
        staged_output: Path,
        output_root: Path,
        filename: str,
    ) -> Path:
        initial = output_root / filename
        for index in range(10_000):
            destination = (
                initial
                if index == 0
                else initial.with_name(f"{initial.stem} ({index}){initial.suffix}")
            )
            try:
                return commit_file_beneath(
                    staged_output,
                    output_root,
                    destination,
                    control_check=self._raise_if_cancelled,
                    replace_existing=False,
                )
            except FileExistsError:
                continue
        raise LocalAudioVideoError(
            "VODForge could not allocate a distinct output filename."
        )

    def _prepare_request(
        self,
        request: LocalAudioVideoRequest,
        on_progress: Callable[[LocalAudioVideoProgress], None],
    ) -> _PreparedLocalAudioVideo:
        if not self.ffmpeg:
            raise LocalAudioVideoError("VODForge's FFmpeg runtime is unavailable.")
        audio_path = self._validate_input_path(request.audio_path, ".mp3", "audio file")
        image_path = self._validate_image_path(request.image_path)
        output_root = Path(request.output_dir).expanduser().resolve(strict=False)
        on_progress(LocalAudioVideoProgress(0.02, "Checking local files…"))
        input_probe = self._probe(audio_path)
        duration = self._validate_mp3_probe(input_probe)
        self._raise_if_cancelled()
        return _PreparedLocalAudioVideo(
            audio_path=audio_path,
            image_path=image_path,
            output_root=output_root,
            input_probe=input_probe,
            duration=duration,
        )

    def _render_and_commit(
        self,
        request: LocalAudioVideoRequest,
        prepared: _PreparedLocalAudioVideo,
        staging_dir: Path,
        on_progress: Callable[[LocalAudioVideoProgress], None],
    ) -> LocalAudioVideoResult:
        normalized_image = staging_dir / "still.png"
        staged_output = staging_dir / "rendered.mp4"
        self._image_normalizer(prepared.image_path, normalized_image)
        on_progress(LocalAudioVideoProgress(0.10, "Preparing still image…"))
        self._raise_if_cancelled()
        command = build_local_audio_video_command(
            self.ffmpeg or "ffmpeg",
            audio_path=prepared.audio_path,
            image_path=normalized_image,
            output_path=staged_output,
            profile=request.profile,
        )
        self._diagnostic(
            "local audio-to-video encode started "
            f"run_id={request.run_id} duration_seconds={prepared.duration:.3f}"
        )
        self._run_ffmpeg(
            command,
            duration=prepared.duration,
            on_progress=on_progress,
        )
        self._raise_if_cancelled()
        on_progress(LocalAudioVideoProgress(0.92, "Validating MP4…"))
        output_probe = self._probe(staged_output)
        validate_output_artifact(
            staged_output,
            OutputType.MP4,
            self.ffprobe or "ffprobe",
            probe_reader=lambda *_args, **_kwargs: dict(output_probe),
            expected_duration_seconds=prepared.duration,
            require_audio=True,
            expected_audio_codec="aac",
            ffprobe_data=dict(output_probe),
        )
        self._validate_output_shape(output_probe, request.profile)
        self._raise_if_cancelled()
        on_progress(LocalAudioVideoProgress(0.97, "Saving to Forge destination…"))
        output_path = self._commit_distinct_output(
            staged_output,
            prepared.output_root,
            local_video_filename(prepared.audio_path),
        )
        metadata = build_local_audio_video_history_metadata(
            request,
            output_path=output_path,
            input_probe=prepared.input_probe,
            output_probe=output_probe,
        )
        on_progress(LocalAudioVideoProgress(1.0, "MP4 created"))
        self._diagnostic(
            "local audio-to-video encode completed "
            f"run_id={request.run_id} output={output_path.name}"
        )
        return LocalAudioVideoResult(
            output_path=output_path,
            image_path=prepared.image_path,
            history_metadata=metadata,
        )

    def convert(
        self,
        request: LocalAudioVideoRequest,
        *,
        on_progress: Callable[[LocalAudioVideoProgress], None],
    ) -> LocalAudioVideoResult:
        if not self._transaction_lock.acquire(blocking=False):
            raise LocalAudioVideoError("Another local conversion is already running.")
        self._idle.clear()
        staging_dir: Path | None = None
        try:
            if self._shutdown.is_set():
                raise LocalAudioVideoCancelled(
                    "The local conversion cannot start while VODForge is closing."
                )
            self._cancel.clear()
            prepared = self._prepare_request(request, on_progress)
            staging_dir = create_private_staging_directory(prepared.output_root)
            self.recovery.begin(
                output_root=prepared.output_root,
                staging_dir=staging_dir,
                run_id=request.run_id,
            )
            return self._render_and_commit(
                request,
                prepared,
                staging_dir,
                on_progress,
            )
        finally:
            if staging_dir is not None and not self._has_active_child():
                cleaned = cleanup_private_staging_directory(staging_dir)
                if cleaned:
                    self.recovery.finish()
                else:
                    self._diagnostic(
                        "local audio-to-video staging cleanup remains pending recovery"
                    )
            elif staging_dir is not None:
                self._diagnostic(
                    "local audio-to-video staging retained for live-child recovery"
                )
            self._idle.set()
            self._transaction_lock.release()

    def shutdown(self, *, timeout_seconds: float = 4.0) -> bool:
        self._shutdown.set()
        self.cancel()
        self._registry.terminate_all(timeout_seconds=2.0)
        return self._idle.wait(timeout=max(0.0, timeout_seconds))
