"""UI-neutral download, recovery, media and diagnostic services."""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
import queue
import re
import shutil
import stat
import subprocess  # nosec B404
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import uuid
import warnings
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Any

from yt_dlp.utils import ISO639Utils

from . import export_planning as _export_planning
from . import platform_services as _platform_services
from .caption_languages import (
    translated_subtitle_language as validate_translation_language,
)
from .cookie_inputs import (
    browser_cookie_value,
    windows_chromium_cookie_warning,
)
from .download_error_presentation import technical_download_error
from .encoding_summary import AUDIO_SUMMARY_COMPARISON_ROWS, SUMMARY_COMPARISON_ROWS
from .export_inputs import (
    validate_custom_cover_art,
)
from .export_planning import (
    DEFAULT_MAX_HEIGHT,
    QUALITY_OPTIONS,
    _is_hdr_format,
    _is_none_codec,
    apply_manual_export_settings,
    build_auto_export_plan,
    build_mp3_export_plan,
    export_mode_display_name,
)
from .failure_diagnostics import (
    FailureDiagnostic,
    SourceSelectionError,
    capture_failure,
)
from .history import (
    application_data_dir,
    observed_output_namespace,
    sanitize_chapters,
    sanitize_durable_text,
    sanitize_durable_thumbnail_record,
    sanitize_durable_url,
    sanitize_heatmap,
)
from .library_state import (
    format_duration,
    metadata_output_type,
    metadata_run_key,
)
from .libvlc_backend import (
    find_libvlc_runtime,
    probe_libvlc_runtime,
)
from .media_player import (
    MediaPlayerError as MediaPlayerError,  # noqa: PLC0414 - compatibility export
)
from .models import (
    AUDIO_CHANNELS,
    AUDIO_SAMPLE_RATE,
    STRICT_AUDIO_BITRATE_KBPS,
    STRICT_VIDEO_BITRATE_KBPS,
    AudioExportPlan,
    DownloadJob,
    DownloadOutcome,
    ExportMode,
    ExportPlan,
    ManualAudioCodec,
    OutputType,
)
from .original_audio import (
    build_original_audio_plan,
    original_audio_extension,
    original_audio_options,
)
from .output_validation import observed_audio_characteristics
from .output_validation import (
    output_artifact_plan_mismatches as _output_artifact_plan_mismatches,
)
from .output_validation import validate_output_artifact as _validate_output_artifact
from .platform_services import (
    diagnostics_dir,
    find_runtime_executable,
    hidden_window_subprocess_kwargs,
    is_windows,
    probe_runtime_version,
)
from .private_files import open_private_text_file, write_private_bytes
from .process_lifecycle import ACTIVE_CHILD_PROCESS_REGISTRY
from .product_telemetry import (
    product_output_kind,
)
from .product_theme import (
    THEME,
)
from .run_identity import (
    annotate_job_metadata,
    job_attempt_signature,
    metadata_attempt_signature,
    metadata_output_variant,
    owned_output_paths,
)
from .run_state import (
    RunRecoveryOwner,
    RunStateError,
)
from .safe_output import (
    cleanup_private_staging_directory,
    commit_file_beneath,
    create_private_staging_directory,
    is_regular_file_beneath,
    is_windows_sharing_violation,
    write_file_beneath,
)
from .source_selection import selection_observation
from .telemetry_features import (
    committed_export_dimensions,
    job_intent_dimensions,
)
from .thumbnail_network import ThumbnailUrlPolicy, download_bounded_url_bytes
from .transfer_refresh import SplitTransferRefresh, TransferRefreshError
from .updates import (
    update_ssl_context,
)
from .url_list_inputs import (
    parse_url_list_text,  # noqa: F401 - compatibility re-export
)
from .version import __version__
from .worker_events import (
    UiEvent,
    UiEventSink,
    history_record_event,
    job_info_event,
    job_log_event,
)

platform_font_families = _platform_services.platform_font_families

choose_audio_bitrate_kbps = _export_planning.choose_audio_bitrate_kbps

choose_best_audio_format = _export_planning.choose_best_audio_format

choose_best_video_format = _export_planning.choose_best_video_format

RUNTIME_SMOKE_PROBE_TIMEOUT_SECONDS = (
    _platform_services.RUNTIME_SMOKE_PROBE_TIMEOUT_SECONDS
)

choose_windows_output_directory = _platform_services.choose_windows_output_directory

runtime_executable_candidates = _platform_services.runtime_executable_candidates

runtime_version_command = _platform_services.runtime_version_command

try:
    from PIL import Image as _PILImage
    from PIL import ImageDraw as _PILImageDraw
    from PIL import ImageOps as _PILImageOps

    Image: Any = _PILImage
    ImageDraw: Any = _PILImageDraw
    ImageOps: Any = _PILImageOps
except Exception:  # noqa: BLE001  # pragma: no cover - optional rendering boundary
    Image = None
    ImageDraw = None
    ImageOps = None

yt_dlp: Any | None = None

YTDLP_IMPORT_ERROR: Exception | None = None

_YTDLP_IMPORT_ATTEMPTED = False

_YTDLP_IMPORT_LOCK = threading.Lock()


def load_yt_dlp() -> Any | None:
    """Load yt-dlp once, allowing the first window to paint without import latency."""
    global yt_dlp, YTDLP_IMPORT_ERROR, _YTDLP_IMPORT_ATTEMPTED
    if yt_dlp is not None or _YTDLP_IMPORT_ATTEMPTED:
        return yt_dlp
    with _YTDLP_IMPORT_LOCK:
        if yt_dlp is not None or _YTDLP_IMPORT_ATTEMPTED:
            return yt_dlp
        try:
            yt_dlp = importlib.import_module("yt_dlp")
            YTDLP_IMPORT_ERROR = None
        except Exception as exc:  # noqa: BLE001  # pragma: no cover - optional provider boundary
            YTDLP_IMPORT_ERROR = exc
            yt_dlp = None
        finally:
            _YTDLP_IMPORT_ATTEMPTED = True
    return yt_dlp


APP_NAME = "VODForge"

PINNED_YTDLP_VERSION = "2026.8.19"

PINNED_YTDLP_EJS_VERSION = "0.8.0"

YTDLP_EJS_SOLVER_RESOURCES = ("core.min.js", "lib.min.js")

WINDOWS_SAFE_PATH_LIMIT = 240

ANALYSIS_TIMEOUT_SECONDS = 1800

ANALYSIS_POLL_SECONDS = 0.1

ANALYSIS_STATUS_SECONDS = 5

SOURCE_ANALYSIS_RETRIES = 5

DOWNLOAD_HTTP_RETRIES = 15

DOWNLOAD_FRAGMENT_RETRIES = 15

DOWNLOAD_EXTRACTOR_RETRIES = 5

NETWORK_RETRY_MAX_DELAY_SECONDS = 15.0

VIDEO_TARGET_BITRATE = "10M"

AUDIO_BITRATE = "320k"

THUMBNAIL_MAX_BYTES = 300 * 1024

THUMBNAIL_MAX_PIXELS = 16_000_000

THUMBNAIL_MAX_DIMENSION = 8192

FFPROBE_TIMEOUT_SECONDS = 30

FFMPEG_COVER_TIMEOUT_SECONDS = 120

PROCESS_TERMINATE_TIMEOUT_SECONDS = 5

APPLICATION_CLOSE_TIMEOUT_SECONDS = 15

PROGRESS_EVENT_INTERVAL_SECONDS = 0.10

MAX_CONCURRENT_BLOCKING_ANALYSES = 2

MAX_QUEUED_PREVIEW_REQUESTS = 64

_BLOCKING_ANALYSIS_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT_BLOCKING_ANALYSES)

DEFAULT_IGNORE_PLAYLISTS = True

BACKEND_TEMP_OUTPUT_NAME = "__vodforge-tmp.mp4"

BACKEND_ORIGINAL_BACKUP_NAME = "__vodforge-original.mp4"

AUTO_UPDATE_INITIAL_DELAY_MS = 0

AUTO_UPDATE_INTERVAL_MS = 6 * 60 * 60 * 1_000


def _persisted_bool(values: dict[str, Any], key: str, default: bool) -> bool:
    value = values.get(key)
    return value if isinstance(value, bool) else default


def _persisted_choice(
    values: dict[str, Any], key: str, allowed: set[str], default: str
) -> str:
    value = values.get(key)
    return value if isinstance(value, str) and value in allowed else default


