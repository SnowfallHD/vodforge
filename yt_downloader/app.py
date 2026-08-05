from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
import uuid
import webbrowser
from datetime import datetime
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .history import (
    HistoryError,
    application_data_dir,
    history_file_path,
    history_identity,
    history_output_dir,
    load_history,
    save_history,
    upsert_history,
)
from .updates import (
    ReleaseInfo,
    download_verified_update,
    fetch_latest_release,
    is_newer_release,
    release_asset_for_platform,
)
from .version import __version__

try:
    from PIL import Image, ImageTk
except Exception:  # pragma: no cover - thumbnail preview becomes unavailable
    Image = None
    ImageTk = None

try:
    import yt_dlp
except Exception as exc:  # pragma: no cover - handled at runtime
    yt_dlp = None
    YTDLP_IMPORT_ERROR = exc
else:
    YTDLP_IMPORT_ERROR = None


def _format_selector(max_height: int) -> str:
    # Always request video + best available audio. Do not fall back to video-only
    # unless a future explicit video-only mode is added.
    return (
        f"bestvideo[height<={max_height}][ext=mp4]+bestaudio/"
        f"bestvideo[height<={max_height}]+bestaudio/"
        f"best[height<={max_height}][ext=mp4][acodec!=none]/"
        f"best[height<={max_height}][acodec!=none]"
    )


APP_NAME = "VODForge"
WINDOWS_SAFE_PATH_LIMIT = 240
ANALYSIS_TIMEOUT_SECONDS = 1800
ANALYSIS_POLL_SECONDS = 0.1
ANALYSIS_STATUS_SECONDS = 5
VIDEO_TARGET_BITRATE = "10M"
AUDIO_BITRATE = "320k"
AUDIO_SAMPLE_RATE = "48000"
AUDIO_CHANNELS = "2"
STRICT_VIDEO_BITRATE_KBPS = 10000
STRICT_AUDIO_BITRATE_KBPS = 320
DEFAULT_MAX_HEIGHT = 1080
THUMBNAIL_MAX_BYTES = 300 * 1024
CLEAN_BITRATE_STEPS = [1000, 1200, 1500, 2000, 2500, 3000, 4000, 5000, 6000, 8000, 10000, 12000, 14000, 24000, 45000, 68000]
VIDEO_MINIMUMS_KBPS = {480: 1000, 720: 1500, 1080: 2000, 1440: 6000, 2160: 12000}
VIDEO_CAPS_KBPS = {(480, 30): 2500, (720, 30): 5000, (1080, 30): 10000, (1080, 60): 14000, (1440, 30): 24000, (2160, 30): 45000, (2160, 60): 68000}
EXPORT_MODES = ["Auto CBR", "Strict Compliance", "Manual Override"]
BACKEND_TEMP_OUTPUT_NAME = "__vodforge-tmp.mp4"
BACKEND_ORIGINAL_BACKUP_NAME = "__vodforge-original.mp4"


def diagnostics_dir(
    *,
    platform_name: str | None = None,
    home: Path | None = None,
    local_app_data: str | None = None,
) -> Path:
    """Return the platform's conventional per-user diagnostics directory."""
    platform_name = sys.platform if platform_name is None else platform_name
    home = Path.home() if home is None else home
    if platform_name.startswith("win"):
        base = local_app_data if local_app_data is not None else os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / APP_NAME / "logs"
    if platform_name == "darwin":
        return home / "Library" / "Logs" / APP_NAME
    return home / ".vodforge" / "logs"


def platform_font_families(platform_name: str | None = None) -> tuple[str, str]:
    platform_name = sys.platform if platform_name is None else platform_name
    if platform_name == "darwin":
        return "Helvetica Neue", "Menlo"
    if platform_name.startswith("win"):
        return "Segoe UI", "Cascadia Mono"
    return "TkDefaultFont", "TkFixedFont"


def runtime_executable_candidates(
    tool_name: str,
    *,
    platform_name: str | None = None,
    frozen: bool | None = None,
    executable: Path | None = None,
    meipass: Path | None = None,
    repo_root: Path | None = None,
) -> list[Path]:
    """Return deterministic runtime locations, including Finder-safe macOS paths."""
    platform_name = sys.platform if platform_name is None else platform_name
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    executable = Path(sys.executable) if executable is None else executable
    raw_meipass = getattr(sys, "_MEIPASS", None) if meipass is None else meipass
    meipass = Path(raw_meipass) if raw_meipass else None
    repo_root = Path(__file__).resolve().parents[1] if repo_root is None else repo_root
    names = [f"{tool_name}.exe", tool_name] if platform_name.startswith("win") else [tool_name, f"{tool_name}.exe"]

    directories: list[Path] = []
    if frozen:
        directories.append(executable.resolve().parent)
        if meipass is not None:
            directories.append(meipass.resolve())
    directories.append(repo_root)
    if tool_name in {"ffmpeg", "ffprobe"}:
        directories.append(repo_root / "vendor" / "ffmpeg" / "bin")
    elif tool_name == "deno":
        directories.append(repo_root / "vendor" / "deno")
    if platform_name == "darwin":
        # Finder-launched .apps do not reliably inherit a shell's Homebrew PATH.
        directories.extend((Path("/opt/homebrew/bin"), Path("/usr/local/bin")))

    candidates: list[Path] = []
    seen: set[Path] = set()
    override = os.environ.get(f"VODFORGE_{tool_name.upper()}")
    if override:
        override_path = Path(override).expanduser()
        candidates.append(override_path)
        seen.add(override_path)
    for directory in directories:
        for name in names:
            candidate = directory / name
            if candidate not in seen:
                candidates.append(candidate)
                seen.add(candidate)
    return candidates


def find_runtime_executable(tool_name: str) -> str | None:
    for candidate in runtime_executable_candidates(tool_name):
        if candidate.is_file():
            return str(candidate)
    return shutil.which(tool_name)


def ytdlp_ffmpeg_location(ffmpeg: str) -> str:
    """Point yt-dlp at an FFmpeg directory when the executable has a standard name."""
    ffmpeg_path = Path(ffmpeg)
    if ffmpeg_path.name.lower() in {"ffmpeg", "ffmpeg.exe"}:
        return str(ffmpeg_path.parent)
    return str(ffmpeg_path)


def runtime_version_command(tool_name: str, executable: str) -> list[str]:
    return [executable, "--version"] if tool_name == "deno" else [executable, "-version"]


def probe_runtime_version(tool_name: str, executable: str) -> str:
    """Execute a bundled runtime so smoke tests also catch missing dynamic libraries."""
    startupinfo = None
    creationflags = 0
    if sys.platform.startswith("win"):
        startupinfo = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        runtime_version_command(tool_name, executable),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        startupinfo=startupinfo,
        creationflags=creationflags,
    )
    return next((line.strip() for line in result.stdout.splitlines() if line.strip()), "version output unavailable")


DIAGNOSTICS_LOG_PATH = diagnostics_dir() / "latest.log"
BATCH_FAILURE_REPORT_PATH = diagnostics_dir() / "batch-url-failures.txt"


def write_diagnostic(message: str) -> None:
    try:
        DIAGNOSTICS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().isoformat(timespec="milliseconds")
        with DIAGNOSTICS_LOG_PATH.open("a", encoding="utf-8") as log:
            log.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


def reset_diagnostics_log() -> None:
    try:
        DIAGNOSTICS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        DIAGNOSTICS_LOG_PATH.write_text("", encoding="utf-8")
    except Exception:
        pass


def reset_batch_failure_report(path: Path = BATCH_FAILURE_REPORT_PATH) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
    except Exception:
        pass


def append_batch_failure_report(path: Path, url: str, issue: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat(timespec="seconds")
    issue_text = str(issue).strip() or type(issue).__name__
    with path.open("a", encoding="utf-8") as report:
        report.write(f"[{timestamp}]\nURL: {url}\nIssue: {issue_text}\n\n")


def _loggable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _loggable(v) for k, v in value.items() if k != "logger"}
    if isinstance(value, (list, tuple)):
        return [_loggable(v) for v in value]
    if callable(value):
        return f"<callable {getattr(value, '__name__', type(value).__name__)}>"
    return value


def log_options(stage: str, opts: dict[str, Any]) -> None:
    try:
        write_diagnostic(f"{stage} options: {json.dumps(_loggable(opts), indent=2, sort_keys=True, default=str)}")
    except Exception as exc:
        write_diagnostic(f"{stage} options logging failed: {exc}")


def run_cancellable_blocking_step(
    step,
    cancel_requested,
    *,
    timeout_seconds: float,
    poll_seconds: float = ANALYSIS_POLL_SECONDS,
    label: str = "step",
    on_wait=None,
    wait_notice_seconds: float = ANALYSIS_STATUS_SECONDS,
):
    """Run an uninterruptible library call behind a cancellable polling boundary.

    yt-dlp extraction does not call progress hooks during source-format analysis,
    so GUI Cancel needs a wrapper that can return control without waiting for the
    library call to finish. The inner daemon thread may finish later, but the UI
    worker can stop promptly and avoid looking hung.
    """
    results: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

    def runner() -> None:
        try:
            results.put(("ok", step()))
        except Exception as exc:
            results.put(("error", exc))

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    started_at = time.monotonic()
    deadline = time.monotonic() + timeout_seconds
    next_wait_notice = started_at + wait_notice_seconds
    while True:
        try:
            kind, payload = results.get_nowait()
        except queue.Empty:
            now = time.monotonic()
            if cancel_requested():
                raise RuntimeError(f"{label} cancelled by user")
            if on_wait is not None and now >= next_wait_notice:
                on_wait(now - started_at)
                next_wait_notice = now + wait_notice_seconds
            if now >= deadline:
                raise TimeoutError(f"{label} timed out after {timeout_seconds:g} seconds")
            time.sleep(poll_seconds)
            continue
        if kind == "error":
            raise payload
        return payload


THEME = {
    "bg": "#08090a",
    "panel": "#0f1011",
    "surface": "#191a1b",
    "surface_2": "#23252a",
    "text": "#f7f8f8",
    "muted": "#8a8f98",
    "subtle": "#62666d",
    "accent": "#7170ff",
    "accent_dark": "#5e6ad2",
    "success": "#10b981",
    "border": "#34343a",
}
FONT_UI_FAMILY, FONT_MONO_FAMILY = platform_font_families()
FONT_UI = (FONT_UI_FAMILY, 10)
FONT_UI_SMALL = (FONT_UI_FAMILY, 9)
FONT_UI_MEDIUM = (FONT_UI_FAMILY, 10, "bold")
FONT_UI_SMALL_MEDIUM = (FONT_UI_FAMILY, 9, "bold")
FONT_TITLE = (FONT_UI_FAMILY, 22, "bold")
FONT_MONO = (FONT_MONO_FAMILY, 9)
QUALITY_OPTIONS = {
    "Best available up to 4K": _format_selector(2160),
    "2160p / 4K": _format_selector(2160),
    "1440p / 2K": _format_selector(1440),
    "1080p Full HD": _format_selector(1080),
    "720p HD": _format_selector(720),
    "480p": _format_selector(480),
    "360p": _format_selector(360),
}


class ExportMode(str, Enum):
    AUTO_CBR = "Auto CBR"
    STRICT_COMPLIANCE = "Strict Compliance"
    MANUAL_OVERRIDE = "Manual Override"


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
    x264_preset: str = "medium"
    fps: float | None = None
    video_codec: str = "unknown"
    audio_codec: str = "unknown"
    warnings: list[str] = field(default_factory=list)
    summary: str = ""


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_none_codec(value: Any) -> bool:
    text = str(value or "").lower()
    return not text or text == "none"


def video_codec_multiplier(vcodec: Any) -> float:
    codec = str(vcodec or "").lower()
    if codec.startswith("avc") or codec.startswith("h264"):
        return 1.0
    if codec.startswith("vp9") or codec.startswith("vp09"):
        return 1.5
    if codec.startswith("av01") or codec.startswith("av1"):
        return 1.8
    if codec.startswith("hev") or codec.startswith("h265") or codec.startswith("hvc1"):
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
    return _num(fmt.get("vbr")) or _num(fmt.get("tbr")) or (_num(fmt.get("filesize")) * 8 / 1000 / max(_num(fmt.get("duration")), 1))


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
    return VIDEO_CAPS_KBPS.get((bucket, fps_bucket)) or VIDEO_CAPS_KBPS.get((bucket, 30)) or 10000


def _transcode_headroom(vcodec: Any) -> float:
    codec = str(vcodec or "").lower()
    if codec.startswith("avc") or codec.startswith("h264"):
        return 1.25
    if codec.startswith(("vp9", "vp09", "av01", "av1", "hev", "h265", "hvc1")):
        return 1.4
    return 1.3


def _is_hdr_format(fmt: dict[str, Any]) -> bool:
    dynamic_range = str(fmt.get("dynamic_range") or "").upper()
    color_transfer = str(fmt.get("color_transfer") or "").lower()
    return dynamic_range not in {"", "SDR"} or "smpte2084" in color_transfer or "arib" in color_transfer


def choose_best_video_format(formats: list[dict[str, Any]], max_height: int = DEFAULT_MAX_HEIGHT) -> dict[str, Any] | None:
    """Select the best video-only format, with progressively relaxed filters.

    Some YouTube videos only expose a limited set of formats (e.g. when no JS
    runtime is available, the player returns fewer streams).  The original
    strict filter (video-only, SDR, known-bitrate, ≤120fps, ≤max_height)
    would reject every format for those videos and raise "No usable SDR video
    source."  We now try the strict pass first, then relax each constraint
    one at a time so we can still download whatever *is* available.
    """
    def _select(*, allow_progressive: bool = False, allow_hdr: bool = False, allow_unknown_bitrate: bool = False, allow_high_fps: bool = False) -> dict[str, Any] | None:
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
            effective = kbps * video_codec_multiplier(fmt.get("vcodec")) if kbps > 0 else 1.0
            # Prefer direct https downloads over HLS/m3u8 streams (which download
            # as hundreds of fragments and are much slower for large videos).
            is_direct = str(fmt.get("protocol", "")).startswith("http")
            candidates.append((height, effective, kbps or 1.0, fmt.get("ext") == "mp4", str(fmt.get("vcodec") or "").startswith("avc"), is_direct, fmt))
        if not candidates:
            return None
        target_height = 1080 if any(item[0] == 1080 for item in candidates) and max_height >= 1080 else max(item[0] for item in candidates)
        same_res = [item for item in candidates if item[0] == target_height]
        # Prefer direct https downloads over HLS/m3u8 streams. Direct formats
        # download as single files; m3u8 streams download as hundreds of
        # fragments and are much slower. If any direct format exists at the
        # target resolution, exclude m3u8 formats before the closeness filter
        # so the direct format isn't rejected for having a slightly lower
        # reported bitrate.
        direct_candidates = [item for item in same_res if item[5]]
        if direct_candidates:
            same_res = direct_candidates
        best_effective = max(item[1] for item in same_res)
        close = [item for item in same_res if item[1] >= best_effective * 0.85]
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


def choose_best_progressive_format(formats: list[dict[str, Any]], max_height: int = DEFAULT_MAX_HEIGHT) -> dict[str, Any] | None:
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
        candidates.append((height, effective, kbps, fmt.get("ext") == "mp4", str(fmt.get("vcodec") or "").startswith("avc"), fmt))
    if not candidates:
        return None
    target_height = 1080 if any(item[0] == 1080 for item in candidates) and max_height >= 1080 else max(item[0] for item in candidates)
    same_res = [item for item in candidates if item[0] == target_height]
    best_effective = max(item[1] for item in same_res)
    close = [item for item in same_res if item[1] >= best_effective * 0.85]
    return max(close, key=lambda item: (item[4], item[1], item[2], item[3]))[5]


def choose_best_audio_format(formats: list[dict[str, Any]]) -> dict[str, Any] | None:
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
            is_direct = str(fmt.get("protocol", "")).startswith("http")
            candidates.append((effective, channels >= 2, sample_rate >= 48000, fmt.get("ext") in {"m4a", "mp4", "webm"}, is_direct, fmt))
        if not candidates:
            return None
        return max(candidates, key=lambda item: (item[4], item[0], item[1], item[2], item[3]))[5]

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


def calculate_auto_video_bitrate_kbps(video_fmt: dict[str, Any]) -> int:
    height = video_fmt.get("height") if isinstance(video_fmt.get("height"), int) else None
    fps = _num(video_fmt.get("fps"), 30.0)
    source_kbps = _format_video_kbps(video_fmt)
    effective = source_kbps * video_codec_multiplier(video_fmt.get("vcodec"))
    estimate = effective * _transcode_headroom(video_fmt.get("vcodec"))
    value = _clamp(estimate, _resolution_minimum_kbps(height), _resolution_cap_kbps(height, fps))
    rounded = _round_clean_bitrate(value)
    return int(_clamp(rounded, _resolution_minimum_kbps(height), _resolution_cap_kbps(height, fps)))


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


