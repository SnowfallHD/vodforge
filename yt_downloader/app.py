from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
import queue
import re
import shutil

# Reviewed subprocess call sites use fixed argv lists and never invoke a shell.
import subprocess  # nosec B404
import sys
import threading
import time
import tkinter as tk
import unicodedata
import urllib.error
import urllib.parse
import uuid
import warnings
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from typing import Any

from . import export_planning as _export_planning
from . import platform_services as _platform_services
from . import ui_layout as _ui_layout
from . import ui_widgets as _ui_widgets
from .cloud_funnel import (
    InstallationIdentityError,
    InstallationState,
    cloud_page_url,
    installation_state_path,
    load_or_create_installation_state,
    record_cloud_click,
    record_cloud_seen,
    record_first_launch,
)
from .export_planning import (
    DEFAULT_MAX_HEIGHT,
    EXPORT_MODES,
    QUALITY_OPTIONS,
    _is_hdr_format,
    _is_none_codec,
    apply_manual_export_settings,
    build_auto_export_plan,
    build_mp3_export_plan,
    export_mode_description,
    export_mode_display_name,
    export_mode_from_display_name,
    mp3_sample_rate_display,
)
from .focus_settings import (
    FocusSettingsActions,
    FocusSettingsBindings,
    FocusSettingsDialog,
    FocusSettingsOptions,
)
from .history import (
    HistoryError,
    application_data_dir,
    history_file_path,
    history_identity,
    history_output_dir,
    load_history,
    sanitize_durable_text,
    sanitize_durable_thumbnail_record,
    sanitize_durable_url,
    sanitize_run_activity,
    save_history,
    upsert_history,
)
from .library_state import (
    ACTIVE_METADATA_RUN_ID_KEY,
    LibraryRemovalPlan,
    claim_active_metadata_row,
    format_duration,
    is_metadata_preview,
    merge_library_metadata_items,
    metadata_output_type,
    metadata_run_key,
    persisted_run_deck_records,
    resolve_library_removal_plan,
)
from .models import (
    AUDIO_CHANNELS,
    AUDIO_SAMPLE_RATE,
    STRICT_AUDIO_BITRATE_KBPS,
    STRICT_VIDEO_BITRATE_KBPS,
    AudioExportPlan,
    CookieSource,
    DownloadJob,
    DownloadOutcome,
    ExportMode,
    ExportPlan,
    ManualAudioCodec,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)
from .output_validation import (
    output_artifact_plan_mismatches as _output_artifact_plan_mismatches,
)
from .output_validation import validate_output_artifact as _validate_output_artifact
from .platform_services import (
    choose_output_directory,
    configure_windows_app_identity,
    diagnostics_dir,
    find_runtime_executable,
    focus_view_shortcut_bindings,
    hidden_window_subprocess_kwargs,
    is_macos,
    is_windows,
    output_directory_failure_guidance,
    probe_runtime_version,
    runtime_window_icon_asset,
)
from .platform_services import (
    open_path as open_system_path,
)
from .private_files import open_private_text_file, write_private_bytes
from .quality_e2e import (
    QualityE2EAttestationError,
    quality_e2e_mode_enabled,
    write_quality_e2e_library_visibility_receipt,
    write_quality_e2e_startup_attestation,
)
from .safe_output import (
    cleanup_private_staging_directory,
    commit_file_beneath,
    create_private_staging_directory,
)
from .thumbnail_network import ThumbnailUrlPolicy, download_bounded_url_bytes
from .ui_events import (
    UiEvent,
    UiEventHandlersMixin,
    UiEventSink,
    history_record_event,
    installation_result_event,
    job_info_event,
    job_log_event,
    thumbnail_preview_event,
)
from .ui_layout import (
    FOCUS_LIBRARY_SELECTED_DESCRIPTION_VISIBLE_LINES,
    FOCUS_LIBRARY_SELECTED_DETAILS_HEIGHT,
    FOCUS_LIBRARY_SELECTED_OVERVIEW_HEIGHT,
    FOCUS_LIBRARY_SELECTED_TAGS_MAX_HEIGHT,
    FOCUS_LIBRARY_SELECTED_TAGS_MAX_VISIBLE_LINES,
    bounded_window_size,
    centered_toplevel_geometry,
    ellipsize_wrapped_text,
    focus_hero_thumbnail_visible,
    focus_layout_mode,
    focus_library_horizontal_padding,
    focus_library_layout_mode,
    focus_library_vertical_layout_mode,
    focus_run_deck_capacity,
    initial_window_geometry,
    library_thumbnail_size,
    measured_wrapped_line_count,
    rounded_canvas_rectangle_points,
    selected_description_max_height,
    selected_overview_height,
    selected_overview_line_budget,
    thumbnail_size_within,
    youtube_thumbnail_size,
)
from .ui_theme import (
    FONT_MONO,
    FONT_MONO_FAMILY,
    FONT_TITLE,
    FONT_UI,
    FONT_UI_FAMILY,
    FONT_UI_MEDIUM,
    FONT_UI_SMALL,
    FONT_UI_SMALL_MEDIUM,
    THEME,
)
from .ui_widgets import (
    PillAction,
    PixelScrollTable,
    RoundedIconButton,
    SegmentedSelector,
    SleekProgressbar,
    SleekScrollbar,
    ToolTip,
    _focus_library_table_item,
    bind_smooth_vertical_wheel,
    reveal_toplevel,
    set_user_scroll_locked,
)
from .updates import (
    MacUpdatePlan,
    ReleaseInfo,
    cleanup_stale_macos_updates,
    download_verified_update,
    fetch_latest_release,
    is_newer_release,
    launch_macos_update,
    prepare_macos_update,
    release_asset_for_platform,
    running_macos_app,
    verify_windows_authenticode,
)
from .version import __version__

# Compatibility re-exports keep the long-standing ``yt_downloader.app``
# helper surface stable while implementation ownership moves to focused UI
# modules.
accumulated_row_scroll = _ui_layout.accumulated_row_scroll
focus_wheel_pixels = _ui_layout.focus_wheel_pixels
pixel_scroll_target = _ui_layout.pixel_scroll_target
pixel_table_visible_row_window = _ui_layout.pixel_table_visible_row_window
resized_table_column_width = _ui_layout.resized_table_column_width
responsive_table_stretch_indices = _ui_layout.responsive_table_stretch_indices
stretched_table_column_widths = _ui_layout.stretched_table_column_widths
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
TOOLTIP_DELAY_MS = _ui_widgets.TOOLTIP_DELAY_MS
TOOLTIP_POINTER_POLL_MS = _ui_widgets.TOOLTIP_POINTER_POLL_MS
_TooltipController = _ui_widgets._TooltipController
pointer_inside_widget_bounds = _ui_widgets.pointer_inside_widget_bounds
touchpad_scroll_deltas = _ui_widgets.touchpad_scroll_deltas

try:
    from PIL import Image, ImageDraw, ImageOps, ImageTk
except Exception:  # noqa: BLE001  # pragma: no cover - optional rendering boundary
    Image = None
    ImageDraw = None
    ImageOps = None
    ImageTk = None

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
MP3_CHANNEL_OPTIONS = {
    "Preserve source": None,
    "Stereo": "2",
    "Mono": "1",
}
MP3_COVER_ART_OPTIONS = ("No Art", "YouTube art", "Custom art")
DEFAULT_IGNORE_PLAYLISTS = True
BACKEND_TEMP_OUTPUT_NAME = "__vodforge-tmp.mp4"
BACKEND_ORIGINAL_BACKUP_NAME = "__vodforge-original.mp4"
AUTO_UPDATE_INITIAL_DELAY_MS = 5_000
AUTO_UPDATE_INTERVAL_MS = 6 * 60 * 60 * 1_000
AUTO_UPDATE_BUSY_RETRY_MS = 10 * 60 * 1_000
THUMBNAIL_CACHE_MAX_ITEMS = 1000
CUSTOM_COVER_MAX_INPUT_BYTES = 50 * 1024 * 1024
CUSTOM_COVER_MAX_PIXELS = 50_000_000
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
_ACTIVE_CHILD_PROCESSES: set[Any] = set()
_ACTIVE_CHILD_PROCESS_LOCK = threading.RLock()
_CHILD_TERMINATION_LOCK = threading.RLock()
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
    items: list[dict[str, Any]],
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
        enriched["vodforge_output_type"] = OutputType.MP3.value
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
            "Output container": "mp3",
            "Output rate-control mode": "CBR",
            "Output audio codec": "MP3 (libmp3lame)",
            "Target audio bitrate": f"{plan.audio_bitrate_kbps} kbps",
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
        "Target video bitrate": f"{plan.video_bitrate_kbps} kbps",
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
        "Measured audio bitrate": _format_bits_per_second_as_kbps(
            audio.get("bit_rate")
        ),
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
    (
        "Effective/target video bitrate",
        "Effective H.264-equivalent video bitrate",
        "Target video bitrate",
    ),
    (
        "Effective/target audio bitrate",
        "Effective AAC-equivalent audio bitrate",
        "Target audio bitrate",
    ),
    ("Selection/status", "Reason selected", "Validation status"),
]

AUDIO_SUMMARY_COMPARISON_ROWS = [
    ("Format selector", "Source format selector used", None),
    ("Audio format ID", "Audio format ID", None),
    ("Container/ext", "Source container/ext", "Output container"),
    ("Audio codec", "Source audio codec", "Output audio codec"),
    ("Audio bitrate", "Source audio bitrate", "Measured audio bitrate"),
    ("Audio sample rate", "Source audio sample rate", "Audio sample rate"),
    ("Audio channels", "Source audio channels", "Audio channels"),
    ("File size", "File size estimate", "Output file size"),
    (
        "Effective/target audio bitrate",
        "Effective MP3-equivalent audio bitrate",
        "Target audio bitrate",
    ),
    ("Selection/status", "Reason selected", "Validation status"),
]


# Keep source/output comparisons visually traceable without turning the summaries
# into a high-saturation legend. Only the label token is tinted; values retain the
# normal text color so codec names, paths, and measurements remain easy to read.
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
        if metadata_output_type(info) == OutputType.MP3
        else SUMMARY_COMPARISON_ROWS
    )
    for label, source_key, output_key in rows:
        source_lines.append(
            f"{label}: {_display_value(source.get(source_key), 'Not available')}"
        )
        if output_key is not None:
            output_lines.append(
                f"{label}: {_display_value(output.get(output_key), 'Not available')}"
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
    else:
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


def _windows_safe_component(value: Any, fallback: str, max_len: int = 80) -> str:
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
    if len(safe.encode("utf-16-le")) // 2 > max_len:
        kept: list[str] = []
        used_units = 0
        for character in safe:
            units = len(character.encode("utf-16-le")) // 2
            if used_units + units > max(1, max_len - 1):
                break
            kept.append(character)
            used_units += units
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
    # _windows_safe_component appends an ellipsis after truncating, so reserve
    # one extra character to keep the final user-facing folder within 96 chars.
    title_max_len = max(1, 95 - len(suffix))
    title = _windows_safe_component(info.get("title"), "video", max_len=title_max_len)
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


def compact_video_folder_name(info: dict[str, Any], max_title_len: int) -> str:
    video_id = _windows_safe_component(info.get("id"), "", max_len=32)
    suffix = f" [{video_id}]" if video_id else ""
    title_text = _clean_windows_component_text(info.get("title"), "video")
    title_safe = "".join(
        ch if ch not in '<>:"/\\|?*\0' else "_" for ch in title_text
    ).strip(" .")
    title_safe = " ".join(title_safe.split()) or "video"
    if len(title_safe) > max_title_len:
        words: list[str] = []
        used = 0
        for word in title_safe.split():
            next_used = used + len(word) + (1 if words else 0)
            if words and next_used > max_title_len:
                break
            if not words and len(word) > max_title_len:
                words.append(word[: max(1, max_title_len)].rstrip(" ._-…"))
                break
            words.append(word)
            used = next_used
        title_safe = " ".join(words).rstrip(" ._-…") + "…"
    return f"{title_safe}{suffix}"


def legacy_shallow_video_output_dir(output_dir: Path, info: dict[str, Any]) -> Path:
    """Locate the v0.1.5 ID-only fallback without creating new opaque paths."""
    video_id = _windows_safe_component(info.get("id"), "video", max_len=32)
    return output_dir / channel_folder_name(info) / "path-safe videos" / video_id


def compact_video_output_dir(
    output_dir: Path, info: dict[str, Any], target_file_name: str
) -> Path:
    has_playlist = bool(info.get("playlist_title") or info.get("playlist_id"))
    channel_limit = 80
    playlist_limit = 80
    title_limit = 80
    while True:
        channel = _windows_safe_component(
            info.get("channel")
            or info.get("uploader")
            or info.get("channel_id")
            or "Unknown Channel",
            "Unknown Channel",
            max_len=channel_limit,
        )
        parent = output_dir / channel
        if has_playlist:
            playlist = _windows_safe_component(
                info.get("playlist_title") or info.get("playlist_id") or "Playlist",
                "Playlist",
                max_len=playlist_limit,
            )
            parent = parent / "playlists" / playlist
        else:
            parent = parent / "videos - no playlist"
        candidate = parent / compact_video_folder_name(info, title_limit)
        if not _path_would_exceed_windows_safe_limit(candidate / target_file_name):
            return candidate
        if title_limit > 4:
            name, current, minimum = "title", title_limit, 4
        elif has_playlist and playlist_limit > 16:
            name, current, minimum = "playlist", playlist_limit, 16
        elif channel_limit > 16:
            name, current, minimum = "channel", channel_limit, 16
        else:
            raise ValueError(
                "The selected output folder is too deep for a Windows-compatible media path. "
                "Choose a shorter output folder and try again."
            )
        updated = max(minimum, current - 4)
        if name == "title":
            title_limit = updated
        elif name == "playlist":
            playlist_limit = updated
        else:
            channel_limit = updated


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
    for parent in {canonical.parent, legacy.parent}:
        try:
            for child in parent.iterdir():
                if child.is_dir() and suffix and child.name.endswith(suffix):
                    add(child)
        except OSError:
            continue
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


def _validate_existing_output_candidate(
    path: Path,
    ffprobe: str,
    requirements: ExistingOutputRequirements,
    *,
    control_check: Callable[[], None] | None,
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
            control_check=control_check,
        )
    except Exception as exc:  # noqa: BLE001 - any invalid candidate must fail closed
        # Validation is cancellable. Recheck the canonical control boundary
        # before classifying the exception as an invalid artifact and scanning on.
        if control_check is not None:
            control_check()
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
    extension = ".mp3" if output_type == OutputType.MP3 else ".mp4"
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
            if not path.is_file():
                continue
            probe_data = _validate_existing_output_candidate(
                path,
                ffprobe,
                requirements,
                control_check=control_check,
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
        require_sidecar=True,
    )


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
        if line.startswith(("http://", "https://")):
            urls.append(line)
    return urls


def read_url_list_file(path: Path) -> list[str]:
    return parse_url_list_text(path.read_text(encoding="utf-8-sig"))


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


def staging_output_template(staging_dir: Path) -> str:
    # yt-dlp writes only into this per-job staging directory. Final user-facing
    # folders are created later from extracted metadata, so old downloads are
    # never scanned or moved.
    return str(staging_dir / "%(id)s.%(ext)s")


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
        "thumbnail": sanitize_durable_url(
            info.get("thumbnail") or (thumb or {}).get("url"),
            preserve_youtube_context=False,
        ),
        "best_thumbnail": sanitize_durable_thumbnail_record(thumb),
        "vodforge_output_type": metadata_output_type(info).value,
        "vodforge_encoding_summary": info.get("vodforge_encoding_summary"),
    }
    return {
        key: value for key, value in compact.items() if value not in (None, "", [], {})
    }


def write_compact_video_metadata(
    output_dir: Path, info: dict[str, Any], extra_tags: list[str]
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / safe_metadata_filename(info)
    path.write_text(
        json.dumps(
            compact_video_metadata(info, extra_tags), ensure_ascii=False, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def write_all_compact_video_metadata(
    output_dir: Path, info: dict[str, Any], extra_tags: list[str]
) -> list[Path]:
    paths: list[Path] = []
    for video in iter_video_infos(info):
        paths.append(
            write_compact_video_metadata(
                video_output_dir(output_dir, video), video, extra_tags
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


def video_file_name(info: dict[str, Any], ext: str, *, max_title_len: int = 120) -> str:
    title = _windows_safe_component(info.get("title"), "video", max_len=max_title_len)
    return f"{title}{ext}"


def resolved_video_output_target(
    output_dir: Path, info: dict[str, Any], ext: str
) -> tuple[Path, str]:
    """Allocate one path budget while preserving the canonical hierarchy."""
    primary = video_output_dir(output_dir, info)
    for title_limit in range(120, 23, -4):
        target_file_name = video_file_name(info, ext, max_title_len=title_limit)
        if not _path_would_exceed_windows_safe_limit(primary / target_file_name):
            return primary, target_file_name
    for title_limit in range(120, 23, -4):
        target_file_name = video_file_name(info, ext, max_title_len=title_limit)
        try:
            compact = compact_video_output_dir(output_dir, info, target_file_name)
        except ValueError:
            continue
        if not _path_would_exceed_windows_safe_limit(compact / target_file_name):
            return compact, target_file_name
    raise ValueError(
        "The selected output folder is too deep for a Windows-compatible media path. "
        "Choose a shorter output folder and try again."
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
        target_dir, target_file_name = resolved_video_output_target(
            output_dir, video, ext
        )
        target = target_dir / target_file_name
        # Commit relative to a freshly verified directory handle so metadata-
        # derived path components cannot follow a pre-existing symlink outside
        # the selected destination. Existing output remains intact on failure.
        commit_file_beneath(
            staged,
            output_dir,
            target,
            control_check=control_check,
        )
        remember_video_output_dir(video, target_dir)
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
    audio_codec: ManualAudioCodec = ManualAudioCodec.AAC,
    x264_preset: str = "medium",
    use_nvenc: bool = False,
    preserve_attached_picture: bool = False,
    preserve_metadata: bool | None = None,
) -> list[str]:
    """Return the constrained-CBR command for one calculated MP4 export plan."""
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
            "p4",
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
            "nal-hrd=cbr:force-cfr=1",
        ]
    )
    primary_video_map = "0:V:0" if preserve_attached_picture else "0:v:0"
    map_args = ["-map", primary_video_map, "-map", "0:a:0?"]
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
    return [
        ffmpeg,
        "-y",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-i",
        str(source),
        *map_args,
        *video_args,
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
        "format=format_name,size,duration:format_tags:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,bit_rate,pix_fmt,profile,sample_rate,channels:stream_disposition",
        str(path),
    ]
    if control_check is None:
        # The media path is one argv entry; no provider metadata becomes a command string.
        result = subprocess.run(  # nosec B603
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            **process_options,
        )
    else:
        result = run_cancellable_process_capture(
            command,
            timeout_seconds=timeout_seconds,
            control_check=control_check,
            check=True,
            **process_options,
        )
    data = json.loads(result.stdout or "{}")
    if not isinstance(data, dict):
        raise RuntimeError(  # noqa: TRY004 - provider protocol failures use RuntimeError
            "ffprobe returned an invalid top-level result"
        )
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
    """Stop a child process without leaving an encoder writing after cleanup."""
    with _CHILD_TERMINATION_LOCK:
        poll = getattr(process, "poll", None)
        if callable(poll) and poll() is not None:
            return
        try:
            process.terminate()
        except Exception as exc:  # noqa: BLE001 - process adapters may raise provider-specific errors
            write_diagnostic(
                f"child process terminate request failed: {type(exc).__name__}"
            )
        try:
            process.wait(timeout=timeout_seconds)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            process.kill()
        except Exception as exc:  # noqa: BLE001 - process adapters may raise provider-specific errors
            write_diagnostic(f"child process kill request failed: {type(exc).__name__}")
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "Child process did not stop after terminate and kill requests"
            ) from exc


def register_active_child_process(process: Any) -> None:
    with _ACTIVE_CHILD_PROCESS_LOCK:
        _ACTIVE_CHILD_PROCESSES.add(process)


def unregister_active_child_process(process: Any) -> None:
    with _ACTIVE_CHILD_PROCESS_LOCK:
        _ACTIVE_CHILD_PROCESSES.discard(process)


def child_process_has_exited(process: Any, *, confirmed_exited: bool = False) -> bool:
    if confirmed_exited:
        return True
    poll = getattr(process, "poll", None)
    return bool(callable(poll) and poll() is not None)


def finalize_active_child_process(
    process: Any, *, confirmed_exited: bool = False
) -> bool:
    """Release process ownership only after exit is positively confirmed.

    If an exceptional path leaves a child alive, retain it in the registry so
    application-close cleanup can retry instead of losing ownership of a writer.
    """
    if child_process_has_exited(process, confirmed_exited=confirmed_exited):
        unregister_active_child_process(process)
        return True
    try:
        terminate_and_reap_process(process)
    except Exception as exc:  # noqa: BLE001 - cleanup retains unconfirmed child ownership
        write_diagnostic(
            f"active child process remains live after cleanup attempt: {type(exc).__name__}: {exc}"
        )
    if child_process_has_exited(process):
        unregister_active_child_process(process)
        return True
    write_diagnostic(
        "active child process remains registered because exit could not be confirmed"
    )
    return False


def terminate_all_active_child_processes(
    *, deadline_monotonic: float | None = None
) -> None:
    with _ACTIVE_CHILD_PROCESS_LOCK:
        active = tuple(_ACTIVE_CHILD_PROCESSES)
    for process in active:
        timeout_seconds: float = PROCESS_TERMINATE_TIMEOUT_SECONDS
        if deadline_monotonic is not None:
            remaining = deadline_monotonic - time.monotonic()
            if remaining <= 0:
                write_diagnostic(
                    "active child process cleanup deadline reached before every child was reaped"
                )
                break
            timeout_seconds = max(0.01, min(timeout_seconds, remaining / 2))
        try:
            terminate_and_reap_process(process, timeout_seconds=timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - shutdown must continue across child adapters
            write_diagnostic(
                f"active child process cleanup failed: {type(exc).__name__}: {exc}"
            )
        finally:
            poll = getattr(process, "poll", None)
            if callable(poll) and poll() is not None:
                unregister_active_child_process(process)


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
    """Run one serialized yt-dlp operation with all of its imported Popen aliases tracked."""
    with _YTDLP_SUBPROCESS_TRACKING_LOCK:
        utils_module = importlib.import_module("yt_dlp.utils")
        original_class = utils_module.Popen
        tracked_class = tracked_ytdlp_popen_class(original_class, control_check)
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
            if control_check is not None:
                control_check()
            return step()
        finally:
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
    failure_prefix = f"VODForge H.264/{audio_codec_label} CBR transcode failed"

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
) -> Path | None:
    thumb = best_thumbnail_for_download(info)
    url = str((thumb or {}).get("url") or "")
    if not url:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    data = download_bounded_url_bytes(url, source_url=source_url)
    if Image is None:
        if len(data) > THUMBNAIL_MAX_BYTES:
            raise RuntimeError(
                "Pillow is required to enforce the 300 KB thumbnail limit"
            )
        path.write_bytes(data)
        return path
    image = decode_bounded_thumbnail(data).convert("RGB")
    _save_jpeg_under_size(image, path)
    return path


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
) -> Path | None:
    path = cached_thumbnail_path(info, data_dir=data_dir)
    if path is None:
        return None
    with thumbnail_cache_lock(path):
        try:
            if path.is_file() and 0 < path.stat().st_size <= THUMBNAIL_MAX_BYTES:
                if Image is not None:
                    cached_image = decode_bounded_thumbnail(path.read_bytes())
                    cached_image.close()
                path.touch(exist_ok=True)
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
                return None
            if Image is not None:
                cached_image = decode_bounded_thumbnail(saved.read_bytes())
                cached_image.close()
            os.replace(saved, path)
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
) -> Path | None:
    """Make a user-selected cover the canonical private artwork for one item."""
    destination = cached_thumbnail_path(info, data_dir=data_dir)
    if destination is None:
        return None
    source_path = validate_custom_cover_art(source_path)
    if Image is None or ImageOps is None:
        raise RuntimeError("Pillow is required to cache custom cover art.")
    with thumbnail_cache_lock(destination):
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
            prune_thumbnail_cache(destination.parent)
            return destination
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def validate_custom_cover_art(path: Path) -> Path:
    """Validate a user-selected local cover image before it enters FFmpeg."""
    candidate = Path(path).expanduser()
    if not candidate.is_file():
        raise ValueError("Choose an existing cover image file.")
    try:
        if candidate.stat().st_size > CUSTOM_COVER_MAX_INPUT_BYTES:
            raise ValueError("Custom cover art must be 50 MB or smaller.")
    except OSError as exc:
        raise ValueError(f"VODForge could not read that cover image: {exc}") from exc
    if Image is None:
        raise ValueError("Pillow is required to validate custom cover art.")
    try:
        with Image.open(candidate) as source:
            width, height = source.size
            if width <= 0 or height <= 0 or width * height > CUSTOM_COVER_MAX_PIXELS:
                raise ValueError("Custom cover art dimensions are too large.")
            source.verify()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Choose a valid JPEG, PNG, or WebP cover image.") from exc
    return candidate.resolve(strict=False)


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


COOKIE_BROWSER_PLACEHOLDER = "Choose a browser"
COOKIE_BROWSER_OPTIONS = [
    COOKIE_BROWSER_PLACEHOLDER,
    "Chrome",
    "Edge",
    "Firefox",
    "Brave",
    "Chromium",
    "Opera",
    "Vivaldi",
]
COOKIE_SOURCE_OPTIONS = tuple(source.value for source in CookieSource)
COOKIE_BROWSER_VALUES = {
    "Chrome": "chrome",
    "Edge": "edge",
    "Firefox": "firefox",
    "Brave": "brave",
    "Chromium": "chromium",
    "Opera": "opera",
    "Vivaldi": "vivaldi",
}
WINDOWS_CHROMIUM_COOKIE_BROWSERS = {
    "brave",
    "chrome",
    "chromium",
    "edge",
    "opera",
    "vivaldi",
}
WINDOWS_CHROMIUM_COOKIE_MESSAGE = (
    "Chrome/Edge/Brave/Chromium browser-cookie import is unreliable on Windows because Chromium locks its cookie database. "
    "Choose cookies.txt with an exported YouTube cookies.txt file, choose Firefox browser cookies under Browser, or switch YouTube access to Public."
)


def download_job_display_title(job: DownloadJob, *, queued: bool = False) -> str:
    """Return resolved run metadata or a neutral state, never a raw source URL."""
    title = str((job.preview_info or {}).get("title") or "").strip()
    if title:
        return title
    state = "Queued" if queued else "Preparing"
    media = "audio" if job.output_type == OutputType.MP3 else "video"
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
            f"{outcome.sidecar_failure_count} optional sidecar failure(s)."
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


def browser_cookie_value(label_or_value: str | None) -> str | None:
    text = str(label_or_value or "").strip()
    if not text or text.lower() in {"none", COOKIE_BROWSER_PLACEHOLDER.lower()}:
        return None
    return COOKIE_BROWSER_VALUES.get(text, text.lower())


def cookie_inputs_for_source(
    source: CookieSource | str,
    cookie_file: Path | None,
    cookie_browser: str | None,
) -> tuple[bool, Path | None, str | None]:
    """Resolve one explicit cookie source without leaking an inactive choice."""
    try:
        selected = (
            source if isinstance(source, CookieSource) else CookieSource(str(source))
        )
    except ValueError:
        selected = CookieSource.PUBLIC
    if selected == CookieSource.FILE:
        return True, cookie_file, None
    if selected == CookieSource.BROWSER:
        return True, None, browser_cookie_value(cookie_browser)
    return False, None, None


def windows_chromium_cookie_warning(
    cookie_browser: str | None, platform: str | None = None
) -> str | None:
    browser = browser_cookie_value(cookie_browser)
    if is_windows(platform) and browser in WINDOWS_CHROMIUM_COOKIE_BROWSERS:
        return WINDOWS_CHROMIUM_COOKIE_MESSAGE
    return None