def _persisted_int_text(
    values: dict[str, Any], key: str, default: int, *, minimum: int, maximum: int
) -> str:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return str(default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if not minimum <= parsed <= maximum:
        parsed = default
    return str(parsed)


AUTO_UPDATE_BUSY_RETRY_MS = 10 * 60 * 1_000

THUMBNAIL_CACHE_MAX_ITEMS = 1000

CUSTOM_COVER_MAX_OUTPUT_BYTES = 2 * 1024 * 1024


def bundled_asset_path(
    name: str, *, meipass: Path | None = None, repo_root: Path | None = None
) -> Path:
    raw_meipass = getattr(sys, "_MEIPASS", None) if meipass is None else meipass
    base = (
        Path(raw_meipass)
        if raw_meipass
        else (Path(__file__).resolve().parents[1] if repo_root is None else repo_root)
    )
    return base / "assets" / name


def rounded_cover_image(source: Any, size: tuple[int, int], radius: int) -> Any:
    """Return a cover-cropped RGBA image with clean transparent corners."""
    if Image is None or ImageDraw is None or ImageOps is None:
        raise RuntimeError("Pillow is required for thumbnail rendering")
    resampling = getattr(Image, "Resampling", Image)
    cover = ImageOps.fit(
        source.convert("RGBA"), size, method=resampling.LANCZOS, centering=(0.5, 0.5)
    )
    mask = rounded_alpha_mask(size, radius)
    cover.putalpha(mask)
    return cover


def rounded_fit_image(source: Any, maximum_size: tuple[int, int], radius: int) -> Any:
    """Return a bounded, aspect-preserving thumbnail with no backing container."""
    if Image is None or ImageDraw is None or ImageOps is None:
        raise RuntimeError("Pillow is required for thumbnail rendering")
    resampling = getattr(Image, "Resampling", Image)
    fitted = ImageOps.contain(
        source.convert("RGBA"), maximum_size, method=resampling.LANCZOS
    )
    fitted.putalpha(rounded_alpha_mask(fitted.size, min(radius, min(fitted.size) // 2)))
    return fitted


def rounded_contain_image(
    source: Any, size: tuple[int, int], radius: int, background: str
) -> Any:
    """Fit placeholder artwork inside a 16:9 slot without cropping its edges."""
    if Image is None or ImageDraw is None or ImageOps is None:
        raise RuntimeError("Pillow is required for thumbnail rendering")
    resampling = getattr(Image, "Resampling", Image)
    padding = max(3, round(min(size) * 0.07))
    bounds = (max(1, size[0] - 2 * padding), max(1, size[1] - 2 * padding))
    contained = ImageOps.contain(
        source.convert("RGBA"), bounds, method=resampling.LANCZOS
    )
    canvas = Image.new("RGBA", size, background)
    canvas.alpha_composite(
        contained, ((size[0] - contained.width) // 2, (size[1] - contained.height) // 2)
    )
    mask = rounded_alpha_mask(size, radius)
    canvas.putalpha(mask)
    return canvas


def rounded_alpha_mask(size: tuple[int, int], radius: int, *, scale: int = 4) -> Any:
    """Return a supersampled rounded mask with smooth corners at display size."""
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow is required for rounded image rendering")
    safe_scale = max(1, int(scale))
    render_size = (max(1, size[0] * safe_scale), max(1, size[1] * safe_scale))
    mask = Image.new("L", render_size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, render_size[0] - 1, render_size[1] - 1),
        radius=max(0, radius) * safe_scale,
        fill=255,
    )
    if safe_scale == 1:
        return mask
    resampling = getattr(Image, "Resampling", Image)
    return mask.resize(size, resampling.LANCZOS)


def flatten_alpha_image(source: Any, background: str) -> Any:
    """Precompose an RGBA surface so Tk never quantizes its antialiased edge."""
    if Image is None:
        raise RuntimeError("Pillow is required for image compositing")
    image = source.convert("RGBA")
    backdrop = Image.new("RGBA", image.size, background)
    return Image.alpha_composite(backdrop, image)


def center_alpha_content(source: Any) -> Any:
    """Center visible RGBA content while preserving the source canvas and scale."""
    if Image is None:
        raise RuntimeError("Pillow is required for icon rendering")
    image = source.convert("RGBA")
    bounds = image.getchannel("A").getbbox()
    if bounds is None:
        return image.copy()
    left, top, right, bottom = bounds
    offset_x = round((image.width - (left + right)) / 2)
    offset_y = round((image.height - (top + bottom)) / 2)
    if offset_x == 0 and offset_y == 0:
        return image.copy()
    centered = Image.new("RGBA", image.size, (0, 0, 0, 0))
    centered.alpha_composite(image, (offset_x, offset_y))
    return centered


def render_monochrome_icon(source: Any, size: int, color: str) -> Any:
    """Render a centered monochrome icon with crisp, contrast-preserving alpha."""
    if Image is None:
        raise RuntimeError("Pillow is required for icon rendering")
    raw = source.convert("RGBA")
    icon = raw if raw.size == (size, size) else center_alpha_content(raw)
    resampling = getattr(Image, "Resampling", Image)
    alpha = icon.getchannel("A")
    if alpha.size != (size, size):
        alpha = alpha.resize((size, size), resampling.LANCZOS)
    alpha = alpha.point(
        lambda value: max(0, min(255, round((value - 128) * 1.24 + 128)))
    )
    rendered = Image.new("RGBA", (size, size), color)
    rendered.putalpha(alpha)
    return rendered


def focus_icon_color_variant(color: str) -> str | None:
    """Map fixed Focus Deck colors to their bundled vector variants."""
    return {
        THEME["muted"].lower(): "muted",
        THEME["accent"].lower(): "accent",
        THEME["text"].lower(): "text",
        "#ffffff": "white",
    }.get(str(color).lower())


def ytdlp_ffmpeg_location(ffmpeg: str) -> str:
    """Point yt-dlp at an FFmpeg directory when the executable has a standard name."""
    normalized = ffmpeg.replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1]
    if name.lower() not in {"ffmpeg", "ffmpeg.exe"}:
        return ffmpeg
    parent = normalized.rsplit("/", 1)[0] if "/" in normalized else "."
    if "\\" in ffmpeg and "/" not in ffmpeg:
        return parent.replace("/", "\\")
    return parent


DIAGNOSTICS_LOG_PATH = diagnostics_dir() / "latest.log"

ACTIVITY_LOG_PATH = diagnostics_dir() / "activity.log"

BATCH_FAILURE_REPORT_PATH = diagnostics_dir() / "batch-url-failures.txt"

ACTIVITY_LOG_MAX_BYTES = 5 * 1024 * 1024

ACTIVITY_LOG_COMPACT_BYTES = 4 * 1024 * 1024

ACTIVITY_LOG_RENDER_CHARS = 500_000

ACTIVITY_LOG_FAILURE_DIAGNOSTIC = (
    "Persistent Activity storage is unavailable. Current-session activity remains visible, "
    "but Activity history may not survive an app restart."
)

_DIAGNOSTICS_LOG_LOCK = threading.RLock()

_DIAGNOSTICS_LOG_HANDLE: Any | None = None

_DIAGNOSTICS_LOG_HANDLE_PATH: Path | None = None

_ACTIVITY_LOG_LOCK = threading.RLock()

_ACTIVITY_LOG_HANDLE: Any | None = None

_ACTIVITY_LOG_HANDLE_PATH: Path | None = None

_ACTIVITY_LOG_FAILURE_REPORTED = False

_ACTIVE_CHILD_PROCESSES = ACTIVE_CHILD_PROCESS_REGISTRY.processes

_ACTIVE_CHILD_PROCESS_LOCK = ACTIVE_CHILD_PROCESS_REGISTRY.inspection_lock

_THUMBNAIL_CACHE_LOCKS = tuple(threading.RLock() for _ in range(64))

_YTDLP_SUBPROCESS_TRACKING_LOCK = threading.RLock()


def write_diagnostic(message: str) -> None:
    global _DIAGNOSTICS_LOG_HANDLE, _DIAGNOSTICS_LOG_HANDLE_PATH
    try:
        with _DIAGNOSTICS_LOG_LOCK:
            if (
                _DIAGNOSTICS_LOG_HANDLE is None
                or _DIAGNOSTICS_LOG_HANDLE_PATH != DIAGNOSTICS_LOG_PATH
            ):
                if _DIAGNOSTICS_LOG_HANDLE is not None:
                    _DIAGNOSTICS_LOG_HANDLE.close()
                _DIAGNOSTICS_LOG_HANDLE = open_private_text_file(DIAGNOSTICS_LOG_PATH)
                _DIAGNOSTICS_LOG_HANDLE_PATH = DIAGNOSTICS_LOG_PATH
            timestamp = datetime.now().isoformat(  # noqa: DTZ005 - local wall-clock receipt
                timespec="milliseconds"
            )
            _DIAGNOSTICS_LOG_HANDLE.write(
                f"[{timestamp}] {sanitize_durable_text(message)}\n"
            )
    except Exception:  # noqa: BLE001 - a diagnostic sink cannot report through itself
        return


def reset_diagnostics_log() -> None:
    global _DIAGNOSTICS_LOG_HANDLE, _DIAGNOSTICS_LOG_HANDLE_PATH
    try:
        with _DIAGNOSTICS_LOG_LOCK:
            if _DIAGNOSTICS_LOG_HANDLE is not None:
                _DIAGNOSTICS_LOG_HANDLE.close()
            _DIAGNOSTICS_LOG_HANDLE = None
            _DIAGNOSTICS_LOG_HANDLE_PATH = None
            with open_private_text_file(DIAGNOSTICS_LOG_PATH, truncate=True):
                pass
    except Exception:  # noqa: BLE001 - reset cannot report through its own sink
        return


def _close_activity_log_locked() -> None:
    global _ACTIVITY_LOG_HANDLE, _ACTIVITY_LOG_HANDLE_PATH
    handle = _ACTIVITY_LOG_HANDLE
    _ACTIVITY_LOG_HANDLE = None
    _ACTIVITY_LOG_HANDLE_PATH = None
    if handle is not None:
        handle.close()


def close_activity_log(path: Path | None = None) -> None:
    """Release this activity sink before a Qt session removes its temporary home."""
    target = ACTIVITY_LOG_PATH if path is None else path
    with _ACTIVITY_LOG_LOCK:
        if _ACTIVITY_LOG_HANDLE_PATH == target:
            _close_activity_log_locked()


def _record_activity_log_failure() -> None:
    """Detach a failed sink and emit one secret-free receipt per failure episode."""
    global \
        _ACTIVITY_LOG_FAILURE_REPORTED, \
        _ACTIVITY_LOG_HANDLE, \
        _ACTIVITY_LOG_HANDLE_PATH
    should_report = False
    with _ACTIVITY_LOG_LOCK:
        try:
            _close_activity_log_locked()
        except (OSError, ValueError):
            # `_close_activity_log_locked` clears first; repeat that invariant
            # explicitly for unusual file wrappers whose close operation fails.
            _ACTIVITY_LOG_HANDLE = None
            _ACTIVITY_LOG_HANDLE_PATH = None
        if not _ACTIVITY_LOG_FAILURE_REPORTED:
            _ACTIVITY_LOG_FAILURE_REPORTED = True
            should_report = True
    if should_report:
        write_diagnostic(ACTIVITY_LOG_FAILURE_DIAGNOSTIC)


def _compact_activity_log_locked(
    path: Path, *, retain_bytes: int | None = None
) -> None:
    retain_bytes = ACTIVITY_LOG_COMPACT_BYTES if retain_bytes is None else retain_bytes
    if not path.exists() or path.stat().st_size <= retain_bytes:
        return
    with path.open("rb") as source:
        source.seek(-retain_bytes, os.SEEK_END)
        retained = source.read()
    newline = retained.find(b"\n")
    if newline >= 0:
        retained = retained[newline + 1 :]
    temporary = path.with_name(f".{path.name}.tmp")
    write_private_bytes(temporary, retained)
    temporary.replace(path)


def _sanitize_existing_activity_log_locked(path: Path) -> None:
    if not path.exists() or path.stat().st_size <= 0:
        return
    original = path.read_text(encoding="utf-8", errors="replace")
    sanitized = "\n".join(sanitize_durable_text(line) for line in original.splitlines())
    if original.endswith("\n"):
        sanitized += "\n"
    if sanitized == original:
        return
    temporary = path.with_name(f".{path.name}.sanitize.tmp")
    write_private_bytes(temporary, sanitized.encode("utf-8"))
    temporary.replace(path)


def prepare_activity_log(path: Path | None = None) -> None:
    """Create and bound the persistent, local-only user-facing activity log."""
    global _ACTIVITY_LOG_FAILURE_REPORTED
    target = ACTIVITY_LOG_PATH if path is None else path
    try:
        with _ACTIVITY_LOG_LOCK:
            if _ACTIVITY_LOG_HANDLE_PATH == target:
                _close_activity_log_locked()
            with open_private_text_file(target):
                pass
            _compact_activity_log_locked(target)
            _sanitize_existing_activity_log_locked(target)
            _ACTIVITY_LOG_FAILURE_REPORTED = False
    except Exception:  # noqa: BLE001 - optional activity persistence must not crash the app
        _record_activity_log_failure()


def append_activity_log(line: str, path: Path | None = None) -> None:
    global \
        _ACTIVITY_LOG_FAILURE_REPORTED, \
        _ACTIVITY_LOG_HANDLE, \
        _ACTIVITY_LOG_HANDLE_PATH
    target = ACTIVITY_LOG_PATH if path is None else path
    try:
        with _ACTIVITY_LOG_LOCK:
            if _ACTIVITY_LOG_HANDLE is None or _ACTIVITY_LOG_HANDLE_PATH != target:
                _close_activity_log_locked()
                _ACTIVITY_LOG_HANDLE = open_private_text_file(target)
                _ACTIVITY_LOG_HANDLE_PATH = target
            persistent_line = line.replace("\x00", "").rstrip()
            if persistent_line.startswith("Loaded YouTube cookies file:"):
                persistent_line = "Loaded YouTube cookies file."
            persistent_line = sanitize_durable_text(persistent_line)
            _ACTIVITY_LOG_HANDLE.write(persistent_line + "\n")
            if _ACTIVITY_LOG_HANDLE.tell() >= ACTIVITY_LOG_MAX_BYTES:
                _close_activity_log_locked()
                _compact_activity_log_locked(target)
            _ACTIVITY_LOG_FAILURE_REPORTED = False
    except Exception:  # noqa: BLE001 - optional activity persistence must not crash the app
        _record_activity_log_failure()


def load_activity_log_tail(
    path: Path | None = None, *, max_chars: int = ACTIVITY_LOG_RENDER_CHARS
) -> str:
    target = ACTIVITY_LOG_PATH if path is None else path
    try:
        with _ACTIVITY_LOG_LOCK:
            if not target.exists():
                return ""
            text = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if len(text) > max_chars:
        text = text[-max_chars:]
        newline = text.find("\n")
        if newline >= 0:
            text = text[newline + 1 :]
    return text.rstrip()


def reset_batch_failure_report(path: Path | None = None) -> None:
    target = BATCH_FAILURE_REPORT_PATH if path is None else path
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.unlink(missing_ok=True)
    except OSError as exc:
        raise RuntimeError(
            f"VODForge could not reset the batch failure report at {target}. "
            "Close any program using that file or choose a writable app-data location, then try again."
        ) from exc


def append_batch_failure_report(path: Path, url: str, issue: Any) -> None:
    timestamp = datetime.now().isoformat(  # noqa: DTZ005 - local wall-clock receipt
        timespec="seconds"
    )
    safe_url = (
        sanitize_durable_url(url, preserve_youtube_context=True)
        or "[redacted invalid URL]"
    )
    issue_text = sanitize_durable_text(str(issue).strip() or type(issue).__name__)
    with open_private_text_file(path) as report:
        report.write(f"[{timestamp}]\nURL: {safe_url}\nIssue: {issue_text}\n\n")


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
        write_diagnostic(
            f"{stage} options: {json.dumps(_loggable(opts), indent=2, sort_keys=True, default=str)}"
        )
    except Exception as exc:  # noqa: BLE001 - diagnostics must not alter job behavior
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
    started_at = time.monotonic()
    deadline = started_at + timeout_seconds
    next_wait_notice = started_at + wait_notice_seconds

    while not _BLOCKING_ANALYSIS_SLOTS.acquire(
        timeout=min(poll_seconds, max(0.001, deadline - time.monotonic()))
    ):
        now = time.monotonic()
        if cancel_requested():
            raise RuntimeError(f"{label} cancelled by user")
        if on_wait is not None and now >= next_wait_notice:
            on_wait(now - started_at)
            next_wait_notice = now + wait_notice_seconds
        if now >= deadline:
            raise TimeoutError(
                f"{label} timed out waiting for an analysis slot after {timeout_seconds:g} seconds"
            )

    def runner() -> None:
        try:
            results.put(("ok", step()))
        except Exception as exc:  # noqa: BLE001 - preserve arbitrary step failure for caller
            results.put(("error", exc))
        finally:
            _BLOCKING_ANALYSIS_SLOTS.release()

    thread = threading.Thread(target=runner, daemon=True)
    try:
        thread.start()
    except Exception:
        _BLOCKING_ANALYSIS_SLOTS.release()
        raise
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
                raise TimeoutError(
                    f"{label} timed out after {timeout_seconds:g} seconds"
                )
            time.sleep(poll_seconds)
            continue
        if kind == "error":
            raise payload
        return payload


TRANSIENT_HTTP_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


def _network_exception_chain(error: BaseException) -> list[BaseException]:
    pending = [error]
    seen: set[int] = set()
    result: list[BaseException] = []
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        result.append(current)
        for nested in (
            getattr(current, "__cause__", None),
            getattr(current, "__context__", None),
            getattr(current, "cause", None),
            getattr(current, "reason", None),
        ):
            if isinstance(nested, BaseException):
                pending.append(nested)
        exc_info = getattr(current, "exc_info", None)
        if (
            isinstance(exc_info, tuple)
            and len(exc_info) > 1
            and isinstance(exc_info[1], BaseException)
        ):
            pending.append(exc_info[1])
    return result


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _first_finite_float(*values: Any, default: float = 0.0) -> float:
    for value in values:
        number = _finite_float(value)
        if number is not None:
            return number
    return default


def transient_network_error_status(error: BaseException) -> int | None:
    for current in _network_exception_chain(error):
        response = getattr(current, "response", None)
        for value in (
            getattr(current, "status", None),
            getattr(current, "code", None),
            getattr(response, "status", None),
            getattr(response, "code", None),
        ):
            if value is None:
                continue
            try:
                status_code = int(value)
            except (TypeError, ValueError, OverflowError):
                continue
            if 100 <= status_code <= 599:
                return status_code
        match = re.search(r"\bHTTP (?:Error )?(\d{3})\b", str(current), re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def is_transient_network_error(error: BaseException) -> bool:
    status_code = transient_network_error_status(error)
    if status_code is not None:
        return status_code in TRANSIENT_HTTP_STATUS_CODES
    for current in _network_exception_chain(error):
        if isinstance(current, (TimeoutError, ConnectionError, urllib.error.URLError)):
            return True
        current_type = type(current)
        if current_type.__module__.startswith(
            "yt_dlp.networking"
        ) and current_type.__name__ in {
            "RequestError",
            "TransportError",
        }:
            return True
    return False


def ytdlp_retry_sleep_seconds(n: float) -> float:
    try:
        retry = max(0.0, float(n))
    except (TypeError, ValueError):
        retry = 0.0
    return min(2.0 * retry, NETWORK_RETRY_MAX_DELAY_SECONDS)


def _retry_after_seconds(error: BaseException) -> float | None:
    for current in _network_exception_chain(error):
        response = getattr(current, "response", None)
        for headers in (
            getattr(current, "headers", None),
            getattr(response, "headers", None),
        ):
            retry_after = (
                headers.get("Retry-After")
                if headers is not None and hasattr(headers, "get")
                else None
            )
            seconds = _finite_float(retry_after)
            if seconds is None:
                continue
            if 0 <= seconds <= NETWORK_RETRY_MAX_DELAY_SECONDS:
                return seconds
    return None


def run_with_bounded_transient_retries(
    operation: Callable[[], Any],
    *,
    max_attempts: int = SOURCE_ANALYSIS_RETRIES + 1,
    control_check: Callable[[], None] | None = None,
    on_retry: Callable[[int, int, float, Exception], None] | None = None,
) -> Any:
    """Retry one source-analysis authority only for bounded transient failures."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least one")
    for attempt in range(1, max_attempts + 1):
        if control_check is not None:
            control_check()
        try:
            return operation()
        except Exception as exc:
            if attempt >= max_attempts or not is_transient_network_error(exc):
                raise
            delay = _retry_after_seconds(exc)
            if delay is None:
                # Match yt-dlp's retry callback numbering: the first retry is
                # numbered zero and is immediate, then backoff is bounded.
                delay = ytdlp_retry_sleep_seconds(attempt - 1)
            if on_retry is not None:
                on_retry(attempt, max_attempts, delay, exc)
            deadline = time.monotonic() + delay
            while True:
                if control_check is not None:
                    control_check()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(ANALYSIS_POLL_SECONDS, remaining))
    raise AssertionError("bounded retry loop exhausted without returning or raising")


def apply_ytdlp_network_retry_policy(
    options: dict[str, Any], *, source_analysis: bool
) -> dict[str, Any]:
    """Give source analysis or media transfer exactly one retry authority."""
    if source_analysis:
        # The outer source-analysis retry re-creates YoutubeDL for generic
        # transport/HTTP failures. Preserve extractor-declared recovery for
        # known extractor operations, but disable overlapping request and
        # fragment retry loops during metadata-only analysis.
        options.update(
            {
                "retries": 0,
                "fragment_retries": 0,
                "extractor_retries": SOURCE_ANALYSIS_RETRIES,
                "retry_sleep_functions": {"extractor": ytdlp_retry_sleep_seconds},
            }
        )
        return options
    options.update(
        {
            "retries": DOWNLOAD_HTTP_RETRIES,
            "fragment_retries": DOWNLOAD_FRAGMENT_RETRIES,
            "extractor_retries": DOWNLOAD_EXTRACTOR_RETRIES,
            "retry_sleep_functions": {
                "http": ytdlp_retry_sleep_seconds,
                "fragment": ytdlp_retry_sleep_seconds,
                "extractor": ytdlp_retry_sleep_seconds,
            },
        }
    )
    return options


def source_analysis_retry_message(
    stage: str,
    failed_attempt: int,
    max_attempts: int,
    delay_seconds: float,
    error: Exception,
) -> str:
    return (
        f"{stage} transient network failure on attempt {failed_attempt}/{max_attempts}; "
        f"retrying attempt {failed_attempt + 1}/{max_attempts} in {delay_seconds:.3f}s: "
        f"{type(error).__name__}: {error}"
    )


class ProviderNetworkCoordinator:
    """Give primary downloads priority while bounding optional provider previews."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._primary_intents = 0
        self._primary_operations = 0
        self._preview_active = False

    def begin_primary(self, control_check: Any | None = None) -> None:
        with self._condition:
            self._primary_intents += 1
            try:
                while self._preview_active:
                    if control_check is not None:
                        control_check()
                    self._condition.wait(timeout=ANALYSIS_POLL_SECONDS)
            except Exception:
                self._primary_intents -= 1
                self._condition.notify_all()
                raise

    def end_primary(self) -> None:
        with self._condition:
            self._primary_intents = max(0, self._primary_intents - 1)
            self._condition.notify_all()

    def run_primary(self, step: Callable[[], Any]) -> Any:
        with self._condition:
            self._primary_operations += 1
            while self._preview_active:
                self._condition.wait(timeout=ANALYSIS_POLL_SECONDS)
        try:
            return step()
        finally:
            with self._condition:
                self._primary_operations = max(0, self._primary_operations - 1)
                self._condition.notify_all()

    def run_preview(
        self,
        step: Callable[[], Any],
        *,
        should_abort: Callable[[], bool] | None = None,
    ) -> tuple[bool, Any]:
        with self._condition:
            while (
                self._primary_intents
                or self._primary_operations
                or self._preview_active
            ):
                if should_abort is not None and should_abort():
                    return False, None
                self._condition.wait(timeout=ANALYSIS_POLL_SECONDS)
            if should_abort is not None and should_abort():
                return False, None
            self._preview_active = True
        try:
            return True, step()
        finally:
            with self._condition:
                self._preview_active = False
                self._condition.notify_all()


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


def _dict_or_empty(value: Any) -> dict[str, Any]:
    """Normalize untrusted persisted/provider sections to a plain mapping."""
    return value if isinstance(value, dict) else {}


def _encoding_summary_sections(
    info: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[Any]]:
    """Read each optional encoding-summary section once and normalize its shape."""
    summary = _dict_or_empty(info.get("vodforge_encoding_summary"))
    source = _dict_or_empty(summary.get("source"))
    output = _dict_or_empty(summary.get("output"))
    raw_warnings = summary.get("warnings")
    warnings = raw_warnings if isinstance(raw_warnings, list) else []
    return source, output, warnings


def build_tags_display_text(info: dict[str, Any]) -> str:
    """Return YouTube tags comma-separated so the GUI copy action is compact."""
    return ", ".join(_clean_list(info.get("tags")))


def build_description_display_text(info: dict[str, Any]) -> str:
    return str(info.get("description") or "").strip()


def metadata_indices_for_output_type(
    items: Sequence[dict[str, Any]],
    output_type: OutputType | str,
) -> list[int]:
    """Return stable source-list indices for one Library media type."""
    selected = OutputType(output_type)
    return [
        index
        for index, item in enumerate(items)
        if metadata_output_type(item) == selected
    ]


def mark_metadata_output_type(
    info: dict[str, Any], output_type: OutputType | str
) -> dict[str, Any]:
    """Return metadata with a stable output classification on root and entries."""
    output_type = OutputType(output_type)
    marked = dict(info)
    marked["vodforge_output_type"] = output_type.value
    entries = marked.get("entries")
    if isinstance(entries, list):
        marked["entries"] = [
            {**entry, "vodforge_output_type": output_type.value}
            if isinstance(entry, dict)
            else entry
            for entry in entries
        ]
    return marked


def fetch_metadata_preview(
    url: str,
    output_type: OutputType,
    *,
    ignore_playlists: bool,
    cookie_inputs: tuple[bool, Path | None, str | None],
    ffmpeg: str | None,
    deno: str | None,
    logger: Any,
    coordinator: ProviderNetworkCoordinator,
    should_abort: Callable[[], bool],
) -> dict[str, Any] | None:
    """Fetch one metadata-only preview through the shared provider gate.

    None means the request was retired before entering the provider. Preview
    metadata is not a durable download or history record.
    """
    ytdlp_module = load_yt_dlp()
    if ytdlp_module is None:
        raise RuntimeError(f"yt-dlp import failed: {YTDLP_IMPORT_ERROR}")
    opts: dict[str, Any] = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": ignore_playlists,
        "extract_flat": False,
        "logger": logger,
        "socket_timeout": 15,
    }
    apply_ytdlp_network_retry_policy(opts, source_analysis=True)
    use_cookies, cookie_file, cookie_browser = cookie_inputs
    apply_ytdlp_cookie_options(
        opts,
        use_cookies=use_cookies,
        cookie_file=cookie_file,
        cookie_browser=cookie_browser,
    )
    if ffmpeg:
        opts["ffmpeg_location"] = ytdlp_ffmpeg_location(ffmpeg)
    apply_youtube_runtime_options(opts, deno_path=deno)

    def control_check() -> None:
        if should_abort():
            raise RuntimeError("Metadata preview cancelled")

    def extract_metadata() -> Any:
        def extract() -> Any:
            with ytdlp_module.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        return run_with_bounded_transient_retries(
            lambda: run_tracked_ytdlp_operation(extract, control_check=control_check),
            control_check=control_check,
            on_retry=lambda attempt, maximum, delay, exc: write_diagnostic(
                source_analysis_retry_message(
                    "metadata preview", attempt, maximum, delay, exc
                )
            ),
        )

    ran, info = coordinator.run_preview(extract_metadata, should_abort=should_abort)
    if not ran:
        return None
    if not isinstance(info, dict):
        raise TypeError("Metadata preview returned no usable item.")
    return mark_metadata_output_type(info, output_type)


def _float_or_none(value: Any) -> float | None:
    number = _finite_float(value)
    if number is None:
        return None
    return number if number > 0 else None


def video_list_row_values(
    info: dict[str, Any], fallback_index: int
) -> tuple[str, str, str, str, str]:
    raw_index = info.get("playlist_index") or fallback_index
    try:
        index = f"{int(raw_index):03d}"
    except (TypeError, ValueError, OverflowError):
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
    number = _finite_float(value)
    if number is None:
        return fallback
    if number <= 0:
        return fallback
    return f"{number:.0f} kbps"


def _format_bits_per_second_as_kbps(value: Any, fallback: str = "Unknown") -> str:
    raw_number = _finite_float(value)
    if raw_number is None:
        return fallback
    number = raw_number / 1000
    if number <= 0:
        return fallback
    return f"{number:.0f} kbps"


def _format_bytes(value: Any, fallback: str = "Not available") -> str:
    size = _finite_float(value)
    if size is None:
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
    if not math.isfinite(fps) or fps <= 0:
        return fallback
    return f"{fps:.2f} fps" if abs(fps - round(fps)) > 0.01 else f"{fps:.0f} fps"


def _selected_format(info: dict[str, Any], format_id: str | None) -> dict[str, Any]:
    if not format_id:
        return {}
    for fmt in info.get("formats") or []:
        if isinstance(fmt, dict) and str(fmt.get("format_id") or "") == str(format_id):
            return fmt
    return {}


def _source_container(
    video_fmt: dict[str, Any], audio_fmt: dict[str, Any], plan: ExportPlan
) -> str:
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
    plan: ExportPlan | AudioExportPlan,
    *,
    output_path: Path | None = None,
    ffprobe_data: dict[str, Any] | None = None,
    validation_status: str | None = None,
) -> dict[str, Any]:
    """Attach per-video source/final-output encoding summary metadata."""
    enriched = dict(info)
    if isinstance(plan, AudioExportPlan):
        audio_fmt = _selected_format(info, plan.audio_format_id)
        source = {
            "Source format selector used": _display_value(
                plan.format_selector, "Not available"
            ),
            "Audio format ID": _display_value(plan.audio_format_id, "Not available"),
            "Source container/ext": _display_value(audio_fmt.get("ext"), "Unknown"),
            "Source audio codec": _display_value(
                audio_fmt.get("acodec") or plan.audio_codec
            ),
            "Source audio bitrate": _format_kbps(plan.source_audio_kbps),
            "Source audio sample rate": _display_value(
                plan.source_sample_rate, "Not available"
            ),
            "Source audio channels": _display_value(
                plan.source_channels, "Not available"
            ),
            "File size estimate": _format_bytes(
                audio_fmt.get("filesize") or audio_fmt.get("filesize_approx")
            ),
            "Effective MP3-equivalent audio bitrate": _format_kbps(
                plan.effective_audio_kbps
            ),
            "Reason selected": "highest-quality available audio-only source",
        }
        output = _planned_output_summary(plan, output_path)
        if ffprobe_data:
            output.update(_ffprobe_output_summary(ffprobe_data, output_path))
            output["Validation status"] = validation_status or "Validated"
        elif validation_status:
            output["Validation status"] = validation_status
        enriched["vodforge_output_type"] = plan.output_type.value
        enriched["vodforge_encoding_summary"] = {
            "source": source,
            "output": output,
            "warnings": list(plan.warnings),
        }
        return enriched

    video_fmt = _selected_format(info, plan.video_format_id)
    audio_fmt = (
        video_fmt
        if plan.video_format_id == plan.audio_format_id
        else _selected_format(info, plan.audio_format_id)
    )
    source = {
        "Source format selector used": _display_value(
            plan.format_selector, "Not available"
        ),
        "Video format ID": _display_value(plan.video_format_id, "Not available"),
        "Audio format ID": _display_value(plan.audio_format_id, "Not available"),
        "Source container/ext": _source_container(video_fmt, audio_fmt, plan),
        "Source resolution": f"{plan.output_width}x{plan.output_height}"
        if plan.output_width and plan.output_height
        else "Unknown",
        "Source frame rate": _format_fractional_fps(video_fmt.get("fps") or plan.fps),
        "Source video codec": _display_value(
            video_fmt.get("vcodec") or plan.video_codec
        ),
        "Source video bitrate": _format_kbps(plan.source_video_kbps),
        "Source audio codec": _display_value(
            audio_fmt.get("acodec") or plan.audio_codec
        ),
        "Source audio bitrate": _format_kbps(plan.source_audio_kbps),
        "Source audio sample rate": _display_value(
            audio_fmt.get("asr"), "Not available"
        ),
        "Source audio channels": _display_value(
            audio_fmt.get("audio_channels") or audio_fmt.get("channels"),
            "Not available",
        ),
        "HDR/SDR status": _hdr_status(video_fmt),
        "File size estimate": _format_bytes(
            video_fmt.get("filesize")
            or video_fmt.get("filesize_approx")
            or audio_fmt.get("filesize")
            or audio_fmt.get("filesize_approx")
        ),
        "Effective H.264-equivalent video bitrate": _format_kbps(
            plan.effective_video_kbps
        ),
        "Effective AAC-equivalent audio bitrate": _format_kbps(
            plan.effective_audio_kbps
        ),
        "Reason selected": _source_selection_reason(plan),
    }
    output = _planned_output_summary(plan, output_path)
    if ffprobe_data:
        output.update(_ffprobe_output_summary(ffprobe_data, output_path))
        output["Validation status"] = validation_status or "Validated"
    elif validation_status:
        output["Validation status"] = validation_status
    enriched["vodforge_output_type"] = OutputType.MP4.value
    enriched["vodforge_encoding_summary"] = {
        "source": source,
        "output": output,
        "warnings": list(plan.warnings),
    }
    return enriched


def build_failed_encoding_summary_metadata(
    info: dict[str, Any], plan: ExportPlan | AudioExportPlan | None, failure_reason: str
) -> dict[str, Any]:
    if plan is not None:
        enriched = build_encoding_summary_metadata(
            info, plan, validation_status="Failed"
        )
    else:
        enriched = dict(info)
        enriched["vodforge_encoding_summary"] = {
            "source": {},
            "output": {},
            "warnings": [],
        }
    enriched["vodforge_encoding_summary"]["output"].update(
        {
            "Output status": "No output produced",
            "Output file path": "Not produced",
            "Validation status": "Failed",
            "Failure reason": _display_value(failure_reason, "Unknown"),
        }
    )
    return enriched


def build_terminal_item_metadata(
    info: dict[str, Any],
    plan: ExportPlan | AudioExportPlan | None,
    status: str,
    message: str,
    run_id: str,
) -> dict[str, Any]:
    """Describe one non-output playlist item without mislabeling it as a preview."""
    if status == "Failed":
        enriched = build_failed_encoding_summary_metadata(info, plan, message)
    elif plan is not None:
        enriched = build_encoding_summary_metadata(info, plan, validation_status=status)
        enriched["vodforge_encoding_summary"]["output"].update(
            {
                "Output status": "No output produced",
                "Output file path": "Not produced",
                "Validation status": status,
                "Reason": message,
            }
        )
    else:
        enriched = dict(info)
        enriched["vodforge_encoding_summary"] = {
            "source": {},
            "output": {
                "Output status": "No output produced",
                "Output file path": "Not produced",
                "Validation status": status,
                "Reason": message,
            },
            "warnings": [],
        }
    enriched["vodforge_terminal_status"] = status
    enriched["vodforge_terminal_message"] = message
    enriched["vodforge_terminal_run_id"] = run_id
    return enriched


def _planned_output_summary(
    plan: ExportPlan | AudioExportPlan, output_path: Path | None = None
) -> dict[str, str]:
    if isinstance(plan, AudioExportPlan):
        return {
            "Output status": "Planned Output",
            "Output file path": str(output_path) if output_path else "Pending",
            "Output container": plan.output_extension.lstrip("."),
            "Output rate-control mode": "Stream copy"
            if plan.output_type == OutputType.ORIGINAL
            else "CBR",
            "Output audio codec": plan.audio_codec
            if plan.output_type == OutputType.ORIGINAL
            else "MP3 (libmp3lame)",
            "Target audio bitrate": "Preserve source"
            if plan.output_type == OutputType.ORIGINAL
            else f"{plan.audio_bitrate_kbps} kbps",
            "Measured audio bitrate": "Pending",
            "Audio sample rate": plan.output_sample_rate or "Preserve source",
            "Audio channels": plan.output_channels or "Preserve source",
            "Embedded ID3 metadata": "Yes" if plan.embed_metadata else "No",
            "Embedded cover art": plan.cover_art_source,
            "Output file size": "Pending",
            "Output duration": "Pending",
            "Validation status": "Pending",
        }
    return {
        "Output status": "Planned Output",
        "Output file path": str(output_path) if output_path else "Pending",
        "Output container": "mp4",
        "Output resolution": f"{plan.output_width}x{plan.output_height}"
        if plan.output_width and plan.output_height
        else "Unknown",
        "Output frame rate": _format_fractional_fps(plan.fps),
        "Output video codec": "H.264",
        "Output rate-control mode": plan.mode.value,
        "Target video bitrate": plan.video_target_label,
        "Video rate control": "Quality" if plan.video_crf is not None else "CBR",
        "Keyframe interval": f"{plan.keyframe_seconds:g} seconds"
        if plan.keyframe_seconds
        else "Encoder default",
        "Measured video bitrate": "Pending",
        "Pixel format": "yuv420p",
        "H.264 profile": "High",
        "Output audio codec": (
            "AAC"
            if plan.output_audio_codec is ManualAudioCodec.AAC
            else "MP3 (libmp3lame)"
        ),
        "Target audio bitrate": f"{plan.audio_bitrate_kbps} kbps",
        "Measured audio bitrate": "Pending",
        "Audio sample rate": plan.audio_sample_rate,
        "Audio channels": plan.audio_channels,
        "Output file size": "Pending",
        "Output duration": "Pending",
        "Validation status": "Pending",
    }


def _normalized_ffprobe_container(
    format_name: Any, output_path: Path | None = None
) -> str:
    tokens = [
        token.strip().lower()
        for token in str(format_name or "").split(",")
        if token.strip()
    ]
    suffix = output_path.suffix.lower().lstrip(".") if output_path else ""
    if suffix and (
        not tokens or suffix in tokens or suffix == "mp4" and "mov" in tokens
    ):
        return suffix
    if "mp4" in tokens:
        return "mp4"
    return _display_value(tokens[0] if tokens else "mp4", "mp4")


def _ffprobe_output_summary(
    ffprobe_data: dict[str, Any], output_path: Path | None = None
) -> dict[str, str]:
    streams = [
        stream
        for stream in ffprobe_data.get("streams") or []
        if isinstance(stream, dict)
    ]
    video = next(
        (stream for stream in streams if stream.get("codec_type") == "video"), {}
    )
    audio = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"), {}
    )
    fmt = _dict_or_empty(ffprobe_data.get("format"))
    width = video.get("width")
    height = video.get("height")
    return {
        "Output status": "Final Output",
        "Output file path": str(output_path or fmt.get("filename") or "Pending"),
        "Output container": _normalized_ffprobe_container(
            fmt.get("format_name"), output_path
        ),
        "Output resolution": f"{width}x{height}" if width and height else "Unknown",
        "Output frame rate": _format_fractional_fps(
            video.get("avg_frame_rate") or video.get("r_frame_rate")
        ),
        "Output video codec": _display_value(video.get("codec_name")),
        "Measured video bitrate": _format_bits_per_second_as_kbps(
            video.get("bit_rate")
        ),
        "Pixel format": _display_value(video.get("pix_fmt")),
        "H.264 profile": _display_value(video.get("profile")),
        "Output audio codec": _display_value(audio.get("codec_name")),
        "Measured audio bitrate": (
            f"{ffprobe_data['measured_audio_packet_bps'] / 1000:.1f} kbps (average)"
            if ffprobe_data.get("measured_audio_packet_bps") is not None
            else _format_bits_per_second_as_kbps(audio.get("bit_rate"))
        ),
        "Audio sample rate": _display_value(audio.get("sample_rate")),
        "Audio channels": _display_value(audio.get("channels")),
        "Output file size": _format_bytes(fmt.get("size")),
        "Output duration": format_duration(fmt.get("duration")),
    }


SUMMARY_LABEL_COLORS = {
    "Format selector": "#9ca1aa",
    "Video format ID": "#a1a5ad",
    "Audio format ID": "#969ca7",
    "Container/ext": "#91a0aa",
    "Resolution": "#8fa2b4",
    "Frame rate": "#999dae",
    "Video codec": "#9c96aa",
    "Video bitrate": "#879da8",
    "Audio codec": "#8fa39d",
    "Audio bitrate": "#829b9d",
    "Audio sample rate": "#999eaa",
    "Audio channels": "#8f99a8",
    "HDR/SDR or pixel format": "#a097a4",
    "File size": "#a39d8f",
    "Effective/target video bitrate": "#8f96b2",
    "Effective/target audio bitrate": "#879fa1",
    "Selection/status": "#9b95a7",
}


def summary_label_color(label: str) -> str:
    return SUMMARY_LABEL_COLORS.get(str(label), THEME["muted"])


def build_encoding_summary_display(info: dict[str, Any]) -> tuple[str, str]:
    source, output, warnings = _encoding_summary_sections(info)
    source_lines: list[str] = []
    output_lines: list[str] = []
    rows = (
        AUDIO_SUMMARY_COMPARISON_ROWS
        if metadata_output_type(info) != OutputType.MP4
        else SUMMARY_COMPARISON_ROWS
    )
    for label, source_key, output_key in rows:
        source_label = label
        output_label = label
        if output_key in {"Target audio bitrate", "Target video bitrate"}:
            media = "audio" if output_key == "Target audio bitrate" else "video"
            source_label = f"Effective {media}"
            output_label = f"{media.capitalize()} target"
        source_lines.append(
            f"{source_label}: {_display_value(source.get(source_key), 'Not available')}"
        )
        if output_key is not None:
            output_lines.append(
                f"{output_label}: {_display_value(output.get(output_key), 'Not available')}"
            )
    output_lines.extend(
        [
            f"Output status: {_display_value(output.get('Output status'), 'Not available')}",
            f"Output file path: {_display_value(output.get('Output file path'), 'Not produced')}",
            f"Output rate-control mode: {_display_value(output.get('Output rate-control mode'), 'Not available')}",
            f"Validation status: {_display_value(output.get('Validation status'), 'Not available')}",
            f"Output duration: {_display_value(output.get('Output duration'), 'Not available')}",
        ]
    )
    if metadata_output_type(info) == OutputType.MP3:
        output_lines.extend(
            [
                f"Embedded ID3 metadata: {_display_value(output.get('Embedded ID3 metadata'), 'Not available')}",
                f"Embedded cover art: {_display_value(output.get('Embedded cover art'), 'Not available')}",
            ]
        )
    elif metadata_output_type(info) == OutputType.MP4:
        output_lines.append(
            f"H.264 profile: {_display_value(output.get('H.264 profile'), 'Not available')}"
        )
    if output.get("Failure reason"):
        output_lines.append(
            f"Failure reason: {_display_value(output.get('Failure reason'), 'Unknown')}"
        )
    output_lines.append(
        f"Warnings: {', '.join(str(w) for w in warnings) if warnings else 'No warnings'}"
    )
    return "\n".join(source_lines), "\n".join(output_lines)


def best_thumbnail(info: dict[str, Any]) -> dict[str, Any] | None:
    thumbs = [
        thumb
        for thumb in info.get("thumbnails") or []
        if isinstance(thumb, dict) and thumb.get("url")
    ]
    if not thumbs:
        url = info.get("thumbnail")
        return {"url": url} if url else None
    return max(
        thumbs,
        key=lambda thumb: (
            (thumb.get("width") or 0) * (thumb.get("height") or 1),
            thumb.get("width") or 0,
        ),
    )


def _thumbnail_declared_size(thumb: dict[str, Any]) -> int | None:
    for key in ("filesize", "filesize_approx"):
        value = thumb.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
    return None


def best_thumbnail_for_download(
    info: dict[str, Any], max_bytes: int = THUMBNAIL_MAX_BYTES
) -> dict[str, Any] | None:
    """Pick a high-quality thumbnail source without pointlessly fetching known-oversize variants.

    yt-dlp usually exposes several YouTube thumbnail URLs. When it gives a
    filesize/filesize_approx, prefer the largest image already below our target;
    otherwise fall back to the largest source and let Pillow compress/resize the
    saved JPEG. This preserves quality when the metadata is sparse while still
    avoiding obviously huge downloads when smaller variants are available.
    """
    thumbs = [
        thumb
        for thumb in info.get("thumbnails") or []
        if isinstance(thumb, dict) and thumb.get("url")
    ]
    if not thumbs:
        return best_thumbnail(info)
    known_under = [
        thumb
        for thumb in thumbs
        if (_thumbnail_declared_size(thumb) or max_bytes + 1) <= max_bytes
    ]
    pool = known_under or thumbs
    return max(
        pool,
        key=lambda thumb: (
            (thumb.get("width") or 0) * (thumb.get("height") or 1),
            thumb.get("width") or 0,
        ),
    )


def validate_embedded_thumbnail_sources(
    info: dict[str, Any],
    *,
    source_url: str,
) -> None:
    """Reject any provider thumbnail URL that yt-dlp could fetch for embedding."""
    policy = ThumbnailUrlPolicy.for_source(source_url)
    candidates: list[Any] = [info.get("thumbnail")]
    candidates.extend(
        thumb.get("url")
        for thumb in info.get("thumbnails") or []
        if isinstance(thumb, dict)
    )
    checked: set[str] = set()
    for candidate in candidates:
        url = str(candidate or "")
        if not url.strip() or url in checked:
            continue
        policy.validate(url)
        checked.add(url)


def job_embeds_provider_thumbnail(job: DownloadJob) -> bool:
    if job.output_type == OutputType.ORIGINAL:
        return False
    if job.output_type == OutputType.MP3:
        return bool(
            job.mp3_settings.embed_cover_art
            and job.mp3_settings.custom_cover_art_path is None
        )
    return bool(job.embed_thumbnail)


def _clean_windows_component_text(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip()
    # Remove hidden/control formatting characters such as zero-width spaces that
    # make Windows paths impossible to reason about while preserving visible title
    # text. Newlines/tabs collapse to spaces below.
    return "".join(ch for ch in text if unicodedata.category(ch) not in {"Cc", "Cf"})


def _windows_safe_component(
    value: Any, fallback: str, max_len: int = 80, *, max_bytes: int = 240
) -> str:
    text = _clean_windows_component_text(value, fallback)
    safe = "".join(ch if ch not in '<>:"/\\|?*\0' else "_" for ch in text).strip(" .")
    safe = " ".join(safe.split())
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
    if safe.partition(".")[0].upper() in reserved:
        safe = f"_{safe}"
    if (
        len(safe.encode("utf-16-le")) // 2 > max_len
        or len(safe.encode("utf-8")) > max_bytes
    ):
        kept: list[str] = []
        used_units = 0
        used_bytes = 0
        for character in safe:
            units = len(character.encode("utf-16-le")) // 2
            byte_count = len(character.encode("utf-8"))
            if used_units + units > max(
                0, max_len - 1
            ) or used_bytes + byte_count > max(0, max_bytes - 3):
                break
            kept.append(character)
            used_units += units
            used_bytes += byte_count
        safe = "".join(kept).rstrip(" ._-…") + "…"
    return safe or fallback


SINGLE_VIDEO_PLAYLIST_ERROR = (
    "This link is a playlist. Turn off ‘Ignore playlists’ to download every item."
)

PLAYLIST_CONTEXT_QUERY_KEYS = {"list", "index", "start_radio"}


def _url_query_pairs(
    url: str,
) -> tuple[urllib.parse.SplitResult, list[tuple[str, str]]]:
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
    has_playlist_context = any(
        key.lower() == "list" and value.strip() for key, value in query
    )
    if has_playlist_context and not youtube_url_has_video_id(
        urllib.parse.urlunsplit(parsed)
    ):
        return SINGLE_VIDEO_PLAYLIST_ERROR
    return None


def clean_single_video_url(url: str) -> str:
    if not youtube_url_has_video_id(url):
        return url.strip()
    parsed, query = _url_query_pairs(url)
    filtered = [
        (key, value)
        for key, value in query
        if key.lower() not in PLAYLIST_CONTEXT_QUERY_KEYS
    ]
    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urllib.parse.urlencode(filtered, doseq=True),
            parsed.fragment,
        )
    )


def youtube_url_video_id(url: str) -> str | None:
    parsed, query = _url_query_pairs(url)
    for key, value in query:
        if key.lower() == "v" and value.strip():
            return value.strip()
    host = parsed.netloc.lower().removeprefix("www.")
    path_parts = [part for part in parsed.path.split("/") if part]
    if host == "youtu.be" and path_parts:
        return path_parts[0].strip() or None
    return None


def youtube_url_playlist_id(url: str) -> str | None:
    _parsed, query = _url_query_pairs(url)
    for key, value in query:
        if key.lower() == "list" and value.strip():
            return value.strip()
    return None


def prepare_batch_item_url(url: str) -> tuple[str, bool]:
    """Return the URL/playlist mode to use for one line from a batch URL file.

    Batch files are normally lists of concrete video URLs copied from YouTube.
    Those copied watch URLs often include playlist/mix context (`list=`, `index=`,
    `start_radio=`). A concrete video remains a single-item job, but its playlist
    identity stays intact so output location and later playlist deduplication use
    one canonical path. Real playlist-only URLs remain playlist jobs.
    """
    if youtube_url_has_video_id(url):
        return url.strip(), True
    return url.strip(), False


def retry_url_for_item(info: dict[str, Any], fallback_url: str) -> str:
    """Preserve a terminal item's playlist identity when creating a fresh retry run."""
    video_id = str(info.get("id") or youtube_url_video_id(fallback_url) or "").strip()
    playlist_id = str(
        info.get("playlist_id") or youtube_url_playlist_id(fallback_url) or ""
    ).strip()
    if video_id and playlist_id:
        return "https://www.youtube.com/watch?" + urllib.parse.urlencode(
            {"v": video_id, "list": playlist_id}
        )
    return fallback_url.strip()


def canonical_youtube_url(info: dict[str, Any], fallback_url: str = "") -> str | None:
    """Return a public item URL without copying unrelated query or auth data."""
    candidates = [
        str(info.get("webpage_url") or "").strip(),
        str(info.get("original_url") or "").strip(),
        str(info.get("url") or "").strip(),
        str(fallback_url or "").strip(),
    ]
    video_id = str(info.get("id") or "").strip()
    playlist_id = str(info.get("playlist_id") or "").strip()
    for candidate in candidates:
        parsed = urllib.parse.urlsplit(candidate)
        host = parsed.netloc.casefold().removeprefix("www.")
        if parsed.scheme not in {"http", "https"} or host not in {
            "youtube.com",
            "m.youtube.com",
            "youtu.be",
        }:
            continue
        video_id = video_id or str(youtube_url_video_id(candidate) or "").strip()
        playlist_id = (
            playlist_id or str(youtube_url_playlist_id(candidate) or "").strip()
        )
    if video_id:
        query: dict[str, str] = {"v": video_id}
        if playlist_id:
            query["list"] = playlist_id
        return "https://www.youtube.com/watch?" + urllib.parse.urlencode(query)
    if playlist_id:
        return "https://www.youtube.com/playlist?" + urllib.parse.urlencode(
            {"list": playlist_id}
        )
    for candidate in candidates:
        parsed = urllib.parse.urlsplit(candidate)
        host = parsed.netloc.casefold().removeprefix("www.")
        if parsed.scheme in {"http", "https"} and host in {
            "youtube.com",
            "m.youtube.com",
            "youtu.be",
        }:
            return urllib.parse.urlunsplit(
                (parsed.scheme, parsed.netloc, parsed.path, "", "")
            )
    return None