def build_auto_export_plan(info: dict[str, Any], mode: ExportMode | str = ExportMode.AUTO_CBR, max_height: int = DEFAULT_MAX_HEIGHT) -> ExportPlan:
    mode = ExportMode(mode)
    formats = [fmt for fmt in info.get("formats") or [] if isinstance(fmt, dict)]
    video = choose_best_video_format(formats, max_height=max_height)
    using_progressive_av = False
    if video is None:
        video = choose_best_progressive_format(formats, max_height=max_height)
        using_progressive_av = video is not None
    audio = video if using_progressive_av else choose_best_audio_format(formats)
    if video is None:
        # Last resort: pick *any* format with a video codec, ignoring all quality filters.
        for fmt in formats:
            if not _is_none_codec(fmt.get("vcodec")):
                video = fmt
                using_progressive_av = not _is_none_codec(fmt.get("acodec"))
                audio = video if using_progressive_av else audio
                break
    if video is None:
        raise RuntimeError(
            "No usable video source was found for this URL. This can happen when:\n"
            "• The video is private, members-only, or region-restricted.\n"
            "• No JavaScript runtime (Deno 2.x) is installed, limiting available formats.\n"
            "• YouTube is rate-limiting the connection (retry later or use cookies).\n"
            "Check the diagnostics log for yt-dlp's detailed format list."
        )
    if audio is None and not using_progressive_av:
        # Last resort: pick any audio-only format, ignoring bitrate filters.
        for fmt in formats:
            if _is_none_codec(fmt.get("vcodec")) and not _is_none_codec(fmt.get("acodec")):
                audio = fmt
                break
    if audio is None and not using_progressive_av:
        raise RuntimeError(
            "No usable audio source was found for this URL. This can happen when "
            "yt-dlp returns limited formats without a JavaScript runtime (Deno 2.x). "
            "Check the diagnostics log for details."
        )
    video_id = str(video.get("format_id") or "") or None
    audio_id = str(audio.get("format_id") or "") if audio else None
    source_video_kbps = _format_video_kbps(video)
    effective_video_kbps = source_video_kbps * video_codec_multiplier(video.get("vcodec"))
    source_audio_kbps = _format_audio_kbps(audio or {})
    effective_audio_kbps = source_audio_kbps * audio_codec_multiplier((audio or {}).get("acodec"))
    warnings: list[str] = []
    height = video.get("height") if isinstance(video.get("height"), int) else None
    width = video.get("width") if isinstance(video.get("width"), int) else None
    fps = _num(video.get("fps"), 30.0)
    if max_height >= 1080 and height != 1080:
        warnings.append("This video is not available in 1080p. VODForge will export the best available lower-resolution version.")
    if mode == ExportMode.STRICT_COMPLIANCE:
        video_bitrate = STRICT_VIDEO_BITRATE_KBPS
        audio_bitrate = STRICT_AUDIO_BITRATE_KBPS
        if height and height < 1080:
            warnings.append("Strict Compliance uses high-bitrate output settings, but the selected source is below 1080p. This will not create true 1080p detail.")
        if effective_video_kbps and video_bitrate / effective_video_kbps > 2:
            warnings.append("Strict Compliance target is far above the selected source quality. The output may satisfy platform requirements, but it will not become true high-bitrate quality.")
    elif mode == ExportMode.MANUAL_OVERRIDE:
        video_bitrate = STRICT_VIDEO_BITRATE_KBPS
        audio_bitrate = STRICT_AUDIO_BITRATE_KBPS
    else:
        video_bitrate = calculate_auto_video_bitrate_kbps(video)
        audio_bitrate = choose_audio_bitrate_kbps(effective_audio_kbps) if audio else 160
    warn = _bitrate_warning(video_bitrate, effective_video_kbps)
    if warn and warn not in warnings:
        warnings.append(warn)
    if effective_audio_kbps and audio_bitrate / effective_audio_kbps > 2:
        warnings.append("Audio target is much higher than the source. This may satisfy the output profile, but it will not restore lost audio quality.")
    if using_progressive_av and video_id:
        selector = video_id
    elif video_id and audio_id:
        selector = f"{video_id}+{audio_id}"
    else:
        raise RuntimeError("VODForge could not build a safe video+audio selector from yt-dlp formats.")
    if mode == ExportMode.STRICT_COMPLIANCE:
        summary = f"Strict Compliance selected the best practical {height or 'unknown'}p source and will export fixed H.264 CBR {video_bitrate / 1000:g} Mbps + AAC {audio_bitrate} kbps."
    elif mode == ExportMode.MANUAL_OVERRIDE:
        summary = f"Manual Override selected the best practical {height or 'unknown'}p source; user-selected encode settings will be applied before transcode."
    elif height == 1080:
        summary = f"Auto mode selected a true 1080p source and recommends {video_bitrate / 1000:g} Mbps CBR based on source quality and the platform's 1080p minimum."
    else:
        summary = f"Auto mode selected the best available {height or 'unknown'}p source and will export at that truthful resolution."
    return ExportPlan(
        mode=mode,
        video_format_id=video_id,
        audio_format_id=audio_id,
        format_selector=selector,
        output_width=width,
        output_height=height,
        source_video_kbps=source_video_kbps,
        effective_video_kbps=effective_video_kbps,
        video_bitrate_kbps=video_bitrate,
        source_audio_kbps=source_audio_kbps,
        effective_audio_kbps=effective_audio_kbps,
        audio_bitrate_kbps=audio_bitrate,
        fps=fps,
        video_codec=str(video.get("vcodec") or "unknown"),
        audio_codec=str((audio or {}).get("acodec") or "unknown"),
        warnings=warnings,
        summary=summary,
    )


def apply_manual_export_settings(plan: ExportPlan, settings: "ManualExportSettings") -> ExportPlan:
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
        x264_preset=settings.x264_preset,
        fps=plan.fps,
        video_codec=plan.video_codec,
        audio_codec=plan.audio_codec,
        warnings=list(plan.warnings),
        summary=(
            f"Manual Override will export H.264 CBR {settings.video_bitrate_kbps / 1000:g} Mbps "
            f"+ AAC {settings.audio_bitrate_kbps} kbps, {settings.audio_sample_rate} Hz, "
            f"{settings.audio_channels} channel(s)."
        ),
    )


def _clean_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        cleaned.append(text)
        seen.add(text)
    return cleaned


def build_tags_display_text(info: dict[str, Any]) -> str:
    """Return YouTube tags comma-separated so the GUI copy action is compact."""
    return ", ".join(_clean_list(info.get("tags")))


def build_description_display_text(info: dict[str, Any]) -> str:
    return str(info.get("description") or "").strip()


def format_duration(seconds: Any) -> str:
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return "—"
    if total < 0:
        return "—"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _float_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def video_list_row_values(info: dict[str, Any], fallback_index: int) -> tuple[str, str, str, str, str]:
    raw_index = info.get("playlist_index") or fallback_index
    try:
        index = f"{int(raw_index):03d}"
    except (TypeError, ValueError):
        index = f"{fallback_index:03d}"
    title = str(info.get("title") or info.get("id") or "Untitled video").strip()
    uploader = str(info.get("uploader") or info.get("channel") or "—").strip() or "—"
    video_id = str(info.get("id") or "—").strip() or "—"
    return (index, title, format_duration(info.get("duration")), uploader, video_id)


def _display_value(value: Any, fallback: str = "Unknown") -> str:
    if value is None or value == "" or value == [] or value == {}:
        return fallback
    return str(value)


def _format_kbps(value: Any, fallback: str = "Unknown") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number <= 0:
        return fallback
    return f"{number:.0f} kbps"


def _format_bits_per_second_as_kbps(value: Any, fallback: str = "Unknown") -> str:
    try:
        number = float(value) / 1000
    except (TypeError, ValueError):
        return fallback
    if number <= 0:
        return fallback
    return f"{number:.0f} kbps"


def _format_bytes(value: Any, fallback: str = "Not available") -> str:
    try:
        size = float(value)
    except (TypeError, ValueError):
        return fallback
    if size <= 0:
        return fallback
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{size:.0f} B"
        size /= 1024
    return fallback


def _format_fractional_fps(value: Any, fallback: str = "Unknown") -> str:
    if value in (None, "", "0/0"):
        return fallback
    text = str(value)
    try:
        if "/" in text:
            numerator, denominator = text.split("/", 1)
            fps = float(numerator) / float(denominator)
        else:
            fps = float(text)
    except (TypeError, ValueError, ZeroDivisionError):
        return fallback
    if fps <= 0:
        return fallback
    return f"{fps:.2f} fps" if abs(fps - round(fps)) > 0.01 else f"{fps:.0f} fps"


def _selected_format(info: dict[str, Any], format_id: str | None) -> dict[str, Any]:
    if not format_id:
        return {}
    for fmt in info.get("formats") or []:
        if isinstance(fmt, dict) and str(fmt.get("format_id") or "") == str(format_id):
            return fmt
    return {}


def _source_container(video_fmt: dict[str, Any], audio_fmt: dict[str, Any], plan: ExportPlan) -> str:
    video_ext = video_fmt.get("ext")
    audio_ext = audio_fmt.get("ext")
    if plan.video_format_id == plan.audio_format_id or not audio_ext:
        return _display_value(video_ext, "Unknown")
    return f"{_display_value(video_ext, 'Unknown')} + {_display_value(audio_ext, 'Unknown')}"


def _hdr_status(fmt: dict[str, Any]) -> str:
    if not fmt:
        return "Unknown"
    dynamic_range = fmt.get("dynamic_range")
    if dynamic_range:
        return str(dynamic_range).upper()
    return "HDR" if _is_hdr_format(fmt) else "SDR"


def _source_selection_reason(plan: ExportPlan) -> str:
    reasons: list[str] = []
    if plan.output_height == 1080:
        reasons.append("true 1080p available")
    elif plan.output_height:
        reasons.append("best lower-resolution source")
    else:
        reasons.append("best available source")
    codec = plan.video_codec.lower()
    if codec.startswith(("avc", "h264")):
        reasons.append("preferred H.264 source")
    else:
        reasons.append("best effective score")
    return "; ".join(reasons)


def build_encoding_summary_metadata(
    info: dict[str, Any],
    plan: ExportPlan,
    *,
    output_path: Path | None = None,
    ffprobe_data: dict[str, Any] | None = None,
    validation_status: str | None = None,
) -> dict[str, Any]:
    """Attach per-video source/final-output encoding summary metadata."""
    enriched = dict(info)
    video_fmt = _selected_format(info, plan.video_format_id)
    audio_fmt = video_fmt if plan.video_format_id == plan.audio_format_id else _selected_format(info, plan.audio_format_id)
    source = {
        "Source format selector used": _display_value(plan.format_selector, "Not available"),
        "Video format ID": _display_value(plan.video_format_id, "Not available"),
        "Audio format ID": _display_value(plan.audio_format_id, "Not available"),
        "Source container/ext": _source_container(video_fmt, audio_fmt, plan),
        "Source resolution": f"{plan.output_width}x{plan.output_height}" if plan.output_width and plan.output_height else "Unknown",
        "Source frame rate": _format_fractional_fps(video_fmt.get("fps") or plan.fps),
        "Source video codec": _display_value(video_fmt.get("vcodec") or plan.video_codec),
        "Source video bitrate": _format_kbps(plan.source_video_kbps),
        "Source audio codec": _display_value(audio_fmt.get("acodec") or plan.audio_codec),
        "Source audio bitrate": _format_kbps(plan.source_audio_kbps),
        "Source audio sample rate": _display_value(audio_fmt.get("asr"), "Not available"),
        "Source audio channels": _display_value(audio_fmt.get("audio_channels") or audio_fmt.get("channels"), "Not available"),
        "HDR/SDR status": _hdr_status(video_fmt),
        "File size estimate": _format_bytes(video_fmt.get("filesize") or video_fmt.get("filesize_approx") or audio_fmt.get("filesize") or audio_fmt.get("filesize_approx")),
        "Effective H.264-equivalent video bitrate": _format_kbps(plan.effective_video_kbps),
        "Effective AAC-equivalent audio bitrate": _format_kbps(plan.effective_audio_kbps),
        "Reason selected": _source_selection_reason(plan),
    }
    output = _planned_output_summary(plan, output_path)
    if ffprobe_data:
        output.update(_ffprobe_output_summary(ffprobe_data, output_path))
        output["Validation status"] = validation_status or "Validated"
    elif validation_status:
        output["Validation status"] = validation_status
    enriched["vodforge_encoding_summary"] = {"source": source, "output": output, "warnings": list(plan.warnings)}
    return enriched


def build_failed_encoding_summary_metadata(info: dict[str, Any], plan: ExportPlan | None, failure_reason: str) -> dict[str, Any]:
    if plan is not None:
        enriched = build_encoding_summary_metadata(info, plan, validation_status="Failed")
    else:
        enriched = dict(info)
        enriched["vodforge_encoding_summary"] = {"source": {}, "output": {}, "warnings": []}
    enriched["vodforge_encoding_summary"]["output"].update({
        "Output status": "No output produced",
        "Output file path": "Not produced",
        "Validation status": "Failed",
        "Failure reason": _display_value(failure_reason, "Unknown"),
    })
    return enriched


def _planned_output_summary(plan: ExportPlan, output_path: Path | None = None) -> dict[str, str]:
    return {
        "Output status": "Planned Output",
        "Output file path": str(output_path) if output_path else "Pending",
        "Output container": "mp4",
        "Output resolution": f"{plan.output_width}x{plan.output_height}" if plan.output_width and plan.output_height else "Unknown",
        "Output frame rate": _format_fractional_fps(plan.fps),
        "Output video codec": "H.264",
        "Output rate-control mode": plan.mode.value,
        "Target video bitrate": f"{plan.video_bitrate_kbps} kbps",
        "Measured video bitrate": "Pending",
        "Pixel format": "yuv420p",
        "H.264 profile": "High",
        "Output audio codec": "AAC",
        "Target audio bitrate": f"{plan.audio_bitrate_kbps} kbps",
        "Measured audio bitrate": "Pending",
        "Audio sample rate": plan.audio_sample_rate,
        "Audio channels": plan.audio_channels,
        "Output file size": "Pending",
        "Output duration": "Pending",
        "Validation status": "Pending",
    }


def _normalized_ffprobe_container(format_name: Any, output_path: Path | None = None) -> str:
    tokens = [token.strip().lower() for token in str(format_name or "").split(",") if token.strip()]
    suffix = output_path.suffix.lower().lstrip(".") if output_path else ""
    if suffix and (not tokens or suffix in tokens or suffix == "mp4" and "mov" in tokens):
        return suffix
    if "mp4" in tokens:
        return "mp4"
    return _display_value(tokens[0] if tokens else "mp4", "mp4")


def _ffprobe_output_summary(ffprobe_data: dict[str, Any], output_path: Path | None = None) -> dict[str, str]:
    streams = [stream for stream in ffprobe_data.get("streams") or [] if isinstance(stream, dict)]
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
    fmt = ffprobe_data.get("format") if isinstance(ffprobe_data.get("format"), dict) else {}
    width = video.get("width")
    height = video.get("height")
    return {
        "Output status": "Final Output",
        "Output file path": str(output_path or fmt.get("filename") or "Pending"),
        "Output container": _normalized_ffprobe_container(fmt.get("format_name"), output_path),
        "Output resolution": f"{width}x{height}" if width and height else "Unknown",
        "Output frame rate": _format_fractional_fps(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        "Output video codec": _display_value(video.get("codec_name")),
        "Measured video bitrate": _format_bits_per_second_as_kbps(video.get("bit_rate")),
        "Pixel format": _display_value(video.get("pix_fmt")),
        "H.264 profile": _display_value(video.get("profile")),
        "Output audio codec": _display_value(audio.get("codec_name")),
        "Measured audio bitrate": _format_bits_per_second_as_kbps(audio.get("bit_rate")),
        "Audio sample rate": _display_value(audio.get("sample_rate")),
        "Audio channels": _display_value(audio.get("channels")),
        "Output file size": _format_bytes(fmt.get("size")),
        "Output duration": format_duration(fmt.get("duration")),
    }


SUMMARY_COMPARISON_ROWS = [
    ("Format selector", "Source format selector used", None),
    ("Video format ID", "Video format ID", None),
    ("Audio format ID", "Audio format ID", None),
    ("Container/ext", "Source container/ext", "Output container"),
    ("Resolution", "Source resolution", "Output resolution"),
    ("Frame rate", "Source frame rate", "Output frame rate"),
    ("Video codec", "Source video codec", "Output video codec"),
    ("Video bitrate", "Source video bitrate", "Measured video bitrate"),
    ("Audio codec", "Source audio codec", "Output audio codec"),
    ("Audio bitrate", "Source audio bitrate", "Measured audio bitrate"),
    ("Audio sample rate", "Source audio sample rate", "Audio sample rate"),
    ("Audio channels", "Source audio channels", "Audio channels"),
    ("HDR/SDR or pixel format", "HDR/SDR status", "Pixel format"),
    ("File size", "File size estimate", "Output file size"),
    ("Effective/target video bitrate", "Effective H.264-equivalent video bitrate", "Target video bitrate"),
    ("Effective/target audio bitrate", "Effective AAC-equivalent audio bitrate", "Target audio bitrate"),
    ("Selection/status", "Reason selected", "Validation status"),
]


def build_encoding_summary_display(info: dict[str, Any]) -> tuple[str, str]:
    summary = info.get("vodforge_encoding_summary") if isinstance(info.get("vodforge_encoding_summary"), dict) else {}
    source = summary.get("source") if isinstance(summary.get("source"), dict) else {}
    output = summary.get("output") if isinstance(summary.get("output"), dict) else {}
    warnings = summary.get("warnings") if isinstance(summary.get("warnings"), list) else []
    source_lines: list[str] = []
    output_lines: list[str] = []
    for label, source_key, output_key in SUMMARY_COMPARISON_ROWS:
        source_lines.append(f"{label}: {_display_value(source.get(source_key), 'Not available')}")
        output_lines.append(f"{label}: {_display_value(output.get(output_key), 'Not applicable' if output_key is None else 'Not available')}")
    output_lines.extend([
        f"Output status: {_display_value(output.get('Output status'), 'Not available')}",
        f"Output file path: {_display_value(output.get('Output file path'), 'Not produced')}",
        f"Output rate-control mode: {_display_value(output.get('Output rate-control mode'), 'Not available')}",
        f"Validation status: {_display_value(output.get('Validation status'), 'Not available')}",
        f"H.264 profile: {_display_value(output.get('H.264 profile'), 'Not available')}",
        f"Output duration: {_display_value(output.get('Output duration'), 'Not available')}",
    ])
    if output.get("Failure reason"):
        output_lines.append(f"Failure reason: {_display_value(output.get('Failure reason'), 'Unknown')}")
    output_lines.append(f"Warnings: {', '.join(str(w) for w in warnings) if warnings else 'No warnings'}")
    return "\n".join(source_lines), "\n".join(output_lines)


def best_thumbnail(info: dict[str, Any]) -> dict[str, Any] | None:
    thumbs = [thumb for thumb in info.get("thumbnails") or [] if isinstance(thumb, dict) and thumb.get("url")]
    if not thumbs:
        url = info.get("thumbnail")
        return {"url": url} if url else None
    return max(thumbs, key=lambda thumb: ((thumb.get("width") or 0) * (thumb.get("height") or 1), thumb.get("width") or 0))


def _thumbnail_declared_size(thumb: dict[str, Any]) -> int | None:
    for key in ("filesize", "filesize_approx"):
        value = thumb.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
    return None


def best_thumbnail_for_download(info: dict[str, Any], max_bytes: int = THUMBNAIL_MAX_BYTES) -> dict[str, Any] | None:
    """Pick a high-quality thumbnail source without pointlessly fetching known-oversize variants.

    yt-dlp usually exposes several YouTube thumbnail URLs. When it gives a
    filesize/filesize_approx, prefer the largest image already below our target;
    otherwise fall back to the largest source and let Pillow compress/resize the
    saved JPEG. This preserves quality when the metadata is sparse while still
    avoiding obviously huge downloads when smaller variants are available.
    """
    thumbs = [thumb for thumb in info.get("thumbnails") or [] if isinstance(thumb, dict) and thumb.get("url")]
    if not thumbs:
        return best_thumbnail(info)
    known_under = [thumb for thumb in thumbs if (_thumbnail_declared_size(thumb) or max_bytes + 1) <= max_bytes]
    pool = known_under or thumbs
    return max(pool, key=lambda thumb: ((thumb.get("width") or 0) * (thumb.get("height") or 1), thumb.get("width") or 0))


def _clean_windows_component_text(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip()
    # Remove hidden/control formatting characters such as zero-width spaces that
    # make Windows paths impossible to reason about while preserving visible title
    # text. Newlines/tabs collapse to spaces below.
    return "".join(ch for ch in text if unicodedata.category(ch) not in {"Cc", "Cf"})


def _windows_safe_component(value: Any, fallback: str, max_len: int = 80) -> str:
    text = _clean_windows_component_text(value, fallback)
    safe = "".join(ch if ch not in '<>:"/\\|?*\0' else "_" for ch in text).strip(" .")
    safe = " ".join(safe.split())
    if len(safe) > max_len:
        safe = safe[:max_len].rstrip(" ._-…") + "…"
    return safe or fallback


SINGLE_VIDEO_PLAYLIST_ERROR = "This is a playlist URL. Turn off Single video only to process the whole playlist."
PLAYLIST_CONTEXT_QUERY_KEYS = {"list", "index", "start_radio"}


def _url_query_pairs(url: str) -> tuple[urllib.parse.SplitResult, list[tuple[str, str]]]:
    parsed = urllib.parse.urlsplit(url.strip())
    return parsed, urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)


def youtube_url_has_video_id(url: str) -> bool:
    parsed, query = _url_query_pairs(url)
    if any(key.lower() == "v" and value.strip() for key, value in query):
        return True
    host = parsed.netloc.lower().removeprefix("www.")
    path_parts = [part for part in parsed.path.split("/") if part]
    return host == "youtu.be" and bool(path_parts and path_parts[0].strip())


def single_video_url_requires_video_id_error(url: str) -> str | None:
    parsed, query = _url_query_pairs(url)
    has_playlist_context = any(key.lower() == "list" and value.strip() for key, value in query)
    if has_playlist_context and not youtube_url_has_video_id(urllib.parse.urlunsplit(parsed)):
        return SINGLE_VIDEO_PLAYLIST_ERROR
    return None


def clean_single_video_url(url: str) -> str:
    if not youtube_url_has_video_id(url):
        return url.strip()
    parsed, query = _url_query_pairs(url)
    filtered = [(key, value) for key, value in query if key.lower() not in PLAYLIST_CONTEXT_QUERY_KEYS]
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(filtered, doseq=True), parsed.fragment))