def format_ytdlp_user_error(error: Any) -> str:
    message = str(error)
    lower = message.lower()
    if (
        "could not copy chrome cookie database" in lower
        or "github.com/yt-dlp/yt-dlp/issues/7271" in lower
    ):
        return f"{WINDOWS_CHROMIUM_COOKIE_MESSAGE}\n\nOriginal yt-dlp error: {message}"
    if "http error 503" in lower or "503: service unavailable" in lower:
        return (
            "YouTube returned HTTP 503 Service Unavailable after retries. This is usually temporary, rate-limit/CDN related, "
            "or a sign that YouTube wants authenticated cookies. Retry once; if it persists, choose cookies.txt under YouTube access with an exported "
            "YouTube cookies.txt file or Firefox browser cookies.\n\n"
            f"Original yt-dlp error: {message}"
        )
    if (
        "video unavailable" in lower
        or "this video is not available" in lower
        or "this content isn't available" in lower
    ):
        return (
            "YouTube reported this video as unavailable. Common causes:\n"
            "• The video is private, deleted, or region-restricted.\n"
            "• The video is marked 'for kids' and yt-dlp's fallback client cannot access it.\n"
            "• No JavaScript runtime (Deno 2.x) is installed, which limits which YouTube clients yt-dlp can use.\n"
            "Try: 1) Retry, 2) Install Deno 2.x, 3) Choose cookies.txt or Browser under YouTube access, 4) Verify the video plays in a browser.\n\n"
            f"Original yt-dlp error: {message}"
        )
    if "no video formats found" in lower or "no usable" in lower and "video" in lower:
        return (
            "yt-dlp could not find any downloadable video formats. This usually means:\n"
            "• No JavaScript runtime (Deno 2.x) is installed — YouTube returns very limited formats without one.\n"
            "• YouTube is rate-limiting the connection — try again later or use cookies.\n"
            "• The video requires authentication — choose cookies.txt under YouTube access and load an exported cookie file.\n\n"
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
            "YouTube is asking for sign-in confirmation (bot detection). Choose cookies.txt under YouTube access with an exported "
            "YouTube cookie file, or choose Browser to read an authorized local browser profile.\n\n"
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
    if job.output_type == OutputType.MP3:
        return build_mp3_export_plan(preflight_info, job.mp3_settings)
    plan = build_auto_export_plan(
        preflight_info,
        mode=job.export_mode,
        max_height=max_height,
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
            f"{label}: Manual Override settings {plan.video_bitrate_kbps} kbps video + "
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
                    f"{label}: MP3 target {plan.audio_bitrate_kbps} kbps CBR; cover art "
                    f"{'embedded' if plan.embed_cover_art else 'not embedded'}."
                ),
            )
        )
    else:
        target_label = (
            "Manual target"
            if job.export_mode == ExportMode.MANUAL_OVERRIDE
            else "Auto CBR target"
        )
        lines.extend(
            (
                (
                    f"{label}: selected video {plan.output_height}p {plan.video_codec} "
                    f"~{plan.source_video_kbps:.0f} kbps; selected audio {plan.audio_codec} "
                    f"~{plan.source_audio_kbps:.0f} kbps."
                ),
                (
                    f"{label}: {target_label} {plan.video_bitrate_kbps} kbps video + "
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


class DownloaderApp(UiEventHandlersMixin, tk.Tk):
    _event_app_name = APP_NAME
    _event_subtle_color = THEME["subtle"]
    video_tree: PixelScrollTable
    _focus_icon_images: dict[tuple[str, int, str], Any]
    _focus_run_list_close_after_id: str | None
    _focus_run_list_window: tk.Frame | None
    _focus_run_list_cleanup: Callable[[], None] | None

    def _event_write_diagnostic(self, message: str) -> None:
        write_diagnostic(message)

    def __init__(self) -> None:
        reset_diagnostics_log()
        prepare_activity_log()
        write_diagnostic(
            f"app start: name={APP_NAME} frozen={getattr(sys, 'frozen', False)} executable={sys.executable} argv={sys.argv}"
        )
        write_diagnostic(f"diagnostics log path: {DIAGNOSTICS_LOG_PATH}")
        write_diagnostic("yt-dlp import deferred until after the first window paint")
        try:
            configure_windows_app_identity()
        except (AttributeError, OSError) as exc:
            write_diagnostic(f"Windows taskbar identity could not be set: {exc}")
        super().__init__()
        self.title(APP_NAME)
        self._app_icon_image: tk.PhotoImage | None = None
        try:
            runtime_icon_asset = runtime_window_icon_asset()
            if runtime_icon_asset is None:
                write_diagnostic(
                    "macOS application icon uses the bundle CFBundleIconFile ICNS"
                )
            elif runtime_icon_asset.endswith(".ico"):
                self.iconbitmap(default=str(bundled_asset_path(runtime_icon_asset)))
            else:
                self._app_icon_image = tk.PhotoImage(
                    file=str(bundled_asset_path(runtime_icon_asset))
                )
                self.iconphoto(True, self._app_icon_image)
        except tk.TclError as exc:
            write_diagnostic(f"app icon could not be loaded: {exc}")
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        window_width, window_height = bounded_window_size(screen_width, screen_height)
        self.geometry(initial_window_geometry(screen_width, screen_height))
        self.minsize(min(820, window_width), min(560, window_height))
        # The window manager owns the top-level dimensions during a native
        # resize.  Responsive descendants may change their requested sizes at
        # breakpoints, but those requests must never move the opposite window
        # edge.  The explicit geometry above and subsequent Configure events
        # remain the sole size authority.
        self.pack_propagate(False)
        self.configure(bg=THEME["bg"])

        self.events: queue.Queue[UiEvent] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.active_job: DownloadJob | None = None
        self.pending_jobs: list[DownloadJob] = []
        self.update_worker: threading.Thread | None = None
        self.update_check_silent = False
        self.update_check_after_id: str | None = None
        self.cancel_requested = False
        self.skip_video_requested = False
        self.skip_url_requested = False
        self._closing = False
        self._close_terminator: threading.Thread | None = None
        self._close_deadline: float | None = None
        self.installation_state_path = installation_state_path()
        self.installation_state: InstallationState | None = None
        self._first_launch_worker: threading.Thread | None = None
        self._cloud_seen_worker: threading.Thread | None = None
        try:
            self.installation_state = load_or_create_installation_state(
                self.installation_state_path
            )
            write_diagnostic(
                "anonymous installation ID loaded from the VODForge application-data folder"
            )
        except (InstallationIdentityError, OSError) as exc:
            write_diagnostic(
                f"anonymous installation ID unavailable; Cloud funnel deduplication is disabled: {exc}"
            )

        self.url_var = tk.StringVar()
        self.url_list_file_var = tk.StringVar(value="No URL list loaded")
        self.batch_urls: list[str] = []
        self.output_var = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.output_type_var = tk.StringVar(value=OutputType.MP4.value)
        self.library_output_type_var = tk.StringVar(value=OutputType.MP4.value)
        self.quality_var = tk.StringVar(value="1080p Full HD")
        self.export_mode_var = tk.StringVar(value=ExportMode.AUTO_CBR.value)
        self.export_mode_choice_var = tk.StringVar(
            value=export_mode_display_name(ExportMode.AUTO_CBR)
        )
        self.export_mode_description_var = tk.StringVar(
            value=export_mode_description(ExportMode.AUTO_CBR)
        )
        self.manual_video_bitrate_var = tk.StringVar(
            value=str(STRICT_VIDEO_BITRATE_KBPS)
        )
        self.manual_audio_bitrate_var = tk.StringVar(
            value=str(STRICT_AUDIO_BITRATE_KBPS)
        )
        self.manual_audio_codec_var = tk.StringVar(value=ManualAudioCodec.AAC.value)
        self.manual_sample_rate_var = tk.StringVar(value=AUDIO_SAMPLE_RATE)
        self.manual_channels_var = tk.StringVar(value="Stereo")
        self.manual_preset_var = tk.StringVar(value="medium")
        self.mp3_quality_var = tk.StringVar(value="Maximum — 320 kbps CBR")
        self.mp3_sample_rate_var = tk.StringVar(value="Preserve source")
        self.mp3_channels_var = tk.StringVar(value="Preserve source")
        self.mp3_embed_metadata_var = tk.BooleanVar(value=True)
        self.mp3_cover_art_mode_var = tk.StringVar(value=MP3_COVER_ART_OPTIONS[0])
        self.mp3_custom_cover_art_path: Path | None = None
        self.mp3_custom_cover_art_var = tk.StringVar(
            value="Select Custom art to choose an image"
        )
        self.mp3_cover_art_description_var = tk.StringVar()
        self.tags_var = tk.StringVar()
        self.single_video_only_var = tk.BooleanVar(value=DEFAULT_IGNORE_PLAYLISTS)
        self.use_nvenc_var = tk.BooleanVar(value=False)
        self.cookie_source_var = tk.StringVar(value=CookieSource.PUBLIC.value)
        self.cookie_file_path: Path | None = None
        self.cookie_file_var = tk.StringVar(value="No cookies.txt selected")
        self.cookie_browser_var = tk.StringVar(value=COOKIE_BROWSER_PLACEHOLDER)
        self.cookie_source_var.trace_add(
            "write", lambda *_args: self._on_cookie_source_changed()
        )
        self.embed_thumbnail_var = tk.BooleanVar(value=False)
        self.write_thumbnail_var = tk.BooleanVar(value=True)
        self.embed_metadata_var = tk.BooleanVar(value=False)
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
        self._provider_network = ProviderNetworkCoordinator()
        self._persist_activity = False

        self._apply_theme()
        self._build_ui()
        previous_activity = load_activity_log_tail()
        if previous_activity:
            self._set_text(self.log, previous_activity, disabled=True)
        self._persist_activity = True
        self._append_log(
            f"—— Session started {datetime.now().isoformat(timespec='seconds')} ——"  # noqa: DTZ005 - local wall-clock receipt
        )
        self._load_download_history()
        self._check_runtime()
        self.after(100, self._pump_events)
        self.after(250, self._record_first_launch)
        self.after(25, self._start_ytdlp_preload)
        self.protocol("WM_DELETE_WINDOW", self._request_application_close)
        if bool(getattr(sys, "frozen", False)):
            self._schedule_auto_update_check(AUTO_UPDATE_INITIAL_DELAY_MS)

    def _apply_theme(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            ".", background=THEME["bg"], foreground=THEME["text"], font=FONT_UI
        )
        style.configure("TFrame", background=THEME["bg"])
        style.configure("Panel.TFrame", background=THEME["panel"])
        style.configure("Card.TFrame", background=THEME["surface"], relief="flat")
        style.configure(
            "TLabel", background=THEME["bg"], foreground=THEME["text"], font=FONT_UI
        )
        style.configure(
            "Muted.TLabel",
            background=THEME["bg"],
            foreground=THEME["muted"],
            font=FONT_UI_SMALL,
        )
        style.configure(
            "Hero.TLabel",
            background=THEME["bg"],
            foreground=THEME["text"],
            font=FONT_TITLE,
        )
        style.configure(
            "Accent.TLabel",
            background=THEME["bg"],
            foreground=THEME["accent"],
            font=FONT_UI_MEDIUM,
        )
        style.configure(
            "TLabelframe",
            background=THEME["bg"],
            foreground=THEME["text"],
            bordercolor=THEME["border"],
            relief="solid",
        )
        style.configure(
            "TLabelframe.Label",
            background=THEME["bg"],
            foreground=THEME["accent"],
            font=FONT_UI_MEDIUM,
        )
        style.configure(
            "TEntry",
            fieldbackground=THEME["surface"],
            foreground=THEME["text"],
            insertcolor=THEME["text"],
            bordercolor=THEME["border"],
            lightcolor=THEME["border"],
            darkcolor=THEME["border"],
            padding=7,
        )
        style.configure(
            "TCombobox",
            fieldbackground=THEME["surface"],
            foreground=THEME["text"],
            background=THEME["surface"],
            arrowcolor=THEME["accent"],
            bordercolor=THEME["border"],
            padding=6,
        )
        style.map(
            "TCombobox",
            fieldbackground=[
                ("readonly", THEME["surface"]),
                ("active", THEME["surface_2"]),
            ],
            foreground=[("readonly", THEME["text"])],
        )
        style.configure(
            "TButton",
            background=THEME["surface_2"],
            foreground=THEME["text"],
            bordercolor=THEME["border"],
            focusthickness=0,
            focuscolor=THEME["surface_2"],
            padding=(12, 7),
            font=FONT_UI_MEDIUM,
        )
        style.configure(
            "Compact.TButton",
            background=THEME["surface_2"],
            foreground=THEME["text"],
            bordercolor=THEME["border"],
            focusthickness=0,
            focuscolor=THEME["surface_2"],
            padding=(10, 4),
            font=FONT_UI_MEDIUM,
        )
        style.map(
            "Compact.TButton",
            background=[
                ("active", THEME["surface_2"]),
                ("pressed", THEME["panel"]),
                ("disabled", THEME["panel"]),
            ],
        )
        style.map(
            "TButton",
            background=[
                ("active", THEME["border"]),
                ("pressed", THEME["accent_dark"]),
                ("disabled", THEME["panel"]),
            ],
            foreground=[("disabled", THEME["subtle"])],
        )
        style.configure(
            "Accent.TButton",
            background=THEME["accent_dark"],
            foreground="#ffffff",
            bordercolor=THEME["accent"],
        )
        style.map(
            "Accent.TButton",
            background=[
                ("active", THEME["accent"]),
                ("pressed", THEME["accent_dark"]),
                ("disabled", THEME["panel"]),
            ],
        )
        style.configure(
            "TCheckbutton",
            background=THEME["bg"],
            foreground=THEME["text"],
            indicatorcolor=THEME["surface"],
            font=FONT_UI,
        )
        style.map(
            "TCheckbutton",
            background=[("active", THEME["bg"])],
            foreground=[("disabled", THEME["subtle"])],
        )
        style.configure(
            "TProgressbar",
            background=THEME["accent"],
            troughcolor=THEME["surface"],
            bordercolor=THEME["border"],
            lightcolor=THEME["accent"],
            darkcolor=THEME["accent_dark"],
        )
        style.configure(
            "TNotebook",
            background=THEME["panel"],
            borderwidth=0,
            tabmargins=(8, 6, 8, 0),
        )
        style.configure(
            "TNotebook.Tab",
            background=THEME["surface"],
            foreground=THEME["muted"],
            padding=(18, 9),
            font=FONT_UI_MEDIUM,
            bordercolor=THEME["border"],
        )
        style.map(
            "TNotebook.Tab",
            background=[
                ("selected", THEME["accent_dark"]),
                ("active", THEME["surface_2"]),
            ],
            foreground=[("selected", "#ffffff"), ("active", THEME["text"])],
            expand=[("selected", (0, 0, 0, 0))],
        )
        style.configure(
            "Treeview",
            background=THEME["surface"],
            fieldbackground=THEME["surface"],
            foreground=THEME["text"],
            bordercolor=THEME["border"],
            rowheight=30,
            font=FONT_UI,
        )
        style.configure(
            "Treeview.Heading",
            background=THEME["panel"],
            foreground=THEME["muted"],
            relief="flat",
            font=FONT_UI_SMALL_MEDIUM,
        )
        style.map(
            "Treeview",
            background=[("selected", THEME["accent_dark"])],
            foreground=[("selected", "#ffffff")],
        )
        style.configure("FocusShell.TFrame", background=THEME["bg"])
        style.configure("FocusSurface.TFrame", background=THEME["surface"])
        style.configure(
            "CloudPreview.TFrame",
            background=THEME["surface"],
            bordercolor=THEME["border"],
            borderwidth=1,
            relief="solid",
        )
        style.configure(
            "FocusBrand.TLabel",
            background=THEME["bg"],
            foreground=THEME["text"],
            font=(FONT_UI_FAMILY, 18, "bold"),
        )
        style.configure(
            "FocusTitle.TLabel",
            background=THEME["bg"],
            foreground=THEME["text"],
            font=(FONT_UI_FAMILY, 15, "bold"),
        )
        style.configure(
            "FocusActiveTitle.TLabel",
            background=THEME["bg"],
            foreground=THEME["text"],
            font=(FONT_UI_FAMILY, 13, "bold"),
        )
        style.configure(
            "FocusProfile.TLabel",
            background=THEME["bg"],
            foreground=THEME["accent"],
            font=FONT_UI_SMALL,
        )
        style.configure(
            "FocusPercent.TLabel",
            background=THEME["bg"],
            foreground=THEME["accent"],
            font=(FONT_UI_FAMILY, 24),
        )
        style.configure(
            "FocusEyebrow.TLabel",
            background=THEME["bg"],
            foreground=THEME["muted"],
            font=FONT_UI_SMALL_MEDIUM,
        )
        style.configure(
            "FocusSurface.TLabel",
            background=THEME["surface"],
            foreground=THEME["text"],
            font=FONT_UI,
        )
        style.configure(
            "FocusSurfaceMuted.TLabel",
            background=THEME["surface"],
            foreground=THEME["muted"],
            font=FONT_UI_SMALL,
        )
        style.configure(
            "CloudTitle.TLabel",
            background=THEME["surface"],
            foreground=THEME["text"],
            font=FONT_UI_MEDIUM,
        )
        style.configure(
            "CloudBadge.TLabel",
            background=THEME["surface"],
            foreground=THEME["accent"],
            font=FONT_UI_SMALL_MEDIUM,
        )
        style.configure(
            "FocusNav.TButton",
            background=THEME["bg"],
            foreground=THEME["muted"],
            bordercolor=THEME["bg"],
            focusthickness=0,
            focuscolor=THEME["bg"],
            padding=(12, 8),
            font=FONT_UI,
        )
        style.configure(
            "FocusNavActive.TButton",
            background=THEME["bg"],
            foreground=THEME["accent"],
            bordercolor=THEME["bg"],
            focusthickness=0,
            focuscolor=THEME["bg"],
            padding=(12, 8),
            font=FONT_UI,
        )
        style.layout(
            "FocusNav.TButton",
            [
                (
                    "Button.padding",
                    {
                        "sticky": "nswe",
                        "children": [("Button.label", {"sticky": "nswe"})],
                    },
                )
            ],
        )
        style.layout(
            "FocusNavActive.TButton",
            [
                (
                    "Button.padding",
                    {
                        "sticky": "nswe",
                        "children": [("Button.label", {"sticky": "nswe"})],
                    },
                )
            ],
        )
        style.map(
            "FocusNav.TButton",
            background=[("active", THEME["surface"])],
            foreground=[("active", THEME["text"])],
        )
        style.map(
            "FocusNavActive.TButton",
            background=[("active", THEME["surface"])],
            foreground=[("active", THEME["accent"])],
        )
        style.configure(
            "FocusQuiet.TButton",
            background=THEME["surface"],
            foreground=THEME["muted"],
            bordercolor=THEME["surface_2"],
            lightcolor=THEME["surface_2"],
            darkcolor=THEME["surface_2"],
            focusthickness=0,
            focuscolor=THEME["surface"],
            relief="flat",
            padding=(11, 6),
            font=FONT_UI_SMALL_MEDIUM,
        )
        style.map(
            "FocusQuiet.TButton",
            background=[("active", THEME["surface_2"]), ("pressed", THEME["panel"])],
            foreground=[("active", THEME["text"])],
        )
        style.configure(
            "CloudDisabled.TButton",
            background=THEME["surface_2"],
            foreground=THEME["subtle"],
            bordercolor=THEME["surface_2"],
            lightcolor=THEME["surface_2"],
            darkcolor=THEME["surface_2"],
            focusthickness=0,
            focuscolor=THEME["surface_2"],
            relief="flat",
            padding=(11, 6),
            font=FONT_UI_SMALL_MEDIUM,
        )
        style.map(
            "CloudDisabled.TButton",
            background=[("disabled", THEME["surface_2"])],
            foreground=[("disabled", THEME["subtle"])],
        )
        style.configure(
            "FocusIcon.TButton",
            background=THEME["bg"],
            foreground=THEME["muted"],
            bordercolor=THEME["bg"],
            lightcolor=THEME["bg"],
            darkcolor=THEME["bg"],
            focusthickness=0,
            focuscolor=THEME["bg"],
            relief="flat",
            padding=(9, 8),
        )
        style.map(
            "FocusIcon.TButton",
            background=[("active", THEME["surface"]), ("pressed", THEME["panel"])],
        )
        style.configure(
            "FocusDestination.TButton",
            background=THEME["surface"],
            foreground=THEME["muted"],
            bordercolor=THEME["border"],
            lightcolor=THEME["border"],
            darkcolor=THEME["border"],
            focusthickness=0,
            focuscolor=THEME["surface"],
            relief="flat",
            padding=(12, 7),
            font=FONT_UI_SMALL,
        )
        style.map(
            "FocusDestination.TButton",
            background=[("active", THEME["surface_2"])],
            foreground=[("active", THEME["text"])],
        )
        style.configure(
            "FocusCommand.TEntry",
            fieldbackground=THEME["surface"],
            foreground=THEME["text"],
            insertcolor=THEME["text"],
            bordercolor=THEME["surface"],
            lightcolor=THEME["surface"],
            darkcolor=THEME["surface"],
            padding=(4, 13),
            font=(FONT_UI_FAMILY, 12),
        )
        style.configure(
            "FocusProgress.Horizontal.TProgressbar",
            background=THEME["accent"],
            troughcolor=THEME["surface_2"],
            bordercolor=THEME["bg"],
            lightcolor=THEME["accent"],
            darkcolor=THEME["accent"],
            thickness=4,
            borderwidth=0,
        )
        style.configure(
            "FocusDeck.Horizontal.TProgressbar",
            background=THEME["accent"],
            troughcolor=THEME["border"],
            bordercolor=THEME["surface"],
            lightcolor=THEME["accent"],
            darkcolor=THEME["accent"],
            thickness=3,
            borderwidth=0,
        )
        style.configure(
            "Focus.TPanedwindow",
            background=THEME["bg"],
            sashwidth=1,
            sashrelief="flat",
            handlesize=0,
            handlepad=0,
        )
        style.configure("Focus.TSizegrip", background=THEME["bg"])
        self.option_add("*TCombobox*Listbox.background", THEME["surface"])
        self.option_add("*TCombobox*Listbox.foreground", THEME["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", THEME["accent_dark"])

    def _build_ui(self) -> None:
        self._build_focus_ui()

    def _load_focus_icon(self, name: str, size: int, color: str) -> Any | None:
        if Image is None or ImageTk is None:
            return None
        cache = getattr(self, "_focus_icon_images", None)
        if cache is None:
            cache = {}
            self._focus_icon_images = cache
        key = (name, size, color)
        if key in cache:
            return cache[key]
        color_variant = focus_icon_color_variant(color)
        vector_asset = (
            bundled_asset_path(f"icons/lucide/{name}-{size}-{color_variant}.svg")
            if color_variant
            else None
        )
        if is_macos() and vector_asset is not None and vector_asset.is_file():
            try:
                image_types = self.tk.splitlist(self.tk.call("image", "types"))
                if "nsimage" in image_types:
                    rendered = self.tk.call(
                        "image",
                        "create",
                        "nsimage",
                        "-source",
                        str(vector_asset),
                        "-as",
                        "file",
                        "-width",
                        size,
                        "-height",
                        size,
                    )
                    cache[key] = rendered
                    return rendered
            except tk.TclError as exc:
                write_diagnostic(
                    f"native vector icon could not be loaded ({name}): {exc}"
                )
        try:
            exact_asset = bundled_asset_path(f"icons/lucide/{name}-{size}.png")
            icon_asset = (
                exact_asset
                if exact_asset.is_file()
                else bundled_asset_path(f"icons/lucide/{name}.png")
            )
            with Image.open(icon_asset) as source:
                icon = render_monochrome_icon(source, size, color)
            rendered = ImageTk.PhotoImage(icon)
        except Exception as exc:  # noqa: BLE001 - optional icon rendering falls back cleanly
            write_diagnostic(f"in-app icon could not be loaded ({name}): {exc}")
            return None
        cache[key] = rendered
        return rendered

    def _build_focus_ui(self) -> None:
        """Build the flat, command-first VODForge workspace."""
        self._compact_popup = None
        self._focus_layout: str | None = None
        self._focus_settings_dialog: FocusSettingsDialog | None = None
        self._focus_active_override = False
        self._focus_selected_run_id: str | None = None
        self._metadata_preview_request: dict[str, Any] | None = None
        self._focus_selected_preview_info: dict[str, Any] | None = None
        self._focus_log_owner_run_id: str | None = None
        self._focus_log_rendered_text = ""
        self._terminal_jobs: list[DownloadJob] = []
        self._completed_jobs: list[DownloadJob] = []
        self._library_suppressed_run_ids: set[str] = set()
        self._thumbnail_preview_request_ids = {"active": 0, "library": 0}
        self._focus_icon_images = {}
        self._focus_run_list_close_after_id = None
        self._focus_run_list_window = None
        self._focus_run_list_cleanup = None

        self.focus_active_title_var = tk.StringVar(value="Ready for a new run")
        self.focus_active_detail_var = tk.StringVar(
            value="Paste a YouTube URL above, then press Return to begin."
        )
        self.focus_active_profile_var = tk.StringVar(
            value=f"{self.quality_var.get()}  •  {self.export_mode_var.get()}"
        )
        self.focus_active_duration_var = tk.StringVar(value="")
        self.focus_percent_var = tk.StringVar(value="0%")
        self.focus_display_progress_var = tk.DoubleVar(value=0)
        self.focus_display_status_var = tk.StringVar(value=self.status_var.get())
        self.focus_run_status_var = tk.StringVar(value="Ready")
        self.focus_transfer_var = tk.StringVar(
            value="VOD-ready MP4 / H.264 video / AAC audio"
        )
        self.focus_run_count_var = tk.StringVar(value="No runs yet")
        self.focus_engine_var = tk.StringVar(value="Sequential queue  /  Auto start on")
        self.focus_output_display_var = tk.StringVar()
        self.focus_update_state_var = tk.StringVar(value="Check updates")
        self._focus_update_full_text = "Check updates"

        shell = ttk.Frame(self, style="FocusShell.TFrame")
        shell.pack(fill="both", expand=True, padx=20, pady=(16, 14))
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(3, weight=1)
        self.focus_shell = shell

        header = ttk.Frame(shell, style="FocusShell.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        self.focus_header = header

        brand = ttk.Frame(header, style="FocusShell.TFrame")
        brand.grid(row=0, column=0, sticky="w", pady=(0, 8))
        self._focus_brand_image = None
        self._focus_brand_nav_image = None
        self._focus_brand_tile_image = None
        self._focus_brand_source_image = None
        self._focus_thumbnail_source_image = None
        self._focus_thumbnail_source_path: Path | None = None
        self._focus_thumbnail_is_placeholder = True
        self._focus_active_thumbnail_source_image = None
        self._focus_active_thumbnail_source_path: Path | None = None
        self._focus_active_thumbnail_is_placeholder = True
        if Image is not None and ImageOps is not None and ImageTk is not None:
            try:
                with Image.open(bundled_asset_path("VODForge.png")) as source:
                    icon = source.convert("RGBA")
                resampling = getattr(Image, "Resampling", Image)
                self._focus_brand_source_image = icon.copy()
                self._focus_thumbnail_source_image = icon.copy()
                self._focus_active_thumbnail_source_image = icon.copy()
                self._focus_brand_image = ImageTk.PhotoImage(
                    icon.resize((34, 34), resampling.LANCZOS)
                )
                self._focus_brand_nav_image = ImageTk.PhotoImage(
                    icon.resize((20, 20), resampling.LANCZOS)
                )
                tile_icon = rounded_contain_image(
                    icon, youtube_thumbnail_size(152), 10, THEME["surface"]
                )
                self._focus_brand_tile_image = ImageTk.PhotoImage(tile_icon)
            except Exception as exc:  # noqa: BLE001 - optional brand rendering falls back cleanly
                write_diagnostic(f"in-app brand mark could not be loaded: {exc}")
        if self._focus_brand_image is not None:
            ttk.Label(brand, image=self._focus_brand_image, style="TLabel").pack(
                side="left", padx=(0, 10)
            )
        ttk.Label(brand, text="VODForge", style="FocusBrand.TLabel").pack(side="left")

        utilities = ttk.Frame(header, style="FocusShell.TFrame")
        utilities.grid(row=0, column=2, sticky="e", pady=(0, 8))
        self.focus_update_dot = tk.Canvas(
            utilities, width=10, height=10, bg=THEME["bg"], bd=0, highlightthickness=0
        )
        self.focus_update_dot.create_oval(
            2, 2, 8, 8, fill=THEME["subtle"], outline="", tags="dot"
        )
        self.focus_update_dot.pack(side="left", padx=(0, 4))
        self.update_button = tk.Label(
            utilities,
            text="Check updates",
            bg=THEME["bg"],
            fg=THEME["muted"],
            bd=0,
            highlightthickness=0,
            padx=2,
            pady=2,
            font=FONT_UI_SMALL,
            cursor="hand2",
        )
        self.update_button.bind(
            "<Button-1>",
            lambda _event: (
                self._check_for_updates()
                if str(self.update_button.cget("state")) != "disabled"
                else None
            ),
        )
        self.update_button.pack(side="left", padx=(0, 8))
        settings_icon = self._load_focus_icon("settings", 20, THEME["muted"])
        settings_hover_icon = self._load_focus_icon("settings", 20, THEME["text"])
        self.focus_settings_button = tk.Label(
            utilities,
            image=settings_icon if settings_icon is not None else "",
            text="Settings" if settings_icon is None else "",
            bg=THEME["bg"],
            fg=THEME["muted"],
            bd=0,
            highlightthickness=0,
            padx=3,
            pady=3,
            cursor="hand2",
            takefocus=1,
        )
        self.focus_settings_button.pack(side="left")
        self.focus_settings_button.bind(
            "<Button-1>", lambda _event: self._show_focus_settings(), add="+"
        )
        self.focus_settings_button.bind(
            "<Return>", lambda _event: self._show_focus_settings(), add="+"
        )
        self.focus_settings_button.bind(
            "<space>", lambda _event: self._show_focus_settings(), add="+"
        )
        if settings_icon is not None and settings_hover_icon is not None:
            self.focus_settings_button.bind(
                "<Enter>",
                lambda _event: self.focus_settings_button.configure(
                    image=settings_hover_icon
                ),
                add="+",
            )
            self.focus_settings_button.bind(
                "<Leave>",
                lambda _event: self.focus_settings_button.configure(
                    image=settings_icon
                ),
                add="+",
            )

        nav_row = ttk.Frame(header, style="FocusShell.TFrame")
        nav_row.grid(row=1, column=0, columnspan=3, sticky="ew")
        nav_row.columnconfigure(1, weight=1)
        nav = ttk.Frame(nav_row, style="FocusShell.TFrame")
        nav.grid(row=0, column=0, sticky="w")
        self._focus_nav_buttons: dict[str, ttk.Button] = {}
        self._focus_nav_underlines: dict[str, tk.Frame] = {}
        self._focus_nav_icons: dict[str, tuple[Any | None, Any | None]] = {
            "forge": (self._focus_brand_nav_image, self._focus_brand_nav_image),
            "library": (
                self._load_focus_icon("library", 20, THEME["muted"]),
                self._load_focus_icon("library", 20, THEME["accent"]),
            ),
            "activity": (
                self._load_focus_icon("activity", 20, THEME["muted"]),
                self._load_focus_icon("activity", 20, THEME["accent"]),
            ),
        }
        for view_name, label in (
            ("forge", "Forge"),
            ("library", "Library"),
            ("activity", "Activity"),
        ):
            item = ttk.Frame(nav, style="FocusShell.TFrame")
            item.pack(side="left", padx=(0, 8))
            inactive_icon, _active_icon = self._focus_nav_icons[view_name]
            button = ttk.Button(
                item,
                text=label,
                image=inactive_icon if inactive_icon is not None else "",
                compound="left",
                style="FocusNav.TButton",
                takefocus=True,
                command=partial(self._select_focus_view, view_name),
            )
            button.pack(fill="x")
            underline = tk.Frame(
                item, height=2, bg=THEME["bg"], bd=0, highlightthickness=0
            )
            underline.pack(fill="x")
            self._focus_nav_buttons[view_name] = button
            self._focus_nav_underlines[view_name] = underline

        folder_icon = self._load_focus_icon("folder", 20, THEME["muted"])
        self.focus_destination_button = PillAction(
            nav_row,
            textvariable=self.focus_output_display_var,
            image=folder_icon,
            command=self._browse_output,
            width=240,
        )
        self.focus_destination_button.grid(row=0, column=2, sticky="e")

        separator = tk.Frame(
            shell, bg=THEME["border"], height=1, bd=0, highlightthickness=0
        )
        separator.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        view_stack = ttk.Frame(shell, style="FocusShell.TFrame")
        view_stack.grid(row=3, column=0, sticky="nsew")
        view_stack.columnconfigure(0, weight=1)
        view_stack.rowconfigure(0, weight=1)
        self.focus_view_stack = view_stack

        forge_view = ttk.Frame(view_stack, style="FocusShell.TFrame")
        library_view = ttk.Frame(view_stack, style="FocusShell.TFrame")
        activity_view = ttk.Frame(view_stack, style="FocusShell.TFrame")
        for frame in (forge_view, library_view, activity_view):
            frame.grid(row=0, column=0, sticky="nsew")
        self._focus_views = {
            "forge": forge_view,
            "library": library_view,
            "activity": activity_view,
        }
        self._bind_focus_view_shortcuts()
        self.download_tab = forge_view
        self.metadata_tab = library_view

        self._build_focus_forge_view(forge_view)
        self._build_focus_library_view(library_view)
        self._build_focus_activity_view(activity_view)

        self.progress_var.trace_add("write", lambda *_args: self._sync_focus_progress())
        self.status_var.trace_add("write", lambda *_args: self._sync_focus_status())
        self.output_var.trace_add(
            "write", lambda *_args: self._sync_focus_destination()
        )
        self.quality_var.trace_add(
            "write", lambda *_args: self._sync_focus_settings_summary()
        )
        self.export_mode_var.trace_add(
            "write", lambda *_args: self._sync_focus_settings_summary()
        )
        self.manual_audio_codec_var.trace_add(
            "write", lambda *_args: self._sync_focus_settings_summary()
        )
        self.export_mode_choice_var.trace_add(
            "write", lambda *_args: self._on_export_mode_choice_changed()
        )
        self.output_type_var.trace_add(
            "write", lambda *_args: self._on_output_type_changed()
        )
        self.library_output_type_var.trace_add(
            "write", lambda *_args: self._on_library_output_type_changed()
        )
        self.mp3_quality_var.trace_add(
            "write", lambda *_args: self._sync_focus_settings_summary()
        )
        self.mp3_sample_rate_var.trace_add(
            "write", lambda *_args: self._sync_focus_settings_summary()
        )
        self.mp3_channels_var.trace_add(
            "write", lambda *_args: self._sync_focus_settings_summary()
        )
        self.mp3_cover_art_mode_var.trace_add(
            "write", lambda *_args: self._on_mp3_cover_mode_changed()
        )
        self._sync_focus_destination()
        self._on_output_type_changed()
        self._on_library_output_type_changed()
        self._sync_focus_progress()
        self._select_focus_view("forge")
        self._refresh_focus_run_deck()
        self.focus_resize_grip = ttk.Sizegrip(self, style="Focus.TSizegrip")
        self.focus_resize_grip.place(relx=1.0, rely=1.0, anchor="se")
        self.focus_resize_grip.lift()
        self.bind("<Configure>", self._schedule_focus_layout, add="+")
        self.after_idle(self.focus_url_entry.focus_set)

    def _build_focus_forge_view(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        command_area = ttk.Frame(parent, style="FocusShell.TFrame")
        command_area.grid(row=0, column=0, sticky="ew", padx=70, pady=(34, 12))
        command_area.columnconfigure(0, weight=1)
        self.focus_command_area = command_area

        command_row = ttk.Frame(command_area, style="FocusShell.TFrame")
        command_row.grid(row=0, column=0, sticky="ew")
        command_row.columnconfigure(0, weight=1)
        command_box = tk.Canvas(
            command_row,
            height=40,
            bg=THEME["bg"],
            bd=0,
            highlightthickness=0,
        )
        command_box.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        command_inner = tk.Frame(
            command_box, bg=THEME["surface"], bd=0, highlightthickness=0
        )
        command_inner.columnconfigure(1, weight=1)
        command_window = command_box.create_window(
            12, 2, anchor="nw", window=command_inner
        )
        command_background = command_box.create_polygon(
            rounded_canvas_rectangle_points(1, 40, 8),
            smooth=True,
            splinesteps=16,
            fill=THEME["surface"],
            outline=THEME["border"],
            width=1,
        )
        command_box.tag_lower(command_background)

        def redraw_command_box(_event: Any = None) -> None:
            width = max(1, command_box.winfo_width())
            height = max(1, command_box.winfo_height())
            command_box.coords(
                command_background,
                *rounded_canvas_rectangle_points(width, height, min(8, height // 2)),
            )
            command_box.tag_lower(command_background)
            command_box.coords(command_window, 10, 2)
            command_box.itemconfigure(
                command_window, width=max(1, width - 20), height=max(1, height - 4)
            )

        command_box.bind("<Configure>", redraw_command_box, add="+")
        link_icon = self._load_focus_icon("link-2", 20, THEME["muted"])
        self.focus_command_link_label = tk.Label(
            command_inner,
            image=link_icon if link_icon is not None else "",
            text="URL" if link_icon is None else "",
            bg=THEME["surface"],
            fg=THEME["muted"],
            bd=0,
            padx=0,
            pady=0,
            font=FONT_UI_SMALL,
        )
        self.focus_command_link_label.grid(row=0, column=0, sticky="w", padx=(3, 13))
        self.focus_url_entry = tk.Entry(
            command_inner,
            textvariable=self.url_var,
            bg=THEME["surface"],
            fg=THEME["text"],
            insertbackground=THEME["text"],
            selectbackground=THEME["accent_dark"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=(FONT_UI_FAMILY, 12),
        )
        self.focus_url_entry.grid(row=0, column=1, sticky="ew", ipady=7)
        self.focus_url_entry.bind("<Return>", lambda _event: self._start_download())
        self.focus_output_type_selector = SegmentedSelector(
            command_inner,
            variable=self.output_type_var,
            background=THEME["surface"],
            compact=True,
        )
        self.focus_output_type_selector.grid(row=0, column=2, sticky="e", padx=(12, 1))
        ToolTip(self.focus_output_type_selector, "Choose MP4 video or MP3 audio")
        sliders_icon = self._load_focus_icon("sliders-horizontal", 20, THEME["muted"])
        self.focus_options_button = RoundedIconButton(
            command_row,
            image=sliders_icon,
            text="Options" if sliders_icon is None else "",
            command=self._show_focus_settings,
        )
        self.focus_options_button.grid(row=0, column=1, padx=(0, 8))
        send_icon = self._load_focus_icon("send-filled", 20, "#ffffff")
        self.download_button = RoundedIconButton(
            command_row,
            image=send_icon,
            text="Forge" if send_icon is None else "",
            command=self._start_download,
            primary=True,
        )
        self.download_button.grid(row=0, column=2)
        ToolTip(self.focus_options_button, "Download options and settings")
        ToolTip(self.download_button, "Start or queue this run")
        self.preview_metadata_button = ttk.Button(
            command_row,
            text="Preview metadata",
            command=self._fetch_metadata,
            style="FocusQuiet.TButton",
        )
        self.focus_command_hint_var = tk.StringVar()
        self.focus_command_box = command_box

        active = ttk.Frame(parent, style="FocusShell.TFrame")
        active.grid(row=1, column=0, sticky="ew", padx=70, pady=(10, 14))
        active.columnconfigure(1, weight=1)
        self.focus_active_frame = active

        active_thumbnail_size = youtube_thumbnail_size(152)
        thumb_wrap = tk.Frame(
            active,
            bg=THEME["bg"],
            width=active_thumbnail_size[0],
            height=active_thumbnail_size[1],
            bd=0,
            highlightthickness=0,
        )
        thumb_wrap.grid(row=0, column=0, rowspan=3, sticky="w", padx=(0, 18))
        thumb_wrap.grid_propagate(False)
        self.focus_active_thumbnail_label = tk.Label(
            thumb_wrap,
            image=self._focus_brand_tile_image
            if self._focus_brand_tile_image is not None
            else "",
            text="" if self._focus_brand_tile_image is not None else APP_NAME,
            bg=THEME["bg"],
            fg=THEME["muted"],
            font=FONT_UI_SMALL_MEDIUM,
            bd=0,
            highlightthickness=0,
        )
        self.focus_active_thumbnail_label.place(relx=0.5, rely=0.5, anchor="center")
        self.focus_active_duration_label = tk.Label(
            thumb_wrap,
            textvariable=self.focus_active_duration_var,
            bg="#08090a",
            fg="#ffffff",
            font=(FONT_UI_FAMILY, 8, "bold"),
            bd=0,
            padx=4,
            pady=1,
        )
        self.focus_active_duration_label.place(relx=0.96, rely=0.91, anchor="se")
        self.focus_active_duration_var.trace_add(
            "write", lambda *_args: self._sync_focus_duration_badge()
        )
        self._sync_focus_duration_badge()
        self.focus_active_thumb_wrap = thumb_wrap

        title_block = ttk.Frame(active, style="FocusShell.TFrame")
        title_block.grid(row=0, column=1, sticky="ew")
        title_block.columnconfigure(0, weight=1)
        self.focus_active_title_label = ttk.Label(
            title_block,
            textvariable=self.focus_active_title_var,
            style="FocusActiveTitle.TLabel",
            justify="left",
        )
        self.focus_active_title_label.grid(row=0, column=0, sticky="w")
        ttk.Label(
            title_block, textvariable=self.focus_active_detail_var, style="Muted.TLabel"
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(
            title_block,
            textvariable=self.focus_active_profile_var,
            style="FocusProfile.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(5, 0))
        self.focus_percent_label = ttk.Label(
            active, textvariable=self.focus_percent_var, style="FocusPercent.TLabel"
        )
        self.focus_percent_label.grid(
            row=0, column=2, rowspan=3, sticky="e", padx=(18, 0)
        )
        self.focus_preview_start_button = ttk.Button(
            active,
            text="Start download",
            command=self._start_selected_preview_download,
            style="Accent.TButton",
        )
        self.focus_preview_start_button.grid(
            row=0,
            column=2,
            rowspan=3,
            sticky="e",
            padx=(22, 0),
            ipadx=10,
            ipady=5,
        )
        self.focus_preview_start_button.grid_remove()

        progress_row = ttk.Frame(active, style="FocusShell.TFrame")
        progress_row.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        progress_row.columnconfigure(0, weight=1)
        self.progress_bar = SleekProgressbar(
            progress_row,
            variable=self.focus_display_progress_var,
            maximum=100,
            mode="determinate",
            style="FocusProgress.Horizontal.TProgressbar",
        )
        self.progress_bar.grid(row=0, column=0, columnspan=5, sticky="ew", ipady=0)
        ttk.Label(
            progress_row,
            textvariable=self.focus_display_status_var,
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(7, 0))
        self.focus_transfer_label = ttk.Label(
            progress_row, textvariable=self.focus_transfer_var, style="Muted.TLabel"
        )
        self.focus_transfer_label.grid(
            row=1, column=1, sticky="e", pady=(7, 0), padx=(12, 0)
        )
        self.cancel_button = ttk.Button(
            progress_row,
            text="Cancel",
            command=self._cancel,
            state="disabled",
            style="FocusQuiet.TButton",
        )
        self.cancel_button.grid(row=1, column=2, padx=(14, 6), pady=(5, 0))
        self.skip_video_button = ttk.Button(
            progress_row,
            text="Skip item",
            command=self._skip_video,
            state="disabled",
            style="FocusQuiet.TButton",
        )
        self.skip_video_button.grid(row=1, column=3, pady=(5, 0))
        ToolTip(
            self.skip_video_button,
            "Skip only the current video or audio item. If this source is a playlist, continue with its next item.",
        )
        self.skip_url_button = ttk.Button(
            progress_row,
            text="Skip source",
            command=self._skip_url,
            state="disabled",
            style="FocusQuiet.TButton",
        )
        self.skip_url_button.grid(row=1, column=4, padx=(6, 0), pady=(5, 0))
        ToolTip(
            self.skip_url_button,
            "Skip the rest of this source URL. If a URL list is loaded, continue with its next URL.",
        )
        self.focus_compact_run_actions_button = ttk.Button(
            progress_row,
            text="Run actions",
            command=self._show_active_focus_run_actions,
            style="FocusQuiet.TButton",
        )
        self.focus_compact_run_actions_button.grid(
            row=1, column=2, padx=(14, 0), pady=(5, 0)
        )
        self.focus_compact_run_actions_button.grid_remove()
        self.focus_run_controls = (
            self.cancel_button,
            self.skip_video_button,
            self.skip_url_button,
        )
        self._set_focus_run_controls_visible(False)

        detail_wrap = ttk.Frame(parent, style="FocusShell.TFrame")
        detail_wrap.grid(row=2, column=0, sticky="nsew", padx=70, pady=(0, 12))
        detail_wrap.columnconfigure(0, weight=1)
        detail_wrap.rowconfigure(1, weight=1)
        self.focus_detail_wrap = detail_wrap
        detail_header = ttk.Frame(detail_wrap, style="FocusShell.TFrame")
        detail_header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        detail_header.columnconfigure(0, weight=1)
        ttk.Label(
            detail_header, text="LIVE ACTIVITY", style="FocusEyebrow.TLabel"
        ).grid(row=0, column=0, sticky="w")
        self.focus_details_button = ttk.Button(
            detail_header,
            text="Output details",
            command=self._show_focus_output_details,
            style="FocusQuiet.TButton",
        )
        self.focus_detail_header = detail_header

        detail_pane = ttk.Frame(detail_wrap, style="FocusShell.TFrame")
        detail_pane.grid(row=1, column=0, sticky="nsew")
        detail_pane.columnconfigure(0, weight=3)
        detail_pane.columnconfigure(1, weight=2)
        detail_pane.rowconfigure(0, weight=1)
        self.focus_detail_pane = detail_pane
        live_frame = ttk.Frame(detail_pane, style="FocusShell.TFrame")
        summary_frame = ttk.Frame(detail_pane, style="FocusShell.TFrame")
        live_frame.grid(row=0, column=0, sticky="nsew")
        summary_frame.grid(row=0, column=1, sticky="nsew")
        self.focus_live_frame = live_frame
        self.focus_summary_frame = summary_frame
        live_frame.columnconfigure(0, weight=1)
        live_frame.rowconfigure(0, weight=1)
        summary_frame.columnconfigure(0, weight=1)
        summary_frame.rowconfigure(0, weight=1)
        self.focus_log = tk.Text(
            live_frame,
            height=4,
            width=1,
            wrap="word",
            state="disabled",
            bg=THEME["bg"],
            fg=THEME["muted"],
            insertbackground=THEME["bg"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=0,
            pady=4,
            font=FONT_MONO,
            takefocus=0,
            insertwidth=0,
        )
        self.focus_log.grid(row=0, column=0, sticky="nsew", padx=(0, 22))
        self.focus_summary_text = tk.Text(
            summary_frame,
            height=4,
            width=1,
            wrap="word",
            state="disabled",
            bg=THEME["bg"],
            fg=THEME["text"],
            insertbackground=THEME["bg"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=0,
            pady=7,
            font=FONT_MONO,
            takefocus=0,
            insertwidth=0,
        )
        self.focus_summary_text.grid(row=0, column=0, sticky="nsew")
        bind_smooth_vertical_wheel(self.focus_log, mode="pixels")
        bind_smooth_vertical_wheel(self.focus_summary_text, mode="pixels")
        self._set_text(
            self.focus_summary_text,
            "Format        MP4\nVideo         H.264\nAudio         AAC\nOutput mode   Auto CBR\nSave to       "
            + self.output_var.get(),
            disabled=True,
        )

        deck_area = ttk.Frame(parent, style="FocusShell.TFrame")
        deck_area.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 4))
        deck_area.columnconfigure(0, weight=1)
        deck_header = ttk.Frame(deck_area, style="FocusShell.TFrame")
        deck_header.grid(row=0, column=0, sticky="ew", padx=6, pady=(0, 6))
        deck_header.columnconfigure(0, weight=1)
        ttk.Label(deck_header, text="RUN DECK", style="FocusEyebrow.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.focus_run_overflow_button = ttk.Button(
            deck_header,
            text="All runs",
            command=self._show_focus_run_menu,
            style="FocusQuiet.TButton",
        )
        self.focus_run_overflow_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self.focus_run_overflow_button.bind(
            "<Enter>", lambda _event: self._show_focus_run_menu(), add="+"
        )
        self.focus_run_overflow_button.bind(
            "<Leave>", lambda _event: self._schedule_focus_run_menu_close(), add="+"
        )
        self.focus_deck_header = deck_header

        deck_border = tk.Frame(
            deck_area, bg=THEME["border"], bd=0, highlightthickness=0
        )
        deck_border.grid(row=1, column=0, sticky="ew")
        deck = ttk.Frame(deck_border, style="FocusShell.TFrame")
        deck.pack(fill="both", expand=True, padx=1, pady=1)
        self.focus_run_deck = deck
        deck.bind(
            "<Configure>", self._schedule_focus_run_deck_geometry_refresh, add="+"
        )

        footer = ttk.Frame(parent, style="FocusShell.TFrame")
        footer.grid(row=4, column=0, sticky="ew", padx=26, pady=(4, 0))
        footer.columnconfigure(1, weight=1)
        ttk.Label(
            footer, textvariable=self.focus_run_count_var, style="Muted.TLabel"
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            footer, textvariable=self.focus_engine_var, style="Muted.TLabel"
        ).grid(row=0, column=2, sticky="e")

    def _build_focus_library_view(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=2, minsize=125)
        parent.rowconfigure(2, weight=3, minsize=180)
        self.focus_library_view = parent

        actions = ttk.Frame(parent, style="FocusShell.TFrame")
        actions.grid(row=0, column=0, sticky="ew", padx=18, pady=(24, 10))
        actions.columnconfigure(0, weight=1)
        heading = ttk.Frame(actions, style="FocusShell.TFrame")
        heading.grid(row=0, column=0, sticky="w")
        heading_title = ttk.Frame(heading, style="FocusShell.TFrame")
        heading_title.pack(anchor="w")
        ttk.Label(heading_title, text="Library", style="FocusTitle.TLabel").pack(
            side="left"
        )
        self.focus_library_output_type_selector = SegmentedSelector(
            heading_title,
            variable=self.library_output_type_var,
            background=THEME["bg"],
            compact=True,
        )
        self.focus_library_output_type_selector.pack(side="left", padx=(14, 0))
        ttk.Label(
            heading, text="Saved downloads and metadata previews", style="Muted.TLabel"
        ).pack(anchor="w", pady=(3, 0))
        action_row = ttk.Frame(actions, style="FocusShell.TFrame")
        action_row.grid(row=0, column=1, sticky="e")
        self.focus_library_details_button = ttk.Button(
            action_row,
            text="Selected details",
            command=self._show_selected_metadata_details,
            style="FocusQuiet.TButton",
        )
        self.focus_library_menu_button = ttk.Button(
            action_row,
            text="Actions",
            width=7,
            command=self._show_library_actions_menu,
            style="FocusQuiet.TButton",
        )
        self._focus_library_action_feedback_after_id: str | None = None
        self.focus_library_menu_button.pack(side="left")

        metadata_content = ttk.Frame(parent, style="FocusShell.TFrame")
        metadata_content.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 14))
        # The media table owns the flexible width. Selected Item is a compact
        # inspection rail, not a second equal-width workspace.
        metadata_content.columnconfigure(0, weight=1)
        metadata_content.columnconfigure(1, weight=0, minsize=340)
        metadata_content.rowconfigure(0, weight=1)
        self.focus_metadata_content = metadata_content
        self.focus_library_actions = actions

        queue_panel = ttk.Frame(metadata_content, style="FocusShell.TFrame")
        queue_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        queue_panel.columnconfigure(0, weight=1)
        queue_panel.rowconfigure(1, weight=1)
        self.focus_library_media_label_var = tk.StringVar(value="MP4 MEDIA")
        ttk.Label(
            queue_panel,
            textvariable=self.focus_library_media_label_var,
            style="FocusEyebrow.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.video_tree = PixelScrollTable(
            queue_panel,
            columns=(
                "index",
                "title",
                "duration",
                "creator",
                "id",
                "location",
                "action",
            ),
            selectmode="browse",
        )
        video_tree = self.video_tree
        for column, label in (
            ("index", "#"),
            ("title", "Title"),
            ("duration", "Length"),
            ("creator", "Creator"),
            ("id", "ID"),
            ("location", "Saved location"),
            ("action", ""),
        ):
            video_tree.heading(
                column,
                text=label,
                anchor="w" if column == "duration" else None,
            )
        video_tree.column(
            "index", width=44, minwidth=38, stretch=False, anchor="center"
        )
        video_tree.column(
            "title", width=360, minwidth=220, stretch=True, stretchmax=560, anchor="w"
        )
        video_tree.column(
            "duration", width=72, minwidth=62, stretch=False, anchor="center"
        )
        video_tree.column("creator", width=140, minwidth=90, stretch=False, anchor="w")
        video_tree.column("id", width=100, minwidth=72, stretch=False, anchor="w")
        video_tree.column("location", width=140, minwidth=90, stretch=False, anchor="w")
        video_tree.column(
            "action", width=42, minwidth=42, stretch=False, anchor="center"
        )
        tree_scroll = SleekScrollbar(queue_panel, command=video_tree.yview)
        tree_x_scroll = SleekScrollbar(
            queue_panel, command=video_tree.xview, orient="horizontal"
        )
        video_tree.configure(
            yscrollcommand=tree_scroll.set, xscrollcommand=tree_x_scroll.set
        )
        video_tree.grid(row=1, column=0, sticky="nsew")
        tree_scroll.grid(row=1, column=1, sticky="ns", padx=(6, 0))
        tree_x_scroll.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        video_tree.bind_body_event("<<TreeviewSelect>>", self._on_video_selected)
        video_tree.bind_body_event("<Button-1>", self._on_library_tree_click, add="+")
        video_tree.bind_body_event("<Button-2>", self._show_library_row_menu)
        video_tree.bind_body_event("<Button-3>", self._show_library_row_menu)
        self.focus_queue_panel = queue_panel

        details = ttk.Frame(metadata_content, style="FocusShell.TFrame")
        details.grid(row=0, column=1, sticky="nsew")
        # Keep the inspection rail authoritative instead of letting wrapped
        # child requests feed back into Grid and progressively starve the
        # table after repeated resize cycles.
        details.configure(width=410, height=FOCUS_LIBRARY_SELECTED_DETAILS_HEIGHT)
        details.grid_propagate(False)
        details.columnconfigure(0, weight=1)
        details.rowconfigure(3, weight=0)
        details.rowconfigure(4, weight=1, minsize=120)
        self.selected_title_var = tk.StringVar(
            value="Choose a saved item or preview a URL to inspect its metadata."
        )
        self.selected_meta_var = tk.StringVar(value="")
        self.selected_location_var = tk.StringVar(value="")
        self.selected_title_display_var = tk.StringVar(
            value=self.selected_title_var.get()
        )
        self.selected_meta_display_var = tk.StringVar(value="")
        self.selected_location_display_var = tk.StringVar(value="")
        ttk.Label(details, text="SELECTED ITEM", style="FocusEyebrow.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        overview = ttk.Frame(details, style="FocusShell.TFrame")
        overview.configure(height=FOCUS_LIBRARY_SELECTED_OVERVIEW_HEIGHT)
        overview.grid_propagate(False)
        overview.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        overview.columnconfigure(0, weight=1)
        self.focus_selected_overview = overview
        self._focus_selected_overview_height = FOCUS_LIBRARY_SELECTED_OVERVIEW_HEIGHT
        self._focus_selected_overview_layout_after_id: str | None = None
        self._focus_selected_text_width = 220
        self._focus_selected_location_is_status = False
        self.focus_selected_title_label = ttk.Label(
            overview,
            textvariable=self.selected_title_display_var,
            wraplength=220,
            justify="left",
            style="FocusActiveTitle.TLabel",
        )
        self.focus_selected_title_label.grid(
            row=0, column=0, sticky="new", padx=(0, 12)
        )
        self.focus_selected_meta_label = ttk.Label(
            overview,
            textvariable=self.selected_meta_display_var,
            wraplength=220,
            justify="left",
            style="Muted.TLabel",
        )
        self.focus_selected_meta_label.grid(
            row=1, column=0, sticky="new", padx=(0, 12), pady=(4, 0)
        )
        self.focus_selected_location_label = ttk.Label(
            overview,
            textvariable=self.selected_location_display_var,
            wraplength=220,
            justify="left",
            style="FocusProfile.TLabel",
        )
        self.focus_selected_location_label.grid(
            row=2, column=0, sticky="new", padx=(0, 12), pady=(4, 0)
        )
        thumbnail_wrap = tk.Frame(
            overview,
            bg=THEME["bg"],
            width=144,
            height=youtube_thumbnail_size(144)[1],
            bd=0,
            highlightthickness=0,
        )
        thumbnail_wrap.grid(row=0, column=1, rowspan=3, sticky="ne")
        # The thumbnail label is packed inside this wrapper, so pack—not Grid—
        # owns child geometry. Disabling the correct propagation keeps the
        # responsive 104/124/144 px artwork cap authoritative.
        thumbnail_wrap.pack_propagate(False)
        self.focus_thumbnail_wrap = thumbnail_wrap
        self.thumbnail_label = tk.Label(
            thumbnail_wrap,
            text="No thumbnail loaded",
            anchor="center",
            bg=THEME["bg"],
            fg=THEME["muted"],
            relief="flat",
            font=FONT_UI,
        )
        self.thumbnail_label.pack(fill="both", expand=True)
        thumbnail_wrap.bind(
            "<Configure>",
            lambda event: self._render_focus_thumbnail_surfaces(
                library_width=event.width
            ),
            add="+",
        )

        def layout_selected_overview(event: tk.Event[Any]) -> None:
            artwork_width = (
                104 if event.height < 300 else 124 if event.width < 380 else 144
            )
            thumbnail_wrap.configure(
                width=artwork_width, height=youtube_thumbnail_size(artwork_width)[1]
            )
            text_width = max(130, event.width - artwork_width - 24)
            self.focus_selected_title_label.configure(wraplength=text_width)
            self.focus_selected_meta_label.configure(wraplength=text_width)
            self.focus_selected_location_label.configure(wraplength=text_width)
            self._focus_selected_text_width = text_width
            self._queue_focus_selected_overview_layout()
            self._queue_focus_description_layout()

        details.bind("<Configure>", layout_selected_overview, add="+")

        tags_line = ttk.Frame(details, style="FocusShell.TFrame")
        tags_line.configure(height=FOCUS_LIBRARY_SELECTED_TAGS_MAX_HEIGHT)
        tags_line.grid_propagate(False)
        tags_line.grid(row=3, column=0, sticky="nsew", pady=(0, 10))
        tags_line.columnconfigure(0, weight=1)
        tags_line.rowconfigure(1, weight=1)
        ttk.Label(tags_line, text="TAGS", style="FocusEyebrow.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        self.pulled_tags_text = tk.Text(
            tags_line,
            height=FOCUS_LIBRARY_SELECTED_TAGS_MAX_VISIBLE_LINES,
            width=1,
            wrap="word",
            bg=THEME["surface"],
            fg=THEME["text"],
            insertbackground=THEME["text"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=9,
            pady=7,
            font=FONT_UI,
        )
        tags_scroll = SleekScrollbar(tags_line, command=self.pulled_tags_text.yview)
        self.pulled_tags_text.configure(yscrollcommand=tags_scroll.set)
        self.pulled_tags_text.grid(row=1, column=0, sticky="nsew")
        tags_scroll.grid(row=1, column=1, sticky="ns", padx=(5, 0))

        description_line = ttk.Frame(details, style="FocusShell.TFrame")
        description_line.grid(row=4, column=0, sticky="nsew")
        description_line.columnconfigure(0, weight=1)
        description_line.rowconfigure(1, weight=1)
        self.focus_description_heading_label = ttk.Label(
            description_line, text="DESCRIPTION", style="FocusEyebrow.TLabel"
        )
        self.focus_description_heading_label.grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        self.description_text = tk.Text(
            description_line,
            height=FOCUS_LIBRARY_SELECTED_DESCRIPTION_VISIBLE_LINES,
            width=1,
            wrap="word",
            bg=THEME["surface"],
            fg=THEME["text"],
            insertbackground=THEME["text"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=9,
            pady=7,
            font=FONT_UI,
        )
        description_scroll = SleekScrollbar(
            description_line, command=self.description_text.yview
        )
        self.description_text.configure(yscrollcommand=description_scroll.set)
        self.description_text.grid(row=1, column=0, sticky="nsew")
        description_scroll.grid(row=1, column=1, sticky="ns", padx=(5, 0))
        self.focus_library_details = details
        self.focus_description_line = description_line
        self._focus_description_layout_after_id: str | None = None
        self._focus_description_bottom_inset: int | None = None
        for layout_owner in (queue_panel, video_tree):
            layout_owner.bind(
                "<Configure>",
                lambda _event: self._queue_focus_description_layout(),
                add="+",
            )
        self._queue_focus_description_layout()

        summary = ttk.Frame(parent, style="FocusShell.TFrame")
        summary.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 10))
        summary.columnconfigure(0, weight=1)
        summary.columnconfigure(1, weight=1)
        summary.rowconfigure(1, weight=1)
        ttk.Label(
            summary, text="SOURCE SELECTED FROM YOUTUBE", style="FocusEyebrow.TLabel"
        ).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=(0, 6))
        ttk.Label(summary, text="FINAL OUTPUT FILE", style="FocusEyebrow.TLabel").grid(
            row=0, column=1, sticky="w", padx=(10, 0), pady=(0, 6)
        )
        self.source_summary_text = tk.Text(
            summary,
            height=8,
            width=1,
            wrap="word",
            state="disabled",
            bg=THEME["surface"],
            fg=THEME["text"],
            insertbackground=THEME["text"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=12,
            pady=10,
            font=FONT_MONO,
        )
        self.output_summary_text = tk.Text(
            summary,
            height=8,
            width=1,
            wrap="word",
            state="disabled",
            bg=THEME["surface"],
            fg=THEME["text"],
            insertbackground=THEME["text"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=12,
            pady=10,
            font=FONT_MONO,
        )
        self.source_summary_text.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        self.output_summary_text.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        self.focus_library_summary = summary
        for text_widget in (
            self.pulled_tags_text,
            self.description_text,
            self.source_summary_text,
            self.output_summary_text,
        ):
            bind_smooth_vertical_wheel(text_widget, mode="pixels")

    def _focus_selected_label_font(self, label: ttk.Label) -> tkfont.Font:
        style_name = str(label.cget("style") or "TLabel")
        font_spec = ttk.Style(self).lookup(style_name, "font") or FONT_UI
        return tkfont.Font(root=self, font=font_spec)

    def _queue_focus_selected_overview_layout(self) -> None:
        if "selected_title_display_var" not in self.__dict__:
            return
        if self.__dict__.get("_focus_selected_overview_layout_after_id") is not None:
            return

        def apply_layout() -> None:
            self._focus_selected_overview_layout_after_id = None
            self._fit_focus_selected_overview_text()

        try:
            self._focus_selected_overview_layout_after_id = self.after_idle(
                apply_layout
            )
        except (AttributeError, tk.TclError):
            apply_layout()

    def _queue_focus_description_layout(self) -> None:
        """Coalesce the measured Description-to-table alignment pass."""

        required = (
            "focus_description_line",
            "focus_library_details",
            "video_tree",
        )
        if any(name not in self.__dict__ for name in required):
            return
        if self.__dict__.get("_focus_description_layout_after_id") is not None:
            return

        def apply_layout() -> None:
            self._focus_description_layout_after_id = None
            self._fit_focus_description_to_library_table()

        try:
            self._focus_description_layout_after_id = self.after_idle(apply_layout)
        except (AttributeError, tk.TclError):
            apply_layout()

    def _fit_focus_description_to_library_table(self) -> None:
        """Cap Description at the measured lower edge of the Library table."""

        required = (
            "focus_description_line",
            "focus_library_details",
            "video_tree",
        )
        if any(name not in self.__dict__ for name in required):
            return
        description_line = self.focus_description_line
        details = self.focus_library_details
        library_table = self.video_tree
        try:
            if not (
                description_line.winfo_ismapped()
                and details.winfo_ismapped()
                and library_table.winfo_ismapped()
            ):
                return
            if (
                min(
                    description_line.winfo_height(),
                    details.winfo_height(),
                    library_table.winfo_height(),
                )
                <= 1
            ):
                return
            description_top = description_line.winfo_rooty()
            details_bottom = details.winfo_rooty() + details.winfo_height()
            library_table_bottom = (
                library_table.winfo_rooty() + library_table.winfo_height()
            )
        except tk.TclError:
            return
        available_height = max(0, details_bottom - description_top)
        maximum_height = selected_description_max_height(
            description_top=description_top,
            library_table_bottom=library_table_bottom,
        )
        if maximum_height <= 1:
            return
        bottom_inset = max(0, available_height - maximum_height)
        if self.__dict__.get("_focus_description_bottom_inset") == bottom_inset:
            return
        description_line.grid_configure(pady=(0, bottom_inset))
        self._focus_description_bottom_inset = bottom_inset

    def _fit_focus_selected_overview_text(self) -> None:
        """Bound selected-item text without letting it displace Description."""

        required = (
            "focus_selected_title_label",
            "focus_selected_meta_label",
            "focus_selected_location_label",
            "selected_title_display_var",
            "selected_meta_display_var",
            "selected_location_display_var",
        )
        if any(name not in self.__dict__ for name in required):
            return
        text_width = max(1, int(self.__dict__.get("_focus_selected_text_width", 220)))
        title = self.selected_title_var.get()
        metadata = self.selected_meta_var.get()
        location = self.selected_location_var.get()
        title_font = self._focus_selected_label_font(self.focus_selected_title_label)
        metadata_font = self._focus_selected_label_font(self.focus_selected_meta_label)
        location_font = self._focus_selected_label_font(
            self.focus_selected_location_label
        )
        overview_height = selected_overview_height(
            title_line_height=title_font.metrics("linespace")
        )
        if self.__dict__.get("_focus_selected_overview_height") != overview_height:
            self.focus_selected_overview.configure(height=overview_height)
            self._focus_selected_overview_height = overview_height
            self._queue_focus_description_layout()
        title_lines = measured_wrapped_line_count(
            title,
            maximum_width=text_width,
            measure_width=title_font.measure,
        )
        metadata_lines = measured_wrapped_line_count(
            metadata,
            maximum_width=text_width,
            measure_width=metadata_font.measure,
        )
        location_lines = measured_wrapped_line_count(
            location,
            maximum_width=text_width,
            measure_width=location_font.measure,
        )
        line_budget = selected_overview_line_budget(
            title_lines=title_lines,
            metadata_lines=metadata_lines,
            location_lines=location_lines,
            available_height=overview_height,
            title_line_height=title_font.metrics("linespace"),
            metadata_line_height=metadata_font.metrics("linespace"),
            location_line_height=location_font.metrics("linespace"),
            protect_location=bool(
                self.__dict__.get("_focus_selected_location_is_status")
            ),
        )
        self.selected_location_display_var.set(
            ellipsize_wrapped_text(
                location,
                maximum_width=text_width,
                maximum_lines=line_budget.location,
                measure_width=location_font.measure,
            )
        )
        displayed_title = ellipsize_wrapped_text(
            title,
            maximum_width=text_width,
            maximum_lines=line_budget.title,
            measure_width=title_font.measure,
        )
        self.selected_title_display_var.set(displayed_title)
        self._focus_selected_displayed_title_lines = measured_wrapped_line_count(
            displayed_title,
            maximum_width=text_width,
            measure_width=title_font.measure,
        )
        self.selected_meta_display_var.set(
            ellipsize_wrapped_text(
                metadata,
                maximum_width=text_width,
                maximum_lines=line_budget.metadata,
                measure_width=metadata_font.measure,
            )
        )

    def _queue_quality_e2e_library_visibility_receipt(self) -> None:
        if not quality_e2e_mode_enabled():
            return
        if self.__dict__.get("_quality_e2e_library_visibility_receipt_path"):
            return
        if self.__dict__.get("_quality_e2e_library_visibility_receipt_scheduled"):
            return
        self._quality_e2e_library_visibility_receipt_scheduled = True

        def record_visibility() -> None:
            self._quality_e2e_library_visibility_receipt_scheduled = False
            self._fit_focus_selected_overview_text()
            try:
                self.update_idletasks()
                self._fit_focus_description_to_library_table()
                self.update_idletasks()
                receipt_path = write_quality_e2e_library_visibility_receipt(
                    details=self.focus_library_details,
                    library_table=self.video_tree,
                    tags_body=self.pulled_tags_text,
                    description_heading=self.focus_description_heading_label,
                    description=self.description_text,
                    full_title=self.selected_title_var.get(),
                    displayed_title=self.selected_title_display_var.get(),
                    displayed_title_visible_lines=int(
                        self.__dict__.get("_focus_selected_displayed_title_lines", 0)
                    ),
                    full_location=self.selected_location_var.get(),
                    displayed_location=self.selected_location_display_var.get(),
                    expected_details_height=FOCUS_LIBRARY_SELECTED_DETAILS_HEIGHT,
                    overview=self.focus_selected_overview,
                    location_label=self.focus_selected_location_label,
                    location_is_status=bool(
                        self.__dict__.get("_focus_selected_location_is_status")
                    ),
                )
            except (AttributeError, QualityE2EAttestationError, tk.TclError) as exc:
                write_diagnostic(
                    "quality-E2E Library visibility receipt failed "
                    f"({type(exc).__name__})"
                )
                return
            if receipt_path is not None:
                self._quality_e2e_library_visibility_receipt_path = str(receipt_path)

        try:
            self.after_idle(record_visibility)
        except (AttributeError, tk.TclError):
            record_visibility()

    def _build_focus_activity_view(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        header = ttk.Frame(parent, style="FocusShell.TFrame")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(24, 12))
        header.columnconfigure(0, weight=1)
        title = ttk.Frame(header, style="FocusShell.TFrame")
        title.grid(row=0, column=0, sticky="w")
        ttk.Label(title, text="Activity", style="FocusTitle.TLabel").pack(anchor="w")
        ttk.Label(title, textvariable=self.status_var, style="Muted.TLabel").pack(
            anchor="w", pady=(3, 0)
        )
        ttk.Button(
            header,
            text="Open log folder",
            command=self._open_log_folder,
            style="FocusQuiet.TButton",
        ).grid(row=0, column=1, sticky="e")
        log_wrap = ttk.Frame(parent, style="FocusShell.TFrame")
        log_wrap.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 10))
        log_wrap.columnconfigure(0, weight=1)
        log_wrap.rowconfigure(1, weight=1)
        ttk.Label(
            log_wrap,
            text="PERSISTENT LOCAL DOWNLOAD AND PROCESSING LOG",
            style="FocusEyebrow.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.log = tk.Text(
            log_wrap,
            height=1,
            width=1,
            wrap="word",
            state="disabled",
            bg=THEME["bg"],
            fg=THEME["muted"],
            insertbackground=THEME["text"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=0,
            pady=6,
            font=FONT_MONO,
        )
        log_scrollbar = SleekScrollbar(log_wrap, command=self.log.yview)
        self.log.configure(yscrollcommand=log_scrollbar.set)
        self.log.grid(row=1, column=0, sticky="nsew")
        log_scrollbar.grid(row=1, column=1, sticky="ns", padx=(6, 0))
        bind_smooth_vertical_wheel(self.log, self.log, log_scrollbar, mode="pixels")

    def _set_focus_run_controls_visible(self, visible: bool) -> None:
        controls = getattr(self, "focus_run_controls", ())
        for control in controls:
            control.grid_remove()

    def _select_focus_view(self, name: str) -> None:
        frame = self._focus_views.get(name)
        if frame is None:
            return
        frame.tkraise()
        for view_name, button in self._focus_nav_buttons.items():
            active = view_name == name
            inactive_icon, active_icon = self._focus_nav_icons.get(
                view_name, (None, None)
            )
            icon = active_icon if active else inactive_icon
            button.configure(
                style="FocusNavActive.TButton" if active else "FocusNav.TButton",
                image=icon if icon is not None else "",
            )
            underline = self._focus_nav_underlines.get(view_name)
            if underline is not None:
                underline.configure(bg=THEME["accent"] if active else THEME["bg"])
        self._focus_selected_view = name
        if name == "library":
            self._queue_focus_selected_overview_layout()
            self._queue_quality_e2e_library_visibility_receipt()
        if name == "activity":
            activity_log = self.__dict__.get("log")
            if activity_log is not None:
                set_user_scroll_locked(activity_log, False)

                def show_latest_activity() -> None:
                    try:
                        activity_log.see("end")
                    except (AttributeError, tk.TclError):
                        pass

                try:
                    activity_log.after_idle(show_latest_activity)
                except (AttributeError, tk.TclError):
                    show_latest_activity()

    def _activate_focus_view_shortcut(
        self,
        name: str,
        _event: tk.Event[Any] | None = None,
    ) -> str:
        self._select_focus_view(name)
        return "break"

    def _bind_focus_view_shortcuts(self) -> None:
        for sequence, view_name in focus_view_shortcut_bindings():
            self.bind(
                sequence,
                partial(self._activate_focus_view_shortcut, view_name),
                add="+",
            )

    def _sync_focus_destination(self) -> None:
        path = self.output_var.get().strip() or "Choose destination"
        max_chars = 34 if self._focus_layout == "compact" else 52
        if len(path) > max_chars:
            path = "..." + path[-(max_chars - 3) :]
        self.focus_output_display_var.set(path)
        if (
            hasattr(self, "focus_summary_text")
            and self._focus_shows_next_run_defaults()
        ):
            current = self.focus_summary_text.get("1.0", "end").strip().splitlines()
            retained = [line for line in current if not line.startswith("Save to")]
            retained.append(f"Save to       {self.output_var.get()}")
            self._set_text(self.focus_summary_text, "\n".join(retained), disabled=True)

    def _selected_output_type(self) -> OutputType:
        try:
            return OutputType(self.output_type_var.get())
        except ValueError:
            self.output_type_var.set(OutputType.MP4.value)
            return OutputType.MP4

    def _selected_cookie_source(self) -> CookieSource:
        try:
            return CookieSource(self.cookie_source_var.get())
        except ValueError:
            self.cookie_source_var.set(CookieSource.PUBLIC.value)
            return CookieSource.PUBLIC

    def _cookie_inputs(self) -> tuple[bool, Path | None, str | None]:
        return cookie_inputs_for_source(
            self._selected_cookie_source(),
            self.cookie_file_path,
            self.cookie_browser_var.get(),
        )

    def _on_cookie_source_changed(self) -> None:
        source = self._selected_cookie_source()
        dialog = self.__dict__.get("_focus_settings_dialog")
        if dialog is not None:
            dialog.refresh_cookie_source(source)

    def _on_browser_cookie_selected(self) -> None:
        source = (
            CookieSource.BROWSER
            if browser_cookie_value(self.cookie_browser_var.get())
            else CookieSource.PUBLIC
        )
        self.cookie_source_var.set(source.value)

    def _mp3_export_settings(self) -> Mp3ExportSettings:
        quality_label = self.mp3_quality_var.get()
        sample_rate_label = self.mp3_sample_rate_var.get()
        channels_label = self.mp3_channels_var.get()
        if quality_label not in MP3_QUALITY_OPTIONS:
            raise ValueError("Choose a valid MP3 quality setting.")
        if sample_rate_label not in MP3_SAMPLE_RATE_OPTIONS:
            raise ValueError("Choose a valid MP3 sample-rate setting.")
        if channels_label not in MP3_CHANNEL_OPTIONS:
            raise ValueError("Choose a valid MP3 channel setting.")
        cover_mode = self.mp3_cover_art_mode_var.get()
        if cover_mode not in MP3_COVER_ART_OPTIONS:
            raise ValueError("Choose a valid MP3 cover-art setting.")
        custom_cover = (
            self.mp3_custom_cover_art_path if cover_mode == "Custom art" else None
        )
        if custom_cover is not None:
            custom_cover = validate_custom_cover_art(custom_cover)
        if cover_mode == "Custom art" and custom_cover is None:
            raise ValueError("Choose a custom cover image or select No Art.")
        return Mp3ExportSettings(
            bitrate_kbps=MP3_QUALITY_OPTIONS[quality_label],
            sample_rate=MP3_SAMPLE_RATE_OPTIONS[sample_rate_label],
            channels=MP3_CHANNEL_OPTIONS[channels_label],
            embed_metadata=self.mp3_embed_metadata_var.get(),
            embed_cover_art=cover_mode == "YouTube art",
            custom_cover_art_path=custom_cover,
        )

    def _choose_mp3_custom_cover_art(self) -> bool:
        selected = filedialog.askopenfilename(
            title="Choose custom MP3 cover art",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.webp"),
                ("JPEG", "*.jpg *.jpeg"),
                ("PNG", "*.png"),
                ("WebP", "*.webp"),
                ("All files", "*.*"),
            ],
        )
        if not selected:
            return False
        try:
            cover_path = validate_custom_cover_art(Path(selected))
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return False
        self.mp3_custom_cover_art_path = cover_path
        self.mp3_custom_cover_art_var.set(cover_path.name)
        if self.mp3_cover_art_mode_var.get() != "Custom art":
            self.mp3_cover_art_mode_var.set("Custom art")
        self._sync_focus_settings_summary()
        return True

    def _clear_mp3_custom_cover_art(self) -> None:
        self.mp3_custom_cover_art_path = None
        self.mp3_custom_cover_art_var.set("Select Custom art to choose an image")
        if self.mp3_cover_art_mode_var.get() == "Custom art":
            self.mp3_cover_art_mode_var.set("No Art")
        self._sync_focus_settings_summary()

    def _on_mp3_cover_mode_changed(self) -> None:
        mode = self.mp3_cover_art_mode_var.get()
        if mode not in MP3_COVER_ART_OPTIONS:
            self.mp3_cover_art_mode_var.set("No Art")
            return
        if (
            mode == "Custom art"
            and self.mp3_custom_cover_art_path is None
            and not self._choose_mp3_custom_cover_art()
        ):
            self.mp3_cover_art_mode_var.set("No Art")
            return
        descriptions = {
            "No Art": "No image is embedded in the MP3. VODForge still keeps the YouTube thumbnail privately for Forge and Library.",
            "YouTube art": "Embeds the video's YouTube thumbnail in the MP3 and also uses it inside VODForge.",
            "Custom art": "Embeds your image and uses that same image for this run in Forge and Library.",
        }
        self.mp3_cover_art_description_var.set(descriptions[mode])
        dialog = self.__dict__.get("_focus_settings_dialog")
        if dialog is not None:
            dialog.refresh_cover_art_mode(mode)
        self._sync_focus_settings_summary()

    def _focus_profile_text(
        self,
        output_type: OutputType | None = None,
        *,
        mp3_settings: Mp3ExportSettings | None = None,
        quality_label: str | None = None,
        export_mode: ExportMode | None = None,
    ) -> str:
        output_type = output_type or self._selected_output_type()
        if output_type == OutputType.MP3:
            settings = mp3_settings or self._mp3_export_settings()
            rate = f"{settings.bitrate_kbps} kbps"
            sample_rate = mp3_sample_rate_display(
                settings.sample_rate,
                source_label="Source rate",
            )
            return f"MP3  •  {rate}  •  {sample_rate}"
        return f"{quality_label or self.quality_var.get()}  •  {(export_mode or ExportMode(self.export_mode_var.get())).value}"

    def _on_output_type_changed(self) -> None:
        self._sync_focus_settings_summary()
        self._refresh_output_specific_settings()

    def _on_export_mode_choice_changed(self) -> None:
        try:
            mode = export_mode_from_display_name(self.export_mode_choice_var.get())
        except ValueError:
            mode = ExportMode.AUTO_CBR
            recommended = export_mode_display_name(mode)
            if self.export_mode_choice_var.get() != recommended:
                self.export_mode_choice_var.set(recommended)
                return
        self.export_mode_description_var.set(export_mode_description(mode))
        if self.export_mode_var.get() != mode.value:
            self.export_mode_var.set(mode.value)
        self._refresh_manual_settings_visibility()

    def _on_library_output_type_changed(self) -> None:
        try:
            output_type = OutputType(self.library_output_type_var.get())
        except ValueError:
            output_type = OutputType.MP4
            self.library_output_type_var.set(output_type.value)
        if hasattr(self, "focus_library_media_label_var"):
            self.focus_library_media_label_var.set(
                "MP4 MEDIA" if output_type == OutputType.MP4 else "MP3 AUDIO"
            )
        if hasattr(self, "video_tree"):
            self._render_metadata_tree()

    def _sync_focus_settings_summary(self) -> None:
        output_type = self._selected_output_type()
        if output_type == OutputType.MP3:
            cover = self.mp3_cover_art_mode_var.get()
            summary = f"Press Return to start  /  MP3 audio  /  {self.mp3_quality_var.get()}  /  {self.mp3_sample_rate_var.get()}  /  {cover}"
        else:
            summary = f"Press Return to start  /  {self.quality_var.get()}  /  {self.export_mode_var.get()}"
        if self.batch_urls:
            summary += f"  /  {len(self.batch_urls)} URLs loaded"
        self.focus_command_hint_var.set(summary)
        if self._focus_shows_next_run_defaults():
            self.focus_active_profile_var.set(self._focus_profile_text(output_type))
            if not self.focus_active_detail_var.get().strip():
                self.focus_active_detail_var.set("Ready")
            self.focus_transfer_var.set(self._focus_next_run_transfer_text(output_type))
            summary_widget = self.__dict__.get("focus_summary_text")
            if summary_widget is not None:
                self._set_text(
                    summary_widget,
                    self._focus_next_run_summary(output_type),
                    disabled=True,
                )

    def _refresh_output_specific_settings(self) -> None:
        output_type = self._selected_output_type()
        dialog = self.__dict__.get("_focus_settings_dialog")
        if dialog is not None:
            dialog.refresh_output_sections(output_type)
        self._refresh_manual_settings_visibility()

    def _sync_focus_duration_badge(self) -> None:
        label = self.__dict__.get("focus_active_duration_label")
        if label is None:
            return
        if self.focus_active_duration_var.get().strip():
            label.place(relx=0.96, rely=0.91, anchor="se")
        else:
            label.place_forget()

    def _sync_focus_progress(self) -> None:
        try:
            value = max(0.0, min(100.0, float(self.progress_var.get())))
        except (TypeError, ValueError, tk.TclError):
            value = 0.0
        if self._focus_follows_active_run():
            self.focus_display_progress_var.set(value)
            self.focus_percent_var.set(f"{value:.0f}%")
        focus_active_override = bool(self.__dict__.get("_focus_active_override", False))
        worker = self.__dict__.get("worker")
        if bool(focus_active_override or (worker and worker.is_alive())):
            self.focus_run_status_var.set(f"{value:.0f}%  /  Active")

    def _sync_focus_status(self) -> None:
        if self._focus_follows_active_run():
            self.focus_display_status_var.set(self.status_var.get())

    def _focus_follows_active_run(self) -> bool:
        selected_run_id = self.__dict__.get("_focus_selected_run_id")
        active_job = self.__dict__.get("active_job")
        if isinstance(active_job, DownloadJob) and self._library_run_is_suppressed(
            active_job
        ):
            return False
        return selected_run_id is None or (
            active_job is not None and selected_run_id == active_job.run_id
        )

    def _focus_shows_next_run_defaults(self) -> bool:
        """Return true only when Forge is showing its neutral, unowned hero."""
        selected_run_id = str(self.__dict__.get("_focus_selected_run_id") or "").strip()
        worker = self.__dict__.get("worker")
        active_job = self.__dict__.get("active_job")
        active_run_suppressed = isinstance(
            active_job, DownloadJob
        ) and self._library_run_is_suppressed(active_job)
        return (
            not selected_run_id
            and not bool(self.__dict__.get("_focus_active_override", False))
            and (active_run_suppressed or not bool(worker and worker.is_alive()))
        )

    def _focus_next_run_summary(self, output_type: OutputType) -> str:
        """Describe pending input settings without borrowing from a run snapshot."""
        if output_type == OutputType.MP3:
            return "\n".join(
                (
                    "Format        MP3",
                    "Audio         Best YouTube source",
                    f"Output mode   {self.mp3_quality_var.get()}",
                    f"Sample rate   {self.mp3_sample_rate_var.get()}",
                    f"Save to       {self.output_var.get()}",
                )
            )
        try:
            export_mode = ExportMode(self.export_mode_var.get())
        except ValueError:
            export_mode = ExportMode.AUTO_CBR
        audio_codec = self._focus_next_run_mp4_audio_codec(export_mode)
        return "\n".join(
            (
                "Format        MP4",
                "Video         H.264",
                f"Audio         {audio_codec}",
                f"Output mode   {export_mode.value}",
                f"Save to       {self.output_var.get()}",
            )
        )

    def _focus_next_run_transfer_text(self, output_type: OutputType) -> str:
        if output_type == OutputType.MP3:
            return "Audio-only MP3  /  best YouTube audio source"
        return f"VOD-ready MP4 / H.264 video / {self._focus_next_run_mp4_audio_codec()} audio"

    def _focus_next_run_mp4_audio_codec(
        self, export_mode: ExportMode | None = None
    ) -> str:
        if export_mode is None:
            try:
                export_mode = ExportMode(self.export_mode_var.get())
            except ValueError:
                export_mode = ExportMode.AUTO_CBR
        if export_mode != ExportMode.MANUAL_OVERRIDE:
            return ManualAudioCodec.AAC.value
        try:
            return ManualAudioCodec(self.manual_audio_codec_var.get()).value
        except ValueError:
            return ManualAudioCodec.AAC.value

    def _reset_source_input_after_send(self) -> None:
        """Prepare the source field for the next run after a job is accepted."""
        self.batch_urls = []
        self.url_list_file_var.set("No URL list loaded")
        self.url_var.set("")
        source_entry = self.__dict__.get("focus_url_entry") or self.__dict__.get(
            "url_entry"
        )
        if source_entry is not None:
            source_entry.focus_set()

    def _record_cloud_cta_seen(self) -> None:
        state = self.installation_state
        if state is None or state.cloud_seen_confirmed or self._closing:
            return
        existing = self._cloud_seen_worker
        if existing is not None and existing.is_alive():
            return

        def worker() -> None:
            success = record_cloud_seen(state, app_version=__version__)
            self.events.put(
                installation_result_event(
                    "cloud_seen_result",
                    success,
                    state.install_id,
                )
            )

        self._cloud_seen_worker = threading.Thread(target=worker, daemon=True)
        self._cloud_seen_worker.start()

    def _record_first_launch(self) -> None:
        state = self.installation_state
        if state is None or state.first_launch_confirmed or self._closing:
            return
        existing = self._first_launch_worker
        if existing is not None and existing.is_alive():
            return

        def worker() -> None:
            success = record_first_launch(state, app_version=__version__)
            self.events.put(
                installation_result_event(
                    "first_launch_result",
                    success,
                    state.install_id,
                )
            )

        self._first_launch_worker = threading.Thread(target=worker, daemon=True)
        self._first_launch_worker.start()

    def _open_cloud_early_access(self) -> None:
        state = self.installation_state
        destination = cloud_page_url(state.install_id if state is not None else None)
        if state is not None:
            threading.Thread(
                target=record_cloud_click, args=(state,), daemon=True
            ).start()
        try:
            opened = webbrowser.open(destination)
            if not opened:
                write_diagnostic(
                    "Cloud early-access page was handed to the OS but no browser confirmed opening"
                )
        except Exception as exc:  # noqa: BLE001 - OS browser adapters raise platform-specific errors
            write_diagnostic(f"Cloud early-access page could not be opened: {exc}")

    def _focus_settings_bindings(self) -> FocusSettingsBindings:
        return FocusSettingsBindings(
            output=self.output_var,
            url_list_file=self.url_list_file_var,
            single_video_only=self.single_video_only_var,
            cookie_source=self.cookie_source_var,
            cookie_file=self.cookie_file_var,
            cookie_browser=self.cookie_browser_var,
            tags=self.tags_var,
            quality=self.quality_var,
            export_mode_choice=self.export_mode_choice_var,
            export_mode_description=self.export_mode_description_var,
            manual_video_bitrate=self.manual_video_bitrate_var,
            manual_audio_bitrate=self.manual_audio_bitrate_var,
            manual_audio_codec=self.manual_audio_codec_var,
            manual_sample_rate=self.manual_sample_rate_var,
            manual_channels=self.manual_channels_var,
            manual_preset=self.manual_preset_var,
            write_thumbnail=self.write_thumbnail_var,
            write_info_json=self.write_info_json_var,
            embed_thumbnail=self.embed_thumbnail_var,
            embed_metadata=self.embed_metadata_var,
            use_nvenc=self.use_nvenc_var,
            mp3_quality=self.mp3_quality_var,
            mp3_sample_rate=self.mp3_sample_rate_var,
            mp3_channels=self.mp3_channels_var,
            mp3_embed_metadata=self.mp3_embed_metadata_var,
            mp3_cover_art_mode=self.mp3_cover_art_mode_var,
            mp3_cover_art_description=self.mp3_cover_art_description_var,
            mp3_custom_cover_art=self.mp3_custom_cover_art_var,
        )

    @staticmethod
    def _focus_settings_options() -> FocusSettingsOptions:
        return FocusSettingsOptions(
            quality=tuple(QUALITY_OPTIONS),
            export_modes=tuple(EXPORT_MODES),
            manual_audio_codecs=tuple(codec.value for codec in ManualAudioCodec),
            cookie_sources=COOKIE_SOURCE_OPTIONS,
            cookie_browsers=tuple(COOKIE_BROWSER_OPTIONS),
            mp3_quality=tuple(MP3_QUALITY_OPTIONS),
            mp3_sample_rates=tuple(MP3_SAMPLE_RATE_OPTIONS),
            mp3_channels=tuple(MP3_CHANNEL_OPTIONS),
            mp3_cover_art=MP3_COVER_ART_OPTIONS,
        )

    def _focus_settings_actions(self) -> FocusSettingsActions:
        return FocusSettingsActions(
            browse_output=self._browse_output,
            load_url_list_file=self._load_url_list_file,
            load_cookie_file=self._load_cookie_file,
            browser_cookie_selected=self._on_browser_cookie_selected,
            refresh_manual_visibility=self._refresh_manual_settings_visibility,
            choose_custom_cover_art=self._choose_mp3_custom_cover_art,
            clear_custom_cover_art=self._clear_mp3_custom_cover_art,
            open_cloud_early_access=self._open_cloud_early_access,
            preview_metadata=self._fetch_metadata,
            record_cloud_cta_seen=self._record_cloud_cta_seen,
            on_closed=self._focus_settings_closed,
        )

    def _focus_settings_closed(self) -> None:
        self._focus_settings_dialog = None

    def _show_focus_settings(self) -> None:
        existing = self._focus_settings_dialog
        if existing is not None and existing.focus_existing():
            return

        if is_macos():
            self.use_nvenc_var.set(False)
        dialog = FocusSettingsDialog(
            self,
            app_name=APP_NAME,
            bindings=self._focus_settings_bindings(),
            options=self._focus_settings_options(),
            actions=self._focus_settings_actions(),
            macos=is_macos(),
        )
        self._focus_settings_dialog = dialog
        self._on_cookie_source_changed()
        self._on_mp3_cover_mode_changed()
        self._refresh_output_specific_settings()
        dialog.show()

    def _show_focus_output_details(self) -> None:
        popup = tk.Toplevel(self)
        popup.withdraw()
        popup.title(f"{APP_NAME} Output Details")
        popup.transient(self)
        popup.configure(bg=THEME["bg"])
        popup.resizable(True, True)
        popup.minsize(480, 300)
        frame = ttk.Frame(popup, style="FocusShell.TFrame")
        frame.pack(fill="both", expand=True, padx=18, pady=18)
        ttk.Label(frame, text="Output details", style="FocusTitle.TLabel").pack(
            anchor="w"
        )
        text = tk.Text(
            frame,
            height=10,
            width=52,
            wrap="word",
            state="normal",
            bg=THEME["surface"],
            fg=THEME["text"],
            insertbackground=THEME["text"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=12,
            pady=10,
            font=FONT_MONO,
        )
        text.pack(fill="both", expand=True, pady=(12, 12))
        text.insert("1.0", self.focus_summary_text.get("1.0", "end").strip())
        text.configure(state="disabled")
        bind_smooth_vertical_wheel(text, mode="pixels")
        ttk.Button(
            frame, text="Done", command=popup.destroy, style="Accent.TButton"
        ).pack(anchor="e")
        popup.update_idletasks()
        reveal_toplevel(popup, centered_toplevel_geometry(self, 560, 360))

    def _cancel_focus_run_menu_close(self) -> None:
        after_id = self.__dict__.pop("_focus_run_list_close_after_id", None)
        if after_id is not None:
            try:
                self.after_cancel(after_id)
            except tk.TclError:
                pass

    def _schedule_focus_run_menu_close(self) -> None:
        self._cancel_focus_run_menu_close()

        def close_if_pointer_left() -> None:
            self._focus_run_list_close_after_id = None
            popup = self.__dict__.get("_focus_run_list_window")
            if popup is None or not popup.winfo_exists():
                return
            button = self.focus_run_overflow_button
            try:
                pointer_x, pointer_y = self.winfo_pointerxy()
                hovered = self.winfo_containing(pointer_x, pointer_y)
                hovered_path = str(hovered or "")
                inside_popup = hovered_path == str(popup) or hovered_path.startswith(
                    f"{popup}."
                )
                if hovered is button or inside_popup:
                    return
            except tk.TclError:
                return
            cleanup = self.__dict__.get("_focus_run_list_cleanup")
            if callable(cleanup):
                cleanup()

        # A tiny bridge lets the pointer cross the visual gap between the
        # button and its drop-up without flicker; closure is still immediate
        # once the pointer is outside both surfaces.
        self._focus_run_list_close_after_id = self.after(40, close_if_pointer_left)

    def _show_focus_run_menu(self) -> None:
        records = self._focus_run_records()
        existing = self.__dict__.get("_focus_run_list_window")
        if existing is not None and existing.winfo_exists():
            self._cancel_focus_run_menu_close()
            return

        # Keep the drop-up inside the application window. Aqua does not
        # reliably deliver trackpad gestures to an override-redirect Toplevel,
        # while in-window widgets follow the same working wheel path as the
        # Library table. The list remains capped at five visible rows.
        popup = tk.Frame(self, bg=THEME["border"], bd=0, highlightthickness=0)
        self._focus_run_list_window = popup

        def close_drop_up() -> None:
            self._cancel_focus_run_menu_close()
            if self.__dict__.get("_focus_run_list_cleanup") is close_drop_up:
                self._focus_run_list_cleanup = None
            self._focus_run_list_window = None
            try:
                popup.destroy()
            except tk.TclError:
                pass

        root = tk.Frame(popup, bg=THEME["surface"], bd=0, highlightthickness=0)
        root.pack(fill="both", expand=True, padx=1, pady=1)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        visible_rows = min(5, max(1, len(records)))
        row_height = 31
        run_list = tk.Canvas(
            root,
            height=visible_rows * row_height,
            width=1,
            bg=THEME["surface"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            yscrollincrement=1,
            takefocus=True,
        )
        run_scroll = SleekScrollbar(root, command=run_list.yview)
        run_list.configure(yscrollcommand=run_scroll.set)
        run_list.grid(row=0, column=0, sticky="nsew", padx=(14, 6), pady=12)
        run_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=10)

        selected_run_id = str(self._focus_selected_run_id or "").strip()
        selected_index = next(
            (
                index
                for index, record in enumerate(records)
                if selected_run_id
                and str(record.get("run_id") or "").strip() == selected_run_id
            ),
            -1,
        )
        row_rectangles: list[int] = []
        if records:
            for index, record in enumerate(records):

                def choose_run(
                    _event: tk.Event[Any],
                    item: dict[str, Any] = record,
                ) -> None:
                    self._focus_select_run_record(item)
                    close_drop_up()

                title = str(record.get("title") or "Untitled run")
                status = str(record.get("status") or "Ready")
                row_tag = f"run-row-{index}"
                top = index * row_height
                rectangle = run_list.create_rectangle(
                    0,
                    top,
                    1,
                    top + row_height - 1,
                    fill=THEME["accent_dark"]
                    if index == selected_index
                    else THEME["surface"],
                    outline="",
                    tags=(row_tag,),
                )
                row_rectangles.append(rectangle)
                label = f"{title}  —  {status}"
                if len(label) > 58:
                    label = f"{label[:55]}..."
                run_list.create_text(
                    10,
                    top + (row_height / 2),
                    text=label,
                    anchor="w",
                    fill=THEME["text"],
                    font=FONT_UI,
                    tags=(row_tag,),
                )
                run_list.tag_bind(
                    row_tag,
                    "<Button-1>",
                    choose_run,
                )

                def show_hover(
                    _event: Any,
                    *,
                    item_index: int = index,
                    item_rectangle: int = rectangle,
                ) -> None:
                    if item_index != selected_index:
                        run_list.itemconfigure(item_rectangle, fill=THEME["surface_2"])

                def hide_hover(
                    _event: Any,
                    *,
                    item_index: int = index,
                    item_rectangle: int = rectangle,
                ) -> None:
                    fill = (
                        THEME["accent_dark"]
                        if item_index == selected_index
                        else THEME["surface"]
                    )
                    run_list.itemconfigure(item_rectangle, fill=fill)

                run_list.tag_bind(row_tag, "<Enter>", show_hover)
                run_list.tag_bind(row_tag, "<Leave>", hide_hover)
        else:
            run_list.create_text(
                10,
                row_height / 2,
                text="No runs yet",
                anchor="w",
                fill=THEME["muted"],
                font=FONT_UI,
            )

        run_list.configure(
            scrollregion=(0, 0, 1, max(row_height, len(records) * row_height))
        )

        def resize_rows(event: tk.Event[Any]) -> None:
            for index, rectangle in enumerate(row_rectangles):
                top = index * row_height
                run_list.coords(
                    rectangle, 0, top, max(1, event.width), top + row_height - 1
                )
            run_list.configure(
                scrollregion=(
                    0,
                    0,
                    max(1, event.width),
                    max(row_height, len(records) * row_height),
                )
            )

        run_list.bind("<Configure>", resize_rows, add="+")

        self._focus_run_list_cleanup = close_drop_up

        run_list.bind("<Escape>", lambda _event: close_drop_up())
        bind_smooth_vertical_wheel(
            run_list,
            popup,
            root,
            run_list,
            run_scroll,
            mode="increments",
        )
        popup.bind("<Escape>", lambda _event: close_drop_up())
        popup.bind(
            "<Enter>", lambda _event: self._cancel_focus_run_menu_close(), add="+"
        )
        popup.bind(
            "<Leave>", lambda _event: self._schedule_focus_run_menu_close(), add="+"
        )

        button = self.focus_run_overflow_button
        button.update_idletasks()
        popup.update_idletasks()
        width = min(440, max(340, self.winfo_width() - 48))
        height = min(184, max(78, popup.winfo_reqheight()))
        x = button.winfo_rootx() - self.winfo_rootx() + button.winfo_width() - width
        x = min(self.winfo_width() - width - 12, max(12, x))
        # The in-window drop-up can sit flush with the trigger. This removes
        # the geometric dead zone instead of asking a short timer to hide it.
        y = button.winfo_rooty() - self.winfo_rooty() - height + 1
        if y < 20:
            y = min(
                self.winfo_height() - height - 20,
                button.winfo_rooty() - self.winfo_rooty() + button.winfo_height() - 1,
            )
        popup.place(x=x, y=y, width=width, height=height)
        popup.lift()
        run_list.focus_set()

    def _focus_select_run_record(self, record: dict[str, Any]) -> None:
        run_id = str(record.get("run_id") or "")
        record_kind = str(record.get("kind") or "")
        self._focus_selected_run_id = run_id or None
        self._set_focus_preview_start_action(None)
        if record_kind == "active":
            active_job = self.active_job
            if active_job is not None and (not run_id or run_id == active_job.run_id):
                self._display_focus_job_snapshot(active_job)
            return

        if record_kind == "queued":
            queued_job = next(
                (job for job in self.pending_jobs if job.run_id == run_id), None
            )
            if queued_job is not None:
                self._display_focus_queued_job_snapshot(record, queued_job)
            return

        if record_kind in {"preview_loading", "preview_failed"}:
            self._display_metadata_preview_request(record)
            return

        if record_kind in {"failed", "skipped", "stopped"} and isinstance(
            record.get("job"), DownloadJob
        ):
            metadata_index = record.get("metadata_index")
            info = (
                self.metadata_items[int(metadata_index)]
                if metadata_index is not None
                and 0 <= int(metadata_index) < len(self.metadata_items)
                else record["job"].preview_info or {}
            )
            self._display_focus_metadata_snapshot(record, info)
            return

        if record.get("metadata_index") is not None:
            index = int(record["metadata_index"])
            if 0 <= index < len(self.metadata_items):
                self._display_focus_metadata_snapshot(
                    record, self.metadata_items[index]
                )

    def _render_focus_run_activity(self, run_id: str, text: str) -> None:
        """Render one run's activity without letting refreshes steal its viewport."""
        owner = str(run_id or "")
        widget = self.focus_log
        same_owner = self.__dict__.get("_focus_log_owner_run_id") == owner
        if same_owner and self.__dict__.get("_focus_log_rendered_text") == text:
            return

        first = 0.0
        last = 1.0
        if same_owner:
            try:
                first, last = (float(value) for value in widget.yview())
            except (AttributeError, TypeError, ValueError, tk.TclError):
                first, last = 0.0, 1.0

        self._set_text(widget, text, disabled=True)
        self._focus_log_owner_run_id = owner
        self._focus_log_rendered_text = text
        if same_owner:
            try:
                if (
                    bool(getattr(widget, "_vodforge_user_scroll_locked", False))
                    or last < 0.995
                ):
                    widget.yview_moveto(first)
                else:
                    widget.see("end")
            except (AttributeError, TypeError, ValueError, tk.TclError):
                pass
        else:
            set_user_scroll_locked(widget, False)
            try:
                widget.see("end")
            except (AttributeError, TypeError, ValueError, tk.TclError):
                pass

    def _display_focus_queued_job_snapshot(
        self, record: dict[str, Any], job: DownloadJob
    ) -> None:
        """Render one queued run without borrowing state from the active run."""
        self._focus_selected_run_id = job.run_id
        self._set_focus_preview_start_action(None)
        self._set_focus_progress_color()
        info = job.preview_info or {}
        title = download_job_display_title(job, queued=True)
        creator = str(
            info.get("uploader") or info.get("channel") or "Waiting for source metadata"
        )
        self.focus_active_title_var.set(title)
        self.focus_active_detail_var.set(creator)
        duration = format_duration(info.get("duration"))
        self.focus_active_duration_var.set("" if duration == "—" else duration)
        self.focus_active_profile_var.set(
            self._focus_profile_text(
                job.output_type,
                mp3_settings=job.mp3_settings,
                quality_label=job.quality_label,
                export_mode=job.export_mode,
            )
        )
        self.focus_display_progress_var.set(0)
        self.focus_percent_var.set("Queued")
        self.focus_display_status_var.set(f"Showing queued run: {title}")
        self.focus_transfer_var.set("Queued  /  Waiting for the current run")
        if job.output_type == OutputType.MP3:
            sample_rate = mp3_sample_rate_display(
                job.mp3_settings.sample_rate,
                source_label="Preserve source",
            )
            channels = (
                "Preserve source"
                if job.mp3_settings.channels is None
                else str(job.mp3_settings.channels)
            )
            summary = "\n".join(
                (
                    "Format          MP3",
                    f"Audio quality   {job.mp3_settings.bitrate_kbps} kbps",
                    f"Sample rate     {sample_rate}",
                    f"Channels        {channels}",
                    f"Save to         {job.output_dir}",
                    "Status          Queued",
                )
            )
        else:
            summary = "\n".join(
                (
                    "Format          MP4",
                    f"Quality ceiling {job.quality_label}",
                    f"Output mode     {job.export_mode.value}",
                    f"Save to         {job.output_dir}",
                    "Status          Queued",
                )
            )
        self._set_text(self.focus_summary_text, summary, disabled=True)
        self._render_focus_run_activity(
            job.run_id,
            "\n".join(job.activity_lines)
            or "Queued. This run will begin after the current run finishes.",
        )
        self._display_focus_record_thumbnail(record, info)

    def _select_record_in_library(self, record: dict[str, Any]) -> None:
        metadata_index = record.get("metadata_index")
        if metadata_index is None:
            return
        index = int(metadata_index)
        if not 0 <= index < len(self.metadata_items):
            return
        output_type = metadata_output_type(self.metadata_items[index])
        if self.library_output_type_var.get() != output_type.value:
            self.library_output_type_var.set(output_type.value)
        iid = str(index)
        if iid not in self.video_tree.get_children():
            self._render_metadata_tree(selected_index=index)
        if iid in self.video_tree.get_children():
            self.video_tree.selection_set(iid)
            _focus_library_table_item(self.video_tree, iid)
        self._display_selected_metadata(index)

    def _start_preview_record(self, record: dict[str, Any]) -> None:
        metadata_index = record.get("metadata_index")
        if metadata_index is None:
            return
        try:
            info = self.metadata_items[int(metadata_index)]
        except (IndexError, TypeError, ValueError):
            return
        if is_metadata_preview(info):
            self._start_preview_download(info)

    def _start_selected_preview_download(self) -> None:
        info = self.__dict__.get("_focus_selected_preview_info")
        if isinstance(info, dict) and is_metadata_preview(info):
            self._start_preview_download(info)

    def _set_focus_preview_start_action(self, info: dict[str, Any] | None) -> None:
        is_preview = is_metadata_preview(info)
        self._focus_selected_preview_info = (
            dict(info) if is_preview and info is not None else None
        )
        percent_label = self.__dict__.get("focus_percent_label")
        start_button = self.__dict__.get("focus_preview_start_button")
        if percent_label is None or start_button is None:
            return
        if is_preview:
            start_button.configure(
                text="Start download", command=self._start_selected_preview_download
            )
            percent_label.grid_remove()
            start_button.grid()
        else:
            start_button.grid_remove()
            percent_label.grid()

    def _set_focus_terminal_action(self, job: DownloadJob, status: str) -> None:
        """Replace terminal percent text with the canonical fresh-run action."""
        self._focus_selected_preview_info = None
        percent_label = self.__dict__.get("focus_percent_label")
        action_button = self.__dict__.get("focus_preview_start_button")
        if percent_label is None or action_button is None:
            return
        label = "Retry Download" if status == "Failed" else "Restart Download"
        action_button.configure(
            text=label, command=lambda: self._retry_terminal_job(job)
        )
        percent_label.grid_remove()
        action_button.grid()

    def _set_focus_progress_color(self, color: str = THEME["accent"]) -> None:
        progress_bar = self.__dict__.get("progress_bar")
        if progress_bar is not None:
            progress_bar.configure(bar_color=color)

    def _display_metadata_preview_request(self, record: dict[str, Any]) -> None:
        """Show a metadata request without turning it into a media-run authority."""
        failed = str(record.get("kind")) == "preview_failed"
        output_type = str(record.get("output_type") or "MP4")
        self._set_focus_preview_start_action(None)
        self._set_focus_progress_color()
        self.focus_active_title_var.set(
            "Preview failed" if failed else "Loading preview…"
        )
        self.focus_active_detail_var.set(
            "Check the message below"
            if failed
            else "Fetching title, creator, and thumbnail"
        )
        self.focus_active_duration_var.set("")
        self.focus_active_profile_var.set(output_type)
        self.focus_display_progress_var.set(0)
        self.focus_percent_var.set("Failed" if failed else "Previewing…")
        self.focus_display_status_var.set(
            str(record.get("message") or "Metadata preview failed")
            if failed
            else "Loading metadata preview…"
        )
        self.focus_transfer_var.set(
            "Preview failed  /  Try again"
            if failed
            else "Metadata only  /  No media is being downloaded"
        )
        message = str(
            record.get("message")
            or ("Metadata preview failed." if failed else "Fetching metadata preview…")
        )
        self._set_text(self.focus_summary_text, message, disabled=True)
        self._render_focus_run_activity(
            str(record.get("run_id") or "metadata-preview"), message
        )
        self._reset_active_thumbnail()

    def _display_focus_job_snapshot(self, job: DownloadJob) -> None:
        self._focus_selected_run_id = job.run_id
        self._set_focus_preview_start_action(None)
        self._set_focus_progress_color()
        info = job.preview_info or {}
        if info:
            self._display_active_job_metadata(job, info)
        else:
            self.focus_active_title_var.set(download_job_display_title(job))
            self.focus_active_detail_var.set("Preparing source")
            self.focus_active_duration_var.set("")
            self.focus_active_profile_var.set(
                self._focus_profile_text(
                    job.output_type,
                    mp3_settings=job.mp3_settings,
                    quality_label=job.quality_label,
                    export_mode=job.export_mode,
                )
            )
            self._reset_active_thumbnail()
        self.focus_display_progress_var.set(float(self.progress_var.get()))
        self.focus_percent_var.set(f"{float(self.progress_var.get()):.0f}%")
        self.focus_display_status_var.set(self.status_var.get())
        self.focus_transfer_var.set(
            "Active MP3 run  /  highest-quality audio source"
            if job.output_type == OutputType.MP3
            else f"Active MP4 run  /  H.264 video and {job.manual_settings.audio_codec.value if job.export_mode == ExportMode.MANUAL_OVERRIDE else 'AAC'} audio"
        )
        self._render_focus_run_activity(
            job.run_id,
            "\n".join(job.activity_lines) or "Preparing this run…",
        )

    def _display_focus_metadata_snapshot(
        self, record: dict[str, Any], info: dict[str, Any]
    ) -> None:
        title = str(
            info.get("title") or info.get("id") or record.get("title") or "Untitled run"
        )
        creator = str(
            info.get("uploader")
            or info.get("channel")
            or record.get("detail")
            or "Unknown creator"
        )
        self.focus_active_title_var.set(title)
        self.focus_active_detail_var.set(creator)
        duration = format_duration(info.get("duration"))
        self.focus_active_duration_var.set("" if duration == "—" else duration)
        record_kind = str(record.get("kind") or "completed")
        self._set_focus_preview_start_action(info if record_kind == "preview" else None)
        self._set_focus_progress_color()
        self.focus_active_profile_var.set(
            focus_metadata_profile_text(info, record_kind)
        )
        terminal_status = str(
            info.get("vodforge_terminal_status") or record_kind.title()
        )
        if record_kind == "completed":
            self.focus_display_progress_var.set(100)
            self.focus_percent_var.set("100%")
            self.focus_display_status_var.set(f"Showing completed run: {title}")
            self.focus_transfer_var.set("Complete  /  Ready to open in Library")
        elif record_kind == "preview":
            self.focus_display_progress_var.set(100)
            self.focus_percent_var.set("Preview complete")
            self.focus_display_status_var.set(f"Showing completed preview: {title}")
            self.focus_transfer_var.set("Preview complete  /  Ready to start download")
        else:
            self.focus_display_progress_var.set(100)
            self.focus_percent_var.set(terminal_status)
            self.focus_display_status_var.set(
                f"Showing {terminal_status.lower()} run: {title}"
            )
            self.focus_transfer_var.set(f"{terminal_status}  /  Retry is available")
            terminal_job = record.get("job")
            if isinstance(terminal_job, DownloadJob):
                self._set_focus_terminal_action(terminal_job, terminal_status)
            self._set_focus_progress_color(
                THEME["danger"] if terminal_status == "Failed" else THEME["warning"]
            )
        _source_summary, output_summary = build_encoding_summary_display(info)
        if record_kind == "preview":
            output_summary = preview_output_summary_display()
        self._set_text(self.focus_summary_text, output_summary, disabled=True)
        job = record.get("job")
        activity = (
            list(job.activity_lines)
            if isinstance(job, DownloadJob)
            else sanitize_run_activity(info.get("vodforge_run_activity"))
        )
        self._render_focus_run_activity(
            str(record.get("run_id") or metadata_run_key(info)),
            "\n".join(activity)
            or "No saved activity is available for this older item.\nOpen Activity for the persistent application log.",
        )
        self._display_focus_record_thumbnail(record, info)

    def _display_focus_record_thumbnail(
        self, record: dict[str, Any], info: dict[str, Any]
    ) -> None:
        preview_thumbnail = str(info.get("preview_thumbnail_path") or "").strip()
        candidates = [Path(preview_thumbnail)] if preview_thumbnail else []
        saved = history_output_dir(info)
        if saved is not None:
            candidates.extend(
                saved / name
                for name in (
                    "thumbnail.jpg",
                    "thumbnail.jpeg",
                    "thumbnail.png",
                    "thumbnail.webp",
                )
            )
        cached = existing_cached_thumbnail_path(info)
        if cached is not None:
            candidates.append(cached)
        for candidate in candidates:
            if candidate.is_file():
                self._load_thumbnail_file(
                    candidate,
                    target="active",
                    owner_run_id=str(record.get("run_id") or ""),
                )
                return
        direct_image = record.get("preview_thumbnail_image")
        if direct_image is not None:
            self._invalidate_thumbnail_request("active")
            self._render_focus_thumbnail_surfaces(
                direct_image, placeholder=False, target="active"
            )
            return
        thumbnail = best_thumbnail(info)
        thumbnail_url = str((thumbnail or {}).get("url") or "").strip()
        if thumbnail_url:
            self._reset_active_thumbnail()
            self._load_thumbnail_preview(
                thumbnail_url,
                target="active",
                owner_run_id=str(record.get("run_id") or ""),
                cache_info=info,
            )
            return
        self._reset_active_thumbnail()

    def _show_library_actions_menu(self) -> None:
        menu = tk.Menu(
            self,
            tearoff=False,
            bg=THEME["surface"],
            fg=THEME["text"],
            activebackground=THEME["accent_dark"],
            activeforeground="#ffffff",
        )
        selection = self.video_tree.selection()
        selected_info = None
        if selection:
            try:
                selected_info = self.metadata_items[int(selection[0])]
            except (IndexError, TypeError, ValueError):
                selected_info = None
        terminal_job = (
            self._terminal_job_for_metadata(selected_info)
            if isinstance(selected_info, dict)
            else None
        )
        if is_metadata_preview(selected_info):
            menu.add_command(
                label="Start download in Forge",
                command=lambda: self._start_preview_download(selected_info),
            )
            menu.add_separator()
        elif terminal_job is not None:
            menu.add_command(
                label="↻ Retry in Forge",
                command=lambda: self._retry_terminal_job(terminal_job),
            )
            menu.add_separator()
        menu.add_command(
            label="Copy tags",
            command=lambda: self._run_library_copy_action(self._copy_tags),
        )
        menu.add_command(
            label="Copy description",
            command=lambda: self._run_library_copy_action(self._copy_description),
        )
        menu.add_command(
            label="Copy thumbnail URL",
            command=lambda: self._run_library_copy_action(self._copy_thumbnail_url),
        )
        menu.add_command(
            label="Copy YouTube URL",
            command=lambda: self._run_library_copy_action(self._copy_youtube_url),
        )
        menu.add_separator()
        menu.add_command(
            label="Open saved location", command=self._open_selected_saved_location
        )
        menu.add_command(
            label="Remove from Library…", command=self._remove_selected_library_item
        )
        try:
            menu.tk_popup(
                self.focus_library_menu_button.winfo_rootx(),
                self.focus_library_menu_button.winfo_rooty()
                + self.focus_library_menu_button.winfo_height(),
            )
        finally:
            menu.grab_release()

    def _show_selected_metadata_details(self) -> None:
        selection = self.video_tree.selection()
        if not selection:
            messagebox.showinfo(APP_NAME, "Choose an item in Library first.")
            return
        try:
            info = self.metadata_items[int(selection[0])]
        except (IndexError, TypeError, ValueError):
            return
        popup = tk.Toplevel(self)
        popup.withdraw()
        popup.title(f"{APP_NAME} Selected Item")
        popup.transient(self)
        popup.configure(bg=THEME["bg"])
        popup.resizable(True, True)
        popup.minsize(560, 520)
        root = ttk.Frame(popup, style="FocusShell.TFrame")
        root.pack(fill="both", expand=True, padx=20, pady=18)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, minsize=135)
        root.rowconfigure(4, weight=2)
        root.rowconfigure(6, weight=3)
        title = str(info.get("title") or info.get("id") or "Selected item")
        creator = str(info.get("uploader") or info.get("channel") or "Unknown creator")
        ttk.Label(
            root, text=title, style="FocusTitle.TLabel", wraplength=600, justify="left"
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(
            root,
            text=f"{creator}  /  {format_duration(info.get('duration'))}  /  {info.get('id') or 'no ID'}",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(5, 12))
        preview = tk.Label(
            root,
            bg=THEME["bg"],
            fg=THEME["muted"],
            text="No thumbnail loaded",
            height=135,
            bd=0,
        )
        preview.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        image = getattr(self, "thumbnail_image", None) or self._focus_brand_tile_image
        if image is not None:
            preview.configure(image=image, text="")
            preview.__dict__["image"] = image
        ttk.Label(root, text="TAGS", style="FocusEyebrow.TLabel").grid(
            row=3, column=0, sticky="w", pady=(0, 4)
        )
        tags = tk.Text(
            root,
            height=3,
            width=1,
            wrap="word",
            bg=THEME["surface"],
            fg=THEME["text"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=10,
            pady=8,
            font=FONT_UI,
        )
        tags.grid(row=4, column=0, sticky="nsew", pady=(0, 10))
        tags.insert(
            "1.0", build_tags_display_text(info) or "No tags found for this video."
        )
        tags.configure(state="disabled")
        bind_smooth_vertical_wheel(tags, mode="pixels")
        ttk.Label(root, text="DESCRIPTION", style="FocusEyebrow.TLabel").grid(
            row=5, column=0, sticky="w", pady=(0, 4)
        )
        description = tk.Text(
            root,
            height=5,
            width=1,
            wrap="word",
            bg=THEME["surface"],
            fg=THEME["text"],
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=10,
            pady=8,
            font=FONT_UI,
        )
        description.grid(row=6, column=0, sticky="nsew")
        description.insert(
            "1.0",
            build_description_display_text(info)
            or "No description found for this video.",
        )
        description.configure(state="disabled")
        bind_smooth_vertical_wheel(description, mode="pixels")
        popup_actions = ttk.Frame(root, style="FocusShell.TFrame")
        popup_actions.grid(row=7, column=0, sticky="e", pady=(14, 0))
        ttk.Button(
            popup_actions,
            text="Copy YouTube URL",
            command=lambda: self._copy_youtube_url(info),
            style="FocusQuiet.TButton",
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            popup_actions, text="Done", command=popup.destroy, style="Accent.TButton"
        ).pack(side="left")
        popup.update_idletasks()
        reveal_toplevel(popup, centered_toplevel_geometry(self, 680, 620))

    def _focus_run_records(self) -> list[dict[str, Any]]:
        preview = getattr(self, "_focus_preview_runs", None)
        if isinstance(preview, list):
            return [dict(record) for record in preview]

        records: list[dict[str, Any]] = []
        active = bool(
            self._focus_active_override
            or self.active_job is not None
            or (self.worker and self.worker.is_alive())
        )
        current_url = (
            self.active_job.url
            if self.active_job is not None
            else self.url_var.get().strip()
        )
        if (
            active
            and current_url
            and not self._library_run_is_suppressed(self.active_job)
        ):
            active_type = (
                self.active_job.output_type
                if self.active_job is not None
                else self._selected_output_type()
            )
            active_preview = (
                self.active_job.preview_info if self.active_job is not None else None
            )
            active_preview_path = str(
                (active_preview or {}).get("preview_thumbnail_path") or ""
            ).strip()
            records.append(
                {
                    "title": (
                        download_job_display_title(self.active_job)
                        if self.active_job is not None
                        else self.focus_active_title_var.get() or "Preparing run"
                    ),
                    "detail": self.focus_active_detail_var.get(),
                    "status": f"{self.status_var.get() or 'Active'}  •  {active_type.value}",
                    "progress": float(self.progress_var.get()),
                    "kind": "active",
                    "output_type": active_type.value,
                    "run_id": self.active_job.run_id
                    if self.active_job is not None
                    else "",
                    "job": self.active_job,
                    "preview_thumbnail_path": active_preview_path,
                    "preview_thumbnail_image": (
                        self.active_job.preview_thumbnail_image
                        if self.active_job is not None
                        else None
                    ),
                }
            )
        metadata_preview = self.__dict__.get("_metadata_preview_request")
        if isinstance(metadata_preview, dict):
            records.append(dict(metadata_preview))
        for job in self.pending_jobs:
            if self._library_run_is_suppressed(job):
                continue
            records.append(self._focus_queued_run_record(job))
        for terminal_job in self._terminal_jobs:
            if self._library_run_is_suppressed(terminal_job):
                continue
            records.append(self._focus_terminal_run_record(terminal_job))
        active_keys = (
            self.active_job.metadata_keys if self.active_job is not None else set()
        )
        active_history_identities = (
            self.active_job.history_identities if self.active_job is not None else set()
        )
        terminal_keys = {
            key
            for terminal_job in self._terminal_jobs
            for key in terminal_job.metadata_keys
        }
        records.extend(
            persisted_run_deck_records(
                self.metadata_items,
                active_metadata_keys=active_keys,
                terminal_metadata_keys=terminal_keys,
                active_history_identities=active_history_identities,
                completed_jobs=self.__dict__.get("_completed_jobs", []),
            )
        )
        return records

    def _focus_queued_run_record(self, job: DownloadJob) -> dict[str, Any]:
        preview = job.preview_info or {}
        detail = preview.get("uploader") or preview.get("channel")
        if not detail:
            detail = self._focus_profile_text(
                job.output_type,
                mp3_settings=job.mp3_settings,
                quality_label=job.quality_label,
                export_mode=job.export_mode,
            )
        return {
            "title": download_job_display_title(job, queued=True),
            "detail": str(detail),
            "status": f"Queued  •  {job.output_type.value}",
            "progress": 0,
            "kind": "queued",
            "output_type": job.output_type.value,
            "run_id": job.run_id,
            "job": job,
            "preview_thumbnail_path": str(
                preview.get("preview_thumbnail_path") or ""
            ).strip(),
            "preview_thumbnail_image": job.preview_thumbnail_image,
        }

    def _focus_terminal_run_record(self, job: DownloadJob) -> dict[str, Any]:
        preview = job.preview_info or {}
        metadata_index = next(
            (
                index
                for index, item in enumerate(self.metadata_items)
                if str(item.get("vodforge_terminal_run_id") or "") == job.run_id
            ),
            None,
        )
        status = job.terminal_status or "Stopped"
        return {
            "title": download_job_display_title(job),
            "detail": str(
                preview.get("uploader")
                or preview.get("channel")
                or job.terminal_message
                or "Run did not produce an output"
            ),
            "status": f"{status}  •  {job.output_type.value}",
            "progress": 0,
            "kind": status.lower(),
            "output_type": job.output_type.value,
            "run_id": job.run_id,
            "job": job,
            "metadata_index": metadata_index,
            "preview_thumbnail_path": str(
                preview.get("preview_thumbnail_path") or ""
            ).strip(),
            "preview_thumbnail_image": job.preview_thumbnail_image,
        }

    def _schedule_focus_run_deck_geometry_refresh(self, event: tk.Event[Any]) -> None:
        """Reconcile the deck immediately when its discrete capacity changes.

        Root Configure arrives before nested widths settle on Windows. A stale
        child width could render three cards and then cache a four-card root
        signature until the user changed tabs. The deck's own width remains the
        final authority, but an idle callback can be deferred for the whole
        native resize gesture. Rebuilding only at 220 px capacity boundaries is
        both immediate and bounded.
        """
        capacity = focus_run_deck_capacity(max(1, int(event.width)))
        if capacity == self.__dict__.get("_focus_run_deck_rendered_capacity"):
            return
        try:
            self._refresh_focus_run_deck()
        except tk.TclError:
            return

    def _render_focus_run_deck_tile(
        self,
        record: dict[str, Any],
        *,
        column: int,
        visible_count: int,
    ) -> None:
        tile_bg = THEME["bg"]
        tile = tk.Frame(
            self.focus_run_deck, bg=tile_bg, bd=0, highlightthickness=0, cursor="hand2"
        )
        left_pad = 9 if column == 0 else 5
        right_pad = 5 if column < visible_count - 1 else 9
        tile.grid(
            row=0,
            column=column,
            sticky="nsew",
            padx=(left_pad, right_pad),
            pady=6 if self._focus_layout == "compact" else 9,
        )
        tile.columnconfigure(1, weight=1)
        source = self._focus_thumbnail_source_for_record(record)
        thumbnail_size = youtube_thumbnail_size(
            64 if self._focus_layout == "compact" else 80
        )
        thumbnail = self._focus_photo_from_source(
            source, thumbnail_size, 6 if self._focus_layout == "compact" else 7
        )
        if thumbnail is not None:
            self._focus_run_thumbnail_images.append(thumbnail)
            image_label = tk.Label(
                tile, image=thumbnail, bg=tile_bg, bd=0, highlightthickness=0
            )
            image_label.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 9))
        title = str(record.get("title") or "Untitled run")
        status = str(record.get("status") or "Ready")
        title_label = tk.Label(
            tile,
            text=title[:27] + ("..." if len(title) > 27 else ""),
            bg=tile_bg,
            fg=THEME["text"],
            anchor="w",
            font=FONT_UI_SMALL_MEDIUM,
            bd=0,
        )
        title_label.grid(row=0, column=1, sticky="ew", padx=(0, 4))
        record_kind = str(record.get("kind"))
        status_color = (
            THEME["success"]
            if record_kind == "completed"
            else THEME["danger"]
            if record_kind == "failed"
            else THEME["warning"]
            if record_kind == "skipped"
            else THEME["accent"]
            if record_kind in {"active", "preview_loading"}
            else THEME["muted"]
        )
        status_label = tk.Label(
            tile,
            text=status,
            bg=tile_bg,
            fg=status_color,
            font=FONT_UI_SMALL,
            bd=0,
            anchor="w",
        )
        is_primary_active = column == 0 and str(record.get("kind")) == "active"
        if is_primary_active:
            status_label.configure(textvariable=self.focus_run_status_var)
        status_label.grid(row=1, column=1, sticky="w", pady=(3, 0))
        value = max(0.0, min(100.0, float(record.get("progress") or 0)))
        bar: SleekProgressbar | None = None
        if is_primary_active or 0 < value < 100:
            if is_primary_active:
                bar = SleekProgressbar(
                    tile,
                    maximum=100,
                    variable=self.progress_var,
                    mode="determinate",
                    height=4,
                    track_color=THEME["border"],
                )
            else:
                bar = SleekProgressbar(
                    tile,
                    maximum=100,
                    value=value,
                    mode="determinate",
                    height=4,
                    track_color=THEME["border"],
                )
            bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(7, 0))
        widgets: list[tk.Widget] = [tile, title_label, status_label]
        if thumbnail is not None:
            widgets.append(image_label)
        hover_widgets = list(widgets)
        retry_job = record.get("job")
        if record_kind in {"failed", "skipped", "stopped"} and isinstance(
            retry_job, DownloadJob
        ):
            verified_retry_job = retry_job

            def retry_from_tile(
                _event: tk.Event[Any],
                job: DownloadJob = verified_retry_job,
            ) -> None:
                self._retry_terminal_job(job)

            retry_button = tk.Canvas(
                tile,
                width=30,
                height=30,
                bg=tile_bg,
                bd=0,
                highlightthickness=0,
                cursor="hand2",
            )
            retry_button.create_oval(
                2, 2, 28, 28, fill=THEME["surface"], outline=THEME["border"], width=1
            )
            retry_button.create_text(
                15, 14, text="↻", fill=THEME["text"], font=(FONT_UI[0], 15, "bold")
            )
            retry_button.bind(
                "<Button-1>",
                retry_from_tile,
            )
            overlay_parent = image_label if thumbnail is not None else tile
            retry_button.place(in_=overlay_parent, relx=0.5, rely=0.5, anchor="center")
            hover_widgets.append(retry_button)
        elif record_kind == "preview" and record.get("metadata_index") is not None:

            def start_preview_from_tile(
                _event: tk.Event[Any],
                item: dict[str, Any] = record,
            ) -> None:
                self._start_preview_record(item)

            play_button = tk.Canvas(
                tile,
                width=30,
                height=30,
                bg=tile_bg,
                bd=0,
                highlightthickness=0,
                cursor="hand2",
            )
            play_button.create_oval(
                2, 2, 28, 28, fill=THEME["accent"], outline=THEME["border"], width=1
            )
            play_icon = self._load_focus_icon("send-filled", 20, "#ffffff")
            if play_icon is not None:
                play_button.create_image(15, 15, image=play_icon)
            play_button.bind(
                "<Button-1>",
                start_preview_from_tile,
            )
            play_button.bind(
                "<Button-2>",
                partial(self._show_focus_run_actions_menu, record),
            )
            play_button.bind(
                "<Button-3>",
                partial(self._show_focus_run_actions_menu, record),
            )
            overlay_parent = image_label if thumbnail is not None else tile
            play_button.place(in_=overlay_parent, relx=0.5, rely=0.5, anchor="center")
            hover_widgets.append(play_button)
        if bar is not None:
            widgets.append(bar)

        def sync_tile_hover(
            *,
            card: tk.Frame = tile,
            card_widgets: tuple[tk.Widget, ...] = tuple(hover_widgets),
        ) -> None:
            try:
                pointer_x = self.winfo_pointerx()
                pointer_y = self.winfo_pointery()
                inside = (
                    card.winfo_rootx()
                    <= pointer_x
                    < card.winfo_rootx() + card.winfo_width()
                    and card.winfo_rooty()
                    <= pointer_y
                    < card.winfo_rooty() + card.winfo_height()
                )
                background = THEME["surface"] if inside else THEME["bg"]
                for card_widget in card_widgets:
                    card_widget.configure({"bg": background})
            except tk.TclError:
                return

        def schedule_tile_hover(
            _event: tk.Event[Any],
            *,
            card: tk.Frame = tile,
            callback: Callable[[], None] = sync_tile_hover,
        ) -> None:
            card.after_idle(callback)

        for widget in widgets:
            widget.bind(
                "<Button-1>",
                partial(self._focus_activate_run_record, record),
            )
            widget.bind(
                "<Button-2>",
                partial(self._show_focus_run_actions_menu, record),
            )
            widget.bind(
                "<Button-3>",
                partial(self._show_focus_run_actions_menu, record),
            )
            widget.bind("<Enter>", schedule_tile_hover, add="+")
            widget.bind("<Leave>", schedule_tile_hover, add="+")

    def _refresh_focus_run_deck(self) -> None:
        if not hasattr(self, "focus_run_deck"):
            return
        for child in self.focus_run_deck.winfo_children():
            child.destroy()
        self._focus_run_thumbnail_images: list[Any] = []
        records = self._focus_run_records()
        deck_width = self.focus_run_deck.winfo_width()
        if deck_width <= 1:
            deck_width = max(1, self.winfo_width() - 52)
        limit = focus_run_deck_capacity(deck_width)
        self._focus_run_deck_rendered_capacity = limit
        visible = records[:limit]
        for column in range(4):
            self.focus_run_deck.columnconfigure(column, weight=0, uniform="")
        if not visible:
            empty = ttk.Frame(self.focus_run_deck, style="FocusShell.TFrame")
            empty.grid(row=0, column=0, sticky="ew", padx=16, pady=14)
            ttk.Label(empty, text="Your runs will collect here", style="TLabel").pack(
                anchor="w"
            )
            ttk.Label(
                empty,
                text="Start with a URL above. Completed downloads stay available in Library.",
                style="Muted.TLabel",
            ).pack(anchor="w", pady=(4, 0))
            self.focus_run_deck.columnconfigure(0, weight=1)
            self.focus_run_count_var.set("No runs yet")
            self.focus_run_overflow_button.grid_remove()
            return

        for column in range(limit):
            self.focus_run_deck.columnconfigure(column, weight=1, uniform="focus-run")
        for column, record in enumerate(visible):
            self._render_focus_run_deck_tile(
                record,
                column=column,
                visible_count=len(visible),
            )

        completed = sum(1 for record in records if record.get("kind") == "completed")
        failed = sum(1 for record in records if record.get("kind") == "failed")
        skipped = sum(1 for record in records if record.get("kind") == "skipped")
        queued = sum(1 for record in records if record.get("kind") == "queued")
        active = sum(1 for record in records if record.get("kind") == "active")
        parts = [f"{len(records)} run{'s' if len(records) != 1 else ''}"]
        if active:
            parts.append(f"{active} active")
        if queued:
            parts.append(f"{queued} queued")
        if completed:
            parts.append(f"{completed} completed")
        if failed:
            parts.append(f"{failed} failed")
        if skipped:
            parts.append(f"{skipped} skipped")
        self.focus_run_count_var.set("  •  ".join(parts))
        self.focus_run_overflow_button.grid()
        self.focus_run_overflow_button.configure(text=f"All {len(records)} runs")

    def _focus_thumbnail_source_for_record(self, record: dict[str, Any]) -> Any | None:
        if Image is None:
            return None
        direct_image = record.get("preview_thumbnail_image")
        if direct_image is not None:
            try:
                return direct_image.convert("RGBA").copy()
            except Exception as exc:  # noqa: BLE001 - untrusted image objects may raise library-specific errors
                write_diagnostic(
                    "in-memory run thumbnail conversion failed: "
                    f"{type(exc).__name__}; trying persisted artwork"
                )
        candidates: list[Path] = []
        direct = str(record.get("preview_thumbnail_path") or "").strip()
        if direct:
            candidates.append(Path(direct))
        metadata_index = record.get("metadata_index")
        if metadata_index is not None:
            try:
                item = self.metadata_items[int(metadata_index)]
            except (IndexError, TypeError, ValueError):
                item = None
            if item is not None:
                preview_path = str(item.get("preview_thumbnail_path") or "").strip()
                if preview_path:
                    candidates.append(Path(preview_path))
                saved = history_output_dir(item)
                if saved is not None:
                    candidates.extend(
                        (
                            saved / "thumbnail.jpg",
                            saved / "thumbnail.jpeg",
                            saved / "thumbnail.png",
                            saved / "thumbnail.webp",
                        )
                    )
                cached = existing_cached_thumbnail_path(item)
                if cached is not None:
                    candidates.append(cached)
        for path in candidates:
            try:
                if path.is_file():
                    with Image.open(path) as source:
                        return source.convert("RGBA").copy()
            except Exception as exc:  # noqa: BLE001 - persisted images may raise decoder-specific errors
                write_diagnostic(f"run thumbnail could not be loaded ({path}): {exc}")
        if (
            str(record.get("kind")) == "active"
            and self._focus_active_thumbnail_source_image is not None
        ):
            return self._focus_active_thumbnail_source_image
        return self._focus_brand_source_image

    def _focus_photo_from_source(
        self, source: Any | None, size: tuple[int, int], radius: int
    ) -> Any | None:
        if source is None or ImageTk is None:
            return None
        try:
            is_placeholder = (
                source is self._focus_brand_source_image
                or (
                    source is self._focus_thumbnail_source_image
                    and self._focus_thumbnail_is_placeholder
                )
                or (
                    source is self._focus_active_thumbnail_source_image
                    and self._focus_active_thumbnail_is_placeholder
                )
            )
            rendered = (
                rounded_contain_image(source, size, radius, THEME["surface"])
                if is_placeholder
                else rounded_fit_image(source, size, radius)
            )
            return ImageTk.PhotoImage(rendered)
        except Exception as exc:  # noqa: BLE001 - optional image rendering falls back cleanly
            write_diagnostic(f"thumbnail surface could not be rendered: {exc}")
            return None

    def _focus_activate_run_record(
        self, record: dict[str, Any], event: tk.Event[Any] | None = None
    ) -> None:
        self._focus_select_run_record(record)

    def _show_focus_run_actions_menu(
        self, record: dict[str, Any], event: tk.Event[Any] | None = None
    ) -> None:
        menu = tk.Menu(
            self,
            tearoff=False,
            bg=THEME["surface"],
            fg=THEME["text"],
            activebackground=THEME["accent_dark"],
            activeforeground="#ffffff",
        )
        if str(record.get("kind")) == "active":
            menu.add_command(label="Cancel run", command=self._cancel)
            menu.add_command(label="Skip current item", command=self._skip_video)
            menu.add_command(label="Skip current source URL", command=self._skip_url)
            menu.add_separator()
        terminal_job = record.get("job")
        if str(record.get("kind")) == "preview":
            menu.add_command(
                label="Start download in Forge",
                command=partial(self._start_preview_record, record),
            )
            menu.add_separator()
        elif str(record.get("kind")) in {"failed", "skipped", "stopped"} and isinstance(
            terminal_job, DownloadJob
        ):
            menu.add_command(
                label="Retry run",
                command=partial(self._retry_terminal_job, terminal_job),
            )
            menu.add_separator()
        metadata_index = record.get("metadata_index")
        if metadata_index is not None:

            def view_in_library() -> None:
                self._select_record_in_library(record)
                self._select_focus_view("library")

            menu.add_command(label="View in Library", command=view_in_library)
            try:
                saved = history_output_dir(self.metadata_items[int(metadata_index)])
            except (IndexError, TypeError, ValueError):
                saved = None
            if saved is not None:

                def open_saved_location() -> None:
                    self._select_record_in_library(record)
                    self._open_selected_saved_location()

                menu.add_command(
                    label="Open saved location",
                    command=open_saved_location,
                )
        youtube_url = self._youtube_url_for_run_record(record)
        if youtube_url:
            menu.add_command(
                label="Copy YouTube URL",
                command=partial(self._copy_youtube_url_value, youtube_url),
            )
        menu.add_command(
            label="View Activity",
            command=partial(self._select_focus_view, "activity"),
        )
        x = event.x_root if event is not None else self.winfo_pointerx()
        y = event.y_root if event is not None else self.winfo_pointery()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _show_active_focus_run_actions(self) -> None:
        records = self._focus_run_records()
        record = next(
            (item for item in records if str(item.get("kind")) == "active"),
            records[0] if records else None,
        )
        if record is not None:
            self._show_focus_run_actions_menu(record)

    def _schedule_focus_layout(self, event: tk.Event[Any] | None = None) -> None:
        """Apply breakpoint authority during, not after, a native resize drag.

        ``after`` callbacks can be held until Aqua or Windows exits its native
        live-resize loop. The expensive layout body is already guarded by a
        discrete signature, so every root Configure can cheaply offer its live
        dimensions while only real breakpoint/capacity transitions rebuild.
        """
        if event is not None and event.widget is not self:
            return
        try:
            width = (
                max(1, int(event.width))
                if event is not None
                else max(1, self.winfo_width())
            )
            height = (
                max(1, int(event.height))
                if event is not None
                else max(1, self.winfo_height())
            )
            self._apply_focus_layout(width=width, height=height)
        except tk.TclError:
            return

    def _schedule_focus_library_padding(self, padding: int) -> None:
        """Settle cosmetic ultrawide centering after native edge motion stops.

        Reconfiguring three large Library grids at every 32-pixel centering
        step can briefly stall a slow native resize.  The pointer then reaches
        the screen boundary before the held window edge catches up.  Structural
        breakpoints still apply synchronously; only this cosmetic centering is
        trailing and coalesced.
        """
        requested = max(18, int(padding))
        self._focus_library_pending_horizontal_padding = requested
        pending_after_id = self.__dict__.get("_focus_library_padding_after_id")
        applied = int(self.__dict__.get("_focus_library_horizontal_padding", 18))
        # An earlier settled ultrawide margin must not squeeze the workspace
        # while the next gesture shrinks the window. Drop to the ordinary live
        # margin once per resize burst, then keep all subsequent motion free of
        # large-grid reflows until the final centering pass.
        if pending_after_id is None and applied > 18 and requested != applied:
            self._set_focus_library_padding(18)
            applied = int(self.__dict__.get("_focus_library_horizontal_padding", 18))
        if pending_after_id is not None:
            try:
                self.after_cancel(pending_after_id)
            except tk.TclError:
                pass
            self._focus_library_padding_after_id = None
        if requested == applied:
            return
        try:
            self._focus_library_padding_after_id = self.after(
                120,
                self._apply_pending_focus_library_padding,
            )
        except tk.TclError:
            self._focus_library_padding_after_id = None

    def _apply_pending_focus_library_padding(self) -> None:
        self._focus_library_padding_after_id = None
        requested = int(
            self.__dict__.get("_focus_library_pending_horizontal_padding", 18)
        )
        applied = int(self.__dict__.get("_focus_library_horizontal_padding", 18))
        if requested == applied:
            return
        self._set_focus_library_padding(requested)

    def _set_focus_library_padding(self, padding: int) -> None:
        requested = max(18, int(padding))
        try:
            self.focus_library_actions.grid_configure(padx=requested)
            self.focus_metadata_content.grid_configure(padx=requested)
            self.focus_library_summary.grid_configure(padx=requested)
        except tk.TclError:
            return
        self._focus_library_horizontal_padding = requested

    def _apply_focus_layout(
        self,
        event: tk.Event[Any] | None = None,
        *,
        force: bool = False,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        if event is not None and event.widget is not self:
            return
        video_tree = self.video_tree
        if not isinstance(video_tree, PixelScrollTable):
            return
        width = max(1, int(width)) if width is not None else max(1, self.winfo_width())
        height = (
            max(1, int(height)) if height is not None else max(1, self.winfo_height())
        )
        mode = focus_layout_mode(width, height)
        compact = mode == "compact"
        balanced = mode == "balanced"
        library_vertical_mode = focus_library_vertical_layout_mode(height)
        library_mode = (
            "compact"
            if compact or library_vertical_mode == "compact"
            else focus_library_layout_mode(width)
        )
        library_padding = focus_library_horizontal_padding(width)
        self._schedule_focus_library_padding(library_padding)
        focus_shell_padding = 12 if compact else 20
        layout_signature = (
            mode,
            library_mode,
            library_vertical_mode,
            focus_run_deck_capacity(max(1, width - 52)),
            focus_hero_thumbnail_visible(width),
        )
        if (
            layout_signature == self.__dict__.get("_focus_layout_signature")
            and not force
        ):
            return
        self._focus_layout_signature = layout_signature
        self._focus_layout = mode
        horizontal_pad = 20 if compact else 42 if balanced else 100
        self.focus_shell.pack_configure(
            padx=focus_shell_padding,
            pady=(10 if compact else 16, 10 if compact else 14),
        )
        self.focus_command_area.grid_configure(
            padx=horizontal_pad,
            pady=(18 if compact else 26 if balanced else 42, 8 if compact else 14),
        )
        self.focus_active_frame.grid_configure(
            padx=horizontal_pad,
            pady=(6 if compact else 10 if balanced else 16, 9 if compact else 14),
        )
        self.focus_detail_wrap.grid_configure(
            padx=horizontal_pad, pady=(0, 7 if compact else 12)
        )
        self.focus_destination_button.configure(
            width=170 if compact else 210 if balanced else 240
        )
        show_hero_thumbnail = focus_hero_thumbnail_visible(width)
        active_title_width = max(
            260,
            width - (2 * horizontal_pad) - (180 if show_hero_thumbnail else 0) - 150,
        )
        self.focus_active_title_label.configure(wraplength=active_title_width)
        self.focus_summary_text.configure(
            font=(FONT_MONO_FAMILY, 8) if balanced else FONT_MONO
        )
        self.focus_log.configure(
            font=(FONT_MONO_FAMILY, 8) if compact else FONT_MONO,
            pady=0 if compact else 4,
        )

        active = bool(
            self._focus_active_override or (self.worker and self.worker.is_alive())
        )
        if compact:
            self.focus_update_dot.pack_forget()
            self.update_button.configure(text="Updates")
            if show_hero_thumbnail:
                self.focus_active_thumb_wrap.grid()
            else:
                self.focus_active_thumb_wrap.grid_remove()
            self.focus_transfer_label.grid_remove()
            if active:
                self.focus_compact_run_actions_button.grid()
            else:
                self.focus_compact_run_actions_button.grid_remove()
            self.cancel_button.grid_remove()
            self.skip_video_button.grid_remove()
            self.skip_url_button.grid_remove()
            self.focus_summary_frame.grid_remove()
            self.focus_live_frame.grid_configure(column=0, columnspan=2)
            self.focus_details_button.grid(row=0, column=1, sticky="e")
            if not self.focus_detail_header.winfo_manager():
                self.focus_detail_header.grid()
        else:
            if not self.focus_update_dot.winfo_manager():
                self.focus_update_dot.pack(
                    side="left", padx=(0, 4), before=self.update_button
                )
            self.update_button.configure(text=self._focus_update_full_text)
            self.focus_active_thumb_wrap.grid()
            self.focus_transfer_label.grid()
            self.focus_compact_run_actions_button.grid_remove()
            self._set_focus_run_controls_visible(active)
            self.focus_live_frame.grid_configure(column=0, columnspan=1)
            self.focus_summary_frame.grid(row=0, column=1, sticky="nsew")
            self.focus_details_button.grid_remove()
            self.focus_detail_header.grid_remove()

        if self._focus_run_records():
            if not self.focus_deck_header.winfo_manager():
                self.focus_deck_header.grid()
        else:
            self.focus_deck_header.grid_remove()

        self._apply_focus_library_layout(
            video_tree,
            library_mode=library_mode,
            vertical_mode=library_vertical_mode,
        )
        self._sync_focus_destination()
        self._refresh_focus_run_deck()

    def _apply_focus_library_layout(
        self,
        video_tree: PixelScrollTable,
        *,
        library_mode: str,
        vertical_mode: str,
    ) -> None:
        """Apply the Library-only mutations for the selected responsive modes."""

        # Library actions intentionally stay behind one stable menu at every
        # size. Only the Selected details launcher follows rail visibility.
        if not self.focus_library_menu_button.winfo_manager():
            self.focus_library_menu_button.pack(side="left")
        if library_mode == "compact":
            if not self.focus_library_details_button.winfo_manager():
                self.focus_library_details_button.pack(
                    side="left", padx=(6, 0), before=self.focus_library_menu_button
                )
        else:
            self.focus_library_details_button.pack_forget()

        if library_mode == "compact":
            self.focus_library_view.rowconfigure(1, weight=2, minsize=125)
            self.focus_library_view.rowconfigure(2, weight=3, minsize=180)
            self.focus_library_details.grid_remove()
            self.focus_queue_panel.grid_configure(column=0, columnspan=2, padx=0)
            self.focus_metadata_content.columnconfigure(0, weight=1)
            self.focus_metadata_content.columnconfigure(1, weight=0, minsize=0)
            # Keep the canonical table intact at small widths. The sleek
            # horizontal scrollbar makes every field reachable without
            # squeezing columns to zero or changing what the table means.
            video_tree.layout_column("index", width=44, minwidth=38, stretch=True)
            video_tree.layout_column(
                "title", width=360, minwidth=220, stretch=True, stretchmax=None
            )
            video_tree.layout_column("duration", width=72, minwidth=62, stretch=True)
            video_tree.layout_column("creator", width=120, minwidth=90, stretch=True)
            video_tree.layout_column("id", width=90, minwidth=72, stretch=True)
            video_tree.layout_column("location", width=140, minwidth=100, stretch=True)
        else:
            if vertical_mode == "balanced":
                # Reduced-height windows give the independently scrollable
                # source/output panes less room before sacrificing metadata.
                self.focus_library_view.rowconfigure(1, weight=4, minsize=360)
                self.focus_library_view.rowconfigure(2, weight=1, minsize=120)
            else:
                self.focus_library_view.rowconfigure(1, weight=2, minsize=360)
                self.focus_library_view.rowconfigure(2, weight=3, minsize=230)
            self.focus_queue_panel.grid_configure(column=0, columnspan=1, padx=(0, 18))
            self.focus_library_details.grid(row=0, column=1, sticky="nsew")
            if library_mode == "balanced":
                self.focus_metadata_content.columnconfigure(0, weight=1)
                self.focus_metadata_content.columnconfigure(1, weight=0, minsize=330)
                self.focus_library_details.configure(width=330)
                video_tree.layout_column("index", width=44, minwidth=38, stretch=False)
                video_tree.layout_column(
                    "duration", width=72, minwidth=62, stretch=False
                )
                video_tree.layout_column(
                    "creator", width=110, minwidth=90, stretch=False
                )
                video_tree.layout_column("id", width=90, minwidth=72, stretch=False)
                video_tree.layout_column(
                    "location", width=120, minwidth=90, stretch=False
                )
                video_tree.layout_column(
                    "title", width=320, minwidth=200, stretch=False
                )
            else:
                self.focus_metadata_content.columnconfigure(0, weight=1)
                self.focus_metadata_content.columnconfigure(1, weight=0, minsize=410)
                self.focus_library_details.configure(width=410)
                video_tree.layout_column("index", width=44, minwidth=38, stretch=False)
                video_tree.layout_column(
                    "duration", width=72, minwidth=62, stretch=False
                )
                video_tree.layout_column(
                    "creator", width=120, minwidth=90, stretch=False
                )
                video_tree.layout_column("id", width=90, minwidth=72, stretch=False)
                video_tree.layout_column(
                    "location", width=120, minwidth=90, stretch=False
                )
                video_tree.layout_column(
                    "title", width=360, minwidth=220, stretch=True, stretchmax=560
                )
        self._queue_focus_description_layout()

    def _check_runtime(self) -> None:
        if _YTDLP_IMPORT_ATTEMPTED and YTDLP_IMPORT_ERROR is not None:
            self._append_log(f"yt-dlp import failed: {YTDLP_IMPORT_ERROR}")
            self.download_button.config(state="disabled")
        ffmpeg = self._find_ffmpeg()
        deno = self._find_deno()
        write_diagnostic(f"runtime path: ffmpeg={ffmpeg}")
        write_diagnostic(f"runtime path: deno={deno}")
        if not ffmpeg:
            self._append_log(
                "FFmpeg not found. Install FFmpeg or place its executable beside the packaged app."
            )
        else:
            self._append_log(f"FFmpeg found: {ffmpeg}")
        self._append_log(f"Diagnostics log: {DIAGNOSTICS_LOG_PATH}")

    def _start_ytdlp_preload(self) -> None:
        threading.Thread(target=self._preload_ytdlp_worker, daemon=True).start()

    def _preload_ytdlp_worker(self) -> None:
        module = load_yt_dlp()
        if module is None:
            self.events.put(
                ("runtime_error", f"yt-dlp import failed: {YTDLP_IMPORT_ERROR}")
            )
            return
        version = getattr(getattr(module, "version", None), "__version__", "unknown")
        write_diagnostic(f"yt-dlp version: {version}")

    def _schedule_auto_update_check(
        self, delay_ms: int = AUTO_UPDATE_INTERVAL_MS
    ) -> None:
        if not bool(getattr(sys, "frozen", False)):
            return
        if self.update_check_after_id is not None:
            try:
                self.after_cancel(self.update_check_after_id)
            except tk.TclError:
                pass
        self.update_check_after_id = self.after(delay_ms, self._run_auto_update_check)

    def _set_focus_update_state(self, text: str, color: str) -> None:
        self._focus_update_full_text = text
        state = self.__dict__
        button = state.get("update_button")
        if button is not None:
            display = "Updates" if state.get("_focus_layout") == "compact" else text
            button.config(text=display)
        dot = state.get("focus_update_dot")
        if dot is not None:
            try:
                dot.itemconfigure("dot", fill=color)
            except tk.TclError:
                pass

    def _run_auto_update_check(self) -> None:
        self.update_check_after_id = None
        if (self.worker and self.worker.is_alive()) or (
            self.update_worker and self.update_worker.is_alive()
        ):
            self._schedule_auto_update_check(AUTO_UPDATE_BUSY_RETRY_MS)
            return
        self._check_for_updates(silent=True)

    def _check_for_updates(self, *, silent: bool = False) -> None:
        if self.update_worker and self.update_worker.is_alive():
            return
        self.update_check_silent = silent
        self.update_button.config(state="disabled")
        self._set_focus_update_state("Checking…", THEME["accent"])
        if not silent:
            self.status_var.set("Checking GitHub Releases for a VODForge update…")
        self.update_worker = threading.Thread(
            target=self._update_check_worker, daemon=True
        )
        self.update_worker.start()

    def _update_check_worker(self) -> None:
        try:
            self.events.put(("update_check_result", fetch_latest_release()))
        except Exception as exc:  # noqa: BLE001 - worker reports any update-provider failure
            self.events.put(("update_check_error", str(exc)))

    def _show_update_result(self, release: ReleaseInfo) -> None:
        silent = self.update_check_silent
        self.update_check_silent = False
        self._schedule_auto_update_check()
        self.update_button.config(state="normal")
        if not is_newer_release(__version__, release.version):
            self._set_focus_update_state("Up to date", THEME["success"])
            if not silent:
                self.status_var.set(f"VODForge v{__version__} is up to date.")
                messagebox.showinfo(
                    APP_NAME,
                    f"You are using the latest VODForge release (v{__version__}).",
                )
            return
        self.status_var.set(f"VODForge {release.tag_name} is available.")
        self._set_focus_update_state(f"Update {release.tag_name}", THEME["accent"])
        asset = release_asset_for_platform(release)
        if asset is None:
            if messagebox.askyesno(
                APP_NAME,
                f"VODForge {release.tag_name} is available, but there is no automatic update for this computer.\n\nOpen the verified GitHub Release page?",
            ):
                webbrowser.open(release.html_url)
            return
        if messagebox.askyesno(
            APP_NAME,
            f"VODForge {release.tag_name} is available.\n\nDownload the signed update, verify it, and restart VODForge?",
        ):
            self._start_update_download(release)

    def _start_update_download(self, release: ReleaseInfo) -> None:
        self.update_button.config(state="disabled")
        self._set_focus_update_state("Downloading update…", THEME["accent"])
        self.status_var.set(f"Downloading and verifying VODForge {release.tag_name}…")
        self.update_worker = threading.Thread(
            target=self._update_download_worker, args=(release,), daemon=True
        )
        self.update_worker.start()

    def _update_download_worker(self, release: ReleaseInfo) -> None:
        try:
            destination = application_data_dir() / "updates" / release.tag_name
            path = download_verified_update(release, destination)
            payload: Path | MacUpdatePlan = path
            if is_macos():
                target_app = running_macos_app()
                if target_app is None:
                    raise RuntimeError(
                        "VODForge must be running from the packaged app to update itself."
                    )
                cleanup_stale_macos_updates(destination)
                payload = prepare_macos_update(path, target_app)
            elif is_windows():
                verify_windows_authenticode(path)
            self.events.put(("update_ready", payload))
        except Exception as exc:  # noqa: BLE001 - worker reports any verified-update failure
            self.events.put(("update_check_error", str(exc)))

    def _install_downloaded_update(self, update: Path | MacUpdatePlan) -> None:
        self.update_button.config(state="normal")
        if isinstance(update, MacUpdatePlan):
            try:
                launch_macos_update(update)
            except Exception as exc:  # noqa: BLE001 - platform launcher failures stay user-visible
                messagebox.showerror(
                    APP_NAME,
                    f"The verified macOS update could not be started:\n\n{exc}",
                )
                self.status_var.set("The macOS update could not be started.")
                return
            self.update_button.config(state="disabled", text="Installing update…")
            self._focus_update_full_text = "Installing update…"
            self.status_var.set(
                "Verified update ready. VODForge is restarting to install it…"
            )
            self.after(250, self.destroy)
            return
        path = update
        if not is_windows() or path.suffix.lower() != ".exe":
            self.status_var.set(f"Verified update downloaded: {path.name}")
            self._open_path(path.parent)
            return
        try:
            # This path was checksum/Authenticode verified before the update_ready event.
            subprocess.Popen(  # nosec B603
                [
                    str(path),
                    "/SP-",
                    "/SILENT",
                    "/CLOSEAPPLICATIONS",
                    "/RESTARTAPPLICATIONS",
                ],
                close_fds=True,
            )
        except OSError as exc:
            messagebox.showerror(
                APP_NAME, f"The verified updater could not be started:\n\n{exc}"
            )
            return
        self.status_var.set(
            "Verified updater started. VODForge will close and reopen when installation completes."
        )

    def _load_download_history(self) -> None:
        try:
            self.download_history = load_history(self.history_path)
        except HistoryError as exc:
            self.download_history = []
            self._append_log(f"WARNING: {exc}")
            self.status_var.set(
                "Download history could not be loaded; the existing history file was left untouched."
            )
            return
        self.metadata_items = [dict(item) for item in self.download_history]
        self._rebuild_output_dir_index()
        if self.metadata_items and not metadata_indices_for_output_type(
            self.metadata_items,
            self.library_output_type_var.get(),
        ):
            self.library_output_type_var.set(
                metadata_output_type(self.metadata_items[0]).value
            )
        self._render_metadata_tree()
        if self.download_history:
            self.status_var.set(
                f"Loaded {len(self.download_history)} downloaded media item(s) from history."
            )
            self._append_log(f"Loaded download history: {self.history_path}")

    def _record_download_history(
        self,
        info: dict[str, Any],
        output_dir: Path,
        *,
        owning_job: DownloadJob | None = None,
    ) -> None:
        history_info = dict(info)
        history_info.pop("vodforge_preview_complete", None)
        history_info.pop("vodforge_preview_run_id", None)
        if owning_job is not None:
            history_info["vodforge_run_id"] = owning_job.run_id
            history_info["vodforge_run_activity"] = sanitize_run_activity(
                owning_job.activity_lines
            )
        try:
            self.download_history = upsert_history(
                self.download_history,
                history_info,
                output_dir,
                replace_missing_media=True,
            )
            save_history(self.history_path, self.download_history)
        except HistoryError as exc:
            if owning_job is not None:
                self._append_job_log(owning_job, f"WARNING: {exc}")
            else:
                self._append_log(f"WARNING: {exc}")
            self.status_var.set(
                "The video finished, but VODForge could not save it to local history."
            )
            return

        saved_record = self.download_history[0]
        if owning_job is not None:
            owning_job.history_identities.add(history_identity(saved_record))
        saved_id = str(saved_record.get("id") or "")
        saved_type = metadata_output_type(saved_record)
        merged = dict(saved_record)
        retained: list[dict[str, Any]] = []
        persisted_identities = {
            history_identity(item) for item in self.download_history
        }
        metadata_items = self.__dict__.get("metadata_items", [])
        for item in metadata_items:
            if (
                history_output_dir(item) is not None
                and history_identity(item) not in persisted_identities
            ):
                continue
            if history_identity(item) == history_identity(saved_record):
                merged = {**item, **saved_record}
                continue
            if (
                saved_id
                and str(item.get("id") or "") == saved_id
                and metadata_output_type(item) == saved_type
                and history_output_dir(item) is None
            ):
                merged = {**item, **saved_record}
                continue
            retained.append(item)
        merged.pop("vodforge_preview_complete", None)
        merged.pop("vodforge_preview_run_id", None)
        merged.pop(ACTIVE_METADATA_RUN_ID_KEY, None)
        self.metadata_items = [merged, *retained]
        self._rebuild_output_dir_index()
        if self.library_output_type_var.get() != saved_type.value:
            self.library_output_type_var.set(saved_type.value)
        self._render_metadata_tree(selected_index=0)
        if owning_job is not None:
            self._append_job_log(
                owning_job, f"Saved download history entry: {output_dir}"
            )
        else:
            self._append_log(f"Saved download history entry: {output_dir}")

    def _persist_job_activity_to_history(self, job: DownloadJob) -> None:
        identities = set(job.history_identities)
        if not identities:
            return
        activity = sanitize_run_activity(job.activity_lines)
        updated_history: list[dict[str, Any]] = []
        changed = False
        for record in self.download_history:
            if history_identity(record) not in identities:
                updated_history.append(record)
                continue
            updated = dict(record)
            updated["vodforge_run_id"] = job.run_id
            updated["vodforge_run_activity"] = activity
            updated_history.append(updated)
            changed = True
        if not changed:
            return
        try:
            save_history(self.history_path, updated_history)
        except HistoryError as exc:
            self._append_job_log(job, f"WARNING: {exc}")
            return
        self.download_history = updated_history
        for index, item in enumerate(self.metadata_items):
            if (
                history_output_dir(item) is None
                or history_identity(item) not in identities
            ):
                continue
            updated = dict(item)
            updated["vodforge_run_id"] = job.run_id
            updated["vodforge_run_activity"] = activity
            self.metadata_items[index] = updated

    def _manual_help_icon(self, frame: ttk.LabelFrame, row: int, text: str) -> None:
        icon = ttk.Label(
            frame, text="?", style="Accent.TLabel", cursor="question_arrow"
        )
        icon.grid(row=row, column=2, sticky="w", padx=(2, 8), pady=6)
        ToolTip(icon, text)

    def _refresh_manual_settings_visibility(self) -> None:
        manual_override = (
            self._selected_output_type() == OutputType.MP4
            and self.export_mode_var.get() == ExportMode.MANUAL_OVERRIDE.value
        )
        dialog = self.__dict__.get("_focus_settings_dialog")
        if dialog is not None:
            dialog.refresh_manual_settings(manual_override)

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
        audio_codec = ManualAudioCodec(self.manual_audio_codec_var.get())
        audio_bitrate_kbps = positive_int(
            self.manual_audio_bitrate_var.get(),
            "Manual audio bitrate",
            32,
            1024,
        )
        if (
            audio_codec is ManualAudioCodec.MP3
            and audio_bitrate_kbps not in MP3_IN_MP4_BITRATES_KBPS
        ):
            choices = ", ".join(str(value) for value in MP3_IN_MP4_BITRATES_KBPS)
            raise ValueError(
                "MP3 audio bitrate must be one of the encoder-supported values: "
                f"{choices} kbps."
            )
        return ManualExportSettings(
            video_bitrate_kbps=positive_int(
                self.manual_video_bitrate_var.get(), "Manual video bitrate", 100, 100000
            ),
            audio_bitrate_kbps=audio_bitrate_kbps,
            audio_sample_rate=self.manual_sample_rate_var.get() or AUDIO_SAMPLE_RATE,
            audio_channels=channels,
            audio_codec=audio_codec,
            x264_preset=self.manual_preset_var.get() or "medium",
        )

    def _browse_output(self) -> None:
        initial_dir = self.output_var.get() or str(Path.home())
        try:
            folder = choose_output_directory(
                initial_dir,
                standard_picker=lambda directory: filedialog.askdirectory(
                    initialdir=directory,
                    mustexist=True,
                ),
            )
        except (OSError, RuntimeError, tk.TclError) as exc:
            self._append_log(f"Output folder browser failed: {exc}")
            messagebox.showerror(
                APP_NAME,
                f"{output_directory_failure_guidance()}\n\nDetails: {exc}",
            )
            return
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
            messagebox.showinfo(
                APP_NAME, "This preview does not have a saved download location yet."
            )
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
        open_system_path(path)

    def _folder_to_open(self) -> Path:
        saved = self._selected_saved_folder()
        if saved is not None:
            return saved
        if self.last_output_dirs:
            return self.last_output_dirs[-1]
        return Path(self.output_var.get()).expanduser()

    def _selected_saved_folder(self) -> Path | None:
        video_tree = getattr(self, "video_tree", None)
        if video_tree is None:
            return None
        selection = video_tree.selection()
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
        except (OSError, UnicodeError) as exc:
            messagebox.showerror(APP_NAME, f"Could not read URL list file:\n{exc}")
            return
        if not urls:
            messagebox.showerror(
                APP_NAME, "That text file did not contain any http:// or https:// URLs."
            )
            return
        self.batch_urls = urls
        self.url_list_file_var.set(f"{Path(path).name} — {len(urls)} URL(s) loaded")
        self.status_var.set(
            f"Loaded {len(urls)} URL(s). Download will process them one at a time."
        )
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
        self.cookie_source_var.set(CookieSource.FILE.value)
        self.status_var.set(
            "Loaded YouTube cookies.txt; VODForge will use it for this session."
        )
        self._append_log(f"Loaded YouTube cookies file: {cookie_path}")

    def _fetch_metadata(self) -> bool:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror(APP_NAME, "Paste a YouTube URL first.")
            return False
        ignore_playlists = self.single_video_only_var.get()
        if ignore_playlists:
            single_item_error = single_video_url_requires_video_id_error(url)
            if single_item_error:
                messagebox.showerror(APP_NAME, single_item_error)
                return False
        if load_yt_dlp() is None:
            messagebox.showerror(
                APP_NAME, f"yt-dlp import failed: {YTDLP_IMPORT_ERROR}"
            )
            return False
        if hasattr(self, "preview_metadata_button"):
            self.preview_metadata_button.config(state="disabled")
        self.status_var.set("Fetching tags and thumbnail…")
        output_type = self._selected_output_type()
        preview_run_id = f"preview:{uuid.uuid4().hex}"
        preview_record = {
            "run_id": preview_run_id,
            "title": "Loading preview…",
            "detail": "Fetching title, creator, and thumbnail",
            "status": f"Loading preview…  •  {output_type.value}",
            "progress": 0,
            "kind": "preview_loading",
            "output_type": output_type.value,
            "message": "Fetching metadata preview…",
        }
        self._metadata_preview_request = preview_record
        self._focus_selected_run_id = preview_run_id
        self._select_focus_view("forge")
        self._display_metadata_preview_request(preview_record)
        self._refresh_focus_run_deck()
        threading.Thread(
            target=self._metadata_worker,
            args=(url, output_type, ignore_playlists),
            daemon=True,
        ).start()
        return True

    def _provider_network_coordinator(self) -> ProviderNetworkCoordinator:
        coordinator = self.__dict__.get("_provider_network")
        if coordinator is None:
            coordinator = ProviderNetworkCoordinator()
            self._provider_network = coordinator
        return coordinator

    def _metadata_worker(
        self, url: str, output_type: OutputType, ignore_playlists: bool = False
    ) -> None:
        ytdlp_module = load_yt_dlp()
        if ytdlp_module is None:
            self.events.put(
                (
                    "metadata_error",
                    f"Metadata fetch failed: yt-dlp import failed: {YTDLP_IMPORT_ERROR}",
                )
            )
            self.events.put(("metadata_fetch_done", None))
            return
        try:
            opts = {
                "quiet": True,
                "skip_download": True,
                "noplaylist": ignore_playlists,
                "extract_flat": False,
                "logger": QueueLogger(self.events),
                "socket_timeout": 15,
            }
            apply_ytdlp_network_retry_policy(opts, source_analysis=True)
            use_cookies, cookie_file, cookie_browser = self._cookie_inputs()
            apply_ytdlp_cookie_options(
                opts,
                use_cookies=use_cookies,
                cookie_file=cookie_file,
                cookie_browser=cookie_browser,
            )
            ffmpeg = self._find_ffmpeg()
            if ffmpeg:
                opts["ffmpeg_location"] = ytdlp_ffmpeg_location(ffmpeg)
            deno = self._find_deno()
            apply_youtube_runtime_options(opts, deno_path=deno)

            def extract_metadata() -> Any:
                def extract() -> Any:
                    with ytdlp_module.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(url, download=False)

                def control_check() -> None:
                    if self.__dict__.get("_closing", False):
                        raise RuntimeError(
                            "Metadata preview cancelled during application close"
                        )

                return run_with_bounded_transient_retries(
                    lambda: run_tracked_ytdlp_operation(
                        extract,
                        control_check=control_check,
                    ),
                    control_check=control_check,
                    on_retry=lambda attempt, maximum, delay, exc: write_diagnostic(
                        source_analysis_retry_message(
                            "metadata preview",
                            attempt,
                            maximum,
                            delay,
                            exc,
                        )
                    ),
                )

            ran, info = self._provider_network_coordinator().run_preview(
                extract_metadata,
                should_abort=lambda: bool(self.__dict__.get("_closing", False)),
            )
            if not ran:
                return
            if isinstance(info, dict):
                info = mark_metadata_output_type(info, output_type)
                self.events.put(("metadata", info))
            else:
                self.events.put(
                    ("metadata_error", "Metadata preview returned no usable item.")
                )
        except Exception as exc:  # noqa: BLE001 - worker converts provider failures into UI events
            self.events.put(
                (
                    "metadata_error",
                    f"Metadata fetch failed: {format_ytdlp_user_error(exc)}",
                )
            )
        finally:
            self.events.put(("metadata_fetch_done", None))

    def _enqueue_queue_preview(self, job: DownloadJob) -> None:
        request_queue = getattr(self, "_queued_preview_requests", None)
        worker = getattr(self, "_queued_preview_thread", None)
        if request_queue is None:
            request_queue = queue.Queue(maxsize=MAX_QUEUED_PREVIEW_REQUESTS)
            self._queued_preview_requests = request_queue
        try:
            request_queue.put_nowait(job)
        except queue.Full:
            write_diagnostic(
                f"queued preview skipped: request cap {MAX_QUEUED_PREVIEW_REQUESTS} reached; media run remains queued"
            )
            return
        if worker is None or not worker.is_alive():
            worker = threading.Thread(target=self._queued_preview_loop, daemon=True)
            self._queued_preview_thread = worker
            worker.start()

    def _queued_preview_loop(self) -> None:
        request_queue: queue.Queue[DownloadJob] = self._queued_preview_requests
        while True:
            job = request_queue.get()
            try:
                if any(item is job for item in self.pending_jobs):
                    self._queue_preview_worker(job)
            finally:
                request_queue.task_done()

    def _queue_preview_worker(self, job: DownloadJob) -> None:
        """Fetch one queued run's display metadata without downloading its media."""
        ytdlp_module = load_yt_dlp()
        if ytdlp_module is None:
            return
        try:
            opts: dict[str, Any] = {
                "quiet": True,
                "skip_download": True,
                "noplaylist": job.single_video_only,
                "playlistend": 1,
                "extract_flat": False,
                "ignore_no_formats_error": True,
                "logger": QueueLogger(None, diagnostic_prefix="queue preview yt-dlp"),
                "socket_timeout": 15,
            }
            apply_ytdlp_network_retry_policy(opts, source_analysis=True)
            apply_ytdlp_cookie_options(
                opts,
                use_cookies=job.use_cookies,
                cookie_file=job.cookie_file,
                cookie_browser=job.cookie_browser,
            )
            ffmpeg = self._find_ffmpeg()
            if ffmpeg:
                opts["ffmpeg_location"] = ytdlp_ffmpeg_location(ffmpeg)
            apply_youtube_runtime_options(opts, deno_path=self._find_deno())

            def fetch_preview() -> dict[str, Any] | None:
                def extract() -> Any:
                    with ytdlp_module.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(job.url, download=False)

                def control_check() -> None:
                    if self.__dict__.get("_closing", False) or not any(
                        item is job for item in self.pending_jobs
                    ):
                        raise RuntimeError("Queued preview is no longer needed")

                extracted = run_with_bounded_transient_retries(
                    lambda: run_tracked_ytdlp_operation(
                        extract,
                        control_check=control_check,
                    ),
                    control_check=control_check,
                    on_retry=lambda attempt, maximum, delay, exc: write_diagnostic(
                        source_analysis_retry_message(
                            "queued metadata preview",
                            attempt,
                            maximum,
                            delay,
                            exc,
                        )
                    ),
                )
                if not isinstance(extracted, dict):
                    return None
                items = iter_video_infos(
                    mark_metadata_output_type(extracted, job.output_type)
                )
                preview = dict(items[0] if items else extracted)
                cached = (
                    save_custom_cached_thumbnail_image(
                        preview, job.mp3_settings.custom_cover_art_path
                    )
                    if job.output_type == OutputType.MP3
                    and job.mp3_settings.custom_cover_art_path is not None
                    else save_cached_thumbnail_image(preview, source_url=job.url)
                )
                if cached is not None:
                    preview["preview_thumbnail_path"] = str(cached)
                return preview

            def pending() -> bool:
                return any(item is job for item in self.pending_jobs)

            ran, preview = self._provider_network_coordinator().run_preview(
                fetch_preview,
                should_abort=lambda: (
                    bool(self.__dict__.get("_closing", False)) or not pending()
                ),
            )
            if not ran or not isinstance(preview, dict) or not pending():
                return
            self.events.put(job_info_event("queued_preview", job, preview))
        except Exception as exc:  # noqa: BLE001 - queued preview failure is intentionally nonfatal
            write_diagnostic(
                f"queued run preview unavailable for {job.url}: {type(exc).__name__}: {exc}"
            )

    def _copy_tags(self) -> bool:
        text = self.pulled_tags_text.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.status_var.set("Copied tags to clipboard.")
            return True
        return False

    def _copy_thumbnail_url(self) -> bool:
        if self.last_thumbnail_url:
            self.clipboard_clear()
            self.clipboard_append(self.last_thumbnail_url)
            self.status_var.set("Copied thumbnail URL to clipboard.")
            return True
        return False

    def _copy_youtube_url_value(self, url: str) -> bool:
        self.clipboard_clear()
        self.clipboard_append(url)
        self.status_var.set("Copied YouTube URL to clipboard.")
        return True

    def _copy_youtube_url(self, info: dict[str, Any] | None = None) -> bool:
        selected = info
        if selected is None:
            selection = self.video_tree.selection()
            if selection:
                try:
                    selected = self.metadata_items[int(selection[0])]
                except (IndexError, TypeError, ValueError):
                    selected = None
        url = canonical_youtube_url(selected or {})
        if not url:
            messagebox.showinfo(
                APP_NAME, "This item does not include a YouTube URL to copy."
            )
            return False
        return self._copy_youtube_url_value(url)

    def _youtube_url_for_run_record(self, record: dict[str, Any]) -> str | None:
        metadata_index = record.get("metadata_index")
        if metadata_index is not None:
            try:
                info = self.metadata_items[int(metadata_index)]
            except (IndexError, TypeError, ValueError):
                info = None
            if isinstance(info, dict):
                url = canonical_youtube_url(info)
                if url:
                    return url
        job = record.get("job")
        if isinstance(job, DownloadJob):
            return canonical_youtube_url(job.preview_info or {}, job.url)
        return canonical_youtube_url(record)

    def _copy_description(self) -> bool:
        text = self.description_text.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.status_var.set("Copied description to clipboard.")
            return True
        return False

    def _run_library_copy_action(self, action: Callable[[], bool]) -> None:
        if not action():
            return
        button = self.focus_library_menu_button
        pending = self._focus_library_action_feedback_after_id
        if pending is not None:
            try:
                self.after_cancel(pending)
            except tk.TclError:
                pass
        button.configure(text="Copied", width=7)

        def restore() -> None:
            self._focus_library_action_feedback_after_id = None
            try:
                button.configure(text="Actions", width=7)
            except tk.TclError:
                pass

        self._focus_library_action_feedback_after_id = self.after(900, restore)

    def _display_metadata(
        self,
        info: dict[str, Any],
        *,
        active_job: DownloadJob | None = None,
        preview_complete: bool = False,
    ) -> None:
        active_status = (
            self.status_var.get()
            if active_job is not None and active_job is self.active_job
            else None
        )
        preview_request = (
            self.__dict__.get("_metadata_preview_request") if preview_complete else None
        )
        preview_run_id = (
            str(preview_request.get("run_id") or "")
            if isinstance(preview_request, dict)
            else ""
        )
        merged = merge_library_metadata_items(
            self.metadata_items,
            iter_video_infos(info),
            active_run_id=active_job.run_id if active_job is not None else None,
            preview_complete=preview_complete,
            preview_run_id=preview_run_id,
        )
        self.metadata_items = merged.items
        incoming_items = merged.incoming_items
        if preview_complete:
            self._metadata_preview_request = None
        self._rebuild_output_dir_index()
        if incoming_items:
            incoming_type = metadata_output_type(incoming_items[0])
            if self.library_output_type_var.get() != incoming_type.value:
                self.library_output_type_var.set(incoming_type.value)
        self._render_metadata_tree()
        if (
            preview_run_id
            and self.__dict__.get("_focus_selected_run_id") == preview_run_id
        ):
            selected_preview = next(
                (
                    record
                    for record in self._focus_run_records()
                    if str(record.get("run_id") or "") == preview_run_id
                    and str(record.get("kind") or "") == "preview"
                ),
                None,
            )
            if (
                selected_preview is not None
                and selected_preview.get("metadata_index") is not None
            ):
                selected_index = int(selected_preview["metadata_index"])
                self._display_focus_metadata_snapshot(
                    selected_preview, self.metadata_items[selected_index]
                )
        if active_job is not None and active_job is self.active_job and incoming_items:
            for incoming in incoming_items:
                key = metadata_run_key(incoming)
                if key is not None:
                    active_job.metadata_keys.add(key)
            self._display_active_job_metadata(active_job, incoming_items[0])
            if active_status is not None:
                self.status_var.set(active_status)
        else:
            self.status_var.set(
                f"Showing metadata for {len(incoming_items)} fetched item(s); saved history remains available."
            )

    def _display_active_job_metadata(
        self, job: DownloadJob, info: dict[str, Any]
    ) -> None:
        """Apply provider metadata only to the run that currently owns the Forge surface."""
        if job is not self.active_job:
            return
        job.preview_info = {**(job.preview_info or {}), **info}
        selected_run_id = getattr(self, "_focus_selected_run_id", None)
        selected_for_details = selected_run_id is None or selected_run_id == job.run_id
        preview_thumbnail = str(info.get("preview_thumbnail_path") or "").strip()
        preview_thumbnail_path = Path(preview_thumbnail) if preview_thumbnail else None
        cached_thumbnail = existing_cached_thumbnail_path(info)
        thumbnail = best_thumbnail(info)
        thumbnail_url = str((thumbnail or {}).get("url") or "").strip()
        local_thumbnail_path = (
            preview_thumbnail_path
            if preview_thumbnail_path is not None and preview_thumbnail_path.is_file()
            else cached_thumbnail
            if cached_thumbnail is not None and cached_thumbnail.is_file()
            else None
        )
        if not selected_for_details:
            if local_thumbnail_path is not None and Image is not None:
                try:
                    with Image.open(local_thumbnail_path) as source:
                        job.preview_thumbnail_image = source.convert("RGBA").copy()
                except Exception as exc:  # noqa: BLE001 - optional deck artwork may fail by decoder
                    write_diagnostic(
                        f"active run thumbnail could not be cached for its deck card: {exc}"
                    )
            elif thumbnail_url:
                self._load_thumbnail_preview(
                    thumbnail_url,
                    target=f"run:{job.run_id}",
                    owner_run_id=job.run_id,
                    cache_info=info,
                    source_url=job.url,
                )
            self._refresh_focus_run_deck()
            return

        self._set_focus_preview_start_action(None)
        self._set_focus_progress_color()
        title = download_job_display_title(job)
        creator = str(info.get("uploader") or info.get("channel") or "YouTube").strip()
        self.focus_active_title_var.set(title)
        self.focus_active_detail_var.set(creator)
        duration = format_duration(info.get("duration"))
        self.focus_active_duration_var.set("" if duration == "—" else duration)
        _source, output, _warnings = _encoding_summary_sections(info)
        if job.output_type == OutputType.MP3:
            bitrate = _display_value(
                output.get("Target audio bitrate"),
                f"{job.mp3_settings.bitrate_kbps} kbps",
            )
            sample_rate = _display_value(output.get("Audio sample rate"), "Source rate")
            self.focus_active_profile_var.set(f"MP3  •  {bitrate}  •  {sample_rate}")
        else:
            mode = _display_value(
                output.get("Output rate-control mode"), job.export_mode.value
            )
            self.focus_active_profile_var.set(f"MP4  •  {job.quality_label}  •  {mode}")
        _source_summary, output_summary = build_encoding_summary_display(info)
        self._set_text(self.focus_summary_text, output_summary, disabled=True)

        if job.preview_thumbnail_image is not None:
            self._invalidate_thumbnail_request("active")
            self._render_focus_thumbnail_surfaces(
                job.preview_thumbnail_image,
                placeholder=False,
                target="active",
            )
        elif local_thumbnail_path is not None:
            self._load_thumbnail_file(local_thumbnail_path, target="active")
        elif thumbnail_url:
            self._reset_active_thumbnail()
            self._load_thumbnail_preview(
                thumbnail_url,
                target="active",
                owner_run_id=job.run_id,
                cache_info=info,
                source_url=job.url,
            )
        else:
            self._reset_active_thumbnail()
        self._refresh_focus_run_deck()

    def _active_run_for_metadata_event(
        self, event_job: DownloadJob
    ) -> DownloadJob | None:
        """Resolve worker copies to the one active run authority; reject stale run events."""
        active_job = self.active_job
        if (
            active_job is None
            or event_job.run_id != active_job.run_id
            or self._library_run_is_suppressed(event_job)
        ):
            return None
        return active_job

    def _library_run_is_suppressed(self, job: DownloadJob | None) -> bool:
        if job is None:
            return False
        suppressed = self.__dict__.get("_library_suppressed_run_ids", set())
        return job.run_id in suppressed or bool(
            job.origin_run_id and job.origin_run_id in suppressed
        )

    def _rebuild_output_dir_index(self) -> None:
        self.video_output_dirs_by_id = {}
        for item in self.metadata_items:
            video_id = str(item.get("id") or "")
            output_dir = history_output_dir(item)
            if video_id and output_dir is not None:
                self.video_output_dirs_by_id.setdefault(video_id, output_dir)

    def _render_metadata_tree(self, *, selected_index: int | None = None) -> None:
        selected_iid = (
            self.video_tree.selection()[0] if self.video_tree.selection() else None
        )
        visible_indices = metadata_indices_for_output_type(
            self.metadata_items, self.library_output_type_var.get()
        )
        rows: list[tuple[str, tuple[Any, ...]]] = []
        for visible_position, metadata_index in enumerate(visible_indices, start=1):
            item = self.metadata_items[metadata_index]
            output_dir = history_output_dir(item)
            terminal_status = str(item.get("vodforge_terminal_status") or "").strip()
            location = (
                terminal_status
                or (output_dir.name if output_dir is not None else "")
                or (
                    "Preview complete"
                    if is_metadata_preview(item)
                    else "Not downloaded"
                )
            )
            retry_available = terminal_status in {"Skipped", "Failed"} and bool(
                item.get("vodforge_terminal_run_id")
            )
            values: tuple[Any, ...] = (
                *video_list_row_values(item, fallback_index=visible_position),
                location,
            )
            if "action" in self.video_tree["columns"]:
                values = (*values, "↻" if retry_available else "")
            rows.append((str(metadata_index), values))
        preferred = str(selected_index) if selected_index is not None else selected_iid
        target = (
            preferred
            if preferred is not None and any(iid == preferred for iid, _values in rows)
            else rows[0][0]
            if rows
            else None
        )
        children = self.video_tree.replace_rows(rows, selected=target)
        if children and target is not None:
            _focus_library_table_item(self.video_tree, target)
            self._display_selected_metadata(int(target))
        else:
            self._clear_library_selection()
        if hasattr(self, "focus_run_deck"):
            self._refresh_focus_run_deck()

    def _clear_library_selection(self) -> None:
        output_type = self.library_output_type_var.get()
        self.selected_title_var.set(
            f"No {output_type} items yet. Preview or forge a URL to add one."
        )
        if hasattr(self, "selected_meta_var"):
            self.selected_meta_var.set("")
        if hasattr(self, "selected_location_var"):
            self.selected_location_var.set("")
        self._focus_selected_location_is_status = False
        self._queue_focus_selected_overview_layout()
        self.last_thumbnail_url = None
        self._set_text(self.pulled_tags_text, f"No {output_type} item selected.")
        self._set_text(
            self.description_text, f"Your {output_type} metadata will appear here."
        )
        self._set_text(self.source_summary_text, "No source selected.", disabled=True)
        self._set_text(self.output_summary_text, "No output selected.", disabled=True)
        if (
            hasattr(self, "focus_run_deck")
            and self._focus_brand_source_image is not None
        ):
            self._render_focus_thumbnail_surfaces(
                self._focus_brand_source_image,
                placeholder=True,
                target="library",
            )

    def _on_video_selected(self, _event: Any = None) -> None:
        selection = self.video_tree.selection()
        if selection:
            try:
                index = int(selection[0])
            except (TypeError, ValueError):
                index = 0
            self._display_selected_metadata(index)

    def _terminal_job_for_metadata(self, info: dict[str, Any]) -> DownloadJob | None:
        run_id = str(info.get("vodforge_terminal_run_id") or "")
        return next((job for job in self._terminal_jobs if job.run_id == run_id), None)

    def _on_library_tree_click(self, event: tk.Event[Any]) -> str | None:
        row = self.video_tree.identify_row(event.y)
        column = self.video_tree.identify_column(event.x)
        if not row or column != f"#{len(self.video_tree['columns'])}":
            return None
        try:
            info = self.metadata_items[int(row)]
        except (IndexError, TypeError, ValueError):
            return None
        terminal_job = self._terminal_job_for_metadata(info)
        if terminal_job is None:
            return None
        self.video_tree.selection_set(row)
        self._retry_terminal_job(terminal_job)
        return "break"

    def _show_library_row_menu(self, event: tk.Event[Any]) -> str:
        row = self.video_tree.identify_row(event.y)
        if row:
            self.video_tree.selection_set(row)
            _focus_library_table_item(self.video_tree, row)
            self._display_selected_metadata(int(row))
        menu = tk.Menu(
            self,
            tearoff=False,
            bg=THEME["surface"],
            fg=THEME["text"],
            activebackground=THEME["accent_dark"],
            activeforeground="#ffffff",
        )
        info = None
        if row:
            try:
                info = self.metadata_items[int(row)]
            except (IndexError, TypeError, ValueError):
                info = None
        terminal_job = (
            self._terminal_job_for_metadata(info) if isinstance(info, dict) else None
        )
        if is_metadata_preview(info):
            menu.add_command(
                label="Start download in Forge",
                command=lambda: self._start_preview_download(info),
            )
            menu.add_separator()
        elif terminal_job is not None:
            menu.add_command(
                label="↻ Retry in Forge",
                command=lambda: self._retry_terminal_job(terminal_job),
            )
            menu.add_separator()
        if isinstance(info, dict) and history_output_dir(info) is not None:
            menu.add_command(
                label="Open saved location", command=self._open_selected_saved_location
            )
            menu.add_separator()
        if isinstance(info, dict) and canonical_youtube_url(info):
            menu.add_command(
                label="Copy YouTube URL",
                command=partial(self._copy_youtube_url, info),
            )
            menu.add_separator()
        menu.add_command(
            label="Remove from Library…", command=self._remove_selected_library_item
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _remove_selected_library_item(self) -> None:
        selection = self.video_tree.selection()
        if not selection:
            return
        try:
            index = int(selection[0])
            info = self.metadata_items[index]
        except (IndexError, TypeError, ValueError):
            return
        title = str(info.get("title") or info.get("id") or "this item")
        active_job_value = self.__dict__.get("active_job")
        active_job = (
            active_job_value if isinstance(active_job_value, DownloadJob) else None
        )
        plan = resolve_library_removal_plan(
            info,
            active_job=active_job,
            pending_jobs=self.__dict__.get("pending_jobs", []),
        )
        if not messagebox.askyesno(
            APP_NAME,
            (
                f"Remove “{title}” from VODForge Library and Forge recents?\n\n"
                "This removes its VODForge history cards. Media files and folders remain on your computer."
                + plan.execution_notice
            ),
        ):
            return
        try:
            removed_run_ids = self._apply_library_removal_plan(info, index, plan)
        except HistoryError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        self._render_metadata_tree()
        self._reconcile_focus_after_library_removal(removed_run_ids)
        if plan.active_run_id is not None:
            self.status_var.set(
                "Removed the item from Library and Forge recents; its active run is stopping. Media files were not deleted."
            )
        elif plan.queued_run_ids:
            self.status_var.set(
                "Removed the item and its queued run from Library and Forge. Media files were not deleted."
            )
        else:
            self.status_var.set(
                "Removed the item from Library and Forge recents. Media files were not deleted."
            )

    def _apply_library_removal_plan(
        self,
        info: dict[str, Any],
        index: int,
        plan: LibraryRemovalPlan,
    ) -> set[str]:
        """Persist removal before applying its live Library and Forge effects."""
        prospective_history = self.download_history
        if plan.history_identity is not None:
            prospective_history = [
                item
                for item in self.download_history
                if history_identity(item) != plan.history_identity
            ]
            save_history(self.history_path, prospective_history)
            self.download_history = prospective_history

        removed_run_ids = set(plan.execution_run_ids)
        if removed_run_ids:
            self.__dict__.setdefault("_library_suppressed_run_ids", set()).update(
                removed_run_ids
            )
        if plan.queued_run_ids:
            self.pending_jobs = [
                job
                for job in self.__dict__.get("pending_jobs", [])
                if job.run_id not in plan.queued_run_ids
            ]
        if plan.active_run_id is not None:
            self._cancel()
        removed_run_ids.update(self._remove_library_item_from_forge_recents(info))
        removed_run_ids.add(
            str(info.get("vodforge_preview_run_id") or f"history:{index}")
        )
        self.metadata_items.pop(index)
        self._rebuild_output_dir_index()
        return removed_run_ids

    def _remove_library_item_from_forge_recents(self, info: dict[str, Any]) -> set[str]:
        """Remove one item's presentation history without deleting media files."""
        removed_run_ids: set[str] = set()
        saved = history_output_dir(info)
        if saved is not None:
            identity = history_identity(info)
            for completed_job in self.__dict__.get("_completed_jobs", []):
                if identity in completed_job.history_identities:
                    removed_run_ids.add(completed_job.run_id)
                completed_job.history_identities.discard(identity)
        terminal_run_ids = {str(info.get("vodforge_terminal_run_id") or "")}
        item_key = metadata_run_key(info)
        if item_key is not None:
            for terminal_job in self._terminal_jobs:
                terminal_info = terminal_job.preview_info or {}
                if (
                    item_key in terminal_job.metadata_keys
                    or metadata_run_key(terminal_info) == item_key
                ):
                    terminal_run_ids.add(terminal_job.run_id)
        terminal_run_ids.discard("")
        if terminal_run_ids:
            self._terminal_jobs = [
                job for job in self._terminal_jobs if job.run_id not in terminal_run_ids
            ]
            removed_run_ids.update(terminal_run_ids)
        return removed_run_ids

    def _reconcile_focus_after_library_removal(self, removed_run_ids: set[str]) -> None:
        """Render a surviving Forge record when the selected history item was removed."""
        selected_run_id = str(self.__dict__.get("_focus_selected_run_id") or "")
        if not selected_run_id or self.__dict__.get("focus_run_deck") is None:
            return
        records = self._focus_run_records()
        if selected_run_id not in removed_run_ids and any(
            str(record.get("run_id") or "") == selected_run_id for record in records
        ):
            return
        if records:
            self._focus_select_run_record(records[0])
            self._refresh_focus_run_deck()
            return
        self._focus_selected_run_id = None
        self._set_focus_preview_start_action(None)
        self._set_focus_progress_color()
        self.focus_active_title_var.set("Ready for a new run")
        self.focus_active_detail_var.set(
            "Paste a YouTube URL above, then press Return to begin."
        )
        self.focus_active_duration_var.set("")
        output_type = self._selected_output_type()
        self.focus_active_profile_var.set(self._focus_profile_text(output_type))
        self.focus_display_progress_var.set(0)
        self.focus_percent_var.set("0%")
        self.focus_display_status_var.set("No run selected")
        self.focus_transfer_var.set(self._focus_next_run_transfer_text(output_type))
        self._set_text(
            self.focus_summary_text,
            self._focus_next_run_summary(output_type),
            disabled=True,
        )
        self._render_focus_run_activity("", "No run selected.")
        self._reset_active_thumbnail()
        self._refresh_focus_run_deck()

    def _set_text(self, widget: tk.Text, text: str, *, disabled: bool = False) -> None:
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        if disabled:
            widget.config(state="disabled")

    def _set_encoding_summary_text(self, widget: tk.Text, text: str) -> None:
        widget.config(state="normal")
        widget.delete("1.0", "end")
        for line_index, line in enumerate(text.splitlines()):
            if line_index:
                widget.insert("end", "\n")
            label, separator, value = line.partition(":")
            if not separator:
                widget.insert("end", line)
                continue
            tag_name = f"summary-label-{line_index}"
            widget.tag_configure(tag_name, foreground=summary_label_color(label))
            widget.insert("end", f"{label}:", tag_name)
            widget.insert("end", value)
        widget.config(state="disabled")

    def _display_selected_metadata(self, index: int) -> None:
        if index < 0 or index >= len(self.metadata_items):
            return
        info = self.metadata_items[index]
        title = str(info.get("title") or info.get("id") or "selected video")
        creator = str(info.get("uploader") or info.get("channel") or "Unknown creator")
        output_type = metadata_output_type(info)
        saved = history_output_dir(info)
        terminal_status = str(info.get("vodforge_terminal_status") or "").strip()
        terminal_message = str(info.get("vodforge_terminal_message") or "").strip()
        if terminal_status:
            location_text = terminal_status + (
                f" — {terminal_message}" if terminal_message else ""
            )
        elif is_metadata_preview(info):
            location_text = "Preview complete — Start download in Forge when ready"
        else:
            location_text = (
                f"Saved in {saved}"
                if saved is not None
                else "Not downloaded in this history"
            )
        metadata_text = (
            f"{output_type.value} • {creator} • {format_duration(info.get('duration'))} • "
            f"{info.get('id') or 'no id'}"
        )
        if hasattr(self, "selected_meta_var") and hasattr(
            self, "selected_location_var"
        ):
            self.selected_title_var.set(title)
            self.selected_meta_var.set(metadata_text)
            self.selected_location_var.set(location_text)
            self._focus_selected_location_is_status = bool(
                terminal_status or is_metadata_preview(info)
            )
            self._queue_focus_selected_overview_layout()
        else:
            self.selected_title_var.set(f"{title}\n{metadata_text}\n{location_text}")
        tags_text = build_tags_display_text(info)
        description = build_description_display_text(info)
        self._set_text(
            self.pulled_tags_text, tags_text or "No tags found for this video."
        )
        self._set_text(
            self.description_text, description or "No description found for this video."
        )
        source_summary, output_summary = build_encoding_summary_display(info)
        if is_metadata_preview(info):
            output_summary = preview_output_summary_display()
        self._set_encoding_summary_text(self.source_summary_text, source_summary)
        self._set_encoding_summary_text(self.output_summary_text, output_summary)
        thumb = best_thumbnail(info)
        self.last_thumbnail_url = str((thumb or {}).get("url") or "") or None
        preview_thumbnail = str(info.get("preview_thumbnail_path") or "").strip()
        preview_thumbnail_path = Path(preview_thumbnail) if preview_thumbnail else None
        local_thumbnail = saved / "thumbnail.jpeg" if saved is not None else None
        cached_thumbnail = existing_cached_thumbnail_path(info)
        thumbnail_target = "library"
        if preview_thumbnail_path is not None and preview_thumbnail_path.is_file():
            self._load_thumbnail_file(preview_thumbnail_path, target=thumbnail_target)
        elif local_thumbnail is not None and local_thumbnail.is_file():
            self._load_thumbnail_file(local_thumbnail, target=thumbnail_target)
        elif cached_thumbnail is not None and cached_thumbnail.is_file():
            self._load_thumbnail_file(cached_thumbnail, target=thumbnail_target)
        elif self.last_thumbnail_url:
            self._load_thumbnail_preview(
                self.last_thumbnail_url,
                target=thumbnail_target,
                cache_info=info,
            )
        else:
            if (
                hasattr(self, "focus_run_deck")
                and self._focus_brand_source_image is not None
            ):
                self._render_focus_thumbnail_surfaces(
                    self._focus_brand_source_image,
                    placeholder=True,
                    target=thumbnail_target,
                )
            else:
                self.thumbnail_label.config(image="", text="No thumbnail loaded")

    def _render_focus_thumbnail_surfaces(
        self,
        source: Any | None = None,
        *,
        library_width: int | None = None,
        placeholder: bool | None = None,
        source_path: Path | None = None,
        target: str = "both",
    ) -> None:
        if (
            Image is None
            or ImageOps is None
            or ImageTk is None
            or not hasattr(self, "focus_thumbnail_wrap")
        ):
            return
        if target not in {"active", "library", "both"}:
            raise ValueError(f"Unsupported thumbnail target: {target}")
        if source is not None:
            normalized = source.convert("RGBA").copy()
            if target in {"active", "both"}:
                self._focus_active_thumbnail_source_image = normalized.copy()
                self._focus_active_thumbnail_source_path = source_path
                if placeholder is not None:
                    self._focus_active_thumbnail_is_placeholder = placeholder
            if target in {"library", "both"}:
                self._focus_thumbnail_source_image = normalized.copy()
                self._focus_thumbnail_source_path = source_path
                if placeholder is not None:
                    self._focus_thumbnail_is_placeholder = placeholder
        active_image = (
            self._focus_active_thumbnail_source_image or self._focus_brand_source_image
        )
        library_image = (
            self._focus_thumbnail_source_image or self._focus_brand_source_image
        )
        if active_image is None or library_image is None:
            return
        width = library_width or max(1, self.focus_thumbnail_wrap.winfo_width())
        if width <= 1:
            width = max(180, self.focus_thumbnail_wrap.winfo_reqwidth())
        active_size = youtube_thumbnail_size(152)
        library_size = library_thumbnail_size(width)
        if int(self.focus_thumbnail_wrap.cget("height")) != library_size[1]:
            self.focus_thumbnail_wrap.configure(height=library_size[1])
        active_rendered = self._render_focus_thumbnail_image(
            active_image,
            active_size,
            placeholder=self._focus_active_thumbnail_is_placeholder,
            source_path=self._focus_active_thumbnail_source_path,
        )
        library_rendered = self._render_focus_thumbnail_image(
            library_image,
            library_size,
            placeholder=self._focus_thumbnail_is_placeholder,
            source_path=self._focus_thumbnail_source_path,
        )
        if active_rendered is not None and library_rendered is not None:
            self._set_focus_thumbnail_images(
                active_rendered,
                library_rendered,
                native=isinstance(active_rendered, str)
                or isinstance(library_rendered, str),
            )

    def _render_focus_thumbnail_image(
        self,
        image: Any,
        size: tuple[int, int],
        *,
        placeholder: bool,
        source_path: Path | None,
    ) -> Any | None:
        if not placeholder and source_path is not None:
            native = self._create_focus_native_image(
                source_path,
                thumbnail_size_within(tuple(image.size), size),
                radius=10,
            )
            if native is not None:
                return native
        rendered = (
            rounded_contain_image(image, size, 10, THEME["surface"])
            if placeholder
            else rounded_fit_image(image, size, 10)
        )
        return ImageTk.PhotoImage(flatten_alpha_image(rendered, THEME["bg"]))

    def _create_focus_native_image(
        self, path: Path, size: tuple[int, int], *, radius: int = 0
    ) -> str | None:
        """Use AppKit-backed NSImage drawing when Tk exposes it on macOS."""
        if not is_macos() or not path.is_file():
            return None
        try:
            image_types = self.tk.splitlist(self.tk.call("image", "types"))
            if "nsimage" not in image_types:
                return None
            options: list[Any] = [
                "image",
                "create",
                "nsimage",
                "-source",
                str(path),
                "-as",
                "file",
                "-width",
                size[0],
                "-height",
                size[1],
            ]
            if radius > 0:
                options.extend(("-radius", radius))
            return str(self.tk.call(*options))
        except tk.TclError as exc:
            write_diagnostic(
                f"native thumbnail image could not be loaded ({path}): {exc}"
            )
            return None

    def _delete_focus_native_images(self, *images: Any) -> None:
        for image in images:
            if not isinstance(image, str) or not image:
                continue
            try:
                self.tk.call("image", "delete", image)
            except tk.TclError:
                pass

    def _set_focus_thumbnail_images(
        self, active: Any, library: Any, *, native: bool
    ) -> None:
        old_native = getattr(self, "_focus_native_thumbnail_images", ())
        self.focus_active_thumbnail_image = active
        self.thumbnail_image = library
        self.focus_active_thumbnail_label.config(image=active, text="")
        self.thumbnail_label.config(image=library, text="")
        self._focus_native_thumbnail_images = (active, library) if native else ()
        self._delete_focus_native_images(*old_native)

    def _thumbnail_request_ids(self) -> dict[str, int]:
        request_ids = getattr(self, "_thumbnail_preview_request_ids", None)
        if not isinstance(request_ids, dict):
            request_ids = {"active": 0, "library": 0}
            self._thumbnail_preview_request_ids = request_ids
        return request_ids

    def _invalidate_thumbnail_request(self, target: str) -> int:
        if target not in {"active", "library"} and not target.startswith("run:"):
            raise ValueError(
                f"Thumbnail requests require one owning surface, not {target!r}."
            )
        request_ids = self._thumbnail_request_ids()
        request_ids[target] = int(request_ids.get(target, 0)) + 1
        return request_ids[target]

    def _thumbnail_label_for_target(self, target: str) -> Any:
        if target == "active" and hasattr(self, "focus_active_thumbnail_label"):
            return self.focus_active_thumbnail_label
        return self.thumbnail_label

    def _reset_active_thumbnail(self) -> None:
        self._invalidate_thumbnail_request("active")
        if self._focus_brand_source_image is not None:
            self._render_focus_thumbnail_surfaces(
                self._focus_brand_source_image,
                placeholder=True,
                target="active",
            )

    def _load_thumbnail_file(
        self, path: Path, *, target: str, owner_run_id: str = ""
    ) -> None:
        self._invalidate_thumbnail_request(target)
        target_label = self._thumbnail_label_for_target(target)
        if Image is None or ImageTk is None:
            target_label.config(text=f"Saved thumbnail:\n{path}")
            return
        try:
            with Image.open(path) as source:
                image = source.copy()
            if (
                target == "active"
                and self.active_job is not None
                and (not owner_run_id or owner_run_id == self.active_job.run_id)
            ):
                self.active_job.preview_thumbnail_image = image.convert("RGBA").copy()
            if hasattr(self, "focus_run_deck"):
                self._render_focus_thumbnail_surfaces(
                    image, placeholder=False, source_path=path, target=target
                )
                return
            image.thumbnail((260, 150))
            self.thumbnail_image = ImageTk.PhotoImage(image)
            self.thumbnail_label.config(image=self.thumbnail_image, text="")
        except Exception as exc:  # noqa: BLE001 - optional saved-artwork preview remains nonfatal
            target_label.config(
                text=f"Saved thumbnail preview failed:\n{exc}\n\n{path}"
            )

    def _load_thumbnail_preview(
        self,
        url: str,
        *,
        target: str,
        owner_run_id: str = "",
        cache_info: dict[str, Any] | None = None,
        source_url: str | None = None,
    ) -> None:
        target_label = self._thumbnail_label_for_target(target)
        if Image is None or ImageTk is None:
            target_label.config(text=f"Thumbnail URL:\n{url}")
            return
        request_target = target
        request_id = self._invalidate_thumbnail_request(request_target)
        request_queue = getattr(self, "_thumbnail_preview_requests", None)
        worker = getattr(self, "_thumbnail_preview_thread", None)
        if request_queue is None:
            request_queue = queue.Queue(maxsize=2)
            self._thumbnail_preview_requests = request_queue
        retained: list[
            tuple[int, str, str, str, dict[str, Any] | None, str | None]
        ] = []
        while True:
            try:
                pending = request_queue.get_nowait()
                request_queue.task_done()
            except queue.Empty:
                break
            if len(pending) >= 4 and pending[2] != request_target:
                retained.append(pending)
        for pending in retained[-1:]:
            request_queue.put_nowait(pending)
        request_queue.put_nowait(
            (
                request_id,
                url,
                request_target,
                owner_run_id,
                dict(cache_info) if cache_info else None,
                source_url,
            )
        )
        if worker is None or not worker.is_alive():
            worker = threading.Thread(target=self._thumbnail_preview_loop, daemon=True)
            self._thumbnail_preview_thread = worker
            worker.start()
        if not target.startswith("run:"):
            target_label.config(text="Loading thumbnail…")

    def _thumbnail_preview_loop(self) -> None:
        request_queue: queue.Queue[
            tuple[int, str, str, str, dict[str, Any] | None, str | None]
        ] = self._thumbnail_preview_requests
        while True:
            request = request_queue.get()
            request_id, url, target, owner_run_id = request[:4]
            cache_info = request[4] if len(request) > 4 else None
            source_url = request[5] if len(request) > 5 else None
            try:
                self._fetch_thumbnail_preview_request(
                    request_id,
                    url,
                    target,
                    owner_run_id,
                    cache_info,
                    source_url,
                )
            except Exception as exc:  # noqa: BLE001 - worker reports arbitrary thumbnail failures
                self.events.put(
                    thumbnail_preview_event(
                        request_id,
                        url,
                        target,
                        owner_run_id,
                        error=str(exc),
                    )
                )
            finally:
                request_queue.task_done()

    def _fetch_thumbnail_preview_request(
        self,
        request_id: int,
        url: str,
        target: str,
        owner_run_id: str,
        cache_info: dict[str, Any] | None = None,
        source_url: str | None = None,
    ) -> None:
        if bool(
            self.__dict__.get("_closing", False)
        ) or request_id != self._thumbnail_request_ids().get(target, 0):
            return
        # Thumbnail bytes are already independently bounded by URL scheme,
        # response size, timeout, and decoded pixel count. They do not use the
        # yt-dlp provider session, so delaying them behind the entire primary
        # media operation only leaves a placeholder visible for most of a run.
        data = download_bounded_url_bytes(
            url,
            source_url=source_url,
            timeout_seconds=15,
        )
        if bool(
            self.__dict__.get("_closing", False)
        ) or request_id != self._thumbnail_request_ids().get(target, 0):
            return
        if cache_info:
            try:
                save_cached_thumbnail_bytes(cache_info, data)
            except Exception as exc:  # noqa: BLE001 - optional cache writes must not fail the preview
                write_diagnostic(
                    f"remote thumbnail cache write failed: {type(exc).__name__}: {exc}"
                )
        self.events.put(
            thumbnail_preview_event(
                request_id,
                url,
                target,
                owner_run_id,
                data=data,
            )
        )

    def _display_thumbnail_preview_result(self, payload: dict[str, Any]) -> None:
        target = str(payload.get("target") or "library")
        if int(payload.get("id") or -1) != self._thumbnail_request_ids().get(target, 0):
            return
        error = str(payload.get("error") or "").strip()
        url = str(payload.get("url") or "")
        target_label = self._thumbnail_label_for_target(target)
        owner_run_id = str(payload.get("run_id") or "")
        selected_run_id = str(self.__dict__.get("_focus_selected_run_id") or "")
        if error:
            if target.startswith("run:") or (
                target == "active" and owner_run_id and owner_run_id != selected_run_id
            ):
                write_diagnostic(
                    f"run thumbnail preview failed: run_id={owner_run_id} error={error}"
                )
                if self.__dict__.get("focus_run_deck") is not None:
                    self._refresh_focus_run_deck()
                return
            target_label.config(
                text=f"Thumbnail preview failed:\n{error}\n\nURL:\n{url}"
            )
            return
        try:
            image = decode_bounded_thumbnail(bytes(payload.get("data") or b""))
            if hasattr(self, "focus_run_deck"):
                if (target == "active" or target.startswith("run:")) and owner_run_id:
                    owner_job = (
                        self.active_job
                        if self.active_job is not None
                        and self.active_job.run_id == owner_run_id
                        else next(
                            (
                                job
                                for job in [
                                    *self._terminal_jobs,
                                    *getattr(self, "_completed_jobs", []),
                                ]
                                if job.run_id == owner_run_id
                            ),
                            None,
                        )
                    )
                    if owner_job is not None:
                        owner_job.preview_thumbnail_image = image.convert("RGBA").copy()
                    if target.startswith("run:") or owner_run_id != selected_run_id:
                        self._refresh_focus_run_deck()
                        return
                self._render_focus_thumbnail_surfaces(
                    image, placeholder=False, target=target
                )
                self._refresh_focus_run_deck()
                return
            image.thumbnail((260, 150))
            self.thumbnail_image = ImageTk.PhotoImage(image)
            self.thumbnail_label.config(image=self.thumbnail_image, text="")
        except Exception as exc:  # noqa: BLE001 - optional preview rendering keeps UI responsive
            if target.startswith("run:") or (
                target == "active" and owner_run_id and owner_run_id != selected_run_id
            ):
                write_diagnostic(
                    f"run thumbnail decode failed: run_id={owner_run_id} error={exc}"
                )
                if self.__dict__.get("focus_run_deck") is not None:
                    self._refresh_focus_run_deck()
                return
            target_label.config(text=f"Thumbnail preview failed:\n{exc}\n\nURL:\n{url}")

    def _start_download(self) -> None:
        urls = (
            list(self.batch_urls) if self.batch_urls else [self.url_var.get().strip()]
        )
        job = self._build_download_job_from_current_settings(
            urls,
            output_type=self._selected_output_type(),
            single_video_only=self.single_video_only_var.get(),
            batch_mode=bool(self.batch_urls),
        )
        if job is None:
            return
        self._adopt_matching_preview_for_download_job(job)
        self._start_or_queue_download_job(job, clear_source=True)

    def _adopt_matching_preview_for_download_job(self, job: DownloadJob) -> bool:
        """Seed a fresh run from its preview so one item changes state instead of duplicating."""
        source_urls = job.urls or [job.url]
        if job.batch_mode or len(source_urls) != 1:
            return False
        video_id = youtube_url_video_id(job.url)
        if not video_id:
            return False
        preview_key = (video_id, job.output_type.value)
        preview = next(
            (
                item
                for item in self.metadata_items
                if is_metadata_preview(item) and metadata_run_key(item) == preview_key
            ),
            None,
        )
        if preview is None:
            return False
        job.preview_info = dict(preview)
        job.preview_info.pop("vodforge_preview_complete", None)
        job.preview_info.pop("vodforge_preview_run_id", None)
        job.metadata_keys.add(preview_key)
        claim_active_metadata_row(preview, job.preview_info, job.run_id)
        return True

    def _validated_submission_urls(
        self, urls: list[str], *, single_video_only: bool
    ) -> list[str] | None:
        normalized_urls = [str(url).strip() for url in urls if str(url).strip()]
        if single_video_only:
            for url in normalized_urls:
                single_video_error = single_video_url_requires_video_id_error(url)
                if single_video_error:
                    messagebox.showerror(APP_NAME, single_video_error)
                    return None
        return normalized_urls

    def _validated_submission_output_directory(self) -> Path | None:
        output_text = self.output_var.get().strip()
        if not output_text:
            messagebox.showerror(APP_NAME, "Choose an output folder.")
            return None
        output_dir = Path(output_text).expanduser()
        try:
            validate_output_directory_access(output_dir)
        except OSError as exc:
            messagebox.showerror(
                APP_NAME,
                "VODForge cannot write to the selected output folder. "
                f"Choose another folder or allow access, then try again.\n\n{exc}",
            )
            return None
        return output_dir

    def _submission_cookie_inputs_are_valid(
        self,
        cookie_source: CookieSource,
        cookie_file: Path | None,
        cookie_browser: str | None,
    ) -> bool:
        if cookie_source == CookieSource.FILE and cookie_file is None:
            messagebox.showerror(
                APP_NAME,
                "Choose a YouTube cookies.txt file, or switch YouTube access back to Public.",
            )
            return False
        if cookie_source == CookieSource.BROWSER and cookie_browser is None:
            messagebox.showerror(
                APP_NAME,
                "Choose a browser profile, or switch YouTube access back to Public.",
            )
            return False
        cookie_warning = (
            windows_chromium_cookie_warning(cookie_browser)
            if cookie_source == CookieSource.BROWSER
            else None
        )
        if cookie_warning:
            messagebox.showerror(APP_NAME, cookie_warning)
            return False
        return True

    def _validated_submission_export_settings(
        self, output_type: OutputType
    ) -> tuple[ExportMode, ManualExportSettings, Mp3ExportSettings] | None:
        export_mode = ExportMode(self.export_mode_var.get())
        try:
            manual_settings = (
                self._manual_export_settings()
                if output_type == OutputType.MP4
                and export_mode == ExportMode.MANUAL_OVERRIDE
                else ManualExportSettings()
            )
            mp3_settings = (
                self._mp3_export_settings()
                if output_type == OutputType.MP3
                else Mp3ExportSettings()
            )
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return None
        return export_mode, manual_settings, mp3_settings

    def _build_download_job_from_current_settings(
        self,
        urls: list[str],
        *,
        output_type: OutputType,
        single_video_only: bool,
        batch_mode: bool,
    ) -> DownloadJob | None:
        normalized_urls = self._validated_submission_urls(
            urls, single_video_only=single_video_only
        )
        if normalized_urls is None:
            return None
        url = normalized_urls[0] if normalized_urls else ""
        write_diagnostic(f"URL received: {url}")
        write_diagnostic(f"normalized URL: {url}")
        write_diagnostic(f"batch URL count: {len(normalized_urls)}")
        cookie_source = self._selected_cookie_source()
        use_cookies, cookie_file, cookie_browser = self._cookie_inputs()
        write_diagnostic(
            f"playlist query present: {'list=' in url.lower()} ; ignore_playlists={single_video_only} ; use_nvenc={self.use_nvenc_var.get()} ; cookie_source={cookie_source.value}"
        )
        if not url:
            messagebox.showerror(
                APP_NAME, "Paste a YouTube URL first or load a URL list text file."
            )
            return None
        output_dir = self._validated_submission_output_directory()
        if output_dir is None:
            return None
        if not self._submission_cookie_inputs_are_valid(
            cookie_source, cookie_file, cookie_browser
        ):
            return None

        tags = [tag.strip() for tag in self.tags_var.get().split(",") if tag.strip()]
        export_settings = self._validated_submission_export_settings(output_type)
        if export_settings is None:
            return None
        export_mode, manual_settings, mp3_settings = export_settings
        return DownloadJob(
            url=url,
            output_dir=output_dir,
            output_type=output_type,
            quality_label=self.quality_var.get(),
            export_mode=export_mode,
            manual_settings=manual_settings,
            mp3_settings=mp3_settings,
            single_video_only=single_video_only,
            use_nvenc=self.use_nvenc_var.get()
            if output_type == OutputType.MP4
            else False,
            embed_thumbnail=self.embed_thumbnail_var.get()
            if output_type == OutputType.MP4
            else False,
            write_thumbnail=self.write_thumbnail_var.get()
            if output_type == OutputType.MP4
            else False,
            embed_metadata=self.embed_metadata_var.get()
            if output_type == OutputType.MP4
            else False,
            write_info_json=self.write_info_json_var.get()
            if output_type == OutputType.MP4
            else False,
            tags=tags,
            urls=normalized_urls,
            use_cookies=use_cookies,
            cookie_file=cookie_file,
            cookie_browser=cookie_browser,
            batch_mode=batch_mode,
        )

    def _start_or_queue_download_job(
        self, job: DownloadJob, *, clear_source: bool
    ) -> None:
        if self.worker is not None and self.worker.is_alive():
            self.pending_jobs.append(job)
            if hasattr(self, "focus_run_deck"):
                self.focus_engine_var.set(
                    f"1 active  /  {len(self.pending_jobs)} queued  /  runs process one at a time"
                )
                self._append_log(f"Queued {job.output_type.value} run: {job.url}")
                self._refresh_focus_run_deck()
                self.download_button.configure(text="Queue run", state="normal")
                self._enqueue_queue_preview(job)
            if clear_source:
                self._reset_source_input_after_send()
            return

        self._launch_download_job(job)
        if clear_source:
            self._reset_source_input_after_send()

    def _start_preview_download(self, info: dict[str, Any]) -> None:
        """Turn one metadata preview into a fresh Forge-owned one-item run."""
        fallback_url = str(
            info.get("webpage_url") or info.get("original_url") or info.get("url") or ""
        ).strip()
        source_url = retry_url_for_item(info, fallback_url) if fallback_url else ""
        if not source_url:
            messagebox.showinfo(
                APP_NAME, "This preview does not include a source URL to download."
            )
            return
        output_type = metadata_output_type(info)
        job = self._build_download_job_from_current_settings(
            [source_url],
            output_type=output_type,
            single_video_only=True,
            batch_mode=False,
        )
        if job is None:
            return
        job.preview_info = dict(info)
        job.preview_info.pop("vodforge_preview_complete", None)
        job.preview_info.pop("vodforge_preview_run_id", None)
        key = metadata_run_key(info)
        if key is not None:
            job.metadata_keys.add(key)
        claim_active_metadata_row(info, job.preview_info, job.run_id)
        self._focus_selected_run_id = job.run_id
        self._start_or_queue_download_job(job, clear_source=False)
        self._select_focus_view("forge")
        if any(pending is job for pending in self.pending_jobs):
            record = next(
                (
                    candidate
                    for candidate in self._focus_run_records()
                    if candidate.get("run_id") == job.run_id
                ),
                None,
            )
            if record is not None:
                self._display_focus_queued_job_snapshot(record, job)

    def _launch_download_job(
        self, job: DownloadJob, *, select_detail: bool = True
    ) -> None:
        self.active_job = job
        if select_detail:
            self._focus_selected_run_id = job.run_id

        self.cancel_requested = False
        self.skip_video_requested = False
        self.skip_url_requested = False
        self._last_progress_event_at = 0.0
        self.progress_var.set(0)
        self.status_var.set("Starting…")
        if hasattr(self, "focus_active_title_var") and select_detail:
            self.focus_active_title_var.set(download_job_display_title(job))
            preview_info = job.preview_info or {}
            self.focus_active_detail_var.set(
                str(
                    preview_info.get("uploader")
                    or preview_info.get("channel")
                    or "Preparing source"
                )
            )
            self.focus_active_duration_var.set("")
            self.focus_active_profile_var.set(
                self._focus_profile_text(
                    job.output_type,
                    mp3_settings=job.mp3_settings,
                    quality_label=job.quality_label,
                    export_mode=job.export_mode,
                )
            )
            self.focus_transfer_var.set(
                "Preparing best audio source and MP3 plan"
                if job.output_type == OutputType.MP3
                else "Preparing source and MP4 output plan"
            )
            self._render_focus_run_activity(job.run_id, "Preparing this run…")
            self._set_text(
                self.focus_summary_text,
                (
                    "Format        MP3\nAudio         Pending\nOutput mode   Highest-quality source\n"
                    if job.output_type == OutputType.MP3
                    else f"Format        MP4\nVideo         H.264\nAudio         {job.manual_settings.audio_codec.value if job.export_mode == ExportMode.MANUAL_OVERRIDE else 'AAC'}\nOutput mode   Pending\n"
                )
                + f"Save to       {job.output_dir}",
                disabled=True,
            )
            if preview_info:
                self._display_active_job_metadata(job, preview_info)
            else:
                self._reset_active_thumbnail()
                self._refresh_focus_run_deck()
        elif hasattr(self, "focus_run_deck"):
            self._refresh_focus_run_deck()
        self.events.put(("progress_determinate", 0))
        if hasattr(self, "focus_run_deck"):
            self.download_button.config(text="Queue run", state="normal")
        else:
            self.download_button.config(state="disabled")
        self.cancel_button.config(state="normal")
        self.skip_video_button.config(state="normal")
        self.skip_url_button.config(state="normal")
        self.worker = threading.Thread(
            target=self._download_worker, args=(job,), daemon=True
        )
        self.worker.start()
        if hasattr(self, "focus_run_controls"):
            self._set_focus_run_controls_visible(True)
            self._apply_focus_layout(force=True)

    def _launch_next_pending_job(self) -> bool:
        if not self.pending_jobs:
            self.active_job = None
            if hasattr(self, "focus_run_deck"):
                self.download_button.configure(text="Forge", state="normal")
                self.focus_engine_var.set("Runs process one at a time")
            return False
        job = self.pending_jobs.pop(0)
        self._launch_download_job(job, select_detail=False)
        return True

    def _archive_active_terminal_job(self, status: str, message: str) -> None:
        job = self.active_job
        if job is None or self._library_run_is_suppressed(job):
            return
        job.terminal_status = status
        job.terminal_message = message
        if (
            job.preview_thumbnail_image is None
            and self._focus_active_thumbnail_source_image is not None
            and not self._focus_active_thumbnail_is_placeholder
            and self._focus_selected_run_id == job.run_id
        ):
            job.preview_thumbnail_image = (
                self._focus_active_thumbnail_source_image.convert("RGBA").copy()
            )
        self._terminal_jobs = [
            item for item in self._terminal_jobs if item.run_id != job.run_id
        ]
        self._terminal_jobs.insert(0, job)
        del self._terminal_jobs[20:]
        preview_key = metadata_run_key(job.preview_info or {})
        if preview_key is not None:
            matching = next(
                (
                    item
                    for item in self.metadata_items
                    if history_output_dir(item) is None
                    and metadata_run_key(item) == preview_key
                ),
                None,
            )
            if matching is not None:
                matching.pop(ACTIVE_METADATA_RUN_ID_KEY, None)
                matching.pop("vodforge_preview_complete", None)
                matching.pop("vodforge_preview_run_id", None)
                matching["vodforge_terminal_status"] = status
                matching["vodforge_terminal_message"] = message
                matching["vodforge_terminal_run_id"] = job.run_id

    def _archive_active_completed_job(self, status: str, message: str) -> None:
        job = self.active_job
        if job is None or self._library_run_is_suppressed(job):
            return
        job.terminal_status = status
        job.terminal_message = message
        if (
            job.preview_thumbnail_image is None
            and self._focus_active_thumbnail_source_image is not None
            and not self._focus_active_thumbnail_is_placeholder
            and self._focus_selected_run_id == job.run_id
        ):
            job.preview_thumbnail_image = (
                self._focus_active_thumbnail_source_image.convert("RGBA").copy()
            )
        self._completed_jobs = [
            item for item in self._completed_jobs if item.run_id != job.run_id
        ]
        self._completed_jobs.insert(0, job)
        del self._completed_jobs[20:]

    def _archive_item_terminal_job(
        self, job: DownloadJob, info: dict[str, Any]
    ) -> None:
        """Archive one playlist item attempt without transferring Library authority."""
        if self._library_run_is_suppressed(job):
            return
        self._terminal_jobs = [
            item for item in self._terminal_jobs if item.run_id != job.run_id
        ]
        self._terminal_jobs.insert(0, job)
        del self._terminal_jobs[20:]
        item_key = metadata_run_key(info)
        matching = next(
            (
                item
                for item in self.metadata_items
                if history_output_dir(item) is None
                and metadata_run_key(item) == item_key
            ),
            None,
        )
        if matching is not None:
            matching.update(info)
            matching.pop(ACTIVE_METADATA_RUN_ID_KEY, None)
        else:
            self.metadata_items.insert(0, dict(info))
        self._rebuild_output_dir_index()
        self._render_metadata_tree()
        if hasattr(self, "focus_run_deck"):
            self._focus_terminal_job(job)
            self._refresh_focus_run_deck()

    def _focus_terminal_job(self, job: DownloadJob) -> None:
        """Make a terminal outcome the explicit Forge selection and render it."""
        if self.__dict__.get("focus_run_deck") is None:
            return
        self._focus_selected_run_id = job.run_id
        if self.__dict__.get("_focus_views") is not None:
            self._select_focus_view("forge")
        record = next(
            (
                candidate
                for candidate in self._focus_run_records()
                if str(candidate.get("run_id") or "") == job.run_id
                and str(candidate.get("kind") or "") in {"failed", "skipped", "stopped"}
            ),
            None,
        )
        if record is not None:
            self._focus_select_run_record(record)

    def _retry_terminal_job(self, failed_job: DownloadJob) -> None:
        retry_url = retry_url_for_item(failed_job.preview_info or {}, failed_job.url)
        retry_job = replace(
            failed_job,
            url=retry_url,
            urls=[retry_url],
            run_id=uuid.uuid4().hex,
            origin_run_id=None,
            metadata_keys=set(),
            history_identities=set(),
            activity_lines=[],
            terminal_status=None,
            terminal_message="",
            item_terminal_emitted=False,
        )
        self._terminal_jobs = [
            item for item in self._terminal_jobs if item.run_id != failed_job.run_id
        ]
        self.metadata_items = [
            item
            for item in self.__dict__.get("metadata_items", [])
            if str(item.get("vodforge_terminal_run_id") or "") != failed_job.run_id
        ]
        self._rebuild_output_dir_index()
        if self.__dict__.get("video_tree") is not None:
            self._render_metadata_tree()
        if self.__dict__.get("_focus_views") is not None:
            self._select_focus_view("forge")
        if self.active_job is not None or (self.worker and self.worker.is_alive()):
            self.pending_jobs.append(retry_job)
            self._enqueue_queue_preview(retry_job)
            self._refresh_focus_run_deck()
            return
        self._launch_download_job(retry_job)

    def _cancel(self) -> None:
        self.cancel_requested = True
        self.status_var.set("Cancel requested; waiting for current step to stop…")
        threading.Thread(
            target=terminate_all_active_child_processes, daemon=True
        ).start()

    def _request_application_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._close_deadline = time.monotonic() + APPLICATION_CLOSE_TIMEOUT_SECONDS
        self.cancel_requested = True
        self.pending_jobs.clear()
        write_diagnostic(
            "application close requested; cancelling active work before destroying the window"
        )
        try:
            self.status_var.set("Closing safely; stopping active media work…")
            self.download_button.config(state="disabled")
            self.cancel_button.config(state="disabled")
            self.skip_video_button.config(state="disabled")
            self.skip_url_button.config(state="disabled")
        except (AttributeError, tk.TclError):
            pass
        self._close_terminator = threading.Thread(
            target=terminate_all_active_child_processes, daemon=True
        )
        self._close_terminator.start()
        self.after(50, self._finish_application_close_when_idle)

    def _finish_application_close_when_idle(self) -> None:
        worker_alive = self.worker is not None and self.worker.is_alive()
        terminator_alive = (
            self._close_terminator is not None and self._close_terminator.is_alive()
        )
        if worker_alive or terminator_alive:
            deadline = self.__dict__.get("_close_deadline")
            if deadline is None or time.monotonic() < deadline:
                self.after(100, self._finish_application_close_when_idle)
                return
            write_diagnostic(
                "application close deadline exceeded; destroying the window while daemon work remains active; "
                "cleanup could not be confirmed"
            )
            terminate_all_active_child_processes(
                deadline_monotonic=time.monotonic() + 0.5
            )
            self.destroy()
            return
        write_diagnostic(
            "active media work and child cleanup confirmed stopped; destroying application window"
        )
        self.destroy()

    def _skip_video(self) -> None:
        self.skip_video_requested = True
        self.status_var.set(
            "Skip item requested; continuing with the next playlist item after the current step stops…"
        )
        threading.Thread(
            target=terminate_all_active_child_processes, daemon=True
        ).start()

    def _skip_url(self) -> None:
        self.skip_url_requested = True
        self.skip_video_requested = True
        self.status_var.set(
            "Skip source URL requested; continuing with the next batch URL after the current step stops…"
        )
        threading.Thread(
            target=terminate_all_active_child_processes, daemon=True
        ).start()

    def _coordinate_download_batch(
        self,
        job: DownloadJob,
        urls: list[str],
    ) -> _DownloadBatchResult:
        """Run child sources without acquiring the batch terminal event."""
        outcome = DownloadOutcome()
        failures: list[tuple[str, str]] = []
        for index, url in enumerate(urls, start=1):
            if self.cancel_requested:
                return _DownloadBatchResult(
                    outcome=outcome,
                    failures=tuple(failures),
                    control_kind=_DownloadControlKind.CANCEL_RUN,
                )
            item_url, forced_single_video = prepare_batch_item_url(url)
            item_single_video_only = job.single_video_only or forced_single_video
            self.events.put(("status", f"Batch URL {index} of {len(urls)} — starting"))
            self._emit_job_log(job, f"Batch URL {index} of {len(urls)}: {item_url}")
            write_diagnostic(
                f"batch URL {index} of {len(urls)} start: {item_url} single_video_only={item_single_video_only}"
            )
            try:
                item_outcome = self._download_worker_single(
                    replace(
                        job,
                        url=item_url,
                        urls=[item_url],
                        single_video_only=item_single_video_only,
                    ),
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
                failures.append((item_url, issue))
                outcome = outcome.combined_with(DownloadOutcome(failure_count=1))
                append_batch_failure_report(BATCH_FAILURE_REPORT_PATH, item_url, issue)
                write_diagnostic(
                    f"batch URL {index} of {len(urls)} failed but batch will continue: "
                    f"{type(provider_error).__name__}: {provider_error}"
                )
                self._emit_job_log(
                    job,
                    f"WARNING: Batch URL {index} failed; continuing. Failure report: {BATCH_FAILURE_REPORT_PATH}",
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
            self._active_progress_context = None
            write_diagnostic(
                f"batch download worker error: {type(exc).__name__}: {exc}"
            )
            self.events.put(
                ("error", f"{exc}\n\nDiagnostics log: {DIAGNOSTICS_LOG_PATH}")
            )

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
            return None
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
        )
        if existing_output is None:
            return None

        existing_path, existing_probe = existing_output
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
            f"{label}: already downloaded and valid; reused {existing_path}.",
        )
        try:
            cached_thumbnail = save_cached_thumbnail_image(
                reused_info,
                source_url=job.url,
            )
            if cached_thumbnail is not None:
                self._emit_job_log(
                    job, f"{label}: refreshed private Library artwork cache"
                )
        except Exception as exc:  # noqa: BLE001 - optional Library artwork cannot invalidate media
            reuse_outcome = reuse_outcome.combined_with(
                DownloadOutcome(sidecar_failure_count=1)
            )
            self._emit_job_log(
                job,
                f"WARNING: {label}: existing media is valid, but Library artwork could not be refreshed: {exc}",
            )
        if job.write_info_json:
            try:
                write_compact_video_metadata(
                    existing_path.parent, reused_info, job.tags
                )
            except Exception as exc:  # noqa: BLE001 - optional metadata cannot invalidate media
                reuse_outcome = reuse_outcome.combined_with(
                    DownloadOutcome(sidecar_failure_count=1)
                )
                self._emit_job_log(
                    job,
                    f"WARNING: {label}: existing media is valid, but compact metadata could not be refreshed: {exc}",
                )
        if job.write_thumbnail:
            try:
                save_thumbnail_image(
                    existing_path.parent,
                    reused_info,
                    source_url=job.url,
                )
            except Exception as exc:  # noqa: BLE001 - optional thumbnail cannot invalidate media
                reuse_outcome = reuse_outcome.combined_with(
                    DownloadOutcome(sidecar_failure_count=1)
                )
                self._emit_job_log(
                    job,
                    f"WARNING: {label}: existing media is valid, but its separate thumbnail could not be refreshed: {exc}",
                )
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
                encoder_label = "NVIDIA NVENC GPU" if job.use_nvenc else "CPU libx264"
                self._emit_job_log(
                    job,
                    f"{label}: FFmpeg command started ({encode_index}/{total_mp4}) using {encoder_label}",
                )
                write_diagnostic(
                    f"{label} ffmpeg command: "
                    f"{build_vod_ffmpeg_command(ffmpeg, staged_mp4, transcode_temp_paths(staged_mp4)[0], video_bitrate_kbps=plan.video_bitrate_kbps, audio_bitrate_kbps=plan.audio_bitrate_kbps, audio_sample_rate=plan.audio_sample_rate, audio_channels=plan.audio_channels, audio_codec=plan.output_audio_codec, x264_preset=plan.x264_preset, use_nvenc=job.use_nvenc, preserve_attached_picture=job.embed_thumbnail, preserve_metadata=job.embed_metadata)}"
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
                    control_check=control_check,
                )
                write_diagnostic(
                    f"{label} transcode elapsed_seconds={time.monotonic() - transcode_started:.3f}"
                )
                self._emit_job_log(job, f"{label}: transcoded staged VODForge output")
        else:
            self.events.put(("status", f"{label} — MP3 encoded"))

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
        write_diagnostic(
            f"{label} atomic output commit elapsed_seconds={time.monotonic() - commit_started:.3f}"
        )
        output_dirs = sorted({path.parent for path in packaged_paths})
        all_output_dirs.extend(output_dirs)
        self.events.put(("download_folders", sorted(set(all_output_dirs))))
        for packaged_path in packaged_paths:
            self._emit_job_log(job, f"{label}: packaged media file {packaged_path}")
        output_paths = [
            path for path in packaged_paths if path.suffix.lower() == expected_extension
        ]
        primary_output = output_paths[0] if output_paths else None
        if primary_output is None:
            raise RuntimeError(
                f"{label}: validated output could not be committed to the destination."
            )
        ffprobe_data = validated_staged[0][2]
        if isinstance(plan, AudioExportPlan):
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
                save_custom_cached_thumbnail_image(info, custom_cover_for_cache)
                if job.output_type == OutputType.MP3
                and custom_cover_for_cache is not None
                else save_cached_thumbnail_image(info, source_url=job.url)
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
                )
                self._emit_job_log(
                    job,
                    f"{label}: saved compact video metadata {metadata_path}",
                )
            except Exception as exc:  # noqa: BLE001 - optional metadata cannot invalidate media
                outcome = outcome.combined_with(
                    DownloadOutcome(sidecar_failure_count=1)
                )
                write_diagnostic(
                    f"{label} compact metadata write failed: {type(exc).__name__}: {exc}"
                )
                self._emit_job_log(
                    job,
                    f"WARNING: {label}: media is valid, but compact metadata could not be saved: {exc}",
                )
        if job.write_thumbnail:
            try:
                thumb_path = save_thumbnail_image(
                    resolved_video_output_dir(job.output_dir, info),
                    info,
                    source_url=job.url,
                )
                if thumb_path:
                    self._emit_job_log(job, f"{label}: saved thumbnail {thumb_path}")
            except Exception as exc:  # noqa: BLE001 - optional thumbnail cannot invalidate media
                outcome = outcome.combined_with(
                    DownloadOutcome(sidecar_failure_count=1)
                )
                write_diagnostic(
                    f"{label} thumbnail write failed: {type(exc).__name__}: {exc}"
                )
                self._emit_job_log(
                    job,
                    f"WARNING: {label}: media is valid, but its separate thumbnail could not be saved: {exc}",
                )
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
            metadata_keys=(
                {key} if (key := metadata_run_key(terminal_info)) is not None else set()
            ),
            history_identities=set(),
            activity_lines=[message],
            terminal_status=status,
            terminal_message=message,
            item_terminal_emitted=True,
        )
        self.events.put(job_info_event("item_terminal", terminal_job, terminal_info))

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
                            f"{outcome.sidecar_failure_count} optional sidecar failure(s)."
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
        single_playlist_context = bool(
            job.single_video_only
            and youtube_url_video_id(job.url)
            and youtube_url_playlist_id(job.url)
        )
        if job.single_video_only and not single_playlist_context:
            # The source URL was already normalized and playlist expansion is
            # disabled. Avoid a full extractor pass whose only result would be
            # confirming the single item that preflight analyzes next.
            playlist_info: dict[str, Any] = {"webpage_url": job.url}
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
                "MP3 audio"
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
        download_step = partial(
            _download_preflight_result_step,
            ytdlp_module,
            options,
            analyzed_item.preflight_info,
            tuple(analyzed_item.session_cookies),
            control_check=control_check,
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
        expected_extension = ".mp3" if job.output_type == OutputType.MP3 else ".mp4"
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
            if control_request.kind is _DownloadControlKind.CANCEL_RUN:
                self._emit_failed_download_item_metadata(
                    job, result, str(control_request)
                )
                raise _DownloadControlRequestError(
                    control_request.kind,
                    result=result,
                ) from error

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
            )
            self._emit_job_log(
                job,
                f"{item.label}: skipped by user; continuing to next video.",
            )
            self.skip_video_requested = False
            return replace(result, outcome=skipped_outcome)

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
        )
        append_batch_failure_report(BATCH_FAILURE_REPORT_PATH, item.video_url, issue)
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
        try:
            staging_dir = create_staging_dir(job.output_dir)
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
            self._put_download_stage_progress(item, 0.90, 0.10, 1.0)
            result_label = (
                "MP3 audio" if job.output_type == OutputType.MP3 else "MP4 video"
            )
            self.events.put(("status", f"{item.label} complete — {result_label}"))
            self._emit_job_log(job, f"{item.label} complete — {result_label}")
        except Exception as exc:  # noqa: BLE001 - item failure policy classifies provider and control errors
            failure = exc
        finally:
            self._active_progress_context = None
            if staging_dir is not None:
                cleanup_private_staging_directory(staging_dir)
            if primary_intent_active:
                source.provider_network.end_primary()
        if failure is not None:
            result = replace(result, output_dirs=tuple(all_output_dirs))
            return self._resolve_download_item_failure(job, item, result, failure)
        return result

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
            all_output_dirs = list(result.output_dirs)
            existing_reuse = self._try_reuse_existing_output(
                job,
                analyzed_item.display_info,
                analyzed_item.plan,
                label=item.label,
                all_output_dirs=all_output_dirs,
                control_check=self._raise_for_download_control_requests,
            )
            if existing_reuse is not None:
                self._put_download_stage_progress(item, 0.10, 0.90, 1.0)
                self.events.put(
                    ("status", f"{item.label} complete — existing valid output")
                )
                return replace(
                    result,
                    outcome=result.outcome.combined_with(existing_reuse.outcome),
                    output_dirs=tuple(all_output_dirs),
                    metadata=existing_reuse.metadata,
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
        self._emit_failed_download_item_metadata(job, result, user_error)
        write_diagnostic(f"download worker error: {type(error).__name__}: {error}")
        if re_raise:
            raise _DownloadItemExecutionError(error, result) from error
        self.events.put(
            ("error", f"{user_error}\n\nDiagnostics log: {DIAGNOSTICS_LOG_PATH}")
        )
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

        outtmpl = staging_output_template(staging_dir)
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
            eta = data.get("eta")
            filename = Path(str(data.get("filename") or "")).name
            self.events.put(
                (
                    "status",
                    f"Downloading {filename} — {self._fmt_bytes(speed)}/s ETA {eta or '?'}s",
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

    def _pump_events(self) -> None:
        try:
            while True:
                self._dispatch_ui_event(self.events.get_nowait())
        except queue.Empty:
            pass
        self.after(100, self._pump_events)

    def _finish_run_ui(
        self,
        message: str,
        run_status: str,
        transfer_text: str,
        *,
        progress: float | None = None,
    ) -> None:
        finished_job = self.active_job
        decision = _resolve_run_finish_decision(
            finished_job,
            run_status,
            suppressed=self._library_run_is_suppressed(finished_job),
        )
        self._record_finished_run_before_handoff(decision, run_status, message)
        if progress is not None:
            self.progress_var.set(progress)
        self.status_var.set(message)
        self.download_button.config(state="normal")
        self.cancel_button.config(state="disabled")
        self.skip_video_button.config(state="disabled")
        self.skip_url_button.config(state="disabled")
        if self.__dict__.get("focus_transfer_var") is not None:
            if self._focus_follows_active_run():
                self.focus_transfer_var.set(transfer_text)
            self.focus_run_status_var.set(run_status)
            self._refresh_focus_run_deck()
        if (
            not self._launch_next_pending_job()
            and self.__dict__.get("focus_transfer_var") is not None
        ):
            self._set_focus_run_controls_visible(False)
            self._refresh_focus_run_deck()
        self._reconcile_finished_run_after_handoff(decision)

    def _record_finished_run_before_handoff(
        self,
        decision: _RunFinishDecision,
        run_status: str,
        message: str,
    ) -> None:
        finished_job = decision.finished_job
        if finished_job is not None and not decision.suppressed:
            self._append_job_log(finished_job, message)
            self._persist_job_activity_to_history(finished_job)
        else:
            self._append_log(message)
        if decision.stopped_without_item_terminal:
            self._archive_active_terminal_job(run_status, message)
        elif decision.archive_completed:
            self._archive_active_completed_job(run_status, message)

    def _reconcile_finished_run_after_handoff(
        self,
        decision: _RunFinishDecision,
    ) -> None:
        finished_job = decision.finished_job
        if decision.suppressed and finished_job is not None:
            self._terminal_jobs = [
                job for job in self._terminal_jobs if job.run_id != finished_job.run_id
            ]
            self._completed_jobs = [
                job for job in self._completed_jobs if job.run_id != finished_job.run_id
            ]
            self._reconcile_focus_after_library_removal({finished_job.run_id})
        elif decision.stopped_without_item_terminal and finished_job is not None:
            self._focus_terminal_job(finished_job)

    def _append_log(self, line: str) -> None:
        self._append_log_widget(self.log, line)
        if self.__dict__.get("_persist_activity", False):
            append_activity_log(line)

    def _emit_job_log(self, job: DownloadJob, line: str) -> None:
        self.events.put(job_log_event(job, line))

    def _append_job_log(self, event_job: DownloadJob, line: str) -> None:
        self._append_log(line)
        active_job = self._active_run_for_metadata_event(event_job)
        if active_job is None:
            return
        active_job.activity_lines.append(line.rstrip())
        if getattr(self, "_focus_selected_run_id", None) == active_job.run_id:
            self._append_log_widget(self.focus_log, line)
            self._focus_log_owner_run_id = active_job.run_id
            self._focus_log_rendered_text = "\n".join(active_job.activity_lines)

    @staticmethod
    def _append_log_widget(widget: Any, line: str) -> None:
        if widget is None:
            return
        follow_tail = not bool(getattr(widget, "_vodforge_user_scroll_locked", False))
        try:
            _first, last = widget.yview()
            follow_tail = follow_tail and float(last) >= 0.995
        except (AttributeError, TypeError, ValueError, tk.TclError):
            # Lightweight test doubles and not-yet-mapped widgets may not
            # expose a meaningful viewport. Preserve the historical default
            # for those cases rather than dropping live-tail behavior.
            pass
        widget.config(state="normal")
        widget.insert("end", line.rstrip() + "\n")
        if follow_tail:
            widget.see("end")
        widget.config(state="disabled")

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
    ffmpeg = DownloaderApp._find_ffmpeg()
    if ffmpeg:
        opts["ffmpeg_location"] = ytdlp_ffmpeg_location(ffmpeg)
    deno = DownloaderApp._find_deno()
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


def _normalized_numeric_version(value: object) -> tuple[int, ...] | None:
    try:
        return tuple(int(component) for component in str(value).split("."))
    except (TypeError, ValueError):
        return None


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


def runtime_smoke() -> int:
    """Verify packaged dependencies without opening the GUI or fetching media."""
    runtimes = {
        "ffmpeg": DownloaderApp._find_ffmpeg(),
        "ffprobe": DownloaderApp._find_ffprobe(),
        "deno": DownloaderApp._find_deno(),
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
    _runtime_smoke_output(f"diagnostics={DIAGNOSTICS_LOG_PATH}")
    if failures:
        _runtime_smoke_output(
            f"VODFORGE_RUNTIME_SMOKE_FAILED dependencies={','.join(failures)}"
        )
        return 1
    _runtime_smoke_output("VODFORGE_RUNTIME_SMOKE_OK")
    return 0


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--runtime-smoke":
        raise SystemExit(runtime_smoke())
    if len(sys.argv) >= 3 and sys.argv[1] == "--debug-preflight":
        raise SystemExit(debug_preflight(" ".join(sys.argv[2:])))
    app = DownloaderApp()
    try:
        write_quality_e2e_startup_attestation(
            app,
            app_version=__version__,
            application_data_path=application_data_dir(),
            diagnostics_path=DIAGNOSTICS_LOG_PATH,
        )
    except QualityE2EAttestationError as exc:
        app.destroy()
        raise SystemExit(f"VODForge quality-E2E startup rejected: {exc}") from exc
    app.mainloop()


if __name__ == "__main__":
    main()