def playlist_context_from_extraction(
    info: dict[str, Any], source_url: str
) -> dict[str, Any]:
    """Return playlist authority only when the provider actually returned playlist entries."""
    if info.get("entries") is not None:
        return info
    return {"webpage_url": source_url}


def apply_playlist_context(
    info: dict[str, Any],
    entry: dict[str, Any],
    playlist_info: dict[str, Any],
    source_url: str,
    index: int,
) -> dict[str, Any]:
    """Attach only playlist identity proven by extraction or the source URL.

    A watch URL carrying ``list=`` remains a single-item run when Ignore
    playlists is enabled, but its output still belongs to that playlist's
    canonical folder. A plain video/share URL has no unambiguous playlist
    authority and intentionally remains under ``videos - no playlist``.
    """
    result = dict(info)
    extracted_playlist = playlist_info.get("entries") is not None
    playlist_title = playlist_info.get("playlist_title")
    playlist_id = playlist_info.get("playlist_id")
    if extracted_playlist:
        playlist_title = playlist_title or playlist_info.get("title")
        playlist_id = playlist_id or playlist_info.get("id")
    playlist_id = playlist_id or youtube_url_playlist_id(source_url)
    if playlist_title:
        result.setdefault("playlist_title", playlist_title)
    if playlist_id:
        result.setdefault("playlist_id", playlist_id)
    if playlist_title or playlist_id:
        result.setdefault("playlist_index", entry.get("playlist_index") or index)
    return result


def playlist_folder_name(info: dict[str, Any]) -> str:
    return _windows_safe_component(
        info.get("playlist_title")
        or info.get("playlist_id")
        or info.get("title")
        or info.get("id"),
        "Playlist",
        max_len=80,
    )


def channel_folder_name(info: dict[str, Any]) -> str:
    return _windows_safe_component(
        info.get("channel")
        or info.get("uploader")
        or info.get("channel_id")
        or "Unknown Channel",
        "Unknown Channel",
        max_len=80,
    )


def video_folder_name(info: dict[str, Any]) -> str:
    video_id = _windows_safe_component(info.get("id"), "", max_len=32)
    suffix = f" [{video_id}]" if video_id else ""
    if variant := metadata_output_variant(info):
        suffix += f" - {variant}"
    # _windows_safe_component appends an ellipsis after truncating, so reserve
    # one extra character to keep the final user-facing folder within 96 chars.
    title_max_len = max(1, 95 - len(suffix.encode("utf-16-le")) // 2)
    title = _windows_safe_component(
        info.get("title"),
        "video",
        max_len=title_max_len,
        max_bytes=255 - len(suffix.encode("utf-8")),
    )
    return f"{title}{suffix}"


def video_output_dir(output_dir: Path, info: dict[str, Any]) -> Path:
    channel_dir = output_dir / channel_folder_name(info)
    if info.get("playlist_title") or info.get("playlist_id"):
        return (
            channel_dir
            / "playlists"
            / playlist_folder_name(info)
            / video_folder_name(info)
        )
    return channel_dir / "videos - no playlist" / video_folder_name(info)


def _path_would_exceed_windows_safe_limit(path: Path) -> bool:
    # Stay below the legacy MAX_PATH boundary because packaged FFmpeg/Explorer and
    # third-party tooling are not guaranteed to be longPathAware on every user PC.
    return len(str(path).encode("utf-16-le")) // 2 > WINDOWS_SAFE_PATH_LIMIT


def compact_video_folder_name(
    info: dict[str, Any], max_title_len: int, *, compact_variant: bool = False
) -> str:
    video_id = _windows_safe_component(info.get("id"), "", max_len=32)
    suffix = f" [{video_id}]" if video_id else ""
    if variant := metadata_output_variant(info, compact=compact_variant):
        suffix += f" - {variant}"
    title_safe = _windows_safe_component(
        info.get("title"),
        "video",
        max_len=max_title_len,
        max_bytes=255 - len(suffix.encode("utf-8")),
    )
    return f"{title_safe}{suffix}"


def legacy_shallow_video_output_dir(output_dir: Path, info: dict[str, Any]) -> Path:
    """Locate the v0.1.5 ID-only fallback without creating new opaque paths."""
    video_id = _windows_safe_component(info.get("id"), "video", max_len=32)
    return output_dir / channel_folder_name(info) / "path-safe videos" / video_id


class OutputPathBudgetError(ValueError):
    """A new media path cannot fit beneath the selected output root."""

    code = "output_path_too_long"
    action = "choose_output_folder"
    action_label = "Choose folder"
    user_message = (
        "We can’t save your downloads in this folder because its full name is too long. "
        "Choose a different folder to continue."
    )

    def __init__(self) -> None:
        super().__init__(self.user_message)


def _allocate_video_output_target(
    output_dir: Path,
    info: dict[str, Any],
    ext: str,
    *,
    fixed_file_name: str | None = None,
) -> tuple[Path, str]:
    """Share one portable path budget among editable names, preserving identity."""
    has_playlist = bool(info.get("playlist_title") or info.get("playlist_id"))
    variant = metadata_output_variant(info)
    video_id = _windows_safe_component(info.get("id"), "", max_len=32)
    identity = f" [{video_id}]" if video_id else ""
    full_suffix = identity + (f" - {variant}" if variant else "")
    limits = {
        "channel": 80,
        "playlist": 80,
        "title": 80
        if fixed_file_name is not None
        else max(1, 95 - len(full_suffix.encode("utf-16-le")) // 2),
        "file": 120,
    }
    minimums = {
        "channel": 1,
        "playlist": 1,
        "title": 1,
        "file": 1,
    }
    compact_variant = False
    while True:
        channel = _windows_safe_component(
            info.get("channel") or info.get("uploader") or info.get("channel_id"),
            "Unknown Channel",
            max_len=limits["channel"],
        )
        parent = output_dir / channel
        playlist = ""
        if has_playlist:
            playlist = _windows_safe_component(
                info.get("playlist_title") or info.get("playlist_id"),
                "Playlist",
                max_len=limits["playlist"],
            )
            parent = parent / "playlists" / playlist
        else:
            parent = parent / "videos - no playlist"
        folder_name = compact_video_folder_name(
            info, limits["title"], compact_variant=compact_variant
        )
        filename = fixed_file_name or video_file_name(
            info, ext, max_title_len=limits["file"]
        )
        candidate = parent / folder_name
        if not _path_would_exceed_windows_safe_limit(candidate / filename):
            return candidate, filename
        suffix = identity + (
            f" - {metadata_output_variant(info, compact=compact_variant)}"
            if variant
            else ""
        )
        text_parts = {
            "title": folder_name.removesuffix(suffix) if suffix else folder_name,
            "playlist": playlist,
            "channel": channel,
        }
        if fixed_file_name is None:
            text_parts["file"] = filename.removesuffix(ext) if ext else filename
        adjustable = [
            name
            for name in text_parts
            if (name != "playlist" or has_playlist) and limits[name] > minimums[name]
        ]
        if adjustable:
            # Fixed-name lookups preserve their historical title-first allocation.
            # New outputs shorten the longest editable text before shorter names.
            name = (
                max(
                    adjustable,
                    key=lambda key: len(text_parts[key].encode("utf-16-le")) // 2,
                )
                if fixed_file_name is None
                else adjustable[0]
            )
            actual_units = len(text_parts[name].encode("utf-16-le")) // 2
            current = (
                limits[name]
                if fixed_file_name is not None
                else min(limits[name], actual_units)
            )
            limits[name] = max(minimums[name], current - 4)
        elif variant and not compact_variant:
            compact_variant = True
        else:
            raise OutputPathBudgetError()


def compact_video_output_dir(
    output_dir: Path, info: dict[str, Any], target_file_name: str
) -> Path:
    folder, _ = _allocate_video_output_target(
        output_dir, info, "", fixed_file_name=target_file_name
    )
    return folder


def resolved_video_output_dir(
    output_dir: Path, info: dict[str, Any], target_file_name: str | None = None
) -> Path:
    remembered = info.get("_vodforge_output_dir")
    if remembered:
        return Path(str(remembered))
    primary = video_output_dir(output_dir, info)
    if target_file_name and _path_would_exceed_windows_safe_limit(
        primary / target_file_name
    ):
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


def existing_output_candidate_dirs(
    output_dir: Path, info: dict[str, Any], target_file_name: str
) -> list[Path]:
    """Return bounded canonical and legacy directories for one provider item."""
    candidates: list[Path] = []

    def add(path: Path) -> None:
        if path not in candidates:
            candidates.append(path)

    canonical_primary = video_output_dir(output_dir, info)
    add(canonical_primary)
    try:
        canonical = resolved_video_output_dir(output_dir, info, target_file_name)
        add(canonical)
    except ValueError:
        canonical = canonical_primary
    legacy_info = dict(info)
    legacy_info.pop("playlist_title", None)
    legacy_info.pop("playlist_id", None)
    legacy_info.pop("playlist_index", None)
    legacy_info.pop("_vodforge_output_dir", None)
    legacy_primary = video_output_dir(output_dir, legacy_info)
    add(legacy_primary)
    try:
        legacy = resolved_video_output_dir(output_dir, legacy_info, target_file_name)
        add(legacy)
    except ValueError:
        legacy = legacy_primary
    add(legacy_shallow_video_output_dir(output_dir, info))
    add(
        output_dir
        / "path-safe videos"
        / _windows_safe_component(info.get("id"), "video", max_len=32)
    )

    safe_video_id = _windows_safe_component(info.get("id"), "", max_len=32)
    suffix = f"[{safe_video_id}]" if safe_video_id else ""
    suffixes: tuple[str, ...] = (suffix,)
    if variant := metadata_output_variant(info):
        suffixes = (
            f"{suffix} - {variant}",
            f"{suffix} - {metadata_output_variant(info, compact=True)}",
        )
    for parent in {canonical.parent, legacy.parent}:
        try:
            for child in parent.iterdir():
                if child.is_dir() and suffix and child.name.endswith(suffixes):
                    add(child)
        except OSError:
            continue
    if metadata_output_variant(info):
        return [path for path in candidates if path.name.endswith(suffixes)]
    return candidates


def is_vodforge_transient_media_path(path: Path, target_file_name: str) -> bool:
    """Return whether a media-looking path is an internal encode backup or temp file."""
    target_stem = Path(target_file_name).stem
    known_prefixes = (
        BACKEND_TEMP_OUTPUT_NAME,
        BACKEND_ORIGINAL_BACKUP_NAME,
        f"{target_stem}.ffmpeg-passlog",
        f"{target_stem}.vodforge-cbr-tmp",
        f"{target_stem}.vodforge-tmp",
        f"{target_stem}.pre-vodforge",
    )
    return any(path.name.startswith(prefix) for prefix in known_prefixes)


def load_vodforge_output_summary(item_dir: Path) -> dict[str, Any] | None:
    """Read the bounded VODForge output contract stored beside a completed artifact."""
    metadata_path = item_dir / safe_metadata_filename({})
    try:
        if (
            not metadata_path.is_file()
            or metadata_path.stat().st_size > 2 * 1024 * 1024
        ):
            return None
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    encoding = (
        payload.get("vodforge_encoding_summary") if isinstance(payload, dict) else None
    )
    output = encoding.get("output") if isinstance(encoding, dict) else None
    return output if isinstance(output, dict) else None


@dataclass(frozen=True)
class ExistingOutputRequirements:
    """The export contract an existing provider-scoped artifact must satisfy."""

    output_type: OutputType
    plan: ExportPlan | AudioExportPlan | None = None
    embed_metadata: bool | None = None
    embed_cover_art: bool | None = None
    custom_cover_art: bool = False
    expected_tags: list[str] | None = None
    expected_duration_seconds: float | None = None


def _report_reuse_rejection(
    callback: Callable[[str, FailureDiagnostic | None], None] | None,
    reason: str,
    error: Exception | None = None,
) -> None:
    if callback is None:
        return
    try:
        callback(reason, capture_failure(error, stage="reuse") if error else None)
    except Exception:  # noqa: BLE001, S110  # nosec B110 - diagnostic callbacks cannot control reuse
        pass


def _validate_existing_output_candidate(
    path: Path,
    ffprobe: str,
    requirements: ExistingOutputRequirements,
    *,
    control_check: Callable[[], None] | None,
    on_rejection: Callable[[str, FailureDiagnostic | None], None] | None = None,
) -> dict[str, Any] | None:
    """Return probe data only when one candidate satisfies the reuse contract."""
    try:
        probe_data = validate_output_artifact(
            path,
            requirements.output_type,
            ffprobe,
            expected_duration_seconds=requirements.expected_duration_seconds,
            require_audio=True,
            expected_audio_codec=(
                requirements.plan.output_audio_codec.ffprobe_codec
                if isinstance(requirements.plan, ExportPlan)
                else "mp3"
            ),
            plan=requirements.plan,
            embed_metadata=requirements.embed_metadata,
            embed_cover_art=requirements.embed_cover_art,
            expected_tags=requirements.expected_tags,
            control_check=control_check,
        )
    except Exception as exc:  # noqa: BLE001 - any invalid candidate must fail closed
        # Validation is cancellable. Recheck the canonical control boundary
        # before classifying the exception as an invalid artifact and scanning on.
        if control_check is not None:
            control_check()
        _report_reuse_rejection(on_rejection, "validation_failed", exc)
        write_diagnostic(
            f"existing output rejected: path={path} reason={type(exc).__name__}: {exc}"
        )
        return None

    if requirements.plan is not None and not output_artifact_matches_plan(
        probe_data,
        requirements.plan,
        embed_metadata=requirements.embed_metadata,
        embed_cover_art=requirements.embed_cover_art,
        custom_cover_art=requirements.custom_cover_art,
        expected_tags=requirements.expected_tags,
        sidecar_summary=load_vodforge_output_summary(path.parent),
    ):
        _report_reuse_rejection(
            on_rejection,
            "custom_artwork_unverifiable"
            if requirements.custom_cover_art
            else "plan_mismatch",
        )
        write_diagnostic(
            f"existing output rejected: path={path} reason=export settings do not match"
        )
        return None
    return probe_data


def find_valid_existing_output(
    output_dir: Path,
    info: dict[str, Any],
    output_type: OutputType,
    ffprobe: str,
    *,
    plan: ExportPlan | AudioExportPlan | None = None,
    embed_metadata: bool | None = None,
    embed_cover_art: bool | None = None,
    custom_cover_art: bool = False,
    expected_tags: list[str] | None = None,
    expected_duration_seconds: float | None = None,
    control_check: Callable[[], None] | None = None,
    owned_legacy_paths: tuple[Path, ...] = (),
    on_rejection: Callable[[str, FailureDiagnostic | None], None] | None = None,
) -> tuple[Path, dict[str, Any]] | None:
    """Reuse only a provider-ID-scoped artifact that passes full media validation."""
    requirements = ExistingOutputRequirements(
        output_type=output_type,
        plan=plan,
        embed_metadata=embed_metadata,
        embed_cover_art=embed_cover_art,
        custom_cover_art=custom_cover_art,
        expected_tags=expected_tags,
        expected_duration_seconds=expected_duration_seconds,
    )
    extension = plan.output_extension if isinstance(plan, AudioExportPlan) else ".mp4"
    target_file_name = video_file_name(info, extension)
    try:
        target_dir, target_file_name = resolved_video_output_target(
            output_dir, info, extension
        )
    except ValueError:
        # Lookup remains compatible with v0.1.5's emergency ID-only paths even
        # when this release would reject creating a new artifact under the
        # same overly deep root.
        target_dir = None
    candidate_dirs = existing_output_candidate_dirs(output_dir, info, target_file_name)
    if target_dir is not None and target_dir not in candidate_dirs:
        candidate_dirs.insert(0, target_dir)
    for path in owned_legacy_paths:
        if control_check is not None:
            control_check()
        if not is_regular_file_beneath(output_dir, path):
            continue
        probe_data = _validate_existing_output_candidate(
            path,
            ffprobe,
            requirements,
            control_check=control_check,
            on_rejection=on_rejection,
        )
        if probe_data is not None:
            return path, probe_data
    for candidate_dir in candidate_dirs:
        exact = candidate_dir / target_file_name
        paths = [exact]
        try:
            paths.extend(
                path
                for path in sorted(candidate_dir.glob(f"*{extension}"))
                if path != exact
                and not is_vodforge_transient_media_path(path, target_file_name)
            )
        except OSError:
            pass
        for path in paths:
            if control_check is not None:
                control_check()
            if not is_regular_file_beneath(output_dir, path):
                continue
            probe_data = _validate_existing_output_candidate(
                path,
                ffprobe,
                requirements,
                control_check=control_check,
                on_rejection=on_rejection,
            )
            if probe_data is None:
                continue
            return path, probe_data
    return None


def output_artifact_matches_plan(
    probe_data: dict[str, Any],
    plan: ExportPlan | AudioExportPlan,
    *,
    embed_metadata: bool | None,
    embed_cover_art: bool | None,
    custom_cover_art: bool,
    expected_tags: list[str] | None,
    sidecar_summary: dict[str, Any] | None = None,
) -> bool:
    """Return true only when an existing artifact proves it satisfies this export request."""
    if custom_cover_art:
        # ffprobe can prove that artwork exists, but not that it is the exact
        # user-selected image. Rebuild instead of silently reusing stale art.
        return False
    return not _output_artifact_plan_mismatches(
        probe_data,
        plan,
        embed_metadata=embed_metadata,
        embed_cover_art=embed_cover_art,
        expected_tags=expected_tags,
        sidecar_summary=sidecar_summary,
        # A compact metadata file is an optional requested output, not the
        # authority for whether the media itself is valid.  Enforce its stored
        # plan when present; when it is missing, require the probe-visible plan
        # contract and let the reuse path regenerate the requested sidecar.
        require_sidecar=isinstance(sidecar_summary, dict),
    )


def create_staging_dir(output_dir: Path) -> Path:
    # Keep staging on the destination volume for atomic commit, but reserve far
    # less of Windows' legacy path budget than the former long root + UUID. The
    # staging directory is private implementation state, so use a deliberately
    # compact name and token; final user-facing paths retain descriptive names.
    return create_private_staging_directory(output_dir)


def validate_output_directory_access(output_dir: Path) -> None:
    """Confirm the selected destination supports the write/remove cycle a run needs.

    VODForge stages media beside the final destination so the validated artifact can
    be committed atomically without crossing filesystems.  Touch the destination at
    submission time so macOS protected-folder consent and unavailable network-drive
    errors appear while the user is intentionally starting the run, rather than later
    during a skip or cleanup operation.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    probe_path = output_dir / f".vodforge-access-{uuid.uuid4().hex}.tmp"
    descriptor: int | None = None
    try:
        descriptor = os.open(probe_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    finally:
        if descriptor is not None:
            os.close(descriptor)
    probe_path.unlink()


def staging_output_template() -> str:
    # The paths options own staging placement, including format-probe files.
    # Final user-facing folders are created only by the commit pipeline.
    return "%(id)s.%(ext)s"


def iter_video_infos(info: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(info.get("entries"), list):
        videos: list[dict[str, Any]] = []
        for idx, entry in enumerate(info.get("entries") or [], start=1):
            if not isinstance(entry, dict):
                continue
            item = dict(entry)
            item.setdefault(
                "playlist_title", info.get("title") or info.get("playlist_title")
            )
            item.setdefault("playlist_id", info.get("id") or info.get("playlist_id"))
            item.setdefault("playlist_index", entry.get("playlist_index") or idx)
            videos.append(item)
        return videos
    return [info]


def process_download_from_preflight(
    ydl: Any,
    preflight_info: dict[str, Any],
    *,
    session_cookies: tuple[Any, ...] = (),
    control_check: Any | None = None,
) -> Any:
    """Download a freshly extracted result without asking the provider to extract it again."""
    seed_ytdlp_session_cookies(ydl, session_cookies)
    reusable = dict(preflight_info)
    for transient_key in (
        "requested_downloads",
        "requested_formats",
        "filepath",
        "__files_to_move",
        "__postprocessors",
    ):
        reusable.pop(transient_key, None)
    return run_tracked_ytdlp_operation(
        lambda: ydl.process_ie_result(reusable, download=True),
        control_check=control_check,
    )


def seed_ytdlp_session_cookies(ydl: Any, session_cookies: tuple[Any, ...]) -> None:
    cookiejar = getattr(ydl, "cookiejar", None)
    set_cookie = getattr(cookiejar, "set_cookie", None)
    if callable(set_cookie):
        for cookie in session_cookies:
            set_cookie(cookie)


def snapshot_ytdlp_session_cookies(ydl: Any) -> tuple[Any, ...]:
    return tuple(getattr(ydl, "cookiejar", ()) or ())


def safe_metadata_filename(info: dict[str, Any]) -> str:
    return "metadata.json"


def compact_video_metadata(
    info: dict[str, Any], extra_tags: list[str]
) -> dict[str, Any]:
    """Keep only copy/useful metadata instead of yt-dlp's huge one-line info dump."""
    thumb = best_thumbnail(info)
    compact: dict[str, Any] = {
        "id": info.get("id"),
        "title": info.get("title"),
        "webpage_url": sanitize_durable_url(
            info.get("webpage_url") or info.get("original_url"),
            preserve_youtube_context=True,
        ),
        "description": build_description_display_text(info),
        "tags": _clean_list(info.get("tags")),
        "extra_tags": _clean_list(extra_tags),
        "categories": _clean_list(info.get("categories")),
        "chapters": sanitize_chapters(info.get("chapters")),
        "heatmap": sanitize_heatmap(info.get("heatmap")),
        "thumbnail": sanitize_durable_url(
            info.get("thumbnail") or (thumb or {}).get("url"),
            preserve_youtube_context=False,
        ),
        "best_thumbnail": sanitize_durable_thumbnail_record(thumb),
        "vodforge_output_type": metadata_output_type(info).value,
        "vodforge_encoding_summary": info.get("vodforge_encoding_summary"),
        "vodforge_subtitle_tracks": sanitized_subtitle_tracks(
            info.get("vodforge_subtitle_tracks")
        ),
        "vodforge_caption_summary": sanitized_caption_summary(
            info.get("vodforge_caption_summary")
        ),
    }
    return {
        key: value for key, value in compact.items() if value not in (None, "", [], {})
    }


def _sidecar_destination_state(path: Path) -> bool | None:
    """A best-effort point-in-time observation, never a commit authority."""
    try:
        observed = path.lstat()
        return True if stat.S_ISREG(observed.st_mode) else None
    except FileNotFoundError:
        return False
    except Exception:  # noqa: BLE001 - best-effort observation must not affect writes
        return None


def _sidecar_write_result(before: bool | None) -> str:
    return "unknown" if before is None else "rewritten" if before else "created"


def _report_sidecar_result(callback: Callable[[str], None] | None, result: str) -> None:
    if callback is not None:
        try:
            callback(result)
        except Exception:  # noqa: BLE001 - callbacks are outside the artifact authority
            return


def write_compact_video_metadata(
    output_dir: Path,
    info: dict[str, Any],
    extra_tags: list[str],
    *,
    output_root: Path | None = None,
    on_result: Callable[[str], None] | None = None,
) -> Path:
    data = (
        json.dumps(
            compact_video_metadata(info, extra_tags), ensure_ascii=False, indent=2
        )
        + "\n"
    )
    destination = output_dir / safe_metadata_filename(info)
    before = _sidecar_destination_state(destination) if on_result is not None else None
    written = write_file_beneath(
        output_root if output_root is not None else output_dir,
        destination,
        lambda staged: staged.write_text(data, encoding="utf-8"),
    )
    _report_sidecar_result(on_result, _sidecar_write_result(before))
    return written


def write_all_compact_video_metadata(
    output_dir: Path, info: dict[str, Any], extra_tags: list[str]
) -> list[Path]:
    paths: list[Path] = []
    for video in iter_video_infos(info):
        paths.append(
            write_compact_video_metadata(
                video_output_dir(output_dir, video),
                video,
                extra_tags,
                output_root=output_dir,
            )
        )
    return paths


STAGED_MEDIA_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".webm",
    ".mov",
    ".mp3",
    ".m4a",
    ".aac",
    ".opus",
    ".ogg",
}


def _find_staged_media_file(
    staging_dir: Path, video_id: str, *, expected_extension: str | None = None
) -> Path | None:
    allowed = (
        {expected_extension.lower()} if expected_extension else STAGED_MEDIA_EXTENSIONS
    )
    candidates = [
        path
        for path in staging_dir.rglob(f"*{video_id}*")
        if path.is_file() and path.suffix.lower() in allowed and path.stat().st_size > 0
    ]
    if not candidates:
        candidates = [
            path
            for path in staging_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in allowed
            and path.stat().st_size > 0
        ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.stat().st_size))


def video_file_name(
    info: dict[str, Any],
    ext: str,
    *,
    max_title_len: int = 120,
    collision_suffix: str = "",
) -> str:
    title = _windows_safe_component(
        info.get("title"),
        "video",
        max_len=max_title_len,
        max_bytes=255 - len((collision_suffix + ext).encode("utf-8")),
    )
    return f"{title}{collision_suffix}{ext}"


def resolved_video_output_target(
    output_dir: Path, info: dict[str, Any], ext: str
) -> tuple[Path, str]:
    """Allocate one path budget while preserving the canonical hierarchy."""
    return _allocate_video_output_target(output_dir, info, ext)


def _video_output_collision_target(
    output_dir: Path, info: dict[str, Any], ext: str, collision_index: int
) -> Path:
    directory, filename = resolved_video_output_target(output_dir, info, ext)
    if collision_index:
        suffix = f" ({collision_index})"
        # Preserve the already allocated video directory so later reuse still
        # discovers collision outputs in the canonical namespace.
        fixed_units = len(str(directory / (suffix + ext)).encode("utf-16-le")) // 2
        title_budget = WINDOWS_SAFE_PATH_LIMIT - fixed_units
        if title_budget < 1:
            raise OutputPathBudgetError()
        filename = video_file_name(
            info, ext, max_title_len=min(120, title_budget), collision_suffix=suffix
        )
    candidate = directory / filename
    if _path_would_exceed_windows_safe_limit(candidate):
        raise OutputPathBudgetError()
    return candidate


def preflight_video_output_target(
    output_dir: Path, info: dict[str, Any], ext: str
) -> Path:
    """Check a bounded new-output allocation without creating folders or files."""
    for collision_index in range(10_000):
        candidate = _video_output_collision_target(
            output_dir, info, ext, collision_index
        )
        if not os.path.lexists(candidate):
            return candidate
    raise RuntimeError(
        "VODForge could not allocate a distinct output filename after "
        "10,000 existing conflicts."
    )


def collect_staged_media_files(
    staging_dir: Path,
    info: dict[str, Any],
    *,
    expected_extension: str,
) -> list[tuple[dict[str, Any], Path]]:
    collected: list[tuple[dict[str, Any], Path]] = []
    for video in iter_video_infos(info):
        video_id = str(video.get("id") or "").strip()
        if not video_id:
            continue
        staged = _find_staged_media_file(
            staging_dir / video_id,
            video_id,
            expected_extension=expected_extension,
        ) or _find_staged_media_file(
            staging_dir, video_id, expected_extension=expected_extension
        )
        if staged is not None:
            collected.append((video, staged))
    return collected


def package_downloaded_media_from_staging(
    staging_dir: Path,
    output_dir: Path,
    info: dict[str, Any],
    *,
    expected_extension: str | None = None,
    staged_media: list[tuple[dict[str, Any], Path]] | None = None,
    control_check: Any | None = None,
) -> list[Path]:
    packaged: list[Path] = []
    if staged_media is None:
        extensions = (
            [expected_extension]
            if expected_extension
            else list(STAGED_MEDIA_EXTENSIONS)
        )
        staged_media = []
        for extension in extensions:
            staged_media.extend(
                collect_staged_media_files(
                    staging_dir, info, expected_extension=extension
                )
            )
            if staged_media:
                break
    for video, staged in staged_media:
        ext = (
            expected_extension.lower() if expected_extension else staged.suffix.lower()
        )
        # Commit relative to a freshly verified directory handle; allocation
        # includes each collision suffix in the same complete-path budget.
        for collision_index in range(10_000):
            candidate = _video_output_collision_target(
                output_dir, video, ext, collision_index
            )
            try:
                commit_file_beneath(
                    staged,
                    output_dir,
                    candidate,
                    control_check=control_check,
                    replace_existing=False,
                )
            except FileExistsError:
                continue
            target = candidate
            break
        else:
            raise RuntimeError(
                "VODForge could not allocate a distinct output filename after "
                "10,000 existing conflicts."
            )
        remember_video_output_dir(video, target.parent)
        packaged.append(target)
    return packaged


def software_transcode_thread_budget() -> int:
    """Reserve two logical CPUs where possible, with at most four worker threads.

    FFmpeg can still perform additional audio/I/O work; this is a conservative
    codec/filter budget, not a process-wide CPU quota. Throughput may decrease.
    """
    return max(1, min(4, (os.cpu_count() or 1) - 2))