def prepare_batch_item_url(url: str) -> tuple[str, bool]:
    """Return the URL/playlist mode to use for one line from a batch URL file.

    Batch files are normally lists of concrete video URLs copied from YouTube.
    Those copied watch URLs often include playlist/mix context (`list=`, `index=`,
    `start_radio=`). Treating each line as a playlist silently expands one line
    into many unrelated videos, including unavailable mix entries. If the line
    names a concrete YouTube video, strip playlist context and force yt-dlp's
    single-video mode for that batch item. Real playlist-only URLs still remain
    playlist jobs.
    """
    if youtube_url_has_video_id(url):
        return clean_single_video_url(url), True
    return url.strip(), False


def playlist_folder_name(info: dict[str, Any]) -> str:
    return _windows_safe_component(info.get("playlist_title") or info.get("title") or info.get("playlist_id") or info.get("id"), "Playlist", max_len=80)


def channel_folder_name(info: dict[str, Any]) -> str:
    return _windows_safe_component(info.get("channel") or info.get("uploader") or info.get("channel_id") or "Unknown Channel", "Unknown Channel", max_len=80)


def video_folder_name(info: dict[str, Any]) -> str:
    video_id = _windows_safe_component(info.get("id"), "", max_len=32)
    suffix = f" [{video_id}]" if video_id else ""
    # _windows_safe_component appends an ellipsis after truncating, so reserve
    # one extra character to keep the final user-facing folder within 96 chars.
    title_max_len = max(1, 95 - len(suffix))
    title = _windows_safe_component(info.get("title"), "video", max_len=title_max_len)
    return f"{title}{suffix}"


def video_output_dir(output_dir: Path, info: dict[str, Any]) -> Path:
    channel_dir = output_dir / channel_folder_name(info)
    if info.get("playlist_title") or info.get("playlist_id"):
        return channel_dir / "playlists" / playlist_folder_name(info) / video_folder_name(info)
    return channel_dir / "videos - no playlist" / video_folder_name(info)


def _path_would_exceed_windows_safe_limit(path: Path) -> bool:
    # Stay below the legacy MAX_PATH boundary because packaged FFmpeg/Explorer and
    # third-party tooling are not guaranteed to be longPathAware on every user PC.
    return len(str(path)) > WINDOWS_SAFE_PATH_LIMIT


def compact_video_folder_name(info: dict[str, Any], max_title_len: int) -> str:
    video_id = _windows_safe_component(info.get("id"), "", max_len=32)
    suffix = f" [{video_id}]" if video_id else ""
    title_text = _clean_windows_component_text(info.get("title"), "video")
    title_safe = "".join(ch if ch not in '<>:"/\\|?*\0' else "_" for ch in title_text).strip(" .")
    title_safe = " ".join(title_safe.split()) or "video"
    if len(title_safe) > max_title_len:
        words: list[str] = []
        used = 0
        for word in title_safe.split():
            next_used = used + len(word) + (1 if words else 0)
            if words and next_used > max_title_len:
                break
            if not words and len(word) > max_title_len:
                words.append(word[:max(1, max_title_len)].rstrip(" ._-…"))
                break
            words.append(word)
            used = next_used
        title_safe = " ".join(words).rstrip(" ._-…") + "…"
    return f"{title_safe}{suffix}"


def shallow_video_output_dir(output_dir: Path, info: dict[str, Any]) -> Path:
    video_id = _windows_safe_component(info.get("id"), "video", max_len=32)
    return output_dir / channel_folder_name(info) / "path-safe videos" / video_id


def compact_video_output_dir(output_dir: Path, info: dict[str, Any], target_file_name: str) -> Path:
    channel_dir = output_dir / channel_folder_name(info)
    if info.get("playlist_title") or info.get("playlist_id"):
        parent = channel_dir / "playlists" / playlist_folder_name(info)
    else:
        parent = channel_dir / "videos - no playlist"
    for max_title_len in range(80, 0, -1):
        candidate = parent / compact_video_folder_name(info, max_title_len)
        if not _path_would_exceed_windows_safe_limit(candidate / target_file_name):
            return candidate
    # Last resort: shallow path-safe directory using just the video ID.
    # This handles cases where the output root + channel name alone are
    # already very deep (e.g. OneDrive paths like
    # C:\Users\Name\OneDrive - org\Downloads\...\Channel\...\file.mp4).
    return shallow_video_output_dir(output_dir, info)


def resolved_video_output_dir(output_dir: Path, info: dict[str, Any], target_file_name: str | None = None) -> Path:
    remembered = info.get("_vodforge_output_dir")
    if remembered:
        return Path(str(remembered))
    primary = video_output_dir(output_dir, info)
    if target_file_name and _path_would_exceed_windows_safe_limit(primary / target_file_name):
        fallback = compact_video_output_dir(output_dir, info, target_file_name)
        write_diagnostic(
            "compact output folder selected: "
            f"primary_length={len(str(primary / target_file_name))} "
            f"fallback={fallback} filename={target_file_name}"
        )
        return fallback
    return primary


def remember_video_output_dir(info: dict[str, Any], target_dir: Path) -> None:
    info["_vodforge_output_dir"] = str(target_dir)


def parse_url_list_text(text: str) -> list[str]:
    urls: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("<") and line.endswith(">") and "|" in line:
            line = line[1:-1].split("|", 1)[0].strip()
        else:
            parts = line.split(maxsplit=1)
            if parts:
                line = parts[0].strip()
        if line.startswith("http://") or line.startswith("https://"):
            urls.append(line)
    return urls


def read_url_list_file(path: Path) -> list[str]:
    return parse_url_list_text(path.read_text(encoding="utf-8-sig"))


def create_staging_dir(output_dir: Path) -> Path:
    staging_root = output_dir / ".yt-dlp-downloader-staging"
    staging = staging_root / uuid.uuid4().hex
    staging.mkdir(parents=True, exist_ok=False)
    return staging


def staging_output_template(staging_dir: Path) -> str:
    # yt-dlp writes only into this per-job staging directory. Final user-facing
    # folders are created later from extracted metadata, so old downloads are
    # never scanned or moved.
    return str(staging_dir / "%(id)s" / "video [%(id)s].%(ext)s")


def iter_video_infos(info: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(info.get("entries"), list):
        videos: list[dict[str, Any]] = []
        for idx, entry in enumerate(info.get("entries") or [], start=1):
            if not isinstance(entry, dict):
                continue
            item = dict(entry)
            item.setdefault("playlist_title", info.get("title") or info.get("playlist_title"))
            item.setdefault("playlist_id", info.get("id") or info.get("playlist_id"))
            item.setdefault("playlist_index", entry.get("playlist_index") or idx)
            videos.append(item)
        return videos
    return [info]


def safe_metadata_filename(info: dict[str, Any]) -> str:
    return "metadata.json"


def compact_video_metadata(info: dict[str, Any], extra_tags: list[str]) -> dict[str, Any]:
    """Keep only copy/useful metadata instead of yt-dlp's huge one-line info dump."""
    thumb = best_thumbnail(info)
    compact: dict[str, Any] = {
        "id": info.get("id"),
        "title": info.get("title"),
        "webpage_url": info.get("webpage_url") or info.get("original_url"),
        "description": build_description_display_text(info),
        "tags": _clean_list(info.get("tags")),
        "extra_tags": _clean_list(extra_tags),
        "categories": _clean_list(info.get("categories")),
        "thumbnail": info.get("thumbnail") or (thumb or {}).get("url"),
        "best_thumbnail": thumb,
        "vodforge_encoding_summary": info.get("vodforge_encoding_summary"),
    }
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}


def write_compact_video_metadata(output_dir: Path, info: dict[str, Any], extra_tags: list[str]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / safe_metadata_filename(info)
    path.write_text(
        json.dumps(compact_video_metadata(info, extra_tags), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def write_all_compact_video_metadata(output_dir: Path, info: dict[str, Any], extra_tags: list[str]) -> list[Path]:
    paths: list[Path] = []
    for video in iter_video_infos(info):
        paths.append(write_compact_video_metadata(video_output_dir(output_dir, video), video, extra_tags))
    return paths


def _find_staged_media_file(staging_dir: Path, video_id: str) -> Path | None:
    candidates = [
        path
        for path in staging_dir.rglob(f"*{video_id}*")
        if path.is_file() and path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}
    ]
    if not candidates:
        candidates = [path for path in staging_dir.rglob("*") if path.is_file() and path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}]
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.stat().st_size))


def video_file_name(info: dict[str, Any], ext: str) -> str:
    title = _windows_safe_component(info.get("title"), "video", max_len=120)
    return f"{title}{ext}"


def package_downloaded_media_from_staging(staging_dir: Path, output_dir: Path, info: dict[str, Any]) -> list[Path]:
    packaged: list[Path] = []
    for video in iter_video_infos(info):
        video_id = str(video.get("id") or "").strip()
        if not video_id:
            continue
        staged = _find_staged_media_file(staging_dir / video_id, video_id) or _find_staged_media_file(staging_dir, video_id)
        if not staged:
            continue
        ext = ".mp4" if staged.suffix.lower() == ".mp4" else staged.suffix.lower()
        target_file_name = video_file_name(video, ext)
        target_dir = resolved_video_output_dir(output_dir, video, target_file_name)
        # If even the shallow fallback + full title filename exceeds the
        # Windows safe limit, use the shallow path-safe directory (just
        # Channel/path-safe videos/VideoID) which keeps the full MP4 title
        # filename while minimizing folder depth. This handles deep output
        # roots (OneDrive, nested user folders) where channel + playlist +
        # video folder + full title filename would exceed Windows limits.
        if _path_would_exceed_windows_safe_limit(target_dir / target_file_name):
            shallow = shallow_video_output_dir(output_dir, video)
            if not _path_would_exceed_windows_safe_limit(shallow / target_file_name):
                target_dir = shallow
                write_diagnostic(f"shallow path-safe directory selected for full-title filename: {target_dir}")
            else:
                # Last resort: the output root itself is so deep that even
                # Channel/path-safe videos/VideoID/FullTitle.mp4 exceeds the
                # limit. Use VideoID/FullTitle.mp4 directly under output root.
                target_dir = output_dir / "path-safe videos" / _windows_safe_component(video.get("id"), "video", max_len=32)
                write_diagnostic(f"emergency shallow directory selected: {target_dir}")
        target_dir.mkdir(parents=True, exist_ok=True)
        remember_video_output_dir(video, target_dir)
        target = target_dir / target_file_name
        if target.exists():
            target.unlink()
        shutil.move(str(staged), str(target))
        packaged.append(target)
    return packaged


def build_vod_ffmpeg_command(
    ffmpeg: str,
    source: Path,
    output: Path,
    video_bitrate_kbps: int = STRICT_VIDEO_BITRATE_KBPS,
    audio_bitrate_kbps: int = STRICT_AUDIO_BITRATE_KBPS,
    audio_sample_rate: str = AUDIO_SAMPLE_RATE,
    audio_channels: str = AUDIO_CHANNELS,
    x264_preset: str = "medium",
    use_nvenc: bool = False,
) -> list[str]:
    """Return the H.264/AAC constrained-CBR command for one calculated export plan."""
    video_bitrate = f"{int(video_bitrate_kbps)}k"
    audio_bitrate = f"{int(audio_bitrate_kbps)}k"
    buffer_size = f"{int(video_bitrate_kbps) * 2}k"
    video_args = [
        "-c:v", "h264_nvenc",
        "-preset", "p4",
        "-rc", "cbr",
        "-b:v", video_bitrate,
        "-minrate", video_bitrate,
        "-maxrate", video_bitrate,
        "-bufsize", buffer_size,
        "-pix_fmt", "yuv420p",
        "-profile:v", "high",
    ] if use_nvenc else [
        "-c:v", "libx264",
        "-preset", x264_preset,
        "-b:v", video_bitrate,
        "-minrate", video_bitrate,
        "-maxrate", video_bitrate,
        "-bufsize", buffer_size,
        "-pix_fmt", "yuv420p",
        "-profile:v", "high",
        "-x264-params", "nal-hrd=cbr:force-cfr=1",
    ]
    return [
        ffmpeg, "-y", "-i", str(source),
        "-map", "0:v:0",
        "-map", "0:a:0?",
        *video_args,
        "-movflags", "+faststart",
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        "-ar", str(audio_sample_rate),
        "-ac", str(audio_channels),
        "-nostats",
        "-progress", "pipe:1",
        str(output),
    ]


def cleanup_legacy_encode_sidecars(video_path: Path) -> None:
    """Remove old VBR/passlog sidecars from earlier VODForge builds."""
    if not video_path.parent.exists():
        return
    prefixes = [
        BACKEND_TEMP_OUTPUT_NAME,
        BACKEND_ORIGINAL_BACKUP_NAME,
        f"{video_path.stem}.ffmpeg-passlog",
        f"{video_path.stem}.vodforge-cbr-tmp",
        f"{video_path.stem}.vodforge-tmp",
        f"{video_path.stem}.pre-vodforge",
    ]
    for sidecar in video_path.parent.iterdir():
        if sidecar == video_path or not sidecar.is_file():
            continue
        if any(sidecar.name.startswith(prefix) for prefix in prefixes):
            sidecar.unlink(missing_ok=True)


def run_ffprobe_json(ffprobe: str, path: Path) -> dict[str, Any]:
    startupinfo = None
    creationflags = 0
    if sys.platform.startswith("win"):
        startupinfo = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        startupinfo=startupinfo,
        creationflags=creationflags,
    )
    return json.loads(result.stdout or "{}")


def _ffprobe_for_ffmpeg(ffmpeg: str) -> str | None:
    ffmpeg_path = Path(ffmpeg)
    sibling_names = ["ffprobe.exe", "ffprobe"] if sys.platform.startswith("win") else ["ffprobe", "ffprobe.exe"]
    for name in sibling_names:
        candidate = ffmpeg_path.with_name(name)
        if candidate.exists():
            return str(candidate)
    return shutil.which("ffprobe")


def _ffprobe_duration_seconds(ffprobe: str, path: Path) -> float | None:
    try:
        data = run_ffprobe_json(ffprobe, path)
    except Exception:
        return None
    streams = data.get("streams") if isinstance(data, dict) else None
    if not any(isinstance(stream, dict) and stream.get("codec_type") == "video" for stream in (streams or [])):
        return None
    try:
        duration = float(((data.get("format") or {}) if isinstance(data, dict) else {}).get("duration") or 0)
    except (TypeError, ValueError):
        return None
    return duration if duration > 0 else None


def _nonzero_transcode_output_is_usable(temp_output: Path, ffmpeg: str, expected_duration_seconds: float | None) -> bool:
    if not temp_output.exists() or temp_output.stat().st_size <= 0:
        return False
    if not expected_duration_seconds or expected_duration_seconds <= 0:
        return False
    ffprobe = _ffprobe_for_ffmpeg(ffmpeg)
    if not ffprobe:
        return False
    output_duration = _ffprobe_duration_seconds(ffprobe, temp_output)
    if output_duration is None:
        return False
    return output_duration >= expected_duration_seconds * 0.98


def transcode_temp_paths(video_path: Path) -> tuple[Path, Path]:
    return video_path.with_name(BACKEND_TEMP_OUTPUT_NAME), video_path.with_name(BACKEND_ORIGINAL_BACKUP_NAME)


def transcode_to_vod_streaming_settings(
    path: Path,
    ffmpeg: str,
    plan: ExportPlan | None = None,
    *,
    duration_seconds: float | None = None,
    progress_callback: Any | None = None,
    use_nvenc: bool = False,
    control_check: Any | None = None,
) -> Path:
    """Re-encode an MP4 to H.264/AAC using Auto CBR, Strict Compliance, or manual per-file targets."""
    if path.suffix.lower() != ".mp4" or not path.exists():
        return path
    temp_output, backup = transcode_temp_paths(path)
    video_bitrate = plan.video_bitrate_kbps if plan else STRICT_VIDEO_BITRATE_KBPS
    audio_bitrate = plan.audio_bitrate_kbps if plan else STRICT_AUDIO_BITRATE_KBPS
    audio_sample_rate = plan.audio_sample_rate if plan else AUDIO_SAMPLE_RATE
    audio_channels = plan.audio_channels if plan else AUDIO_CHANNELS
    x264_preset = plan.x264_preset if plan else "medium"

    cleanup_legacy_encode_sidecars(path)
    if temp_output.exists():
        temp_output.unlink()
    if backup.exists():
        backup.unlink()

    startupinfo = None
    creationflags = 0
    if sys.platform.startswith("win"):
        startupinfo = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        command = build_vod_ffmpeg_command(
            ffmpeg,
            path,
            temp_output,
            video_bitrate_kbps=video_bitrate,
            audio_bitrate_kbps=audio_bitrate,
            audio_sample_rate=audio_sample_rate,
            audio_channels=audio_channels,
            x264_preset=x264_preset,
            use_nvenc=use_nvenc,
        )
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        output_lines: list[str] = []
        assert process.stdout is not None
        for line in process.stdout:
            if control_check is not None:
                try:
                    control_check()
                except Exception:
                    try:
                        process.terminate()
                    except Exception:
                        pass
                    raise
            text_line = line.strip()
            if text_line:
                output_lines.append(text_line)
                output_lines = output_lines[-80:]
            if progress_callback and duration_seconds:
                key, sep, value = text_line.partition("=")
                if sep and key == "out_time_ms":
                    try:
                        fraction = min(1.0, max(0.0, (float(value) / 1_000_000) / float(duration_seconds)))
                        progress_callback(fraction)
                    except (TypeError, ValueError, ZeroDivisionError):
                        pass
        return_code = process.wait()
        if return_code != 0:
            tail = "\n".join(output_lines[-40:])
            if _nonzero_transcode_output_is_usable(temp_output, ffmpeg, duration_seconds):
                write_diagnostic(
                    f"ffmpeg exited with code {return_code} for {path.name}, "
                    "but the temporary output validated close to source duration; accepting output"
                )
            else:
                raise RuntimeError(f"VODForge H.264/AAC CBR transcode failed for {path.name}; ffmpeg exited with code {return_code}: {tail[-4000:]}")
        if progress_callback:
            progress_callback(1.0)
        path.replace(backup)
        temp_output.replace(path)
        backup.unlink(missing_ok=True)
        return path
    except Exception as exc:
        if temp_output.exists():
            temp_output.unlink()
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(f"VODForge H.264/AAC CBR transcode failed for {path.name}: {exc}") from exc


def _save_jpeg_under_size(image: Any, path: Path, max_bytes: int = THUMBNAIL_MAX_BYTES) -> None:
    rgb = image.convert("RGB")
    best_data: bytes | None = None

    def encode(candidate: Any, quality: int) -> bytes:
        from io import BytesIO

        buf = BytesIO()
        candidate.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
        return buf.getvalue()

    for quality in (92, 88, 84, 80, 76, 72, 68, 64, 60, 55, 50, 45):
        data = encode(rgb, quality)
        if best_data is None or len(data) < len(best_data):
            best_data = data
        if len(data) <= max_bytes:
            path.write_bytes(data)
            return

    working = rgb
    while min(working.size) > 16:
        assert best_data is not None
        shrink = max(0.50, min(0.90, (max_bytes / len(best_data)) ** 0.5 * 0.95))
        new_size = (max(16, int(working.size[0] * shrink)), max(16, int(working.size[1] * shrink)))
        if new_size == working.size:
            new_size = (max(16, working.size[0] - 1), max(16, working.size[1] - 1))
        resample = getattr(Image, "Resampling", Image).LANCZOS
        working = working.resize(new_size, resample)
        for quality in (82, 76, 70, 64, 58, 52, 46, 40, 34, 28, 20, 12, 5):
            data = encode(working, quality)
            if best_data is None or len(data) < len(best_data):
                best_data = data
            if len(data) <= max_bytes:
                path.write_bytes(data)
                return

    assert best_data is not None
    if len(best_data) > max_bytes:
        raise RuntimeError(f"Unable to compress thumbnail below {max_bytes} bytes")
    path.write_bytes(best_data)


def save_thumbnail_image(output_dir: Path, info: dict[str, Any]) -> Path | None:
    thumb = best_thumbnail_for_download(info)
    url = str((thumb or {}).get("url") or "")
    if not url:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "thumbnail.jpeg"
    with urllib.request.urlopen(url, timeout=30) as response:
        data = response.read()
    if Image is None:
        if len(data) > THUMBNAIL_MAX_BYTES:
            raise RuntimeError("Pillow is required to enforce the 300 KB thumbnail limit")
        path.write_bytes(data)
        return path
    from io import BytesIO

    image = Image.open(BytesIO(data)).convert("RGB")
    _save_jpeg_under_size(image, path)
    return path


def _quality_max_height(label: str) -> int:
    if "2160" in label or "4K" in label:
        return 2160
    if "1440" in label or "2K" in label:
        return 1440
    if "720" in label:
        return 720
    if "480" in label:
        return 480
    if "360" in label:
        return 360
    return DEFAULT_MAX_HEIGHT


def _plans_by_video_id(info: dict[str, Any], mode: ExportMode, max_height: int) -> dict[str, ExportPlan]:
    plans: dict[str, ExportPlan] = {}
    for item in iter_video_infos(info):
        if item.get("formats"):
            plan = build_auto_export_plan(item, mode=mode, max_height=max_height)
            video_id = str(item.get("id") or "").strip()
            if video_id:
                plans[video_id] = plan
    if not plans and info.get("formats"):
        plan = build_auto_export_plan(info, mode=mode, max_height=max_height)
        video_id = str(info.get("id") or "").strip()
        if video_id:
            plans[video_id] = plan
    return plans


@dataclass(frozen=True)
class ManualExportSettings:
    video_bitrate_kbps: int = STRICT_VIDEO_BITRATE_KBPS
    audio_bitrate_kbps: int = STRICT_AUDIO_BITRATE_KBPS
    audio_sample_rate: str = AUDIO_SAMPLE_RATE
    audio_channels: str = AUDIO_CHANNELS
    x264_preset: str = "medium"


COOKIE_BROWSER_OPTIONS = ["None", "Chrome", "Edge", "Firefox", "Brave", "Chromium", "Opera", "Vivaldi"]
COOKIE_BROWSER_VALUES = {
    "Chrome": "chrome",
    "Edge": "edge",
    "Firefox": "firefox",
    "Brave": "brave",
    "Chromium": "chromium",
    "Opera": "opera",
    "Vivaldi": "vivaldi",
}
WINDOWS_CHROMIUM_COOKIE_BROWSERS = {"brave", "chrome", "chromium", "edge", "opera", "vivaldi"}
WINDOWS_CHROMIUM_COOKIE_MESSAGE = (
    "Chrome/Edge/Brave/Chromium browser-cookie import is unreliable on Windows because Chromium locks its cookie database. "
    "Use Load Cookies… with an exported YouTube cookies.txt file, choose Firefox browser cookies, or turn off Use YouTube cookies."
)


@dataclass
class DownloadJob:
    url: str
    output_dir: Path
    quality_label: str
    export_mode: ExportMode
    manual_settings: ManualExportSettings
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


def browser_cookie_value(label_or_value: str | None) -> str | None:
    text = str(label_or_value or "").strip()
    if not text or text.lower() == "none":
        return None
    return COOKIE_BROWSER_VALUES.get(text, text.lower())


def windows_chromium_cookie_warning(cookie_browser: str | None, platform: str | None = None) -> str | None:
    platform = sys.platform if platform is None else platform
    browser = browser_cookie_value(cookie_browser)
    if platform.startswith("win") and browser in WINDOWS_CHROMIUM_COOKIE_BROWSERS:
        return WINDOWS_CHROMIUM_COOKIE_MESSAGE
    return None


def format_ytdlp_user_error(error: Any) -> str:
    message = str(error)
    lower = message.lower()
    if "could not copy chrome cookie database" in lower or "github.com/yt-dlp/yt-dlp/issues/7271" in lower:
        return f"{WINDOWS_CHROMIUM_COOKIE_MESSAGE}\n\nOriginal yt-dlp error: {message}"
    if "http error 503" in lower or "503: service unavailable" in lower:
        return (
            "YouTube returned HTTP 503 Service Unavailable after retries. This is usually temporary, rate-limit/CDN related, "
            "or a sign that YouTube wants authenticated cookies. Retry once; if it persists, use Load Cookies… with an exported "
            "YouTube cookies.txt file or Firefox browser cookies.\n\n"
            f"Original yt-dlp error: {message}"
        )
    if "video unavailable" in lower or "this video is not available" in lower or "this content isn't available" in lower:
        return (
            "YouTube reported this video as unavailable. Common causes:\n"
            "• The video is private, deleted, or region-restricted.\n"
            "• The video is marked 'for kids' and yt-dlp's fallback client cannot access it.\n"
            "• No JavaScript runtime (Deno 2.x) is installed, which limits which YouTube clients yt-dlp can use.\n"
            "Try: 1) Retry, 2) Install Deno 2.x, 3) Use cookies (Load Cookies…), 4) Verify the video plays in a browser.\n\n"
            f"Original yt-dlp error: {message}"
        )
    if "no video formats found" in lower or "no usable" in lower and "video" in lower:
        return (
            "yt-dlp could not find any downloadable video formats. This usually means:\n"
            "• No JavaScript runtime (Deno 2.x) is installed — YouTube returns very limited formats without one.\n"
            "• YouTube is rate-limiting the connection — try again later or use cookies.\n"
            "• The video requires authentication — use Load Cookies… with a YouTube cookies.txt file.\n\n"
            f"Original yt-dlp error: {message}"
        )
    if "no supported javascript runtime" in lower or "js runtime" in lower:
        return (
            "No JavaScript runtime was found. YouTube extraction without a JS runtime (Deno 2.x) is deprecated "
            "and causes some videos to fail. Install Deno 2.0+ or use --js-runtimes node as a fallback.\n\n"
            f"Original yt-dlp error: {message}"
        )
    if "requested format is not available" in lower:
        return (
            "The format selected during analysis is no longer available for download. This can happen when "
            "YouTube rotates format IDs between analysis and download. VODForge will retry with a broader "
            "format fallback. If this persists, try a different quality setting.\n\n"
            f"Original yt-dlp error: {message}"
        )
    if "sign in to confirm" in lower or "confirm you're not a bot" in lower:
        return (
            "YouTube is asking for sign-in confirmation (bot detection). Use Load Cookies… with an exported "
            "YouTube cookies.txt file or choose a browser under Browser cookies to authenticate.\n\n"
            f"Original yt-dlp error: {message}"
        )
    return message


def apply_ytdlp_cookie_options(
    opts: dict[str, Any],
    *,
    use_cookies: bool,
    cookie_file: Path | str | None,
    cookie_browser: str | None = None,
) -> dict[str, Any]:
    if not use_cookies:
        return opts
    if cookie_file:
        opts["cookiefile"] = str(cookie_file)
        return opts
    browser = browser_cookie_value(cookie_browser)
    warning = windows_chromium_cookie_warning(browser)
    if warning:
        raise RuntimeError(warning)
    if browser:
        opts["cookiesfrombrowser"] = (browser,)
    return opts


def apply_youtube_extractor_args(opts: dict[str, Any]) -> dict[str, Any]:
    """Configure YouTube extractor to try multiple player clients.

    yt-dlp's built-in default clients are ``android_vr`` and ``web_safari``.
    ``android_vr`` cannot access videos marked "for kids" and returns fewer
    formats.  Adding ``android`` fixes that, but we avoid ``web`` because it
    does a separate full extraction pass with JS challenge solving that
    duplicates what ``web_safari`` already provides — adding ~2-4s per video
    on machines with Deno installed.

    NOTE: yt-dlp 2026.x expects player_client as a *list* of client names,
    not a comma-separated string.  Passing a string like "default,android"
    causes yt-dlp to iterate over individual characters ("d","e","f",...)
    and silently skip every "unsupported client", falling back to the
    built-in defaults which fail on some videos.

    See: https://github.com/yt-dlp/yt-dlp/issues/16556
    """
    existing = opts.get("extractor_args", {})
    if not isinstance(existing, dict):
        existing = {}
    youtube_args = existing.get("youtube", {})
    if not isinstance(youtube_args, dict):
        youtube_args = {}
    # Don't overwrite an explicit player_client if the caller set one.
    # Order matters: web_safari is tried first (gets all formats via Deno),
    # android is the fallback (no JS needed, handles "for kids" videos).
    if "player_client" not in youtube_args:
        youtube_args["player_client"] = ["web_safari", "android"]
    existing["youtube"] = youtube_args
    opts["extractor_args"] = existing
    return opts


class ToolTip:
    """Small hover tooltip for Tk/ttk widgets."""

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _event: Any = None) -> None:
        if self.tip is not None or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
            self.tip = tk.Toplevel(self.widget)
            self.tip.wm_overrideredirect(True)
            self.tip.wm_geometry(f"+{x}+{y}")
            label = tk.Label(
                self.tip,
                text=self.text,
                justify="left",
                wraplength=320,
                bg="#111214",
                fg=THEME["text"],
                relief="solid",
                borderwidth=1,
                padx=8,
                pady=6,
                font=FONT_UI_SMALL,
            )
            label.pack()
        except tk.TclError:
            self.tip = None

    def hide(self, _event: Any = None) -> None:
        if self.tip is not None:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = None


class QueueLogger:
    def __init__(self, events: queue.Queue[tuple[str, Any]] | None = None, *, diagnostic_prefix: str = "yt-dlp"):
        self.events = events
        self.diagnostic_prefix = diagnostic_prefix

    def debug(self, msg: str) -> None:
        if msg:
            write_diagnostic(f"{self.diagnostic_prefix} DEBUG: {msg}")
        if self.events is not None and msg and not msg.startswith("["):
            self.events.put(("log", msg))

    def warning(self, msg: str) -> None:
        write_diagnostic(f"{self.diagnostic_prefix} WARNING: {msg}")
        if self.events is not None:
            self.events.put(("log", f"WARNING: {msg}"))

    def error(self, msg: str) -> None:
        write_diagnostic(f"{self.diagnostic_prefix} ERROR: {msg}")
        if self.events is not None:
            self.events.put(("log", f"ERROR: {msg}"))