def build_vod_ffmpeg_command(
    ffmpeg: str,
    source: Path,
    output: Path,
    video_bitrate_kbps: int = STRICT_VIDEO_BITRATE_KBPS,
    audio_bitrate_kbps: int = STRICT_AUDIO_BITRATE_KBPS,
    audio_sample_rate: str = AUDIO_SAMPLE_RATE,
    audio_channels: str = AUDIO_CHANNELS,
    audio_codec: ManualAudioCodec = ManualAudioCodec.AAC,
    x264_preset: str = "medium",
    use_nvenc: bool = False,
    preserve_attached_picture: bool = False,
    preserve_metadata: bool | None = None,
    preserve_caption_metadata: int = 0,
    video_crf: int | None = None,
    nvenc_cq: int | None = None,
    keyframe_seconds: float | None = None,
    fps: float | None = None,
    constant_frame_rate: bool = False,
    video_maxrate_kbps: int | None = None,
) -> list[str]:
    """Encode the selected quality or constrained-CBR contract."""
    if video_crf is not None and not 1 <= video_crf <= 51:
        raise ValueError("Video CRF must be between 1 and 51 for H.264 High profile.")
    if nvenc_cq is not None and (video_crf is None or not 1 <= nvenc_cq <= 51):
        raise ValueError(
            "NVENC CQ requires a quality plan and must be between 1 and 51."
        )
    # Explicit Custom CRF remains x264; automatic presets carry calibrated CQ.
    use_nvenc = use_nvenc and (video_crf is None or nvenc_cq is not None)
    # Scope decoder and encoder options separately around -i. Restrict only the
    # software path; preserve NVENC's existing hardware encoding contract.
    thread_budget = str(software_transcode_thread_budget())
    software_input_args = (
        [
            "-threads:v:0",
            thread_budget,
            "-filter_threads",
            thread_budget,
            "-filter_complex_threads",
            thread_budget,
        ]
        if not use_nvenc
        else []
    )
    software_output_args = ["-threads:v:0", thread_budget] if not use_nvenc else []
    video_bitrate = f"{int(video_bitrate_kbps)}k"
    audio_bitrate = f"{int(audio_bitrate_kbps)}k"
    buffer_size = f"{int(video_bitrate_kbps) * 2}k"
    codec_option = "-c:v:0" if preserve_attached_picture else "-c:v"
    preset_option = "-preset:v:0" if preserve_attached_picture else "-preset"
    rate_control_option = "-rc:v:0" if preserve_attached_picture else "-rc"
    bitrate_option = "-b:v:0" if preserve_attached_picture else "-b:v"
    minrate_option = "-minrate:v:0" if preserve_attached_picture else "-minrate"
    maxrate_option = "-maxrate:v:0" if preserve_attached_picture else "-maxrate"
    buffer_option = "-bufsize:v:0" if preserve_attached_picture else "-bufsize"
    pixel_format_option = "-pix_fmt:v:0" if preserve_attached_picture else "-pix_fmt"
    profile_option = "-profile:v:0" if preserve_attached_picture else "-profile:v"
    x264_params_option = (
        "-x264-params:v:0" if preserve_attached_picture else "-x264-params"
    )
    video_args = (
        [
            codec_option,
            "h264_nvenc",
            preset_option,
            "p6",
            "-tune:v:0",
            "hq",
            "-rc-lookahead:v:0",
            "20",
            "-bf:v:0",
            "3",
            "-temporal-aq:v:0",
            "1",
            "-multipass:v:0",
            "fullres",
            rate_control_option,
            "cbr",
            bitrate_option,
            video_bitrate,
            minrate_option,
            video_bitrate,
            maxrate_option,
            video_bitrate,
            buffer_option,
            buffer_size,
            pixel_format_option,
            "yuv420p",
            profile_option,
            "high",
        ]
        if use_nvenc
        else [
            codec_option,
            "libx264",
            preset_option,
            x264_preset,
            bitrate_option,
            video_bitrate,
            minrate_option,
            video_bitrate,
            maxrate_option,
            video_bitrate,
            buffer_option,
            buffer_size,
            pixel_format_option,
            "yuv420p",
            profile_option,
            "high",
            x264_params_option,
            "nal-hrd=cbr:force-cfr=1:8x8dct=1",
        ]
    )
    if video_crf is not None:
        video_args = [
            codec_option,
            "libx264",
            preset_option,
            x264_preset,
            "-crf:v:0",
            str(video_crf),
            pixel_format_option,
            "yuv420p",
            profile_option,
            "high",
            # x264's ultrafast preset otherwise disables every High-profile
            # tool; -profile high alone only sets an upper constraint.
            x264_params_option,
            "8x8dct=1",
        ]
        if use_nvenc:
            video_args = [
                codec_option,
                "h264_nvenc",
                preset_option,
                "p6",
                rate_control_option,
                "vbr",
                "-cq:v:0",
                str(nvenc_cq),
                bitrate_option,
                "0",
                "-tune:v:0",
                "hq",
                "-rc-lookahead:v:0",
                "20",
                "-bf:v:0",
                "3",
                "-temporal-aq:v:0",
                "1",
                "-multipass:v:0",
                "fullres",
                pixel_format_option,
                "yuv420p",
                profile_option,
                "high",
            ]
        if video_maxrate_kbps is not None:
            if video_maxrate_kbps <= 0:
                raise ValueError("Maximum video bitrate must be positive.")
            video_args.extend(
                [
                    maxrate_option,
                    f"{video_maxrate_kbps}k",
                    buffer_option,
                    f"{video_maxrate_kbps * 2}k",
                ]
            )
    if keyframe_seconds is not None:
        if keyframe_seconds <= 0 or not math.isfinite(keyframe_seconds):
            raise ValueError("Keyframe interval must be finite and positive.")
        video_args.extend(
            ["-force_key_frames:v:0", f"expr:gte(t,n_forced*{keyframe_seconds:g})"]
        )
        if fps and math.isfinite(fps) and fps > 0:
            video_args.extend(["-g:v:0", str(max(1, round(fps * keyframe_seconds)))])
    if constant_frame_rate:
        video_args.extend(["-fps_mode:v:0", "cfr"])
        if fps and math.isfinite(fps) and fps > 0:
            video_args.extend(["-r:v:0", f"{fps:.8f}"])
    primary_video_map = "0:V:0" if preserve_attached_picture else "0:v:0"
    map_args = ["-map", primary_video_map, "-map", "0:a:0?", "-map", "0:s?"]
    artwork_args: list[str] = []
    if preserve_attached_picture:
        map_args.extend(("-map", "0:v:disp:attached_pic:0?"))
        artwork_args.extend(
            (
                "-c:v:1",
                "copy",
                "-disposition:v:0",
                "default",
                "-disposition:v:1",
                "attached_pic",
                "-metadata:s:v:1",
                "title=Album cover",
                "-metadata:s:v:1",
                "comment=Cover (front)",
            )
        )
    metadata_args: list[str] = []
    if preserve_metadata is not None:
        metadata_args.extend(("-map_metadata", "0" if preserve_metadata else "-1"))
    if not 0 <= preserve_caption_metadata <= 2:
        raise ValueError("At most two selected subtitle metadata tracks are supported.")
    for index in range(preserve_caption_metadata):
        metadata_args.extend((f"-map_metadata:s:s:{index}", f"0:s:s:{index}"))
    return [
        ffmpeg,
        "-y",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "warning",
        *software_input_args,
        "-i",
        str(source),
        *map_args,
        *video_args,
        *software_output_args,
        "-movflags",
        "+faststart",
        "-c:a",
        audio_codec.ffmpeg_encoder,
        "-b:a",
        audio_bitrate,
        "-ar",
        str(audio_sample_rate),
        "-ac",
        str(audio_channels),
        "-c:s",
        "mov_text",
        *metadata_args,
        *artwork_args,
        "-nostats",
        "-progress",
        "pipe:1",
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


def run_ffprobe_json(
    ffprobe: str,
    path: Path,
    *,
    timeout_seconds: float = FFPROBE_TIMEOUT_SECONDS,
    control_check: Any | None = None,
) -> dict[str, Any]:
    process_options = hidden_window_subprocess_kwargs()
    command = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_entries",
        "format=format_name,size,duration:format_tags:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,bit_rate,pix_fmt,profile,sample_rate,channels:stream_disposition:stream_tags=language",
        str(path),
    ]

    def run(command: list[str]) -> subprocess.CompletedProcess[str]:
        if control_check is not None:
            return run_cancellable_process_capture(
                command,
                timeout_seconds=timeout_seconds,
                control_check=control_check,
                check=True,
                **process_options,
            )
        # The media path is one argv entry; no provider metadata becomes a command string.
        return subprocess.run(  # nosec B603
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            **process_options,
        )

    result = run(command)
    data = json.loads(result.stdout or "{}")
    if not isinstance(data, dict):
        raise RuntimeError(  # noqa: TRY004 - provider protocol failures use RuntimeError
            "ffprobe returned an invalid top-level result"
        )
    from .audio_bitrate import measure_packet_average, needs_packet_average

    if needs_packet_average(data):
        average = measure_packet_average(ffprobe, path, run)
        if average is not None:
            data["measured_audio_packet_bps"] = average
    return data


def _ffprobe_for_ffmpeg(ffmpeg: str) -> str | None:
    ffmpeg_path = Path(ffmpeg)
    sibling_names = (
        ["ffprobe.exe", "ffprobe"] if is_windows() else ["ffprobe", "ffprobe.exe"]
    )
    for name in sibling_names:
        candidate = ffmpeg_path.with_name(name)
        if candidate.exists():
            return str(candidate)
    return shutil.which("ffprobe")


def validate_output_artifact(
    path: Path,
    output_type: OutputType,
    ffprobe: str,
    *,
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
    return _validate_output_artifact(
        path,
        output_type,
        ffprobe,
        probe_reader=run_ffprobe_json,
        expected_duration_seconds=expected_duration_seconds,
        require_audio=require_audio,
        expected_audio_codec=expected_audio_codec,
        plan=plan,
        embed_metadata=embed_metadata,
        embed_cover_art=embed_cover_art,
        expected_tags=expected_tags,
        ffprobe_data=ffprobe_data,
        control_check=control_check,
    )


def terminate_and_reap_process(
    process: Any, *, timeout_seconds: float = PROCESS_TERMINATE_TIMEOUT_SECONDS
) -> None:
    ACTIVE_CHILD_PROCESS_REGISTRY.set_diagnostic(write_diagnostic)
    ACTIVE_CHILD_PROCESS_REGISTRY.terminate_and_reap(
        process, timeout_seconds=timeout_seconds
    )


def set_active_child_process_observer(
    observer: Callable[[str, Any], None] | None,
) -> None:
    ACTIVE_CHILD_PROCESS_REGISTRY.set_diagnostic(write_diagnostic)
    ACTIVE_CHILD_PROCESS_REGISTRY.set_observer(observer)


def register_active_child_process(process: Any) -> None:
    ACTIVE_CHILD_PROCESS_REGISTRY.set_diagnostic(write_diagnostic)
    ACTIVE_CHILD_PROCESS_REGISTRY.register(
        process, timeout_seconds=PROCESS_TERMINATE_TIMEOUT_SECONDS
    )


def unregister_active_child_process(process: Any) -> None:
    ACTIVE_CHILD_PROCESS_REGISTRY.set_diagnostic(write_diagnostic)
    ACTIVE_CHILD_PROCESS_REGISTRY.unregister(process)


def child_process_has_exited(process: Any, *, confirmed_exited: bool = False) -> bool:
    return ACTIVE_CHILD_PROCESS_REGISTRY.has_exited(
        process, confirmed_exited=confirmed_exited
    )


def finalize_active_child_process(
    process: Any, *, confirmed_exited: bool = False
) -> bool:
    """Release process ownership only after exit is positively confirmed.

    If an exceptional path leaves a child alive, retain it in the registry so
    application-close cleanup can retry instead of losing ownership of a writer.
    """
    ACTIVE_CHILD_PROCESS_REGISTRY.set_diagnostic(write_diagnostic)
    return ACTIVE_CHILD_PROCESS_REGISTRY.finalize(
        process,
        timeout_seconds=PROCESS_TERMINATE_TIMEOUT_SECONDS,
        confirmed_exited=confirmed_exited,
    )


def terminate_all_active_child_processes(
    *, deadline_monotonic: float | None = None
) -> None:
    ACTIVE_CHILD_PROCESS_REGISTRY.set_diagnostic(write_diagnostic)
    ACTIVE_CHILD_PROCESS_REGISTRY.terminate_all(
        timeout_seconds=PROCESS_TERMINATE_TIMEOUT_SECONDS,
        deadline_monotonic=deadline_monotonic,
    )


def tracked_ytdlp_popen_class(
    base_class: type, control_check: Any | None = None
) -> type:
    """Wrap yt-dlp's process class so every provider-owned child remains ours to reap."""

    class VODForgeTrackedPopen(base_class):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            register_active_child_process(self)
            if control_check is not None:
                try:
                    control_check()
                except Exception:
                    finalize_active_child_process(self)
                    raise

        def wait(self, *args: Any, **kwargs: Any) -> Any:
            result = super().wait(*args, **kwargs)
            unregister_active_child_process(self)
            return result

        def communicate(self, *args: Any, **kwargs: Any) -> Any:
            try:
                return super().communicate(*args, **kwargs)
            finally:
                if child_process_has_exited(self):
                    unregister_active_child_process(self)

        def __exit__(self, *args: object, **kwargs: Any) -> Any:
            try:
                return super().__exit__(*args, **kwargs)
            finally:
                finalize_active_child_process(self)

    VODForgeTrackedPopen.__name__ = "VODForgeTrackedYtDlpPopen"
    return VODForgeTrackedPopen


def run_tracked_ytdlp_operation(
    step: Callable[[], Any], *, control_check: Any | None = None
) -> Any:
    """Own child processes and fragment files for one serialized yt-dlp operation."""
    with _YTDLP_SUBPROCESS_TRACKING_LOCK:
        utils_module = importlib.import_module("yt_dlp.utils")
        original_class = utils_module.Popen
        tracked_class = tracked_ytdlp_popen_class(original_class, control_check)
        fragment_class = importlib.import_module(
            "yt_dlp.downloader.fragment"
        ).FragmentFD
        original_prepare = fragment_class._prepare_frag_download
        for module_name, module in tuple(sys.modules.items()):
            if module is None or not (
                module_name == "yt_dlp" or module_name.startswith("yt_dlp.")
            ):
                continue
            if getattr(module, "Popen", None) is original_class:
                setattr(  # noqa: B010 - module alias patching preserves child tracking
                    module, "Popen", tracked_class
                )
        try:
            with ExitStack() as fragment_files:

                def close_fragment_destination(context):
                    stream = context.get("dest_stream")
                    if stream is not None and context.get("tmpfilename") != "-":
                        stream.close()

                def prepare_fragment(downloader, context):
                    # FragmentFD does not close its destination when our progress
                    # hook raises Cancel/Skip. Own that destination until the
                    # operation unwinds, before Windows staging cleanup runs.
                    # Register first so a partially failed preparation is covered.
                    fragment_files.callback(close_fragment_destination, context)
                    return original_prepare(downloader, context)

                fragment_class._prepare_frag_download = prepare_fragment
                if control_check is not None:
                    control_check()
                return step()
        finally:
            fragment_class._prepare_frag_download = original_prepare
            # Include modules imported during the operation; they may have
            # copied the temporarily patched class from yt_dlp.utils.
            for module_name, module in tuple(sys.modules.items()):
                if module is None or not (
                    module_name == "yt_dlp" or module_name.startswith("yt_dlp.")
                ):
                    continue
                if getattr(module, "Popen", None) is tracked_class:
                    setattr(  # noqa: B010 - module alias restoration preserves child tracking
                        module, "Popen", original_class
                    )


def _extract_playlist_source_step(
    ytdlp_module: Any,
    playlist_options: dict[str, Any],
    source_url: str,
    *,
    control_check: Callable[[], None],
    emit_log: Callable[[str], None],
) -> tuple[dict[str, Any] | None, tuple[Any, ...]]:
    """Extract playlist identity with the same bounded provider retry contract."""
    write_diagnostic("playlist extraction start")

    def extract() -> tuple[Any, tuple[Any, ...]]:
        with ytdlp_module.YoutubeDL(playlist_options) as ydl:
            extracted = ydl.extract_info(source_url, download=False)
            return extracted, snapshot_ytdlp_session_cookies(ydl)

    def report_retry(
        attempt: int,
        maximum: int,
        delay: float,
        exc: Exception,
    ) -> None:
        message = source_analysis_retry_message(
            "playlist detection",
            attempt,
            maximum,
            delay,
            exc,
        )
        write_diagnostic(message)
        emit_log(message)

    extracted, session_cookies = run_with_bounded_transient_retries(
        lambda: run_tracked_ytdlp_operation(
            extract,
            control_check=control_check,
        ),
        control_check=control_check,
        on_retry=report_retry,
    )
    write_diagnostic("playlist extraction completed")
    return (
        extracted if isinstance(extracted, dict) else None,
        session_cookies,
    )


def _analyze_source_formats_step(
    ytdlp_module: Any,
    preflight_options: dict[str, Any],
    session_cookies: tuple[Any, ...],
    video_url: str,
    label: str,
    *,
    control_check: Callable[[], None],
    emit_log: Callable[[str], None],
) -> tuple[dict[str, Any] | None, tuple[Any, ...]]:
    """Analyze one playlist item using only its immutable iteration inputs."""
    write_diagnostic(f"{label} analysis start")
    analysis_started = time.monotonic()

    def extract() -> tuple[Any, tuple[Any, ...]]:
        with ytdlp_module.YoutubeDL(preflight_options) as ydl:
            seed_ytdlp_session_cookies(ydl, session_cookies)
            extracted = ydl.extract_info(video_url, download=False)
            return extracted, snapshot_ytdlp_session_cookies(ydl)

    def report_retry(
        attempt: int,
        maximum: int,
        delay: float,
        exc: Exception,
    ) -> None:
        message = source_analysis_retry_message(
            f"{label} source analysis",
            attempt,
            maximum,
            delay,
            exc,
        )
        write_diagnostic(message)
        emit_log(message)

    extracted, updated_session_cookies = run_with_bounded_transient_retries(
        lambda: run_tracked_ytdlp_operation(
            extract,
            control_check=control_check,
        ),
        control_check=control_check,
        on_retry=report_retry,
    )
    write_diagnostic(
        f"{label} analysis completed "
        f"elapsed_seconds={time.monotonic() - analysis_started:.3f}"
    )
    return (
        extracted if isinstance(extracted, dict) else None,
        updated_session_cookies,
    )


def _download_preflight_result_step(
    ytdlp_module: Any,
    ydl_options: dict[str, Any],
    preflight_info: dict[str, Any],
    session_cookies: tuple[Any, ...],
    *,
    control_check: Callable[[], None],
) -> tuple[Any, tuple[Any, ...]]:
    """Download one analyzed item using only its bound iteration inputs."""
    with ytdlp_module.YoutubeDL(ydl_options) as ydl:
        downloaded_info = process_download_from_preflight(
            ydl,
            preflight_info,
            session_cookies=session_cookies,
            control_check=control_check,
        )
        return downloaded_info, snapshot_ytdlp_session_cookies(ydl)


def _download_with_audio_url_refresh(
    ytdlp_module: Any,
    options: dict[str, Any],
    info: dict[str, Any],
    session_cookies: tuple[Any, ...],
    guard: SplitTransferRefresh | None,
    *,
    refresh: Callable[[], tuple[dict[str, Any] | None, tuple[Any, ...]]],
    control_check: Callable[[], None],
    emit_log: Callable[[str], None],
) -> tuple[Any, tuple[Any, ...]]:
    transfer_options = dict(options)
    if guard is not None:
        transfer_options["progress_hooks"] = [
            guard.observe,
            *(options.get("progress_hooks") or []),
        ]
    try:
        return _download_preflight_result_step(
            ytdlp_module,
            transfer_options,
            info,
            session_cookies,
            control_check=control_check,
        )
    except Exception as exc:
        if guard is None or not guard.eligible(
            transient_network_error_status(exc), _network_exception_chain(exc)
        ):
            raise
        control_check()
        emit_log(
            "Audio transfer was rejected after video completed; refreshing source metadata once with the same access settings."
        )
        fresh, refreshed_cookies = refresh()
        control_check()
        fresh = guard.checked_refresh(fresh)
        # Re-select exactly the original streams. /best is not a transfer-failure
        # fallback and must not silently reduce quality during recovery.
        transfer_options["format"] = f"{guard.video_id}+{guard.audio_id}"
        emit_log(
            "Fresh audio URL available for the same selected formats; resuming the staged transfer once without redownloading completed video."
        )
        try:
            return _download_preflight_result_step(
                ytdlp_module,
                transfer_options,
                fresh,
                refreshed_cookies,
                control_check=control_check,
            )
        except Exception as retry_error:
            if transient_network_error_status(retry_error) == 403:
                raise TransferRefreshError(
                    "Audio access was rejected again after one metadata refresh; stopped without changing access settings or lowering quality."
                ) from retry_error
            raise


def run_cancellable_process_capture(
    command: list[str],
    *,
    timeout_seconds: float,
    control_check: Any | None = None,
    check: bool = False,
    stderr_to_stdout: bool = False,
    startupinfo: Any | None = None,
    creationflags: int = 0,
) -> subprocess.CompletedProcess[str]:
    """Capture a bounded child process while polling app cancellation."""
    # Internal callers pass argv lists for ffprobe/FFmpeg; shell execution is never used.
    process = subprocess.Popen(  # nosec B603
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if stderr_to_stdout else subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        startupinfo=startupinfo,
        creationflags=creationflags,
    )
    register_active_child_process(process)
    deadline = time.monotonic() + timeout_seconds
    confirmed_exited = False
    try:
        while True:
            if control_check is not None:
                try:
                    control_check()
                except Exception:
                    terminate_and_reap_process(process)
                    raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                terminate_and_reap_process(process)
                raise subprocess.TimeoutExpired(command, timeout_seconds)
            try:
                stdout, stderr = process.communicate(timeout=min(0.10, remaining))
                confirmed_exited = True
                break
            except subprocess.TimeoutExpired:
                continue
        result = subprocess.CompletedProcess(
            command, process.returncode, stdout or "", stderr or ""
        )
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode,
                command,
                output=result.stdout,
                stderr=result.stderr,
            )
        return result
    finally:
        finalize_active_child_process(process, confirmed_exited=confirmed_exited)


def transcode_temp_paths(video_path: Path) -> tuple[Path, Path]:
    return video_path.with_name(BACKEND_TEMP_OUTPUT_NAME), video_path.with_name(
        BACKEND_ORIGINAL_BACKUP_NAME
    )


@dataclass(frozen=True)
class _TranscodeProcessResult:
    return_code: int
    output_lines: tuple[str, ...]


def _emit_transcode_progress_line(
    text_line: str,
    *,
    duration_seconds: float | None,
    progress_callback: Callable[[float], None] | None,
) -> None:
    if not progress_callback or not duration_seconds:
        return
    key, separator, value = text_line.partition("=")
    if not separator or key != "out_time_ms":
        return
    try:
        fraction = min(
            1.0,
            max(
                0.0,
                (float(value) / 1_000_000) / float(duration_seconds),
            ),
        )
        progress_callback(fraction)
    except (TypeError, ValueError, ZeroDivisionError):
        # Preserve the established best-effort progress contract, including
        # these errors when raised by the internal callback itself.
        pass


def _check_transcode_control_while_running(
    control_check: Callable[[], None] | None,
    process: Any,
    output_reader: threading.Thread,
) -> None:
    if control_check is None:
        return
    try:
        control_check()
    except Exception:
        terminate_and_reap_process(process)
        output_reader.join(timeout=PROCESS_TERMINATE_TIMEOUT_SECONDS)
        raise


def _run_cancellable_transcode_process(
    command: list[str],
    *,
    failure_prefix: str,
    duration_seconds: float | None,
    progress_callback: Callable[[float], None] | None,
    control_check: Callable[[], None] | None,
) -> _TranscodeProcessResult:
    """Run one FFmpeg encode while retaining cancellation and child ownership."""
    process_options = hidden_window_subprocess_kwargs()
    # The caller supplies a fixed FFmpeg argv list with paths as single entries.
    process = subprocess.Popen(  # nosec B603
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        **process_options,
    )
    process_confirmed_exited = False
    try:
        register_active_child_process(process)
        output_lines: list[str] = []
        encoder_output = process.stdout
        if encoder_output is None:
            raise RuntimeError(
                f"{failure_prefix}: FFmpeg did not expose a captured output stream"
            )
        output_queue: queue.Queue[str | None] = queue.Queue()

        def read_encoder_output() -> None:
            try:
                for output_line in encoder_output:
                    output_queue.put(output_line)
            finally:
                output_queue.put(None)

        output_reader = threading.Thread(target=read_encoder_output, daemon=True)
        output_reader.start()
        while True:
            _check_transcode_control_while_running(
                control_check,
                process,
                output_reader,
            )
            try:
                line = output_queue.get(timeout=0.10)
            except queue.Empty:
                continue
            if line is None:
                break
            text_line = line.strip()
            if text_line:
                output_lines.append(text_line)
                output_lines = output_lines[-80:]
            _emit_transcode_progress_line(
                text_line,
                duration_seconds=duration_seconds,
                progress_callback=progress_callback,
            )
        if control_check is not None:
            control_check()
        return_code = process.wait()
        process_confirmed_exited = True
        output_reader.join(timeout=1)
        return _TranscodeProcessResult(
            return_code=return_code,
            output_lines=tuple(output_lines),
        )
    finally:
        finalize_active_child_process(
            process, confirmed_exited=process_confirmed_exited
        )


def transcode_to_vod_streaming_settings(
    path: Path,
    ffmpeg: str,
    plan: ExportPlan | None = None,
    *,
    duration_seconds: float | None = None,
    progress_callback: Any | None = None,
    use_nvenc: bool = False,
    preserve_attached_picture: bool = False,
    preserve_metadata: bool | None = None,
    preserve_caption_metadata: int = 0,
    control_check: Any | None = None,
) -> Path:
    """Re-encode an MP4 to the selected VODForge delivery plan."""
    if path.suffix.lower() != ".mp4" or not path.exists():
        return path
    temp_output, backup = transcode_temp_paths(path)
    video_bitrate = plan.video_bitrate_kbps if plan else STRICT_VIDEO_BITRATE_KBPS
    audio_bitrate = plan.audio_bitrate_kbps if plan else STRICT_AUDIO_BITRATE_KBPS
    audio_sample_rate = plan.audio_sample_rate if plan else AUDIO_SAMPLE_RATE
    audio_channels = plan.audio_channels if plan else AUDIO_CHANNELS
    audio_codec = plan.output_audio_codec if plan else ManualAudioCodec.AAC
    audio_codec_label = audio_codec.value
    x264_preset = plan.x264_preset if plan else "medium"
    rate_label = "quality" if plan and plan.video_crf is not None else "CBR"
    failure_prefix = f"VODForge H.264/{audio_codec_label} {rate_label} transcode failed"

    cleanup_legacy_encode_sidecars(path)
    if temp_output.exists():
        temp_output.unlink()
    if backup.exists():
        backup.unlink()

    try:
        command = build_vod_ffmpeg_command(
            ffmpeg,
            path,
            temp_output,
            video_bitrate_kbps=video_bitrate,
            audio_bitrate_kbps=audio_bitrate,
            audio_sample_rate=audio_sample_rate,
            audio_channels=audio_channels,
            audio_codec=audio_codec,
            x264_preset=x264_preset,
            use_nvenc=use_nvenc,
            preserve_attached_picture=preserve_attached_picture,
            preserve_metadata=preserve_metadata,
            preserve_caption_metadata=preserve_caption_metadata,
            video_crf=plan.video_crf if plan else None,
            nvenc_cq=plan.nvenc_cq if plan else None,
            keyframe_seconds=plan.keyframe_seconds if plan else None,
            fps=plan.fps if plan else None,
            constant_frame_rate=plan.constant_frame_rate if plan else False,
            video_maxrate_kbps=plan.video_maxrate_kbps if plan else None,
        )
        process_result = _run_cancellable_transcode_process(
            command,
            failure_prefix=failure_prefix,
            duration_seconds=duration_seconds,
            progress_callback=progress_callback,
            control_check=control_check,
        )
        if process_result.return_code != 0:
            tail = "\n".join(process_result.output_lines[-40:])
            raise RuntimeError(
                f"{failure_prefix} for {path.name}; ffmpeg exited with code "
                f"{process_result.return_code}: {tail[-4000:]}"
            )
        if not temp_output.is_file() or temp_output.stat().st_size <= 0:
            raise RuntimeError(
                f"{failure_prefix} for {path.name}; FFmpeg produced no usable output"
            )
        if progress_callback:
            progress_callback(1.0)
        # The downloaded source and temp live in the per-job staging directory.
        # Replacing in place is atomic and leaves the source intact if commit fails.
        os.replace(temp_output, path)
        backup.unlink(missing_ok=True)
        return path
    except Exception as exc:
        try:
            temp_output.unlink(missing_ok=True)
        except OSError as cleanup_exc:
            write_diagnostic(
                f"transcode temp cleanup failed for {temp_output}: {cleanup_exc}"
            )
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(f"{failure_prefix} for {path.name}: {exc}") from exc


def _save_jpeg_under_size(
    image: Any, path: Path, max_bytes: int = THUMBNAIL_MAX_BYTES
) -> None:
    rgb = image.convert("RGB")

    def encode(candidate: Any, quality: int) -> bytes:
        from io import BytesIO

        buf = BytesIO()
        candidate.save(
            buf, format="JPEG", quality=quality, optimize=True, progressive=True
        )
        return buf.getvalue()

    quality_steps = (92, 88, 84, 80, 76, 72, 68, 64, 60, 55, 50, 45)
    best_data = encode(rgb, quality_steps[0])
    if len(best_data) <= max_bytes:
        path.write_bytes(best_data)
        return
    for quality in quality_steps[1:]:
        data = encode(rgb, quality)
        if len(data) < len(best_data):
            best_data = data
        if len(data) <= max_bytes:
            path.write_bytes(data)
            return

    working = rgb
    while min(working.size) > 16:
        shrink = max(0.50, min(0.90, (max_bytes / len(best_data)) ** 0.5 * 0.95))
        new_size = (
            max(16, int(working.size[0] * shrink)),
            max(16, int(working.size[1] * shrink)),
        )
        if new_size == working.size:
            new_size = (max(16, working.size[0] - 1), max(16, working.size[1] - 1))
        resample = getattr(Image, "Resampling", Image).LANCZOS
        working = working.resize(new_size, resample)
        for quality in (82, 76, 70, 64, 58, 52, 46, 40, 34, 28, 20, 12, 5):
            data = encode(working, quality)
            if len(data) < len(best_data):
                best_data = data
            if len(data) <= max_bytes:
                path.write_bytes(data)
                return

    if len(best_data) > max_bytes:
        raise RuntimeError(f"Unable to compress thumbnail below {max_bytes} bytes")
    path.write_bytes(best_data)


def decode_bounded_thumbnail(data: bytes) -> Any:
    """Decode remote thumbnail bytes without allowing compressed pixel bombs."""
    if Image is None:
        raise RuntimeError("Pillow is required to validate thumbnail dimensions")
    from io import BytesIO

    try:
        with warnings.catch_warnings():
            decompression_warning = getattr(Image, "DecompressionBombWarning", Warning)
            warnings.simplefilter("error", decompression_warning)
            with Image.open(BytesIO(data)) as source:
                width, height = source.size
                if (
                    width <= 0
                    or height <= 0
                    or width > THUMBNAIL_MAX_DIMENSION
                    or height > THUMBNAIL_MAX_DIMENSION
                    or width * height > THUMBNAIL_MAX_PIXELS
                ):
                    raise RuntimeError(
                        "Thumbnail dimensions exceed the safe preview limit"
                    )
                source.verify()
            with Image.open(BytesIO(data)) as source:
                source.load()
                return source.copy()
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Thumbnail image is invalid or unsafe: {exc}") from exc


def save_thumbnail_image(
    output_dir: Path,
    info: dict[str, Any],
    *,
    filename: str = "thumbnail.jpeg",
    source_url: str | None = None,
    output_root: Path | None = None,
    on_result: Callable[[str], None] | None = None,
) -> Path | None:
    thumb = best_thumbnail_for_download(info)
    url = str((thumb or {}).get("url") or "")
    if not url:
        _report_sidecar_result(on_result, "unavailable")
        return None
    path = output_dir / filename
    data = download_bounded_url_bytes(url, source_url=source_url)
    before = _sidecar_destination_state(path) if on_result is not None else None
    if Image is None:
        if len(data) > THUMBNAIL_MAX_BYTES:
            raise RuntimeError(
                "Pillow is required to enforce the 300 KB thumbnail limit"
            )
        written = write_file_beneath(
            output_root if output_root is not None else output_dir,
            path,
            lambda staged: staged.write_bytes(data),
        )
    else:
        image = decode_bounded_thumbnail(data).convert("RGB")
        written = write_file_beneath(
            output_root if output_root is not None else output_dir,
            path,
            lambda staged: _save_jpeg_under_size(image, staged),
        )
    _report_sidecar_result(on_result, _sidecar_write_result(before))
    return written


def cached_thumbnail_path(
    info: dict[str, Any], *, data_dir: Path | None = None
) -> Path | None:
    """Return a private deterministic UI-thumbnail path without trusting source filenames."""
    thumb = best_thumbnail_for_download(info)
    url = str((thumb or {}).get("url") or "").strip()
    identity = (
        str(info.get("id") or "").strip() or url or str(info.get("title") or "").strip()
    )
    if not identity:
        return None
    output_type = metadata_output_type(info).value
    digest = hashlib.sha256(
        f"{identity}\0{output_type}".encode("utf-8", errors="replace")
    ).hexdigest()[:32]
    root = data_dir if data_dir is not None else application_data_dir()
    return root / "thumbnail-cache" / f"{digest}.jpeg"


def legacy_cached_thumbnail_paths(
    info: dict[str, Any], *, data_dir: Path | None = None
) -> tuple[Path, ...]:
    """Return every derivable v0.1.5 URL-sensitive cache path."""
    urls: list[str] = []

    def add_url(value: Any) -> None:
        if isinstance(value, dict):
            value = value.get("url")
        url = str(value or "").strip()
        if url not in urls:
            urls.append(url)

    add_url(best_thumbnail_for_download(info))
    add_url(info.get("best_thumbnail"))
    add_url(info.get("thumbnail"))
    # v0.1.5 keyed the cache by the exact selected URL, while its history row
    # could retain only a lower-resolution `thumbnail` URL. Reconstruct the
    # bounded, deterministic YouTube variants that yt-dlp used so a cold
    # upgrade can find the old private JPEG without guessing among unrelated
    # cache files. Query-bearing URLs cannot be reconstructed safely and will
    # simply be fetched into the stable cache when the network is available.
    provider_id = str(info.get("id") or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{6,128}", provider_id):
        for filename in (
            "maxresdefault.jpg",
            "hq720.jpg",
            "sddefault.jpg",
            "hqdefault.jpg",
            "mqdefault.jpg",
            "default.jpg",
            "0.jpg",
            "1.jpg",
            "2.jpg",
            "3.jpg",
        ):
            add_url(f"https://i.ytimg.com/vi/{provider_id}/{filename}")
            add_url(f"https://img.youtube.com/vi/{provider_id}/{filename}")
        for filename in (
            "maxresdefault.webp",
            "sddefault.webp",
            "hqdefault.webp",
            "mqdefault.webp",
            "default.webp",
        ):
            add_url(f"https://i.ytimg.com/vi_webp/{provider_id}/{filename}")
    if not urls:
        urls.append("")

    root = data_dir if data_dir is not None else application_data_dir()
    paths: list[Path] = []
    for url in urls:
        identity = (
            str(info.get("id") or "").strip()
            or url
            or str(info.get("title") or "").strip()
        )
        if not identity:
            continue
        digest = hashlib.sha256(
            f"{identity}\0{url}".encode("utf-8", errors="replace")
        ).hexdigest()[:32]
        path = root / "thumbnail-cache" / f"{digest}.jpeg"
        if path not in paths:
            paths.append(path)
    return tuple(paths)


def legacy_cached_thumbnail_path(
    info: dict[str, Any], *, data_dir: Path | None = None
) -> Path | None:
    """Return the first v0.1.5 cache candidate for compatibility callers."""
    paths = legacy_cached_thumbnail_paths(info, data_dir=data_dir)
    return paths[0] if paths else None


def existing_cached_thumbnail_path(
    info: dict[str, Any], *, data_dir: Path | None = None
) -> Path | None:
    """Prefer the stable cache key while retaining already-downloaded v0.1.5 art."""
    stable = cached_thumbnail_path(info, data_dir=data_dir)
    candidates = (stable, *legacy_cached_thumbnail_paths(info, data_dir=data_dir))
    for path in candidates:
        try:
            if (
                path is not None
                and path.is_file()
                and 0 < path.stat().st_size <= THUMBNAIL_MAX_BYTES
            ):
                if path == stable:
                    return path
                migrated = save_cached_thumbnail_bytes(
                    info, path.read_bytes(), data_dir=data_dir
                )
                return migrated or path
        except (OSError, RuntimeError):
            continue
    return None


def prune_thumbnail_cache(
    cache_dir: Path, *, max_items: int = THUMBNAIL_CACHE_MAX_ITEMS
) -> None:
    try:
        files = sorted(
            (path for path in cache_dir.glob("*.jpeg") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return
    for stale in files[max(0, max_items) :]:
        try:
            stale.unlink()
        except OSError:
            continue


def thumbnail_cache_lock(path: Path) -> threading.RLock:
    slot = int(
        hashlib.sha256(str(path).encode("utf-8", errors="replace")).hexdigest()[:8], 16
    )
    return _THUMBNAIL_CACHE_LOCKS[slot % len(_THUMBNAIL_CACHE_LOCKS)]


def save_cached_thumbnail_image(
    info: dict[str, Any],
    *,
    data_dir: Path | None = None,
    source_url: str | None = None,
    on_result: Callable[[str], None] | None = None,
) -> Path | None:
    path = cached_thumbnail_path(info, data_dir=data_dir)
    if path is None:
        _report_sidecar_result(on_result, "unavailable")
        return None
    with thumbnail_cache_lock(path):
        before = _sidecar_destination_state(path) if on_result is not None else None
        try:
            if path.is_file() and 0 < path.stat().st_size <= THUMBNAIL_MAX_BYTES:
                if Image is not None:
                    cached_image = decode_bounded_thumbnail(path.read_bytes())
                    cached_image.close()
                path.touch(exist_ok=True)
                _report_sidecar_result(on_result, "already_present")
                return path
        except (OSError, RuntimeError):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.stem}.{uuid.uuid4().hex}.tmp")
        try:
            saved = save_thumbnail_image(
                temporary.parent,
                info,
                filename=temporary.name,
                source_url=source_url,
            )
            if saved is None:
                _report_sidecar_result(on_result, "unavailable")
                return None
            if Image is not None:
                cached_image = decode_bounded_thumbnail(saved.read_bytes())
                cached_image.close()
            os.replace(saved, path)
            _report_sidecar_result(
                on_result, "repaired" if before else _sidecar_write_result(before)
            )
            prune_thumbnail_cache(path.parent)
            return path
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def save_cached_thumbnail_bytes(
    info: dict[str, Any],
    data: bytes,
    *,
    data_dir: Path | None = None,
) -> Path | None:
    """Persist already-bounded remote preview bytes for later offline deck use."""
    path = cached_thumbnail_path(info, data_dir=data_dir)
    if path is None:
        return None
    image = decode_bounded_thumbnail(data).convert("RGB")
    with thumbnail_cache_lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.stem}.{uuid.uuid4().hex}.tmp")
        try:
            _save_jpeg_under_size(image, temporary)
            os.replace(temporary, path)
            prune_thumbnail_cache(path.parent)
            return path
        finally:
            image.close()
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def save_custom_cached_thumbnail_image(
    info: dict[str, Any],
    source_path: Path,
    *,
    data_dir: Path | None = None,
    on_result: Callable[[str], None] | None = None,
) -> Path | None:
    """Make a user-selected cover the canonical private artwork for one item."""
    destination = cached_thumbnail_path(info, data_dir=data_dir)
    if destination is None:
        _report_sidecar_result(on_result, "unavailable")
        return None
    source_path = validate_custom_cover_art(source_path)
    if Image is None or ImageOps is None:
        raise RuntimeError("Pillow is required to cache custom cover art.")
    with thumbnail_cache_lock(destination):
        before = (
            _sidecar_destination_state(destination) if on_result is not None else None
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.stem}.{uuid.uuid4().hex}.tmp")
        try:
            with Image.open(source_path) as source:
                normalized = ImageOps.exif_transpose(source).convert("RGB")
                normalized.thumbnail(
                    (1600, 1600), getattr(Image, "Resampling", Image).LANCZOS
                )
                _save_jpeg_under_size(normalized, temporary)
            cached_image = decode_bounded_thumbnail(temporary.read_bytes())
            cached_image.close()
            os.replace(temporary, destination)
            _report_sidecar_result(on_result, _sidecar_write_result(before))
            prune_thumbnail_cache(destination.parent)
            return destination
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def prepare_custom_cover_art(source_path: Path, staging_dir: Path) -> Path:
    """Normalize custom artwork to a broadly compatible bounded JPEG."""
    source_path = validate_custom_cover_art(source_path)
    if Image is None or ImageOps is None:
        raise RuntimeError("Pillow is required to prepare custom cover art.")
    destination = staging_dir / "__vodforge-custom-cover.jpeg"
    try:
        with Image.open(source_path) as source:
            normalized = ImageOps.exif_transpose(source).convert("RGB")
            normalized.thumbnail(
                (1600, 1600), getattr(Image, "Resampling", Image).LANCZOS
            )
            _save_jpeg_under_size(
                normalized, destination, max_bytes=CUSTOM_COVER_MAX_OUTPUT_BYTES
            )
    except Exception as exc:
        raise RuntimeError(
            f"VODForge could not prepare the custom cover image: {exc}"
        ) from exc
    return destination


def embed_custom_mp3_cover_art(
    mp3_path: Path,
    cover_path: Path,
    ffmpeg: str,
    *,
    control_check: Any | None = None,
) -> Path:
    """Atomically attach a normalized custom front cover to one MP3."""
    mp3_path = Path(mp3_path)
    cover_path = Path(cover_path)
    if not mp3_path.is_file():
        raise RuntimeError("The staged MP3 was not found for custom cover embedding.")
    if not cover_path.is_file():
        raise RuntimeError("The prepared custom cover image was not found.")
    temporary = mp3_path.with_name(
        f".{mp3_path.stem}.vodforge-cover-{uuid.uuid4().hex}.mp3"
    )
    command = [
        ffmpeg,
        "-y",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(mp3_path),
        "-i",
        str(cover_path),
        "-map",
        "0:a:0",
        "-map",
        "1:v:0",
        "-map_metadata",
        "0",
        "-c:a",
        "copy",
        "-c:v",
        "copy",
        "-disposition:v:0",
        "attached_pic",
        "-write_id3v1",
        "1",
        "-id3v2_version",
        "3",
        "-metadata:s:v",
        "title=Album cover",
        "-metadata:s:v",
        "comment=Cover (front)",
        str(temporary),
    ]
    process_options = hidden_window_subprocess_kwargs()
    try:
        result = run_cancellable_process_capture(
            command,
            timeout_seconds=FFMPEG_COVER_TIMEOUT_SECONDS,
            control_check=control_check,
            check=False,
            stderr_to_stdout=True,
            **process_options,
        )
        if (
            result.returncode != 0
            or not temporary.is_file()
            or temporary.stat().st_size <= 0
        ):
            detail = next(
                (
                    line.strip()
                    for line in reversed(result.stdout.splitlines())
                    if line.strip()
                ),
                "FFmpeg did not produce an output file",
            )
            raise RuntimeError(f"Custom cover art could not be embedded: {detail}")
        os.replace(temporary, mp3_path)
        return mp3_path
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "Custom cover art embedding timed out before FFmpeg completed"
        ) from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


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


def _plans_by_video_id(
    info: dict[str, Any], mode: ExportMode, max_height: int
) -> dict[str, ExportPlan]:
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


def download_job_display_title(job: DownloadJob, *, queued: bool = False) -> str:
    """Return resolved run metadata or a neutral state, never a raw source URL."""
    title = str((job.preview_info or {}).get("title") or "").strip()
    if title:
        return title
    state = "Queued" if queued else "Preparing"
    media = "video" if job.output_type == OutputType.MP4 else "audio"
    return f"{state} {media} run"


def focus_metadata_profile_text(info: dict[str, Any], record_kind: str) -> str:
    """Describe saved output or a completed preview without redundant placeholders."""
    output_type = metadata_output_type(info)
    _source, output, _warnings = _encoding_summary_sections(info)
    tokens = [output_type.value]
    resolution = str(
        output.get("Output resolution") or output.get("Resolution") or ""
    ).strip()
    if resolution.casefold() not in {
        "",
        "unknown",
        "not available",
        "mp4",
        "audio only",
    }:
        tokens.append(resolution)
    mode = str(
        output.get("Output rate-control mode")
        or output.get("Target audio bitrate")
        or ""
    ).strip()
    if mode.casefold() not in {"", "unknown", "not available", "not applicable"}:
        tokens.append(mode)
    if record_kind == "preview":
        tokens.append("Preview complete")
    elif record_kind == "completed" and len(tokens) == 1:
        tokens.append("Completed")
    return "  •  ".join(tokens)


def preview_output_summary_display() -> str:
    """Explain the boundary between metadata preview and produced media."""
    return (
        "Output status: Preview complete\n"
        "Output file path: Not produced\n"
        "Next action: Start download in Forge"
    )


@dataclass(frozen=True)
class _ExistingOutputReuse:
    metadata: dict[str, Any]
    outcome: DownloadOutcome


@dataclass(frozen=True)
class _CommittedMedia:
    metadata: dict[str, Any]
    primary_output: Path
    success_count: int


@dataclass(frozen=True)
class _ExpandedDownloadSource:
    """The playlist identity and item inputs bound by source expansion."""

    playlist_info: dict[str, Any]
    entries: list[dict[str, Any]]
    session_cookies: tuple[Any, ...] = ()
    cookie_source_loaded: bool = False


@dataclass(frozen=True)
class _DownloadItemContext:
    entry: dict[str, Any]
    index: int
    total: int
    video_url: str
    label: str


@dataclass(frozen=True)
class _AnalyzedDownloadItem:
    preflight_info: dict[str, Any]
    display_info: dict[str, Any]
    plan: ExportPlan | AudioExportPlan
    session_cookies: tuple[Any, ...]
    cookie_source_loaded: bool


@dataclass(frozen=True)
class _DownloadedStagingItem:
    metadata: dict[str, Any]
    session_cookies: tuple[Any, ...]
    ffmpeg: str


@dataclass(frozen=True)
class _PreparedStagingItem:
    metadata: dict[str, Any]
    staged_media: list[tuple[dict[str, Any], Path]]
    expected_extension: str
    ffmpeg: str
    custom_cover_for_cache: Path | None


class _DownloadControlKind(Enum):
    CANCEL_RUN = "cancel_run"
    SKIP_SOURCE = "skip_source"
    SKIP_ITEM = "skip_item"


class _DownloadControlRequestError(RuntimeError):
    """A user-owned worker control request, distinct from provider error text."""

    def __init__(
        self,
        kind: _DownloadControlKind,
        *,
        result: _DownloadItemResult | None = None,
    ) -> None:
        self.kind = kind
        self.result = result
        message = {
            _DownloadControlKind.CANCEL_RUN: "Download cancelled by user",
            _DownloadControlKind.SKIP_SOURCE: "URL skipped by user",
            _DownloadControlKind.SKIP_ITEM: "Video skipped by user",
        }[kind]
        super().__init__(message)


@dataclass(frozen=True)
class _DownloadSourceContext:
    ytdlp_module: Any
    provider_network: ProviderNetworkCoordinator
    playlist_info: dict[str, Any]
    max_height: int


@dataclass(frozen=True)
class _DownloadItemResult:
    """The source-owned state that may advance after one playlist item."""

    outcome: DownloadOutcome
    session_cookies: tuple[Any, ...] = ()
    cookie_source_loaded: bool = False
    output_dirs: tuple[Path, ...] = ()
    analysis: _AnalyzedDownloadItem | None = None
    metadata: dict[str, Any] | None = None
    plan: ExportPlan | AudioExportPlan | None = None
    stop_source: bool = False


@dataclass(frozen=True)
class _DownloadBatchResult:
    outcome: DownloadOutcome
    failures: tuple[tuple[str, str], ...] = ()
    control_kind: _DownloadControlKind | None = None


class _DownloadItemExecutionError(RuntimeError):
    """Carry the latest frozen item result with a fatal provider error."""

    def __init__(
        self,
        error: Exception,
        result: _DownloadItemResult,
    ) -> None:
        self.error = error
        self.result = result
        super().__init__(str(error))


def _committed_download_outcome(result: _DownloadItemResult) -> DownloadOutcome:
    """Carry only durable child effects across a source-level abort."""
    return DownloadOutcome(
        success_count=result.outcome.success_count,
        sidecar_failure_count=result.outcome.sidecar_failure_count,
    )


def _download_source_failure_context(
    error: Exception,
    fallback_result: _DownloadItemResult,
) -> tuple[_DownloadItemResult, Exception]:
    if isinstance(error, _DownloadItemExecutionError):
        return error.result, error.error
    return fallback_result, error


def _download_batch_terminal_event(
    result: _DownloadBatchResult,
    url_count: int,
) -> UiEvent:
    """Resolve one batch terminal without acquiring terminal-event authority."""
    outcome = result.outcome
    if result.control_kind is _DownloadControlKind.CANCEL_RUN:
        if outcome.success_count:
            return (
                "partial",
                (
                    f"Batch cancelled — {outcome.success_count} valid output(s) completed before cancellation. "
                    "No incomplete output was committed."
                ),
            )
        return (
            "stopped",
            "Batch cancelled. No incomplete output was committed.",
        )
    if result.control_kind is not None:
        return ("stopped", "Batch stopped without producing an output.")
    if outcome.success_count == 0:
        if outcome.failure_count:
            raise RuntimeError(
                f"Batch produced no valid output — {outcome.failure_count} item(s) failed. "
                f"Failure report: {BATCH_FAILURE_REPORT_PATH}"
            )
        return ("stopped", "Batch stopped without producing an output.")
    if outcome.failure_count or outcome.skipped_count or outcome.sidecar_failure_count:
        return (
            "partial",
            f"Batch completed with issues — {outcome.success_count} valid output(s), "
            f"{outcome.failure_count} failed, {outcome.skipped_count} skipped, "
            f"{outcome.sidecar_failure_count} optional sidecar failure(s). "
            "Keep the valid files. Review Technical details for each issue and its next step."
            + (
                f" Failure report: {BATCH_FAILURE_REPORT_PATH}"
                if result.failures
                else ""
            ),
        )
    return (
        "done",
        f"Batch complete — {outcome.success_count} valid output(s) from {url_count} URL(s).",
    )


def _download_source_control_terminal_event(
    job: DownloadJob,
    result: _DownloadItemResult,
    control_kind: _DownloadControlKind,
) -> UiEvent:
    """Resolve a source control terminal without emitting it."""
    if control_kind is _DownloadControlKind.CANCEL_RUN:
        if result.outcome.success_count:
            return (
                "partial",
                (
                    f"{job.output_type.value} cancelled — "
                    f"{result.outcome.success_count} valid output(s) completed before cancellation. "
                    "No incomplete output was committed."
                ),
            )
        return (
            "stopped",
            "Download cancelled. No incomplete output was committed.",
        )
    if control_kind is _DownloadControlKind.SKIP_SOURCE:
        return ("stopped", "URL skipped. No incomplete output was committed.")
    return ("stopped", "Video skipped. No incomplete output was committed.")


def _download_entry_url(entry: dict[str, Any], fallback_url: str) -> str:
    url = str(entry.get("webpage_url") or entry.get("url") or "").strip()
    if url.startswith(("http://", "https://")):
        return url
    video_id = str(entry.get("id") or url).strip()
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return fallback_url


def _global_download_progress(
    video_index: int,
    total_videos: int,
    stage_start: float,
    stage_weight: float,
    stage_fraction: float = 0.0,
) -> float:
    total_videos = max(total_videos, 1)
    stage_fraction = max(0.0, min(1.0, stage_fraction))
    video_fraction = (stage_start + stage_weight * stage_fraction) / total_videos
    return max(
        0.0,
        min(
            100.0,
            ((video_index - 1) / total_videos + video_fraction) * 100.0,
        ),
    )