class DownloaderApp(tk.Tk):
    def __init__(self) -> None:
        reset_diagnostics_log()
        write_diagnostic(f"app start: name={APP_NAME} frozen={getattr(sys, 'frozen', False)} executable={sys.executable} argv={sys.argv}")
        write_diagnostic(f"diagnostics log path: {DIAGNOSTICS_LOG_PATH}")
        if yt_dlp is not None:
            write_diagnostic(f"yt-dlp version: {getattr(yt_dlp.version, '__version__', 'unknown')}")
        else:
            write_diagnostic(f"yt-dlp import failed: {YTDLP_IMPORT_ERROR}")
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1180x900")
        self.minsize(980, 760)
        self.configure(bg=THEME["bg"])

        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.update_worker: threading.Thread | None = None
        self.cancel_requested = False
        self.skip_video_requested = False
        self.skip_url_requested = False

        self.url_var = tk.StringVar()
        self.url_list_file_var = tk.StringVar(value="No URL list loaded")
        self.batch_urls: list[str] = []
        self.output_var = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.quality_var = tk.StringVar(value="1080p Full HD")
        self.export_mode_var = tk.StringVar(value=ExportMode.AUTO_CBR.value)
        self.manual_video_bitrate_var = tk.StringVar(value=str(STRICT_VIDEO_BITRATE_KBPS))
        self.manual_audio_bitrate_var = tk.StringVar(value=str(STRICT_AUDIO_BITRATE_KBPS))
        self.manual_sample_rate_var = tk.StringVar(value=AUDIO_SAMPLE_RATE)
        self.manual_channels_var = tk.StringVar(value="Stereo")
        self.manual_preset_var = tk.StringVar(value="medium")
        self.tags_var = tk.StringVar()
        self.single_video_only_var = tk.BooleanVar(value=False)
        self.use_nvenc_var = tk.BooleanVar(value=False)
        self.use_cookies_var = tk.BooleanVar(value=False)
        self.cookie_file_path: Path | None = None
        self.cookie_file_var = tk.StringVar(value="No cookies loaded")
        self.cookie_browser_var = tk.StringVar(value="None")
        self.embed_thumbnail_var = tk.BooleanVar(value=True)
        self.write_thumbnail_var = tk.BooleanVar(value=True)
        self.embed_metadata_var = tk.BooleanVar(value=True)
        self.write_info_json_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.thumbnail_image: Any | None = None
        self.last_thumbnail_url: str | None = None
        self.metadata_items: list[dict[str, Any]] = []
        self.download_history: list[dict[str, Any]] = []
        self.history_path = history_file_path()
        self.last_output_dirs: list[Path] = []
        self.video_output_dirs_by_id: dict[str, Path] = {}
        self._active_progress_context: tuple[int, int, float, float] | None = None

        self._apply_theme()
        self._build_ui()
        self._load_download_history()
        self._check_runtime()
        self.after(100, self._pump_events)

    def _apply_theme(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=THEME["bg"], foreground=THEME["text"], font=FONT_UI)
        style.configure("TFrame", background=THEME["bg"])
        style.configure("Panel.TFrame", background=THEME["panel"])
        style.configure("Card.TFrame", background=THEME["surface"], relief="flat")
        style.configure("TLabel", background=THEME["bg"], foreground=THEME["text"], font=FONT_UI)
        style.configure("Muted.TLabel", background=THEME["bg"], foreground=THEME["muted"], font=FONT_UI_SMALL)
        style.configure("Hero.TLabel", background=THEME["bg"], foreground=THEME["text"], font=FONT_TITLE)
        style.configure("Accent.TLabel", background=THEME["bg"], foreground=THEME["accent"], font=FONT_UI_MEDIUM)
        style.configure("TLabelframe", background=THEME["bg"], foreground=THEME["text"], bordercolor=THEME["border"], relief="solid")
        style.configure("TLabelframe.Label", background=THEME["bg"], foreground=THEME["accent"], font=FONT_UI_MEDIUM)
        style.configure("TEntry", fieldbackground=THEME["surface"], foreground=THEME["text"], insertcolor=THEME["text"], bordercolor=THEME["border"], lightcolor=THEME["border"], darkcolor=THEME["border"], padding=7)
        style.configure("TCombobox", fieldbackground=THEME["surface"], foreground=THEME["text"], background=THEME["surface"], arrowcolor=THEME["accent"], bordercolor=THEME["border"], padding=6)
        style.map("TCombobox", fieldbackground=[("readonly", THEME["surface"]), ("active", THEME["surface_2"])], foreground=[("readonly", THEME["text"])])
        style.configure("TButton", background=THEME["surface_2"], foreground=THEME["text"], bordercolor=THEME["border"], focusthickness=1, focuscolor=THEME["accent"], padding=(12, 7), font=FONT_UI_MEDIUM)
        style.map("TButton", background=[("active", THEME["border"]), ("pressed", THEME["accent_dark"]), ("disabled", THEME["panel"])], foreground=[("disabled", THEME["subtle"])])
        style.configure("Accent.TButton", background=THEME["accent_dark"], foreground="#ffffff", bordercolor=THEME["accent"])
        style.map("Accent.TButton", background=[("active", THEME["accent"]), ("pressed", THEME["accent_dark"]), ("disabled", THEME["panel"])])
        style.configure("TCheckbutton", background=THEME["bg"], foreground=THEME["text"], indicatorcolor=THEME["surface"], font=FONT_UI)
        style.map("TCheckbutton", background=[("active", THEME["bg"])], foreground=[("disabled", THEME["subtle"])])
        style.configure("TProgressbar", background=THEME["accent"], troughcolor=THEME["surface"], bordercolor=THEME["border"], lightcolor=THEME["accent"], darkcolor=THEME["accent_dark"])
        style.configure("TNotebook", background=THEME["panel"], borderwidth=0, tabmargins=(8, 6, 8, 0))
        style.configure("TNotebook.Tab", background=THEME["surface"], foreground=THEME["muted"], padding=(18, 9), font=FONT_UI_MEDIUM, bordercolor=THEME["border"])
        style.map("TNotebook.Tab", background=[("selected", THEME["accent_dark"]), ("active", THEME["surface_2"])], foreground=[("selected", "#ffffff"), ("active", THEME["text"])], expand=[("selected", (0, 0, 0, 0))])
        style.configure("Treeview", background=THEME["surface"], fieldbackground=THEME["surface"], foreground=THEME["text"], bordercolor=THEME["border"], rowheight=30, font=FONT_UI)
        style.configure("Treeview.Heading", background=THEME["panel"], foreground=THEME["muted"], relief="flat", font=FONT_UI_SMALL_MEDIUM)
        style.map("Treeview", background=[("selected", THEME["accent_dark"])], foreground=[("selected", "#ffffff")])
        self.option_add("*TCombobox*Listbox.background", THEME["surface"])
        self.option_add("*TCombobox*Listbox.foreground", THEME["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", THEME["accent_dark"])

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 6}

        shell = ttk.Frame(self, style="Panel.TFrame")
        shell.pack(fill="both", expand=True, padx=14, pady=14)

        hero = ttk.Frame(shell, style="Panel.TFrame")
        hero.pack(fill="x", padx=16, pady=(12, 4))
        hero_header = ttk.Frame(hero, style="Panel.TFrame")
        hero_header.pack(fill="x")
        ttk.Label(hero_header, text="⬇ VODForge", style="Hero.TLabel").pack(side="left", anchor="w")
        self.update_button = ttk.Button(hero_header, text="Check for updates", command=self._check_for_updates)
        self.update_button.pack(side="right", anchor="e")
        ttk.Label(
            hero,
            text="VOD-ready MP4 downloads with H.264 CBR video, AAC audio, thumbnails, compact metadata, tags, and playlist packaging.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(3, 0))
        ttk.Label(hero, text=f"Midnight Violet build · v{__version__}", style="Accent.TLabel").pack(anchor="w", pady=(6, 0))

        self.main_notebook = ttk.Notebook(shell)
        self.main_notebook.pack(fill="both", expand=True, padx=4, pady=(8, 4))
        download_tab = ttk.Frame(self.main_notebook, style="Panel.TFrame")
        metadata_tab = ttk.Frame(self.main_notebook, style="Panel.TFrame")
        self.download_tab = download_tab
        self.metadata_tab = metadata_tab
        self.main_notebook.add(download_tab, text="Download")
        self.main_notebook.add(metadata_tab, text="Metadata Browser")

        download_tab.columnconfigure(0, weight=1)
        download_tab.columnconfigure(1, weight=1)
        download_tab.rowconfigure(5, weight=1)

        url_frame = ttk.LabelFrame(download_tab, text="Source")
        url_frame.grid(row=0, column=0, columnspan=2, sticky="ew", **pad)
        ttk.Label(url_frame, text="YouTube URL").grid(row=0, column=0, sticky="w", padx=10, pady=10)
        ttk.Entry(url_frame, textvariable=self.url_var).grid(row=0, column=1, sticky="ew", padx=10, pady=10)
        self.preview_metadata_button = ttk.Button(url_frame, text="Preview Metadata", command=self._fetch_metadata)
        self.preview_metadata_button.grid(row=0, column=2, sticky="e", padx=10, pady=10)
        ttk.Label(url_frame, text="Batch URL text file").grid(row=1, column=0, sticky="w", padx=10, pady=(0, 10))
        ttk.Label(url_frame, textvariable=self.url_list_file_var, style="Muted.TLabel").grid(row=1, column=1, sticky="w", padx=10, pady=(0, 10))
        ttk.Button(url_frame, text="Load URL List…", command=self._load_url_list_file).grid(row=1, column=2, sticky="e", padx=10, pady=(0, 10))
        ttk.Label(url_frame, text="YouTube cookies.txt").grid(row=2, column=0, sticky="w", padx=10, pady=(0, 10))
        ttk.Label(url_frame, textvariable=self.cookie_file_var, style="Muted.TLabel").grid(row=2, column=1, sticky="w", padx=10, pady=(0, 10))
        ttk.Button(url_frame, text="Load Cookies…", command=self._load_cookie_file).grid(row=2, column=2, sticky="e", padx=10, pady=(0, 10))
        ttk.Label(url_frame, text="Browser cookies").grid(row=3, column=0, sticky="w", padx=10, pady=(0, 10))
        ttk.Combobox(
            url_frame,
            textvariable=self.cookie_browser_var,
            values=COOKIE_BROWSER_OPTIONS,
            state="readonly",
            width=18,
        ).grid(row=3, column=1, sticky="w", padx=10, pady=(0, 10))
        url_frame.columnconfigure(1, weight=1)

        out_frame = ttk.LabelFrame(download_tab, text="Destination")
        out_frame.grid(row=1, column=0, sticky="ew", **pad)
        ttk.Label(out_frame, text="Output folder").grid(row=0, column=0, sticky="w", padx=10, pady=10)
        ttk.Entry(out_frame, textvariable=self.output_var).grid(row=0, column=1, sticky="ew", padx=10, pady=10)
        ttk.Button(out_frame, text="Browse…", command=self._browse_output).grid(row=0, column=2, sticky="e", padx=10, pady=10)
        out_frame.columnconfigure(1, weight=1)

        options = ttk.LabelFrame(download_tab, text="Download Options")
        options.grid(row=1, column=1, rowspan=2, sticky="nsew", **pad)
        ttk.Label(options, text="Quality ceiling").grid(row=0, column=0, sticky="w", padx=10, pady=8)
        ttk.Combobox(
            options,
            textvariable=self.quality_var,
            values=list(QUALITY_OPTIONS.keys()),
            state="readonly",
            width=26,
        ).grid(row=0, column=1, sticky="ew", padx=10, pady=8)
        ttk.Label(options, text="Output mode").grid(row=1, column=0, sticky="w", padx=10, pady=8)
        export_mode_combo = ttk.Combobox(
            options,
            textvariable=self.export_mode_var,
            values=EXPORT_MODES,
            state="readonly",
            width=26,
        )
        export_mode_combo.grid(row=1, column=1, sticky="ew", padx=10, pady=8)
        export_mode_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_manual_settings_visibility())
        ttk.Label(options, text="Extra tags").grid(row=2, column=0, sticky="w", padx=10, pady=8)
        ttk.Entry(options, textvariable=self.tags_var).grid(row=2, column=1, sticky="ew", padx=10, pady=8)
        ttk.Checkbutton(options, text="Embed thumbnail", variable=self.embed_thumbnail_var).grid(row=3, column=0, sticky="w", padx=10, pady=4)
        ttk.Checkbutton(options, text="Save thumbnail", variable=self.write_thumbnail_var).grid(row=3, column=1, sticky="w", padx=10, pady=4)
        ttk.Checkbutton(options, text="Embed metadata", variable=self.embed_metadata_var).grid(row=4, column=0, sticky="w", padx=10, pady=4)
        ttk.Checkbutton(options, text="Save compact JSON", variable=self.write_info_json_var).grid(row=4, column=1, sticky="w", padx=10, pady=4)
        ttk.Checkbutton(options, text="Single video only (ignore playlist)", variable=self.single_video_only_var).grid(row=5, column=0, columnspan=2, sticky="w", padx=10, pady=4)
        nvenc_label = "Use NVIDIA NVENC GPU encoding"
        if sys.platform == "darwin":
            nvenc_label += " (not available on macOS)"
        nvenc_checkbox = ttk.Checkbutton(options, text=nvenc_label, variable=self.use_nvenc_var)
        nvenc_checkbox.grid(row=6, column=0, columnspan=2, sticky="w", padx=10, pady=4)
        if sys.platform == "darwin":
            self.use_nvenc_var.set(False)
            nvenc_checkbox.state(["disabled"])
        ttk.Checkbutton(options, text="Use YouTube cookies", variable=self.use_cookies_var).grid(row=7, column=0, columnspan=2, sticky="w", padx=10, pady=4)

        self.manual_settings_frame = ttk.LabelFrame(options, text="Manual Override Settings")
        self.manual_settings_frame.grid(row=8, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 8))
        ttk.Label(self.manual_settings_frame, text="Video bitrate (kbps)").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(self.manual_settings_frame, textvariable=self.manual_video_bitrate_var, width=12).grid(row=0, column=1, sticky="ew", padx=8, pady=6)
        self._manual_help_icon(0, "Target video bitrate for the H.264 encode. Higher = larger file and more CPU time; it cannot add detail beyond the source.")
        ttk.Label(self.manual_settings_frame, text="Audio bitrate (kbps)").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(self.manual_settings_frame, textvariable=self.manual_audio_bitrate_var, width=12).grid(row=1, column=1, sticky="ew", padx=8, pady=6)
        self._manual_help_icon(1, "Target AAC audio bitrate. 192 kbps is usually enough; 320 kbps matches the VOD preset but may exceed source quality.")
        ttk.Label(self.manual_settings_frame, text="Sample rate").grid(row=2, column=0, sticky="w", padx=8, pady=6)
        ttk.Combobox(self.manual_settings_frame, textvariable=self.manual_sample_rate_var, values=["44100", "48000"], state="readonly", width=10).grid(row=2, column=1, sticky="ew", padx=8, pady=6)
        self._manual_help_icon(2, "Audio samples per second. Use 48000 for video/streaming; use 44100 only when matching music/audio sources.")
        ttk.Label(self.manual_settings_frame, text="Channels").grid(row=3, column=0, sticky="w", padx=8, pady=6)
        ttk.Combobox(self.manual_settings_frame, textvariable=self.manual_channels_var, values=["Mono", "Stereo"], state="readonly", width=10).grid(row=3, column=1, sticky="ew", padx=8, pady=6)
        self._manual_help_icon(3, "Output audio layout. Stereo is normal for YouTube/VOD; Mono is only for speech-first files or smaller audio.")
        ttk.Label(self.manual_settings_frame, text="x264 preset").grid(row=4, column=0, sticky="w", padx=8, pady=6)
        ttk.Combobox(self.manual_settings_frame, textvariable=self.manual_preset_var, values=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower"], state="readonly", width=10).grid(row=4, column=1, sticky="ew", padx=8, pady=6)
        self._manual_help_icon(4, "Encoder speed/efficiency tradeoff. Ultrafast = quickest but bigger/lower quality; slower = better compression but heavier CPU. Medium is safest.")
        ttk.Label(
            self.manual_settings_frame,
            text="Codec stays H.264 + AAC; these fields control the encode profile used when Manual Override is selected. x264 preset applies only when NVENC is off.",
            style="Muted.TLabel",
            wraplength=360,
            justify="left",
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=8, pady=(4, 8))
        self.manual_settings_frame.columnconfigure(1, weight=1)
        self._refresh_manual_settings_visibility()
        options.columnconfigure(1, weight=1)

        quick_meta = ttk.LabelFrame(download_tab, text="Metadata Preview")
        quick_meta.grid(row=2, column=0, sticky="nsew", **pad)
        ttk.Label(
            quick_meta,
            text="Use the Metadata Browser tab for the full playlist table, long titles, tags, descriptions, and thumbnails.",
            style="Muted.TLabel",
            wraplength=620,
            justify="left",
        ).pack(anchor="w", padx=10, pady=(10, 4))
        ttk.Button(quick_meta, text="Open Metadata Browser", command=lambda: self.main_notebook.select(metadata_tab), style="Accent.TButton").pack(anchor="w", padx=10, pady=(4, 10))

        progress = ttk.LabelFrame(download_tab, text="Progress")
        progress.grid(row=3, column=0, columnspan=2, sticky="ew", **pad)
        self.progress_bar = ttk.Progressbar(progress, variable=self.progress_var, maximum=100, mode="determinate")
        self.progress_bar.pack(fill="x", padx=10, pady=(10, 5))
        ttk.Label(progress, textvariable=self.status_var, style="Muted.TLabel").pack(anchor="w", padx=10, pady=(0, 10))

        buttons = ttk.Frame(download_tab, style="Panel.TFrame")
        buttons.grid(row=4, column=0, columnspan=2, sticky="ew", **pad)
        self.download_button = ttk.Button(buttons, text="Download MP4", command=self._start_download, style="Accent.TButton")
        self.download_button.pack(side="left", padx=4)
        self.cancel_button = ttk.Button(buttons, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=6)
        self.skip_video_button = ttk.Button(buttons, text="Skip Video", command=self._skip_video, state="disabled")
        self.skip_video_button.pack(side="left", padx=4)
        self.skip_url_button = ttk.Button(buttons, text="Skip URL", command=self._skip_url, state="disabled")
        self.skip_url_button.pack(side="left", padx=4)
        ttk.Button(buttons, text="Open Folder", command=self._open_folder).pack(side="right", padx=4)
        ttk.Button(buttons, text="Open Log Folder", command=self._open_log_folder).pack(side="right", padx=4)

        log_frame = ttk.LabelFrame(download_tab, text="Log")
        log_frame.grid(row=5, column=0, columnspan=2, sticky="nsew", **pad)
        self.log = tk.Text(log_frame, height=10, wrap="word", state="disabled", bg="#050607", fg=THEME["muted"], insertbackground=THEME["text"], relief="flat", padx=10, pady=8, font=FONT_MONO)
        self.log.pack(fill="both", expand=True, padx=10, pady=10)

        metadata_tab.columnconfigure(0, weight=3)
        metadata_tab.columnconfigure(1, weight=2)
        metadata_tab.columnconfigure(2, weight=0, minsize=320)
        metadata_tab.rowconfigure(2, weight=3)
        metadata_tab.rowconfigure(4, weight=2)
        metadata_tab.rowconfigure(5, weight=3)

        meta_buttons = ttk.Frame(metadata_tab, style="Panel.TFrame")
        meta_buttons.grid(row=0, column=0, columnspan=3, sticky="ew", padx=12, pady=(12, 8))
        ttk.Button(meta_buttons, text="Copy Tags", command=self._copy_tags).pack(side="left", padx=5)
        ttk.Button(meta_buttons, text="Copy Description", command=self._copy_description).pack(side="left", padx=5)
        ttk.Button(meta_buttons, text="Copy Thumbnail URL", command=self._copy_thumbnail_url).pack(side="left", padx=5)
        ttk.Button(meta_buttons, text="Open Saved Location", command=self._open_selected_saved_location).pack(side="left", padx=5)
        ttk.Button(meta_buttons, text="Back to Download", command=lambda: self.main_notebook.select(download_tab)).pack(side="right", padx=5)

        ttk.Label(metadata_tab, text="Playlist / Video Queue", style="Accent.TLabel").grid(row=1, column=0, sticky="w", padx=12, pady=(0, 5))
        tree_wrap = ttk.Frame(metadata_tab, style="Card.TFrame")
        tree_wrap.grid(row=2, column=0, rowspan=3, sticky="nsew", padx=12, pady=(0, 12))
        tree_wrap.columnconfigure(0, weight=1)
        tree_wrap.rowconfigure(0, weight=1)
        self.video_tree = ttk.Treeview(
            tree_wrap,
            columns=("index", "title", "duration", "creator", "id", "location"),
            show="headings",
            selectmode="browse",
            height=16,
        )
        self.video_tree.heading("index", text="#")
        self.video_tree.heading("title", text="Title")
        self.video_tree.heading("duration", text="Length")
        self.video_tree.heading("creator", text="Creator")
        self.video_tree.heading("id", text="ID")
        self.video_tree.heading("location", text="Saved Location")
        self.video_tree.column("index", width=56, minwidth=48, stretch=False, anchor="center")
        self.video_tree.column("title", width=620, minwidth=420, stretch=True, anchor="w")
        self.video_tree.column("duration", width=82, minwidth=70, stretch=False, anchor="center")
        self.video_tree.column("creator", width=170, minwidth=110, stretch=False, anchor="w")
        self.video_tree.column("id", width=120, minwidth=90, stretch=False, anchor="w")
        self.video_tree.column("location", width=170, minwidth=120, stretch=False, anchor="w")
        y_scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.video_tree.yview)
        x_scroll = ttk.Scrollbar(tree_wrap, orient="horizontal", command=self.video_tree.xview)
        self.video_tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.video_tree.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=(10, 0))
        y_scroll.grid(row=0, column=1, sticky="ns", pady=(10, 0), padx=(0, 10))
        x_scroll.grid(row=1, column=0, sticky="ew", padx=(10, 0), pady=(0, 10))
        self.video_tree.bind("<<TreeviewSelect>>", self._on_video_selected)

        self.selected_title_var = tk.StringVar(value="Fetch metadata to preview long titles, tags, description, and thumbnails.")
        ttk.Label(metadata_tab, textvariable=self.selected_title_var, wraplength=520, justify="left", style="Muted.TLabel").grid(row=1, column=1, sticky="ew", padx=12, pady=(0, 5))
        ttk.Label(metadata_tab, text="Tags", style="Accent.TLabel").grid(row=2, column=1, sticky="nw", padx=12, pady=(0, 5))
        self.pulled_tags_text = tk.Text(metadata_tab, height=5, wrap="word", bg=THEME["surface"], fg=THEME["text"], insertbackground=THEME["text"], relief="flat", padx=10, pady=8, font=FONT_UI)
        self.pulled_tags_text.grid(row=2, column=1, sticky="nsew", padx=12, pady=(24, 12))
        ttk.Label(metadata_tab, text="Description", style="Accent.TLabel").grid(row=3, column=1, sticky="w", padx=12, pady=(0, 5))
        self.description_text = tk.Text(metadata_tab, height=10, wrap="word", bg=THEME["surface"], fg=THEME["text"], insertbackground=THEME["text"], relief="flat", padx=10, pady=8, font=FONT_UI)
        self.description_text.grid(row=4, column=1, sticky="nsew", padx=12, pady=(0, 12))

        summary_frame = ttk.LabelFrame(metadata_tab, text="Encoding Summary")
        summary_frame.grid(row=5, column=0, columnspan=3, sticky="nsew", padx=12, pady=(0, 12))
        summary_frame.columnconfigure(0, weight=1)
        summary_frame.columnconfigure(1, weight=1)
        summary_frame.rowconfigure(1, weight=1)
        ttk.Label(summary_frame, text="Source Selected from YouTube", style="Accent.TLabel").grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))
        ttk.Label(summary_frame, text="Final Output File", style="Accent.TLabel").grid(row=0, column=1, sticky="w", padx=10, pady=(8, 4))
        self.source_summary_text = tk.Text(summary_frame, height=12, wrap="word", state="disabled", bg=THEME["surface"], fg=THEME["text"], insertbackground=THEME["text"], relief="flat", padx=10, pady=8, font=FONT_MONO)
        self.output_summary_text = tk.Text(summary_frame, height=12, wrap="word", state="disabled", bg=THEME["surface"], fg=THEME["text"], insertbackground=THEME["text"], relief="flat", padx=10, pady=8, font=FONT_MONO)
        self.source_summary_text.grid(row=1, column=0, sticky="nsew", padx=(10, 6), pady=(0, 10))
        self.output_summary_text.grid(row=1, column=1, sticky="nsew", padx=(6, 10), pady=(0, 10))

        thumb_box = ttk.Frame(metadata_tab, style="Card.TFrame", width=320)
        thumb_box.grid(row=1, column=2, rowspan=4, sticky="nsew", padx=12, pady=(0, 12))
        thumb_box.grid_propagate(False)
        ttk.Label(thumb_box, text="Thumbnail", style="Accent.TLabel").pack(anchor="w", padx=10, pady=(10, 6))
        self.thumbnail_label = tk.Label(thumb_box, text="No thumbnail loaded", anchor="center", bg=THEME["surface"], fg=THEME["muted"], relief="flat", font=FONT_UI)
        self.thumbnail_label.pack(fill="both", expand=True, padx=10, pady=(0, 10), ipadx=8, ipady=8)

    def _check_runtime(self) -> None:
        if YTDLP_IMPORT_ERROR is not None:
            self._append_log(f"yt-dlp import failed: {YTDLP_IMPORT_ERROR}")
            self.download_button.config(state="disabled")
        ffmpeg = self._find_ffmpeg()
        deno = self._find_deno()
        write_diagnostic(f"runtime path: ffmpeg={ffmpeg}")
        write_diagnostic(f"runtime path: deno={deno}")
        if not ffmpeg:
            self._append_log("FFmpeg not found. Install FFmpeg or place its executable beside the packaged app.")
        else:
            self._append_log(f"FFmpeg found: {ffmpeg}")
        self._append_log(f"Diagnostics log: {DIAGNOSTICS_LOG_PATH}")

    def _check_for_updates(self) -> None:
        if self.update_worker and self.update_worker.is_alive():
            return
        self.update_button.config(state="disabled")
        self.status_var.set("Checking GitHub Releases for a VODForge update…")
        self.update_worker = threading.Thread(target=self._update_check_worker, daemon=True)
        self.update_worker.start()

    def _update_check_worker(self) -> None:
        try:
            self.events.put(("update_check_result", fetch_latest_release()))
        except Exception as exc:
            self.events.put(("update_check_error", str(exc)))

    def _show_update_result(self, release: ReleaseInfo) -> None:
        self.update_button.config(state="normal")
        if not is_newer_release(__version__, release.version):
            self.status_var.set(f"VODForge v{__version__} is up to date.")
            messagebox.showinfo(APP_NAME, f"You are using the latest VODForge release (v{__version__}).")
            return
        self.status_var.set(f"VODForge {release.tag_name} is available.")
        if sys.platform.startswith("win") and release_asset_for_platform(release) is not None:
            if messagebox.askyesno(
                APP_NAME,
                f"VODForge {release.tag_name} is available.\n\nDownload the release artifact, verify its SHA-256 checksum, and start the updater?",
            ):
                self._start_update_download(release)
            return
        if messagebox.askyesno(
            APP_NAME,
            f"VODForge {release.tag_name} is available.\n\nOpen the verified GitHub Release page to download it?",
        ):
            webbrowser.open(release.html_url)

    def _start_update_download(self, release: ReleaseInfo) -> None:
        self.update_button.config(state="disabled")
        self.status_var.set(f"Downloading and verifying VODForge {release.tag_name}…")
        self.update_worker = threading.Thread(target=self._update_download_worker, args=(release,), daemon=True)
        self.update_worker.start()

    def _update_download_worker(self, release: ReleaseInfo) -> None:
        try:
            destination = application_data_dir() / "updates" / release.tag_name
            path = download_verified_update(release, destination)
            self.events.put(("update_ready", path))
        except Exception as exc:
            self.events.put(("update_check_error", str(exc)))

    def _install_downloaded_update(self, path: Path) -> None:
        self.update_button.config(state="normal")
        if not sys.platform.startswith("win") or path.suffix.lower() != ".exe":
            self.status_var.set(f"Verified update downloaded: {path.name}")
            self._open_path(path.parent)
            return
        try:
            subprocess.Popen(
                [str(path), "/SP-", "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
                close_fds=True,
            )
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"The verified updater could not be started:\n\n{exc}")
            return
        self.status_var.set("Verified updater started. VODForge will close and reopen when installation completes.")

    def _load_download_history(self) -> None:
        try:
            self.download_history = load_history(self.history_path)
        except HistoryError as exc:
            self.download_history = []
            self._append_log(f"WARNING: {exc}")
            self.status_var.set("Download history could not be loaded; the existing history file was left untouched.")
            return
        self.metadata_items = [dict(item) for item in self.download_history]
        self._rebuild_output_dir_index()
        self._render_metadata_tree()
        if self.download_history:
            self.status_var.set(f"Loaded {len(self.download_history)} downloaded video(s) from history.")
            self._append_log(f"Loaded download history: {self.history_path}")

    def _record_download_history(self, info: dict[str, Any], output_dir: Path) -> None:
        try:
            self.download_history = upsert_history(self.download_history, info, output_dir)
            save_history(self.history_path, self.download_history)
        except HistoryError as exc:
            self._append_log(f"WARNING: {exc}")
            self.status_var.set("The video finished, but VODForge could not save it to local history.")
            return

        saved_record = self.download_history[0]
        saved_id = str(saved_record.get("id") or "")
        merged = dict(saved_record)
        retained: list[dict[str, Any]] = []
        for item in self.metadata_items:
            if history_identity(item) == history_identity(saved_record):
                merged = {**item, **saved_record}
                continue
            if saved_id and str(item.get("id") or "") == saved_id and history_output_dir(item) is None:
                merged = {**item, **saved_record}
                continue
            retained.append(item)
        self.metadata_items = [merged, *retained]
        self._rebuild_output_dir_index()
        self._render_metadata_tree(selected_index=0)
        self._append_log(f"Saved download history entry: {output_dir}")

    def _manual_help_icon(self, row: int, text: str) -> None:
        icon = ttk.Label(self.manual_settings_frame, text="?", style="Accent.TLabel", cursor="question_arrow")
        icon.grid(row=row, column=2, sticky="w", padx=(2, 8), pady=6)
        ToolTip(icon, text)

    def _refresh_manual_settings_visibility(self) -> None:
        frame = getattr(self, "manual_settings_frame", None)
        if frame is None:
            return
        if self.export_mode_var.get() == ExportMode.MANUAL_OVERRIDE.value:
            frame.grid()
        else:
            frame.grid_remove()

    def _manual_export_settings(self) -> ManualExportSettings:
        def positive_int(value: str, label: str, low: int, high: int) -> int:
            try:
                parsed = int(str(value).strip())
            except ValueError as exc:
                raise ValueError(f"{label} must be a whole number.") from exc
            if parsed < low or parsed > high:
                raise ValueError(f"{label} must be between {low} and {high} kbps.")
            return parsed

        channels_label = self.manual_channels_var.get()
        channels = "1" if channels_label == "Mono" else "2"
        return ManualExportSettings(
            video_bitrate_kbps=positive_int(self.manual_video_bitrate_var.get(), "Manual video bitrate", 100, 100000),
            audio_bitrate_kbps=positive_int(self.manual_audio_bitrate_var.get(), "Manual audio bitrate", 32, 1024),
            audio_sample_rate=self.manual_sample_rate_var.get() or AUDIO_SAMPLE_RATE,
            audio_channels=channels,
            x264_preset=self.manual_preset_var.get() or "medium",
        )

    def _browse_output(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.output_var.get() or str(Path.home()))
        if folder:
            self.output_var.set(folder)

    def _open_folder(self) -> None:
        saved = self._selected_saved_folder()
        if saved is not None:
            self._open_existing_saved_folder(saved)
            return
        self._open_path(self._folder_to_open())

    def _open_selected_saved_location(self) -> None:
        saved = self._selected_saved_folder()
        if saved is None:
            messagebox.showinfo(APP_NAME, "This preview does not have a saved download location yet.")
            return
        self._open_existing_saved_folder(saved)

    def _open_existing_saved_folder(self, path: Path) -> None:
        if not path.is_dir():
            messagebox.showwarning(
                APP_NAME,
                f"The saved folder is no longer available:\n\n{path}\n\nThe history entry was kept so you can still review its metadata.",
            )
            return
        self._open_path(path)

    def _open_log_folder(self) -> None:
        write_diagnostic("open log folder requested")
        self._open_path(DIAGNOSTICS_LOG_PATH.parent)

    @staticmethod
    def _open_path(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _folder_to_open(self) -> Path:
        saved = self._selected_saved_folder()
        if saved is not None:
            return saved
        if self.last_output_dirs:
            return self.last_output_dirs[-1]
        return Path(self.output_var.get()).expanduser()

    def _selected_saved_folder(self) -> Path | None:
        selection = getattr(self, "video_tree", None).selection() if hasattr(self, "video_tree") else ()
        if selection:
            try:
                info = self.metadata_items[int(selection[0])]
                return history_output_dir(info)
            except (IndexError, TypeError, ValueError):
                pass
        return None

    def _load_url_list_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose VODForge URL list",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            urls = read_url_list_file(Path(path))
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not read URL list file:\n{exc}")
            return
        if not urls:
            messagebox.showerror(APP_NAME, "That text file did not contain any http:// or https:// URLs.")
            return
        self.batch_urls = urls
        self.url_list_file_var.set(f"{Path(path).name} — {len(urls)} URL(s) loaded")
        self.status_var.set(f"Loaded {len(urls)} URL(s). Download will process them one at a time.")
        self._append_log(f"Loaded URL list: {path} ({len(urls)} URL(s))")

    def _load_cookie_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose YouTube cookies.txt",
            filetypes=[("Cookie text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        cookie_path = Path(path)
        if not cookie_path.exists():
            messagebox.showerror(APP_NAME, "That cookies file does not exist.")
            return
        self.cookie_file_path = cookie_path
        self.cookie_file_var.set(cookie_path.name)
        self.use_cookies_var.set(True)
        self.status_var.set("Loaded YouTube cookies; authenticated/private videos can use them when enabled.")
        self._append_log(f"Loaded YouTube cookies file: {cookie_path}")

    def _fetch_metadata(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror(APP_NAME, "Paste a YouTube URL first.")
            return
        if yt_dlp is None:
            messagebox.showerror(APP_NAME, f"yt-dlp import failed: {YTDLP_IMPORT_ERROR}")
            return
        if hasattr(self, "preview_metadata_button"):
            self.preview_metadata_button.config(state="disabled")
        self.status_var.set("Fetching tags and thumbnail…")
        threading.Thread(target=self._metadata_worker, args=(url,), daemon=True).start()

    def _metadata_worker(self, url: str) -> None:
        assert yt_dlp is not None
        try:
            opts = {"quiet": True, "skip_download": True, "noplaylist": False, "extract_flat": False, "logger": QueueLogger(self.events)}
            apply_youtube_extractor_args(opts)
            apply_ytdlp_cookie_options(
                opts,
                use_cookies=self.use_cookies_var.get(),
                cookie_file=self.cookie_file_path,
                cookie_browser=self.cookie_browser_var.get(),
            )
            ffmpeg = self._find_ffmpeg()
            if ffmpeg:
                opts["ffmpeg_location"] = ytdlp_ffmpeg_location(ffmpeg)
            deno = self._find_deno()
            if deno:
                opts["js_runtimes"] = {"deno": {"path": deno}}
                opts["remote_components"] = ["ejs:github"]
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            self.events.put(("metadata", info))
        except Exception as exc:
            self.events.put(("error", f"Metadata fetch failed: {format_ytdlp_user_error(exc)}"))
        finally:
            self.events.put(("metadata_fetch_done", None))

    def _copy_tags(self) -> None:
        text = self.pulled_tags_text.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.status_var.set("Copied tags to clipboard.")

    def _copy_thumbnail_url(self) -> None:
        if self.last_thumbnail_url:
            self.clipboard_clear()
            self.clipboard_append(self.last_thumbnail_url)
            self.status_var.set("Copied thumbnail URL to clipboard.")

    def _copy_description(self) -> None:
        text = self.description_text.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.status_var.set("Copied description to clipboard.")

    def _display_metadata(self, info: dict[str, Any]) -> None:
        incoming_items = iter_video_infos(info)
        new_items: list[dict[str, Any]] = []
        for incoming in incoming_items:
            video_id = str(incoming.get("id") or "")
            matching = next(
                (item for item in [*new_items, *self.metadata_items] if video_id and str(item.get("id") or "") == video_id),
                None,
            )
            if matching is not None:
                matching.update(incoming)
            else:
                new_items.append(incoming)
        if new_items:
            self.metadata_items = [*new_items, *self.metadata_items]
        self._rebuild_output_dir_index()
        self._render_metadata_tree()
        self.status_var.set(f"Showing metadata for {len(incoming_items)} fetched video(s); saved history remains available.")

    def _rebuild_output_dir_index(self) -> None:
        self.video_output_dirs_by_id = {}
        for item in self.metadata_items:
            video_id = str(item.get("id") or "")
            output_dir = history_output_dir(item)
            if video_id and output_dir is not None:
                self.video_output_dirs_by_id.setdefault(video_id, output_dir)

    def _render_metadata_tree(self, *, selected_index: int | None = None) -> None:
        selected_iid = self.video_tree.selection()[0] if self.video_tree.selection() else None
        for item in self.video_tree.get_children():
            self.video_tree.delete(item)
        for idx, item in enumerate(self.metadata_items, start=1):
            output_dir = history_output_dir(item)
            location = output_dir.name if output_dir is not None else "Preview only"
            values = (*video_list_row_values(item, fallback_index=idx), location)
            self.video_tree.insert("", "end", iid=str(idx - 1), values=values)
        if self.metadata_items:
            preferred = str(selected_index) if selected_index is not None else selected_iid
            target = preferred if preferred in self.video_tree.get_children() else self.video_tree.get_children()[0]
            self.video_tree.selection_set(target)
            self.video_tree.focus(target)
            self._display_selected_metadata(int(target))

    def _on_video_selected(self, _event: Any = None) -> None:
        selection = self.video_tree.selection()
        if selection:
            try:
                index = int(selection[0])
            except (TypeError, ValueError):
                index = 0
            self._display_selected_metadata(index)

    def _set_text(self, widget: tk.Text, text: str, *, disabled: bool = False) -> None:
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        if disabled:
            widget.config(state="disabled")

    def _display_selected_metadata(self, index: int) -> None:
        if index < 0 or index >= len(self.metadata_items):
            return
        info = self.metadata_items[index]
        title = str(info.get("title") or info.get("id") or "selected video")
        creator = str(info.get("uploader") or info.get("channel") or "Unknown creator")
        saved = history_output_dir(info)
        location_text = f"Saved in {saved}" if saved is not None else "Not downloaded in this history"
        self.selected_title_var.set(
            f"{title}\n{creator} • {format_duration(info.get('duration'))} • {info.get('id') or 'no id'}\n{location_text}"
        )
        tags_text = build_tags_display_text(info)
        description = build_description_display_text(info)
        self._set_text(self.pulled_tags_text, tags_text or "No tags found for this video.")
        self._set_text(self.description_text, description or "No description found for this video.")
        source_summary, output_summary = build_encoding_summary_display(info)
        self._set_text(self.source_summary_text, source_summary, disabled=True)
        self._set_text(self.output_summary_text, output_summary, disabled=True)
        thumb = best_thumbnail(info)
        self.last_thumbnail_url = str((thumb or {}).get("url") or "") or None
        local_thumbnail = saved / "thumbnail.jpeg" if saved is not None else None
        if local_thumbnail is not None and local_thumbnail.is_file():
            self._load_thumbnail_file(local_thumbnail)
        elif self.last_thumbnail_url:
            self._load_thumbnail_preview(self.last_thumbnail_url)
        else:
            self.thumbnail_label.config(image="", text="No thumbnail loaded")
        self.status_var.set(f"Showing metadata for: {info.get('title') or info.get('id') or 'selected video'}")

    def _load_thumbnail_file(self, path: Path) -> None:
        if Image is None or ImageTk is None:
            self.thumbnail_label.config(text=f"Saved thumbnail:\n{path}")
            return
        try:
            with Image.open(path) as source:
                image = source.copy()
            image.thumbnail((260, 150))
            self.thumbnail_image = ImageTk.PhotoImage(image)
            self.thumbnail_label.config(image=self.thumbnail_image, text="")
        except Exception as exc:
            self.thumbnail_label.config(text=f"Saved thumbnail preview failed:\n{exc}\n\n{path}")

    def _load_thumbnail_preview(self, url: str) -> None:
        if Image is None or ImageTk is None:
            self.thumbnail_label.config(text=f"Thumbnail URL:\n{url}")
            return
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                data = response.read()
            from io import BytesIO

            image = Image.open(BytesIO(data))
            image.thumbnail((260, 150))
            self.thumbnail_image = ImageTk.PhotoImage(image)
            self.thumbnail_label.config(image=self.thumbnail_image, text="")
        except Exception as exc:
            self.thumbnail_label.config(text=f"Thumbnail preview failed:\n{exc}\n\nURL:\n{url}")

    def _start_download(self) -> None:
        urls = list(self.batch_urls) if self.batch_urls else [self.url_var.get().strip()]
        cleaned_urls: list[str] = []
        if self.single_video_only_var.get():
            for url in urls:
                single_video_error = single_video_url_requires_video_id_error(url)
                if single_video_error:
                    messagebox.showerror(APP_NAME, single_video_error)
                    return
                cleaned_urls.append(clean_single_video_url(url))
            urls = cleaned_urls
            if not self.batch_urls and urls:
                self.url_var.set(urls[0])
        url = urls[0].strip() if urls else ""
        write_diagnostic(f"URL received: {url}")
        write_diagnostic(f"normalized URL: {url}")
        write_diagnostic(f"batch URL count: {len(urls)}")
        write_diagnostic(f"playlist query present: {'list=' in url.lower()} ; single_video_only={self.single_video_only_var.get()} ; use_nvenc={self.use_nvenc_var.get()}")
        if not url:
            messagebox.showerror(APP_NAME, "Paste a YouTube URL first or load a URL list text file.")
            return
        output_dir = Path(self.output_var.get()).expanduser()
        if not output_dir:
            messagebox.showerror(APP_NAME, "Choose an output folder.")
            return
        output_dir.mkdir(parents=True, exist_ok=True)
        if self.use_cookies_var.get() and not self.cookie_file_path and not browser_cookie_value(self.cookie_browser_var.get()):
            messagebox.showerror(APP_NAME, "Load a YouTube cookies.txt file, choose a browser under Browser cookies, or turn off Use YouTube cookies.")
            return
        cookie_warning = None if self.cookie_file_path else windows_chromium_cookie_warning(self.cookie_browser_var.get())
        if self.use_cookies_var.get() and cookie_warning:
            messagebox.showerror(APP_NAME, cookie_warning)
            return

        tags = [tag.strip() for tag in self.tags_var.get().split(",") if tag.strip()]
        try:
            manual_settings = self._manual_export_settings()
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        job = DownloadJob(
            url=url,
            output_dir=output_dir,
            quality_label=self.quality_var.get(),
            export_mode=ExportMode(self.export_mode_var.get()),
            manual_settings=manual_settings,
            single_video_only=self.single_video_only_var.get(),
            use_nvenc=self.use_nvenc_var.get(),
            embed_thumbnail=self.embed_thumbnail_var.get(),
            write_thumbnail=self.write_thumbnail_var.get(),
            embed_metadata=self.embed_metadata_var.get(),
            write_info_json=self.write_info_json_var.get(),
            tags=tags,
            urls=urls,
            use_cookies=self.use_cookies_var.get(),
            cookie_file=self.cookie_file_path,
            cookie_browser=browser_cookie_value(self.cookie_browser_var.get()),
            batch_mode=bool(self.batch_urls),
        )

        self.cancel_requested = False
        self.skip_video_requested = False
        self.skip_url_requested = False
        self.progress_var.set(0)
        self.status_var.set("Starting…")
        self.events.put(("progress_determinate", 0))
        self.download_button.config(state="disabled")
        self.cancel_button.config(state="normal")
        self.skip_video_button.config(state="normal")
        self.skip_url_button.config(state="normal")
        self.worker = threading.Thread(target=self._download_worker, args=(job,), daemon=True)
        self.worker.start()

    def _cancel(self) -> None:
        self.cancel_requested = True
        self.status_var.set("Cancel requested; waiting for current step to stop…")

    def _skip_video(self) -> None:
        self.skip_video_requested = True
        self.status_var.set("Skip video requested; moving to the next playlist item after current step stops…")

    def _skip_url(self) -> None:
        self.skip_url_requested = True
        self.skip_video_requested = True
        self.status_var.set("Skip URL requested; moving to the next batch URL after current step stops…")

    def _download_worker(self, job: DownloadJob) -> None:
        urls = [url.strip() for url in (job.urls or [job.url]) if url.strip()]
        if len(urls) <= 1:
            single_url = urls[0] if urls else job.url
            single_video_only = job.single_video_only
            if job.batch_mode:
                single_url, forced_single_video = prepare_batch_item_url(single_url)
                single_video_only = single_video_only or forced_single_video
                if forced_single_video and single_url != (urls[0] if urls else job.url):
                    self.events.put(("log", f"Batch URL normalized to single video: {single_url}"))
            self._download_worker_single(replace(job, url=single_url, urls=[single_url], single_video_only=single_video_only))
            return
        try:
            reset_batch_failure_report()
            failures: list[tuple[str, str]] = []
            for index, url in enumerate(urls, start=1):
                if self.cancel_requested:
                    raise RuntimeError("Download cancelled by user")
                item_url, forced_single_video = prepare_batch_item_url(url)
                item_single_video_only = job.single_video_only or forced_single_video
                self.events.put(("status", f"Batch URL {index} of {len(urls)} — starting"))
                self.events.put(("log", f"Batch URL {index} of {len(urls)}: {item_url}"))
                if forced_single_video and item_url != url:
                    self.events.put(("log", f"Batch URL {index}: stripped playlist/mix context; processing the pasted video only."))
                write_diagnostic(f"batch URL {index} of {len(urls)} start: {item_url} single_video_only={item_single_video_only}")
                try:
                    self._download_worker_single(replace(job, url=item_url, urls=[item_url], single_video_only=item_single_video_only), emit_done=False, re_raise=True)
                except Exception as exc:
                    issue = format_ytdlp_user_error(exc)
                    if "cancelled" in issue.lower():
                        raise
                    if "url skipped" in issue.lower():
                        self.skip_url_requested = False
                        self.skip_video_requested = False
                        write_diagnostic(f"batch URL {index} skipped by user: {item_url}")
                        self.events.put(("log", f"Batch URL {index} skipped by user; continuing."))
                        continue
                    failures.append((item_url, issue))
                    append_batch_failure_report(BATCH_FAILURE_REPORT_PATH, item_url, issue)
                    write_diagnostic(f"batch URL {index} of {len(urls)} failed but batch will continue: {type(exc).__name__}: {exc}")
                    self.events.put(("log", f"WARNING: Batch URL {index} failed; continuing. Failure report: {BATCH_FAILURE_REPORT_PATH}"))
                    continue
            if failures:
                self.events.put(("done", f"Batch complete — processed {len(urls)} URL(s), {len(failures)} failed. Failure report: {BATCH_FAILURE_REPORT_PATH}"))
            else:
                self.events.put(("done", f"Batch complete — processed {len(urls)} URL(s)."))
        except Exception as exc:
            self._active_progress_context = None
            write_diagnostic(f"batch download worker error: {type(exc).__name__}: {exc}")
            self.events.put(("error", f"{exc}\n\nDiagnostics log: {DIAGNOSTICS_LOG_PATH}"))

    def _download_worker_single(self, job: DownloadJob, *, emit_done: bool = True, re_raise: bool = False) -> None:
        assert yt_dlp is not None

        def video_url_from_entry(entry: dict[str, Any]) -> str:
            url = str(entry.get("webpage_url") or entry.get("url") or "").strip()
            if url.startswith("http://") or url.startswith("https://"):
                return url
            video_id = str(entry.get("id") or url).strip()
            if video_id:
                return f"https://www.youtube.com/watch?v={video_id}"
            return job.url

        def global_progress(video_index: int, total_videos: int, stage_start: float, stage_weight: float, stage_fraction: float = 0.0) -> float:
            total_videos = max(total_videos, 1)
            stage_fraction = max(0.0, min(1.0, stage_fraction))
            video_fraction = (stage_start + stage_weight * stage_fraction) / total_videos
            return max(0.0, min(100.0, ((video_index - 1) / total_videos + video_fraction) * 100.0))

        def put_stage_progress(video_index: int, total_videos: int, stage_start: float, stage_weight: float, stage_fraction: float = 0.0) -> None:
            self.events.put(("progress", global_progress(video_index, total_videos, stage_start, stage_weight, stage_fraction)))

        def raise_for_control_requests() -> None:
            if self.cancel_requested:
                raise RuntimeError("Download cancelled by user")
            if self.skip_url_requested:
                raise RuntimeError("URL skipped by user")
            if self.skip_video_requested:
                raise RuntimeError("Video skipped by user")

        def playlist_blocking_step_cancelled() -> bool:
            if self.skip_url_requested:
                raise RuntimeError("URL skipped by user")
            return self.cancel_requested

        def video_blocking_step_cancelled() -> bool:
            if self.skip_url_requested:
                raise RuntimeError("URL skipped by user")
            if self.skip_video_requested:
                raise RuntimeError("Video skipped by user")
            return self.cancel_requested

        def add_playlist_context(info: dict[str, Any], entry: dict[str, Any], playlist_info: dict[str, Any], index: int) -> dict[str, Any]:
            info.setdefault("playlist_title", playlist_info.get("title") or playlist_info.get("playlist_title"))
            info.setdefault("playlist_id", playlist_info.get("id") or playlist_info.get("playlist_id"))
            info.setdefault("playlist_index", entry.get("playlist_index") or index)
            return info

        current_video_info: dict[str, Any] | None = None
        current_plan: ExportPlan | None = None

        try:
            max_height = _quality_max_height(job.quality_label)
            self.events.put(("status", "Reading playlist…"))
            self.events.put(("log", f"Normalized URL: {job.url}"))
            write_diagnostic("playlist detection start")
            self.events.put(("progress", 0))

            playlist_opts: dict[str, Any] = {
                "quiet": True,
                "skip_download": True,
                "noplaylist": job.single_video_only,
                "extract_flat": False if job.single_video_only else "in_playlist",
                "logger": QueueLogger(self.events, diagnostic_prefix="playlist yt-dlp"),
                "socket_timeout": 30,
                "retries": 5,
                "fragment_retries": 5,
                "extractor_retries": 5,
                "ignore_no_formats_error": True,
            }
            apply_ytdlp_cookie_options(playlist_opts, use_cookies=job.use_cookies, cookie_file=job.cookie_file, cookie_browser=job.cookie_browser)
            apply_youtube_extractor_args(playlist_opts)
            log_options("playlist detection", playlist_opts)

            def detect_playlist() -> dict[str, Any] | None:
                write_diagnostic("playlist extraction start")
                with yt_dlp.YoutubeDL(playlist_opts) as ydl:
                    extracted = ydl.extract_info(job.url, download=False)
                write_diagnostic("playlist extraction completed")
                return extracted if isinstance(extracted, dict) else None

            playlist_info = run_cancellable_blocking_step(
                detect_playlist,
                playlist_blocking_step_cancelled,
                timeout_seconds=ANALYSIS_TIMEOUT_SECONDS,
                poll_seconds=ANALYSIS_POLL_SECONDS,
                label="Playlist detection",
                on_wait=lambda elapsed: (write_diagnostic(f"playlist detection still running after {elapsed:.0f}s"), self.events.put(("status", f"Reading playlist… {elapsed:.0f}s elapsed; Cancel is available."))),
            ) or {"webpage_url": job.url}

            raw_entries = playlist_info.get("entries") if isinstance(playlist_info, dict) else None
            entries = [entry for entry in (raw_entries or []) if isinstance(entry, dict)]
            if not entries:
                entries = [{"webpage_url": job.url, "id": playlist_info.get("id") if isinstance(playlist_info, dict) else None, "title": playlist_info.get("title") if isinstance(playlist_info, dict) else None}]
            total_videos = len(entries)
            if total_videos > 1:
                self.events.put(("log", f"Playlist detected: {total_videos} videos."))
                write_diagnostic(f"playlist detected: video_count={total_videos}")
            else:
                self.events.put(("log", "Single video detected."))
                write_diagnostic("single video detected")

            all_output_dirs: list[Path] = []
            self.video_output_dirs_by_id = {}

            for video_index, entry in enumerate(entries, start=1):
                try:
                    current_video_info = None
                    current_plan = None
                    video_url = video_url_from_entry(entry)
                    label = f"Video {video_index} of {total_videos}"
                    raise_for_control_requests()
                    self.events.put(("status", f"{label} — analyzing source formats"))
                    self.events.put(("log", f"{label}: URL {video_url}"))
                    put_stage_progress(video_index, total_videos, 0.0, 0.10, 0.0)

                    preflight_opts: dict[str, Any] = {
                        "quiet": True,
                        "skip_download": True,
                        "noplaylist": True,
                        "extract_flat": False,
                        "logger": QueueLogger(self.events, diagnostic_prefix="preflight yt-dlp"),
                        "socket_timeout": 30,
                        "retries": 5,
                        "fragment_retries": 5,
                        "extractor_retries": 5,
                        "ignore_no_formats_error": True,
                    }
                    apply_ytdlp_cookie_options(preflight_opts, use_cookies=job.use_cookies, cookie_file=job.cookie_file, cookie_browser=job.cookie_browser)
                    apply_youtube_extractor_args(preflight_opts)
                    ffmpeg_for_preflight = self._find_ffmpeg()
                    if ffmpeg_for_preflight:
                        preflight_opts["ffmpeg_location"] = ytdlp_ffmpeg_location(ffmpeg_for_preflight)
                    deno = self._find_deno()
                    write_diagnostic(f"{label} preflight runtime path: ffmpeg={ffmpeg_for_preflight}")
                    write_diagnostic(f"{label} preflight runtime path: deno={deno}")
                    if deno:
                        preflight_opts["js_runtimes"] = {"deno": {"path": deno}}
                        preflight_opts["remote_components"] = ["ejs:github"]
                        write_diagnostic(f"{label} preflight Deno/EJS enabled: remote_components=ejs:github")
                    else:
                        write_diagnostic(f"{label} preflight Deno/EJS disabled: no deno runtime found")
                    log_options(f"{label} preflight", preflight_opts)

                    def analyze_source_formats() -> dict[str, Any] | None:
                        write_diagnostic(f"{label} analysis start")
                        with yt_dlp.YoutubeDL(preflight_opts) as ydl:
                            extracted = ydl.extract_info(video_url, download=False)
                        write_diagnostic(f"{label} analysis completed")
                        return extracted if isinstance(extracted, dict) else None

                    preflight_info = run_cancellable_blocking_step(
                        analyze_source_formats,
                        video_blocking_step_cancelled,
                        timeout_seconds=ANALYSIS_TIMEOUT_SECONDS,
                        poll_seconds=ANALYSIS_POLL_SECONDS,
                        label=f"{label} source analysis",
                        on_wait=lambda elapsed, label=label: (write_diagnostic(f"{label} analysis still running after {elapsed:.0f}s"), self.events.put(("status", f"{label} — analyzing source formats ({elapsed:.0f}s elapsed); Cancel is available."))),
                    )
                    if not isinstance(preflight_info, dict):
                        raise RuntimeError(f"{label}: YouTube source analysis did not return metadata")
                    preflight_info = add_playlist_context(preflight_info, entry, playlist_info, video_index)
                    plan = build_auto_export_plan(preflight_info, mode=job.export_mode, max_height=max_height)
                    if job.export_mode == ExportMode.MANUAL_OVERRIDE:
                        plan = apply_manual_export_settings(plan, job.manual_settings)
                        self.events.put(("log", f"{label}: Manual Override settings {plan.video_bitrate_kbps} kbps video + {plan.audio_bitrate_kbps} kbps audio, {plan.audio_sample_rate} Hz, {plan.audio_channels} channel(s), x264 preset {plan.x264_preset}."))
                    current_plan = plan
                    current_video_info = build_encoding_summary_metadata(preflight_info, plan)
                    self.events.put(("metadata", current_video_info))
                    self.events.put(("log", f"{label}: selected format {plan.format_selector}"))
                    self.events.put(("log", f"{label}: selected video {plan.output_height}p {plan.video_codec} ~{plan.source_video_kbps:.0f} kbps; selected audio {plan.audio_codec} ~{plan.source_audio_kbps:.0f} kbps."))
                    target_label = "Manual target" if job.export_mode == ExportMode.MANUAL_OVERRIDE else "Auto CBR target"
                    self.events.put(("log", f"{label}: {target_label} {plan.video_bitrate_kbps} kbps video + {plan.audio_bitrate_kbps} kbps audio."))
                    for warning in plan.warnings:
                        self.events.put(("log", f"WARNING: {label}: {warning}"))
                    put_stage_progress(video_index, total_videos, 0.0, 0.10, 1.0)

                    staging_dir = create_staging_dir(job.output_dir)
                    try:
                        ydl_opts = self._build_ydl_options(job, staging_dir=staging_dir, format_selector=plan.format_selector)
                        ydl_opts["noplaylist"] = True
                        log_options(f"{label} download", ydl_opts)
                        self._active_progress_context = (video_index, total_videos, 0.10, 0.40)
                        self.events.put(("status", f"{label} — downloading"))
                        self.events.put(("log", f"{label}: downloading"))
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(video_url, download=True)
                        self._active_progress_context = None
                        if not isinstance(info, dict):
                            raise RuntimeError(f"{label}: download did not return metadata")
                        info = add_playlist_context(info, entry, playlist_info, video_index)
                        if current_video_info and current_video_info.get("vodforge_encoding_summary"):
                            info["vodforge_encoding_summary"] = current_video_info["vodforge_encoding_summary"]
                        current_video_info = info
                        self.events.put(("metadata", info))
                        put_stage_progress(video_index, total_videos, 0.10, 0.40, 1.0)

                        packaged_paths = package_downloaded_media_from_staging(staging_dir, job.output_dir, info)
                        output_dirs = sorted({path.parent for path in packaged_paths})
                        all_output_dirs.extend(output_dirs)
                        self.events.put(("download_folders", sorted(set(all_output_dirs))))
                        for packaged_path in packaged_paths:
                            self.events.put(("log", f"{label}: packaged media file {packaged_path}"))
                        ffmpeg = self._find_ffmpeg()
                        if not ffmpeg:
                            raise RuntimeError("FFmpeg is required to create the H.264 CBR / AAC 320k output.")

                        mp4_paths = [path for path in packaged_paths if path.suffix.lower() == ".mp4"]
                        primary_output = mp4_paths[0] if mp4_paths else None
                        info = build_encoding_summary_metadata(info, plan, output_path=primary_output)
                        current_video_info = info
                        self.events.put(("metadata", info))
                        total_mp4 = max(len(mp4_paths), 1)
                        for encode_index, mp4_path in enumerate(mp4_paths, start=1):
                            raise_for_control_requests()
                            self.events.put(("status", f"{label} — transcoding"))
                            encoder_label = "NVIDIA NVENC GPU" if job.use_nvenc else "CPU libx264"
                            self.events.put(("log", f"{label}: FFmpeg command started ({encode_index}/{total_mp4}) using {encoder_label}"))
                            write_diagnostic(f"{label} ffmpeg command: {build_vod_ffmpeg_command(ffmpeg, mp4_path, transcode_temp_paths(mp4_path)[0], video_bitrate_kbps=plan.video_bitrate_kbps, audio_bitrate_kbps=plan.audio_bitrate_kbps, audio_sample_rate=plan.audio_sample_rate, audio_channels=plan.audio_channels, x264_preset=plan.x264_preset, use_nvenc=job.use_nvenc)}")
                            put_stage_progress(video_index, total_videos, 0.50, 0.40, (encode_index - 1) / total_mp4)
                            transcode_to_vod_streaming_settings(
                                mp4_path,
                                ffmpeg,
                                plan=plan,
                                duration_seconds=_float_or_none(info.get("duration")),
                                progress_callback=lambda fraction, encode_index=encode_index, total_mp4=total_mp4: put_stage_progress(
                                    video_index,
                                    total_videos,
                                    0.50,
                                    0.40,
                                    ((encode_index - 1) + fraction) / total_mp4,
                                ),
                                use_nvenc=job.use_nvenc,
                                control_check=raise_for_control_requests,
                            )
                            self.events.put(("log", f"{label}: transcoded VODForge output {mp4_path}"))
                        put_stage_progress(video_index, total_videos, 0.50, 0.40, 1.0)

                        self.events.put(("status", f"{label} — validating output"))
                        ffprobe_data: dict[str, Any] | None = None
                        ffprobe = self._find_ffprobe()
                        if primary_output and ffprobe:
                            try:
                                ffprobe_data = run_ffprobe_json(ffprobe, primary_output)
                                self.events.put(("log", f"{label}: ffprobe validation complete for {primary_output.name}"))
                            except Exception as exc:
                                write_diagnostic(f"{label} ffprobe validation failed: {type(exc).__name__}: {exc}")
                                self.events.put(("log", f"WARNING: {label}: ffprobe validation failed: {exc}"))
                        elif not ffprobe:
                            self.events.put(("log", f"WARNING: {label}: ffprobe not found; output summary will keep planned values."))
                        info = build_encoding_summary_metadata(
                            info,
                            plan,
                            output_path=primary_output,
                            ffprobe_data=ffprobe_data,
                            validation_status="Validated" if ffprobe_data else "Output exists; ffprobe unavailable",
                        )
                        current_video_info = info
                        self.events.put(("metadata", info))
                        if primary_output is not None:
                            self.events.put(
                                (
                                    "history_record",
                                    {"info": info, "output_dir": str(primary_output.parent)},
                                )
                            )
                        if job.write_info_json:
                            metadata_path = write_compact_video_metadata(resolved_video_output_dir(job.output_dir, info), info, job.tags)
                            self.events.put(("log", f"{label}: saved compact video metadata {metadata_path}"))
                        if job.write_thumbnail:
                            thumb_path = save_thumbnail_image(resolved_video_output_dir(job.output_dir, info), info)
                            if thumb_path:
                                self.events.put(("log", f"{label}: saved thumbnail {thumb_path}"))
                        put_stage_progress(video_index, total_videos, 0.90, 0.10, 1.0)
                        self.events.put(("status", f"{label} complete"))
                        self.events.put(("log", f"{label} complete"))
                    finally:
                        self._active_progress_context = None
                        staging_root = staging_dir.parent
                        shutil.rmtree(staging_dir, ignore_errors=True)
                        try:
                            staging_root.rmdir()
                        except OSError:
                            pass
                except Exception as exc:
                    self._active_progress_context = None
                    issue = format_ytdlp_user_error(exc)
                    if "cancelled" in issue.lower():
                        raise
                    if "url skipped" in issue.lower():
                        self.skip_url_requested = False
                        self.skip_video_requested = False
                        self.events.put(("log", f"{label}: skipped URL by user."))
                        break
                    if total_videos <= 1 and "video skipped" not in issue.lower():
                        raise
                    append_batch_failure_report(BATCH_FAILURE_REPORT_PATH, video_url, issue)
                    if current_video_info is not None:
                        self.events.put(("metadata", build_failed_encoding_summary_metadata(current_video_info, current_plan, issue)))
                    write_diagnostic(f"{label} failed but playlist will continue: {type(exc).__name__}: {exc}")
                    if "video skipped" in issue.lower():
                        self.events.put(("log", f"{label}: skipped by user; continuing to next video."))
                    else:
                        self.events.put(("log", f"WARNING: {label} failed; continuing to next video. Failure report: {BATCH_FAILURE_REPORT_PATH}"))
                    self.skip_video_requested = False
                    continue


            if emit_done:
                self.events.put(("done", "Download complete."))
        except Exception as exc:
            self._active_progress_context = None
            if current_video_info is not None:
                self.events.put(("metadata", build_failed_encoding_summary_metadata(current_video_info, current_plan, format_ytdlp_user_error(exc))))
            user_error = format_ytdlp_user_error(exc)
            write_diagnostic(f"download worker error: {type(exc).__name__}: {exc}")
            if "url skipped" in user_error.lower() and not re_raise:
                self.skip_url_requested = False
                self.skip_video_requested = False
                self.events.put(("done", "URL skipped."))
                return
            if re_raise:
                raise
            self.events.put(("error", f"{user_error}\n\nDiagnostics log: {DIAGNOSTICS_LOG_PATH}"))

    def _build_ydl_options(self, job: DownloadJob, staging_dir: Path, format_selector: str | None = None) -> dict[str, Any]:
        postprocessors: list[dict[str, Any]] = [
            {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
        ]
        if job.embed_metadata:
            postprocessors.append({"key": "FFmpegMetadata", "add_chapters": True, "add_metadata": True})
        if job.embed_thumbnail:
            postprocessors.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})

        outtmpl = staging_output_template(staging_dir)
        opts: dict[str, Any] = {
            "format": (format_selector or QUALITY_OPTIONS[job.quality_label]) + "/best",
            "merge_output_format": "mp4",
            "outtmpl": outtmpl,
            "windowsfilenames": True,
            "restrictfilenames": False,
            "noplaylist": False,
            "writethumbnail": job.write_thumbnail or job.embed_thumbnail,
            "writeinfojson": False,
            "postprocessors": postprocessors,
            "progress_hooks": [self._progress_hook],
            "logger": QueueLogger(self.events),
            "embed_infojson": False,
            "postprocessor_args": self._metadata_args(job.tags),
            "concurrent_fragment_downloads": 1,
            "retries": 15,
            "fragment_retries": 15,
            "extractor_retries": 5,
            "retry_sleep_functions": {"http": lambda n: min(2 * n, 15), "fragment": lambda n: min(2 * n, 15)},
            "ignore_no_formats_error": True,
        }
        ffmpeg = self._find_ffmpeg()
        if ffmpeg:
            opts["ffmpeg_location"] = ytdlp_ffmpeg_location(ffmpeg)
        deno = self._find_deno()
        if deno:
            opts["js_runtimes"] = {"deno": {"path": deno}}
            opts["remote_components"] = ["ejs:github"]
        apply_ytdlp_cookie_options(opts, use_cookies=job.use_cookies, cookie_file=job.cookie_file, cookie_browser=job.cookie_browser)
        apply_youtube_extractor_args(opts)
        return opts

    @staticmethod
    def _find_ffmpeg() -> str | None:
        runtime_ffmpeg = find_runtime_executable("ffmpeg")
        if runtime_ffmpeg:
            return runtime_ffmpeg
        try:
            import imageio_ffmpeg

            bundled = imageio_ffmpeg.get_ffmpeg_exe()
            if bundled and Path(bundled).exists():
                return str(bundled)
        except Exception:
            pass
        return None

    @staticmethod
    def _find_ffprobe() -> str | None:
        return find_runtime_executable("ffprobe")

    @staticmethod
    def _find_deno() -> str | None:
        return find_runtime_executable("deno")

    def _metadata_args(self, tags: list[str]) -> dict[str, list[str]]:
        if not tags:
            return {}
        # FFmpegMetadata supports extra ffmpeg args. This writes comma-separated keywords
        # into the MP4 metadata when supported by the muxer/player.
        return {"FFmpegMetadata": ["-metadata", f"keywords={','.join(tags)}"]}

    def _progress_hook(self, data: dict[str, Any]) -> None:
        if self.cancel_requested:
            raise RuntimeError("Download cancelled by user")
        if self.skip_url_requested:
            raise RuntimeError("URL skipped by user")
        if self.skip_video_requested:
            raise RuntimeError("Video skipped by user")
        status = data.get("status")
        if status == "downloading":
            self.events.put(("progress_determinate", None))
            downloaded = data.get("downloaded_bytes") or 0
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            if total:
                pct = downloaded / total * 100
                context = self._active_progress_context
                if context:
                    video_index, total_videos, stage_start, stage_weight = context
                    global_pct = ((video_index - 1) / max(total_videos, 1) + (stage_start + stage_weight * (pct / 100.0)) / max(total_videos, 1)) * 100.0
                    self.events.put(("progress", global_pct))
                else:
                    self.events.put(("progress", pct))
            speed = data.get("speed")
            eta = data.get("eta")
            filename = Path(data.get("filename", "")).name
            self.events.put(("status", f"Downloading {filename} — {self._fmt_bytes(speed)}/s ETA {eta or '?'}s"))
        elif status == "finished":
            context = self._active_progress_context
            if context:
                video_index, total_videos, stage_start, stage_weight = context
                global_pct = ((video_index - 1) / max(total_videos, 1) + (stage_start + stage_weight) / max(total_videos, 1)) * 100.0
                self.events.put(("progress", global_pct))
            else:
                self.events.put(("progress", 100))
            self.events.put(("status", "Download finished; converting/embedding metadata…"))

    def _pump_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "progress_indeterminate_start":
                    if hasattr(self, "progress_bar"):
                        self.progress_bar.stop()
                        self.progress_bar.config(mode="indeterminate")
                        self.progress_bar.start(50)
                elif kind == "progress_indeterminate_stop":
                    if hasattr(self, "progress_bar"):
                        self.progress_bar.stop()
                        self.progress_bar.config(mode="determinate")
                    if payload is not None:
                        self.progress_var.set(float(payload))
                elif kind == "progress_determinate":
                    if hasattr(self, "progress_bar"):
                        self.progress_bar.stop()
                        self.progress_bar.config(mode="determinate")
                    if payload is not None:
                        self.progress_var.set(float(payload))
                elif kind == "progress":
                    if hasattr(self, "progress_bar"):
                        self.progress_bar.stop()
                        self.progress_bar.config(mode="determinate")
                    self.progress_var.set(float(payload))
                elif kind == "status":
                    self.status_var.set(str(payload))
                elif kind == "metadata":
                    if isinstance(payload, dict):
                        self._display_metadata(payload)
                elif kind == "history_record":
                    if isinstance(payload, dict) and isinstance(payload.get("info"), dict):
                        output_dir = str(payload.get("output_dir") or "").strip()
                        if output_dir:
                            self._record_download_history(payload["info"], Path(output_dir))
                elif kind == "metadata_fetch_done":
                    if hasattr(self, "preview_metadata_button"):
                        self.preview_metadata_button.config(state="normal")
                elif kind == "download_folders":
                    if isinstance(payload, list):
                        self.last_output_dirs = [Path(path) for path in payload]
                elif kind == "update_check_result":
                    if isinstance(payload, ReleaseInfo):
                        self._show_update_result(payload)
                elif kind == "update_ready":
                    if isinstance(payload, Path):
                        self._install_downloaded_update(payload)
                elif kind == "update_check_error":
                    self.update_button.config(state="normal")
                    self.status_var.set("Could not check for updates.")
                    messagebox.showinfo(APP_NAME, str(payload))
                elif kind == "done":
                    self.progress_var.set(100)
                    self.status_var.set(str(payload))
                    self._append_log(str(payload))
                    self.download_button.config(state="normal")
                    self.cancel_button.config(state="disabled")
                    self.skip_video_button.config(state="disabled")
                    self.skip_url_button.config(state="disabled")
                elif kind == "error":
                    self.status_var.set("Failed")
                    self._append_log(f"ERROR: {payload}")
                    messagebox.showerror(APP_NAME, str(payload))
                    self.download_button.config(state="normal")
                    self.cancel_button.config(state="disabled")
                    self.skip_video_button.config(state="disabled")
                    self.skip_url_button.config(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._pump_events)

    def _append_log(self, line: str) -> None:
        self.log.config(state="normal")
        self.log.insert("end", line.rstrip() + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    @staticmethod
    def _fmt_bytes(value: Any) -> str:
        if not value:
            return "?"
        size = float(value)
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"


def debug_preflight(url: str) -> int:
    reset_diagnostics_log()
    write_diagnostic(f"debug-preflight start: frozen={getattr(sys, 'frozen', False)} executable={sys.executable} argv={sys.argv}")
    write_diagnostic(f"diagnostics log path: {DIAGNOSTICS_LOG_PATH}")
    write_diagnostic(f"URL received: {url}")
    normalized_url = url.strip()
    write_diagnostic(f"normalized URL: {normalized_url}")
    write_diagnostic(f"playlist query present: {'list=' in normalized_url.lower()} ; noplaylist setting for analysis: False")
    if yt_dlp is None:
        write_diagnostic(f"yt-dlp import failed: {YTDLP_IMPORT_ERROR}")
        print(f"yt-dlp import failed: {YTDLP_IMPORT_ERROR}")
        print(f"Diagnostics log: {DIAGNOSTICS_LOG_PATH}")
        return 2
    write_diagnostic(f"yt-dlp version: {getattr(yt_dlp.version, '__version__', 'unknown')}")
    opts: dict[str, Any] = {
        "quiet": False,
        "verbose": True,
        "skip_download": True,
        "noplaylist": False,
        "extract_flat": False,
        "logger": QueueLogger(None, diagnostic_prefix="debug-preflight yt-dlp"),
        "socket_timeout": 30,
        "retries": 2,
        "fragment_retries": 2,
    }
    ffmpeg = DownloaderApp._find_ffmpeg()
    if ffmpeg:
        opts["ffmpeg_location"] = ytdlp_ffmpeg_location(ffmpeg)
    deno = DownloaderApp._find_deno()
    write_diagnostic(f"debug-preflight runtime path: ffmpeg={ffmpeg}")
    write_diagnostic(f"debug-preflight runtime path: deno={deno}")
    if deno:
        opts["js_runtimes"] = {"deno": {"path": deno}}
        opts["remote_components"] = ["ejs:github"]
        write_diagnostic("debug-preflight Deno/EJS enabled: remote_components=ejs:github")
    else:
        write_diagnostic("debug-preflight Deno/EJS disabled: no deno runtime found")
    apply_youtube_extractor_args(opts)
    log_options("debug-preflight", opts)

    def analyze_source_formats() -> dict[str, Any] | None:
        write_diagnostic("debug-preflight analysis start")
        with yt_dlp.YoutubeDL(opts) as ydl:
            extracted = ydl.extract_info(normalized_url, download=False)
        write_diagnostic("debug-preflight analysis completed")
        return extracted if isinstance(extracted, dict) else None

    try:
        info = run_cancellable_blocking_step(
            analyze_source_formats,
            lambda: False,
            timeout_seconds=ANALYSIS_TIMEOUT_SECONDS,
            poll_seconds=ANALYSIS_POLL_SECONDS,
            label="YouTube source analysis",
            on_wait=lambda elapsed: write_diagnostic(f"debug-preflight analysis still running after {elapsed:.0f}s"),
        )
    except Exception as exc:
        write_diagnostic(f"debug-preflight failed: {type(exc).__name__}: {exc}")
        print(f"DEBUG_PREFLIGHT_FAILED: {type(exc).__name__}: {exc}")
        print(f"Diagnostics log: {DIAGNOSTICS_LOG_PATH}")
        return 1
    video_count = len(iter_video_infos(info)) if isinstance(info, dict) else 0
    format_count = len(info.get("formats") or []) if isinstance(info, dict) else 0
    write_diagnostic(f"debug-preflight success: id={(info or {}).get('id') if isinstance(info, dict) else None} videos={video_count} formats={format_count}")
    print(f"DEBUG_PREFLIGHT_OK videos={video_count} formats={format_count}")
    print(f"Diagnostics log: {DIAGNOSTICS_LOG_PATH}")
    return 0


def runtime_smoke() -> int:
    """Verify packaged dependencies without opening the GUI or fetching media."""
    runtimes = {
        "ffmpeg": DownloaderApp._find_ffmpeg(),
        "ffprobe": DownloaderApp._find_ffprobe(),
        "deno": DownloaderApp._find_deno(),
    }
    print(
        f"VODFORGE_RUNTIME_SMOKE version={__version__} "
        f"platform={sys.platform} frozen={bool(getattr(sys, 'frozen', False))}"
    )
    failures: list[str] = []
    for name, path in runtimes.items():
        if not path:
            print(f"{name}=missing")
            failures.append(name)
            continue
        try:
            version = probe_runtime_version(name, path)
        except Exception as exc:
            print(f"{name}={path} execution_failed={type(exc).__name__}: {exc}")
            failures.append(name)
        else:
            print(f"{name}={path} version={version}")
    print(f"diagnostics={DIAGNOSTICS_LOG_PATH}")
    if failures:
        print(f"VODFORGE_RUNTIME_SMOKE_FAILED runtimes={','.join(failures)}")
        return 1
    print("VODFORGE_RUNTIME_SMOKE_OK")
    return 0


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--runtime-smoke":
        raise SystemExit(runtime_smoke())
    if len(sys.argv) >= 3 and sys.argv[1] == "--debug-preflight":
        raise SystemExit(debug_preflight(" ".join(sys.argv[2:])))
    app = DownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