def _normalize_download_source_result(
    extracted_info: dict[str, Any] | None,
    source_url: str,
    *,
    single_video_only: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normalize yt-dlp's video/playlist shapes without assigning false playlist identity."""
    playlist_info = extracted_info or {"webpage_url": source_url}
    raw_entries = playlist_info.get("entries")
    extracted_playlist = raw_entries is not None
    entries = [entry for entry in (raw_entries or []) if isinstance(entry, dict)]
    if not entries:
        entries = [
            {
                "webpage_url": source_url,
                "id": playlist_info.get("id"),
                "title": playlist_info.get("title"),
            }
        ]
    if not extracted_playlist:
        # A normal video extraction is not a one-item playlist. Do not use the
        # video's own title/id as playlist authority.
        playlist_info = playlist_context_from_extraction(playlist_info, source_url)
    if single_video_only:
        requested_video_id = youtube_url_video_id(source_url)
        selected_entry = next(
            (
                entry
                for entry in entries
                if str(entry.get("id") or "").strip() == requested_video_id
            ),
            None,
        )
        entries = [
            selected_entry
            or {
                "webpage_url": clean_single_video_url(source_url),
                "id": requested_video_id,
            }
        ]
    return playlist_info, entries


def format_ytdlp_user_error(error: Any) -> str:
    from .download_error_presentation import download_error_message

    return download_error_message(error)


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


def apply_youtube_runtime_options(
    opts: dict[str, Any], *, deno_path: str | None
) -> dict[str, Any]:
    """Enable yt-dlp's supported YouTube challenge solver without pinning clients.

    YouTube changes which player clients can expose downloadable adaptive
    formats.  A previously useful hard-coded ``web_safari``/``android`` list
    eventually caused some 1080p videos to expose only the progressive 360p
    format.  Leave ``player_client`` unset so the pinned yt-dlp release can use
    its maintained defaults and contextual authenticated/age-restricted
    fallbacks.  Deno remains explicit because JavaScript challenge solving is
    required for reliable format discovery.  The matching EJS scripts are
    installed and packaged by the pinned ``yt-dlp[default]`` dependency rather
    than fetched as executable code while the app is running.
    """
    if deno_path:
        opts["js_runtimes"] = {"deno": {"path": deno_path}}
    return opts


class QueueLogger:
    def __init__(
        self,
        events: UiEventSink | None = None,
        *,
        diagnostic_prefix: str = "yt-dlp",
    ) -> None:
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


def _build_playlist_detection_options(
    job: DownloadJob,
    *,
    deno_path: str | None,
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": False,
        "extract_flat": "in_playlist",
        "logger": QueueLogger(None, diagnostic_prefix="playlist yt-dlp"),
        "socket_timeout": 30,
        "ignore_no_formats_error": True,
    }
    apply_ytdlp_network_retry_policy(options, source_analysis=True)
    apply_ytdlp_cookie_options(
        options,
        use_cookies=job.use_cookies,
        cookie_file=job.cookie_file,
        cookie_browser=job.cookie_browser,
    )
    apply_youtube_runtime_options(options, deno_path=deno_path)
    return options


def sanitized_caption_summary(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    language = value.get("language")
    kind = value.get("source_kind")
    if (
        not isinstance(language, str)
        or not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", language)
        or kind not in ("manual", "automatic")
        or value.get("role") != "original"
    ):
        return None
    return {"language": language, "source_kind": kind, "role": "original"}


def require_original_caption_stream(probe: dict[str, Any]) -> None:
    """Do not commit a claimed caption download whose subtitle stream is missing."""
    if not any(
        isinstance(stream, dict) and stream.get("codec_type") == "subtitle"
        for stream in probe.get("streams", [])
    ):
        raise RuntimeError(
            "Original-language captions could not be embedded or preserved; no output was committed. Retry the download."
        )


def original_caption_selection(info: dict[str, Any]) -> tuple[str, str] | None:
    """Select one evidenced original language, never a guessed translation."""
    automatic = info.get("automatic_captions") or {}
    manual = info.get("subtitles") or {}
    if not isinstance(automatic, dict) or not isinstance(manual, dict):
        return None
    original_languages = {
        key.removesuffix("-orig")
        for key, tracks in automatic.items()
        if isinstance(key, str) and key.endswith("-orig") and tracks
    }
    for audio in info.get("formats") or []:
        if (
            isinstance(audio, dict)
            and audio.get("language_preference") == 10
            and isinstance(audio.get("language"), str)
            and audio.get("acodec") not in (None, "none")
        ):
            original_languages.add(audio["language"])
    if len(original_languages) != 1:
        return None
    language = next(iter(original_languages))
    if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", language):
        return None
    if manual.get(language):
        return language, "manual"
    original_key = f"{language}-orig"
    if automatic.get(original_key):
        return original_key, "automatic"
    return None


def apply_original_caption_options(
    options: dict[str, Any],
    info: dict[str, Any],
    translation_language: str | None = None,
) -> dict[str, Any]:
    """Acquire original captions and at most one explicitly selected translation."""
    target = validate_translation_language(translation_language)
    selection = original_caption_selection(info)
    if selection is None:
        if target:
            raise RuntimeError(
                "Selected translated subtitles are unavailable or their source language "
                "could not be verified; no output was committed. "
                "Choose another language or turn translated subtitles Off."
            )
        return info
    key, kind = selection
    language = key.removesuffix("-orig")
    prepared = dict(info)
    prepared["subtitles"] = {}
    prepared["automatic_captions"] = {}
    summaries = []

    def add_track(
        code: str, source: str, tracks: list[Any], source_kind: str, role: str
    ) -> None:
        label = "Original captions" if role == "original" else "Translated subtitles"
        prepared[source][code] = [
            {**track, "name": f"{label} ({source_kind.replace('_', ' ')})"}
            for track in tracks
            if isinstance(track, dict)
        ]
        summaries.append({"language": code, "source_kind": source_kind, "role": role})

    source = "subtitles" if kind == "manual" else "automatic_captions"
    add_track(language, source, info[source][key], kind, "original")
    if target and target != language:
        uploaded = (info.get("subtitles") or {}).get(target)
        if uploaded:
            add_track(target, "subtitles", uploaded, "manual", "translated")
        else:
            automatic = info.get("automatic_captions") or {}
            for translated_key in (f"{target}-{language}", target):
                tracks = automatic.get(translated_key) or []
                matching = []
                for track in tracks:
                    if not isinstance(track, dict):
                        continue
                    query = urllib.parse.parse_qs(
                        urllib.parse.urlparse(str(track.get("url") or "")).query
                    )
                    if query.get("tlang") == [target] and query.get("lang") == [
                        language
                    ]:
                        matching.append(track)
                if matching:
                    add_track(
                        target,
                        "automatic_captions",
                        matching,
                        "automatic_translation",
                        "translated",
                    )
                    break
    if (
        target
        and target != language
        and not any(track["role"] == "translated" for track in summaries)
    ):
        raise RuntimeError(
            "Selected translated subtitles are unavailable; no output was committed. "
            "Choose another language or turn translated subtitles Off."
        )
    prepared["vodforge_caption_summary"] = summaries[0]
    prepared["vodforge_subtitle_tracks"] = summaries
    options.update(
        writesubtitles=bool(prepared["subtitles"]),
        writeautomaticsub=bool(prepared["automatic_captions"]),
        subtitleslangs=[re.escape(track["language"]) for track in summaries],
        subtitlesformat="vtt/srt/best",
    )
    options["postprocessors"].append({"key": "FFmpegEmbedSubtitle"})
    return prepared


def sanitized_subtitle_tracks(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > 2:
        return []
    result = []
    for track in value:
        if not isinstance(track, dict):
            return []
        language, kind, role = (
            track.get("language"),
            track.get("source_kind"),
            track.get("role"),
        )
        if (
            not isinstance(language, str)
            or not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", language)
            or kind not in ("manual", "automatic", "automatic_translation")
            or role not in ("original", "translated")
        ):
            return []
        result.append({"language": language, "source_kind": kind, "role": role})
    return result


def require_selected_subtitle_streams(probe: dict[str, Any], expected: Any) -> None:
    require_original_caption_stream(probe)
    tracks = sanitized_subtitle_tracks(expected)
    languages = [
        stream.get("tags", {}).get("language")
        for stream in probe.get("streams", [])
        if stream.get("codec_type") == "subtitle"
    ]
    for track in tracks:
        language = track["language"]
        iso = ISO639Utils.short2long(language) or language
        if iso not in languages and language not in languages:
            raise RuntimeError(
                "Selected subtitle language could not be preserved; no output was committed. Retry the download."
            )
    if tracks and len(languages) != len(tracks):
        raise RuntimeError(
            "Selected subtitle tracks could not be verified; no output was committed."
        )


def _build_item_preflight_options(
    job: DownloadJob,
    *,
    cookie_source_loaded: bool,
    ffmpeg: str | None,
    deno_path: str | None,
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
        "extract_flat": False,
        "logger": QueueLogger(None, diagnostic_prefix="preflight yt-dlp"),
        "socket_timeout": 30,
        "ignore_no_formats_error": True,
    }
    if job.output_type == OutputType.MP4 and job.translated_subtitle_language:
        # Discover provider translation metadata, not all-language downloads.
        options["writeautomaticsub"] = True
    apply_ytdlp_network_retry_policy(options, source_analysis=True)
    apply_ytdlp_cookie_options(
        options,
        use_cookies=job.use_cookies,
        cookie_file=job.cookie_file,
        cookie_browser=job.cookie_browser,
    )
    if cookie_source_loaded:
        options.pop("cookiefile", None)
        options.pop("cookiesfrombrowser", None)
    if ffmpeg:
        options["ffmpeg_location"] = ytdlp_ffmpeg_location(ffmpeg)
    apply_youtube_runtime_options(options, deno_path=deno_path)
    return options


def _build_download_item_plan(
    job: DownloadJob,
    preflight_info: dict[str, Any],
    *,
    max_height: int,
) -> ExportPlan | AudioExportPlan:
    job.selection_dimensions = {}
    if job.output_type == OutputType.ORIGINAL:
        return build_original_audio_plan(preflight_info)
    if job.output_type == OutputType.MP3:
        return build_mp3_export_plan(preflight_info, job.mp3_settings)
    try:
        plan = build_auto_export_plan(
            preflight_info,
            mode=job.export_mode,
            max_height=max_height,
            use_nvenc=job.use_nvenc,
        )
    except SourceSelectionError as exc:
        job.selection_dimensions = selection_observation(
            exc.selection_dimensions, scope="item"
        )
        raise
    job.selection_dimensions = selection_observation(
        plan.selection_dimensions, scope="item"
    )
    if job.export_mode == ExportMode.MANUAL_OVERRIDE:
        return apply_manual_export_settings(plan, job.manual_settings)
    return plan


def _download_item_plan_log_lines(
    job: DownloadJob,
    label: str,
    plan: ExportPlan | AudioExportPlan,
) -> list[str]:
    lines: list[str] = []
    if job.export_mode == ExportMode.MANUAL_OVERRIDE and isinstance(plan, ExportPlan):
        lines.append(
            f"{label}: Custom settings {plan.video_target_label} video + "
            f"{plan.audio_bitrate_kbps} kbps audio, {plan.audio_sample_rate} Hz, "
            f"{plan.audio_channels} channel(s), x264 preset {plan.x264_preset}."
        )
    lines.append(f"{label}: selected format {plan.format_selector}")
    if isinstance(plan, AudioExportPlan):
        lines.extend(
            (
                (
                    f"{label}: selected highest-quality audio source {plan.audio_codec} "
                    f"~{plan.source_audio_kbps:.0f} kbps."
                ),
                (
                    f"{label}: preserve original audio without re-encoding."
                    if plan.output_type == OutputType.ORIGINAL
                    else f"{label}: MP3 target {plan.audio_bitrate_kbps} kbps CBR; cover art "
                    f"{'embedded' if plan.embed_cover_art else 'not embedded'}."
                ),
            )
        )
    else:
        target_label = f"{export_mode_display_name(plan.mode)} target"
        lines.extend(
            (
                (
                    f"{label}: selected video {plan.output_height}p {plan.video_codec} "
                    f"~{plan.source_video_kbps:.0f} kbps; selected audio {plan.audio_codec} "
                    f"~{plan.source_audio_kbps:.0f} kbps."
                ),
                (
                    f"{label}: {target_label} {plan.video_target_label} video + "
                    f"{plan.audio_bitrate_kbps} kbps audio."
                ),
            )
        )
    lines.extend(f"WARNING: {label}: {warning}" for warning in plan.warnings)
    return lines


@dataclass(frozen=True)
class _RunFinishDecision:
    """Stable finished-run authority across a possible successor handoff."""

    finished_job: DownloadJob | None
    suppressed: bool
    stopped_without_item_terminal: bool
    archive_completed: bool


def _resolve_run_finish_decision(
    finished_job: DownloadJob | None,
    run_status: str,
    *,
    suppressed: bool,
) -> _RunFinishDecision:
    item_terminal_emitted = bool(
        finished_job is not None and finished_job.item_terminal_emitted
    )
    return _RunFinishDecision(
        finished_job=finished_job,
        suppressed=suppressed,
        stopped_without_item_terminal=(
            not suppressed and run_status == "Stopped" and not item_terminal_emitted
        ),
        archive_completed=(not suppressed and run_status in {"Completed", "Partial"}),
    )


class DownloadWorkerCore:
    """UI-independent serialized provider, staging, and export owner."""

    events: queue.Queue[Any]
    cancel_requested: bool
    download_history: list[dict[str, Any]]
    run_recovery: RunRecoveryOwner
    product_telemetry: Any
    _active_progress_context: tuple[int, int, float, float] | None
    video_output_dirs_by_id: dict[str, Path]

    def _provider_network_coordinator(self) -> ProviderNetworkCoordinator:
        coordinator = self.__dict__.get("_provider_network")
        if coordinator is None:
            coordinator = ProviderNetworkCoordinator()
            self._provider_network = coordinator
        return coordinator

    def _coordinate_download_batch(
        self,
        job: DownloadJob,
        urls: list[str],
    ) -> _DownloadBatchResult:
        """Run child sources without acquiring the batch terminal event."""
        outcome = job.batch_outcome
        failures: list[tuple[str, str]] = []
        for index, url in enumerate(urls, start=1):
            if index <= job.completed_batch_items:
                continue
            if self.cancel_requested:
                return _DownloadBatchResult(
                    outcome=outcome,
                    failures=tuple(failures),
                    control_kind=_DownloadControlKind.CANCEL_RUN,
                )
            item_url, forced_single_video = prepare_batch_item_url(url)
            item_single_video_only = job.single_video_only or forced_single_video
            child = replace(
                job,
                url=item_url,
                urls=[item_url],
                single_video_only=item_single_video_only,
            )
            self.events.put(
                (
                    "batch_item",
                    {
                        "job": job,
                        "child": child,
                        "index": index,
                        "total": len(urls),
                        "finished": False,
                    },
                )
            )
            self.events.put(("status", f"Batch URL {index} of {len(urls)} — starting"))
            self._emit_job_log(job, f"Batch URL {index} of {len(urls)}: {item_url}")
            write_diagnostic(
                f"batch URL {index} of {len(urls)} start: {item_url} single_video_only={item_single_video_only}"
            )
            try:
                item_outcome = self._download_worker_single(
                    child,
                    emit_done=False,
                    re_raise=True,
                )
                outcome = outcome.combined_with(item_outcome)
            except _DownloadControlRequestError as control_request:
                if control_request.result is not None:
                    outcome = outcome.combined_with(
                        _committed_download_outcome(control_request.result)
                    )
                if control_request.kind is _DownloadControlKind.CANCEL_RUN:
                    return _DownloadBatchResult(
                        outcome=outcome,
                        failures=tuple(failures),
                        control_kind=control_request.kind,
                    )
                self.skip_video_requested = False
                if control_request.kind is _DownloadControlKind.SKIP_SOURCE:
                    self.skip_url_requested = False
                write_diagnostic(f"batch URL {index} skipped by user: {item_url}")
                self._emit_job_log(
                    job, f"Batch URL {index} skipped by user; continuing."
                )
                outcome = outcome.combined_with(DownloadOutcome(skipped_count=1))
            except Exception as exc:  # noqa: BLE001 - each provider child failure is isolated in the batch result
                provider_error = exc
                if isinstance(exc, _DownloadItemExecutionError):
                    outcome = outcome.combined_with(
                        _committed_download_outcome(exc.result)
                    )
                    provider_error = exc.error
                issue = format_ytdlp_user_error(provider_error)
                if job.failure_diagnostic is None:
                    job.failure_diagnostic = capture_failure(
                        provider_error, stage="batch"
                    )
                failures.append((item_url, issue))
                outcome = outcome.combined_with(DownloadOutcome(failure_count=1))
                append_batch_failure_report(
                    BATCH_FAILURE_REPORT_PATH, item_url, provider_error
                )
                write_diagnostic(
                    f"batch URL {index} of {len(urls)} failed but batch will continue: "
                    f"{type(provider_error).__name__}: {provider_error}"
                )
                self._emit_job_log(
                    job,
                    f"WARNING: Batch URL {index} failed; continuing. Failure report: {BATCH_FAILURE_REPORT_PATH}",
                )
            self.events.put(
                (
                    "batch_item",
                    {
                        "job": job,
                        "child": child,
                        "index": index,
                        "total": len(urls),
                        "finished": True,
                        "outcome": outcome,
                    },
                )
            )
        return _DownloadBatchResult(outcome=outcome, failures=tuple(failures))

    def _download_worker(self, job: DownloadJob) -> None:
        urls = [url.strip() for url in (job.urls or [job.url]) if url.strip()]
        if len(urls) <= 1:
            single_url = urls[0] if urls else job.url
            single_video_only = job.single_video_only
            if job.batch_mode:
                single_url, forced_single_video = prepare_batch_item_url(single_url)
                single_video_only = single_video_only or forced_single_video
            # Keep the active authority object itself through the worker. A
            # dataclass copy would strand terminal flags and resolved metadata
            # on a private worker object that Forge never observes.
            job.url = single_url
            job.urls = [single_url]
            job.single_video_only = single_video_only
            self._download_worker_single(job)
            return
        try:
            if job.completed_batch_items == 0:
                reset_batch_failure_report()
            batch_result = self._coordinate_download_batch(job, urls)
            if batch_result.control_kind is not None:
                self._active_progress_context = None
                write_diagnostic(
                    "batch download worker control request: "
                    f"{batch_result.control_kind.value}"
                )
            self.events.put(_download_batch_terminal_event(batch_result, len(urls)))
        except Exception as exc:  # noqa: BLE001 - worker converts terminal failures into UI outcomes
            job.failure_diagnostic = capture_failure(exc, stage="batch")
            self._active_progress_context = None
            write_diagnostic(
                f"batch download worker error: {type(exc).__name__}: {exc}"
            )
            self.events.put(("error", format_ytdlp_user_error(exc)))

    def _try_reuse_existing_output(
        self,
        job: DownloadJob,
        info: dict[str, Any],
        plan: ExportPlan | AudioExportPlan,
        *,
        label: str,
        all_output_dirs: list[Path],
        control_check: Callable[[], None],
    ) -> _ExistingOutputReuse | None:
        ffprobe = self._find_ffprobe()
        if not ffprobe:
            DownloadWorkerCore._observe_download_operation(
                self,
                job,
                "stage",
                stage="reuse",
                dimensions={
                    "reuse_result": "unavailable",
                    "reuse_rejection": "probe_unavailable",
                },
            )
            return None
        history = self.__dict__.get("download_history", ())
        legacy_paths = owned_output_paths(
            job, info, history if isinstance(history, (list, tuple)) else ()
        )
        rejection: tuple[str, FailureDiagnostic | None] = (
            "no_eligible_candidate",
            None,
        )

        def rejected(reason: str, detail: FailureDiagnostic | None) -> None:
            nonlocal rejection
            # Keep only the last rejection; candidate count can be large.
            rejection = (reason, detail)

        existing_output = find_valid_existing_output(
            job.output_dir,
            info,
            job.output_type,
            ffprobe,
            plan=plan,
            embed_metadata=(
                job.mp3_settings.embed_metadata
                if job.output_type == OutputType.MP3
                else job.embed_metadata
            ),
            embed_cover_art=(
                job.mp3_settings.embed_cover_art
                if job.output_type == OutputType.MP3
                else job.embed_thumbnail
            ),
            custom_cover_art=(
                job.output_type == OutputType.MP3
                and job.mp3_settings.custom_cover_art_path is not None
            ),
            expected_tags=job.tags,
            expected_duration_seconds=_float_or_none(info.get("duration")),
            control_check=control_check,
            owned_legacy_paths=legacy_paths,
            on_rejection=rejected,
        )
        if existing_output is None:
            DownloadWorkerCore._observe_download_operation(
                self,
                job,
                "stage"
                if rejection[0] == "no_eligible_candidate"
                else "candidate_rejected",
                stage="reuse",
                dimensions={"reuse_result": "miss", "reuse_rejection": rejection[0]},
                failure_detail=rejection[1],
            )
            return None

        existing_path, existing_probe = existing_output
        namespace = "unknown"
        if metadata_output_variant(info):
            try:
                variant_dir, _ = resolved_video_output_target(
                    job.output_dir, info, existing_path.suffix
                )
                if existing_path.parent == variant_dir:
                    namespace = "variant"
            except ValueError:
                pass  # A legacy lookup can succeed when a new path is too long.
        if namespace == "unknown" and existing_path in legacy_paths:
            namespace = "owned_legacy"
        DownloadWorkerCore._observe_download_operation(
            self,
            job,
            "reused",
            stage="reuse",
            dimensions={
                "reused_count": "1",
                "committed_count": "0",
                "storage_namespace": namespace,
            },
            output_path=existing_path,
            output_probe=existing_probe,
            output_info=info,
        )
        remember_video_output_dir(info, existing_path.parent)
        reused_info = build_encoding_summary_metadata(
            info,
            plan,
            output_path=existing_path,
            ffprobe_data=existing_probe,
            validation_status="Validated existing output",
        )
        self.events.put(job_info_event("job_metadata", job, reused_info))
        self.events.put(
            history_record_event(
                job,
                reused_info,
                str(existing_path.parent),
            )
        )
        all_output_dirs.append(existing_path.parent)
        self.events.put(("download_folders", sorted(set(all_output_dirs))))
        reuse_outcome = DownloadOutcome(success_count=1)
        self._emit_job_log(
            job,
            f"{label}: Already downloaded and valid — reused existing file. "
            f"Path: {existing_path}",
        )
        try:
            cached_thumbnail = save_cached_thumbnail_image(
                reused_info,
                source_url=job.url,
                on_result=DownloadWorkerCore._download_sidecar_observer(
                    self, job, "library_artwork", reused=True
                ),
            )
            if cached_thumbnail is not None:
                self._emit_job_log(
                    job, f"{label}: refreshed private Library artwork cache"
                )
        except Exception as exc:  # noqa: BLE001 - optional Library artwork cannot invalidate media
            DownloadWorkerCore._observe_download_sidecar_failure(
                self, job, exc, kind="library_artwork", reused=True
            )
            write_diagnostic(technical_download_error(exc))
            reuse_outcome = reuse_outcome.combined_with(
                DownloadOutcome(sidecar_failure_count=1)
            )
            self._emit_job_log(
                job,
                f"WARNING: {label}: existing media is valid, but Library artwork could not be refreshed.",
            )
        if job.write_info_json:
            try:
                write_compact_video_metadata(
                    existing_path.parent,
                    reused_info,
                    job.tags,
                    output_root=job.output_dir,
                    on_result=DownloadWorkerCore._download_sidecar_observer(
                        self, job, "metadata", reused=True
                    ),
                )
            except Exception as exc:  # noqa: BLE001 - optional metadata cannot invalidate media
                DownloadWorkerCore._observe_download_sidecar_failure(
                    self, job, exc, kind="metadata", reused=True
                )
                write_diagnostic(technical_download_error(exc))
                reuse_outcome = reuse_outcome.combined_with(
                    DownloadOutcome(sidecar_failure_count=1)
                )
                self._emit_job_log(
                    job,
                    f"WARNING: {label}: existing media is valid, but compact metadata could not be refreshed.",
                )
        else:
            observer = DownloadWorkerCore._download_sidecar_observer(
                self, job, "metadata", reused=True
            )
            if observer is not None:
                observer("not_requested")
        if job.write_thumbnail:
            try:
                save_thumbnail_image(
                    existing_path.parent,
                    reused_info,
                    source_url=job.url,
                    output_root=job.output_dir,
                    on_result=DownloadWorkerCore._download_sidecar_observer(
                        self, job, "thumbnail", reused=True
                    ),
                )
            except Exception as exc:  # noqa: BLE001 - optional thumbnail cannot invalidate media
                DownloadWorkerCore._observe_download_sidecar_failure(
                    self, job, exc, kind="thumbnail", reused=True
                )
                write_diagnostic(technical_download_error(exc))
                reuse_outcome = reuse_outcome.combined_with(
                    DownloadOutcome(sidecar_failure_count=1)
                )
                self._emit_job_log(
                    job,
                    f"WARNING: {label}: existing media is valid, but its separate thumbnail could not be refreshed.",
                )
        else:
            observer = DownloadWorkerCore._download_sidecar_observer(
                self, job, "thumbnail", reused=True
            )
            if observer is not None:
                observer("not_requested")
        return _ExistingOutputReuse(
            metadata=reused_info,
            outcome=reuse_outcome,
        )

    def _transcode_and_validate_staged_media(
        self,
        job: DownloadJob,
        info: dict[str, Any],
        plan: ExportPlan | AudioExportPlan,
        staged_media: list[tuple[dict[str, Any], Path]],
        ffmpeg: str,
        *,
        label: str,
        progress_callback: Callable[[float], None],
        control_check: Callable[[], None],
    ) -> list[tuple[dict[str, Any], Path, dict[str, Any]]]:
        ffprobe = self._find_ffprobe() or _ffprobe_for_ffmpeg(ffmpeg)
        if not ffprobe:
            raise RuntimeError(
                f"{label}: FFprobe is required to validate the final output."
            )

        if isinstance(plan, ExportPlan):
            total_mp4 = len(staged_media)
            for encode_index, (staged_info, staged_mp4) in enumerate(
                staged_media,
                start=1,
            ):
                control_check()
                self.events.put(("status", f"{label} — transcoding"))
                encoder_label = (
                    "NVIDIA NVENC GPU"
                    if job.use_nvenc
                    and (plan.video_crf is None or plan.nvenc_cq is not None)
                    else "CPU libx264"
                )
                self._emit_job_log(
                    job,
                    f"{label}: FFmpeg command started ({encode_index}/{total_mp4}) using {encoder_label}",
                )
                write_diagnostic(
                    f"{label} ffmpeg command: "
                    f"{build_vod_ffmpeg_command(ffmpeg, staged_mp4, transcode_temp_paths(staged_mp4)[0], video_bitrate_kbps=plan.video_bitrate_kbps, audio_bitrate_kbps=plan.audio_bitrate_kbps, audio_sample_rate=plan.audio_sample_rate, audio_channels=plan.audio_channels, audio_codec=plan.output_audio_codec, x264_preset=plan.x264_preset, use_nvenc=job.use_nvenc, preserve_attached_picture=job.embed_thumbnail, preserve_metadata=job.embed_metadata, video_crf=plan.video_crf, nvenc_cq=plan.nvenc_cq, keyframe_seconds=plan.keyframe_seconds, fps=plan.fps, constant_frame_rate=plan.constant_frame_rate, video_maxrate_kbps=plan.video_maxrate_kbps)}"
                )
                progress_callback((encode_index - 1) / total_mp4)
                transcode_started = time.monotonic()
                transcode_to_vod_streaming_settings(
                    staged_mp4,
                    ffmpeg,
                    plan=plan,
                    duration_seconds=_float_or_none(
                        staged_info.get("duration") or info.get("duration")
                    ),
                    progress_callback=lambda fraction, encode_index=encode_index, total_mp4=total_mp4: (
                        progress_callback(((encode_index - 1) + fraction) / total_mp4)
                    ),
                    use_nvenc=job.use_nvenc,
                    preserve_attached_picture=job.embed_thumbnail,
                    preserve_metadata=job.embed_metadata,
                    preserve_caption_metadata=len(
                        sanitized_subtitle_tracks(info.get("vodforge_subtitle_tracks"))
                    ),
                    control_check=control_check,
                )
                write_diagnostic(
                    f"{label} transcode elapsed_seconds={time.monotonic() - transcode_started:.3f}"
                )
                self._emit_job_log(job, f"{label}: transcoded staged VODForge output")
        elif job.output_type == OutputType.ORIGINAL:
            self.events.put(("status", f"{label} — original audio extracted"))
        else:
            self.events.put(("status", f"{label} — MP3 encoded"))

        DownloadWorkerCore._observe_download_operation(
            self, job, "stage", stage="validation"
        )
        self.events.put(("status", f"{label} — validating output"))
        validation_started = time.monotonic()
        validated_staged: list[tuple[dict[str, Any], Path, dict[str, Any]]] = []
        embed_metadata = (
            plan.embed_metadata
            if isinstance(plan, AudioExportPlan)
            else job.embed_metadata
        )
        embed_cover_art = (
            plan.embed_cover_art
            if isinstance(plan, AudioExportPlan)
            else job.embed_thumbnail
        )
        for staged_info, staged_path in staged_media:
            control_check()
            probe_data = validate_output_artifact(
                staged_path,
                job.output_type,
                ffprobe,
                expected_duration_seconds=_float_or_none(
                    staged_info.get("duration") or info.get("duration")
                ),
                require_audio=True,
                plan=plan,
                embed_metadata=embed_metadata,
                embed_cover_art=embed_cover_art,
                expected_tags=job.tags if embed_metadata else None,
                control_check=control_check,
            )
            if info.get("vodforge_original_caption_expected"):
                require_selected_subtitle_streams(
                    probe_data, info.get("vodforge_subtitle_tracks")
                )
            validated_staged.append((staged_info, staged_path, probe_data))
        control_check()
        write_diagnostic(
            f"{label} artifact validation elapsed_seconds={time.monotonic() - validation_started:.3f}"
        )
        return validated_staged

    def _commit_validated_staged_media(
        self,
        job: DownloadJob,
        info: dict[str, Any],
        plan: ExportPlan | AudioExportPlan,
        staging_dir: Path,
        expected_extension: str,
        validated_staged: list[tuple[dict[str, Any], Path, dict[str, Any]]],
        *,
        label: str,
        all_output_dirs: list[Path],
        progress_callback: Callable[[float], None],
        control_check: Callable[[], None],
    ) -> _CommittedMedia:
        commit_started = time.monotonic()
        packaged_paths = package_downloaded_media_from_staging(
            staging_dir,
            job.output_dir,
            info,
            expected_extension=expected_extension,
            staged_media=[
                (staged_info, staged_path)
                for staged_info, staged_path, _probe in validated_staged
            ],
            control_check=control_check,
        )
        output_paths = [
            path for path in packaged_paths if path.suffix.lower() == expected_extension
        ]
        primary_output = output_paths[0] if output_paths else None
        if primary_output is None:
            raise RuntimeError(
                f"{label}: validated output could not be committed to the destination."
            )
        DownloadWorkerCore._observe_download_operation(
            self,
            job,
            "committed",
            stage="commit",
            dimensions={
                "committed_count": str(min(len(output_paths), 10000)),
                "storage_namespace": "variant",
            },
            output_path=primary_output,
            output_probe=validated_staged[0][2] if len(validated_staged) == 1 else None,
            output_info=info,
            artifact_count=len(output_paths),
        )
        write_diagnostic(
            f"{label} atomic output commit elapsed_seconds={time.monotonic() - commit_started:.3f}"
        )
        output_dirs = sorted({path.parent for path in packaged_paths})
        all_output_dirs.extend(output_dirs)
        self.events.put(("download_folders", sorted(set(all_output_dirs))))
        for packaged_path in packaged_paths:
            self._emit_job_log(job, f"{label}: packaged media file {packaged_path}")
        ffprobe_data = validated_staged[0][2]
        if isinstance(plan, AudioExportPlan):
            if job.output_type == OutputType.ORIGINAL:
                self._emit_job_log(
                    job,
                    f"{label}: saved original audio without re-encoding {primary_output.name}",
                )
            else:
                self._emit_job_log(
                    job,
                    f"{label}: created {plan.audio_bitrate_kbps} kbps MP3 output {primary_output.name}",
                )
        progress_callback(1.0)
        self._emit_job_log(
            job,
            f"{label}: validated {primary_output.name} before atomic commit",
        )
        committed_info = build_encoding_summary_metadata(
            info,
            plan,
            output_path=primary_output,
            ffprobe_data=ffprobe_data,
            validation_status="Validated",
        )
        telemetry = self.__dict__.get("product_telemetry")
        if telemetry is not None:
            telemetry.record(
                "media_exported",
                dedupe_key=job.run_id + ":" + str(primary_output),
                attempt_key=job.run_id,
                retry_key=job.retry_of_run_id,
                run_kind="youtube",
                output_type=product_output_kind(job.output_type.value),
                dimensions=committed_export_dimensions(
                    job,
                    plan,
                    ffprobe_data,
                    source_height=_float_or_none(info.get("height")),
                ),
            )
        self.events.put(job_info_event("job_metadata", job, committed_info))
        return _CommittedMedia(
            metadata=committed_info,
            primary_output=primary_output,
            success_count=len(output_paths),
        )

    def _record_committed_media_and_write_sidecars(
        self,
        job: DownloadJob,
        info: dict[str, Any],
        primary_output: Path,
        *,
        label: str,
        custom_cover_for_cache: Path | None,
    ) -> DownloadOutcome:
        outcome = DownloadOutcome()
        try:
            cached_thumbnail = (
                save_custom_cached_thumbnail_image(
                    info,
                    custom_cover_for_cache,
                    on_result=DownloadWorkerCore._download_sidecar_observer(
                        self, job, "library_artwork", reused=False
                    ),
                )
                if job.output_type == OutputType.MP3
                and custom_cover_for_cache is not None
                else save_cached_thumbnail_image(
                    info,
                    source_url=job.url,
                    on_result=DownloadWorkerCore._download_sidecar_observer(
                        self, job, "library_artwork", reused=False
                    ),
                )
            )
            if cached_thumbnail is not None:
                artwork_source = (
                    "custom cover"
                    if custom_cover_for_cache is not None
                    else "YouTube thumbnail"
                )
                self._emit_job_log(
                    job,
                    f"{label}: cached {artwork_source} privately for Forge and Library",
                )
        except Exception as exc:  # noqa: BLE001 - optional Library artwork cannot invalidate media
            DownloadWorkerCore._observe_download_sidecar_failure(
                self, job, exc, kind="library_artwork", reused=False
            )
            outcome = outcome.combined_with(DownloadOutcome(sidecar_failure_count=1))
            write_diagnostic(
                f"{label} private thumbnail cache failed: {type(exc).__name__}: {exc}"
            )
            self._emit_job_log(
                job,
                f"WARNING: {label}: the media is complete, but its Library artwork could not be cached.",
            )
        self.events.put(
            history_record_event(
                job,
                info,
                str(primary_output.parent),
            )
        )
        if job.write_info_json:
            try:
                metadata_path = write_compact_video_metadata(
                    resolved_video_output_dir(job.output_dir, info),
                    info,
                    job.tags,
                    output_root=job.output_dir,
                    on_result=DownloadWorkerCore._download_sidecar_observer(
                        self, job, "metadata", reused=False
                    ),
                )
                self._emit_job_log(
                    job,
                    f"{label}: saved compact video metadata {metadata_path}",
                )
            except Exception as exc:  # noqa: BLE001 - optional metadata cannot invalidate media
                DownloadWorkerCore._observe_download_sidecar_failure(
                    self, job, exc, kind="metadata", reused=False
                )
                outcome = outcome.combined_with(
                    DownloadOutcome(sidecar_failure_count=1)
                )
                write_diagnostic(
                    f"{label} compact metadata write failed: {type(exc).__name__}: {exc}"
                )
                self._emit_job_log(
                    job,
                    f"WARNING: {label}: media is valid, but compact metadata could not be saved.",
                )
        else:
            observer = DownloadWorkerCore._download_sidecar_observer(
                self, job, "metadata", reused=False
            )
            if observer is not None:
                observer("not_requested")
        if job.write_thumbnail:
            try:
                thumb_path = save_thumbnail_image(
                    resolved_video_output_dir(job.output_dir, info),
                    info,
                    source_url=job.url,
                    output_root=job.output_dir,
                    on_result=DownloadWorkerCore._download_sidecar_observer(
                        self, job, "thumbnail", reused=False
                    ),
                )
                if thumb_path:
                    self._emit_job_log(job, f"{label}: saved thumbnail {thumb_path}")
            except Exception as exc:  # noqa: BLE001 - optional thumbnail cannot invalidate media
                DownloadWorkerCore._observe_download_sidecar_failure(
                    self, job, exc, kind="thumbnail", reused=False
                )
                outcome = outcome.combined_with(
                    DownloadOutcome(sidecar_failure_count=1)
                )
                write_diagnostic(
                    f"{label} thumbnail write failed: {type(exc).__name__}: {exc}"
                )
                self._emit_job_log(
                    job,
                    f"WARNING: {label}: media is valid, but its separate thumbnail could not be saved.",
                )
        else:
            observer = DownloadWorkerCore._download_sidecar_observer(
                self, job, "thumbnail", reused=False
            )
            if observer is not None:
                observer("not_requested")
        return outcome

    def _put_download_stage_progress(
        self,
        item: _DownloadItemContext,
        stage_start: float,
        stage_weight: float,
        stage_fraction: float = 0.0,
    ) -> None:
        self.events.put(
            (
                "progress",
                _global_download_progress(
                    item.index,
                    item.total,
                    stage_start,
                    stage_weight,
                    stage_fraction,
                ),
            )
        )

    def _raise_for_download_control_requests(self) -> None:
        if self.cancel_requested:
            raise _DownloadControlRequestError(_DownloadControlKind.CANCEL_RUN)
        if self.skip_url_requested:
            raise _DownloadControlRequestError(_DownloadControlKind.SKIP_SOURCE)
        if self.skip_video_requested:
            raise _DownloadControlRequestError(_DownloadControlKind.SKIP_ITEM)

    def _playlist_blocking_step_cancelled(self) -> bool:
        if self.cancel_requested:
            raise _DownloadControlRequestError(_DownloadControlKind.CANCEL_RUN)
        if self.skip_url_requested:
            raise _DownloadControlRequestError(_DownloadControlKind.SKIP_SOURCE)
        return False

    def _video_blocking_step_cancelled(self) -> bool:
        if self.cancel_requested:
            raise _DownloadControlRequestError(_DownloadControlKind.CANCEL_RUN)
        if self.skip_url_requested:
            raise _DownloadControlRequestError(_DownloadControlKind.SKIP_SOURCE)
        if self.skip_video_requested:
            raise _DownloadControlRequestError(_DownloadControlKind.SKIP_ITEM)
        return False

    def _emit_download_item_terminal(
        self,
        job: DownloadJob,
        status: str,
        message: str,
        info: dict[str, Any] | None,
        plan: ExportPlan | AudioExportPlan | None,
        video_url: str,
        *,
        playlist_continues: bool = False,
        failure_details: str = "",
    ) -> None:
        if not isinstance(info, dict):
            return
        terminal_run_id = uuid.uuid4().hex
        terminal_info = build_terminal_item_metadata(
            info,
            plan,
            status,
            message,
            terminal_run_id,
        )
        retry_url = retry_url_for_item(terminal_info, video_url)
        job.item_terminal_emitted = True
        terminal_job = replace(
            job,
            url=retry_url,
            urls=[retry_url],
            single_video_only=True,
            batch_mode=False,
            preview_info=terminal_info,
            run_id=terminal_run_id,
            origin_run_id=job.run_id,
            execution_run_id=job.run_id,
            retry_of_run_id=None,
            metadata_keys=(
                {key} if (key := metadata_run_key(terminal_info)) is not None else set()
            ),
            history_identities=set(),
            activity_lines=([failure_details] if failure_details else []) + [message],
            terminal_status=status,
            terminal_message=message,
            item_terminal_emitted=True,
        )
        terminal_info = annotate_job_metadata(terminal_job, terminal_info)
        terminal_job.preview_info = terminal_info
        event = job_info_event("item_terminal", terminal_job, terminal_info)
        event[1]["playlist_continues"] = playlist_continues
        self.events.put(event)

    def _finish_download_run_outcome(
        self,
        job: DownloadJob,
        outcome: DownloadOutcome,
        *,
        emit_done: bool,
    ) -> DownloadOutcome:
        if outcome.success_count == 0:
            if outcome.failure_count:
                raise RuntimeError(
                    f"No valid {job.output_type.value} output was produced; "
                    f"{outcome.failure_count} item(s) failed. Failure report: "
                    f"{BATCH_FAILURE_REPORT_PATH}"
                )
            if emit_done:
                self.events.put(
                    (
                        "stopped",
                        f"{job.output_type.value} run stopped without producing an output.",
                    )
                )
            return outcome
        if emit_done:
            if (
                outcome.failure_count
                or outcome.skipped_count
                or outcome.sidecar_failure_count
            ):
                self.events.put(
                    (
                        "partial",
                        (
                            f"{job.output_type.value} completed with issues — "
                            f"{outcome.success_count} valid output(s), "
                            f"{outcome.failure_count} failed, {outcome.skipped_count} skipped, "
                            f"{outcome.sidecar_failure_count} optional sidecar failure(s). "
                            "Keep the valid files. Review Technical details for each issue and its next step."
                        ),
                    )
                )
            else:
                self.events.put(
                    (
                        "done",
                        (
                            f"{job.output_type.value} download complete — "
                            f"{outcome.success_count} valid output(s)."
                        ),
                    )
                )
        return outcome

    def _expand_download_source(
        self,
        job: DownloadJob,
        ytdlp_module: Any,
        provider_network: ProviderNetworkCoordinator,
        *,
        control_check: Callable[[], None],
        blocking_step_cancelled: Callable[[], bool],
    ) -> _ExpandedDownloadSource:
        """Resolve one submitted source into ordered item inputs and playlist identity."""
        saved = job.preview_info or {}
        if (
            job.recovery_reason == "missing_media"
            and job.single_video_only
            and not job.batch_mode
            and (job.urls or [job.url]) == [job.url]
            and youtube_url_video_id(job.url)
            and youtube_url_video_id(job.url) == str(saved.get("id") or "")
            and (youtube_url_playlist_id(job.url) or "")
            == str(saved.get("playlist_id") or "")
        ):
            # The recovery owner validated this saved item. Its captured playlist
            # is organization only; item preflight still reads current formats.
            control_check()
            playlist_info: dict[str, Any] = {
                key: saved[key]
                for key in ("playlist_id", "playlist_title")
                if saved.get(key)
            }
            playlist_info["webpage_url"] = job.url
            entry = {"webpage_url": job.url}
            if saved.get("playlist_index") is not None:
                entry["playlist_index"] = saved["playlist_index"]
            write_diagnostic("playlist detection skipped: selected Library recovery")
            return _ExpandedDownloadSource(playlist_info=playlist_info, entries=[entry])

        single_playlist_context = bool(
            job.single_video_only
            and youtube_url_video_id(job.url)
            and youtube_url_playlist_id(job.url)
        )
        if job.single_video_only and not single_playlist_context:
            # The source URL was already normalized and playlist expansion is
            # disabled. Avoid a full extractor pass whose only result would be
            # confirming the single item that preflight analyzes next.
            playlist_info = {"webpage_url": job.url}
            entries = [{"webpage_url": job.url}]
            write_diagnostic("playlist detection skipped: Ignore playlists is active")
            if youtube_url_video_id(job.url):
                self._emit_job_log(
                    job,
                    "No playlist context was included in this URL. To preserve a YouTube playlist folder, "
                    "copy the full browser address containing list= instead of the shortened Share link.",
                )
            return _ExpandedDownloadSource(playlist_info=playlist_info, entries=entries)

        self.events.put(("status", "Reading playlist…"))
        write_diagnostic("playlist detection start")
        playlist_started = time.monotonic()
        playlist_opts = _build_playlist_detection_options(
            job,
            deno_path=self._find_deno(),
        )
        log_options("playlist detection", playlist_opts)

        detect_playlist = partial(
            _extract_playlist_source_step,
            ytdlp_module,
            dict(playlist_opts),
            job.url,
            control_check=control_check,
            emit_log=partial(self._emit_job_log, job),
        )

        def report_playlist_wait(elapsed: float) -> None:
            write_diagnostic(f"playlist detection still running after {elapsed:.0f}s")
            self.events.put(
                (
                    "status",
                    f"Reading playlist… {elapsed:.0f}s elapsed; Cancel is available.",
                )
            )

        provider_network.begin_primary(control_check)
        try:
            playlist_result = run_cancellable_blocking_step(
                lambda: provider_network.run_primary(detect_playlist),
                blocking_step_cancelled,
                timeout_seconds=ANALYSIS_TIMEOUT_SECONDS,
                poll_seconds=ANALYSIS_POLL_SECONDS,
                label="Playlist detection",
                on_wait=report_playlist_wait,
            )
        finally:
            provider_network.end_primary()

        extracted_info, session_cookies = playlist_result
        write_diagnostic(
            f"playlist detection elapsed_seconds={time.monotonic() - playlist_started:.3f}"
        )
        playlist_info, entries = _normalize_download_source_result(
            extracted_info,
            job.url,
            single_video_only=job.single_video_only,
        )
        if job.single_video_only:
            requested_video_id = youtube_url_video_id(job.url)
            write_diagnostic(
                "playlist identity retained for single item: "
                f"playlist_id={playlist_info.get('id') or playlist_info.get('playlist_id')} "
                f"video_id={requested_video_id}"
            )
        return _ExpandedDownloadSource(
            playlist_info=playlist_info,
            entries=entries,
            session_cookies=session_cookies,
            cookie_source_loaded=job.use_cookies,
        )

    def _analyze_download_item(
        self,
        job: DownloadJob,
        ytdlp_module: Any,
        provider_network: ProviderNetworkCoordinator,
        item: _DownloadItemContext,
        playlist_info: dict[str, Any],
        max_height: int,
        session_cookies: tuple[Any, ...],
        cookie_source_loaded: bool,
        *,
        control_check: Callable[[], None],
        blocking_step_cancelled: Callable[[], bool],
        progress_callback: Callable[[float], None],
    ) -> _AnalyzedDownloadItem:
        """Analyze and plan one item while the caller owns the provider lease."""
        self.events.put(("status", f"{item.label} — analyzing source formats"))
        self._emit_job_log(job, f"{item.label}: URL {item.video_url}")
        progress_callback(0.0)

        ffmpeg = self._find_ffmpeg()
        deno = self._find_deno()
        options = _build_item_preflight_options(
            job,
            cookie_source_loaded=cookie_source_loaded,
            ffmpeg=ffmpeg,
            deno_path=deno,
        )
        write_diagnostic(f"{item.label} preflight runtime path: ffmpeg={ffmpeg}")
        write_diagnostic(f"{item.label} preflight runtime path: deno={deno}")
        write_diagnostic(
            f"{item.label} preflight Deno/bundled-EJS enabled"
            if deno
            else f"{item.label} preflight Deno/EJS disabled: no deno runtime found"
        )
        log_options(f"{item.label} preflight", options)

        analysis_step = partial(
            _analyze_source_formats_step,
            ytdlp_module,
            dict(options),
            tuple(session_cookies),
            item.video_url,
            item.label,
            control_check=control_check,
            emit_log=partial(self._emit_job_log, job),
        )

        def report_analysis_wait(elapsed: float) -> None:
            write_diagnostic(
                f"{item.label} analysis still running after {elapsed:.0f}s"
            )
            self.events.put(
                (
                    "status",
                    f"{item.label} — analyzing source formats ({elapsed:.0f}s elapsed); Cancel is available.",
                )
            )

        preflight_info, updated_session_cookies = run_cancellable_blocking_step(
            partial(provider_network.run_primary, analysis_step),
            blocking_step_cancelled,
            timeout_seconds=ANALYSIS_TIMEOUT_SECONDS,
            poll_seconds=ANALYSIS_POLL_SECONDS,
            label=f"{item.label} source analysis",
            on_wait=report_analysis_wait,
        )
        if not isinstance(preflight_info, dict):
            raise RuntimeError(  # noqa: TRY004 - provider protocol failures use RuntimeError
                f"{item.label}: YouTube source analysis did not return metadata"
            )
        preflight_info = mark_metadata_output_type(
            apply_playlist_context(
                preflight_info,
                item.entry,
                playlist_info,
                job.url,
                item.index,
            ),
            job.output_type,
        )
        plan = _build_download_item_plan(
            job,
            preflight_info,
            max_height=max_height,
        )
        preflight_info = annotate_job_metadata(job, preflight_info)
        display_info = build_encoding_summary_metadata(preflight_info, plan)
        self.events.put(job_info_event("job_metadata", job, display_info))
        for line in _download_item_plan_log_lines(job, item.label, plan):
            self._emit_job_log(job, line)
        progress_callback(1.0)
        return _AnalyzedDownloadItem(
            preflight_info=preflight_info,
            display_info=display_info,
            plan=plan,
            session_cookies=updated_session_cookies,
            cookie_source_loaded=job.use_cookies,
        )

    def _download_item_to_staging(
        self,
        job: DownloadJob,
        ytdlp_module: Any,
        provider_network: ProviderNetworkCoordinator,
        item: _DownloadItemContext,
        playlist_info: dict[str, Any],
        analyzed_item: _AnalyzedDownloadItem,
        staging_dir: Path,
        *,
        control_check: Callable[[], None],
        progress_callback: Callable[[float], None],
    ) -> _DownloadedStagingItem:
        """Transfer one analyzed item while the caller owns the provider lease."""
        plan = analyzed_item.plan
        ffmpeg = self._find_ffmpeg()
        if not ffmpeg:
            required_output = (
                "original audio"
                if job.output_type == OutputType.ORIGINAL
                else "MP3 audio"
                if isinstance(plan, AudioExportPlan)
                else f"H.264 / {plan.output_audio_codec.value} MP4 video"
            )
            raise RuntimeError(
                f"FFmpeg is required to create the {required_output} output."
            )
        if job_embeds_provider_thumbnail(job):
            validate_embedded_thumbnail_sources(
                analyzed_item.preflight_info,
                source_url=item.video_url,
            )
        options = self._build_ydl_options(
            job,
            staging_dir=staging_dir,
            format_selector=plan.format_selector,
        )
        transfer_info = analyzed_item.preflight_info
        if job.output_type == OutputType.MP4:
            transfer_info = apply_original_caption_options(
                options, transfer_info, job.translated_subtitle_language
            )
            if "subtitleslangs" not in options:
                self._emit_job_log(
                    job,
                    f"{item.label}: original-language captions unavailable or language unverified; no translated track selected.",
                )
            if job.translated_subtitle_language and not any(
                track.get("role") == "translated"
                for track in transfer_info.get("vodforge_subtitle_tracks", [])
            ):
                self._emit_job_log(
                    job,
                    f"{item.label}: selected translated subtitles unavailable; exporting available original captions only.",
                )
        options["noplaylist"] = True
        # Preflight already loaded the selected cookie source. Reuse its
        # in-memory session jar instead of reopening a browser profile or file.
        options.pop("cookiefile", None)
        options.pop("cookiesfrombrowser", None)
        log_options(f"{item.label} download", options)
        self._active_progress_context = (item.index, item.total, 0.10, 0.40)
        self.events.put(("status", f"{item.label} — downloading"))
        self._emit_job_log(job, f"{item.label}: downloading")
        download_started = time.monotonic()
        guard = None
        if (
            job.output_type == OutputType.MP4
            and isinstance(plan, ExportPlan)
            and plan.video_format_id
            and plan.audio_format_id
            and "subtitleslangs" not in options
        ):
            guard = SplitTransferRefresh(
                transfer_info, plan.video_format_id, plan.audio_format_id, staging_dir
            )

        def refresh_transfer_metadata():
            refresh_options = _build_item_preflight_options(
                job,
                cookie_source_loaded=True,
                ffmpeg=ffmpeg,
                deno_path=self._find_deno(),
            )
            step = partial(
                _analyze_source_formats_step,
                ytdlp_module,
                refresh_options,
                tuple(analyzed_item.session_cookies),
                item.video_url,
                item.label,
                control_check=control_check,
                emit_log=partial(self._emit_job_log, job),
            )

            def cancelled():
                control_check()
                return False

            return run_cancellable_blocking_step(
                step,
                cancelled,
                timeout_seconds=ANALYSIS_TIMEOUT_SECONDS,
                poll_seconds=ANALYSIS_POLL_SECONDS,
                label=f"{item.label} transfer metadata refresh",
            )

        download_step = partial(
            _download_with_audio_url_refresh,
            ytdlp_module,
            options,
            transfer_info,
            tuple(analyzed_item.session_cookies),
            guard,
            refresh=refresh_transfer_metadata,
            control_check=control_check,
            emit_log=partial(self._emit_job_log, job),
        )
        info, session_cookies = provider_network.run_primary(download_step)
        write_diagnostic(
            f"{item.label} download and yt-dlp post-processing "
            f"elapsed_seconds={time.monotonic() - download_started:.3f}"
        )
        self._active_progress_context = None
        control_check()
        if not isinstance(info, dict):
            raise RuntimeError(  # noqa: TRY004 - provider protocol failures use RuntimeError
                f"{item.label}: download did not return metadata"
            )
        info = mark_metadata_output_type(
            apply_playlist_context(
                info,
                item.entry,
                playlist_info,
                job.url,
                item.index,
            ),
            job.output_type,
        )
        if "subtitleslangs" in options:
            info["vodforge_original_caption_expected"] = True
            info["vodforge_caption_summary"] = transfer_info["vodforge_caption_summary"]
            info["vodforge_subtitle_tracks"] = transfer_info["vodforge_subtitle_tracks"]
        info = annotate_job_metadata(job, info)
        encoding_summary = analyzed_item.display_info.get("vodforge_encoding_summary")
        if encoding_summary:
            info["vodforge_encoding_summary"] = encoding_summary
        self.events.put(job_info_event("job_metadata", job, info))
        progress_callback(1.0)
        return _DownloadedStagingItem(
            metadata=info,
            session_cookies=session_cookies,
            ffmpeg=ffmpeg,
        )

    def _prepare_staged_download_item(
        self,
        job: DownloadJob,
        item: _DownloadItemContext,
        downloaded_item: _DownloadedStagingItem,
        staging_dir: Path,
        *,
        control_check: Callable[[], None],
    ) -> _PreparedStagingItem:
        """Bind expected staged media and optional cover art before validation."""
        expected_extension = (
            original_audio_extension(str(downloaded_item.metadata.get("acodec") or ""))
            if job.output_type == OutputType.ORIGINAL
            else ".mp3"
            if job.output_type == OutputType.MP3
            else ".mp4"
        )
        staged_media = collect_staged_media_files(
            staging_dir,
            downloaded_item.metadata,
            expected_extension=expected_extension,
        )
        if not staged_media:
            raise RuntimeError(
                f"{item.label}: yt-dlp completed without producing the expected "
                f"{expected_extension} file."
            )

        if downloaded_item.metadata.get("vodforge_original_caption_expected"):
            ffprobe = _ffprobe_for_ffmpeg(downloaded_item.ffmpeg)
            if not ffprobe:
                raise RuntimeError("FFprobe is required to verify downloaded captions.")
            for _staged_info, staged_video in staged_media:
                probe = run_ffprobe_json(
                    ffprobe, staged_video, control_check=control_check
                )
                require_selected_subtitle_streams(
                    probe, downloaded_item.metadata.get("vodforge_subtitle_tracks")
                )

        custom_cover_for_cache: Path | None = None
        custom_cover_path = job.mp3_settings.custom_cover_art_path
        if job.output_type == OutputType.MP3 and custom_cover_path is not None:
            control_check()
            prepared_cover = prepare_custom_cover_art(custom_cover_path, staging_dir)
            for _staged_info, staged_mp3 in staged_media:
                embed_custom_mp3_cover_art(
                    staged_mp3,
                    prepared_cover,
                    downloaded_item.ffmpeg,
                    control_check=control_check,
                )
            control_check()
            custom_cover_for_cache = prepared_cover
            self._emit_job_log(
                job,
                f"{item.label}: embedded custom cover art ({custom_cover_path.name})",
            )
        return _PreparedStagingItem(
            metadata=downloaded_item.metadata,
            staged_media=staged_media,
            expected_extension=expected_extension,
            ffmpeg=downloaded_item.ffmpeg,
            custom_cover_for_cache=custom_cover_for_cache,
        )

    def _emit_failed_download_item_metadata(
        self,
        job: DownloadJob,
        result: _DownloadItemResult,
        issue: str,
    ) -> None:
        if result.metadata is None:
            return
        self.events.put(
            job_info_event(
                "job_metadata",
                job,
                build_failed_encoding_summary_metadata(
                    result.metadata,
                    result.plan,
                    issue,
                ),
            )
        )

    def _resolve_download_item_failure(
        self,
        job: DownloadJob,
        item: _DownloadItemContext,
        result: _DownloadItemResult,
        error: Exception,
    ) -> _DownloadItemResult:
        """Classify one item failure from typed user authority and item scope."""
        self._active_progress_context = None
        control_request = (
            error if isinstance(error, _DownloadControlRequestError) else None
        )
        if control_request is None:
            try:
                self._raise_for_download_control_requests()
            except _DownloadControlRequestError as pending_request:
                control_request = pending_request

        if control_request is not None:
            DownloadWorkerCore._observe_download_operation(
                self,
                job,
                "cancelled",
                dimensions={
                    "outcome": "stopped"
                    if control_request.kind is _DownloadControlKind.CANCEL_RUN
                    else "skipped"
                },
            )
            if control_request.kind is _DownloadControlKind.CANCEL_RUN:
                self._emit_failed_download_item_metadata(
                    job, result, str(control_request)
                )
                raise _DownloadControlRequestError(
                    control_request.kind,
                    result=result,
                ) from error

            telemetry = self.__dict__.get("product_telemetry")
            if telemetry is not None:
                telemetry.record(
                    "run_skipped",
                    dedupe_key=job.run_id + ":" + str(item.index),
                    attempt_key=job.run_id,
                    run_kind="youtube",
                    output_type=product_output_kind(job.output_type.value),
                )
            skipped_outcome = result.outcome.combined_with(
                DownloadOutcome(skipped_count=1)
            )
            if control_request.kind is _DownloadControlKind.SKIP_SOURCE:
                self.skip_url_requested = False
                self.skip_video_requested = False
                self._emit_download_item_terminal(
                    job,
                    "Skipped",
                    "URL skipped by user",
                    result.metadata,
                    result.plan,
                    item.video_url,
                )
                self._emit_job_log(job, f"{item.label}: skipped URL by user.")
                return replace(
                    result,
                    outcome=skipped_outcome,
                    stop_source=True,
                )

            issue = str(control_request)
            self._emit_failed_download_item_metadata(job, result, issue)
            self._emit_download_item_terminal(
                job,
                "Skipped",
                "Video skipped by user",
                result.metadata,
                result.plan,
                item.video_url,
                playlist_continues=item.index < item.total,
            )
            self._emit_job_log(
                job,
                f"{item.label}: skipped by user; continuing to next video.",
            )
            self.skip_video_requested = False
            return replace(result, outcome=skipped_outcome)

        job.failure_diagnostic = capture_failure(error, stage=job.failure_stage)
        DownloadWorkerCore._observe_download_operation(
            self,
            job,
            "failed",
            failure_detail=job.failure_diagnostic,
            dimensions={"failed_count": "1"},
        )
        issue = format_ytdlp_user_error(error)
        if item.total <= 1:
            raise _DownloadItemExecutionError(error, result) from error
        self._emit_failed_download_item_metadata(job, result, issue)
        write_diagnostic(
            f"{item.label} failed but playlist will continue: "
            f"{type(error).__name__}: {error}"
        )
        failed_outcome = result.outcome.combined_with(DownloadOutcome(failure_count=1))
        self._emit_download_item_terminal(
            job,
            "Failed",
            issue,
            result.metadata,
            result.plan,
            item.video_url,
            failure_details=technical_download_error(error),
        )
        append_batch_failure_report(BATCH_FAILURE_REPORT_PATH, item.video_url, error)
        self._emit_job_log(
            job,
            f"WARNING: {item.label} failed; continuing to next video. Failure report: {BATCH_FAILURE_REPORT_PATH}",
        )
        self.skip_video_requested = False
        return replace(result, outcome=failed_outcome)

    def _complete_staged_download_item(
        self,
        job: DownloadJob,
        source: _DownloadSourceContext,
        item: _DownloadItemContext,
        result: _DownloadItemResult,
    ) -> _DownloadItemResult:
        """Own one staging transaction after analysis and a reuse miss."""
        analyzed_item = result.analysis
        current_info = result.metadata
        current_plan = result.plan
        if analyzed_item is None or current_info is None or current_plan is None:
            raise RuntimeError("download item analysis contract is incomplete")

        all_output_dirs = list(result.output_dirs)
        staging_dir: Path | None = None
        primary_intent_active = True
        failure: Exception | None = None
        validated_media_pending_commit = False
        preserve_completed_media = False
        try:
            staging_dir = create_staging_dir(job.output_dir)
            recovery_owner = self.__dict__.get("run_recovery")
            if recovery_owner is not None:
                recovery_owner.staging_started(job, staging_dir)
            DownloadWorkerCore._observe_download_operation(
                self, job, "stage", stage="download"
            )
            downloaded_item = self._download_item_to_staging(
                job,
                source.ytdlp_module,
                source.provider_network,
                item,
                source.playlist_info,
                analyzed_item,
                staging_dir,
                control_check=self._raise_for_download_control_requests,
                progress_callback=partial(
                    self._put_download_stage_progress,
                    item,
                    0.10,
                    0.40,
                ),
            )
            result = replace(
                result,
                session_cookies=downloaded_item.session_cookies,
            )
            source.provider_network.end_primary()
            primary_intent_active = False
            prepared_item = self._prepare_staged_download_item(
                job,
                item,
                downloaded_item,
                staging_dir,
                control_check=self._raise_for_download_control_requests,
            )
            current_info = prepared_item.metadata
            result = replace(result, metadata=current_info)

            DownloadWorkerCore._observe_download_operation(
                self, job, "stage", stage="transcode"
            )
            validated_staged = self._transcode_and_validate_staged_media(
                job,
                current_info,
                current_plan,
                prepared_item.staged_media,
                prepared_item.ffmpeg,
                label=item.label,
                progress_callback=partial(
                    self._put_download_stage_progress,
                    item,
                    0.50,
                    0.40,
                ),
                control_check=self._raise_for_download_control_requests,
            )
            validated_media_pending_commit = bool(validated_staged)
            DownloadWorkerCore._observe_download_operation(
                self, job, "stage", stage="commit"
            )
            committed_media = self._commit_validated_staged_media(
                job,
                current_info,
                current_plan,
                staging_dir,
                prepared_item.expected_extension,
                validated_staged,
                label=item.label,
                all_output_dirs=all_output_dirs,
                progress_callback=partial(
                    self._put_download_stage_progress,
                    item,
                    0.50,
                    0.40,
                ),
                control_check=self._raise_for_download_control_requests,
            )
            validated_media_pending_commit = False
            before_sidecars = result.outcome.sidecar_failure_count
            DownloadWorkerCore._observe_download_operation(
                self, job, "stage", stage="sidecars"
            )
            current_info = committed_media.metadata
            result = replace(
                result,
                outcome=result.outcome.combined_with(
                    DownloadOutcome(success_count=committed_media.success_count)
                ),
                output_dirs=tuple(all_output_dirs),
                metadata=current_info,
            )
            result = replace(
                result,
                outcome=result.outcome.combined_with(
                    self._record_committed_media_and_write_sidecars(
                        job,
                        current_info,
                        committed_media.primary_output,
                        label=item.label,
                        custom_cover_for_cache=prepared_item.custom_cover_for_cache,
                    )
                ),
            )
            sidecar_failures = result.outcome.sidecar_failure_count - before_sidecars
            DownloadWorkerCore._observe_download_operation(
                self,
                job,
                "completed",
                dimensions={
                    "committed_count": str(min(committed_media.success_count, 10000)),
                    "reused_count": "0",
                    "sidecar_failure_count": str(min(sidecar_failures, 10000)),
                    "outcome": "partial" if sidecar_failures else "complete",
                },
            )
            self._put_download_stage_progress(item, 0.90, 0.10, 1.0)
            result_label = (
                "Original audio"
                if job.output_type == OutputType.ORIGINAL
                else "MP3 audio"
                if job.output_type == OutputType.MP3
                else "MP4 video"
            )
            self.events.put(("status", f"{item.label} complete — {result_label}"))
            self._emit_job_log(job, f"{item.label} complete — {result_label}")
        except Exception as exc:  # noqa: BLE001 - item failure policy classifies provider and control errors
            failure = exc
            preserve_completed_media = (
                validated_media_pending_commit and is_windows_sharing_violation(exc)
            )
            if preserve_completed_media:
                recovery_owner = self.__dict__.get("run_recovery")
                if recovery_owner is not None and staging_dir is not None:
                    try:
                        recovery_owner.completed_staging_retained(job, staging_dir)
                    except RunStateError as state_error:
                        write_diagnostic(
                            f"Retained media recovery ownership could not be saved: {state_error}"
                        )
                self._emit_job_log(
                    job,
                    f"{item.label}: completed media retained at {staging_dir}. "
                    "Another process still holds the file. Close that program "
                    "and recover the completed media from this folder.",
                )
        finally:
            self._active_progress_context = None
            if staging_dir is not None and not preserve_completed_media:
                cleanup_private_staging_directory(staging_dir)
            if primary_intent_active:
                source.provider_network.end_primary()
        if failure is not None:
            result = replace(result, output_dirs=tuple(all_output_dirs))
            return self._resolve_download_item_failure(job, item, result, failure)
        return result

    def _observed_output_dimensions(
        self,
        output_path: Path,
        probe: Any,
        *,
        info: dict[str, Any] | None = None,
        artifact_count: int = 1,
    ) -> dict[str, str]:
        # No extra filesystem observations without current collection consent.
        telemetry = self.__dict__.get("product_telemetry")
        try:
            permitted = getattr(telemetry, "permitted", None)
            if not callable(permitted) or not permitted():
                return {}
        except Exception:  # noqa: BLE001 - unavailable consent is not permission
            return {}
        facts = {"output_observation": "unavailable", "observed_audio_state": "unknown"}
        try:
            facts.update(
                observed_audio_characteristics(probe, artifact_count=artifact_count)
            )
        except Exception:  # noqa: BLE001, S110  # nosec B110 - malformed probe observations cannot break media
            pass
        if artifact_count != 1:
            facts.update(
                namespace_scan_state="not_applicable",
                peer_namespace_state="not_applicable",
            )
            return facts
        try:
            facts.update(
                observed_output_namespace(
                    output_path, info, self.__dict__.get("download_history")
                )
            )
        except Exception:  # noqa: BLE001 - optional observation cannot control the commit
            facts.update(namespace_scan_state="unknown", peer_namespace_state="unknown")
        return facts

    def _observe_download_operation(
        self,
        job: DownloadJob,
        action: str,
        *,
        stage: str | None = None,
        dimensions: dict[str, str] | None = None,
        failure_detail: FailureDiagnostic | None = None,
        output_path: Path | None = None,
        output_probe: Any = None,
        output_info: dict[str, Any] | None = None,
        artifact_count: int = 1,
    ) -> None:
        if stage is not None:
            job.failure_stage = stage
        telemetry = self.__dict__.get("product_telemetry")
        operation = getattr(job, "telemetry_operation_id", None)
        if telemetry is not None and operation:
            facts = {
                "stage": job.failure_stage,
                **selection_observation(
                    getattr(job, "selection_dimensions", {}), scope="item"
                ),
                **dict(dimensions or {}),
            }
            if output_path is not None:
                facts.update(
                    DownloadWorkerCore._observed_output_dimensions(
                        self,
                        output_path,
                        output_probe,
                        info=output_info,
                        artifact_count=artifact_count,
                    )
                )
            try:
                telemetry.record_operation(
                    "download_operation",
                    action,
                    operation_key=operation,
                    attempt_key=job.run_id,
                    retry_key=job.retry_of_run_id,
                    dimensions=facts,
                    failure_detail=failure_detail,
                )
            except Exception:  # noqa: BLE001, S110  # nosec B110 - telemetry cannot own export success
                pass

    def _observe_download_sidecar_failure(
        self, job: DownloadJob, error: Exception, *, kind: str, reused: bool = False
    ) -> None:
        DownloadWorkerCore._observe_download_operation(
            self,
            job,
            "failed",
            stage="sidecars",
            dimensions={
                "sidecar_failure_count": "1",
                "failed_count": "0",
                "sidecar_kind": kind,
                "sidecar_outcome": "failed",
                "sidecar_context": "reused_media" if reused else "committed_media",
            },
            failure_detail=capture_failure(error, stage="sidecars"),
        )

    def _download_sidecar_observer(
        self, job: DownloadJob, kind: str, *, reused: bool = False
    ) -> Callable[[str], None] | None:
        telemetry = self.__dict__.get("product_telemetry")
        try:
            if telemetry is None or not telemetry.permitted():
                return None
        except Exception:  # noqa: BLE001 - unavailable consent fails closed
            return None

        def observed(result: str) -> None:
            # Repaired here means a missing requested companion was restored
            # beside reused media, not that a prior deletion was reconstructed.
            outcome = "repaired" if reused and result == "created" else result
            DownloadWorkerCore._observe_download_operation(
                self,
                job,
                "stage",
                stage="sidecars",
                dimensions={
                    "sidecar_kind": kind,
                    "sidecar_outcome": outcome,
                    "sidecar_context": "reused_media" if reused else "committed_media",
                },
            )

        return observed

    def _observed_intent_relation(self, job: DownloadJob, info: dict[str, Any]) -> str:
        # An observational comparison must never create media-work failure.
        # Invalid/absent evidence is unknown, not a claim of first use.
        history = self.__dict__.get("download_history")
        if not isinstance(history, (list, tuple)) or not isinstance(
            info.get("id"), str
        ):
            return "unknown"
        if any(
            not isinstance(record, dict)
            or not isinstance(record.get("id"), str)
            or any(
                record.get(key) is not None and not isinstance(record[key], str)
                for key in (
                    "webpage_url",
                    "vodforge_attempt_signature",
                    "vodforge_output_variant",
                    "vodforge_output_variant_compact",
                )
            )
            for record in history
        ):
            return "unknown"
        previous = [
            record
            for record in history
            if info.get("id") and record.get("id") == info["id"]
        ]
        if not previous:
            return "first_observed"
        source_url = sanitize_durable_url(
            str(info.get("webpage_url") or ""), preserve_youtube_context=True
        )
        if not source_url:
            return "unknown"
        same_source = [
            record
            for record in previous
            if sanitize_durable_url(
                str(record.get("webpage_url") or ""), preserve_youtube_context=True
            )
            == source_url
        ]
        if not same_source:
            # Equal provider IDs alone do not establish equal sources.
            return "unknown"
        previous = same_source
        signature = job_attempt_signature(job)
        if any(metadata_attempt_signature(record) == signature for record in previous):
            return "same_intent"
        variant = metadata_output_variant(info)
        known = [
            metadata_output_variant(record)
            for record in previous
            if metadata_output_variant(record)
        ]
        if not variant or not known:
            return "unknown"
        return (
            "different_destination_or_organization"
            if variant in known
            else "different_settings"
        )

    def _coordinate_download_item(
        self,
        job: DownloadJob,
        source: _DownloadSourceContext,
        item: _DownloadItemContext,
        previous: _DownloadItemResult,
    ) -> _DownloadItemResult:
        """Acquire, analyze, and choose reuse or a staging transaction."""
        result = replace(
            previous,
            analysis=None,
            metadata=None,
            plan=None,
            stop_source=False,
        )
        primary_intent_active = False
        job.telemetry_operation_id = str(uuid.uuid4())
        job.selection_dimensions = {}
        DownloadWorkerCore._observe_download_operation(
            self,
            job,
            "started",
            stage="analysis",
            dimensions={
                **job_intent_dimensions(job),
                "item_count": str(min(item.total, 10000)),
            },
        )
        try:
            self._raise_for_download_control_requests()
            source.provider_network.begin_primary(
                self._raise_for_download_control_requests
            )
            primary_intent_active = True
            analyzed_item = self._analyze_download_item(
                job,
                source.ytdlp_module,
                source.provider_network,
                item,
                source.playlist_info,
                source.max_height,
                result.session_cookies,
                result.cookie_source_loaded,
                control_check=self._raise_for_download_control_requests,
                blocking_step_cancelled=self._video_blocking_step_cancelled,
                progress_callback=partial(
                    self._put_download_stage_progress,
                    item,
                    0.0,
                    0.10,
                ),
            )
            result = replace(
                result,
                session_cookies=analyzed_item.session_cookies,
                cookie_source_loaded=analyzed_item.cookie_source_loaded,
                analysis=analyzed_item,
                metadata=analyzed_item.display_info,
                plan=analyzed_item.plan,
            )
            recovery_owner = self.__dict__.get("run_recovery")
            if recovery_owner is not None:
                recovery_owner.metadata_observed(job, analyzed_item.display_info)
            all_output_dirs = list(result.output_dirs)
            job.failure_stage = "reuse"
            DownloadWorkerCore._observe_download_operation(
                self,
                job,
                "stage",
                stage="reuse",
                dimensions={
                    "intent_relation": DownloadWorkerCore._observed_intent_relation(
                        self, job, analyzed_item.display_info
                    )
                },
            )
            existing_reuse = self._try_reuse_existing_output(
                job,
                analyzed_item.display_info,
                analyzed_item.plan,
                label=item.label,
                all_output_dirs=all_output_dirs,
                control_check=self._raise_for_download_control_requests,
            )
            if existing_reuse is not None:
                DownloadWorkerCore._observe_download_operation(
                    self,
                    job,
                    "completed",
                    dimensions={
                        "reuse_result": "hit",
                        "reused_count": "1",
                        "committed_count": "0",
                        "sidecar_failure_count": str(
                            min(existing_reuse.outcome.sidecar_failure_count, 10000)
                        ),
                        "outcome": "partial"
                        if existing_reuse.outcome.sidecar_failure_count
                        else "complete",
                    },
                )
                self._put_download_stage_progress(item, 0.10, 0.90, 1.0)
                self.events.put(
                    (
                        "status",
                        (
                            f"{item.label} complete — Already downloaded and valid — "
                            "reused existing file."
                        ),
                    )
                )
                return replace(
                    result,
                    outcome=result.outcome.combined_with(existing_reuse.outcome),
                    output_dirs=tuple(all_output_dirs),
                    metadata=existing_reuse.metadata,
                )
            job.failure_stage = "validation"
            extension = (
                analyzed_item.plan.output_extension
                if isinstance(analyzed_item.plan, AudioExportPlan)
                else ".mp4"
            )
            preflight_video_output_target(
                job.output_dir, analyzed_item.display_info, extension
            )
            DownloadWorkerCore._observe_download_operation(
                self, job, "stage", stage="staging", dimensions={"reuse_result": "miss"}
            )
            primary_intent_active = False
        except Exception as exc:  # noqa: BLE001 - item failure resolver separates user control from provider text
            return self._resolve_download_item_failure(job, item, result, exc)
        finally:
            if primary_intent_active:
                source.provider_network.end_primary()

        return self._complete_staged_download_item(job, source, item, result)

    def _log_expanded_download_source(
        self,
        job: DownloadJob,
        total_videos: int,
    ) -> None:
        if total_videos > 1:
            self._emit_job_log(job, f"Playlist detected: {total_videos} videos.")
            write_diagnostic(f"playlist detected: video_count={total_videos}")
            return
        self._emit_job_log(job, "Single video detected.")
        write_diagnostic("single video detected")

    def _finish_download_source_failure(
        self,
        job: DownloadJob,
        result: _DownloadItemResult,
        error: Exception,
        *,
        re_raise: bool,
    ) -> DownloadOutcome:
        self._active_progress_context = None
        user_error = format_ytdlp_user_error(error)
        job.failure_diagnostic = capture_failure(error, stage=job.failure_stage)
        self._emit_failed_download_item_metadata(job, result, user_error)
        write_diagnostic(f"download worker error: {type(error).__name__}: {error}")
        if re_raise:
            raise _DownloadItemExecutionError(error, result) from error
        self.events.put(("error", user_error))
        return result.outcome

    def _download_worker_single(
        self,
        job: DownloadJob,
        *,
        emit_done: bool = True,
        re_raise: bool = False,
    ) -> DownloadOutcome:
        result = _DownloadItemResult(outcome=DownloadOutcome())
        provider_network = self._provider_network_coordinator()

        try:
            ytdlp_module = load_yt_dlp()
            if ytdlp_module is None:
                raise RuntimeError(f"yt-dlp import failed: {YTDLP_IMPORT_ERROR}")
            max_height = _quality_max_height(job.quality_label)
            self._emit_job_log(job, f"Normalized URL: {job.url}")
            self.events.put(("progress", 0))
            expanded_source = self._expand_download_source(
                job,
                ytdlp_module,
                provider_network,
                control_check=self._raise_for_download_control_requests,
                blocking_step_cancelled=self._playlist_blocking_step_cancelled,
            )
            result = replace(
                result,
                session_cookies=expanded_source.session_cookies,
                cookie_source_loaded=expanded_source.cookie_source_loaded,
            )
            entries = expanded_source.entries
            total_videos = len(entries)
            self._log_expanded_download_source(job, total_videos)

            self.video_output_dirs_by_id = {}
            source = _DownloadSourceContext(
                ytdlp_module=ytdlp_module,
                provider_network=provider_network,
                playlist_info=expanded_source.playlist_info,
                max_height=max_height,
            )
            for video_index, entry in enumerate(entries, start=1):
                if total_videos > 1:
                    self.events.put(
                        ("status", f"Video {video_index} of {total_videos} — preparing")
                    )
                    self.events.put(("progress", 0))
                    self.events.put(
                        job_info_event(
                            "job_metadata",
                            job,
                            {
                                **entry,
                                "title": entry.get("title")
                                or f"Preparing video {video_index} of {total_videos}",
                                "webpage_url": _download_entry_url(entry, job.url),
                                "vodforge_output_type": job.output_type.value,
                            },
                        )
                    )
                item = _DownloadItemContext(
                    entry=entry,
                    index=video_index,
                    total=total_videos,
                    video_url=_download_entry_url(entry, job.url),
                    label=f"Video {video_index} of {total_videos}",
                )
                result = self._coordinate_download_item(job, source, item, result)
                if result.stop_source:
                    break

            return self._finish_download_run_outcome(
                job,
                result.outcome,
                emit_done=emit_done,
            )
        except _DownloadControlRequestError as control_request:
            self._active_progress_context = None
            if control_request.result is not None:
                result = control_request.result
            write_diagnostic(
                f"download worker control request: {control_request.kind.value}"
            )
            if re_raise:
                raise
            if control_request.kind is _DownloadControlKind.SKIP_SOURCE:
                self.skip_url_requested = False
                self.skip_video_requested = False
            elif control_request.kind is _DownloadControlKind.SKIP_ITEM:
                self.skip_video_requested = False
            self.events.put(
                _download_source_control_terminal_event(
                    job,
                    result,
                    control_request.kind,
                )
            )
            return result.outcome
        except Exception as exc:  # noqa: BLE001 - source parent converts provider failures into one terminal outcome
            result, source_error = _download_source_failure_context(exc, result)
            return self._finish_download_source_failure(
                job,
                result,
                source_error,
                re_raise=re_raise,
            )

    def _build_ydl_options(
        self, job: DownloadJob, staging_dir: Path, format_selector: str | None = None
    ) -> dict[str, Any]:
        if job.output_type == OutputType.MP3:
            use_youtube_cover = job_embeds_provider_thumbnail(job)
            postprocessors: list[dict[str, Any]] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": str(job.mp3_settings.bitrate_kbps),
                },
            ]
            if job.mp3_settings.embed_metadata:
                postprocessors.append(
                    {
                        "key": "FFmpegMetadata",
                        "add_chapters": True,
                        "add_metadata": True,
                    }
                )
            if use_youtube_cover:
                postprocessors.append(
                    {"key": "EmbedThumbnail", "already_have_thumbnail": False}
                )
            selected_format = format_selector or "bestaudio/best"
            write_thumbnail = use_youtube_cover
            postprocessor_args = (
                self._metadata_args(job.tags) if job.mp3_settings.embed_metadata else {}
            )
            audio_args: list[str] = []
            if job.mp3_settings.sample_rate:
                audio_args.extend(("-ar", job.mp3_settings.sample_rate))
            if job.mp3_settings.channels:
                audio_args.extend(("-ac", job.mp3_settings.channels))
            if audio_args:
                postprocessor_args["extractaudio+ffmpeg_o"] = audio_args
        else:
            postprocessors = [
                {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
            ]
            if job.embed_metadata:
                postprocessors.append(
                    {
                        "key": "FFmpegMetadata",
                        "add_chapters": True,
                        "add_metadata": True,
                    }
                )
            if job.embed_thumbnail:
                postprocessors.append(
                    {"key": "EmbedThumbnail", "already_have_thumbnail": False}
                )
            selected_format = (
                format_selector or QUALITY_OPTIONS[job.quality_label]
            ) + "/best"
            # A separate thumbnail is fetched through VODForge's bounded,
            # redirect-aware authority policy after the media commit. yt-dlp
            # needs thumbnail network authority only when it must embed one.
            write_thumbnail = job_embeds_provider_thumbnail(job)
            postprocessor_args = self._metadata_args(job.tags)

        outtmpl = staging_output_template()
        opts: dict[str, Any] = {
            "format": selected_format,
            "outtmpl": outtmpl,
            # yt-dlp probes formats with NamedTemporaryFile before downloading.
            # An absolute per-run temp path is required because packaged macOS
            # applications may start with `/` as their working directory.
            "paths": {"home": str(staging_dir), "temp": str(staging_dir)},
            "windowsfilenames": True,
            "restrictfilenames": False,
            "noplaylist": False,
            "writethumbnail": write_thumbnail,
            "writeinfojson": False,
            "postprocessors": postprocessors,
            # VODForge owns progress through the hook below. Suppressing yt-dlp's
            # terminal printer avoids caching its logger wrapper, which otherwise
            # retains the per-job event queue after the download completes.
            "noprogress": True,
            "progress_hooks": [self._progress_hook],
            "logger": QueueLogger(self.events),
            "embed_infojson": False,
            "postprocessor_args": postprocessor_args,
            "concurrent_fragment_downloads": 1,
            "ignore_no_formats_error": True,
        }
        if job.output_type == OutputType.ORIGINAL:
            opts.update(original_audio_options(format_selector))
        apply_ytdlp_network_retry_policy(opts, source_analysis=False)
        if job.output_type == OutputType.MP4:
            opts["merge_output_format"] = "mp4"
        ffmpeg = self._find_ffmpeg()
        if ffmpeg:
            opts["ffmpeg_location"] = ytdlp_ffmpeg_location(ffmpeg)
        deno = self._find_deno()
        apply_youtube_runtime_options(opts, deno_path=deno)
        apply_ytdlp_cookie_options(
            opts,
            use_cookies=job.use_cookies,
            cookie_file=job.cookie_file,
            cookie_browser=job.cookie_browser,
        )
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
        except Exception as exc:  # noqa: BLE001 - optional runtime discovery remains nonfatal
            write_diagnostic(
                f"optional imageio FFmpeg fallback unavailable: {type(exc).__name__}"
            )
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
        # Apply extra keywords specifically to FFmpegMetadata's output command.
        # yt-dlp normalizes postprocessor argument keys to lowercase.
        return {"metadata+ffmpeg_o": ["-metadata", f"keywords={','.join(tags)}"]}

    def _progress_hook(self, data: dict[str, Any]) -> None:
        self._raise_for_download_control_requests()
        status = data.get("status")
        if status == "downloading":
            now = time.monotonic()
            last_event_at = getattr(self, "_last_progress_event_at", 0.0)
            downloaded = _first_finite_float(data.get("downloaded_bytes"))
            total = _first_finite_float(
                data.get("total_bytes"),
                data.get("total_bytes_estimate"),
            )
            if now - last_event_at < PROGRESS_EVENT_INTERVAL_SECONDS and not (
                total and downloaded >= total
            ):
                return
            self._last_progress_event_at = now
            self.events.put(("progress_determinate", None))
            if total:
                pct = downloaded / total * 100
                context = self._active_progress_context
                if context:
                    video_index, total_videos, stage_start, stage_weight = context
                    global_pct = (
                        (video_index - 1) / max(total_videos, 1)
                        + (stage_start + stage_weight * (pct / 100.0))
                        / max(total_videos, 1)
                    ) * 100.0
                    self.events.put(("progress", global_pct))
                else:
                    self.events.put(("progress", pct))
            speed = data.get("speed")
            eta_seconds = _finite_float(data.get("eta"))
            eta = (
                f"{max(0, math.ceil(eta_seconds))}s" if eta_seconds is not None else "?"
            )
            filename = Path(str(data.get("filename") or "")).name
            self.events.put(
                (
                    "status",
                    f"Downloading {filename} — {self._fmt_bytes(speed)}/s ETA {eta}",
                )
            )
        elif status == "finished":
            context = self._active_progress_context
            if context:
                video_index, total_videos, stage_start, stage_weight = context
                global_pct = (
                    (video_index - 1) / max(total_videos, 1)
                    + (stage_start + stage_weight) / max(total_videos, 1)
                ) * 100.0
                self.events.put(("progress", global_pct))
            else:
                self.events.put(("progress", 100))
            self.events.put(("status", "Download finished; finalizing output…"))

    def _emit_job_log(self, job: DownloadJob, line: str) -> None:
        self.events.put(job_log_event(job, line))

    @staticmethod
    def _fmt_bytes(value: Any) -> str:
        if not value:
            return "?"
        size = _finite_float(value)
        if size is None:
            return "?"
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"


def debug_preflight(url: str) -> int:
    reset_diagnostics_log()
    write_diagnostic(
        f"debug-preflight start: frozen={getattr(sys, 'frozen', False)} executable={sys.executable} argv={sys.argv}"
    )
    write_diagnostic(f"diagnostics log path: {DIAGNOSTICS_LOG_PATH}")
    write_diagnostic(f"URL received: {url}")
    normalized_url = url.strip()
    write_diagnostic(f"normalized URL: {normalized_url}")
    write_diagnostic(
        f"playlist query present: {'list=' in normalized_url.lower()} ; noplaylist setting for analysis: False"
    )
    ytdlp_module = load_yt_dlp()
    if ytdlp_module is None:
        write_diagnostic(f"yt-dlp import failed: {YTDLP_IMPORT_ERROR}")
        print(f"yt-dlp import failed: {YTDLP_IMPORT_ERROR}")
        print(f"Diagnostics log: {DIAGNOSTICS_LOG_PATH}")
        return 2
    write_diagnostic(
        f"yt-dlp version: {getattr(ytdlp_module.version, '__version__', 'unknown')}"
    )
    opts: dict[str, Any] = {
        "quiet": False,
        "verbose": True,
        "skip_download": True,
        "noplaylist": False,
        "extract_flat": False,
        "logger": QueueLogger(None, diagnostic_prefix="debug-preflight yt-dlp"),
        "socket_timeout": 30,
    }
    apply_ytdlp_network_retry_policy(opts, source_analysis=True)
    ffmpeg = DownloadWorkerCore._find_ffmpeg()
    if ffmpeg:
        opts["ffmpeg_location"] = ytdlp_ffmpeg_location(ffmpeg)
    deno = DownloadWorkerCore._find_deno()
    write_diagnostic(f"debug-preflight runtime path: ffmpeg={ffmpeg}")
    write_diagnostic(f"debug-preflight runtime path: deno={deno}")
    apply_youtube_runtime_options(opts, deno_path=deno)
    if deno:
        write_diagnostic("debug-preflight Deno/bundled-EJS enabled")
    else:
        write_diagnostic("debug-preflight Deno/EJS disabled: no deno runtime found")
    log_options("debug-preflight", opts)

    def analyze_source_formats() -> dict[str, Any] | None:
        write_diagnostic("debug-preflight analysis start")

        def extract() -> Any:
            with ytdlp_module.YoutubeDL(opts) as ydl:
                return ydl.extract_info(normalized_url, download=False)

        extracted = run_with_bounded_transient_retries(
            lambda: run_tracked_ytdlp_operation(extract),
            on_retry=lambda attempt, maximum, delay, exc: write_diagnostic(
                source_analysis_retry_message(
                    "debug-preflight source analysis",
                    attempt,
                    maximum,
                    delay,
                    exc,
                )
            ),
        )
        write_diagnostic("debug-preflight analysis completed")
        return extracted if isinstance(extracted, dict) else None

    try:
        info = run_cancellable_blocking_step(
            analyze_source_formats,
            lambda: False,
            timeout_seconds=ANALYSIS_TIMEOUT_SECONDS,
            poll_seconds=ANALYSIS_POLL_SECONDS,
            label="YouTube source analysis",
            on_wait=lambda elapsed: write_diagnostic(
                f"debug-preflight analysis still running after {elapsed:.0f}s"
            ),
        )
    except Exception as exc:  # noqa: BLE001 - debug preflight reports the full provider boundary
        write_diagnostic(f"debug-preflight failed: {type(exc).__name__}: {exc}")
        print(f"DEBUG_PREFLIGHT_FAILED: {type(exc).__name__}: {exc}")
        print(f"Diagnostics log: {DIAGNOSTICS_LOG_PATH}")
        return 1
    video_infos = iter_video_infos(info) if isinstance(info, dict) else []
    video_count = len(video_infos)
    format_count = len(info.get("formats") or []) if isinstance(info, dict) else 0
    write_diagnostic(
        f"debug-preflight success: id={(info or {}).get('id') if isinstance(info, dict) else None} videos={video_count} formats={format_count}"
    )
    print(f"DEBUG_PREFLIGHT_OK videos={video_count} formats={format_count}")
    for video_info in video_infos:
        try:
            plan = build_auto_export_plan(
                video_info, mode=ExportMode.AUTO_CBR, max_height=DEFAULT_MAX_HEIGHT
            )
        except Exception as exc:  # noqa: BLE001 - debug probe reports each provider failure
            print(
                f"DEBUG_PREFLIGHT_SELECTION_FAILED id={video_info.get('id') or 'unknown'}: {type(exc).__name__}: {exc}"
            )
            continue
        exposed_heights = [
            height
            for fmt in video_info.get("formats") or []
            if isinstance(fmt, dict)
            and isinstance(height := fmt.get("height"), int)
            and not _is_none_codec(fmt.get("vcodec"))
        ]
        print(
            f"DEBUG_PREFLIGHT_SELECTION id={video_info.get('id') or 'unknown'} "
            f"exposed_max_height={max(exposed_heights) if exposed_heights else 'unknown'} "
            f"selected={plan.format_selector} output={plan.output_width or 'unknown'}x{plan.output_height or 'unknown'}"
        )
        try:
            audio_plan = build_mp3_export_plan(video_info)
        except Exception as exc:  # noqa: BLE001 - debug probe reports each provider failure
            print(
                f"DEBUG_PREFLIGHT_AUDIO_FAILED id={video_info.get('id') or 'unknown'}: {type(exc).__name__}: {exc}"
            )
        else:
            print(
                f"DEBUG_PREFLIGHT_AUDIO id={video_info.get('id') or 'unknown'} "
                f"selected={audio_plan.format_selector} source_codec={audio_plan.audio_codec} "
                f"source_kbps={audio_plan.source_audio_kbps:.0f} target_kbps={audio_plan.audio_bitrate_kbps}"
            )
    print(f"Diagnostics log: {DIAGNOSTICS_LOG_PATH}")
    return 0


def _runtime_smoke_output(message: str) -> None:
    """Report smoke results even when a Windows windowed build has no console."""
    write_diagnostic(message)
    stream = getattr(sys, "stdout", None)
    if stream is not None:
        print(message, file=stream, flush=True)


def _smoke_ytdlp_stack() -> tuple[str, str, tuple[str, ...]]:
    """Import the pinned extractor stack and prove its packaged solver data is readable."""
    ytdlp_module = load_yt_dlp()
    if ytdlp_module is None:
        raise RuntimeError(f"yt-dlp import failed: {YTDLP_IMPORT_ERROR}")
    ytdlp_version = str(getattr(ytdlp_module.version, "__version__", "unknown"))
    if _normalized_numeric_version(ytdlp_version) != _normalized_numeric_version(
        PINNED_YTDLP_VERSION
    ):
        raise RuntimeError(
            f"yt-dlp version {ytdlp_version} does not match pinned {PINNED_YTDLP_VERSION}"
        )

    ejs_module = importlib.import_module("yt_dlp_ejs")
    ejs_version = str(getattr(ejs_module, "version", "unknown"))
    if _normalized_numeric_version(ejs_version) != _normalized_numeric_version(
        PINNED_YTDLP_EJS_VERSION
    ):
        raise RuntimeError(
            f"yt-dlp-ejs version {ejs_version} does not match pinned {PINNED_YTDLP_EJS_VERSION}"
        )

    resources_module = importlib.import_module("importlib.resources")
    solver_root = resources_module.files("yt_dlp_ejs.yt.solver")
    verified_resources: list[str] = []
    for resource_name in YTDLP_EJS_SOLVER_RESOURCES:
        resource = solver_root.joinpath(resource_name)
        if not resource.is_file() or not resource.read_bytes():
            raise RuntimeError(
                f"yt-dlp-ejs solver resource is missing or empty: {resource_name}"
            )
        verified_resources.append(resource_name)
    return ytdlp_version, ejs_version, tuple(verified_resources)


def _smoke_impersonation_targets() -> tuple[str, ...]:
    """Prove the bundled TLS backend loads and exposes real browser targets."""
    module = load_yt_dlp()
    if module is None:
        raise RuntimeError("yt-dlp unavailable")
    with module.YoutubeDL({"quiet": True}) as downloader:
        targets = tuple(
            str(target)
            for target, handler in downloader._get_available_impersonate_targets()
            if handler == "curl_cffi"
        )
    if not targets:
        raise RuntimeError("curl_cffi exposes no impersonation targets")
    return targets


def runtime_smoke(*, require_libvlc: bool = False) -> int:
    """Verify packaged dependencies without opening the GUI or fetching media."""
    try:
        context = update_ssl_context()
        if context.cert_store_stats()["x509_ca"] < 50:
            raise RuntimeError("Bundled update certificate roots are incomplete")
    except Exception as exc:  # noqa: BLE001 - packaged smoke reports dependency failure
        _runtime_smoke_output(f"update-tls=failed error={type(exc).__name__}")
        return 1
    _runtime_smoke_output("update-tls=verified-roots")
    runtimes = {
        "ffmpeg": DownloadWorkerCore._find_ffmpeg(),
        "ffprobe": DownloadWorkerCore._find_ffprobe(),
        "deno": DownloadWorkerCore._find_deno(),
    }
    _runtime_smoke_output(
        f"VODFORGE_RUNTIME_SMOKE version={__version__} "
        f"platform={sys.platform} frozen={bool(getattr(sys, 'frozen', False))}"
    )
    failures: list[str] = []
    for name, path in runtimes.items():
        if not path:
            _runtime_smoke_output(f"{name}=missing")
            failures.append(name)
            continue
        try:
            version = probe_runtime_version(name, path)
        except Exception as exc:  # noqa: BLE001 - smoke probe must receipt any runtime failure
            _runtime_smoke_output(
                f"{name}={path} execution_failed={type(exc).__name__}: {exc}"
            )
            failures.append(name)
        else:
            _runtime_smoke_output(f"{name}={path} version={version}")
    if require_libvlc:
        libvlc_runtime = find_libvlc_runtime()
        if libvlc_runtime is None:
            _runtime_smoke_output("libvlc=missing")
            failures.append("libvlc")
        else:
            try:
                libvlc_version = probe_libvlc_runtime(libvlc_runtime)
            except Exception as exc:  # noqa: BLE001 - smoke probe must receipt native failure
                _runtime_smoke_output(
                    f"libvlc={libvlc_runtime.root} execution_failed={type(exc).__name__}: {exc}"
                )
                failures.append("libvlc")
            else:
                _runtime_smoke_output(
                    f"libvlc={libvlc_runtime.root} version={libvlc_version}"
                )
    try:
        ytdlp_version, ejs_version, solver_resources = _smoke_ytdlp_stack()
    except Exception as exc:  # noqa: BLE001 - smoke probe must receipt any provider-stack failure
        _runtime_smoke_output(f"yt-dlp-stack=failed error={type(exc).__name__}: {exc}")
        failures.append("yt-dlp-stack")
    else:
        _runtime_smoke_output(
            f"yt-dlp={ytdlp_version} yt-dlp-ejs={ejs_version} "
            f"solver_resources={','.join(solver_resources)}"
        )
    try:
        targets = _smoke_impersonation_targets()
    except Exception as exc:  # noqa: BLE001 - packaged capability probe reports missing native dependencies
        _runtime_smoke_output(f"impersonation=failed error={type(exc).__name__}: {exc}")
        failures.append("impersonation")
    else:
        _runtime_smoke_output(f"impersonation=curl_cffi targets={len(targets)}")
    _runtime_smoke_output(f"diagnostics={DIAGNOSTICS_LOG_PATH}")
    if failures:
        _runtime_smoke_output(
            f"VODFORGE_RUNTIME_SMOKE_FAILED dependencies={','.join(failures)}"
        )
        return 1
    _runtime_smoke_output("VODFORGE_RUNTIME_SMOKE_OK")
    return 0


def _normalized_numeric_version(value: object) -> tuple[int, ...] | None:
    try:
        return tuple(int(component) for component in str(value).split("."))
    except (TypeError, ValueError):
        return None
