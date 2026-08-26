from __future__ import annotations

import hashlib
import importlib
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
import warnings
import webbrowser
from datetime import datetime
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

from .cloud_funnel import (
    InstallationIdentityError,
    InstallationState,
    cloud_page_url,
    installation_state_path,
    load_or_create_installation_state,
    mark_first_launch_confirmed,
    mark_cloud_seen_confirmed,
    record_cloud_click,
    record_first_launch,
    record_cloud_seen,
)
from .history import (
    HistoryError,
    application_data_dir,
    history_file_path,
    history_identity,
    history_output_dir,
    load_history,
    sanitize_run_activity,
    save_history,
    upsert_history,
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

try:
    from PIL import Image, ImageDraw, ImageOps, ImageTk
except Exception:  # pragma: no cover - thumbnail preview becomes unavailable
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
        except Exception as exc:  # pragma: no cover - handled at runtime
            YTDLP_IMPORT_ERROR = exc
            yt_dlp = None
        finally:
            _YTDLP_IMPORT_ATTEMPTED = True
    return yt_dlp


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
PINNED_YTDLP_VERSION = "2026.8.19"
PINNED_YTDLP_EJS_VERSION = "0.8.0"
YTDLP_EJS_SOLVER_RESOURCES = ("core.min.js", "lib.min.js")
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
THUMBNAIL_DOWNLOAD_MAX_BYTES = 10 * 1024 * 1024
THUMBNAIL_DOWNLOAD_CHUNK_BYTES = 64 * 1024
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
CLEAN_BITRATE_STEPS = [1000, 1200, 1500, 2000, 2500, 3000, 4000, 5000, 6000, 8000, 10000, 12000, 14000, 24000, 45000, 68000]
VIDEO_MINIMUMS_KBPS = {480: 1000, 720: 1500, 1080: 2000, 1440: 6000, 2160: 12000}
VIDEO_CAPS_KBPS = {(480, 30): 2500, (720, 30): 5000, (1080, 30): 10000, (1080, 60): 14000, (1440, 30): 24000, (2160, 30): 45000, (2160, 60): 68000}
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
RUNTIME_SMOKE_PROBE_TIMEOUT_SECONDS = 60
THUMBNAIL_CACHE_MAX_ITEMS = 1000
CUSTOM_COVER_MAX_INPUT_BYTES = 50 * 1024 * 1024
CUSTOM_COVER_MAX_PIXELS = 50_000_000
CUSTOM_COVER_MAX_OUTPUT_BYTES = 2 * 1024 * 1024


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


def bounded_window_size(screen_width: int, screen_height: int) -> tuple[int, int]:
    """Choose an initial size that stays clear of common taskbar and dock areas."""
    width_margin = 80 if screen_width > 800 else 24
    height_margin = 120 if screen_height > 640 else 48
    return (
        max(1, min(1180, screen_width - width_margin)),
        max(1, min(900, screen_height - height_margin)),
    )


def initial_window_geometry(
    screen_width: int,
    screen_height: int,
    *,
    platform_name: str | None = None,
) -> str:
    """Place the first window fully on-screen instead of accepting OS cascade state."""
    platform_name = sys.platform if platform_name is None else platform_name
    width, height = bounded_window_size(screen_width, screen_height)
    x = max(0, (int(screen_width) - width) // 2)
    if platform_name == "darwin":
        # Keep a stable menu-bar gap and leave the existing height allowance
        # below the window for the Dock, even when macOS remembers a low
        # cascade position from a prior process.
        y = 28 if int(screen_height) > 640 else 20
    else:
        y = max(0, (int(screen_height) - height) // 2)
    return f"{width}x{height}+{x}+{y}"


def download_layout_mode(width: int, height: int, *, manual_override: bool = False) -> str:
    """Choose the most expanded Download layout that fits without scrolling."""
    if width >= 1000:
        required_height = 570 if manual_override else 390
        density = "wide"
    else:
        required_height = 820 if manual_override else 650
        density = "stacked"
    disclosure = "expanded" if height >= required_height else "compact"
    return f"{density}-{disclosure}"


def metadata_layout_mode(width: int) -> str:
    """Keep all metadata surfaces visible while protecting useful reading widths."""
    return "three-column" if width >= 700 else "two-column"


def focus_layout_mode(width: int, height: int) -> str:
    """Choose the Focus Deck density without introducing a page scrollbar."""
    if width < 920 or height < 690:
        return "compact"
    if width < 1080 or height < 760:
        return "balanced"
    return "wide"


def focus_library_layout_mode(width: int) -> str:
    """Protect the selected item before the media table consumes medium widths."""
    if width < 920:
        return "compact"
    if width < 1000:
        return "balanced"
    return "wide"


def focus_run_deck_capacity(available_width: int, *, maximum: int = 4) -> int:
    """Show every run card that fits instead of collapsing by breakpoint."""
    safe_width = max(1, int(available_width))
    return max(1, min(max(1, int(maximum)), safe_width // 220))


def focus_hero_thumbnail_visible(width: int) -> bool:
    """Keep the selected-run artwork until the window is genuinely narrow."""
    return int(width) >= 720


def focus_wheel_pixels(delta: int | float) -> int:
    """Normalize high-resolution trackpad and coarse wheel deltas to pixels."""
    raw_delta = float(delta)
    if raw_delta == 0:
        return 0
    pixels = -raw_delta
    if abs(raw_delta) >= 120:
        pixels = -round(raw_delta / 120) * 36
    magnitude = max(1, round(abs(pixels)))
    return int(max(-72, min(72, magnitude if pixels > 0 else -magnitude)))


def accumulated_row_scroll(remainder: float, pixels: int, row_pixels: int) -> tuple[int, float]:
    """Accumulate high-resolution wheel motion before moving row widgets."""
    safe_row_pixels = max(1, int(row_pixels))
    total = float(remainder) + int(pixels)
    rows = int(total / safe_row_pixels)
    return rows, total - (rows * safe_row_pixels)


def touchpad_scroll_deltas(widget: tk.Misc, packed_delta: int | float) -> tuple[float, float]:
    """Decode Tk 9's packed macOS precision-scroll delta into x/y motion."""
    try:
        raw_x, raw_y = widget.tk.call("tk::PreciseScrollDeltas", packed_delta)
        return float(raw_x), float(raw_y)
    except (AttributeError, TypeError, ValueError, tk.TclError):
        return 0.0, 0.0


def bind_smooth_vertical_wheel(
    scroller: tk.Misc,
    *targets: tk.Misc,
    mode: str = "pixels",
    row_pixels: int = 30,
) -> None:
    """Preserve trackpad deltas instead of letting Tk amplify them into jumps."""
    if mode not in {"pixels", "increments", "rows"}:
        raise ValueError(f"Unsupported smooth-scroll mode: {mode}")
    wheel_targets = targets or (scroller,)
    remainder = 0.0

    def scrollable_pixel_height() -> int:
        try:
            if isinstance(scroller, tk.Text):
                measured = scroller.count("1.0", "end", "ypixels")
                if measured:
                    return max(scroller.winfo_height(), int(measured[0]))
            if isinstance(scroller, tk.Canvas):
                raw_region = str(scroller.cget("scrollregion") or "").split()
                if len(raw_region) == 4:
                    return max(scroller.winfo_height(), round(float(raw_region[3]) - float(raw_region[1])))
                bounds = scroller.bbox("all")
                if bounds is not None:
                    return max(scroller.winfo_height(), int(bounds[3] - bounds[1]))
        except (tk.TclError, TypeError, ValueError):
            pass
        return 0

    def scroll_pixels(pixels: int) -> str:
        nonlocal remainder
        if not pixels:
            return "break"
        # A live log may append while a precision gesture is still moving.
        # Record the reader's intent before moving the viewport so a writer
        # cannot mistake a near-tail position for permission to snap back.
        if pixels < 0:
            setattr(scroller, "_vodforge_user_scroll_locked", True)
        if mode == "rows":
            rows, remainder = accumulated_row_scroll(remainder, pixels, row_pixels)
            if rows:
                scroller.yview_scroll(rows, "units")
            if pixels > 0:
                try:
                    _first, last = scroller.yview()
                    if float(last) >= 0.995:
                        setattr(scroller, "_vodforge_user_scroll_locked", False)
                except (AttributeError, TypeError, ValueError, tk.TclError):
                    pass
            return "break"
        if mode == "pixels":
            content_height = scrollable_pixel_height()
            viewport_height = max(1, scroller.winfo_height())
            if content_height > viewport_height:
                first, _last = scroller.yview()
                scroller.yview_moveto(max(0.0, min(1.0, float(first) + (pixels / content_height))))
            if pixels > 0:
                try:
                    _first, last = scroller.yview()
                    if float(last) >= 0.995:
                        setattr(scroller, "_vodforge_user_scroll_locked", False)
                except (AttributeError, TypeError, ValueError, tk.TclError):
                    pass
            return "break"
        try:
            scroller.yview_scroll(pixels, "units")
        except tk.TclError:
            rows, remainder = accumulated_row_scroll(remainder, pixels, row_pixels)
            if rows:
                scroller.yview_scroll(rows, "units")
        if pixels > 0:
            try:
                _first, last = scroller.yview()
                if float(last) >= 0.995:
                    setattr(scroller, "_vodforge_user_scroll_locked", False)
            except (AttributeError, TypeError, ValueError, tk.TclError):
                pass
        return "break"

    def on_wheel(event: tk.Event[Any]) -> str:
        return scroll_pixels(focus_wheel_pixels(getattr(event, "delta", 0)))

    def on_touchpad_scroll(event: tk.Event[Any]) -> str:
        _delta_x, delta_y = touchpad_scroll_deltas(scroller, getattr(event, "delta", 0))
        return scroll_pixels(focus_wheel_pixels(delta_y))

    for target in wheel_targets:
        target.bind("<MouseWheel>", on_wheel, add="+")
        target.bind("<Button-4>", lambda _event: scroll_pixels(-36), add="+")
        target.bind("<Button-5>", lambda _event: scroll_pixels(36), add="+")
        try:
            target.bind("<TouchpadScroll>", on_touchpad_scroll, add="+")
        except tk.TclError:
            pass


def reveal_toplevel(popup: tk.Toplevel, geometry: str) -> None:
    """Place a hidden custom window before mapping it to avoid visible jumps."""
    popup.geometry(geometry)
    popup.deiconify()
    popup.lift()


def centered_toplevel_geometry(
    owner: tk.Misc,
    width: int,
    height: int,
    *,
    minimum_x: int = 20,
    minimum_y: int = 40,
) -> str:
    """Return owner-centered geometry without mapping a Toplevel early."""
    x = max(minimum_x, owner.winfo_rootx() + (owner.winfo_width() - width) // 2)
    y = max(minimum_y, owner.winfo_rooty() + (owner.winfo_height() - height) // 2)
    return f"{width}x{height}+{x}+{y}"


def bundled_asset_path(name: str, *, meipass: Path | None = None, repo_root: Path | None = None) -> Path:
    raw_meipass = getattr(sys, "_MEIPASS", None) if meipass is None else meipass
    base = Path(raw_meipass) if raw_meipass else (Path(__file__).resolve().parents[1] if repo_root is None else repo_root)
    return base / "assets" / name


def rounded_cover_image(source: Any, size: tuple[int, int], radius: int) -> Any:
    """Return a cover-cropped RGBA image with clean transparent corners."""
    if Image is None or ImageDraw is None or ImageOps is None:
        raise RuntimeError("Pillow is required for thumbnail rendering")
    resampling = getattr(Image, "Resampling", Image)
    cover = ImageOps.fit(source.convert("RGBA"), size, method=resampling.LANCZOS, centering=(0.5, 0.5))
    mask = rounded_alpha_mask(size, radius)
    cover.putalpha(mask)
    return cover


def youtube_thumbnail_size(width: int) -> tuple[int, int]:
    """Return the standard 16:9 thumbnail slot for a given display width."""
    safe_width = max(1, int(width))
    return safe_width, max(1, round(safe_width * 9 / 16))


def library_thumbnail_size(available_width: int) -> tuple[int, int]:
    """Keep Library artwork useful without crowding tags and description."""
    return youtube_thumbnail_size(min(max(1, int(available_width)), 240))


def thumbnail_size_within(
    source_size: tuple[int, int],
    maximum_size: tuple[int, int],
) -> tuple[int, int]:
    """Aspect-fit a thumbnail inside a maximum box without cropping or distortion."""
    source_width, source_height = source_size
    maximum_width, maximum_height = maximum_size
    if min(source_width, source_height, maximum_width, maximum_height) <= 0:
        return 1, 1
    scale = min(maximum_width / source_width, maximum_height / source_height)
    return max(1, round(source_width * scale)), max(1, round(source_height * scale))


def rounded_fit_image(source: Any, maximum_size: tuple[int, int], radius: int) -> Any:
    """Return a bounded, aspect-preserving thumbnail with no backing container."""
    if Image is None or ImageDraw is None or ImageOps is None:
        raise RuntimeError("Pillow is required for thumbnail rendering")
    resampling = getattr(Image, "Resampling", Image)
    fitted = ImageOps.contain(source.convert("RGBA"), maximum_size, method=resampling.LANCZOS)
    fitted.putalpha(rounded_alpha_mask(fitted.size, min(radius, min(fitted.size) // 2)))
    return fitted


def rounded_contain_image(source: Any, size: tuple[int, int], radius: int, background: str) -> Any:
    """Fit placeholder artwork inside a 16:9 slot without cropping its edges."""
    if Image is None or ImageDraw is None or ImageOps is None:
        raise RuntimeError("Pillow is required for thumbnail rendering")
    resampling = getattr(Image, "Resampling", Image)
    padding = max(3, round(min(size) * 0.07))
    bounds = (max(1, size[0] - 2 * padding), max(1, size[1] - 2 * padding))
    contained = ImageOps.contain(source.convert("RGBA"), bounds, method=resampling.LANCZOS)
    canvas = Image.new("RGBA", size, background)
    canvas.alpha_composite(contained, ((size[0] - contained.width) // 2, (size[1] - contained.height) // 2))
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
    alpha = alpha.point(lambda value: max(0, min(255, round((value - 128) * 1.24 + 128))))
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


def runtime_window_icon_asset(platform_name: str | None = None) -> str | None:
    """Return the runtime window icon, leaving macOS to the bundle ICNS."""
    platform_name = sys.platform if platform_name is None else platform_name
    if platform_name.startswith("win"):
        return "VODForge.ico"
    if platform_name == "darwin":
        return None
    return "VODForge.png"


def configure_windows_app_identity(platform_name: str | None = None) -> bool:
    """Give Windows a stable taskbar identity instead of a Python/Tk fallback."""
    platform_name = sys.platform if platform_name is None else platform_name
    if not platform_name.startswith("win"):
        return False
    import ctypes

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SnowfallHD.VODForge")  # type: ignore[attr-defined]
    return True


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
        # Keep the caller's path semantics intact. Resolving a simulated macOS
        # bundle path on a Windows test host incorrectly prefixes its drive.
        directories.append(executable.parent)
        if meipass is not None:
            directories.append(meipass)
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
    normalized = ffmpeg.replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1]
    if name.lower() not in {"ffmpeg", "ffmpeg.exe"}:
        return ffmpeg
    parent = normalized.rsplit("/", 1)[0] if "/" in normalized else "."
    if "\\" in ffmpeg and "/" not in ffmpeg:
        return parent.replace("/", "\\")
    return parent


def choose_windows_output_directory(
    initial_dir: str,
    *,
    runner: Any = subprocess.run,
) -> str | None:
    """Run the Windows shell folder picker out of process so shell failures cannot close VODForge."""
    command = (
        "$utf8=New-Object System.Text.UTF8Encoding($false);"
        "[Console]::OutputEncoding=$utf8;$OutputEncoding=$utf8;"
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$dialog=New-Object System.Windows.Forms.FolderBrowserDialog;"
        "$dialog.Description='Choose where VODForge should save downloads.';"
        "$dialog.ShowNewFolderButton=$true;"
        "$initial=$env:VODFORGE_INITIAL_OUTPUT_DIR;"
        "if($initial -and (Test-Path -LiteralPath $initial -PathType Container)){$dialog.SelectedPath=$initial};"
        "if($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){"
        "@{path=$dialog.SelectedPath} | ConvertTo-Json -Compress}"
    )
    environment = os.environ.copy()
    environment["VODFORGE_INITIAL_OUTPUT_DIR"] = initial_dir
    startupinfo = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
    result = runner(
        ["powershell.exe", "-NoProfile", "-STA", "-Command", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        startupinfo=startupinfo,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        detail = str(result.stderr or "").strip()
        raise RuntimeError(detail or "Windows could not open the folder browser.")
    output = str(result.stdout or "").strip()
    if not output:
        return None
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Windows returned an unreadable folder selection.") from exc
    selected = payload.get("path") if isinstance(payload, dict) else None
    return str(selected) if selected else None


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
        # Rosetta's first translation of the Intel Deno binary can take around
        # 30 seconds on Apple silicon; keep the release gate bounded above it.
        timeout=RUNTIME_SMOKE_PROBE_TIMEOUT_SECONDS,
        startupinfo=startupinfo,
        creationflags=creationflags,
    )
    return next((line.strip() for line in result.stdout.splitlines() if line.strip()), "version output unavailable")


DIAGNOSTICS_LOG_PATH = diagnostics_dir() / "latest.log"
ACTIVITY_LOG_PATH = diagnostics_dir() / "activity.log"
BATCH_FAILURE_REPORT_PATH = diagnostics_dir() / "batch-url-failures.txt"
ACTIVITY_LOG_MAX_BYTES = 5 * 1024 * 1024
ACTIVITY_LOG_COMPACT_BYTES = 4 * 1024 * 1024
ACTIVITY_LOG_RENDER_CHARS = 500_000
_DIAGNOSTICS_LOG_LOCK = threading.RLock()
_DIAGNOSTICS_LOG_HANDLE: Any | None = None
_DIAGNOSTICS_LOG_HANDLE_PATH: Path | None = None
_ACTIVITY_LOG_LOCK = threading.RLock()
_ACTIVITY_LOG_HANDLE: Any | None = None
_ACTIVITY_LOG_HANDLE_PATH: Path | None = None
_ACTIVE_CHILD_PROCESSES: set[Any] = set()
_ACTIVE_CHILD_PROCESS_LOCK = threading.RLock()
_CHILD_TERMINATION_LOCK = threading.RLock()
_THUMBNAIL_CACHE_LOCKS = tuple(threading.RLock() for _ in range(64))
_YTDLP_SUBPROCESS_TRACKING_LOCK = threading.RLock()


def write_diagnostic(message: str) -> None:
    global _DIAGNOSTICS_LOG_HANDLE, _DIAGNOSTICS_LOG_HANDLE_PATH
    try:
        with _DIAGNOSTICS_LOG_LOCK:
            if _DIAGNOSTICS_LOG_HANDLE is None or _DIAGNOSTICS_LOG_HANDLE_PATH != DIAGNOSTICS_LOG_PATH:
                if _DIAGNOSTICS_LOG_HANDLE is not None:
                    _DIAGNOSTICS_LOG_HANDLE.close()
                DIAGNOSTICS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
                _DIAGNOSTICS_LOG_HANDLE = DIAGNOSTICS_LOG_PATH.open(
                    "a",
                    encoding="utf-8",
                    buffering=1,
                )
                _DIAGNOSTICS_LOG_HANDLE_PATH = DIAGNOSTICS_LOG_PATH
            timestamp = datetime.now().isoformat(timespec="milliseconds")
            _DIAGNOSTICS_LOG_HANDLE.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


def reset_diagnostics_log() -> None:
    global _DIAGNOSTICS_LOG_HANDLE, _DIAGNOSTICS_LOG_HANDLE_PATH
    try:
        with _DIAGNOSTICS_LOG_LOCK:
            if _DIAGNOSTICS_LOG_HANDLE is not None:
                _DIAGNOSTICS_LOG_HANDLE.close()
            _DIAGNOSTICS_LOG_HANDLE = None
            _DIAGNOSTICS_LOG_HANDLE_PATH = None
            DIAGNOSTICS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            DIAGNOSTICS_LOG_PATH.write_text("", encoding="utf-8")
    except Exception:
        pass


def _close_activity_log_locked() -> None:
    global _ACTIVITY_LOG_HANDLE, _ACTIVITY_LOG_HANDLE_PATH
    if _ACTIVITY_LOG_HANDLE is not None:
        _ACTIVITY_LOG_HANDLE.close()
    _ACTIVITY_LOG_HANDLE = None
    _ACTIVITY_LOG_HANDLE_PATH = None


def _compact_activity_log_locked(path: Path, *, retain_bytes: int | None = None) -> None:
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
    temporary.write_bytes(retained)
    if os.name != "nt":
        temporary.chmod(0o600)
    temporary.replace(path)


def prepare_activity_log(path: Path | None = None) -> None:
    """Create and bound the persistent, local-only user-facing activity log."""
    target = ACTIVITY_LOG_PATH if path is None else path
    try:
        with _ACTIVITY_LOG_LOCK:
            if _ACTIVITY_LOG_HANDLE_PATH == target:
                _close_activity_log_locked()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch(exist_ok=True)
            if os.name != "nt":
                target.chmod(0o600)
            _compact_activity_log_locked(target)
    except Exception:
        pass


def append_activity_log(line: str, path: Path | None = None) -> None:
    global _ACTIVITY_LOG_HANDLE, _ACTIVITY_LOG_HANDLE_PATH
    target = ACTIVITY_LOG_PATH if path is None else path
    try:
        with _ACTIVITY_LOG_LOCK:
            if _ACTIVITY_LOG_HANDLE is None or _ACTIVITY_LOG_HANDLE_PATH != target:
                _close_activity_log_locked()
                target.parent.mkdir(parents=True, exist_ok=True)
                _ACTIVITY_LOG_HANDLE = target.open("a", encoding="utf-8", buffering=1)
                _ACTIVITY_LOG_HANDLE_PATH = target
            persistent_line = line.replace("\x00", "").rstrip()
            if persistent_line.startswith("Loaded YouTube cookies file:"):
                persistent_line = "Loaded YouTube cookies file."
            _ACTIVITY_LOG_HANDLE.write(persistent_line + "\n")
            if _ACTIVITY_LOG_HANDLE.tell() >= ACTIVITY_LOG_MAX_BYTES:
                _close_activity_log_locked()
                _compact_activity_log_locked(target)
    except Exception:
        pass


def load_activity_log_tail(path: Path | None = None, *, max_chars: int = ACTIVITY_LOG_RENDER_CHARS) -> str:
    target = ACTIVITY_LOG_PATH if path is None else path
    try:
        with _ACTIVITY_LOG_LOCK:
            if not target.exists():
                return ""
            text = target.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    if len(text) > max_chars:
        text = text[-max_chars:]
        newline = text.find("\n")
        if newline >= 0:
            text = text[newline + 1 :]
    return text.rstrip()


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
    started_at = time.monotonic()
    deadline = started_at + timeout_seconds
    next_wait_notice = started_at + wait_notice_seconds

    while not _BLOCKING_ANALYSIS_SLOTS.acquire(timeout=min(poll_seconds, max(0.001, deadline - time.monotonic()))):
        now = time.monotonic()
        if cancel_requested():
            raise RuntimeError(f"{label} cancelled by user")
        if on_wait is not None and now >= next_wait_notice:
            on_wait(now - started_at)
            next_wait_notice = now + wait_notice_seconds
        if now >= deadline:
            raise TimeoutError(f"{label} timed out waiting for an analysis slot after {timeout_seconds:g} seconds")

    def runner() -> None:
        try:
            results.put(("ok", step()))
        except Exception as exc:
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
                raise TimeoutError(f"{label} timed out after {timeout_seconds:g} seconds")
            time.sleep(poll_seconds)
            continue
        if kind == "error":
            raise payload
        return payload


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
            while self._primary_intents or self._primary_operations or self._preview_active:
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


THEME = {
    "bg": "#08090a",
    "panel": "#0d0f12",
    "surface": "#121419",
    "surface_2": "#1a1d24",
    "text": "#f7f8f8",
    "muted": "#9297a3",
    "subtle": "#636874",
    "accent": "#7170ff",
    "accent_dark": "#5e6ad2",
    "success": "#35d07f",
    "border": "#2b2e37",
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
    return "Uses the exact video bitrate, audio bitrate, and encoding speed you choose below."


EXPORT_MODES = [export_mode_display_name(mode) for mode in ExportMode]


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


def _is_single_file_http_transport(fmt: dict[str, Any]) -> bool:
    return str(fmt.get("protocol") or "").strip().lower() in {"http", "https"}


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
            is_direct = _is_single_file_http_transport(fmt)
            candidates.append((height, effective, kbps or 1.0, fmt.get("ext") == "mp4", str(fmt.get("vcodec") or "").startswith("avc"), is_direct, fmt))
        if not candidates:
            return None
        target_height = 1080 if any(item[0] == 1080 for item in candidates) and max_height >= 1080 else max(item[0] for item in candidates)
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


def choose_best_audio_format(formats: list[dict[str, Any]], *, prefer_quality: bool = False) -> dict[str, Any] | None:
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
            candidates.append((effective, channels >= 2, sample_rate >= 48000, fmt.get("ext") in {"m4a", "mp4", "webm"}, is_direct, fmt))
        if not candidates:
            return None
        if prefer_quality:
            return max(candidates, key=lambda item: (item[0], item[1], item[2], item[4], item[3]))[5]
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


def build_mp3_export_plan(info: dict[str, Any], settings: Mp3ExportSettings | None = None) -> AudioExportPlan:
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
        raise RuntimeError("VODForge could not identify the selected YouTube audio format.")
    source_audio_kbps = _format_audio_kbps(audio)
    effective_audio_kbps = source_audio_kbps * audio_codec_multiplier(audio.get("acodec"))
    source_sample_rate = str(audio.get("asr") or "").strip() or None
    source_channels_value = audio.get("audio_channels") or audio.get("channels")
    source_channels = str(source_channels_value).strip() if source_channels_value not in (None, "") else None
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
        embed_cover_art=bool(settings.custom_cover_art_path or settings.embed_cover_art),
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


def metadata_output_type(info: dict[str, Any]) -> OutputType:
    raw = str(info.get("vodforge_output_type") or "").strip().upper()
    if raw in {item.value for item in OutputType}:
        return OutputType(raw)
    summary = info.get("vodforge_encoding_summary") if isinstance(info.get("vodforge_encoding_summary"), dict) else {}
    output = summary.get("output") if isinstance(summary.get("output"), dict) else {}
    output_path = str(output.get("Output file path") or "").strip().lower()
    container = str(output.get("Output container") or "").strip().lower()
    if output_path.endswith(".mp3") or container == "mp3":
        return OutputType.MP3
    return OutputType.MP4


def metadata_indices_for_output_type(
    items: list[dict[str, Any]],
    output_type: OutputType | str,
) -> list[int]:
    """Return stable source-list indices for one Library media type."""
    selected = OutputType(output_type)
    return [index for index, item in enumerate(items) if metadata_output_type(item) == selected]


def mark_metadata_output_type(info: dict[str, Any], output_type: OutputType | str) -> dict[str, Any]:
    """Return metadata with a stable output classification on root and entries."""
    output_type = OutputType(output_type)
    marked = dict(info)
    marked["vodforge_output_type"] = output_type.value
    entries = marked.get("entries")
    if isinstance(entries, list):
        marked["entries"] = [
            {**entry, "vodforge_output_type": output_type.value} if isinstance(entry, dict) else entry
            for entry in entries
        ]
    return marked


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
            "Source format selector used": _display_value(plan.format_selector, "Not available"),
            "Audio format ID": _display_value(plan.audio_format_id, "Not available"),
            "Source container/ext": _display_value(audio_fmt.get("ext"), "Unknown"),
            "Source audio codec": _display_value(audio_fmt.get("acodec") or plan.audio_codec),
            "Source audio bitrate": _format_kbps(plan.source_audio_kbps),
            "Source audio sample rate": _display_value(plan.source_sample_rate, "Not available"),
            "Source audio channels": _display_value(plan.source_channels, "Not available"),
            "File size estimate": _format_bytes(audio_fmt.get("filesize") or audio_fmt.get("filesize_approx")),
            "Effective MP3-equivalent audio bitrate": _format_kbps(plan.effective_audio_kbps),
            "Reason selected": "highest-quality available audio-only source",
        }
        output = _planned_output_summary(plan, output_path)
        if ffprobe_data:
            output.update(_ffprobe_output_summary(ffprobe_data, output_path))
            output["Validation status"] = validation_status or "Validated"
        elif validation_status:
            output["Validation status"] = validation_status
        enriched["vodforge_output_type"] = OutputType.MP3.value
        enriched["vodforge_encoding_summary"] = {"source": source, "output": output, "warnings": list(plan.warnings)}
        return enriched

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
    enriched["vodforge_output_type"] = OutputType.MP4.value
    enriched["vodforge_encoding_summary"] = {"source": source, "output": output, "warnings": list(plan.warnings)}
    return enriched


def build_failed_encoding_summary_metadata(info: dict[str, Any], plan: ExportPlan | AudioExportPlan | None, failure_reason: str) -> dict[str, Any]:
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
        enriched["vodforge_encoding_summary"]["output"].update({
            "Output status": "No output produced",
            "Output file path": "Not produced",
            "Validation status": status,
            "Reason": message,
        })
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


def _planned_output_summary(plan: ExportPlan | AudioExportPlan, output_path: Path | None = None) -> dict[str, str]:
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

AUDIO_SUMMARY_COMPARISON_ROWS = [
    ("Format selector", "Source format selector used", None),
    ("Audio format ID", "Audio format ID", None),
    ("Container/ext", "Source container/ext", "Output container"),
    ("Audio codec", "Source audio codec", "Output audio codec"),
    ("Audio bitrate", "Source audio bitrate", "Measured audio bitrate"),
    ("Audio sample rate", "Source audio sample rate", "Audio sample rate"),
    ("Audio channels", "Source audio channels", "Audio channels"),
    ("File size", "File size estimate", "Output file size"),
    ("Effective/target audio bitrate", "Effective MP3-equivalent audio bitrate", "Target audio bitrate"),
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
    summary = info.get("vodforge_encoding_summary") if isinstance(info.get("vodforge_encoding_summary"), dict) else {}
    source = summary.get("source") if isinstance(summary.get("source"), dict) else {}
    output = summary.get("output") if isinstance(summary.get("output"), dict) else {}
    warnings = summary.get("warnings") if isinstance(summary.get("warnings"), list) else []
    source_lines: list[str] = []
    output_lines: list[str] = []
    rows = AUDIO_SUMMARY_COMPARISON_ROWS if metadata_output_type(info) == OutputType.MP3 else SUMMARY_COMPARISON_ROWS
    for label, source_key, output_key in rows:
        source_lines.append(f"{label}: {_display_value(source.get(source_key), 'Not available')}")
        if output_key is not None:
            output_lines.append(f"{label}: {_display_value(output.get(output_key), 'Not available')}")
    output_lines.extend([
        f"Output status: {_display_value(output.get('Output status'), 'Not available')}",
        f"Output file path: {_display_value(output.get('Output file path'), 'Not produced')}",
        f"Output rate-control mode: {_display_value(output.get('Output rate-control mode'), 'Not available')}",
        f"Validation status: {_display_value(output.get('Validation status'), 'Not available')}",
        f"Output duration: {_display_value(output.get('Output duration'), 'Not available')}",
    ])
    if metadata_output_type(info) == OutputType.MP3:
        output_lines.extend([
            f"Embedded ID3 metadata: {_display_value(output.get('Embedded ID3 metadata'), 'Not available')}",
            f"Embedded cover art: {_display_value(output.get('Embedded cover art'), 'Not available')}",
        ])
    else:
        output_lines.append(f"H.264 profile: {_display_value(output.get('H.264 profile'), 'Not available')}")
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


SINGLE_VIDEO_PLAYLIST_ERROR = "This link is a playlist. Turn off ‘Ignore playlists’ to download every item."
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
    playlist_id = str(info.get("playlist_id") or youtube_url_playlist_id(fallback_url) or "").strip()
    if video_id and playlist_id:
        return "https://www.youtube.com/watch?" + urllib.parse.urlencode({"v": video_id, "list": playlist_id})
    return fallback_url.strip()


def playlist_context_from_extraction(info: dict[str, Any], source_url: str) -> dict[str, Any]:
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
        info.get("playlist_title") or info.get("playlist_id") or info.get("title") or info.get("id"),
        "Playlist",
        max_len=80,
    )


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


def existing_output_candidate_dirs(output_dir: Path, info: dict[str, Any], target_file_name: str) -> list[Path]:
    """Return bounded canonical and legacy directories for one provider item."""
    candidates: list[Path] = []

    def add(path: Path) -> None:
        if path not in candidates:
            candidates.append(path)

    canonical = resolved_video_output_dir(output_dir, info, target_file_name)
    add(canonical)
    legacy_info = dict(info)
    legacy_info.pop("playlist_title", None)
    legacy_info.pop("playlist_id", None)
    legacy_info.pop("playlist_index", None)
    legacy_info.pop("_vodforge_output_dir", None)
    legacy = resolved_video_output_dir(output_dir, legacy_info, target_file_name)
    add(legacy)

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
        if not metadata_path.is_file() or metadata_path.stat().st_size > 2 * 1024 * 1024:
            return None
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    encoding = payload.get("vodforge_encoding_summary") if isinstance(payload, dict) else None
    output = encoding.get("output") if isinstance(encoding, dict) else None
    return output if isinstance(output, dict) else None


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
    control_check: Any | None = None,
) -> tuple[Path, dict[str, Any]] | None:
    """Reuse only a provider-ID-scoped artifact that passes full media validation."""
    extension = ".mp3" if output_type == OutputType.MP3 else ".mp4"
    target_file_name = video_file_name(info, extension)
    for candidate_dir in existing_output_candidate_dirs(output_dir, info, target_file_name):
        exact = candidate_dir / target_file_name
        paths = [exact]
        try:
            paths.extend(
                path
                for path in sorted(candidate_dir.glob(f"*{extension}"))
                if path != exact and not is_vodforge_transient_media_path(path, target_file_name)
            )
        except OSError:
            pass
        for path in paths:
            if control_check is not None:
                control_check()
            if not path.is_file():
                continue
            try:
                probe_data = validate_output_artifact(
                    path,
                    output_type,
                    ffprobe,
                    expected_duration_seconds=expected_duration_seconds,
                    require_audio=True,
                    control_check=control_check,
                )
            except Exception as exc:
                write_diagnostic(f"existing output rejected: path={path} reason={type(exc).__name__}: {exc}")
                continue
            if plan is not None and not output_artifact_matches_plan(
                probe_data,
                plan,
                embed_metadata=embed_metadata,
                embed_cover_art=embed_cover_art,
                custom_cover_art=custom_cover_art,
                expected_tags=expected_tags,
                sidecar_summary=load_vodforge_output_summary(path.parent),
            ):
                write_diagnostic(f"existing output rejected: path={path} reason=export settings do not match")
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
    streams = [stream for stream in probe_data.get("streams") or [] if isinstance(stream, dict)]
    video = next((stream for stream in streams if stream.get("codec_type") == "video" and not int((stream.get("disposition") or {}).get("attached_pic") or 0)), {})
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
    attached_art = any(
        stream.get("codec_type") == "video"
        and int((stream.get("disposition") or {}).get("attached_pic") or 0)
        for stream in streams
    )
    if embed_cover_art is not None and attached_art != embed_cover_art:
        return False

    fmt = probe_data.get("format") if isinstance(probe_data.get("format"), dict) else {}
    tags = fmt.get("tags") if isinstance(fmt.get("tags"), dict) else {}
    normalized_tag_keys = {str(key).lower() for key in tags}
    user_metadata_keys = {"title", "artist", "album", "album_artist", "comment", "description", "synopsis", "keywords"}
    has_user_metadata = bool(normalized_tag_keys & user_metadata_keys)
    if embed_metadata is True and not has_user_metadata:
        return False
    if embed_metadata is False and has_user_metadata:
        return False
    requested_tags = [tag.strip().casefold() for tag in (expected_tags or []) if tag.strip()]
    if requested_tags:
        stored_keywords = str(tags.get("keywords") or tags.get("KEYWORDS") or "").casefold()
        if not all(tag in stored_keywords for tag in requested_tags):
            return False

    # Average bitrate cannot prove constant-rate output or distinguish the
    # supported MP4 rate-control modes. Reuse therefore also requires the
    # compact output contract written after a validated VODForge commit.
    if not isinstance(sidecar_summary, dict):
        return False

    def close_numeric(actual: Any, expected: Any, *, relative: float = 0.10) -> bool:
        try:
            actual_number = float(actual)
            expected_number = float(expected)
        except (TypeError, ValueError):
            return False
        return abs(actual_number - expected_number) <= max(1.0, abs(expected_number) * relative)

    def stream_kbps(stream: dict[str, Any]) -> float | None:
        value = stream.get("bit_rate") or fmt.get("bit_rate")
        try:
            return float(value) / 1000.0
        except (TypeError, ValueError):
            return None

    if isinstance(plan, AudioExportPlan):
        if str(sidecar_summary.get("Output rate-control mode") or "") != "CBR":
            return False
        if str(sidecar_summary.get("Target audio bitrate") or "") != f"{plan.audio_bitrate_kbps} kbps":
            return False
        measured_kbps = stream_kbps(audio)
        if measured_kbps is None or not close_numeric(measured_kbps, plan.audio_bitrate_kbps, relative=0.12):
            return False
        if plan.output_sample_rate and not close_numeric(audio.get("sample_rate"), plan.output_sample_rate, relative=0.0):
            return False
        if plan.output_channels and not close_numeric(audio.get("channels"), plan.output_channels, relative=0.0):
            return False
        return True

    if str(sidecar_summary.get("Output rate-control mode") or "") != plan.mode.value:
        return False
    if str(sidecar_summary.get("Target video bitrate") or "") != f"{plan.video_bitrate_kbps} kbps":
        return False
    if str(sidecar_summary.get("Target audio bitrate") or "") != f"{plan.audio_bitrate_kbps} kbps":
        return False
    if str(video.get("pix_fmt") or "").lower() != "yuv420p":
        return False
    if str(video.get("profile") or "").casefold() != "high":
        return False
    if plan.output_width and int(video.get("width") or 0) != int(plan.output_width):
        return False
    if plan.output_height and int(video.get("height") or 0) != int(plan.output_height):
        return False
    measured_video_kbps = stream_kbps(video)
    if measured_video_kbps is None or not close_numeric(measured_video_kbps, plan.video_bitrate_kbps, relative=0.18):
        return False
    measured_audio_kbps = stream_kbps(audio)
    if measured_audio_kbps is None or not close_numeric(measured_audio_kbps, plan.audio_bitrate_kbps, relative=0.18):
        return False
    if plan.audio_sample_rate and not close_numeric(audio.get("sample_rate"), plan.audio_sample_rate, relative=0.0):
        return False
    if plan.audio_channels and not close_numeric(audio.get("channels"), plan.audio_channels, relative=0.0):
        return False
    return True


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
        "vodforge_output_type": metadata_output_type(info).value,
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


STAGED_MEDIA_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".mp3", ".m4a", ".aac", ".opus", ".ogg"}


def _find_staged_media_file(staging_dir: Path, video_id: str, *, expected_extension: str | None = None) -> Path | None:
    allowed = {expected_extension.lower()} if expected_extension else STAGED_MEDIA_EXTENSIONS
    candidates = [
        path
        for path in staging_dir.rglob(f"*{video_id}*")
        if path.is_file() and path.suffix.lower() in allowed and path.stat().st_size > 0
    ]
    if not candidates:
        candidates = [
            path
            for path in staging_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in allowed and path.stat().st_size > 0
        ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.stat().st_size))


def video_file_name(info: dict[str, Any], ext: str) -> str:
    title = _windows_safe_component(info.get("title"), "video", max_len=120)
    return f"{title}{ext}"


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
        ) or _find_staged_media_file(staging_dir, video_id, expected_extension=expected_extension)
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
        extensions = [expected_extension] if expected_extension else list(STAGED_MEDIA_EXTENSIONS)
        staged_media = []
        for extension in extensions:
            staged_media.extend(collect_staged_media_files(staging_dir, info, expected_extension=extension))
            if staged_media:
                break
    for video, staged in staged_media:
        ext = expected_extension.lower() if expected_extension else staged.suffix.lower()
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
        if control_check is not None:
            control_check()
        # Staging lives below output_dir, so this is a same-volume atomic commit.
        # os.replace preserves an existing valid target if the commit itself fails.
        os.replace(staged, target)
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
        ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "warning", "-i", str(source),
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


def run_ffprobe_json(
    ffprobe: str,
    path: Path,
    *,
    timeout_seconds: float = FFPROBE_TIMEOUT_SECONDS,
    control_check: Any | None = None,
) -> dict[str, Any]:
    startupinfo = None
    creationflags = 0
    if sys.platform.startswith("win"):
        startupinfo = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    command = [
        ffprobe,
        "-v", "error",
        "-print_format", "json",
        "-show_entries",
        "format=format_name,size,duration:format_tags:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,bit_rate,pix_fmt,profile,sample_rate,channels:stream_disposition",
        str(path),
    ]
    if control_check is None:
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
    else:
        result = run_cancellable_process_capture(
            command,
            timeout_seconds=timeout_seconds,
            control_check=control_check,
            check=True,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
    data = json.loads(result.stdout or "{}")
    if not isinstance(data, dict):
        raise RuntimeError("ffprobe returned an invalid top-level result")
    return data


def _ffprobe_for_ffmpeg(ffmpeg: str) -> str | None:
    ffmpeg_path = Path(ffmpeg)
    sibling_names = ["ffprobe.exe", "ffprobe"] if sys.platform.startswith("win") else ["ffprobe", "ffprobe.exe"]
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
    ffprobe_data: dict[str, Any] | None = None,
    control_check: Any | None = None,
) -> dict[str, Any]:
    """Fail closed unless a final artifact has the required streams and duration."""
    try:
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError("the output file is missing or empty")
    except OSError as exc:
        raise RuntimeError(f"the output file could not be read: {exc}") from exc

    try:
        data = (
            ffprobe_data
            if ffprobe_data is not None
            else run_ffprobe_json(ffprobe, path, control_check=control_check)
        )
    except Exception as exc:
        raise RuntimeError(f"ffprobe could not validate the output: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("ffprobe returned malformed output metadata")

    streams = [stream for stream in data.get("streams") or [] if isinstance(stream, dict)]
    fmt = data.get("format") if isinstance(data.get("format"), dict) else {}
    container_tokens = {token.strip().lower() for token in str(fmt.get("format_name") or "").split(",") if token.strip()}
    try:
        duration = float(fmt.get("duration") or 0)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("the output duration is missing or invalid") from exc
    if duration <= 0:
        raise RuntimeError("the output duration is missing or zero")
    if expected_duration_seconds and expected_duration_seconds > 0:
        tolerance = max(2.0, expected_duration_seconds * 0.02)
        if duration + tolerance < expected_duration_seconds:
            raise RuntimeError(
                f"the output is truncated ({duration:.2f}s versus {expected_duration_seconds:.2f}s expected)"
            )

    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if output_type == OutputType.MP3:
        if "mp3" not in container_tokens:
            raise RuntimeError(f"the output container is not MP3 ({','.join(sorted(container_tokens)) or 'unknown'})")
        if not any(str(stream.get("codec_name") or "").lower() == "mp3" for stream in audio_streams):
            raise RuntimeError("the MP3 output does not contain a valid MP3 audio stream")
        return data

    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    if not ({"mp4", "mov"} & container_tokens):
        raise RuntimeError(f"the output container is not MP4 ({','.join(sorted(container_tokens)) or 'unknown'})")
    if not any(str(stream.get("codec_name") or "").lower() == "h264" for stream in video_streams):
        raise RuntimeError("the MP4 output does not contain the required H.264 video stream")
    if require_audio and not any(str(stream.get("codec_name") or "").lower() == "aac" for stream in audio_streams):
        raise RuntimeError("the MP4 output does not contain the required AAC audio stream")
    return data


def terminate_and_reap_process(process: Any, *, timeout_seconds: float = PROCESS_TERMINATE_TIMEOUT_SECONDS) -> None:
    """Stop a child process without leaving an encoder writing after cleanup."""
    with _CHILD_TERMINATION_LOCK:
        poll = getattr(process, "poll", None)
        if callable(poll) and poll() is not None:
            return
        try:
            process.terminate()
        except Exception:
            pass
        try:
            process.wait(timeout=timeout_seconds)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            process.kill()
        except Exception:
            pass
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Child process did not stop after terminate and kill requests") from exc


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


def finalize_active_child_process(process: Any, *, confirmed_exited: bool = False) -> bool:
    """Release process ownership only after exit is positively confirmed.

    If an exceptional path leaves a child alive, retain it in the registry so
    application-close cleanup can retry instead of losing ownership of a writer.
    """
    if child_process_has_exited(process, confirmed_exited=confirmed_exited):
        unregister_active_child_process(process)
        return True
    try:
        terminate_and_reap_process(process)
    except Exception as exc:
        write_diagnostic(f"active child process remains live after cleanup attempt: {type(exc).__name__}: {exc}")
    if child_process_has_exited(process):
        unregister_active_child_process(process)
        return True
    write_diagnostic("active child process remains registered because exit could not be confirmed")
    return False


def terminate_all_active_child_processes(*, deadline_monotonic: float | None = None) -> None:
    with _ACTIVE_CHILD_PROCESS_LOCK:
        active = tuple(_ACTIVE_CHILD_PROCESSES)
    for process in active:
        timeout_seconds = PROCESS_TERMINATE_TIMEOUT_SECONDS
        if deadline_monotonic is not None:
            remaining = deadline_monotonic - time.monotonic()
            if remaining <= 0:
                write_diagnostic("active child process cleanup deadline reached before every child was reaped")
                break
            timeout_seconds = max(0.01, min(timeout_seconds, remaining / 2))
        try:
            terminate_and_reap_process(process, timeout_seconds=timeout_seconds)
        except Exception as exc:
            write_diagnostic(f"active child process cleanup failed: {type(exc).__name__}: {exc}")
        finally:
            poll = getattr(process, "poll", None)
            if callable(poll) and poll() is not None:
                unregister_active_child_process(process)


def tracked_ytdlp_popen_class(base_class: type, control_check: Any | None = None) -> type:
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

        def __exit__(self, *args: Any, **kwargs: Any) -> Any:
            try:
                return super().__exit__(*args, **kwargs)
            finally:
                finalize_active_child_process(self)

    VODForgeTrackedPopen.__name__ = "VODForgeTrackedYtDlpPopen"
    return VODForgeTrackedPopen


def run_tracked_ytdlp_operation(step: Callable[[], Any], *, control_check: Any | None = None) -> Any:
    """Run one serialized yt-dlp operation with all of its imported Popen aliases tracked."""
    with _YTDLP_SUBPROCESS_TRACKING_LOCK:
        utils_module = importlib.import_module("yt_dlp.utils")
        original_class = getattr(utils_module, "Popen")
        tracked_class = tracked_ytdlp_popen_class(original_class, control_check)
        for module_name, module in tuple(sys.modules.items()):
            if module is None or not (module_name == "yt_dlp" or module_name.startswith("yt_dlp.")):
                continue
            if getattr(module, "Popen", None) is original_class:
                setattr(module, "Popen", tracked_class)
        try:
            if control_check is not None:
                control_check()
            return step()
        finally:
            # Include modules imported during the operation; they may have
            # copied the temporarily patched class from yt_dlp.utils.
            for module_name, module in tuple(sys.modules.items()):
                if module is None or not (module_name == "yt_dlp" or module_name.startswith("yt_dlp.")):
                    continue
                if getattr(module, "Popen", None) is tracked_class:
                    setattr(module, "Popen", original_class)


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
    process = subprocess.Popen(
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
        result = subprocess.CompletedProcess(command, process.returncode, stdout or "", stderr or "")
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

    process: Any | None = None
    process_confirmed_exited = False
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
        register_active_child_process(process)
        output_lines: list[str] = []
        assert process.stdout is not None
        output_queue: queue.Queue[str | None] = queue.Queue()

        def read_encoder_output() -> None:
            try:
                for output_line in process.stdout:
                    output_queue.put(output_line)
            finally:
                output_queue.put(None)

        output_reader = threading.Thread(target=read_encoder_output, daemon=True)
        output_reader.start()
        while True:
            if control_check is not None:
                try:
                    control_check()
                except Exception:
                    terminate_and_reap_process(process)
                    output_reader.join(timeout=PROCESS_TERMINATE_TIMEOUT_SECONDS)
                    raise
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
            if progress_callback and duration_seconds:
                key, sep, value = text_line.partition("=")
                if sep and key == "out_time_ms":
                    try:
                        fraction = min(1.0, max(0.0, (float(value) / 1_000_000) / float(duration_seconds)))
                        progress_callback(fraction)
                    except (TypeError, ValueError, ZeroDivisionError):
                        pass
        if control_check is not None:
            control_check()
        return_code = process.wait()
        process_confirmed_exited = True
        output_reader.join(timeout=1)
        if return_code != 0:
            tail = "\n".join(output_lines[-40:])
            raise RuntimeError(f"VODForge H.264/AAC CBR transcode failed for {path.name}; ffmpeg exited with code {return_code}: {tail[-4000:]}")
        if not temp_output.is_file() or temp_output.stat().st_size <= 0:
            raise RuntimeError(f"VODForge H.264/AAC CBR transcode failed for {path.name}; FFmpeg produced no usable output")
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
            write_diagnostic(f"transcode temp cleanup failed for {temp_output}: {cleanup_exc}")
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(f"VODForge H.264/AAC CBR transcode failed for {path.name}: {exc}") from exc
    finally:
        if process is not None:
            finalize_active_child_process(process, confirmed_exited=process_confirmed_exited)


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


def download_bounded_url_bytes(
    url: str,
    *,
    timeout_seconds: float = 30,
    max_bytes: int = THUMBNAIL_DOWNLOAD_MAX_BYTES,
) -> bytes:
    """Read an HTTP(S) asset with a hard memory bound, including chunked responses."""
    parsed = urllib.parse.urlparse(str(url))
    if parsed.scheme.lower() not in {"http", "https"}:
        raise RuntimeError("Thumbnail URLs must use HTTP or HTTPS")
    with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
        headers = getattr(response, "headers", None)
        content_length = headers.get("Content-Length") if headers is not None else None
        if content_length:
            try:
                if int(content_length) > max_bytes:
                    raise RuntimeError(f"Thumbnail response exceeds the {max_bytes}-byte safety limit")
            except ValueError:
                pass
        payload = bytearray()
        while True:
            chunk = response.read(min(THUMBNAIL_DOWNLOAD_CHUNK_BYTES, max_bytes + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > max_bytes:
                raise RuntimeError(f"Thumbnail response exceeds the {max_bytes}-byte safety limit")
        return bytes(payload)


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
                    raise RuntimeError("Thumbnail dimensions exceed the safe preview limit")
                source.verify()
            with Image.open(BytesIO(data)) as source:
                source.load()
                return source.copy()
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Thumbnail image is invalid or unsafe: {exc}") from exc


def save_thumbnail_image(output_dir: Path, info: dict[str, Any], *, filename: str = "thumbnail.jpeg") -> Path | None:
    thumb = best_thumbnail_for_download(info)
    url = str((thumb or {}).get("url") or "")
    if not url:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    data = download_bounded_url_bytes(url)
    if Image is None:
        if len(data) > THUMBNAIL_MAX_BYTES:
            raise RuntimeError("Pillow is required to enforce the 300 KB thumbnail limit")
        path.write_bytes(data)
        return path
    image = decode_bounded_thumbnail(data).convert("RGB")
    _save_jpeg_under_size(image, path)
    return path


def cached_thumbnail_path(info: dict[str, Any], *, data_dir: Path | None = None) -> Path | None:
    """Return a private deterministic UI-thumbnail path without trusting source filenames."""
    thumb = best_thumbnail_for_download(info)
    url = str((thumb or {}).get("url") or "").strip()
    identity = str(info.get("id") or "").strip() or url or str(info.get("title") or "").strip()
    if not identity:
        return None
    digest = hashlib.sha256(f"{identity}\0{url}".encode("utf-8", errors="replace")).hexdigest()[:32]
    root = data_dir if data_dir is not None else application_data_dir()
    return root / "thumbnail-cache" / f"{digest}.jpeg"


def prune_thumbnail_cache(cache_dir: Path, *, max_items: int = THUMBNAIL_CACHE_MAX_ITEMS) -> None:
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
    slot = int(hashlib.sha256(str(path).encode("utf-8", errors="replace")).hexdigest()[:8], 16)
    return _THUMBNAIL_CACHE_LOCKS[slot % len(_THUMBNAIL_CACHE_LOCKS)]


def save_cached_thumbnail_image(info: dict[str, Any], *, data_dir: Path | None = None) -> Path | None:
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
        except Exception:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.stem}.{uuid.uuid4().hex}.tmp")
        try:
            saved = save_thumbnail_image(temporary.parent, info, filename=temporary.name)
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
                normalized.thumbnail((1600, 1600), getattr(Image, "Resampling", Image).LANCZOS)
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
            normalized.thumbnail((1600, 1600), getattr(Image, "Resampling", Image).LANCZOS)
            _save_jpeg_under_size(normalized, destination, max_bytes=CUSTOM_COVER_MAX_OUTPUT_BYTES)
    except Exception as exc:
        raise RuntimeError(f"VODForge could not prepare the custom cover image: {exc}") from exc
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
    temporary = mp3_path.with_name(f".{mp3_path.stem}.vodforge-cover-{uuid.uuid4().hex}.mp3")
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
    startupinfo = None
    creationflags = 0
    if sys.platform.startswith("win"):
        startupinfo = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = run_cancellable_process_capture(
            command,
            timeout_seconds=FFMPEG_COVER_TIMEOUT_SECONDS,
            control_check=control_check,
            check=False,
            stderr_to_stdout=True,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        if result.returncode != 0 or not temporary.is_file() or temporary.stat().st_size <= 0:
            detail = next((line.strip() for line in reversed(result.stdout.splitlines()) if line.strip()), "FFmpeg did not produce an output file")
            raise RuntimeError(f"Custom cover art could not be embedded: {detail}")
        os.replace(temporary, mp3_path)
        return mp3_path
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Custom cover art embedding timed out before FFmpeg completed") from exc
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


COOKIE_BROWSER_PLACEHOLDER = "Choose a browser"
COOKIE_BROWSER_OPTIONS = [COOKIE_BROWSER_PLACEHOLDER, "Chrome", "Edge", "Firefox", "Brave", "Chromium", "Opera", "Vivaldi"]
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
WINDOWS_CHROMIUM_COOKIE_BROWSERS = {"brave", "chrome", "chromium", "edge", "opera", "vivaldi"}
WINDOWS_CHROMIUM_COOKIE_MESSAGE = (
    "Chrome/Edge/Brave/Chromium browser-cookie import is unreliable on Windows because Chromium locks its cookie database. "
    "Choose cookies.txt with an exported YouTube cookies.txt file, choose Firefox browser cookies under Browser, or switch YouTube access to Public."
)


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
    metadata_keys: set[tuple[str, str]] = field(default_factory=set)
    history_identities: set[tuple[str, str, str]] = field(default_factory=set)
    preview_thumbnail_image: Any | None = field(default=None, repr=False)
    activity_lines: list[str] = field(default_factory=list, repr=False)
    terminal_status: str | None = None
    terminal_message: str = ""
    item_terminal_emitted: bool = False


def download_job_display_title(job: DownloadJob, *, queued: bool = False) -> str:
    """Return resolved run metadata or a neutral state, never a raw source URL."""
    title = str((job.preview_info or {}).get("title") or "").strip()
    if title:
        return title
    state = "Queued" if queued else "Preparing"
    media = "audio" if job.output_type == OutputType.MP3 else "video"
    return f"{state} {media} run"


def metadata_run_key(info: dict[str, Any]) -> tuple[str, str] | None:
    """Identify in-memory metadata that belongs to one provider item and output type."""
    video_id = str(info.get("id") or "").strip()
    if not video_id:
        return None
    return video_id, metadata_output_type(info).value


@dataclass(frozen=True)
class DownloadOutcome:
    success_count: int = 0
    failure_count: int = 0
    skipped_count: int = 0
    sidecar_failure_count: int = 0

    def combined_with(self, other: "DownloadOutcome") -> "DownloadOutcome":
        return DownloadOutcome(
            success_count=self.success_count + other.success_count,
            failure_count=self.failure_count + other.failure_count,
            skipped_count=self.skipped_count + other.skipped_count,
            sidecar_failure_count=self.sidecar_failure_count + other.sidecar_failure_count,
        )


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
        selected = source if isinstance(source, CookieSource) else CookieSource(str(source))
    except ValueError:
        selected = CookieSource.PUBLIC
    if selected == CookieSource.FILE:
        return True, cookie_file, None
    if selected == CookieSource.BROWSER:
        return True, None, browser_cookie_value(cookie_browser)
    return False, None, None


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
            "or a sign that YouTube wants authenticated cookies. Retry once; if it persists, choose cookies.txt under YouTube access with an exported "
            "YouTube cookies.txt file or Firefox browser cookies.\n\n"
            f"Original yt-dlp error: {message}"
        )
    if "video unavailable" in lower or "this video is not available" in lower or "this content isn't available" in lower:
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


def apply_youtube_runtime_options(opts: dict[str, Any], *, deno_path: str | None) -> dict[str, Any]:
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


TOOLTIP_DELAY_MS = 420
TOOLTIP_POINTER_POLL_MS = 40


def pointer_inside_widget_bounds(widgets: tuple[tk.Widget, ...], pointer_x: int, pointer_y: int) -> bool:
    """Return whether a screen-space point is inside one of the exact widget bounds."""
    for widget in widgets:
        try:
            if not widget.winfo_ismapped():
                continue
            left = widget.winfo_rootx()
            top = widget.winfo_rooty()
            width = widget.winfo_width()
            height = widget.winfo_height()
        except tk.TclError:
            continue
        if left <= pointer_x < left + width and top <= pointer_y < top + height:
            return True
    return False


class _TooltipController:
    """One authoritative tooltip surface per window.

    Tk can miss a widget ``<Leave>`` when a pointer moves quickly across child
    widgets or when an override-redirect tooltip appears under the pointer. A
    single controller prevents competing tooltip windows, delays transient
    flyovers, and verifies the real pointer position while a tooltip is open.
    """

    def __init__(self, host: tk.Misc) -> None:
        self.host = host
        self.tip: tk.Toplevel | None = None
        self.pending_after_id: str | None = None
        self.pointer_poll_after_id: str | None = None
        self.pending: ToolTip | None = None
        self.active: ToolTip | None = None
        host.bind("<Unmap>", lambda _event: self.hide(), add="+")
        host.bind("<Destroy>", lambda event: self.hide() if event.widget is host else None, add="+")

    def request_show(self, tooltip: "ToolTip") -> None:
        if not tooltip.text:
            return
        if self.active is tooltip:
            return
        self._cancel_pending()
        if self.active is not None and self.active is not tooltip:
            self._destroy_tip()
        self.pending = tooltip
        try:
            self.pending_after_id = self.host.after(TOOLTIP_DELAY_MS, lambda: self._show_if_owned(tooltip))
        except tk.TclError:
            self.pending = None

    def request_hide(self, tooltip: "ToolTip") -> None:
        try:
            self.host.after_idle(lambda: self._hide_if_pointer_left(tooltip))
        except tk.TclError:
            self.hide()

    def _hide_if_pointer_left(self, tooltip: "ToolTip") -> None:
        if (self.pending is tooltip or self.active is tooltip) and not tooltip.contains_pointer():
            self.hide()

    def _show_if_owned(self, tooltip: "ToolTip") -> None:
        self.pending_after_id = None
        if self.pending is not tooltip or not tooltip.contains_pointer():
            if self.pending is tooltip:
                self.pending = None
            return
        self._destroy_tip()
        try:
            left, top, _right, bottom = tooltip.anchor_bounds()
            tip = tk.Toplevel(self.host)
            tip.withdraw()
            tip.wm_overrideredirect(True)
            label = tk.Label(
                tip,
                text=tooltip.text,
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
            tip.update_idletasks()
            screen_width = tip.winfo_screenwidth()
            screen_height = tip.winfo_screenheight()
            tip_width = tip.winfo_reqwidth()
            tip_height = tip.winfo_reqheight()
            x = min(max(8, left), max(8, screen_width - tip_width - 8))
            y = bottom + 8
            if y + tip_height > screen_height - 8:
                y = max(8, top - tip_height - 8)
            self.tip = tip
            self.pending = None
            self.active = tooltip
            reveal_toplevel(tip, f"+{x}+{y}")
            self._schedule_pointer_poll()
        except (tk.TclError, ValueError):
            self._destroy_tip()

    def _schedule_pointer_poll(self) -> None:
        self._cancel_pointer_poll()
        try:
            self.pointer_poll_after_id = self.host.after(TOOLTIP_POINTER_POLL_MS, self._poll_pointer)
        except tk.TclError:
            self.pointer_poll_after_id = None

    def _poll_pointer(self) -> None:
        self.pointer_poll_after_id = None
        tooltip = self.active
        if tooltip is None or not tooltip.contains_pointer():
            self.hide()
            return
        self._schedule_pointer_poll()

    def _cancel_pending(self) -> None:
        if self.pending_after_id is not None:
            try:
                self.host.after_cancel(self.pending_after_id)
            except tk.TclError:
                pass
        self.pending_after_id = None
        self.pending = None

    def _cancel_pointer_poll(self) -> None:
        if self.pointer_poll_after_id is not None:
            try:
                self.host.after_cancel(self.pointer_poll_after_id)
            except tk.TclError:
                pass
        self.pointer_poll_after_id = None

    def _destroy_tip(self) -> None:
        self._cancel_pointer_poll()
        if self.tip is not None:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
        self.tip = None
        self.active = None

    def hide(self) -> None:
        self._cancel_pending()
        self._cancel_pointer_poll()
        self._destroy_tip()


class ToolTip:
    """Precise, delayed hover tooltip coordinated within its containing window."""

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        targets_provider = getattr(widget, "tooltip_targets", None)
        targets = tuple(targets_provider()) if callable(targets_provider) else (widget,)
        self.targets = targets or (widget,)
        host = widget.winfo_toplevel()
        controller = getattr(host, "_vodforge_tooltip_controller", None)
        if controller is None:
            controller = _TooltipController(host)
            setattr(host, "_vodforge_tooltip_controller", controller)
        self.controller: _TooltipController = controller
        for target in self.targets:
            target.bind("<Enter>", lambda _event, tooltip=self: tooltip.controller.request_show(tooltip), add="+")
            target.bind("<Leave>", lambda _event, tooltip=self: tooltip.controller.request_hide(tooltip), add="+")
            target.bind("<ButtonPress>", lambda _event, tooltip=self: tooltip.controller.hide(), add="+")
            target.bind("<Destroy>", lambda _event, tooltip=self: tooltip.controller.hide(), add="+")

    def contains_pointer(self) -> bool:
        try:
            pointer_x, pointer_y = self.widget.winfo_pointerxy()
        except tk.TclError:
            return False
        return pointer_inside_widget_bounds(self.targets, pointer_x, pointer_y)

    def anchor_bounds(self) -> tuple[int, int, int, int]:
        bounds: list[tuple[int, int, int, int]] = []
        for target in self.targets:
            try:
                if target.winfo_ismapped():
                    left = target.winfo_rootx()
                    top = target.winfo_rooty()
                    bounds.append((left, top, left + target.winfo_width(), top + target.winfo_height()))
            except tk.TclError:
                continue
        if not bounds:
            raise ValueError("tooltip target is not visible")
        return (
            min(item[0] for item in bounds),
            min(item[1] for item in bounds),
            max(item[2] for item in bounds),
            max(item[3] for item in bounds),
        )


class SleekProgressbar(tk.Canvas):
    """A thin, borderless progress track with ttk-compatible controls."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        variable: tk.Variable | None = None,
        maximum: float = 100.0,
        value: float = 0.0,
        mode: str = "determinate",
        height: int = 5,
        track_color: str = THEME["surface_2"],
        bar_color: str = THEME["accent"],
        **kwargs: Any,
    ) -> None:
        kwargs.pop("style", None)
        super().__init__(parent, height=height, bg=THEME["bg"], bd=0, highlightthickness=0, **kwargs)
        self._maximum = max(1.0, float(maximum))
        self._mode = mode
        self._track_color = track_color
        self._bar_color = bar_color
        self._phase = 0.0
        self._after_id: str | None = None
        self._variable = variable if variable is not None else tk.DoubleVar(master=self, value=value)
        if variable is not None and value:
            self._variable.set(value)
        self._variable.trace_add("write", lambda *_args: self._redraw())
        self.bind("<Configure>", lambda _event: self._redraw(), add="+")
        self.after_idle(self._redraw)

    def configure(self, cnf: Any | None = None, **kwargs: Any) -> Any:
        if cnf:
            kwargs.update(cnf)
        if "mode" in kwargs:
            self._mode = str(kwargs.pop("mode"))
        if "maximum" in kwargs:
            self._maximum = max(1.0, float(kwargs.pop("maximum")))
        if "value" in kwargs:
            self._variable.set(float(kwargs.pop("value")))
        result = super().configure(**kwargs) if kwargs else None
        self._redraw()
        return result

    config = configure

    def start(self, interval: int = 50) -> None:
        self.stop()
        self._mode = "indeterminate"

        def tick() -> None:
            self._phase = (self._phase + 0.035) % 1.0
            self._redraw()
            self._after_id = self.after(interval, tick)

        tick()

    def stop(self) -> None:
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _redraw(self) -> None:
        try:
            width = max(1, self.winfo_width())
            height = max(3, self.winfo_height())
        except tk.TclError:
            return
        self.delete("all")
        y1 = max(0, (height - 3) // 2)
        y2 = min(height, y1 + 3)
        self.create_rectangle(0, y1, width, y2, fill=self._track_color, outline="")
        if self._mode == "indeterminate":
            segment = max(24, int(width * 0.24))
            start = max(0, int((width + segment) * self._phase) - segment)
            end = min(width, start + segment)
        else:
            try:
                fraction = max(0.0, min(1.0, float(self._variable.get()) / self._maximum))
            except (TypeError, ValueError, tk.TclError):
                fraction = 0.0
            start, end = 0, int(width * fraction)
        if end > start:
            self.create_rectangle(start, y1, end, y2, fill=self._bar_color, outline="")
            if y1 > 0:
                self.create_line(start, y1, end, y1, fill="#9a96ff")


class PixelScrollTable(tk.Frame):
    """Small Treeview-compatible table with true pixel scrolling."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        columns: tuple[str, ...],
        selectmode: str = "browse",
        row_height: int = 30,
        header_height: int = 28,
    ) -> None:
        del selectmode
        super().__init__(parent, bg=THEME["border"], bd=0, highlightthickness=1, highlightbackground=THEME["subtle"])
        self._columns = tuple(columns)
        self._headings = {column: column for column in columns}
        self._column_options: dict[str, dict[str, Any]] = {
            column: {"width": 100, "minwidth": 40, "stretch": False, "anchor": "w"}
            for column in columns
        }
        self._items: dict[str, tuple[Any, ...]] = {}
        self._order: list[str] = []
        self._selection: str | None = None
        self._focus_item: str | None = None
        self._row_height = max(20, int(row_height))
        self._header_height = max(20, int(header_height))
        self._yscrollcommand: Callable[[float, float], Any] | None = None
        self._xscrollcommand: Callable[[float, float], Any] | None = None
        self._font = tkfont.Font(font=FONT_UI)
        self._header_font = tkfont.Font(font=FONT_UI_SMALL_MEDIUM)

        self._header = tk.Canvas(self, height=self._header_height, bg=THEME["surface"], bd=0, highlightthickness=0, xscrollincrement=1)
        self._body = tk.Canvas(self, bg=THEME["surface"], bd=0, highlightthickness=0, takefocus=True, xscrollincrement=1, yscrollincrement=1)
        self._header.pack(fill="x")
        self._body.pack(fill="both", expand=True)
        self._body.configure(yscrollcommand=self._report_yview, xscrollcommand=self._report_xview)
        self._body.bind("<Configure>", lambda _event: self._redraw(), add="+")
        self._body.bind("<Button-1>", self._select_from_pointer, add="+")
        self._body.bind("<Up>", lambda _event: self._move_selection(-1), add="+")
        self._body.bind("<Down>", lambda _event: self._move_selection(1), add="+")
        self._body.bind("<Prior>", lambda _event: self._move_selection(-max(1, self._visible_rows() - 1)), add="+")
        self._body.bind("<Next>", lambda _event: self._move_selection(max(1, self._visible_rows() - 1)), add="+")
        self._bind_precision_scroll(self._body)
        self._bind_precision_scroll(self._header, horizontal_only=True)

    def __getitem__(self, key: str) -> Any:
        if key == "columns":
            return self._columns
        return super().__getitem__(key)

    def configure(self, cnf: Any | None = None, **kwargs: Any) -> Any:
        if cnf:
            kwargs.update(cnf)
        if "yscrollcommand" in kwargs:
            self._yscrollcommand = kwargs.pop("yscrollcommand")
        if "xscrollcommand" in kwargs:
            self._xscrollcommand = kwargs.pop("xscrollcommand")
        result = super().configure(**kwargs) if kwargs else None
        self._report_yview(*self._body.yview())
        self._report_xview(*self._body.xview())
        return result

    config = configure

    def bind(self, sequence: str | None = None, func: Callable[..., Any] | None = None, add: str | bool | None = None) -> str:
        if sequence in {"<<TreeviewSelect>>", "<Button-1>", "<Button-2>", "<Button-3>"}:
            return self._body.bind(sequence, func, add)
        return super().bind(sequence, func, add)

    def heading(self, column: str, *, text: str = "") -> None:
        self._headings[column] = text
        self._redraw()

    def column(self, column: str, **kwargs: Any) -> dict[str, Any]:
        options = self._column_options[column]
        options.update(kwargs)
        options["width"] = max(int(options.get("minwidth", 1)), int(options.get("width", 100)))
        self._redraw()
        return dict(options)

    def insert(self, _parent: str, index: str | int, *, iid: str, values: tuple[Any, ...]) -> str:
        item_id = str(iid)
        if item_id in self._items:
            self.delete(item_id)
        self._order.append(item_id) if index == "end" else self._order.insert(max(0, int(index)), item_id)
        self._items[item_id] = tuple(values)
        self._redraw()
        return item_id

    def delete(self, *items: str) -> None:
        for raw_item in items:
            item = str(raw_item)
            self._items.pop(item, None)
            if item in self._order:
                self._order.remove(item)
            if self._selection == item:
                self._selection = None
            if self._focus_item == item:
                self._focus_item = None
        self._redraw()

    def get_children(self, _item: str | None = None) -> tuple[str, ...]:
        return tuple(self._order)

    def selection(self) -> tuple[str, ...]:
        return (self._selection,) if self._selection in self._items else ()

    def selection_set(self, item: str) -> None:
        item_id = str(item)
        if item_id not in self._items:
            return
        changed = item_id != self._selection
        self._selection = item_id
        self._focus_item = item_id
        self._redraw()
        self._see(item_id)
        if changed:
            self._body.event_generate("<<TreeviewSelect>>", when="tail")

    def focus(self, item: str | None = None) -> str:
        if item is None:
            return self._focus_item or ""
        if str(item) in self._items:
            self._focus_item = str(item)
        return self._focus_item or ""

    def identify_row(self, y: int | float) -> str:
        index = int(float(self._body.canvasy(y)) // self._row_height)
        return self._order[index] if 0 <= index < len(self._order) else ""

    def identify_column(self, x: int | float) -> str:
        position = float(self._body.canvasx(x))
        cursor = 0.0
        for index, (_column, width, _anchor) in enumerate(self._layout_columns(), start=1):
            cursor += width
            if position < cursor:
                return f"#{index}"
        return ""

    def yview(self, *args: Any) -> tuple[float, float] | None:
        if not args:
            return self._body.yview()
        self._body.yview(*args)
        return None

    def xview(self, *args: Any) -> tuple[float, float] | None:
        if not args:
            return self._body.xview()
        self._body.xview(*args)
        self._header.xview(*args)
        return None

    def _report_yview(self, first: str | float, last: str | float) -> None:
        if self._yscrollcommand is not None:
            self._yscrollcommand(float(first), float(last))

    def _report_xview(self, first: str | float, last: str | float) -> None:
        self._header.xview_moveto(float(first))
        if self._xscrollcommand is not None:
            self._xscrollcommand(float(first), float(last))

    def _visible_rows(self) -> int:
        return max(1, self._body.winfo_height() // self._row_height)

    def _layout_columns(self) -> list[tuple[str, int, str]]:
        widths = [max(int(self._column_options[column].get("minwidth", 1)), int(self._column_options[column].get("width", 100))) for column in self._columns]
        extra = max(1, self._body.winfo_width()) - sum(widths)
        if extra > 0:
            stretch_indices = [index for index, column in enumerate(self._columns) if self._column_options[column].get("stretch")]
            if stretch_indices:
                widths[stretch_indices[0]] += extra
        return [(column, widths[index], str(self._column_options[column].get("anchor", "w"))) for index, column in enumerate(self._columns)]

    def _ellipsize(self, value: Any, width: int, *, font: tkfont.Font) -> str:
        text = str(value or "")
        available = max(0, width - 16)
        if font.measure(text) <= available:
            return text
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if font.measure(text[:middle] + "…") <= available:
                low = middle
            else:
                high = middle - 1
        return text[:low] + "…"

    def _redraw(self) -> None:
        try:
            y_first, x_first = self._body.yview()[0], self._body.xview()[0]
        except tk.TclError:
            return
        layout = self._layout_columns()
        content_width = max(1, sum(width for _column, width, _anchor in layout))
        content_height = max(self._row_height, len(self._order) * self._row_height)
        self._header.delete("all")
        self._body.delete("all")
        cursor = 0
        for column, width, anchor in layout:
            self._header.create_rectangle(cursor, 0, cursor + width, self._header_height, fill=THEME["surface"], outline="")
            self._header.create_text(cursor + (width / 2 if anchor == "center" else 10), self._header_height / 2, text=self._ellipsize(self._headings.get(column, column), width, font=self._header_font), anchor="center" if anchor == "center" else "w", fill=THEME["muted"], font=self._header_font)
            cursor += width
        self._header.create_line(0, self._header_height - 1, content_width, self._header_height - 1, fill=THEME["border"])
        for row_index, item_id in enumerate(self._order):
            top = row_index * self._row_height
            selected = item_id == self._selection
            self._body.create_rectangle(0, top, content_width, top + self._row_height, fill=THEME["accent_dark"] if selected else THEME["surface"], outline="")
            values = self._items.get(item_id, ())
            cursor = 0
            for value_index, (_column, width, anchor) in enumerate(layout):
                value = values[value_index] if value_index < len(values) else ""
                text_x = cursor + (width / 2 if anchor == "center" else width - 10 if anchor == "e" else 10)
                self._body.create_text(text_x, top + (self._row_height / 2), text=self._ellipsize(value, width, font=self._font), anchor="center" if anchor == "center" else "e" if anchor == "e" else "w", fill="#ffffff" if selected else THEME["text"], font=self._font)
                cursor += width
        self._header.configure(scrollregion=(0, 0, content_width, self._header_height))
        self._body.configure(scrollregion=(0, 0, content_width, content_height))
        self._body.xview_moveto(x_first)
        self._header.xview_moveto(x_first)
        self._body.yview_moveto(y_first)

    def _select_from_pointer(self, event: tk.Event[Any]) -> None:
        row = self.identify_row(event.y)
        if row:
            self.selection_set(row)
            self._body.focus_set()

    def _move_selection(self, amount: int) -> str:
        if not self._order:
            return "break"
        try:
            current = self._order.index(self._selection or "")
        except ValueError:
            current = 0 if amount >= 0 else len(self._order) - 1
        self.selection_set(self._order[max(0, min(len(self._order) - 1, current + amount))])
        return "break"

    def _see(self, item: str) -> None:
        try:
            index = self._order.index(item)
        except ValueError:
            return
        content_height = max(1, len(self._order) * self._row_height)
        viewport = max(1, self._body.winfo_height())
        top, bottom = index * self._row_height, (index + 1) * self._row_height
        visible_top = self._body.canvasy(0)
        if top < visible_top:
            self._body.yview_moveto(top / content_height)
        elif bottom > visible_top + viewport:
            self._body.yview_moveto(max(0.0, (bottom - viewport) / content_height))

    def _scroll_pixels(self, dx: int, dy: int) -> str:
        if dy:
            content_height = max(self._body.winfo_height(), len(self._order) * self._row_height)
            self._body.yview_moveto(max(0.0, min(1.0, self._body.yview()[0] + (dy / max(1, content_height)))))
        if dx:
            content_width = max(self._body.winfo_width(), sum(width for _column, width, _anchor in self._layout_columns()))
            self.xview("moveto", max(0.0, min(1.0, self._body.xview()[0] + (dx / max(1, content_width)))))
        return "break"

    def _bind_precision_scroll(self, target: tk.Misc, *, horizontal_only: bool = False) -> None:
        def on_wheel(event: tk.Event[Any]) -> str:
            pixels = focus_wheel_pixels(getattr(event, "delta", 0))
            horizontal = horizontal_only or bool(getattr(event, "state", 0) & 0x0001)
            return self._scroll_pixels(pixels if horizontal else 0, 0 if horizontal else pixels)

        def on_touchpad(event: tk.Event[Any]) -> str:
            delta_x, delta_y = touchpad_scroll_deltas(self, getattr(event, "delta", 0))
            return self._scroll_pixels(focus_wheel_pixels(delta_x), 0 if horizontal_only else focus_wheel_pixels(delta_y))

        target.bind("<MouseWheel>", on_wheel, add="+")
        target.bind("<Shift-MouseWheel>", on_wheel, add="+")
        target.bind("<Button-4>", lambda _event: self._scroll_pixels(0, -36), add="+")
        target.bind("<Button-5>", lambda _event: self._scroll_pixels(0, 36), add="+")
        try:
            target.bind("<TouchpadScroll>", on_touchpad, add="+")
        except tk.TclError:
            pass


class SleekScrollbar(tk.Canvas):
    """A narrow auto-hiding scrollbar without platform arrow chrome."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        command: Callable[..., Any],
        orient: str = "vertical",
        width: int = 8,
        thumb_color: str = THEME["border"],
        hover_color: str = THEME["subtle"],
    ) -> None:
        if orient not in {"vertical", "horizontal"}:
            raise ValueError(f"Unsupported scrollbar orientation: {orient}")
        self._orient = orient
        super().__init__(
            parent,
            width=width if orient == "vertical" else 1,
            height=width if orient == "horizontal" else 1,
            bg=THEME["bg"],
            bd=0,
            highlightthickness=0,
            takefocus=0,
            cursor="arrow",
        )
        self._command = command
        self._thumb_color = thumb_color
        self._hover_color = hover_color
        self._first = 0.0
        self._last = 1.0
        self._hovered = False
        self._drag_offset: float | None = None
        self.bind("<Configure>", lambda _event: self._redraw(), add="+")
        self.bind("<Enter>", self._set_hovered, add="+")
        self.bind("<Leave>", self._set_unhovered, add="+")
        self.bind("<Button-1>", self._begin_drag, add="+")
        self.bind("<B1-Motion>", self._drag, add="+")
        self.bind("<ButtonRelease-1>", self._end_drag, add="+")

    def set(self, first: str | float, last: str | float) -> None:
        try:
            self._first = max(0.0, min(1.0, float(first)))
            self._last = max(self._first, min(1.0, float(last)))
        except (TypeError, ValueError):
            self._first, self._last = 0.0, 1.0
        self._redraw()

    def _thumb_bounds(self) -> tuple[float, float] | None:
        length = max(1, self.winfo_height() if self._orient == "vertical" else self.winfo_width())
        visible = max(0.0, min(1.0, self._last - self._first))
        if visible >= 0.999:
            return None
        thumb_length = min(float(length), max(28.0, length * visible))
        travel = max(1.0, length - thumb_length)
        scrollable = max(0.001, 1.0 - visible)
        start = travel * min(1.0, self._first / scrollable)
        return start, start + thumb_length

    def _redraw(self) -> None:
        try:
            self.delete("all")
            bounds = self._thumb_bounds()
            if bounds is None:
                return
            start, end = bounds
            color = self._hover_color if self._hovered else self._thumb_color
            if self._orient == "vertical":
                cross = max(2, self.winfo_width() // 2)
                self.create_line(cross, start + 3, cross, max(start + 3, end - 3), fill=color, width=4, capstyle=tk.ROUND)
            else:
                cross = max(2, self.winfo_height() // 2)
                self.create_line(start + 3, cross, max(start + 3, end - 3), cross, fill=color, width=4, capstyle=tk.ROUND)
        except tk.TclError:
            return

    def _set_hovered(self, _event: tk.Event[Any]) -> None:
        self._hovered = True
        self._redraw()

    def _set_unhovered(self, _event: tk.Event[Any]) -> None:
        self._hovered = False
        self._drag_offset = None
        self._redraw()

    def _begin_drag(self, event: tk.Event[Any]) -> None:
        bounds = self._thumb_bounds()
        if bounds is None:
            return
        start, end = bounds
        pointer = event.y if self._orient == "vertical" else event.x
        if start <= pointer <= end:
            self._drag_offset = pointer - start
            return
        self._drag_offset = (end - start) / 2
        self._move_thumb(pointer - self._drag_offset)

    def _drag(self, event: tk.Event[Any]) -> None:
        if self._drag_offset is not None:
            pointer = event.y if self._orient == "vertical" else event.x
            self._move_thumb(pointer - self._drag_offset)

    def _end_drag(self, _event: tk.Event[Any]) -> None:
        self._drag_offset = None

    def _move_thumb(self, top: float) -> None:
        bounds = self._thumb_bounds()
        if bounds is None:
            return
        length = max(1.0, float(self.winfo_height() if self._orient == "vertical" else self.winfo_width()))
        thumb_length = bounds[1] - bounds[0]
        travel = max(1.0, length - thumb_length)
        visible = max(0.0, min(1.0, self._last - self._first))
        first = max(0.0, min(1.0 - visible, (max(0.0, min(travel, top)) / travel) * (1.0 - visible)))
        self._command("moveto", first)


class PillAction(tk.Canvas):
    """A compact rounded action surface for header utilities."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        textvariable: tk.StringVar,
        command: Callable[[], None],
        image: Any | None = None,
        width: int = 240,
        height: int = 34,
    ) -> None:
        super().__init__(parent, width=width, height=height, bg=THEME["bg"], bd=0, highlightthickness=0, cursor="hand2", takefocus=1)
        self._textvariable = textvariable
        self._command = command
        self._icon = image
        self._hovered = False
        self._background_image: Any | None = None
        self._background_item = self.create_image(0, 0, anchor="nw")
        self._icon_item = self.create_image(15, height // 2, image=image, anchor="w") if image is not None else None
        self._text_item = self.create_text(18 if image is None else 38, height // 2, text=textvariable.get(), fill=THEME["muted"], font=FONT_UI_SMALL, anchor="w")
        textvariable.trace_add("write", lambda *_args: self._sync_text())
        self.bind("<Configure>", lambda _event: self._redraw(), add="+")
        self.bind("<Enter>", lambda _event: self._set_hover(True), add="+")
        self.bind("<Leave>", lambda _event: self._set_hover(False), add="+")
        self.bind("<Button-1>", lambda _event: self._command(), add="+")
        self.bind("<Return>", lambda _event: self._command(), add="+")
        self.bind("<space>", lambda _event: self._command(), add="+")
        self.after_idle(self._redraw)

    def _sync_text(self) -> None:
        try:
            self.itemconfigure(self._text_item, text=self._textvariable.get())
        except tk.TclError:
            pass

    def _set_hover(self, hovered: bool) -> None:
        self._hovered = hovered
        try:
            self.itemconfigure(self._text_item, fill=THEME["text"] if hovered else THEME["muted"])
            self._redraw()
        except tk.TclError:
            pass

    def _redraw(self) -> None:
        try:
            width = max(1, self.winfo_width())
            height = max(1, self.winfo_height())
        except tk.TclError:
            return
        if Image is not None and ImageDraw is not None and ImageTk is not None:
            surface = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            ImageDraw.Draw(surface).rounded_rectangle(
                (0, 0, width - 1, height - 1),
                radius=min(17, height // 2),
                fill=THEME["surface_2"] if self._hovered else THEME["surface"],
                outline=THEME["border"],
                width=1,
            )
            self._background_image = ImageTk.PhotoImage(surface)
            self.itemconfigure(self._background_item, image=self._background_image)
            self.coords(self._background_item, 0, 0)
            self.tag_lower(self._background_item)
        if self._icon_item is not None:
            self.coords(self._icon_item, 15, height // 2)
        self.coords(self._text_item, 18 if self._icon is None else 38, height // 2)


class RoundedIconButton(tk.Canvas):
    """A Retina-friendly rounded icon control drawn with native canvas shapes."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        image: Any | None,
        text: str,
        command: Callable[[], None],
        primary: bool = False,
        width: int = 40,
        height: int = 40,
        radius: int = 8,
    ) -> None:
        resolved_width = width if image is not None else max(width, 76)
        super().__init__(
            parent,
            width=resolved_width,
            height=height,
            bg=THEME["bg"],
            bd=0,
            highlightthickness=0,
            takefocus=1,
            cursor="hand2",
        )
        self._button_image = image
        self._button_text = text
        self._command = command
        self._primary = primary
        self._radius = radius
        self._state = "normal"
        self._hovered = False
        self._pressed = False
        self._background_image: Any | None = None
        self._background_item = self.create_image(0, 0, anchor="nw")
        if image is not None:
            self._content_item = self.create_image(resolved_width // 2, height // 2, image=image, anchor="center")
        else:
            self._content_item = self.create_text(
                resolved_width // 2,
                height // 2,
                text=text,
                fill="#ffffff" if primary else THEME["muted"],
                font=FONT_UI_SMALL_MEDIUM,
                anchor="center",
            )
        self.bind("<Configure>", lambda _event: self._redraw(), add="+")
        self.bind("<Enter>", lambda _event: self._set_hovered(True), add="+")
        self.bind("<Leave>", lambda _event: self._set_hovered(False), add="+")
        self.bind("<ButtonPress-1>", self._press, add="+")
        self.bind("<ButtonRelease-1>", self._release, add="+")
        self.bind("<Return>", lambda _event: self._invoke(), add="+")
        self.bind("<space>", lambda _event: self._invoke(), add="+")
        self.after_idle(self._redraw)

    def configure(self, cnf: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        options = dict(cnf or {})
        options.update(kwargs)
        if not options:
            return super().configure()
        state = options.pop("state", None)
        if state is not None:
            self._state = str(state)
            super().configure(cursor="arrow" if self._state == "disabled" else "hand2")
        text = options.pop("text", None)
        if text is not None:
            self._button_text = str(text)
            if self._button_image is None:
                self.itemconfigure(self._content_item, text=self._button_text)
        result = super().configure(**options) if options else None
        self._redraw()
        return result

    config = configure

    def _set_hovered(self, hovered: bool) -> None:
        self._hovered = hovered and self._state != "disabled"
        if not hovered:
            self._pressed = False
        self._redraw()

    def _press(self, _event: tk.Event[Any]) -> None:
        if self._state != "disabled":
            self._pressed = True
            self._redraw()

    def _release(self, event: tk.Event[Any]) -> None:
        should_invoke = (
            self._state != "disabled"
            and self._pressed
            and 0 <= event.x < self.winfo_width()
            and 0 <= event.y < self.winfo_height()
        )
        self._pressed = False
        self._redraw()
        if should_invoke:
            self._command()

    def _invoke(self) -> None:
        if self._state != "disabled":
            self._command()

    def _redraw(self) -> None:
        try:
            disabled = self._state == "disabled"
            if self._primary:
                border = THEME["panel"] if disabled else THEME["accent"]
                if disabled:
                    fill = THEME["panel"]
                elif self._pressed:
                    fill = THEME["accent_dark"]
                elif self._hovered:
                    fill = "#8584ff"
                else:
                    fill = THEME["accent"]
            else:
                border = THEME["border"]
                fill = THEME["panel"] if self._pressed else THEME["surface_2"] if self._hovered else THEME["surface"]
            width = max(1, self.winfo_width())
            height = max(1, self.winfo_height())
            if width <= 2 or height <= 2:
                return
            if Image is not None and ImageDraw is not None and ImageTk is not None:
                scale = 4
                surface = Image.new("RGBA", (width * scale, height * scale), THEME["bg"])
                draw = ImageDraw.Draw(surface)
                radius = min(self._radius, height // 2) * scale
                draw.rounded_rectangle(
                    (0, 0, width * scale - 1, height * scale - 1),
                    radius=radius,
                    fill=border,
                )
                draw.rounded_rectangle(
                    (scale, scale, width * scale - scale - 1, height * scale - scale - 1),
                    radius=max(0, radius - scale),
                    fill=fill,
                )
                resampling = getattr(Image, "Resampling", Image)
                surface = surface.resize((width, height), resampling.LANCZOS)
                self._background_image = ImageTk.PhotoImage(surface)
                self.itemconfigure(self._background_item, image=self._background_image)
                self.coords(self._background_item, 0, 0)
            else:
                self.itemconfigure(self._background_item, image="")
                self.delete("button-fallback")
                self.create_rectangle(0, 0, width - 1, height - 1, fill=fill, outline=border, tags="button-fallback")
                self.tag_lower("button-fallback")
            self.tag_lower(self._background_item)
            self.coords(self._content_item, width // 2, height // 2)
        except tk.TclError:
            return


class SegmentedSelector(tk.Frame):
    """Small two-state selector with consistent rendering across Tk platforms."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        variable: tk.StringVar,
        values: tuple[str, ...] = (OutputType.MP4.value, OutputType.MP3.value),
        background: str = THEME["surface"],
        compact: bool = False,
    ) -> None:
        super().__init__(parent, bg=THEME["border"], bd=0, highlightthickness=0, padx=1, pady=1)
        self._variable = variable
        self._background = background
        self._labels: dict[str, tk.Label] = {}
        horizontal_padding = 7 if compact else 10
        vertical_padding = 3 if compact else 4
        for value in values:
            label = tk.Label(
                self,
                text=value,
                bg=background,
                fg=THEME["muted"],
                bd=0,
                highlightthickness=0,
                padx=horizontal_padding,
                pady=vertical_padding,
                font=FONT_UI_SMALL_MEDIUM,
                cursor="hand2",
                takefocus=1,
            )
            label.pack(side="left")
            label.bind("<Button-1>", lambda _event, selected=value: self._variable.set(selected))
            label.bind("<Return>", lambda _event, selected=value: self._variable.set(selected))
            label.bind("<space>", lambda _event, selected=value: self._variable.set(selected))
            label.bind("<Enter>", lambda _event, selected=value: self._set_hover(selected, True), add="+")
            label.bind("<Leave>", lambda _event, selected=value: self._set_hover(selected, False), add="+")
            self._labels[value] = label
        self._trace_id = variable.trace_add("write", lambda *_args: self._sync())
        self._sync()

    def tooltip_targets(self) -> tuple[tk.Label, ...]:
        """Use only the visible segments as tooltip hit zones, not the frame."""
        return tuple(self._labels.values())

    def _set_hover(self, value: str, hovered: bool) -> None:
        if self._variable.get() == value:
            return
        label = self._labels.get(value)
        if label is not None:
            label.configure(bg=THEME["surface_2"] if hovered else self._background, fg=THEME["text"] if hovered else THEME["muted"])

    def _sync(self) -> None:
        selected = self._variable.get()
        for value, label in self._labels.items():
            active = value == selected
            label.configure(
                bg=THEME["accent_dark"] if active else self._background,
                fg="#ffffff" if active else THEME["muted"],
            )

    def destroy(self) -> None:
        try:
            self._variable.trace_remove("write", self._trace_id)
        except (tk.TclError, AttributeError, ValueError):
            pass
        super().destroy()


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
        prepare_activity_log()
        write_diagnostic(f"app start: name={APP_NAME} frozen={getattr(sys, 'frozen', False)} executable={sys.executable} argv={sys.argv}")
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
                write_diagnostic("macOS application icon uses the bundle CFBundleIconFile ICNS")
            elif runtime_icon_asset.endswith(".ico"):
                self.iconbitmap(default=str(bundled_asset_path(runtime_icon_asset)))
            else:
                self._app_icon_image = tk.PhotoImage(file=str(bundled_asset_path(runtime_icon_asset)))
                self.iconphoto(True, self._app_icon_image)
        except tk.TclError as exc:
            write_diagnostic(f"app icon could not be loaded: {exc}")
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        window_width, window_height = bounded_window_size(screen_width, screen_height)
        self.geometry(initial_window_geometry(screen_width, screen_height))
        self.minsize(min(820, window_width), min(560, window_height))
        self.configure(bg=THEME["bg"])

        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
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
            self.installation_state = load_or_create_installation_state(self.installation_state_path)
            write_diagnostic("anonymous installation ID loaded from the VODForge application-data folder")
        except (InstallationIdentityError, OSError) as exc:
            write_diagnostic(f"anonymous installation ID unavailable; Cloud funnel deduplication is disabled: {exc}")

        self.url_var = tk.StringVar()
        self.url_list_file_var = tk.StringVar(value="No URL list loaded")
        self.batch_urls: list[str] = []
        self.output_var = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.output_type_var = tk.StringVar(value=OutputType.MP4.value)
        self.library_output_type_var = tk.StringVar(value=OutputType.MP4.value)
        self.quality_var = tk.StringVar(value="1080p Full HD")
        self.export_mode_var = tk.StringVar(value=ExportMode.AUTO_CBR.value)
        self.export_mode_choice_var = tk.StringVar(value=export_mode_display_name(ExportMode.AUTO_CBR))
        self.export_mode_description_var = tk.StringVar(value=export_mode_description(ExportMode.AUTO_CBR))
        self.manual_video_bitrate_var = tk.StringVar(value=str(STRICT_VIDEO_BITRATE_KBPS))
        self.manual_audio_bitrate_var = tk.StringVar(value=str(STRICT_AUDIO_BITRATE_KBPS))
        self.manual_sample_rate_var = tk.StringVar(value=AUDIO_SAMPLE_RATE)
        self.manual_channels_var = tk.StringVar(value="Stereo")
        self.manual_preset_var = tk.StringVar(value="medium")
        self.mp3_quality_var = tk.StringVar(value="Maximum — 320 kbps CBR")
        self.mp3_sample_rate_var = tk.StringVar(value="Preserve source")
        self.mp3_channels_var = tk.StringVar(value="Preserve source")
        self.mp3_embed_metadata_var = tk.BooleanVar(value=True)
        self.mp3_cover_art_mode_var = tk.StringVar(value=MP3_COVER_ART_OPTIONS[0])
        self.mp3_custom_cover_art_path: Path | None = None
        self.mp3_custom_cover_art_var = tk.StringVar(value="Select Custom art to choose an image")
        self.mp3_cover_art_description_var = tk.StringVar()
        self.tags_var = tk.StringVar()
        self.single_video_only_var = tk.BooleanVar(value=DEFAULT_IGNORE_PLAYLISTS)
        self.use_nvenc_var = tk.BooleanVar(value=False)
        self.cookie_source_var = tk.StringVar(value=CookieSource.PUBLIC.value)
        self.cookie_file_path: Path | None = None
        self.cookie_file_var = tk.StringVar(value="No cookies.txt selected")
        self.cookie_browser_var = tk.StringVar(value=COOKIE_BROWSER_PLACEHOLDER)
        self._cookie_file_frames: list[ttk.Frame] = []
        self._cookie_browser_frames: list[ttk.Frame] = []
        self.cookie_source_var.trace_add("write", lambda *_args: self._on_cookie_source_changed())
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
        self._append_log(f"—— Session started {datetime.now().isoformat(timespec='seconds')} ——")
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
        style.configure("TButton", background=THEME["surface_2"], foreground=THEME["text"], bordercolor=THEME["border"], focusthickness=0, focuscolor=THEME["surface_2"], padding=(12, 7), font=FONT_UI_MEDIUM)
        style.configure("Compact.TButton", background=THEME["surface_2"], foreground=THEME["text"], bordercolor=THEME["border"], focusthickness=0, focuscolor=THEME["surface_2"], padding=(10, 4), font=FONT_UI_MEDIUM)
        style.map("Compact.TButton", background=[("active", THEME["surface_2"]), ("pressed", THEME["panel"]), ("disabled", THEME["panel"])])
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
        style.configure("FocusShell.TFrame", background=THEME["bg"])
        style.configure("FocusSurface.TFrame", background=THEME["surface"])
        style.configure(
            "CloudPreview.TFrame",
            background=THEME["surface"],
            bordercolor=THEME["border"],
            borderwidth=1,
            relief="solid",
        )
        style.configure("FocusBrand.TLabel", background=THEME["bg"], foreground=THEME["text"], font=(FONT_UI_FAMILY, 18, "bold"))
        style.configure("FocusTitle.TLabel", background=THEME["bg"], foreground=THEME["text"], font=(FONT_UI_FAMILY, 15, "bold"))
        style.configure("FocusActiveTitle.TLabel", background=THEME["bg"], foreground=THEME["text"], font=(FONT_UI_FAMILY, 13, "bold"))
        style.configure("FocusProfile.TLabel", background=THEME["bg"], foreground=THEME["accent"], font=FONT_UI_SMALL)
        style.configure("FocusPercent.TLabel", background=THEME["bg"], foreground=THEME["accent"], font=(FONT_UI_FAMILY, 24))
        style.configure("FocusEyebrow.TLabel", background=THEME["bg"], foreground=THEME["muted"], font=FONT_UI_SMALL_MEDIUM)
        style.configure("FocusSurface.TLabel", background=THEME["surface"], foreground=THEME["text"], font=FONT_UI)
        style.configure("FocusSurfaceMuted.TLabel", background=THEME["surface"], foreground=THEME["muted"], font=FONT_UI_SMALL)
        style.configure("CloudTitle.TLabel", background=THEME["surface"], foreground=THEME["text"], font=FONT_UI_MEDIUM)
        style.configure("CloudBadge.TLabel", background=THEME["surface"], foreground=THEME["accent"], font=FONT_UI_SMALL_MEDIUM)
        style.configure("FocusNav.TButton", background=THEME["bg"], foreground=THEME["muted"], bordercolor=THEME["bg"], focusthickness=0, focuscolor=THEME["bg"], padding=(12, 8), font=FONT_UI)
        style.configure("FocusNavActive.TButton", background=THEME["bg"], foreground=THEME["accent"], bordercolor=THEME["bg"], focusthickness=0, focuscolor=THEME["bg"], padding=(12, 8), font=FONT_UI)
        style.layout("FocusNav.TButton", [("Button.padding", {"sticky": "nswe", "children": [("Button.label", {"sticky": "nswe"})]})])
        style.layout("FocusNavActive.TButton", [("Button.padding", {"sticky": "nswe", "children": [("Button.label", {"sticky": "nswe"})]})])
        style.map("FocusNav.TButton", background=[("active", THEME["surface"])], foreground=[("active", THEME["text"])])
        style.map("FocusNavActive.TButton", background=[("active", THEME["surface"])], foreground=[("active", THEME["accent"])])
        style.configure("FocusQuiet.TButton", background=THEME["surface"], foreground=THEME["muted"], bordercolor=THEME["surface_2"], lightcolor=THEME["surface_2"], darkcolor=THEME["surface_2"], focusthickness=0, focuscolor=THEME["surface"], relief="flat", padding=(11, 6), font=FONT_UI_SMALL_MEDIUM)
        style.map("FocusQuiet.TButton", background=[("active", THEME["surface_2"]), ("pressed", THEME["panel"])], foreground=[("active", THEME["text"])])
        style.configure("CloudDisabled.TButton", background=THEME["surface_2"], foreground=THEME["subtle"], bordercolor=THEME["surface_2"], lightcolor=THEME["surface_2"], darkcolor=THEME["surface_2"], focusthickness=0, focuscolor=THEME["surface_2"], relief="flat", padding=(11, 6), font=FONT_UI_SMALL_MEDIUM)
        style.map("CloudDisabled.TButton", background=[("disabled", THEME["surface_2"])], foreground=[("disabled", THEME["subtle"])])
        style.configure("FocusCopySuccess.TButton", background=THEME["accent_dark"], foreground="#ffffff", bordercolor=THEME["accent"], lightcolor=THEME["accent"], darkcolor=THEME["accent"], focusthickness=0, focuscolor=THEME["accent_dark"], relief="flat", padding=(11, 6), font=FONT_UI_SMALL_MEDIUM)
        style.map("FocusCopySuccess.TButton", background=[("active", THEME["accent"]), ("pressed", THEME["accent_dark"])], foreground=[("active", "#ffffff")])
        style.configure("FocusIcon.TButton", background=THEME["bg"], foreground=THEME["muted"], bordercolor=THEME["bg"], lightcolor=THEME["bg"], darkcolor=THEME["bg"], focusthickness=0, focuscolor=THEME["bg"], relief="flat", padding=(9, 8))
        style.map("FocusIcon.TButton", background=[("active", THEME["surface"]), ("pressed", THEME["panel"])])
        style.configure("FocusDestination.TButton", background=THEME["surface"], foreground=THEME["muted"], bordercolor=THEME["border"], lightcolor=THEME["border"], darkcolor=THEME["border"], focusthickness=0, focuscolor=THEME["surface"], relief="flat", padding=(12, 7), font=FONT_UI_SMALL)
        style.map("FocusDestination.TButton", background=[("active", THEME["surface_2"])], foreground=[("active", THEME["text"])])
        style.configure("FocusCommand.TEntry", fieldbackground=THEME["surface"], foreground=THEME["text"], insertcolor=THEME["text"], bordercolor=THEME["surface"], lightcolor=THEME["surface"], darkcolor=THEME["surface"], padding=(4, 13), font=(FONT_UI_FAMILY, 12))
        style.configure("FocusProgress.Horizontal.TProgressbar", background=THEME["accent"], troughcolor=THEME["surface_2"], bordercolor=THEME["bg"], lightcolor=THEME["accent"], darkcolor=THEME["accent"], thickness=4, borderwidth=0)
        style.configure("FocusDeck.Horizontal.TProgressbar", background=THEME["accent"], troughcolor=THEME["border"], bordercolor=THEME["surface"], lightcolor=THEME["accent"], darkcolor=THEME["accent"], thickness=3, borderwidth=0)
        style.configure("Focus.TPanedwindow", background=THEME["bg"], sashwidth=1, sashrelief="flat", handlesize=0, handlepad=0)
        self.option_add("*TCombobox*Listbox.background", THEME["surface"])
        self.option_add("*TCombobox*Listbox.foreground", THEME["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", THEME["accent_dark"])

    def _build_ui(self) -> None:
        # Keep the former layout available only while the Focus Deck is under
        # review. The new experience is the default and Git remains the durable
        # rollback path once the direction is approved.
        if os.environ.get("VODFORGE_LEGACY_UI") != "1":
            self._build_focus_ui()
            return

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
        hero_description = ttk.Label(
            hero,
            text="VOD-ready MP4 downloads with H.264 CBR video, AAC audio, thumbnails, compact metadata, tags, and playlist packaging.",
            style="Muted.TLabel",
        )
        hero_description.pack(anchor="w", pady=(3, 0))
        hero_version = ttk.Label(hero, text=f"Midnight Violet build · v{__version__}", style="Accent.TLabel")
        hero_version.pack(anchor="w", pady=(6, 0))

        def adapt_hero(event: tk.Event[Any]) -> None:
            if event.widget is not self:
                return
            if event.height < 720 and hero_description.winfo_manager():
                hero_description.pack_forget()
            elif event.height >= 720 and not hero_description.winfo_manager():
                hero_description.pack(anchor="w", pady=(3, 0), before=hero_version)

        self.bind("<Configure>", adapt_hero, add="+")

        self.main_notebook = ttk.Notebook(shell)
        self.main_notebook.pack(fill="both", expand=True, padx=4, pady=(8, 4))
        download_tab = ttk.Frame(self.main_notebook, style="Panel.TFrame")
        metadata_tab = ttk.Frame(self.main_notebook, style="Panel.TFrame")
        log_tab = ttk.Frame(self.main_notebook, style="Panel.TFrame")
        self.download_tab = download_tab
        self.metadata_tab = metadata_tab
        self.main_notebook.add(download_tab, text="Download")
        self.main_notebook.add(metadata_tab, text="Metadata Browser")
        self.main_notebook.add(log_tab, text="Log")

        download_tab.columnconfigure(0, weight=1)
        download_tab.rowconfigure(0, weight=1)

        settings = ttk.Frame(download_tab, style="Panel.TFrame")
        settings.grid(row=0, column=0, sticky="nsew", padx=12, pady=(6, 0))
        self._compact_popup: tk.Toplevel | None = None

        def dismiss_compact_popup() -> None:
            popup = self._compact_popup
            self._compact_popup = None
            if popup is not None and popup.winfo_exists():
                popup.destroy()

        def show_compact_popup(
            title: str,
            anchor: ttk.Button,
            builder: Callable[[ttk.LabelFrame], None],
            *,
            minimum_width: int,
        ) -> None:
            dismiss_compact_popup()
            popup = tk.Toplevel(self)
            popup.withdraw()
            self._compact_popup = popup
            popup.title(f"{APP_NAME} · {title}")
            popup.transient(self)
            popup.configure(bg=THEME["bg"])
            popup.resizable(True, True)

            content = ttk.LabelFrame(popup, text=title)
            content.pack(fill="both", expand=True, padx=12, pady=(12, 6))
            builder(content)
            ttk.Button(popup, text="Done", command=dismiss_compact_popup).pack(anchor="e", padx=12, pady=(0, 12))

            popup.update_idletasks()
            screen_width = popup.winfo_screenwidth()
            screen_height = popup.winfo_screenheight()
            popup_width = min(max(minimum_width, popup.winfo_reqwidth()), max(360, screen_width - 40))
            popup_height = min(max(280, popup.winfo_reqheight()), max(320, screen_height - 80))
            popup_x = min(anchor.winfo_rootx(), max(20, screen_width - popup_width - 20))
            popup_y = anchor.winfo_rooty() + anchor.winfo_height() + 6
            if popup_y + popup_height > screen_height - 40:
                popup_y = max(20, anchor.winfo_rooty() - popup_height - 6)
            popup.minsize(popup_width, popup_height)
            reveal_toplevel(popup, f"{popup_width}x{popup_height}+{popup_x}+{popup_y}")
            popup.bind("<Escape>", lambda _event: dismiss_compact_popup())
            popup.protocol("WM_DELETE_WINDOW", dismiss_compact_popup)

        def build_source_details(parent: ttk.LabelFrame | ttk.Frame) -> None:
            batch = ttk.Frame(parent)
            batch.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 6))
            batch.columnconfigure(1, weight=1)
            ttk.Label(batch, text="Batch URL list").grid(row=0, column=0, sticky="w")
            ttk.Label(batch, textvariable=self.url_list_file_var, style="Muted.TLabel").grid(row=0, column=1, sticky="ew", padx=10)
            batch_button = ttk.Button(batch, text="Load URL List…", command=self._load_url_list_file)
            batch_button.grid(row=0, column=2, sticky="e")
            ToolTip(batch_button, "Process a batch of links from a text file, one URL per line.")

            access = ttk.Frame(parent)
            access.grid(row=1, column=0, sticky="ew", padx=10, pady=6)
            access.columnconfigure(1, weight=1)
            ttk.Label(access, text="YouTube access").grid(row=0, column=0, sticky="w", padx=(0, 10))
            access_combo = ttk.Combobox(
                access,
                textvariable=self.cookie_source_var,
                values=COOKIE_SOURCE_OPTIONS,
                state="readonly",
                width=18,
            )
            access_combo.grid(row=0, column=1, sticky="ew")
            ToolTip(access_combo, "Public uses no cookies. Choose cookies.txt or Browser only when YouTube requires sign-in.")

            cookie_file = ttk.Frame(parent)
            cookie_file.grid(row=2, column=0, sticky="ew", padx=10, pady=(4, 8))
            cookie_file.columnconfigure(0, weight=1)
            ttk.Label(cookie_file, textvariable=self.cookie_file_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
            cookie_file_button = ttk.Button(cookie_file, text="Choose cookies.txt…", command=self._load_cookie_file)
            cookie_file_button.grid(row=0, column=1, sticky="e")
            ToolTip(cookie_file_button, "Use an exported YouTube cookies.txt file for content that requires your authorized account.")

            browser_frame = ttk.Frame(parent)
            browser_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(4, 8))
            browser_frame.columnconfigure(1, weight=1)
            ttk.Label(browser_frame, text="Browser profile").grid(row=0, column=0, sticky="w", padx=(0, 10))
            browser_combo = ttk.Combobox(
                browser_frame,
                textvariable=self.cookie_browser_var,
                values=COOKIE_BROWSER_OPTIONS,
                state="readonly",
                width=18,
            )
            browser_combo.grid(row=0, column=1, sticky="ew")
            browser_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_browser_cookie_selected())
            ToolTip(browser_combo, "Read YouTube cookies directly from the selected local browser. VODForge does not save their contents.")
            self._register_cookie_source_frames(cookie_file, browser_frame)
            parent.columnconfigure(0, weight=1)

        self.manual_settings_frames: list[ttk.Frame] = []

        def build_manual_settings(parent: ttk.Frame) -> ttk.LabelFrame:
            frame = ttk.LabelFrame(parent, text="Manual Override Settings")
            ttk.Label(frame, text="Video bitrate (kbps)").grid(row=0, column=0, sticky="w", padx=8, pady=6)
            ttk.Entry(frame, textvariable=self.manual_video_bitrate_var, width=12).grid(row=0, column=1, sticky="ew", padx=8, pady=6)
            self._manual_help_icon(frame, 0, "Target video bitrate for the H.264 encode. Higher = larger file and more CPU time; it cannot add detail beyond the source.")
            ttk.Label(frame, text="Audio bitrate (kbps)").grid(row=1, column=0, sticky="w", padx=8, pady=6)
            ttk.Entry(frame, textvariable=self.manual_audio_bitrate_var, width=12).grid(row=1, column=1, sticky="ew", padx=8, pady=6)
            self._manual_help_icon(frame, 1, "Target AAC audio bitrate. 192 kbps is usually enough; 320 kbps matches the VOD preset but may exceed source quality.")
            ttk.Label(frame, text="Sample rate").grid(row=2, column=0, sticky="w", padx=8, pady=6)
            ttk.Combobox(frame, textvariable=self.manual_sample_rate_var, values=["44100", "48000"], state="readonly", width=10).grid(row=2, column=1, sticky="ew", padx=8, pady=6)
            self._manual_help_icon(frame, 2, "Audio samples per second. Use 48000 for video/streaming; use 44100 only when matching music/audio sources.")
            ttk.Label(frame, text="Channels").grid(row=3, column=0, sticky="w", padx=8, pady=6)
            ttk.Combobox(frame, textvariable=self.manual_channels_var, values=["Mono", "Stereo"], state="readonly", width=10).grid(row=3, column=1, sticky="ew", padx=8, pady=6)
            self._manual_help_icon(frame, 3, "Output audio layout. Stereo is normal for YouTube/VOD; Mono is only for speech-first files or smaller audio.")
            ttk.Label(frame, text="x264 preset").grid(row=4, column=0, sticky="w", padx=8, pady=6)
            ttk.Combobox(frame, textvariable=self.manual_preset_var, values=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower"], state="readonly", width=10).grid(row=4, column=1, sticky="ew", padx=8, pady=6)
            self._manual_help_icon(frame, 4, "Encoder speed/efficiency tradeoff. Ultrafast = quickest but bigger/lower quality; slower = better compression but heavier CPU. Medium is safest.")
            ttk.Label(
                frame,
                text="Codec stays H.264 + AAC; these fields control the encode profile used when Manual Override is selected. x264 preset applies only when NVENC is off.",
                style="Muted.TLabel",
                wraplength=420,
                justify="left",
            ).grid(row=5, column=0, columnspan=2, sticky="w", padx=8, pady=(4, 8))
            frame.columnconfigure(1, weight=1)
            self.manual_settings_frames.append(frame)
            if not hasattr(self, "manual_settings_frame"):
                self.manual_settings_frame = frame
            return frame

        def build_advanced_options(parent: ttk.LabelFrame | ttk.Frame) -> None:
            ttk.Label(parent, text="Extra tags").grid(row=0, column=0, sticky="w", padx=10, pady=4)
            tags_entry = ttk.Entry(parent, textvariable=self.tags_var)
            tags_entry.grid(row=0, column=1, sticky="ew", padx=10, pady=4)
            ToolTip(tags_entry, "Add comma-separated tags to embedded metadata and the compact metadata file when those outputs are enabled.")
            ignore_playlists = ttk.Checkbutton(parent, text="Ignore playlists", variable=self.single_video_only_var)
            ignore_playlists.grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=1)
            ToolTip(ignore_playlists, "When a link includes a playlist, download only the linked video or audio item instead of the full playlist.")
            ttk.Checkbutton(parent, text="Embed thumbnail", variable=self.embed_thumbnail_var).grid(row=2, column=0, sticky="w", padx=10, pady=1)
            ttk.Checkbutton(parent, text="Save thumbnail", variable=self.write_thumbnail_var).grid(row=2, column=1, sticky="w", padx=10, pady=1)
            ttk.Checkbutton(parent, text="Embed metadata", variable=self.embed_metadata_var).grid(row=3, column=0, sticky="w", padx=10, pady=1)
            ttk.Checkbutton(parent, text="Save compact JSON", variable=self.write_info_json_var).grid(row=3, column=1, sticky="w", padx=10, pady=1)
            nvenc_label = "Use NVIDIA NVENC GPU encoding"
            if sys.platform == "darwin":
                nvenc_label = "NVIDIA NVENC (Windows only)"
            nvenc_checkbox = ttk.Checkbutton(parent, text=nvenc_label, variable=self.use_nvenc_var)
            nvenc_checkbox.grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=1)
            if sys.platform == "darwin":
                self.use_nvenc_var.set(False)
                nvenc_checkbox.state(["disabled"])
            manual_frame = build_manual_settings(parent)
            manual_frame.grid(row=5, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 8))
            parent.columnconfigure(1, weight=1)
            self._refresh_manual_settings_visibility()

        url_frame = ttk.LabelFrame(settings, text="Source")
        ttk.Label(url_frame, text="YouTube URL").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(url_frame, textvariable=self.url_var, width=12).grid(row=0, column=1, sticky="ew", padx=10, pady=6)
        self.preview_metadata_button = ttk.Button(url_frame, text="Preview", command=self._fetch_metadata)
        self.preview_metadata_button.grid(row=0, column=2, sticky="e", padx=10, pady=6)
        optional_source = ttk.Frame(url_frame)
        build_source_details(optional_source)
        optional_source_button = ttk.Button(
            url_frame,
            text="Batch & cookies…",
            style="Compact.TButton",
            command=lambda: show_compact_popup("Batch & cookies", optional_source_button, build_source_details, minimum_width=640),
        )
        url_frame.columnconfigure(1, weight=1)

        out_frame = ttk.LabelFrame(settings, text="Destination")
        output_folder_label = ttk.Label(out_frame, text="Output folder")
        output_folder_entry = ttk.Entry(out_frame, textvariable=self.output_var, width=8)
        output_browse_button = ttk.Button(out_frame, text="Browse…", command=self._browse_output)
        out_frame.columnconfigure(0, weight=1)

        options = ttk.LabelFrame(settings, text="Download Options")
        ttk.Label(options, text="Quality ceiling").grid(row=0, column=0, sticky="w", padx=10, pady=4)
        ttk.Combobox(
            options,
            textvariable=self.quality_var,
            values=list(QUALITY_OPTIONS.keys()),
            state="readonly",
            width=16,
        ).grid(row=0, column=1, sticky="ew", padx=10, pady=2)
        ttk.Label(options, text="Output mode").grid(row=1, column=0, sticky="w", padx=10, pady=4)
        export_mode_combo = ttk.Combobox(
            options,
            textvariable=self.export_mode_choice_var,
            values=EXPORT_MODES,
            state="readonly",
            width=22,
        )
        export_mode_combo.grid(row=1, column=1, sticky="ew", padx=10, pady=2)
        advanced_options = ttk.Frame(options)
        build_advanced_options(advanced_options)
        advanced_options_button = ttk.Button(
            options,
            text="More options…",
            style="Compact.TButton",
            command=lambda: show_compact_popup("More options", advanced_options_button, build_advanced_options, minimum_width=560),
        )
        options.columnconfigure(1, weight=1)

        def apply_download_layout() -> None:
            width = max(1, download_tab.winfo_width())
            height = max(1, download_tab.winfo_height())
            layout = download_layout_mode(
                width,
                height,
                manual_override=self.export_mode_var.get() == ExportMode.MANUAL_OVERRIDE.value,
            )
            very_compact = height < 430
            output_folder_label.grid_forget()
            output_folder_entry.grid_forget()
            output_browse_button.grid_forget()
            if very_compact:
                output_folder_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(6, 2))
                output_folder_entry.grid(row=1, column=0, sticky="ew", padx=(10, 5), pady=(2, 6))
                output_browse_button.grid(row=1, column=1, sticky="e", padx=(5, 10), pady=(2, 6))
            else:
                output_folder_label.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 4))
                output_folder_entry.grid(row=1, column=0, sticky="ew", padx=10, pady=4)
                output_browse_button.grid(row=2, column=0, sticky="e", padx=10, pady=(4, 10))
            for column in range(3):
                settings.columnconfigure(column, weight=0, minsize=0)
            for row in range(3):
                settings.rowconfigure(row, weight=0)

            if layout.startswith("wide"):
                settings.columnconfigure(0, weight=4)
                settings.columnconfigure(1, weight=3, minsize=220)
                settings.columnconfigure(2, weight=3)
                settings.rowconfigure(0, weight=1)
                url_frame.grid(row=0, column=0, columnspan=1, sticky="nsew", **pad)
                out_frame.grid(row=0, column=1, columnspan=1, sticky="nsew", **pad)
                options.grid(row=0, column=2, columnspan=1, sticky="nsew", **pad)
            elif layout.endswith("expanded"):
                settings.columnconfigure(0, weight=1)
                settings.rowconfigure(2, weight=1)
                url_frame.grid(row=0, column=0, columnspan=3, sticky="ew", **pad)
                out_frame.grid(row=1, column=0, columnspan=3, sticky="ew", **pad)
                options.grid(row=2, column=0, columnspan=3, sticky="nsew", **pad)
            else:
                settings.columnconfigure(0, weight=5)
                settings.columnconfigure(1, weight=6)
                settings.rowconfigure(0, weight=1)
                settings.rowconfigure(1, weight=1)
                url_frame.grid(row=0, column=0, columnspan=3, sticky="nsew", **pad)
                out_frame.grid(row=1, column=0, columnspan=1, sticky="nsew", **pad)
                options.grid(row=1, column=1, columnspan=2, sticky="nsew", **pad)

            if layout.endswith("expanded"):
                optional_source_button.grid_remove()
                advanced_options_button.grid_remove()
                optional_source.grid(row=1, column=0, columnspan=4, sticky="ew")
                advanced_options.grid(row=2, column=0, columnspan=2, sticky="ew")
                dismiss_compact_popup()
            else:
                optional_source.grid_remove()
                advanced_options.grid_remove()
                optional_source_button.grid(row=1, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 4))
                advanced_options_button.grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 4))

        def export_mode_changed(_event: tk.Event[Any]) -> None:
            self._refresh_manual_settings_visibility()
            apply_download_layout()

        export_mode_combo.bind("<<ComboboxSelected>>", export_mode_changed)
        self._apply_download_layout = apply_download_layout
        download_tab.bind("<Configure>", lambda _event: apply_download_layout(), add="+")

        log_tab.columnconfigure(0, weight=1)
        log_tab.rowconfigure(1, weight=1)
        log_actions = ttk.Frame(log_tab, style="Panel.TFrame")
        log_actions.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 0))
        ttk.Label(log_actions, text="Download and processing activity", style="Accent.TLabel").pack(side="left")
        ttk.Button(log_actions, text="Open Log Folder", command=self._open_log_folder).pack(side="right")
        log_frame = ttk.LabelFrame(log_tab, text="Activity Log")
        log_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=12)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=1, width=1, wrap="word", state="disabled", bg="#050607", fg=THEME["muted"], insertbackground=THEME["text"], relief="flat", padx=10, pady=8, font=FONT_MONO)
        log_scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=log_scrollbar.set)
        self.log.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        log_scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)

        progress = ttk.LabelFrame(download_tab, text="Progress")
        progress.grid(row=1, column=0, sticky="ew", padx=12, pady=(4, 2))
        self.progress_bar = ttk.Progressbar(progress, variable=self.progress_var, maximum=100, mode="determinate")
        self.progress_bar.pack(fill="x", padx=10, pady=(4, 2))
        ttk.Label(progress, textvariable=self.status_var, style="Muted.TLabel").pack(anchor="w", padx=10, pady=(0, 4))

        buttons = ttk.Frame(download_tab, style="Panel.TFrame")
        buttons.grid(row=2, column=0, sticky="ew", padx=12, pady=(2, 6))
        self.download_button = ttk.Button(buttons, text="Download MP4", command=self._start_download, style="Accent.TButton")
        self.download_button.pack(side="left", padx=4)
        self.cancel_button = ttk.Button(buttons, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=6)
        self.skip_video_button = ttk.Button(buttons, text="Skip Item", command=self._skip_video, state="disabled")
        self.skip_video_button.pack(side="left", padx=4)
        ToolTip(self.skip_video_button, "Skip only the current video or audio item. If this source is a playlist, continue with its next item.")
        self.skip_url_button = ttk.Button(buttons, text="Skip Source", command=self._skip_url, state="disabled")
        self.skip_url_button.pack(side="left", padx=4)
        ToolTip(self.skip_url_button, "Skip the rest of this source URL. If a URL list is loaded, continue with its next URL.")
        open_folder_button = ttk.Button(buttons, text="Open Folder", command=self._open_folder)
        open_folder_button.pack(side="right", padx=4)
        view_log_button = ttk.Button(buttons, text="View Log", command=lambda: self.main_notebook.select(log_tab))
        view_log_button.pack(side="right", padx=4)

        def adapt_download_actions(_event: tk.Event[Any] | None = None) -> None:
            compact = buttons.winfo_width() < 900
            view_log_button.configure(text="Log" if compact else "View Log")
            open_folder_button.configure(text="Folder" if compact else "Open Folder")

        buttons.bind("<Configure>", adapt_download_actions, add="+")

        metadata_tab.columnconfigure(0, weight=1)
        metadata_tab.rowconfigure(1, weight=6, minsize=160)
        metadata_tab.rowconfigure(2, weight=5, minsize=160)

        meta_buttons = ttk.Frame(metadata_tab, style="Panel.TFrame")
        meta_buttons.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        metadata_action_buttons = [
            ttk.Button(meta_buttons, text="Copy Tags", command=self._copy_tags),
            ttk.Button(meta_buttons, text="Copy Description", command=self._copy_description),
            ttk.Button(meta_buttons, text="Copy Thumbnail URL", command=self._copy_thumbnail_url),
            ttk.Button(meta_buttons, text="Open Saved Location", command=self._open_selected_saved_location),
            ttk.Button(meta_buttons, text="Back to Download", command=lambda: self.main_notebook.select(download_tab)),
        ]

        metadata_content = ttk.Frame(metadata_tab, style="Panel.TFrame")
        metadata_content.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))

        queue_panel = ttk.Frame(metadata_content, style="Panel.TFrame")
        queue_panel.grid_propagate(False)
        queue_panel.columnconfigure(0, weight=1)
        queue_panel.rowconfigure(1, weight=1)
        ttk.Label(queue_panel, text="Playlist / Video Queue", style="Accent.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 5))
        tree_wrap = ttk.Frame(queue_panel, style="Card.TFrame")
        tree_wrap.grid(row=1, column=0, sticky="nsew")
        tree_wrap.columnconfigure(0, weight=1)
        tree_wrap.rowconfigure(0, weight=1)
        self.video_tree = ttk.Treeview(
            tree_wrap,
            columns=("index", "title", "duration", "creator", "id", "location"),
            show="headings",
            selectmode="browse",
            height=1,
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

        details_panel = ttk.Frame(metadata_content, style="Panel.TFrame")
        details_panel.grid_propagate(False)
        details_panel.columnconfigure(0, weight=1)
        details_panel.rowconfigure(2, weight=2)
        details_panel.rowconfigure(4, weight=3)
        self.selected_title_var = tk.StringVar(value="Fetch metadata to preview long titles, tags, description, and thumbnails.")
        selected_title_label = ttk.Label(details_panel, textvariable=self.selected_title_var, wraplength=360, justify="left", style="Muted.TLabel")
        selected_title_label.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        tags_label = ttk.Label(details_panel, text="Tags", style="Accent.TLabel")
        tags_label.grid(row=1, column=0, sticky="w", pady=(0, 5))
        self.pulled_tags_text = tk.Text(details_panel, height=1, width=1, wrap="word", bg=THEME["surface"], fg=THEME["text"], insertbackground=THEME["text"], relief="flat", padx=10, pady=8, font=FONT_UI)
        self.pulled_tags_text.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        description_label = ttk.Label(details_panel, text="Description", style="Accent.TLabel")
        description_label.grid(row=3, column=0, sticky="w", pady=(0, 5))
        self.description_text = tk.Text(details_panel, height=1, width=1, wrap="word", bg=THEME["surface"], fg=THEME["text"], insertbackground=THEME["text"], relief="flat", padx=10, pady=8, font=FONT_UI)
        self.description_text.grid(row=4, column=0, sticky="nsew")
        details_panel.bind(
            "<Configure>",
            lambda event: selected_title_label.configure(wraplength=max(180, event.width - 12)),
            add="+",
        )

        thumb_box = ttk.Frame(metadata_content, style="Card.TFrame")
        thumb_box.grid_propagate(False)
        thumb_box.pack_propagate(False)
        ttk.Label(thumb_box, text="Thumbnail", style="Accent.TLabel").pack(anchor="w", padx=10, pady=(10, 6))
        self.thumbnail_label = tk.Label(thumb_box, text="No thumbnail loaded", anchor="center", bg=THEME["surface"], fg=THEME["muted"], relief="flat", font=FONT_UI)
        self.thumbnail_label.pack(fill="both", expand=True, padx=10, pady=(0, 10), ipadx=8, ipady=8)

        summary_frame = ttk.LabelFrame(metadata_tab, text="Encoding Summary")
        summary_frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        summary_frame.columnconfigure(0, weight=1)
        summary_frame.columnconfigure(1, weight=1)
        summary_frame.rowconfigure(1, weight=1)
        ttk.Label(summary_frame, text="Source Selected from YouTube", style="Accent.TLabel").grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))
        ttk.Label(summary_frame, text="Final Output File", style="Accent.TLabel").grid(row=0, column=1, sticky="w", padx=10, pady=(8, 4))
        self.source_summary_text = tk.Text(summary_frame, height=1, width=1, wrap="word", state="disabled", bg=THEME["surface"], fg=THEME["text"], insertbackground=THEME["text"], relief="flat", padx=10, pady=8, font=FONT_MONO)
        self.output_summary_text = tk.Text(summary_frame, height=1, width=1, wrap="word", state="disabled", bg=THEME["surface"], fg=THEME["text"], insertbackground=THEME["text"], relief="flat", padx=10, pady=8, font=FONT_MONO)
        self.source_summary_text.grid(row=1, column=0, sticky="nsew", padx=(10, 6), pady=(0, 10))
        self.output_summary_text.grid(row=1, column=1, sticky="nsew", padx=(6, 10), pady=(0, 10))

        def apply_metadata_layout() -> None:
            width = max(1, metadata_content.winfo_width())
            height = max(1, metadata_tab.winfo_height())
            action_width = max(1, meta_buttons.winfo_width())
            for button in metadata_action_buttons:
                button.grid_forget()
                button.configure(style="TButton")
            for column in range(6):
                meta_buttons.columnconfigure(column, weight=0)
            if action_width >= 790:
                for button, label in zip(
                    metadata_action_buttons,
                    ["Copy Tags", "Copy Description", "Copy Thumbnail URL", "Open Saved Location", "Back to Download"],
                ):
                    button.configure(text=label)
                for column, button in enumerate(metadata_action_buttons[:4]):
                    button.grid(row=0, column=column, sticky="w", padx=5)
                meta_buttons.columnconfigure(4, weight=1)
                metadata_action_buttons[4].grid(row=0, column=5, sticky="e", padx=5)
            elif action_width >= 700:
                for button, label in zip(
                    metadata_action_buttons,
                    ["Copy Tags", "Copy Description", "Copy Thumbnail", "Open Folder", "Download"],
                ):
                    button.configure(text=label, style="Compact.TButton")
                for column, button in enumerate(metadata_action_buttons[:4]):
                    button.grid(row=0, column=column, sticky="w", padx=4)
                meta_buttons.columnconfigure(4, weight=1)
                metadata_action_buttons[4].grid(row=0, column=5, sticky="e", padx=4)
            else:
                for button, label in zip(
                    metadata_action_buttons,
                    ["Copy Tags", "Copy Description", "Copy Thumbnail", "Open Folder", "Download"],
                ):
                    button.configure(text=label, style="Compact.TButton")
                for column, button in enumerate(metadata_action_buttons[:3]):
                    button.grid(row=0, column=column, sticky="w", padx=5, pady=(0, 5))
                metadata_action_buttons[3].grid(row=1, column=0, columnspan=2, sticky="w", padx=5)
                meta_buttons.columnconfigure(3, weight=1)
                metadata_action_buttons[4].grid(row=1, column=3, sticky="e", padx=5)

            for column in range(3):
                metadata_content.columnconfigure(column, weight=0, minsize=0, uniform="")
            for row in range(2):
                metadata_content.rowconfigure(row, weight=0, minsize=0)

            if metadata_layout_mode(width) == "three-column":
                metadata_content.columnconfigure(0, weight=5)
                metadata_content.columnconfigure(1, weight=3)
                metadata_content.columnconfigure(2, weight=2)
                metadata_content.rowconfigure(0, weight=1)
                queue_panel.grid(row=0, column=0, rowspan=1, sticky="nsew", padx=(0, 10))
                details_panel.grid(row=0, column=1, rowspan=1, sticky="nsew", padx=(0, 10))
                thumb_box.grid(row=0, column=2, rowspan=1, sticky="nsew")
            else:
                metadata_content.columnconfigure(0, weight=3)
                metadata_content.columnconfigure(1, weight=2, minsize=230)
                metadata_content.rowconfigure(0, weight=3)
                metadata_content.rowconfigure(1, weight=2)
                queue_panel.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 10))
                details_panel.grid(row=0, column=1, rowspan=1, sticky="nsew", pady=(0, 8))
                thumb_box.grid(row=1, column=1, rowspan=1, sticky="nsew")

            compact_height = height < 440
            selected_title_label.grid_forget()
            tags_label.grid_forget()
            self.pulled_tags_text.grid_forget()
            description_label.grid_forget()
            self.description_text.grid_forget()
            for column in range(2):
                details_panel.columnconfigure(column, weight=0, minsize=0, uniform="")
            for row in range(5):
                details_panel.rowconfigure(row, weight=0)
            if compact_height:
                details_panel.columnconfigure(0, weight=1)
                details_panel.rowconfigure(1, weight=1)
                details_panel.rowconfigure(3, weight=1)
                tags_label.grid(row=0, column=0, sticky="w", pady=(0, 2))
                self.pulled_tags_text.grid(row=1, column=0, sticky="nsew", pady=(0, 3))
                description_label.grid(row=2, column=0, sticky="w", pady=(0, 2))
                self.description_text.grid(row=3, column=0, sticky="nsew")
            else:
                details_panel.columnconfigure(0, weight=1)
                details_panel.rowconfigure(2, weight=2)
                details_panel.rowconfigure(4, weight=3)
                selected_title_label.grid(row=0, column=0, sticky="ew", pady=(0, 5))
                tags_label.grid(row=1, column=0, sticky="w", pady=(0, 5))
                self.pulled_tags_text.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
                description_label.grid(row=3, column=0, sticky="w", pady=(0, 5))
                self.description_text.grid(row=4, column=0, sticky="nsew")
            metadata_tab.rowconfigure(1, weight=4 if compact_height else 6, minsize=120 if compact_height else 170)
            metadata_tab.rowconfigure(2, weight=6 if compact_height else 5, minsize=170 if compact_height else 190)

        self._apply_metadata_layout = apply_metadata_layout
        metadata_tab.bind("<Configure>", lambda _event: apply_metadata_layout(), add="+")
        metadata_content.bind("<Configure>", lambda _event: apply_metadata_layout(), add="+")
        meta_buttons.bind("<Configure>", lambda _event: apply_metadata_layout(), add="+")

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
        vector_asset = bundled_asset_path(f"icons/lucide/{name}-{size}-{color_variant}.svg") if color_variant else None
        if sys.platform == "darwin" and vector_asset is not None and vector_asset.is_file():
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
                write_diagnostic(f"native vector icon could not be loaded ({name}): {exc}")
        try:
            exact_asset = bundled_asset_path(f"icons/lucide/{name}-{size}.png")
            icon_asset = exact_asset if exact_asset.is_file() else bundled_asset_path(f"icons/lucide/{name}.png")
            with Image.open(icon_asset) as source:
                icon = render_monochrome_icon(source, size, color)
            rendered = ImageTk.PhotoImage(icon)
        except Exception as exc:
            write_diagnostic(f"in-app icon could not be loaded ({name}): {exc}")
            return None
        cache[key] = rendered
        return rendered

    def _build_focus_ui(self) -> None:
        """Build the flat, command-first VODForge workspace."""
        self._compact_popup = None
        self.manual_settings_frames = []
        self._focus_layout: str | None = None
        self._focus_settings_window: tk.Toplevel | None = None
        self._focus_active_override = False
        self._focus_selected_run_id: str | None = None
        self._focus_log_owner_run_id: str | None = None
        self._focus_log_rendered_text = ""
        self._terminal_jobs: list[DownloadJob] = []
        self._completed_jobs: list[DownloadJob] = []
        self._thumbnail_preview_request_ids = {"active": 0, "library": 0}
        self._focus_icon_images: dict[tuple[str, int, str], Any] = {}

        self.focus_active_title_var = tk.StringVar(value="Ready for a new run")
        self.focus_active_detail_var = tk.StringVar(value="Paste a YouTube URL above, then press Return to begin.")
        self.focus_active_profile_var = tk.StringVar(value=f"{self.quality_var.get()}  •  {self.export_mode_var.get()}")
        self.focus_active_duration_var = tk.StringVar(value="")
        self.focus_percent_var = tk.StringVar(value="0%")
        self.focus_display_progress_var = tk.DoubleVar(value=0)
        self.focus_display_status_var = tk.StringVar(value=self.status_var.get())
        self.focus_run_status_var = tk.StringVar(value="Ready")
        self.focus_transfer_var = tk.StringVar(value="VOD-ready MP4 / H.264 video / AAC audio")
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
                self._focus_brand_image = ImageTk.PhotoImage(icon.resize((34, 34), resampling.LANCZOS))
                self._focus_brand_nav_image = ImageTk.PhotoImage(icon.resize((20, 20), resampling.LANCZOS))
                tile_icon = rounded_contain_image(icon, youtube_thumbnail_size(152), 10, THEME["surface"])
                self._focus_brand_tile_image = ImageTk.PhotoImage(tile_icon)
            except Exception as exc:
                write_diagnostic(f"in-app brand mark could not be loaded: {exc}")
        if self._focus_brand_image is not None:
            ttk.Label(brand, image=self._focus_brand_image, style="TLabel").pack(side="left", padx=(0, 10))
        ttk.Label(brand, text="VODForge", style="FocusBrand.TLabel").pack(side="left")

        utilities = ttk.Frame(header, style="FocusShell.TFrame")
        utilities.grid(row=0, column=2, sticky="e", pady=(0, 8))
        self.focus_update_dot = tk.Canvas(utilities, width=10, height=10, bg=THEME["bg"], bd=0, highlightthickness=0)
        self.focus_update_dot.create_oval(2, 2, 8, 8, fill=THEME["subtle"], outline="", tags="dot")
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
            lambda _event: self._check_for_updates() if str(self.update_button.cget("state")) != "disabled" else None,
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
        self.focus_settings_button.bind("<Button-1>", lambda _event: self._show_focus_settings(), add="+")
        self.focus_settings_button.bind("<Return>", lambda _event: self._show_focus_settings(), add="+")
        self.focus_settings_button.bind("<space>", lambda _event: self._show_focus_settings(), add="+")
        if settings_icon is not None and settings_hover_icon is not None:
            self.focus_settings_button.bind("<Enter>", lambda _event: self.focus_settings_button.configure(image=settings_hover_icon), add="+")
            self.focus_settings_button.bind("<Leave>", lambda _event: self.focus_settings_button.configure(image=settings_icon), add="+")

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
        for view_name, label in (("forge", "Forge"), ("library", "Library"), ("activity", "Activity")):
            item = ttk.Frame(nav, style="FocusShell.TFrame")
            item.pack(side="left", padx=(0, 8))
            inactive_icon, _active_icon = self._focus_nav_icons[view_name]
            button = ttk.Button(
                item,
                text=label,
                image=inactive_icon if inactive_icon is not None else "",
                compound="left",
                style="FocusNav.TButton",
                command=lambda name=view_name: self._select_focus_view(name),
            )
            button.pack(fill="x")
            underline = tk.Frame(item, height=2, bg=THEME["bg"], bd=0, highlightthickness=0)
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

        separator = tk.Frame(shell, bg=THEME["border"], height=1, bd=0, highlightthickness=0)
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
        self._focus_views = {"forge": forge_view, "library": library_view, "activity": activity_view}
        self.download_tab = forge_view
        self.metadata_tab = library_view

        self._build_focus_forge_view(forge_view)
        self._build_focus_library_view(library_view)
        self._build_focus_activity_view(activity_view)

        self.progress_var.trace_add("write", lambda *_args: self._sync_focus_progress())
        self.status_var.trace_add("write", lambda *_args: self._sync_focus_status())
        self.output_var.trace_add("write", lambda *_args: self._sync_focus_destination())
        self.quality_var.trace_add("write", lambda *_args: self._sync_focus_settings_summary())
        self.export_mode_var.trace_add("write", lambda *_args: self._sync_focus_settings_summary())
        self.export_mode_choice_var.trace_add("write", lambda *_args: self._on_export_mode_choice_changed())
        self.output_type_var.trace_add("write", lambda *_args: self._on_output_type_changed())
        self.library_output_type_var.trace_add("write", lambda *_args: self._on_library_output_type_changed())
        self.mp3_quality_var.trace_add("write", lambda *_args: self._sync_focus_settings_summary())
        self.mp3_sample_rate_var.trace_add("write", lambda *_args: self._sync_focus_settings_summary())
        self.mp3_channels_var.trace_add("write", lambda *_args: self._sync_focus_settings_summary())
        self.mp3_cover_art_mode_var.trace_add("write", lambda *_args: self._on_mp3_cover_mode_changed())
        self._sync_focus_destination()
        self._on_output_type_changed()
        self._on_library_output_type_changed()
        self._sync_focus_progress()
        self._select_focus_view("forge")
        self._refresh_focus_run_deck()
        self.bind("<Configure>", self._apply_focus_layout, add="+")
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
        command_inner = tk.Frame(command_box, bg=THEME["surface"], bd=0, highlightthickness=0)
        command_inner.columnconfigure(1, weight=1)
        command_window = command_box.create_window(12, 2, anchor="nw", window=command_inner)
        command_background = command_box.create_image(0, 0, anchor="nw")
        command_box.tag_lower(command_background)
        command_state = {"image": None}

        def redraw_command_box(_event: Any = None) -> None:
            width = max(1, command_box.winfo_width())
            height = max(1, command_box.winfo_height())
            if Image is not None and ImageDraw is not None and ImageTk is not None:
                scale = 4
                surface = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
                ImageDraw.Draw(surface).rounded_rectangle(
                    (0, 0, width * scale - 1, height * scale - 1),
                    radius=min(8, height // 2) * scale,
                    fill=THEME["surface"],
                    outline=THEME["border"],
                    width=scale,
                )
                resampling = getattr(Image, "Resampling", Image)
                surface = surface.resize((width, height), resampling.LANCZOS)
                command_state["image"] = ImageTk.PhotoImage(surface)
                command_box.itemconfigure(command_background, image=command_state["image"])
                command_box.coords(command_background, 0, 0)
                command_box.tag_lower(command_background)
            command_box.coords(command_window, 10, 2)
            command_box.itemconfigure(command_window, width=max(1, width - 20), height=max(1, height - 4))

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
        self.preview_metadata_button = ttk.Button(command_row, text="Preview metadata", command=self._fetch_metadata, style="FocusQuiet.TButton")
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
            image=self._focus_brand_tile_image if self._focus_brand_tile_image is not None else "",
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
        self.focus_active_duration_var.trace_add("write", lambda *_args: self._sync_focus_duration_badge())
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
        ttk.Label(title_block, textvariable=self.focus_active_detail_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(title_block, textvariable=self.focus_active_profile_var, style="FocusProfile.TLabel").grid(row=2, column=0, sticky="w", pady=(5, 0))
        ttk.Label(active, textvariable=self.focus_percent_var, style="FocusPercent.TLabel").grid(row=0, column=2, rowspan=3, sticky="e", padx=(18, 0))

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
        ttk.Label(progress_row, textvariable=self.focus_display_status_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(7, 0))
        self.focus_transfer_label = ttk.Label(progress_row, textvariable=self.focus_transfer_var, style="Muted.TLabel")
        self.focus_transfer_label.grid(row=1, column=1, sticky="e", pady=(7, 0), padx=(12, 0))
        self.cancel_button = ttk.Button(progress_row, text="Cancel", command=self._cancel, state="disabled", style="FocusQuiet.TButton")
        self.cancel_button.grid(row=1, column=2, padx=(14, 6), pady=(5, 0))
        self.skip_video_button = ttk.Button(progress_row, text="Skip item", command=self._skip_video, state="disabled", style="FocusQuiet.TButton")
        self.skip_video_button.grid(row=1, column=3, pady=(5, 0))
        ToolTip(self.skip_video_button, "Skip only the current video or audio item. If this source is a playlist, continue with its next item.")
        self.skip_url_button = ttk.Button(progress_row, text="Skip source", command=self._skip_url, state="disabled", style="FocusQuiet.TButton")
        self.skip_url_button.grid(row=1, column=4, padx=(6, 0), pady=(5, 0))
        ToolTip(self.skip_url_button, "Skip the rest of this source URL. If a URL list is loaded, continue with its next URL.")
        self.focus_compact_run_actions_button = ttk.Button(
            progress_row,
            text="Run actions",
            command=self._show_active_focus_run_actions,
            style="FocusQuiet.TButton",
        )
        self.focus_compact_run_actions_button.grid(row=1, column=2, padx=(14, 0), pady=(5, 0))
        self.focus_compact_run_actions_button.grid_remove()
        self.focus_run_controls = (self.cancel_button, self.skip_video_button, self.skip_url_button)
        self._set_focus_run_controls_visible(False)

        detail_wrap = ttk.Frame(parent, style="FocusShell.TFrame")
        detail_wrap.grid(row=2, column=0, sticky="nsew", padx=70, pady=(0, 12))
        detail_wrap.columnconfigure(0, weight=1)
        detail_wrap.rowconfigure(1, weight=1)
        self.focus_detail_wrap = detail_wrap
        detail_header = ttk.Frame(detail_wrap, style="FocusShell.TFrame")
        detail_header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        detail_header.columnconfigure(0, weight=1)
        ttk.Label(detail_header, text="LIVE ACTIVITY", style="FocusEyebrow.TLabel").grid(row=0, column=0, sticky="w")
        self.focus_details_button = ttk.Button(detail_header, text="Output details", command=self._show_focus_output_details, style="FocusQuiet.TButton")
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
            "Format        MP4\nVideo         H.264\nAudio         AAC\nOutput mode   Auto CBR\nSave to       " + self.output_var.get(),
            disabled=True,
        )

        deck_area = ttk.Frame(parent, style="FocusShell.TFrame")
        deck_area.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 4))
        deck_area.columnconfigure(0, weight=1)
        deck_header = ttk.Frame(deck_area, style="FocusShell.TFrame")
        deck_header.grid(row=0, column=0, sticky="ew", padx=6, pady=(0, 6))
        deck_header.columnconfigure(0, weight=1)
        ttk.Label(deck_header, text="RUN DECK", style="FocusEyebrow.TLabel").grid(row=0, column=0, sticky="w")
        self.focus_run_overflow_button = ttk.Button(deck_header, text="All runs", command=self._show_focus_run_menu, style="FocusQuiet.TButton")
        self.focus_run_overflow_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self.focus_run_overflow_button.bind("<Enter>", lambda _event: self._show_focus_run_menu(), add="+")
        self.focus_run_overflow_button.bind("<Leave>", lambda _event: self._schedule_focus_run_menu_close(), add="+")
        self.focus_deck_header = deck_header

        deck_border = tk.Frame(deck_area, bg=THEME["border"], bd=0, highlightthickness=0)
        deck_border.grid(row=1, column=0, sticky="ew")
        deck = ttk.Frame(deck_border, style="FocusShell.TFrame")
        deck.pack(fill="both", expand=True, padx=1, pady=1)
        self.focus_run_deck = deck

        footer = ttk.Frame(parent, style="FocusShell.TFrame")
        footer.grid(row=4, column=0, sticky="ew", padx=26, pady=(4, 0))
        footer.columnconfigure(1, weight=1)
        ttk.Label(footer, textvariable=self.focus_run_count_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(footer, textvariable=self.focus_engine_var, style="Muted.TLabel").grid(row=0, column=2, sticky="e")

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
        ttk.Label(heading_title, text="Library", style="FocusTitle.TLabel").pack(side="left")
        self.focus_library_output_type_selector = SegmentedSelector(
            heading_title,
            variable=self.library_output_type_var,
            background=THEME["bg"],
            compact=True,
        )
        self.focus_library_output_type_selector.pack(side="left", padx=(14, 0))
        ttk.Label(heading, text="Saved downloads and metadata previews", style="Muted.TLabel").pack(anchor="w", pady=(3, 0))
        action_row = ttk.Frame(actions, style="FocusShell.TFrame")
        action_row.grid(row=0, column=1, sticky="e")
        self.focus_library_copy_buttons = {
            "tags": (ttk.Button(action_row, text="Copy tags", command=self._copy_tags, style="FocusQuiet.TButton"), "Copy tags"),
            "description": (
                ttk.Button(action_row, text="Copy description", command=self._copy_description, style="FocusQuiet.TButton"),
                "Copy description",
            ),
            "thumbnail": (
                ttk.Button(action_row, text="Copy thumbnail URL", command=self._copy_thumbnail_url, style="FocusQuiet.TButton"),
                "Copy thumbnail URL",
            ),
        }
        self._focus_copy_feedback_after_ids: dict[str, str] = {}
        self.focus_library_action_buttons = [
            *(button for button, _label in self.focus_library_copy_buttons.values()),
            ttk.Button(action_row, text="Open saved location", command=self._open_selected_saved_location, style="FocusQuiet.TButton"),
        ]
        for button in self.focus_library_action_buttons:
            button.pack(side="left", padx=(6, 0))
        self.focus_library_details_button = ttk.Button(action_row, text="Selected details", command=self._show_selected_metadata_details, style="FocusQuiet.TButton")
        self.focus_library_menu_button = ttk.Button(action_row, text="Actions", command=self._show_library_actions_menu, style="FocusQuiet.TButton")

        metadata_content = ttk.Frame(parent, style="FocusShell.TFrame")
        metadata_content.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 14))
        # The media table owns the flexible width. Selected Item is a compact
        # inspection rail, not a second equal-width workspace.
        metadata_content.columnconfigure(0, weight=1)
        metadata_content.columnconfigure(1, weight=0, minsize=340)
        metadata_content.rowconfigure(0, weight=1)
        self.focus_metadata_content = metadata_content

        queue_panel = ttk.Frame(metadata_content, style="FocusShell.TFrame")
        queue_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        queue_panel.columnconfigure(0, weight=1)
        queue_panel.rowconfigure(1, weight=1)
        self.focus_library_media_label_var = tk.StringVar(value="MP4 MEDIA")
        ttk.Label(queue_panel, textvariable=self.focus_library_media_label_var, style="FocusEyebrow.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.video_tree = PixelScrollTable(
            queue_panel,
            columns=("index", "title", "duration", "creator", "id", "location", "action"),
            selectmode="browse",
        )
        for column, label in (("index", "#"), ("title", "Title"), ("duration", "Length"), ("creator", "Creator"), ("id", "ID"), ("location", "Saved location"), ("action", "")):
            self.video_tree.heading(column, text=label)
        self.video_tree.column("index", width=44, minwidth=38, stretch=False, anchor="center")
        self.video_tree.column("title", width=420, minwidth=220, stretch=True, anchor="w")
        self.video_tree.column("duration", width=72, minwidth=62, stretch=False, anchor="center")
        self.video_tree.column("creator", width=140, minwidth=90, stretch=False, anchor="w")
        self.video_tree.column("id", width=100, minwidth=72, stretch=False, anchor="w")
        self.video_tree.column("location", width=140, minwidth=90, stretch=False, anchor="w")
        self.video_tree.column("action", width=42, minwidth=42, stretch=False, anchor="center")
        tree_scroll = SleekScrollbar(queue_panel, command=self.video_tree.yview)
        tree_x_scroll = SleekScrollbar(queue_panel, command=self.video_tree.xview, orient="horizontal")
        self.video_tree.configure(yscrollcommand=tree_scroll.set, xscrollcommand=tree_x_scroll.set)
        self.video_tree.grid(row=1, column=0, sticky="nsew")
        tree_scroll.grid(row=1, column=1, sticky="ns", padx=(6, 0))
        tree_x_scroll.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self.video_tree.bind("<<TreeviewSelect>>", self._on_video_selected)
        self.video_tree.bind("<Button-1>", self._on_library_tree_click, add="+")
        self.video_tree.bind("<Button-2>", self._show_library_row_menu)
        self.video_tree.bind("<Button-3>", self._show_library_row_menu)
        self.focus_queue_panel = queue_panel

        details = ttk.Frame(metadata_content, style="FocusShell.TFrame")
        details.grid(row=0, column=1, sticky="nsew")
        details.columnconfigure(0, weight=1)
        self.selected_title_var = tk.StringVar(value="Choose a saved item or preview a URL to inspect its metadata.")
        ttk.Label(details, text="SELECTED ITEM", style="FocusEyebrow.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.focus_selected_title_label = ttk.Label(details, textvariable=self.selected_title_var, wraplength=320, justify="left", style="Muted.TLabel")
        self.focus_selected_title_label.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        details.bind(
            "<Configure>",
            lambda event: self.focus_selected_title_label.configure(wraplength=max(180, event.width - 8)),
            add="+",
        )
        thumbnail_wrap = tk.Frame(details, bg=THEME["bg"], height=youtube_thumbnail_size(196)[1], bd=0, highlightthickness=0)
        thumbnail_wrap.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        thumbnail_wrap.grid_propagate(False)
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
            lambda event: self._render_focus_thumbnail_surfaces(library_width=event.width),
            add="+",
        )
        tags_line = ttk.Frame(details, style="FocusShell.TFrame")
        tags_line.grid(row=3, column=0, sticky="nsew", pady=(0, 6))
        tags_line.columnconfigure(1, weight=1)
        ttk.Label(tags_line, text="TAGS", style="FocusEyebrow.TLabel").grid(row=0, column=0, sticky="nw", padx=(0, 10))
        self.pulled_tags_text = tk.Text(tags_line, height=1, width=1, wrap="word", bg=THEME["bg"], fg=THEME["text"], insertbackground=THEME["text"], relief="flat", bd=0, highlightthickness=0, padx=0, pady=1, font=FONT_UI)
        self.pulled_tags_text.grid(row=0, column=1, sticky="nsew")

        description_line = ttk.Frame(details, style="FocusShell.TFrame")
        description_line.grid(row=4, column=0, sticky="nsew")
        description_line.columnconfigure(1, weight=1)
        ttk.Label(description_line, text="DESCRIPTION", style="FocusEyebrow.TLabel").grid(row=0, column=0, sticky="nw", padx=(0, 10))
        self.description_text = tk.Text(description_line, height=2, width=1, wrap="word", bg=THEME["bg"], fg=THEME["text"], insertbackground=THEME["text"], relief="flat", bd=0, highlightthickness=0, padx=0, pady=1, font=FONT_UI)
        self.description_text.grid(row=0, column=1, sticky="nsew")
        details.rowconfigure(3, weight=1)
        details.rowconfigure(4, weight=2)
        self.focus_library_details = details

        summary = ttk.Frame(parent, style="FocusShell.TFrame")
        summary.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 10))
        summary.columnconfigure(0, weight=1)
        summary.columnconfigure(1, weight=1)
        summary.rowconfigure(1, weight=1)
        ttk.Label(summary, text="SOURCE SELECTED FROM YOUTUBE", style="FocusEyebrow.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=(0, 6))
        ttk.Label(summary, text="FINAL OUTPUT FILE", style="FocusEyebrow.TLabel").grid(row=0, column=1, sticky="w", padx=(10, 0), pady=(0, 6))
        self.source_summary_text = tk.Text(summary, height=8, width=1, wrap="word", state="disabled", bg=THEME["surface"], fg=THEME["text"], insertbackground=THEME["text"], relief="flat", bd=0, highlightthickness=0, padx=12, pady=10, font=FONT_MONO)
        self.output_summary_text = tk.Text(summary, height=8, width=1, wrap="word", state="disabled", bg=THEME["surface"], fg=THEME["text"], insertbackground=THEME["text"], relief="flat", bd=0, highlightthickness=0, padx=12, pady=10, font=FONT_MONO)
        self.source_summary_text.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        self.output_summary_text.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        for text_widget in (
            self.pulled_tags_text,
            self.description_text,
            self.source_summary_text,
            self.output_summary_text,
        ):
            bind_smooth_vertical_wheel(text_widget, mode="pixels")
        self.focus_library_summary = summary

    def _build_focus_activity_view(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        header = ttk.Frame(parent, style="FocusShell.TFrame")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(24, 12))
        header.columnconfigure(0, weight=1)
        title = ttk.Frame(header, style="FocusShell.TFrame")
        title.grid(row=0, column=0, sticky="w")
        ttk.Label(title, text="Activity", style="FocusTitle.TLabel").pack(anchor="w")
        ttk.Label(title, textvariable=self.status_var, style="Muted.TLabel").pack(anchor="w", pady=(3, 0))
        ttk.Button(header, text="Open log folder", command=self._open_log_folder, style="FocusQuiet.TButton").grid(row=0, column=1, sticky="e")
        log_wrap = ttk.Frame(parent, style="FocusShell.TFrame")
        log_wrap.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 10))
        log_wrap.columnconfigure(0, weight=1)
        log_wrap.rowconfigure(1, weight=1)
        ttk.Label(log_wrap, text="PERSISTENT LOCAL DOWNLOAD AND PROCESSING LOG", style="FocusEyebrow.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.log = tk.Text(log_wrap, height=1, width=1, wrap="word", state="disabled", bg=THEME["bg"], fg=THEME["muted"], insertbackground=THEME["text"], relief="flat", bd=0, highlightthickness=0, padx=0, pady=6, font=FONT_MONO)
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
            inactive_icon, active_icon = self._focus_nav_icons.get(view_name, (None, None))
            icon = active_icon if active else inactive_icon
            button.configure(
                style="FocusNavActive.TButton" if active else "FocusNav.TButton",
                image=icon if icon is not None else "",
            )
            underline = self._focus_nav_underlines.get(view_name)
            if underline is not None:
                underline.configure(bg=THEME["accent"] if active else THEME["bg"])
        self._focus_selected_view = name

    def _sync_focus_destination(self) -> None:
        path = self.output_var.get().strip() or "Choose destination"
        max_chars = 34 if self._focus_layout == "compact" else 52
        if len(path) > max_chars:
            path = "..." + path[-(max_chars - 3) :]
        self.focus_output_display_var.set(path)
        if hasattr(self, "focus_summary_text") and self._focus_follows_active_run():
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

    def _register_cookie_source_frames(self, file_frame: ttk.Frame, browser_frame: ttk.Frame) -> None:
        self._cookie_file_frames.append(file_frame)
        self._cookie_browser_frames.append(browser_frame)
        self._on_cookie_source_changed()

    def _on_cookie_source_changed(self) -> None:
        source = self._selected_cookie_source()

        def refresh(frames: list[ttk.Frame], visible: bool) -> list[ttk.Frame]:
            live: list[ttk.Frame] = []
            for frame in frames:
                try:
                    if not frame.winfo_exists():
                        continue
                    if visible:
                        frame.grid()
                    else:
                        frame.grid_remove()
                    live.append(frame)
                except tk.TclError:
                    continue
            return live

        self._cookie_file_frames = refresh(self._cookie_file_frames, source == CookieSource.FILE)
        self._cookie_browser_frames = refresh(self._cookie_browser_frames, source == CookieSource.BROWSER)

    def _on_browser_cookie_selected(self) -> None:
        source = CookieSource.BROWSER if browser_cookie_value(self.cookie_browser_var.get()) else CookieSource.PUBLIC
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
        custom_cover = self.mp3_custom_cover_art_path if cover_mode == "Custom art" else None
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
        if mode == "Custom art" and self.mp3_custom_cover_art_path is None:
            if not self._choose_mp3_custom_cover_art():
                self.mp3_cover_art_mode_var.set("No Art")
                return
        descriptions = {
            "No Art": "No image is embedded in the MP3. VODForge still keeps the YouTube thumbnail privately for Forge and Library.",
            "YouTube art": "Embeds the video's YouTube thumbnail in the MP3 and also uses it inside VODForge.",
            "Custom art": "Embeds your image and uses that same image for this run in Forge and Library.",
        }
        self.mp3_cover_art_description_var.set(descriptions[mode])
        cover_file = getattr(self, "focus_mp3_cover_file_frame", None)
        try:
            if cover_file is not None and cover_file.winfo_exists():
                if mode == "Custom art":
                    cover_file.grid()
                else:
                    cover_file.grid_remove()
        except tk.TclError:
            pass
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
            sample_rate = f"{int(settings.sample_rate) / 1000:g} kHz" if settings.sample_rate else "Source rate"
            return f"MP3  •  {rate}  •  {sample_rate}"
        return f"{quality_label or self.quality_var.get()}  •  {(export_mode or ExportMode(self.export_mode_var.get())).value}"

    def _on_output_type_changed(self) -> None:
        self._sync_focus_settings_summary()
        self._refresh_output_specific_settings()
        if not bool(self.worker and self.worker.is_alive()):
            output_type = self._selected_output_type()
            if output_type == OutputType.MP3:
                self.focus_transfer_var.set("Audio-only MP3  /  best YouTube audio source")
            else:
                self.focus_transfer_var.set("VOD-ready MP4 / H.264 video / AAC audio")

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
            self.focus_library_media_label_var.set("MP4 MEDIA" if output_type == OutputType.MP4 else "MP3 AUDIO")
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
        if not bool(self.worker and self.worker.is_alive()):
            self.focus_active_profile_var.set(self._focus_profile_text(output_type))
            if not self.focus_active_detail_var.get().strip():
                self.focus_active_detail_var.set("Ready")

    def _refresh_output_specific_settings(self) -> None:
        output_type = self._selected_output_type()
        mp4_frame = getattr(self, "focus_mp4_settings_frame", None)
        mp3_frame = getattr(self, "focus_mp3_settings_frame", None)
        try:
            if mp4_frame is not None and mp4_frame.winfo_exists():
                if output_type == OutputType.MP4:
                    mp4_frame.grid()
                else:
                    mp4_frame.grid_remove()
            if mp3_frame is not None and mp3_frame.winfo_exists():
                if output_type == OutputType.MP3:
                    mp3_frame.grid()
                else:
                    mp3_frame.grid_remove()
        except tk.TclError:
            pass
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
        return selected_run_id is None or (
            active_job is not None and selected_run_id == active_job.run_id
        )

    def _reset_source_input_after_send(self) -> None:
        """Prepare the source field for the next run after a job is accepted."""
        self.batch_urls = []
        self.url_list_file_var.set("No URL list loaded")
        self.url_var.set("")
        source_entry = self.__dict__.get("focus_url_entry") or self.__dict__.get("url_entry")
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
            self.events.put(("cloud_seen_result", {"success": success, "install_id": state.install_id}))

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
            self.events.put(("first_launch_result", {"success": success, "install_id": state.install_id}))

        self._first_launch_worker = threading.Thread(target=worker, daemon=True)
        self._first_launch_worker.start()

    def _open_cloud_early_access(self) -> None:
        state = self.installation_state
        destination = cloud_page_url(state.install_id if state is not None else None)
        if state is not None:
            threading.Thread(target=record_cloud_click, args=(state,), daemon=True).start()
        try:
            opened = webbrowser.open(destination)
            if not opened:
                write_diagnostic("Cloud early-access page was handed to the OS but no browser confirmed opening")
        except Exception as exc:
            write_diagnostic(f"Cloud early-access page could not be opened: {exc}")

    def _show_focus_settings(self) -> None:
        existing = self._focus_settings_window
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    existing.focus_force()
                    return
            except tk.TclError:
                pass

        popup = tk.Toplevel(self)
        popup.withdraw()
        self._focus_settings_window = popup
        popup.title(f"{APP_NAME} Settings")
        popup.transient(self)
        popup.configure(bg=THEME["bg"])
        popup.resizable(True, True)
        popup.minsize(700, 540)

        root = ttk.Frame(popup, style="FocusShell.TFrame")
        root.pack(fill="both", expand=True, padx=22, pady=20)
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(2, weight=1)

        def bind_readonly_combo(
            combo: ttk.Combobox,
            command: Callable[[], None] | None = None,
        ) -> None:
            """Run the selection action without leaving native entry text selected."""

            def selected(_event: tk.Event[Any]) -> None:
                if command is not None:
                    command()

                def release_selection() -> None:
                    try:
                        combo.selection_clear()
                        popup.focus_set()
                    except tk.TclError:
                        return

                popup.after_idle(release_selection)

            combo.bind("<<ComboboxSelected>>", selected, add="+")

        heading = ttk.Frame(root, style="FocusShell.TFrame")
        heading.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 16))
        heading.columnconfigure(0, weight=1)
        ttk.Label(heading, text="Forge settings", style="FocusTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(heading, text="Every option is available here; the main workspace stays focused.", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(3, 0))

        source = ttk.Frame(root, style="FocusShell.TFrame")
        source.grid(row=1, column=0, sticky="nsew", padx=(0, 16))
        source.columnconfigure(0, weight=1)
        ttk.Label(source, text="SAVE LOCATION", style="FocusEyebrow.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 7))
        destination = ttk.Frame(source, style="FocusShell.TFrame")
        destination.grid(row=1, column=0, sticky="ew")
        destination.columnconfigure(0, weight=1)
        ttk.Entry(destination, textvariable=self.output_var).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(destination, text="Browse", command=self._browse_output, style="FocusQuiet.TButton").grid(row=0, column=1, sticky="e")

        ttk.Label(source, text="BATCH AND PLAYLISTS", style="FocusEyebrow.TLabel").grid(row=2, column=0, sticky="w", pady=(16, 7))
        batch_button = ttk.Button(source, text="Load URL list", command=self._load_url_list_file, style="FocusQuiet.TButton")
        batch_button.grid(row=3, column=0, sticky="w")
        ToolTip(batch_button, "Process a batch of links from a text file, one URL per line.")
        self.focus_batch_url_list_button = batch_button
        ttk.Label(source, textvariable=self.url_list_file_var, style="Muted.TLabel", wraplength=300).grid(row=4, column=0, sticky="w", pady=(4, 6))
        ignore_playlists = ttk.Checkbutton(source, text="Ignore playlists", variable=self.single_video_only_var)
        ignore_playlists.grid(row=5, column=0, sticky="w")
        ToolTip(ignore_playlists, "When a link includes a playlist, download only the linked video or audio item instead of the full playlist.")
        self.focus_ignore_playlists_button = ignore_playlists

        ttk.Label(source, text="YOUTUBE ACCESS", style="FocusEyebrow.TLabel").grid(row=6, column=0, sticky="w", pady=(16, 5))
        ttk.Label(
            source,
            text="Optional — use an authorized account only when public access is not enough.",
            style="Muted.TLabel",
            wraplength=300,
            justify="left",
        ).grid(row=7, column=0, sticky="w", pady=(0, 7))
        cookie_selector = SegmentedSelector(
            source,
            variable=self.cookie_source_var,
            values=COOKIE_SOURCE_OPTIONS,
            background=THEME["bg"],
            compact=True,
        )
        cookie_selector.grid(row=8, column=0, sticky="w")
        ToolTip(cookie_selector, "Public uses no cookies. Choose cookies.txt or Browser only when YouTube requires sign-in.")
        self.focus_cookie_source_selector = cookie_selector

        cookie_file = ttk.Frame(source, style="FocusShell.TFrame")
        cookie_file.grid(row=9, column=0, sticky="ew", pady=(7, 0))
        cookie_file.columnconfigure(0, weight=1)
        ttk.Label(cookie_file, textvariable=self.cookie_file_var, style="Muted.TLabel", wraplength=180).grid(row=0, column=0, sticky="w")
        cookie_file_button = ttk.Button(cookie_file, text="Choose cookies.txt", command=self._load_cookie_file, style="FocusQuiet.TButton")
        cookie_file_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
        ToolTip(cookie_file_button, "Use an exported YouTube cookies.txt file for content that requires your authorized account.")

        browser_frame = ttk.Frame(source, style="FocusShell.TFrame")
        browser_frame.grid(row=9, column=0, sticky="ew", pady=(7, 0))
        browser_frame.columnconfigure(0, weight=1)
        browser_combo = ttk.Combobox(
            browser_frame,
            textvariable=self.cookie_browser_var,
            values=COOKIE_BROWSER_OPTIONS,
            state="readonly",
            width=24,
        )
        browser_combo.grid(row=0, column=0, sticky="ew")
        bind_readonly_combo(browser_combo, self._on_browser_cookie_selected)
        ToolTip(browser_combo, "Read YouTube cookies directly from the selected local browser. VODForge does not save their contents.")
        self._register_cookie_source_frames(cookie_file, browser_frame)

        ttk.Label(source, text="METADATA", style="FocusEyebrow.TLabel").grid(row=10, column=0, sticky="w", pady=(16, 5))
        ttk.Label(source, text="Extra tags (comma-separated)", style="Muted.TLabel").grid(row=11, column=0, sticky="w", pady=(0, 3))
        tags_entry = ttk.Entry(source, textvariable=self.tags_var)
        tags_entry.grid(row=12, column=0, sticky="ew")
        ToolTip(tags_entry, "Add tags to embedded metadata and the compact metadata file when those outputs are enabled.")
        self.focus_tags_entry = tags_entry

        mp4_output = ttk.Frame(root, style="FocusShell.TFrame")
        mp4_output.grid(row=1, column=1, sticky="nsew", padx=(16, 0))
        mp4_output.columnconfigure(1, weight=1)
        ttk.Label(mp4_output, text="MP4 VIDEO", style="FocusEyebrow.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(mp4_output, text="Quality ceiling", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        quality_combo = ttk.Combobox(mp4_output, textvariable=self.quality_var, values=list(QUALITY_OPTIONS.keys()), state="readonly", width=20)
        quality_combo.grid(row=1, column=1, sticky="ew", pady=4)
        bind_readonly_combo(quality_combo)
        ToolTip(quality_combo, "Set the highest resolution VODForge may select from the available YouTube source formats.")
        ttk.Label(mp4_output, text="Output mode", style="Muted.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        export_combo = ttk.Combobox(mp4_output, textvariable=self.export_mode_choice_var, values=EXPORT_MODES, state="readonly", width=24)
        export_combo.grid(row=2, column=1, sticky="ew", pady=4)
        bind_readonly_combo(export_combo, self._refresh_manual_settings_visibility)
        ttk.Label(
            mp4_output,
            textvariable=self.export_mode_description_var,
            style="Muted.TLabel",
            wraplength=360,
            justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 8))
        manual = ttk.Frame(mp4_output, style="FocusShell.TFrame")
        manual.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(3, 8))
        manual.columnconfigure(0, weight=1, uniform="manual-field")
        manual.columnconfigure(1, weight=1, uniform="manual-field")
        manual_fields = (
            ("Video bitrate (kbps)", self.manual_video_bitrate_var, None),
            ("Audio bitrate (kbps)", self.manual_audio_bitrate_var, None),
            ("Sample rate", self.manual_sample_rate_var, ["44100", "48000"]),
            ("Channels", self.manual_channels_var, ["Mono", "Stereo"]),
            ("Encoding speed", self.manual_preset_var, ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower"]),
        )
        for index, (label, variable, values) in enumerate(manual_fields):
            field = ttk.Frame(manual, style="FocusShell.TFrame")
            field.grid(
                row=index // 2,
                column=index % 2,
                sticky="ew",
                padx=(0, 8) if index % 2 == 0 else (8, 0),
                pady=(0, 7),
            )
            field.columnconfigure(0, weight=1)
            ttk.Label(field, text=label, style="Muted.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 3))
            if values is None:
                widget: ttk.Entry | ttk.Combobox = ttk.Entry(field, textvariable=variable)
            else:
                widget = ttk.Combobox(field, textvariable=variable, values=values, state="readonly", width=12)
                bind_readonly_combo(widget)
            widget.grid(row=1, column=0, sticky="ew")
        self.manual_settings_frames = [manual]
        self.manual_settings_frame = manual

        ttk.Checkbutton(mp4_output, text="Save thumbnail", variable=self.write_thumbnail_var).grid(row=5, column=0, sticky="w", pady=2)
        ttk.Checkbutton(mp4_output, text="Save compact JSON", variable=self.write_info_json_var).grid(row=5, column=1, sticky="w", pady=2)
        ttk.Checkbutton(mp4_output, text="Embed thumbnail", variable=self.embed_thumbnail_var).grid(row=6, column=0, sticky="w", pady=2)
        ttk.Checkbutton(mp4_output, text="Embed metadata", variable=self.embed_metadata_var).grid(row=6, column=1, sticky="w", pady=2)
        nvenc_label = "Use NVIDIA NVENC GPU encoding"
        if sys.platform == "darwin":
            nvenc_label = "NVIDIA NVENC (Windows only)"
            self.use_nvenc_var.set(False)
        nvenc = ttk.Checkbutton(mp4_output, text=nvenc_label, variable=self.use_nvenc_var)
        nvenc.grid(row=7, column=0, columnspan=2, sticky="w", pady=2)
        ToolTip(nvenc, "Use a supported NVIDIA GPU for MP4 encoding on Windows. CPU encoding remains the compatibility default.")
        if sys.platform == "darwin":
            nvenc.state(["disabled"])

        mp3_output = ttk.Frame(root, style="FocusShell.TFrame")
        mp3_output.grid(row=1, column=1, sticky="nsew", padx=(16, 0))
        mp3_output.columnconfigure(1, weight=1)
        ttk.Label(mp3_output, text="MP3 AUDIO", style="FocusEyebrow.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(mp3_output, text="Encoding quality", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        mp3_quality_combo = ttk.Combobox(mp3_output, textvariable=self.mp3_quality_var, values=list(MP3_QUALITY_OPTIONS.keys()), state="readonly", width=24)
        mp3_quality_combo.grid(row=1, column=1, sticky="ew", pady=4)
        bind_readonly_combo(mp3_quality_combo)
        ToolTip(mp3_quality_combo, "Set the MP3 export bitrate. Higher settings reduce additional encoding loss but cannot restore detail missing from YouTube's source audio.")
        ttk.Label(mp3_output, text="Sample rate", style="Muted.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        sample_rate_combo = ttk.Combobox(mp3_output, textvariable=self.mp3_sample_rate_var, values=list(MP3_SAMPLE_RATE_OPTIONS.keys()), state="readonly", width=24)
        sample_rate_combo.grid(row=2, column=1, sticky="ew", pady=4)
        bind_readonly_combo(sample_rate_combo)
        ToolTip(sample_rate_combo, "Preserve source avoids unnecessary resampling. Choose 44.1 or 48 kHz only when a music or DAW workflow requires it.")
        ttk.Label(mp3_output, text="Channels", style="Muted.TLabel").grid(row=3, column=0, sticky="w", pady=4)
        channels_combo = ttk.Combobox(mp3_output, textvariable=self.mp3_channels_var, values=list(MP3_CHANNEL_OPTIONS.keys()), state="readonly", width=24)
        channels_combo.grid(row=3, column=1, sticky="ew", pady=4)
        bind_readonly_combo(channels_combo)
        ToolTip(channels_combo, "Preserve the source channel layout, or force Stereo or Mono for a specific production workflow.")
        mp3_metadata = ttk.Checkbutton(mp3_output, text="Embed title, artist, and tags", variable=self.mp3_embed_metadata_var)
        mp3_metadata.grid(row=4, column=0, columnspan=2, sticky="w", pady=(5, 2))
        ToolTip(mp3_metadata, "Write standard ID3 title, artist, and tag information into the MP3 file.")
        ttk.Label(mp3_output, text="Cover art", style="Muted.TLabel").grid(row=5, column=0, sticky="w", pady=(8, 4))
        cover_selector = SegmentedSelector(
            mp3_output,
            variable=self.mp3_cover_art_mode_var,
            values=MP3_COVER_ART_OPTIONS,
            background=THEME["bg"],
            compact=True,
        )
        cover_selector.grid(row=5, column=1, sticky="w", pady=(8, 4))
        ToolTip(cover_selector, "No Art leaves the MP3 unembedded. YouTube art or Custom art writes a front-cover image into the file.")
        ttk.Label(
            mp3_output,
            textvariable=self.mp3_cover_art_description_var,
            style="Muted.TLabel",
            wraplength=330,
            justify="left",
        ).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(3, 0))
        cover_file = ttk.Frame(mp3_output, style="FocusShell.TFrame")
        cover_file.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        cover_file.columnconfigure(0, weight=1)
        ttk.Label(cover_file, textvariable=self.mp3_custom_cover_art_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(cover_file, text="Replace image", command=self._choose_mp3_custom_cover_art, style="FocusQuiet.TButton").grid(row=0, column=1, padx=(8, 0))
        ttk.Button(cover_file, text="Clear", command=self._clear_mp3_custom_cover_art, style="FocusQuiet.TButton").grid(row=0, column=2, padx=(6, 0))
        ttk.Label(
            mp3_output,
            text="Maximum 320 kbps minimizes additional encoding loss. Preserve source avoids unnecessary resampling; choose 44.1 or 48 kHz only when your music or DAW workflow requires it.",
            style="Muted.TLabel",
            wraplength=330,
            justify="left",
        ).grid(row=8, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.focus_mp4_settings_frame = mp4_output
        self.focus_mp3_settings_frame = mp3_output
        self.focus_mp3_cover_file_frame = cover_file
        self._on_mp3_cover_mode_changed()

        self._refresh_output_specific_settings()

        cloud = ttk.Frame(root, style="CloudPreview.TFrame", padding=(14, 10))
        cloud.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        cloud.columnconfigure(0, weight=1)
        ttk.Label(cloud, text="VODForge Cloud", style="CloudTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            cloud,
            text="Run downloads even when this computer is offline.",
            style="FocusSurfaceMuted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        cloud_action = ttk.Frame(cloud, style="FocusSurface.TFrame")
        cloud_action.grid(row=0, column=1, rowspan=2, sticky="e", padx=(18, 0))
        ttk.Label(cloud_action, text="EARLY ACCESS", style="CloudBadge.TLabel").pack(anchor="e", pady=(0, 4))
        self.focus_cloud_early_access_button = ttk.Button(
            cloud_action,
            text="Join early access",
            command=self._open_cloud_early_access,
            style="FocusQuiet.TButton",
        )
        self.focus_cloud_early_access_button.pack(anchor="e")
        ToolTip(self.focus_cloud_early_access_button, "Open the VODForge Cloud early-access signup page in your browser.")

        footer = ttk.Frame(root, style="FocusShell.TFrame")
        footer.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        footer.columnconfigure(0, weight=1)
        preview_button = ttk.Button(footer, text="Preview metadata", command=self._fetch_metadata, style="FocusQuiet.TButton")
        preview_button.grid(row=0, column=0, sticky="w")

        def close_popup() -> None:
            self._focus_settings_window = None
            self.focus_mp4_settings_frame = None
            self.focus_mp3_settings_frame = None
            self.focus_mp3_cover_file_frame = None
            self.focus_batch_url_list_button = None
            self.focus_ignore_playlists_button = None
            self.focus_cookie_source_selector = None
            self.focus_tags_entry = None
            popup.destroy()

        ttk.Button(footer, text="Done", command=close_popup, style="Accent.TButton").grid(row=0, column=1, sticky="e")
        popup.protocol("WM_DELETE_WINDOW", close_popup)
        popup.bind("<Escape>", lambda _event: close_popup())
        popup.update_idletasks()
        width = min(820, max(700, popup.winfo_reqwidth()))
        height = min(720, max(560, popup.winfo_reqheight()))
        reveal_toplevel(popup, centered_toplevel_geometry(self, width, height))
        self.after_idle(self._record_cloud_cta_seen)

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
        ttk.Label(frame, text="Output details", style="FocusTitle.TLabel").pack(anchor="w")
        text = tk.Text(frame, height=10, width=52, wrap="word", state="normal", bg=THEME["surface"], fg=THEME["text"], insertbackground=THEME["text"], relief="flat", bd=0, highlightthickness=0, padx=12, pady=10, font=FONT_MONO)
        text.pack(fill="both", expand=True, pady=(12, 12))
        text.insert("1.0", self.focus_summary_text.get("1.0", "end").strip())
        text.configure(state="disabled")
        bind_smooth_vertical_wheel(text, mode="pixels")
        ttk.Button(frame, text="Done", command=popup.destroy, style="Accent.TButton").pack(anchor="e")
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
                inside_popup = hovered_path == str(popup) or hovered_path.startswith(f"{popup}.")
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

        selected_index = -1
        selected_run_id = str(self._focus_selected_run_id or "").strip()
        row_rectangles: list[int] = []
        if records:
            for index, record in enumerate(records):
                title = str(record.get("title") or "Untitled run")
                status = str(record.get("status") or "Ready")
                record_run_id = str(record.get("run_id") or "").strip()
                if selected_run_id and record_run_id == selected_run_id:
                    selected_index = index
                row_tag = f"run-row-{index}"
                top = index * row_height
                rectangle = run_list.create_rectangle(
                    0,
                    top,
                    1,
                    top + row_height - 1,
                    fill=THEME["accent_dark"] if index == selected_index else THEME["surface"],
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
                    lambda _event, item=record: choose_run(item),
                )

                def show_hover(_event: Any, *, item_index: int = index, item_rectangle: int = rectangle) -> None:
                    if item_index != selected_index:
                        run_list.itemconfigure(item_rectangle, fill=THEME["surface_2"])

                def hide_hover(_event: Any, *, item_index: int = index, item_rectangle: int = rectangle) -> None:
                    fill = THEME["accent_dark"] if item_index == selected_index else THEME["surface"]
                    run_list.itemconfigure(item_rectangle, fill=fill)

                run_list.tag_bind(row_tag, "<Enter>", show_hover)
                run_list.tag_bind(row_tag, "<Leave>", hide_hover)
        else:
            run_list.create_text(10, row_height / 2, text="No runs yet", anchor="w", fill=THEME["muted"], font=FONT_UI)

        run_list.configure(scrollregion=(0, 0, 1, max(row_height, len(records) * row_height)))

        def resize_rows(event: tk.Event[Any]) -> None:
            for index, rectangle in enumerate(row_rectangles):
                top = index * row_height
                run_list.coords(rectangle, 0, top, max(1, event.width), top + row_height - 1)
            run_list.configure(scrollregion=(0, 0, max(1, event.width), max(row_height, len(records) * row_height)))

        run_list.bind("<Configure>", resize_rows, add="+")

        def close_drop_up() -> None:
            self._cancel_focus_run_menu_close()
            if self.__dict__.get("_focus_run_list_cleanup") is close_drop_up:
                self._focus_run_list_cleanup = None
            self._focus_run_list_window = None
            try:
                popup.destroy()
            except tk.TclError:
                pass

        self._focus_run_list_cleanup = close_drop_up

        def choose_run(record: dict[str, Any]) -> None:
            self._focus_select_run_record(record)
            close_drop_up()

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
        popup.bind("<Enter>", lambda _event: self._cancel_focus_run_menu_close(), add="+")
        popup.bind("<Leave>", lambda _event: self._schedule_focus_run_menu_close(), add="+")

        button = self.focus_run_overflow_button
        button.update_idletasks()
        popup.update_idletasks()
        width = min(440, max(340, self.winfo_width() - 48))
        height = min(184, max(78, popup.winfo_reqheight()))
        x = button.winfo_rootx() - self.winfo_rootx() + button.winfo_width() - width
        x = min(self.winfo_width() - width - 12, max(12, x))
        y = button.winfo_rooty() - self.winfo_rooty() - height - 6
        if y < 20:
            y = min(
                self.winfo_height() - height - 20,
                button.winfo_rooty() - self.winfo_rooty() + button.winfo_height() + 6,
            )
        popup.place(x=x, y=y, width=width, height=height)
        popup.lift()
        run_list.focus_set()

    def _focus_select_run_record(self, record: dict[str, Any]) -> None:
        run_id = str(record.get("run_id") or "")
        self._focus_selected_run_id = run_id or None
        if str(record.get("kind")) == "active":
            active_job = self.active_job
            if active_job is not None and (not run_id or run_id == active_job.run_id):
                self._display_focus_job_snapshot(active_job)
            return

        if str(record.get("kind")) == "queued":
            queued_job = next((job for job in self.pending_jobs if job.run_id == run_id), None)
            if queued_job is not None:
                self._display_focus_queued_job_snapshot(record, queued_job)
            return

        if record.get("metadata_index") is not None:
            index = int(record["metadata_index"])
            if 0 <= index < len(self.metadata_items):
                self._display_focus_metadata_snapshot(record, self.metadata_items[index])

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
                if bool(getattr(widget, "_vodforge_user_scroll_locked", False)) or last < 0.995:
                    widget.yview_moveto(first)
                else:
                    widget.see("end")
            except (AttributeError, TypeError, ValueError, tk.TclError):
                pass
        else:
            setattr(widget, "_vodforge_user_scroll_locked", False)
            try:
                widget.yview_moveto(0.0)
            except (AttributeError, TypeError, ValueError, tk.TclError):
                pass

    def _display_focus_queued_job_snapshot(self, record: dict[str, Any], job: DownloadJob) -> None:
        """Render one queued run without borrowing state from the active run."""
        self._focus_selected_run_id = job.run_id
        info = job.preview_info or {}
        title = download_job_display_title(job, queued=True)
        creator = str(info.get("uploader") or info.get("channel") or "Waiting for source metadata")
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
            sample_rate = (
                "Preserve source"
                if job.mp3_settings.sample_rate is None
                else f"{job.mp3_settings.sample_rate // 1000} kHz"
            )
            channels = "Preserve source" if job.mp3_settings.channels is None else str(job.mp3_settings.channels)
            summary = "\n".join(
                (
                    "Format          MP3",
                    f"Audio quality   {job.mp3_settings.audio_bitrate_kbps} kbps",
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
            "\n".join(job.activity_lines) or "Queued. This run will begin after the current run finishes.",
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
            self.video_tree.focus(iid)
        self._display_selected_metadata(index)

    def _display_focus_job_snapshot(self, job: DownloadJob) -> None:
        self._focus_selected_run_id = job.run_id
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
            else "Active MP4 run  /  H.264 video and AAC audio"
        )
        self._render_focus_run_activity(
            job.run_id,
            "\n".join(job.activity_lines) or "Preparing this run…",
        )

    def _display_focus_metadata_snapshot(self, record: dict[str, Any], info: dict[str, Any]) -> None:
        title = str(info.get("title") or info.get("id") or record.get("title") or "Untitled run")
        creator = str(info.get("uploader") or info.get("channel") or record.get("detail") or "Unknown creator")
        output_type = metadata_output_type(info)
        self.focus_active_title_var.set(title)
        self.focus_active_detail_var.set(creator)
        duration = format_duration(info.get("duration"))
        self.focus_active_duration_var.set("" if duration == "—" else duration)
        summary = info.get("vodforge_encoding_summary") if isinstance(info.get("vodforge_encoding_summary"), dict) else {}
        output = summary.get("output") if isinstance(summary.get("output"), dict) else {}
        resolution = _display_value(output.get("Resolution"), "Audio only" if output_type == OutputType.MP3 else "MP4")
        mode = _display_value(
            output.get("Output rate-control mode"),
            _display_value(output.get("Target audio bitrate"), "Completed"),
        )
        self.focus_active_profile_var.set(f"{output_type.value}  •  {resolution}  •  {mode}")
        record_kind = str(record.get("kind") or "completed")
        terminal_status = str(info.get("vodforge_terminal_status") or record_kind.title())
        if record_kind == "completed":
            self.focus_display_progress_var.set(100)
            self.focus_percent_var.set("100%")
            self.focus_display_status_var.set(f"Showing completed run: {title}")
            self.focus_transfer_var.set("Complete  /  Ready to open in Library")
        else:
            self.focus_display_progress_var.set(0)
            self.focus_percent_var.set(terminal_status)
            self.focus_display_status_var.set(f"Showing {terminal_status.lower()} run: {title}")
            self.focus_transfer_var.set(f"{terminal_status}  /  Retry is available")
        _source_summary, output_summary = build_encoding_summary_display(info)
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

    def _display_focus_record_thumbnail(self, record: dict[str, Any], info: dict[str, Any]) -> None:
        preview_thumbnail = str(info.get("preview_thumbnail_path") or "").strip()
        candidates = [Path(preview_thumbnail)] if preview_thumbnail else []
        saved = history_output_dir(info)
        if saved is not None:
            candidates.extend(
                saved / name
                for name in ("thumbnail.jpg", "thumbnail.jpeg", "thumbnail.png", "thumbnail.webp")
            )
        cached = cached_thumbnail_path(info)
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
            self._render_focus_thumbnail_surfaces(direct_image, placeholder=False, target="active")
            return
        thumbnail = best_thumbnail(info)
        thumbnail_url = str((thumbnail or {}).get("url") or "").strip()
        if thumbnail_url:
            self._reset_active_thumbnail()
            self._load_thumbnail_preview(thumbnail_url, target="active", owner_run_id=str(record.get("run_id") or ""))
            return
        self._reset_active_thumbnail()

    def _show_library_actions_menu(self) -> None:
        menu = tk.Menu(self, tearoff=False, bg=THEME["surface"], fg=THEME["text"], activebackground=THEME["accent_dark"], activeforeground="#ffffff")
        selection = self.video_tree.selection()
        selected_info = None
        if selection:
            try:
                selected_info = self.metadata_items[int(selection[0])]
            except (IndexError, TypeError, ValueError):
                selected_info = None
        terminal_job = self._terminal_job_for_metadata(selected_info) if isinstance(selected_info, dict) else None
        if terminal_job is not None:
            menu.add_command(label="↻ Retry in Forge", command=lambda: self._retry_terminal_job(terminal_job))
            menu.add_separator()
        menu.add_command(label="Copy tags", command=self._copy_tags)
        menu.add_command(label="Copy description", command=self._copy_description)
        menu.add_command(label="Copy thumbnail URL", command=self._copy_thumbnail_url)
        menu.add_separator()
        menu.add_command(label="Open saved location", command=self._open_selected_saved_location)
        menu.add_command(label="Remove from Library…", command=self._remove_selected_library_item)
        try:
            menu.tk_popup(self.focus_library_menu_button.winfo_rootx(), self.focus_library_menu_button.winfo_rooty() + self.focus_library_menu_button.winfo_height())
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
        ttk.Label(root, text=title, style="FocusTitle.TLabel", wraplength=600, justify="left").grid(row=0, column=0, sticky="ew")
        ttk.Label(root, text=f"{creator}  /  {format_duration(info.get('duration'))}  /  {info.get('id') or 'no ID'}", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(5, 12))
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
            preview.image = image
        ttk.Label(root, text="TAGS", style="FocusEyebrow.TLabel").grid(row=3, column=0, sticky="w", pady=(0, 4))
        tags = tk.Text(root, height=3, width=1, wrap="word", bg=THEME["surface"], fg=THEME["text"], relief="flat", bd=0, highlightthickness=0, padx=10, pady=8, font=FONT_UI)
        tags.grid(row=4, column=0, sticky="nsew", pady=(0, 10))
        tags.insert("1.0", build_tags_display_text(info) or "No tags found for this video.")
        tags.configure(state="disabled")
        bind_smooth_vertical_wheel(tags, mode="pixels")
        ttk.Label(root, text="DESCRIPTION", style="FocusEyebrow.TLabel").grid(row=5, column=0, sticky="w", pady=(0, 4))
        description = tk.Text(root, height=5, width=1, wrap="word", bg=THEME["surface"], fg=THEME["text"], relief="flat", bd=0, highlightthickness=0, padx=10, pady=8, font=FONT_UI)
        description.grid(row=6, column=0, sticky="nsew")
        description.insert("1.0", build_description_display_text(info) or "No description found for this video.")
        description.configure(state="disabled")
        bind_smooth_vertical_wheel(description, mode="pixels")
        ttk.Button(root, text="Done", command=popup.destroy, style="Accent.TButton").grid(row=7, column=0, sticky="e", pady=(14, 0))
        popup.update_idletasks()
        reveal_toplevel(popup, centered_toplevel_geometry(self, 680, 620))

    def _focus_run_records(self) -> list[dict[str, Any]]:
        preview = getattr(self, "_focus_preview_runs", None)
        if isinstance(preview, list):
            return [dict(record) for record in preview]

        records: list[dict[str, Any]] = []
        active = bool(self._focus_active_override or self.active_job is not None or (self.worker and self.worker.is_alive()))
        current_url = self.active_job.url if self.active_job is not None else self.url_var.get().strip()
        if active and current_url:
            active_type = self.active_job.output_type if self.active_job is not None else self._selected_output_type()
            active_preview = self.active_job.preview_info if self.active_job is not None else None
            active_preview_path = str((active_preview or {}).get("preview_thumbnail_path") or "").strip()
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
                    "run_id": self.active_job.run_id if self.active_job is not None else "",
                    "job": self.active_job,
                    "preview_thumbnail_path": active_preview_path,
                    "preview_thumbnail_image": (
                        self.active_job.preview_thumbnail_image if self.active_job is not None else None
                    ),
                }
            )
        for job in self.pending_jobs:
            preview_info = job.preview_info or {}
            preview_path = str(preview_info.get("preview_thumbnail_path") or "").strip()
            records.append(
                {
                    "title": download_job_display_title(job, queued=True),
                    "detail": str(preview_info.get("uploader") or preview_info.get("channel") or self._focus_profile_text(
                            job.output_type,
                            mp3_settings=job.mp3_settings,
                            quality_label=job.quality_label,
                            export_mode=job.export_mode,
                        )),
                    "status": f"Queued  •  {job.output_type.value}",
                    "progress": 0,
                    "kind": "queued",
                    "output_type": job.output_type.value,
                    "run_id": job.run_id,
                    "job": job,
                    "preview_thumbnail_path": preview_path,
                    "preview_thumbnail_image": job.preview_thumbnail_image,
                }
            )
        for terminal_job in self._terminal_jobs:
            terminal_preview = terminal_job.preview_info or {}
            terminal_metadata_index = next(
                (
                    index
                    for index, item in enumerate(self.metadata_items)
                    if str(item.get("vodforge_terminal_run_id") or "") == terminal_job.run_id
                ),
                None,
            )
            terminal_status = terminal_job.terminal_status or "Stopped"
            records.append(
                {
                    "title": download_job_display_title(terminal_job),
                    "detail": str(
                        terminal_preview.get("uploader")
                        or terminal_preview.get("channel")
                        or terminal_job.terminal_message
                        or "Run did not produce an output"
                    ),
                    "status": f"{terminal_status}  •  {terminal_job.output_type.value}",
                    "progress": 0,
                    "kind": terminal_status.lower(),
                    "output_type": terminal_job.output_type.value,
                    "run_id": terminal_job.run_id,
                    "job": terminal_job,
                    "metadata_index": terminal_metadata_index,
                    "preview_thumbnail_path": str(terminal_preview.get("preview_thumbnail_path") or "").strip(),
                    "preview_thumbnail_image": terminal_job.preview_thumbnail_image,
                }
            )
        active_keys = self.active_job.metadata_keys if self.active_job is not None else set()
        active_history_identities = (
            self.active_job.history_identities if self.active_job is not None else set()
        )
        terminal_keys = {
            key
            for terminal_job in self._terminal_jobs
            for key in terminal_job.metadata_keys
        }
        completed_jobs_by_identity: dict[tuple[str, str, str], DownloadJob] = {}
        for completed_job in self.__dict__.get("_completed_jobs", []):
            for identity in completed_job.history_identities:
                # Completed jobs are newest-first. The first owner is the
                # canonical owner; an older repeated run must not overwrite it.
                completed_jobs_by_identity.setdefault(identity, completed_job)
        for index, item in enumerate(self.metadata_items):
            item_key = metadata_run_key(item)
            item_history_identity = history_identity(item) if history_output_dir(item) is not None else None
            if (
                history_output_dir(item) is None
                and item_key is not None
                and (item_key in active_keys or item_key in terminal_keys)
            ):
                continue
            if item_history_identity is not None and item_history_identity in active_history_identities:
                continue
            saved = history_output_dir(item)
            output_type = metadata_output_type(item)
            completed_job = (
                completed_jobs_by_identity.get(item_history_identity)
                if item_history_identity is not None
                else None
            )
            records.append(
                {
                    "title": str(item.get("title") or item.get("id") or "Untitled media"),
                    "detail": str(item.get("uploader") or item.get("channel") or format_duration(item.get("duration"))),
                    "status": f"{'Completed' if saved is not None else 'Previewed'}  •  {output_type.value}",
                    "progress": 100 if saved is not None else 0,
                    "kind": "completed" if saved is not None else "preview",
                    "metadata_index": index,
                    "output_type": output_type.value,
                    "run_id": completed_job.run_id if completed_job is not None else f"history:{index}",
                    "job": completed_job,
                    "preview_thumbnail_image": (
                        completed_job.preview_thumbnail_image if completed_job is not None else None
                    ),
                }
            )
        return records

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
        visible = records[:limit]
        if not visible:
            empty = ttk.Frame(self.focus_run_deck, style="FocusShell.TFrame")
            empty.grid(row=0, column=0, sticky="ew", padx=16, pady=14)
            ttk.Label(empty, text="Your runs will collect here", style="TLabel").pack(anchor="w")
            ttk.Label(empty, text="Start with a URL above. Completed downloads stay available in Library.", style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
            self.focus_run_deck.columnconfigure(0, weight=1)
            self.focus_run_count_var.set("No runs yet")
            self.focus_run_overflow_button.grid_remove()
            return

        for column in range(limit):
            self.focus_run_deck.columnconfigure(column, weight=1, uniform="focus-run")
        for column, record in enumerate(visible):
            tile_bg = THEME["bg"]
            tile = tk.Frame(self.focus_run_deck, bg=tile_bg, bd=0, highlightthickness=0, cursor="hand2")
            left_pad = 9 if column == 0 else 5
            right_pad = 5 if column < len(visible) - 1 else 9
            tile.grid(row=0, column=column, sticky="nsew", padx=(left_pad, right_pad), pady=6 if self._focus_layout == "compact" else 9)
            tile.columnconfigure(1, weight=1)
            source = self._focus_thumbnail_source_for_record(record)
            thumbnail_size = youtube_thumbnail_size(64 if self._focus_layout == "compact" else 80)
            thumbnail = self._focus_photo_from_source(source, thumbnail_size, 6 if self._focus_layout == "compact" else 7)
            if thumbnail is not None:
                self._focus_run_thumbnail_images.append(thumbnail)
                image_label = tk.Label(tile, image=thumbnail, bg=tile_bg, bd=0, highlightthickness=0)
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
                else "#ff7a7a"
                if record_kind == "failed"
                else "#e8b15e"
                if record_kind == "skipped"
                else THEME["accent"]
                if record_kind == "active"
                else THEME["muted"]
            )
            status_label = tk.Label(tile, text=status, bg=tile_bg, fg=status_color, font=FONT_UI_SMALL, bd=0, anchor="w")
            is_primary_active = column == 0 and str(record.get("kind")) == "active"
            if is_primary_active:
                status_label.configure(textvariable=self.focus_run_status_var)
            status_label.grid(row=1, column=1, sticky="w", pady=(3, 0))
            value = max(0.0, min(100.0, float(record.get("progress") or 0)))
            bar: SleekProgressbar | None = None
            if is_primary_active or 0 < value < 100:
                if is_primary_active:
                    bar = SleekProgressbar(tile, maximum=100, variable=self.progress_var, mode="determinate", height=4, track_color=THEME["border"])
                else:
                    bar = SleekProgressbar(tile, maximum=100, value=value, mode="determinate", height=4, track_color=THEME["border"])
                bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(7, 0))
            widgets = [tile, title_label, status_label]
            if thumbnail is not None:
                widgets.append(image_label)
            if record_kind in {"failed", "skipped", "stopped"} and isinstance(record.get("job"), DownloadJob):
                retry_button = tk.Canvas(
                    tile,
                    width=30,
                    height=30,
                    bg=tile_bg,
                    bd=0,
                    highlightthickness=0,
                    cursor="hand2",
                )
                retry_button.create_oval(2, 2, 28, 28, fill=THEME["surface"], outline=THEME["border"], width=1)
                retry_button.create_text(15, 14, text="↻", fill=THEME["text"], font=(FONT_UI[0], 15, "bold"))
                retry_button.bind(
                    "<Button-1>",
                    lambda _event, job=record["job"]: self._retry_terminal_job(job),
                )
                retry_button.place(x=thumbnail_size[0] // 2, y=thumbnail_size[1] // 2, anchor="center")
                widgets.append(retry_button)
            if bar is not None:
                widgets.append(bar)

            def sync_tile_hover(
                *,
                card: tk.Frame = tile,
                card_widgets: tuple[tk.Widget, ...] = tuple(widgets),
            ) -> None:
                try:
                    pointer_x = self.winfo_pointerx()
                    pointer_y = self.winfo_pointery()
                    inside = (
                        card.winfo_rootx() <= pointer_x < card.winfo_rootx() + card.winfo_width()
                        and card.winfo_rooty() <= pointer_y < card.winfo_rooty() + card.winfo_height()
                    )
                    background = THEME["surface"] if inside else THEME["bg"]
                    for card_widget in card_widgets:
                        card_widget.configure(bg=background)
                except tk.TclError:
                    return

            for widget in widgets:
                widget.bind("<Button-1>", lambda event, item=record: self._focus_activate_run_record(item, event))
                widget.bind("<Button-2>", lambda event, item=record: self._show_focus_run_actions_menu(item, event))
                widget.bind("<Button-3>", lambda event, item=record: self._show_focus_run_actions_menu(item, event))
                widget.bind("<Enter>", lambda _event, card=tile, sync=sync_tile_hover: card.after_idle(sync), add="+")
                widget.bind("<Leave>", lambda _event, card=tile, sync=sync_tile_hover: card.after_idle(sync), add="+")

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
            except Exception:
                pass
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
                    candidates.extend((saved / "thumbnail.jpg", saved / "thumbnail.jpeg", saved / "thumbnail.png", saved / "thumbnail.webp"))
                cached = cached_thumbnail_path(item)
                if cached is not None:
                    candidates.append(cached)
        for path in candidates:
            try:
                if path.is_file():
                    with Image.open(path) as source:
                        return source.convert("RGBA").copy()
            except Exception as exc:
                write_diagnostic(f"run thumbnail could not be loaded ({path}): {exc}")
        if str(record.get("kind")) == "active" and self._focus_active_thumbnail_source_image is not None:
            return self._focus_active_thumbnail_source_image
        return self._focus_brand_source_image

    def _focus_photo_from_source(self, source: Any | None, size: tuple[int, int], radius: int) -> Any | None:
        if source is None or ImageTk is None:
            return None
        try:
            is_placeholder = source is self._focus_brand_source_image or (
                source is self._focus_thumbnail_source_image and self._focus_thumbnail_is_placeholder
            ) or (
                source is self._focus_active_thumbnail_source_image and self._focus_active_thumbnail_is_placeholder
            )
            rendered = (
                rounded_contain_image(source, size, radius, THEME["surface"])
                if is_placeholder
                else rounded_fit_image(source, size, radius)
            )
            return ImageTk.PhotoImage(rendered)
        except Exception as exc:
            write_diagnostic(f"thumbnail surface could not be rendered: {exc}")
            return None

    def _focus_activate_run_record(self, record: dict[str, Any], event: tk.Event[Any] | None = None) -> None:
        self._focus_select_run_record(record)

    def _show_focus_run_actions_menu(self, record: dict[str, Any], event: tk.Event[Any] | None = None) -> None:
        menu = tk.Menu(self, tearoff=False, bg=THEME["surface"], fg=THEME["text"], activebackground=THEME["accent_dark"], activeforeground="#ffffff")
        if str(record.get("kind")) == "active":
            menu.add_command(label="Cancel run", command=self._cancel)
            menu.add_command(label="Skip current item", command=self._skip_video)
            menu.add_command(label="Skip current source URL", command=self._skip_url)
            menu.add_separator()
        terminal_job = record.get("job")
        if str(record.get("kind")) in {"failed", "skipped", "stopped"} and isinstance(terminal_job, DownloadJob):
            menu.add_command(label="Retry run", command=lambda job=terminal_job: self._retry_terminal_job(job))
            menu.add_separator()
        metadata_index = record.get("metadata_index")
        if metadata_index is not None:
            menu.add_command(label="View in Library", command=lambda: (self._select_record_in_library(record), self._select_focus_view("library")))
            try:
                saved = history_output_dir(self.metadata_items[int(metadata_index)])
            except (IndexError, TypeError, ValueError):
                saved = None
            if saved is not None:
                menu.add_command(
                    label="Open saved location",
                    command=lambda item=record: (
                        self._select_record_in_library(item),
                        self._open_selected_saved_location(),
                    ),
                )
        menu.add_command(label="View Activity", command=lambda: self._select_focus_view("activity"))
        x = event.x_root if event is not None else self.winfo_pointerx()
        y = event.y_root if event is not None else self.winfo_pointery()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _show_active_focus_run_actions(self) -> None:
        records = self._focus_run_records()
        record = next((item for item in records if str(item.get("kind")) == "active"), records[0] if records else None)
        if record is not None:
            self._show_focus_run_actions_menu(record)

    def _apply_focus_layout(self, event: tk.Event[Any] | None = None, *, force: bool = False) -> None:
        if event is not None and event.widget is not self:
            return
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        mode = focus_layout_mode(width, height)
        compact = mode == "compact"
        balanced = mode == "balanced"
        library_mode = "compact" if compact else focus_library_layout_mode(width)
        layout_signature = (
            mode,
            library_mode,
            focus_run_deck_capacity(max(1, width - 52)),
            focus_hero_thumbnail_visible(width),
        )
        if layout_signature == self.__dict__.get("_focus_layout_signature") and not force:
            return
        self._focus_layout_signature = layout_signature
        self._focus_layout = mode
        horizontal_pad = 20 if compact else 42 if balanced else 100
        self.focus_shell.pack_configure(padx=12 if compact else 20, pady=(10 if compact else 16, 10 if compact else 14))
        self.focus_command_area.grid_configure(padx=horizontal_pad, pady=(18 if compact else 26 if balanced else 42, 8 if compact else 14))
        self.focus_active_frame.grid_configure(padx=horizontal_pad, pady=(6 if compact else 10 if balanced else 16, 9 if compact else 14))
        self.focus_detail_wrap.grid_configure(padx=horizontal_pad, pady=(0, 7 if compact else 12))
        self.focus_destination_button.configure(width=170 if compact else 210 if balanced else 240)
        show_hero_thumbnail = focus_hero_thumbnail_visible(width)
        active_title_width = max(260, width - (2 * horizontal_pad) - (180 if show_hero_thumbnail else 0) - 150)
        self.focus_active_title_label.configure(wraplength=active_title_width)
        self.focus_summary_text.configure(font=(FONT_MONO_FAMILY, 8) if balanced else FONT_MONO)
        self.focus_log.configure(font=(FONT_MONO_FAMILY, 8) if compact else FONT_MONO, pady=0 if compact else 4)

        active = bool(self._focus_active_override or (self.worker and self.worker.is_alive()))
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
                self.focus_update_dot.pack(side="left", padx=(0, 4), before=self.update_button)
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

        # The selected-details rail and its controls share one authority. When
        # the rail is visible its four direct actions stay visible; when the
        # rail is absent the two compact menu buttons replace them.
        if library_mode == "compact":
            for button in self.focus_library_action_buttons:
                button.pack_forget()
            if not self.focus_library_menu_button.winfo_manager():
                self.focus_library_menu_button.pack(side="left")
            if not self.focus_library_details_button.winfo_manager():
                self.focus_library_details_button.pack(side="left", padx=(6, 0), before=self.focus_library_menu_button)
        else:
            self.focus_library_menu_button.pack_forget()
            self.focus_library_details_button.pack_forget()
            for button in self.focus_library_action_buttons:
                if not button.winfo_manager():
                    button.pack(side="left", padx=(6, 0))

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
            self.video_tree.column("creator", width=120, minwidth=90, stretch=False)
            self.video_tree.column("id", width=90, minwidth=72, stretch=False)
            self.video_tree.column("location", width=140, minwidth=100, stretch=False)
            self.video_tree.column("title", width=360, minwidth=220, stretch=False)
        else:
            if library_mode == "balanced":
                self.focus_library_view.rowconfigure(1, weight=2, minsize=190)
                self.focus_library_view.rowconfigure(2, weight=3, minsize=210)
            else:
                self.focus_library_view.rowconfigure(1, weight=2, minsize=220)
                self.focus_library_view.rowconfigure(2, weight=3, minsize=230)
            self.focus_queue_panel.grid_configure(column=0, columnspan=1, padx=(0, 18))
            self.focus_library_details.grid(row=0, column=1, sticky="nsew")
            if library_mode == "balanced":
                self.focus_metadata_content.columnconfigure(0, weight=1)
                self.focus_metadata_content.columnconfigure(1, weight=0, minsize=300)
                self.video_tree.column("creator", width=110, minwidth=90, stretch=False)
                self.video_tree.column("id", width=90, minwidth=72, stretch=False)
                self.video_tree.column("location", width=120, minwidth=90, stretch=False)
                self.video_tree.column("title", width=320, minwidth=200, stretch=False)
            else:
                self.focus_metadata_content.columnconfigure(0, weight=1)
                self.focus_metadata_content.columnconfigure(1, weight=0, minsize=340)
                self.video_tree.column("creator", width=120, minwidth=90, stretch=False)
                self.video_tree.column("id", width=90, minwidth=72, stretch=False)
                self.video_tree.column("location", width=120, minwidth=90, stretch=False)
                self.video_tree.column("title", minwidth=220)
        self._sync_focus_destination()
        self._refresh_focus_run_deck()

    def _check_runtime(self) -> None:
        if _YTDLP_IMPORT_ATTEMPTED and YTDLP_IMPORT_ERROR is not None:
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

    def _start_ytdlp_preload(self) -> None:
        threading.Thread(target=self._preload_ytdlp_worker, daemon=True).start()

    def _preload_ytdlp_worker(self) -> None:
        module = load_yt_dlp()
        if module is None:
            self.events.put(("runtime_error", f"yt-dlp import failed: {YTDLP_IMPORT_ERROR}"))
            return
        version = getattr(getattr(module, "version", None), "__version__", "unknown")
        write_diagnostic(f"yt-dlp version: {version}")

    def _schedule_auto_update_check(self, delay_ms: int = AUTO_UPDATE_INTERVAL_MS) -> None:
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
        if (self.worker and self.worker.is_alive()) or (self.update_worker and self.update_worker.is_alive()):
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
        self.update_worker = threading.Thread(target=self._update_check_worker, daemon=True)
        self.update_worker.start()

    def _update_check_worker(self) -> None:
        try:
            self.events.put(("update_check_result", fetch_latest_release()))
        except Exception as exc:
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
                messagebox.showinfo(APP_NAME, f"You are using the latest VODForge release (v{__version__}).")
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
        self.update_worker = threading.Thread(target=self._update_download_worker, args=(release,), daemon=True)
        self.update_worker.start()

    def _update_download_worker(self, release: ReleaseInfo) -> None:
        try:
            destination = application_data_dir() / "updates" / release.tag_name
            path = download_verified_update(release, destination)
            payload: Path | MacUpdatePlan = path
            if sys.platform == "darwin":
                target_app = running_macos_app()
                if target_app is None:
                    raise RuntimeError("VODForge must be running from the packaged app to update itself.")
                cleanup_stale_macos_updates(destination)
                payload = prepare_macos_update(path, target_app)
            elif sys.platform.startswith("win"):
                verify_windows_authenticode(path)
            self.events.put(("update_ready", payload))
        except Exception as exc:
            self.events.put(("update_check_error", str(exc)))

    def _install_downloaded_update(self, update: Path | MacUpdatePlan) -> None:
        self.update_button.config(state="normal")
        if isinstance(update, MacUpdatePlan):
            try:
                launch_macos_update(update)
            except Exception as exc:
                messagebox.showerror(APP_NAME, f"The verified macOS update could not be started:\n\n{exc}")
                self.status_var.set("The macOS update could not be started.")
                return
            self.update_button.config(state="disabled", text="Installing update…")
            self._focus_update_full_text = "Installing update…"
            self.status_var.set("Verified update ready. VODForge is restarting to install it…")
            self.after(250, self.destroy)
            return
        path = update
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
        if self.metadata_items and not metadata_indices_for_output_type(
            self.metadata_items,
            self.library_output_type_var.get(),
        ):
            self.library_output_type_var.set(metadata_output_type(self.metadata_items[0]).value)
        self._render_metadata_tree()
        if self.download_history:
            self.status_var.set(f"Loaded {len(self.download_history)} downloaded media item(s) from history.")
            self._append_log(f"Loaded download history: {self.history_path}")

    def _record_download_history(
        self,
        info: dict[str, Any],
        output_dir: Path,
        *,
        owning_job: DownloadJob | None = None,
    ) -> None:
        history_info = dict(info)
        if owning_job is not None:
            history_info["vodforge_run_id"] = owning_job.run_id
            history_info["vodforge_run_activity"] = sanitize_run_activity(owning_job.activity_lines)
        try:
            self.download_history = upsert_history(self.download_history, history_info, output_dir)
            save_history(self.history_path, self.download_history)
        except HistoryError as exc:
            if owning_job is not None:
                self._append_job_log(owning_job, f"WARNING: {exc}")
            else:
                self._append_log(f"WARNING: {exc}")
            self.status_var.set("The video finished, but VODForge could not save it to local history.")
            return

        saved_record = self.download_history[0]
        if owning_job is not None:
            owning_job.history_identities.add(history_identity(saved_record))
        saved_id = str(saved_record.get("id") or "")
        saved_type = metadata_output_type(saved_record)
        merged = dict(saved_record)
        retained: list[dict[str, Any]] = []
        metadata_items = self.__dict__.get("metadata_items", [])
        for item in metadata_items:
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
        self.metadata_items = [merged, *retained]
        self._rebuild_output_dir_index()
        if self.library_output_type_var.get() != saved_type.value:
            self.library_output_type_var.set(saved_type.value)
        self._render_metadata_tree(selected_index=0)
        if owning_job is not None:
            self._append_job_log(owning_job, f"Saved download history entry: {output_dir}")
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
            if history_output_dir(item) is None or history_identity(item) not in identities:
                continue
            updated = dict(item)
            updated["vodforge_run_id"] = job.run_id
            updated["vodforge_run_activity"] = activity
            self.metadata_items[index] = updated

    def _manual_help_icon(self, frame: ttk.LabelFrame, row: int, text: str) -> None:
        icon = ttk.Label(frame, text="?", style="Accent.TLabel", cursor="question_arrow")
        icon.grid(row=row, column=2, sticky="w", padx=(2, 8), pady=6)
        ToolTip(icon, text)

    def _refresh_manual_settings_visibility(self) -> None:
        frames = list(getattr(self, "manual_settings_frames", []))
        if not frames:
            fallback = getattr(self, "manual_settings_frame", None)
            frames = [fallback] if fallback is not None else []
        live_frames: list[ttk.Frame] = []
        manual_override = (
            self._selected_output_type() == OutputType.MP4
            and self.export_mode_var.get() == ExportMode.MANUAL_OVERRIDE.value
        )
        for frame in frames:
            try:
                if not frame.winfo_exists():
                    continue
                if manual_override:
                    frame.grid()
                else:
                    frame.grid_remove()
                live_frames.append(frame)
            except tk.TclError:
                continue
        if hasattr(self, "manual_settings_frames"):
            self.manual_settings_frames = live_frames

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
        initial_dir = self.output_var.get() or str(Path.home())
        try:
            if sys.platform.startswith("win"):
                folder = choose_windows_output_directory(initial_dir)
            else:
                folder = filedialog.askdirectory(initialdir=initial_dir, mustexist=True)
        except (OSError, RuntimeError, tk.TclError) as exc:
            self._append_log(f"Output folder browser failed: {exc}")
            guidance = (
                "Windows could not browse that location. VODForge stayed open.\n\n"
                "You can paste a mapped-drive or \\\\server\\share path directly into Output folder."
                if sys.platform.startswith("win")
                else "VODForge could not browse that location. You can type or paste the folder path directly."
            )
            messagebox.showerror(
                APP_NAME,
                f"{guidance}\n\nDetails: {exc}",
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
        self.cookie_source_var.set(CookieSource.FILE.value)
        self.status_var.set("Loaded YouTube cookies.txt; VODForge will use it for this session.")
        self._append_log(f"Loaded YouTube cookies file: {cookie_path}")

    def _fetch_metadata(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror(APP_NAME, "Paste a YouTube URL first.")
            return
        ignore_playlists = self.single_video_only_var.get()
        if ignore_playlists:
            single_item_error = single_video_url_requires_video_id_error(url)
            if single_item_error:
                messagebox.showerror(APP_NAME, single_item_error)
                return
        if load_yt_dlp() is None:
            messagebox.showerror(APP_NAME, f"yt-dlp import failed: {YTDLP_IMPORT_ERROR}")
            return
        if hasattr(self, "preview_metadata_button"):
            self.preview_metadata_button.config(state="disabled")
        self.status_var.set("Fetching tags and thumbnail…")
        output_type = self._selected_output_type()
        threading.Thread(target=self._metadata_worker, args=(url, output_type, ignore_playlists), daemon=True).start()

    def _provider_network_coordinator(self) -> ProviderNetworkCoordinator:
        coordinator = self.__dict__.get("_provider_network")
        if coordinator is None:
            coordinator = ProviderNetworkCoordinator()
            self._provider_network = coordinator
        return coordinator

    def _metadata_worker(self, url: str, output_type: OutputType, ignore_playlists: bool = False) -> None:
        ytdlp_module = load_yt_dlp()
        if ytdlp_module is None:
            self.events.put(("metadata_error", f"Metadata fetch failed: yt-dlp import failed: {YTDLP_IMPORT_ERROR}"))
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
                "retries": 2,
                "extractor_retries": 2,
            }
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
                        raise RuntimeError("Metadata preview cancelled during application close")

                return run_tracked_ytdlp_operation(
                    extract,
                    control_check=control_check,
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
        except Exception as exc:
            self.events.put(("metadata_error", f"Metadata fetch failed: {format_ytdlp_user_error(exc)}"))
        finally:
            self.events.put(("metadata_fetch_done", None))

    def _enqueue_queue_preview(self, job: DownloadJob) -> None:
        requests = getattr(self, "_queued_preview_requests", None)
        worker = getattr(self, "_queued_preview_thread", None)
        if requests is None:
            requests = queue.Queue(maxsize=MAX_QUEUED_PREVIEW_REQUESTS)
            self._queued_preview_requests = requests
        try:
            requests.put_nowait(job)
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
        requests: queue.Queue[DownloadJob] = self._queued_preview_requests
        while True:
            job = requests.get()
            try:
                if any(item is job for item in self.pending_jobs):
                    self._queue_preview_worker(job)
            finally:
                requests.task_done()

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
                "retries": 2,
                "extractor_retries": 2,
            }
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

                extracted = run_tracked_ytdlp_operation(extract, control_check=control_check)
                if not isinstance(extracted, dict):
                    return None
                items = iter_video_infos(mark_metadata_output_type(extracted, job.output_type))
                preview = dict(items[0] if items else extracted)
                cached = (
                    save_custom_cached_thumbnail_image(preview, job.mp3_settings.custom_cover_art_path)
                    if job.output_type == OutputType.MP3 and job.mp3_settings.custom_cover_art_path is not None
                    else save_cached_thumbnail_image(preview)
                )
                if cached is not None:
                    preview["preview_thumbnail_path"] = str(cached)
                return preview

            pending = lambda: any(item is job for item in self.pending_jobs)
            ran, preview = self._provider_network_coordinator().run_preview(
                fetch_preview,
                should_abort=lambda: bool(self.__dict__.get("_closing", False)) or not pending(),
            )
            if not ran or not isinstance(preview, dict) or not pending():
                return
            self.events.put(("queued_preview", {"job": job, "info": preview}))
        except Exception as exc:
            write_diagnostic(f"queued run preview unavailable for {job.url}: {type(exc).__name__}: {exc}")

    def _copy_tags(self) -> None:
        text = self.pulled_tags_text.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.status_var.set("Copied tags to clipboard.")
            self._show_copy_feedback("tags")

    def _copy_thumbnail_url(self) -> None:
        if self.last_thumbnail_url:
            self.clipboard_clear()
            self.clipboard_append(self.last_thumbnail_url)
            self.status_var.set("Copied thumbnail URL to clipboard.")
            self._show_copy_feedback("thumbnail")

    def _copy_description(self) -> None:
        text = self.description_text.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.status_var.set("Copied description to clipboard.")
            self._show_copy_feedback("description")

    def _show_copy_feedback(self, key: str) -> None:
        """Briefly confirm a successful copy without adding persistent UI."""
        entry = getattr(self, "focus_library_copy_buttons", {}).get(key)
        if entry is None:
            return
        button, original_label = entry
        pending = getattr(self, "_focus_copy_feedback_after_ids", {})
        previous_after_id = pending.pop(key, None)
        if previous_after_id is not None:
            try:
                self.after_cancel(previous_after_id)
            except tk.TclError:
                pass
        button.configure(text="Copied", style="FocusCopySuccess.TButton")

        def restore() -> None:
            try:
                button.configure(text=original_label, style="FocusQuiet.TButton")
            except tk.TclError:
                pass
            pending.pop(key, None)

        pending[key] = self.after(900, restore)
        self._focus_copy_feedback_after_ids = pending

    def _display_metadata(self, info: dict[str, Any], *, active_job: DownloadJob | None = None) -> None:
        active_status = self.status_var.get() if active_job is not None and active_job is self.active_job else None
        incoming_items = iter_video_infos(info)
        new_items: list[dict[str, Any]] = []
        for incoming in incoming_items:
            video_id = str(incoming.get("id") or "")
            output_type = metadata_output_type(incoming)
            matching = next(
                (
                    item
                    for item in [*new_items, *self.metadata_items]
                    if video_id
                    and str(item.get("id") or "") == video_id
                    and metadata_output_type(item) == output_type
                    and not (active_job is not None and history_output_dir(item) is not None)
                ),
                None,
            )
            if matching is not None:
                matching.update(incoming)
            else:
                new_items.append(incoming)
        if new_items:
            self.metadata_items = [*new_items, *self.metadata_items]
        self._rebuild_output_dir_index()
        if incoming_items:
            incoming_type = metadata_output_type(incoming_items[0])
            if self.library_output_type_var.get() != incoming_type.value:
                self.library_output_type_var.set(incoming_type.value)
        self._render_metadata_tree()
        if active_job is not None and active_job is self.active_job and incoming_items:
            for incoming in incoming_items:
                key = metadata_run_key(incoming)
                if key is not None:
                    active_job.metadata_keys.add(key)
            self._display_active_job_metadata(active_job, incoming_items[0])
            if active_status is not None:
                self.status_var.set(active_status)
        else:
            self.status_var.set(f"Showing metadata for {len(incoming_items)} fetched item(s); saved history remains available.")

    def _display_active_job_metadata(self, job: DownloadJob, info: dict[str, Any]) -> None:
        """Apply provider metadata only to the run that currently owns the Forge surface."""
        if job is not self.active_job:
            return
        job.preview_info = {**(job.preview_info or {}), **info}
        selected_run_id = getattr(self, "_focus_selected_run_id", None)
        selected_for_details = selected_run_id is None or selected_run_id == job.run_id
        preview_thumbnail = str(info.get("preview_thumbnail_path") or "").strip()
        preview_thumbnail_path = Path(preview_thumbnail) if preview_thumbnail else None
        cached_thumbnail = cached_thumbnail_path(info)
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
                except Exception as exc:
                    write_diagnostic(f"active run thumbnail could not be cached for its deck card: {exc}")
            elif thumbnail_url:
                self._load_thumbnail_preview(
                    thumbnail_url,
                    target=f"run:{job.run_id}",
                    owner_run_id=job.run_id,
                )
            self._refresh_focus_run_deck()
            return

        title = download_job_display_title(job)
        creator = str(info.get("uploader") or info.get("channel") or "YouTube").strip()
        self.focus_active_title_var.set(title)
        self.focus_active_detail_var.set(creator)
        duration = format_duration(info.get("duration"))
        self.focus_active_duration_var.set("" if duration == "—" else duration)
        summary = info.get("vodforge_encoding_summary") if isinstance(info.get("vodforge_encoding_summary"), dict) else {}
        output = summary.get("output") if isinstance(summary.get("output"), dict) else {}
        if job.output_type == OutputType.MP3:
            bitrate = _display_value(output.get("Target audio bitrate"), f"{job.mp3_settings.bitrate_kbps} kbps")
            sample_rate = _display_value(output.get("Audio sample rate"), "Source rate")
            self.focus_active_profile_var.set(f"MP3  •  {bitrate}  •  {sample_rate}")
        else:
            mode = _display_value(output.get("Output rate-control mode"), job.export_mode.value)
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
            self._load_thumbnail_preview(thumbnail_url, target="active", owner_run_id=job.run_id)
        else:
            self._reset_active_thumbnail()
        self._refresh_focus_run_deck()

    def _active_run_for_metadata_event(self, event_job: DownloadJob) -> DownloadJob | None:
        """Resolve worker copies to the one active run authority; reject stale run events."""
        active_job = self.active_job
        if active_job is None or event_job.run_id != active_job.run_id:
            return None
        return active_job

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
        visible_indices = metadata_indices_for_output_type(self.metadata_items, self.library_output_type_var.get())
        for visible_position, metadata_index in enumerate(visible_indices, start=1):
            item = self.metadata_items[metadata_index]
            output_dir = history_output_dir(item)
            terminal_status = str(item.get("vodforge_terminal_status") or "").strip()
            location = terminal_status or (output_dir.name if output_dir is not None else "Preview only")
            retry_available = terminal_status in {"Skipped", "Failed"} and bool(item.get("vodforge_terminal_run_id"))
            values = (*video_list_row_values(item, fallback_index=visible_position), location)
            if "action" in self.video_tree["columns"]:
                values = (*values, "↻" if retry_available else "")
            self.video_tree.insert("", "end", iid=str(metadata_index), values=values)
        children = self.video_tree.get_children()
        if children:
            preferred = str(selected_index) if selected_index is not None else selected_iid
            target = preferred if preferred in children else children[0]
            self.video_tree.selection_set(target)
            self.video_tree.focus(target)
            self._display_selected_metadata(int(target))
        else:
            self._clear_library_selection()
        if hasattr(self, "focus_run_deck"):
            self._refresh_focus_run_deck()

    def _clear_library_selection(self) -> None:
        output_type = self.library_output_type_var.get()
        self.selected_title_var.set(f"No {output_type} items yet. Preview or forge a URL to add one.")
        self.last_thumbnail_url = None
        self._set_text(self.pulled_tags_text, f"No {output_type} item selected.")
        self._set_text(self.description_text, f"Your {output_type} metadata will appear here.")
        self._set_text(self.source_summary_text, "No source selected.", disabled=True)
        self._set_text(self.output_summary_text, "No output selected.", disabled=True)
        if hasattr(self, "focus_run_deck") and self._focus_brand_source_image is not None:
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
            self.video_tree.focus(row)
            self._display_selected_metadata(int(row))
        menu = tk.Menu(self, tearoff=False, bg=THEME["surface"], fg=THEME["text"], activebackground=THEME["accent_dark"], activeforeground="#ffffff")
        info = None
        if row:
            try:
                info = self.metadata_items[int(row)]
            except (IndexError, TypeError, ValueError):
                info = None
        terminal_job = self._terminal_job_for_metadata(info) if isinstance(info, dict) else None
        if terminal_job is not None:
            menu.add_command(label="↻ Retry in Forge", command=lambda: self._retry_terminal_job(terminal_job))
            menu.add_separator()
        if isinstance(info, dict) and history_output_dir(info) is not None:
            menu.add_command(label="Open saved location", command=self._open_selected_saved_location)
            menu.add_separator()
        menu.add_command(label="Remove from Library…", command=self._remove_selected_library_item)
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
        if not messagebox.askyesno(
            APP_NAME,
            f"Remove “{title}” from VODForge Library?\n\nThe media file and its folder will remain on your computer.",
        ):
            return
        saved = history_output_dir(info)
        previous_history = list(self.download_history)
        if saved is not None:
            identity = history_identity(info)
            self.download_history = [item for item in self.download_history if history_identity(item) != identity]
            try:
                save_history(self.history_path, self.download_history)
            except HistoryError as exc:
                self.download_history = previous_history
                messagebox.showerror(APP_NAME, str(exc))
                return
            for completed_job in self.__dict__.get("_completed_jobs", []):
                completed_job.history_identities.discard(identity)
        terminal_run_id = str(info.get("vodforge_terminal_run_id") or "")
        if terminal_run_id:
            self._terminal_jobs = [job for job in self._terminal_jobs if job.run_id != terminal_run_id]
        self.metadata_items.pop(index)
        self._rebuild_output_dir_index()
        self._render_metadata_tree()
        self.status_var.set("Removed the Library record. The media file was not deleted.")

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
            location_text = terminal_status + (f" — {terminal_message}" if terminal_message else "")
        else:
            location_text = f"Saved in {saved}" if saved is not None else "Not downloaded in this history"
        self.selected_title_var.set(
            f"{title}\n{output_type.value} • {creator} • {format_duration(info.get('duration'))} • {info.get('id') or 'no id'}\n{location_text}"
        )
        tags_text = build_tags_display_text(info)
        description = build_description_display_text(info)
        self._set_text(self.pulled_tags_text, tags_text or "No tags found for this video.")
        self._set_text(self.description_text, description or "No description found for this video.")
        source_summary, output_summary = build_encoding_summary_display(info)
        self._set_encoding_summary_text(self.source_summary_text, source_summary)
        self._set_encoding_summary_text(self.output_summary_text, output_summary)
        thumb = best_thumbnail(info)
        self.last_thumbnail_url = str((thumb or {}).get("url") or "") or None
        preview_thumbnail = str(info.get("preview_thumbnail_path") or "").strip()
        preview_thumbnail_path = Path(preview_thumbnail) if preview_thumbnail else None
        local_thumbnail = saved / "thumbnail.jpeg" if saved is not None else None
        cached_thumbnail = cached_thumbnail_path(info)
        thumbnail_target = "library"
        if preview_thumbnail_path is not None and preview_thumbnail_path.is_file():
            self._load_thumbnail_file(preview_thumbnail_path, target=thumbnail_target)
        elif local_thumbnail is not None and local_thumbnail.is_file():
            self._load_thumbnail_file(local_thumbnail, target=thumbnail_target)
        elif cached_thumbnail is not None and cached_thumbnail.is_file():
            self._load_thumbnail_file(cached_thumbnail, target=thumbnail_target)
        elif self.last_thumbnail_url:
            self._load_thumbnail_preview(self.last_thumbnail_url, target=thumbnail_target)
        else:
            if hasattr(self, "focus_run_deck") and self._focus_brand_source_image is not None:
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
        if Image is None or ImageOps is None or ImageTk is None or not hasattr(self, "focus_thumbnail_wrap"):
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
        active_image = self._focus_active_thumbnail_source_image or self._focus_brand_source_image
        library_image = self._focus_thumbnail_source_image or self._focus_brand_source_image
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
                native=isinstance(active_rendered, str) or isinstance(library_rendered, str),
            )

    def _render_focus_thumbnail_image(
        self,
        image: Any,
        size: tuple[int, int],
        *,
        placeholder: bool,
        source_path: Path | None,
    ) -> Any | None:
        if (
            not placeholder
            and source_path is not None
        ):
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

    def _create_focus_native_image(self, path: Path, size: tuple[int, int], *, radius: int = 0) -> str | None:
        """Use AppKit-backed NSImage drawing when Tk exposes it on macOS."""
        if sys.platform != "darwin" or not path.is_file():
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
            write_diagnostic(f"native thumbnail image could not be loaded ({path}): {exc}")
            return None

    def _delete_focus_native_images(self, *images: Any) -> None:
        for image in images:
            if not isinstance(image, str) or not image:
                continue
            try:
                self.tk.call("image", "delete", image)
            except tk.TclError:
                pass

    def _set_focus_thumbnail_images(self, active: Any, library: Any, *, native: bool) -> None:
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
            raise ValueError(f"Thumbnail requests require one owning surface, not {target!r}.")
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

    def _load_thumbnail_file(self, path: Path, *, target: str, owner_run_id: str = "") -> None:
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
                self._render_focus_thumbnail_surfaces(image, placeholder=False, source_path=path, target=target)
                return
            image.thumbnail((260, 150))
            self.thumbnail_image = ImageTk.PhotoImage(image)
            self.thumbnail_label.config(image=self.thumbnail_image, text="")
        except Exception as exc:
            target_label.config(text=f"Saved thumbnail preview failed:\n{exc}\n\n{path}")

    def _load_thumbnail_preview(
        self,
        url: str,
        *,
        target: str,
        owner_run_id: str = "",
    ) -> None:
        target_label = self._thumbnail_label_for_target(target)
        if Image is None or ImageTk is None:
            target_label.config(text=f"Thumbnail URL:\n{url}")
            return
        request_target = target
        request_id = self._invalidate_thumbnail_request(request_target)
        requests = getattr(self, "_thumbnail_preview_requests", None)
        worker = getattr(self, "_thumbnail_preview_thread", None)
        if requests is None:
            requests = queue.Queue(maxsize=2)
            self._thumbnail_preview_requests = requests
        retained: list[tuple[int, str, str, str]] = []
        while True:
            try:
                pending = requests.get_nowait()
                requests.task_done()
            except queue.Empty:
                break
            if len(pending) == 4 and pending[2] != request_target:
                retained.append(pending)
        for pending in retained[-1:]:
            requests.put_nowait(pending)
        requests.put_nowait((request_id, url, request_target, owner_run_id))
        if worker is None or not worker.is_alive():
            worker = threading.Thread(target=self._thumbnail_preview_loop, daemon=True)
            self._thumbnail_preview_thread = worker
            worker.start()
        if not target.startswith("run:"):
            target_label.config(text="Loading thumbnail…")

    def _thumbnail_preview_loop(self) -> None:
        requests: queue.Queue[tuple[int, str, str, str]] = self._thumbnail_preview_requests
        while True:
            request_id, url, target, owner_run_id = requests.get()
            try:
                self._fetch_thumbnail_preview_request(request_id, url, target, owner_run_id)
            except Exception as exc:
                self.events.put((
                    "thumbnail_preview_result",
                    {"id": request_id, "url": url, "error": str(exc), "target": target, "run_id": owner_run_id},
                ))
            finally:
                requests.task_done()

    def _fetch_thumbnail_preview_request(
        self,
        request_id: int,
        url: str,
        target: str,
        owner_run_id: str,
    ) -> None:
        if (
            bool(self.__dict__.get("_closing", False))
            or request_id != self._thumbnail_request_ids().get(target, 0)
        ):
            return
        # Thumbnail bytes are already independently bounded by URL scheme,
        # response size, timeout, and decoded pixel count. They do not use the
        # yt-dlp provider session, so delaying them behind the entire primary
        # media operation only leaves a placeholder visible for most of a run.
        data = download_bounded_url_bytes(url, timeout_seconds=15)
        if (
            bool(self.__dict__.get("_closing", False))
            or request_id != self._thumbnail_request_ids().get(target, 0)
        ):
            return
        self.events.put((
            "thumbnail_preview_result",
            {"id": request_id, "url": url, "data": data, "target": target, "run_id": owner_run_id},
        ))

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
            if target.startswith("run:") or (target == "active" and owner_run_id and owner_run_id != selected_run_id):
                write_diagnostic(f"run thumbnail preview failed: run_id={owner_run_id} error={error}")
                if self.__dict__.get("focus_run_deck") is not None:
                    self._refresh_focus_run_deck()
                return
            target_label.config(text=f"Thumbnail preview failed:\n{error}\n\nURL:\n{url}")
            return
        try:
            image = decode_bounded_thumbnail(bytes(payload.get("data") or b""))
            if hasattr(self, "focus_run_deck"):
                if (target == "active" or target.startswith("run:")) and owner_run_id:
                    owner_job = self.active_job if self.active_job is not None and self.active_job.run_id == owner_run_id else next(
                        (
                            job
                            for job in [*self._terminal_jobs, *getattr(self, "_completed_jobs", [])]
                            if job.run_id == owner_run_id
                        ),
                        None,
                    )
                    if owner_job is not None:
                        owner_job.preview_thumbnail_image = image.convert("RGBA").copy()
                    if target.startswith("run:") or owner_run_id != selected_run_id:
                        self._refresh_focus_run_deck()
                        return
                self._render_focus_thumbnail_surfaces(image, placeholder=False, target=target)
                if target == "active":
                    self._refresh_focus_run_deck()
                return
            image.thumbnail((260, 150))
            self.thumbnail_image = ImageTk.PhotoImage(image)
            self.thumbnail_label.config(image=self.thumbnail_image, text="")
        except Exception as exc:
            if target.startswith("run:") or (target == "active" and owner_run_id and owner_run_id != selected_run_id):
                write_diagnostic(f"run thumbnail decode failed: run_id={owner_run_id} error={exc}")
                if self.__dict__.get("focus_run_deck") is not None:
                    self._refresh_focus_run_deck()
                return
            target_label.config(text=f"Thumbnail preview failed:\n{exc}\n\nURL:\n{url}")

    def _start_download(self) -> None:
        urls = list(self.batch_urls) if self.batch_urls else [self.url_var.get().strip()]
        if self.single_video_only_var.get():
            for url in urls:
                single_video_error = single_video_url_requires_video_id_error(url)
                if single_video_error:
                    messagebox.showerror(APP_NAME, single_video_error)
                    return
        url = urls[0].strip() if urls else ""
        write_diagnostic(f"URL received: {url}")
        write_diagnostic(f"normalized URL: {url}")
        write_diagnostic(f"batch URL count: {len(urls)}")
        cookie_source = self._selected_cookie_source()
        use_cookies, cookie_file, cookie_browser = self._cookie_inputs()
        write_diagnostic(f"playlist query present: {'list=' in url.lower()} ; ignore_playlists={self.single_video_only_var.get()} ; use_nvenc={self.use_nvenc_var.get()} ; cookie_source={cookie_source.value}")
        if not url:
            messagebox.showerror(APP_NAME, "Paste a YouTube URL first or load a URL list text file.")
            return
        output_text = self.output_var.get().strip()
        if not output_text:
            messagebox.showerror(APP_NAME, "Choose an output folder.")
            return
        output_dir = Path(output_text).expanduser()
        try:
            validate_output_directory_access(output_dir)
        except OSError as exc:
            messagebox.showerror(
                APP_NAME,
                "VODForge cannot write to the selected output folder. "
                f"Choose another folder or allow access, then try again.\n\n{exc}",
            )
            return
        if cookie_source == CookieSource.FILE and cookie_file is None:
            messagebox.showerror(APP_NAME, "Choose a YouTube cookies.txt file, or switch YouTube access back to Public.")
            return
        if cookie_source == CookieSource.BROWSER and cookie_browser is None:
            messagebox.showerror(APP_NAME, "Choose a browser profile, or switch YouTube access back to Public.")
            return
        cookie_warning = windows_chromium_cookie_warning(cookie_browser) if cookie_source == CookieSource.BROWSER else None
        if cookie_warning:
            messagebox.showerror(APP_NAME, cookie_warning)
            return

        tags = [tag.strip() for tag in self.tags_var.get().split(",") if tag.strip()]
        output_type = self._selected_output_type()
        try:
            manual_settings = (
                self._manual_export_settings()
                if output_type == OutputType.MP4
                else ManualExportSettings()
            )
            mp3_settings = self._mp3_export_settings() if output_type == OutputType.MP3 else Mp3ExportSettings()
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        job = DownloadJob(
            url=url,
            output_dir=output_dir,
            output_type=output_type,
            quality_label=self.quality_var.get(),
            export_mode=ExportMode(self.export_mode_var.get()),
            manual_settings=manual_settings,
            mp3_settings=mp3_settings,
            single_video_only=self.single_video_only_var.get(),
            use_nvenc=self.use_nvenc_var.get() if output_type == OutputType.MP4 else False,
            embed_thumbnail=self.embed_thumbnail_var.get() if output_type == OutputType.MP4 else False,
            write_thumbnail=self.write_thumbnail_var.get() if output_type == OutputType.MP4 else False,
            embed_metadata=self.embed_metadata_var.get() if output_type == OutputType.MP4 else False,
            write_info_json=self.write_info_json_var.get() if output_type == OutputType.MP4 else False,
            tags=tags,
            urls=urls,
            use_cookies=use_cookies,
            cookie_file=cookie_file,
            cookie_browser=cookie_browser,
            batch_mode=bool(self.batch_urls),
        )

        if self.worker is not None and self.worker.is_alive():
            self.pending_jobs.append(job)
            if hasattr(self, "focus_run_deck"):
                self.focus_engine_var.set(f"1 active  /  {len(self.pending_jobs)} queued  /  runs process one at a time")
                self._append_log(f"Queued {job.output_type.value} run: {job.url}")
                self._refresh_focus_run_deck()
                self.download_button.configure(text="Queue run", state="normal")
                self._enqueue_queue_preview(job)
            self._reset_source_input_after_send()
            return

        self._launch_download_job(job)
        self._reset_source_input_after_send()

    def _launch_download_job(self, job: DownloadJob, *, select_detail: bool = True) -> None:
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
                str(preview_info.get("uploader") or preview_info.get("channel") or "Preparing source")
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
                    else "Format        MP4\nVideo         H.264\nAudio         AAC\nOutput mode   Pending\n"
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
        self.worker = threading.Thread(target=self._download_worker, args=(job,), daemon=True)
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
        if job is None:
            return
        job.terminal_status = status
        job.terminal_message = message
        if (
            job.preview_thumbnail_image is None
            and self._focus_active_thumbnail_source_image is not None
            and not self._focus_active_thumbnail_is_placeholder
            and self._focus_selected_run_id == job.run_id
        ):
            job.preview_thumbnail_image = self._focus_active_thumbnail_source_image.convert("RGBA").copy()
        self._terminal_jobs = [item for item in self._terminal_jobs if item.run_id != job.run_id]
        self._terminal_jobs.insert(0, job)
        del self._terminal_jobs[20:]

    def _archive_active_completed_job(self, status: str, message: str) -> None:
        job = self.active_job
        if job is None:
            return
        job.terminal_status = status
        job.terminal_message = message
        if (
            job.preview_thumbnail_image is None
            and self._focus_active_thumbnail_source_image is not None
            and not self._focus_active_thumbnail_is_placeholder
            and self._focus_selected_run_id == job.run_id
        ):
            job.preview_thumbnail_image = self._focus_active_thumbnail_source_image.convert("RGBA").copy()
        self._completed_jobs = [item for item in self._completed_jobs if item.run_id != job.run_id]
        self._completed_jobs.insert(0, job)
        del self._completed_jobs[20:]

    def _archive_item_terminal_job(self, job: DownloadJob, info: dict[str, Any]) -> None:
        """Archive one playlist item attempt without transferring Library authority."""
        self._terminal_jobs = [item for item in self._terminal_jobs if item.run_id != job.run_id]
        self._terminal_jobs.insert(0, job)
        del self._terminal_jobs[20:]
        item_key = metadata_run_key(info)
        matching = next(
            (
                item
                for item in self.metadata_items
                if history_output_dir(item) is None and metadata_run_key(item) == item_key
            ),
            None,
        )
        if matching is not None:
            matching.update(info)
        else:
            self.metadata_items.insert(0, dict(info))
        self._rebuild_output_dir_index()
        self._render_metadata_tree()
        if hasattr(self, "focus_run_deck"):
            self._refresh_focus_run_deck()

    def _retry_terminal_job(self, failed_job: DownloadJob) -> None:
        retry_url = retry_url_for_item(failed_job.preview_info or {}, failed_job.url)
        retry_job = replace(
            failed_job,
            url=retry_url,
            urls=[retry_url],
            run_id=uuid.uuid4().hex,
            metadata_keys=set(),
            history_identities=set(),
            activity_lines=[],
            terminal_status=None,
            terminal_message="",
            item_terminal_emitted=False,
        )
        self._terminal_jobs = [item for item in self._terminal_jobs if item.run_id != failed_job.run_id]
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
        threading.Thread(target=terminate_all_active_child_processes, daemon=True).start()

    def _request_application_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._close_deadline = time.monotonic() + APPLICATION_CLOSE_TIMEOUT_SECONDS
        self.cancel_requested = True
        self.pending_jobs.clear()
        write_diagnostic("application close requested; cancelling active work before destroying the window")
        try:
            self.status_var.set("Closing safely; stopping active media work…")
            self.download_button.config(state="disabled")
            self.cancel_button.config(state="disabled")
            self.skip_video_button.config(state="disabled")
            self.skip_url_button.config(state="disabled")
        except (AttributeError, tk.TclError):
            pass
        self._close_terminator = threading.Thread(target=terminate_all_active_child_processes, daemon=True)
        self._close_terminator.start()
        self.after(50, self._finish_application_close_when_idle)

    def _finish_application_close_when_idle(self) -> None:
        worker_alive = self.worker is not None and self.worker.is_alive()
        terminator_alive = self._close_terminator is not None and self._close_terminator.is_alive()
        if worker_alive or terminator_alive:
            deadline = self.__dict__.get("_close_deadline")
            if deadline is None or time.monotonic() < deadline:
                self.after(100, self._finish_application_close_when_idle)
                return
            write_diagnostic(
                "application close deadline exceeded; destroying the window while daemon work remains active; "
                "cleanup could not be confirmed"
            )
            terminate_all_active_child_processes(deadline_monotonic=time.monotonic() + 0.5)
            self.destroy()
            return
        write_diagnostic("active media work and child cleanup confirmed stopped; destroying application window")
        self.destroy()

    def _skip_video(self) -> None:
        self.skip_video_requested = True
        self.status_var.set("Skip item requested; continuing with the next playlist item after the current step stops…")
        threading.Thread(target=terminate_all_active_child_processes, daemon=True).start()

    def _skip_url(self) -> None:
        self.skip_url_requested = True
        self.skip_video_requested = True
        self.status_var.set("Skip source URL requested; continuing with the next batch URL after the current step stops…")
        threading.Thread(target=terminate_all_active_child_processes, daemon=True).start()

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
        batch_outcome = DownloadOutcome()
        try:
            reset_batch_failure_report()
            failures: list[tuple[str, str]] = []
            for index, url in enumerate(urls, start=1):
                if self.cancel_requested:
                    raise RuntimeError("Download cancelled by user")
                item_url, forced_single_video = prepare_batch_item_url(url)
                item_single_video_only = job.single_video_only or forced_single_video
                self.events.put(("status", f"Batch URL {index} of {len(urls)} — starting"))
                self._emit_job_log(job, f"Batch URL {index} of {len(urls)}: {item_url}")
                write_diagnostic(f"batch URL {index} of {len(urls)} start: {item_url} single_video_only={item_single_video_only}")
                try:
                    item_outcome = self._download_worker_single(
                        replace(job, url=item_url, urls=[item_url], single_video_only=item_single_video_only),
                        emit_done=False,
                        re_raise=True,
                    )
                    batch_outcome = batch_outcome.combined_with(item_outcome)
                except Exception as exc:
                    issue = format_ytdlp_user_error(exc)
                    if "cancelled" in issue.lower():
                        raise
                    if "url skipped" in issue.lower():
                        self.skip_url_requested = False
                        self.skip_video_requested = False
                        write_diagnostic(f"batch URL {index} skipped by user: {item_url}")
                        self._emit_job_log(job, f"Batch URL {index} skipped by user; continuing.")
                        batch_outcome = batch_outcome.combined_with(DownloadOutcome(skipped_count=1))
                        continue
                    failures.append((item_url, issue))
                    batch_outcome = batch_outcome.combined_with(DownloadOutcome(failure_count=1))
                    append_batch_failure_report(BATCH_FAILURE_REPORT_PATH, item_url, issue)
                    write_diagnostic(f"batch URL {index} of {len(urls)} failed but batch will continue: {type(exc).__name__}: {exc}")
                    self._emit_job_log(job, f"WARNING: Batch URL {index} failed; continuing. Failure report: {BATCH_FAILURE_REPORT_PATH}")
                    continue
            if batch_outcome.success_count == 0:
                if batch_outcome.failure_count:
                    raise RuntimeError(
                        f"Batch produced no valid output — {batch_outcome.failure_count} item(s) failed. "
                        f"Failure report: {BATCH_FAILURE_REPORT_PATH}"
                    )
                self.events.put(("stopped", "Batch stopped without producing an output."))
            elif batch_outcome.failure_count or batch_outcome.skipped_count or batch_outcome.sidecar_failure_count:
                self.events.put((
                    "partial",
                    f"Batch completed with issues — {batch_outcome.success_count} valid output(s), "
                    f"{batch_outcome.failure_count} failed, {batch_outcome.skipped_count} skipped, "
                    f"{batch_outcome.sidecar_failure_count} optional sidecar failure(s)."
                    + (f" Failure report: {BATCH_FAILURE_REPORT_PATH}" if failures else ""),
                ))
            else:
                self.events.put(("done", f"Batch complete — {batch_outcome.success_count} valid output(s) from {len(urls)} URL(s)."))
        except Exception as exc:
            self._active_progress_context = None
            issue = format_ytdlp_user_error(exc)
            write_diagnostic(f"batch download worker error: {type(exc).__name__}: {exc}")
            if "cancelled" in issue.lower():
                if batch_outcome.success_count:
                    self.events.put((
                        "partial",
                        f"Batch cancelled — {batch_outcome.success_count} valid output(s) completed before cancellation. "
                        "No incomplete output was committed.",
                    ))
                else:
                    self.events.put(("stopped", "Batch cancelled. No incomplete output was committed."))
            else:
                self.events.put(("error", f"{exc}\n\nDiagnostics log: {DIAGNOSTICS_LOG_PATH}"))

    def _download_worker_single(
        self,
        job: DownloadJob,
        *,
        emit_done: bool = True,
        re_raise: bool = False,
    ) -> DownloadOutcome:
        ytdlp_module = load_yt_dlp()
        if ytdlp_module is None:
            raise RuntimeError(f"yt-dlp import failed: {YTDLP_IMPORT_ERROR}")

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

        def emit_item_terminal(
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
                metadata_keys={key} if (key := metadata_run_key(terminal_info)) is not None else set(),
                history_identities=set(),
                activity_lines=[message],
                terminal_status=status,
                terminal_message=message,
                item_terminal_emitted=True,
            )
            self.events.put(("item_terminal", {"job": terminal_job, "info": terminal_info}))

        current_video_info: dict[str, Any] | None = None
        current_plan: ExportPlan | AudioExportPlan | None = None
        outcome = DownloadOutcome()
        provider_network = self._provider_network_coordinator()
        job_session_cookies: tuple[Any, ...] = ()
        cookie_source_loaded = False

        try:
            max_height = _quality_max_height(job.quality_label)
            self._emit_job_log(job, f"Normalized URL: {job.url}")
            self.events.put(("progress", 0))
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
            else:
                self.events.put(("status", "Reading playlist…"))
                write_diagnostic("playlist detection start")
                playlist_started = time.monotonic()
                playlist_opts: dict[str, Any] = {
                    "quiet": True,
                    "skip_download": True,
                    "noplaylist": False,
                    "extract_flat": "in_playlist",
                    "logger": QueueLogger(None, diagnostic_prefix="playlist yt-dlp"),
                    "socket_timeout": 30,
                    "retries": 5,
                    "fragment_retries": 5,
                    "extractor_retries": 5,
                    "ignore_no_formats_error": True,
                }
                apply_ytdlp_cookie_options(playlist_opts, use_cookies=job.use_cookies, cookie_file=job.cookie_file, cookie_browser=job.cookie_browser)
                apply_youtube_runtime_options(playlist_opts, deno_path=self._find_deno())
                log_options("playlist detection", playlist_opts)

                def detect_playlist() -> tuple[dict[str, Any] | None, tuple[Any, ...]]:
                    write_diagnostic("playlist extraction start")
                    def extract() -> tuple[Any, tuple[Any, ...]]:
                        with ytdlp_module.YoutubeDL(playlist_opts) as ydl:
                            extracted = ydl.extract_info(job.url, download=False)
                            return extracted, snapshot_ytdlp_session_cookies(ydl)

                    extracted, session_cookies = run_tracked_ytdlp_operation(
                        extract,
                        control_check=raise_for_control_requests,
                    )
                    write_diagnostic("playlist extraction completed")
                    return (extracted if isinstance(extracted, dict) else None, session_cookies)

                provider_network.begin_primary(raise_for_control_requests)
                try:
                    playlist_result = run_cancellable_blocking_step(
                        lambda: provider_network.run_primary(detect_playlist),
                        playlist_blocking_step_cancelled,
                        timeout_seconds=ANALYSIS_TIMEOUT_SECONDS,
                        poll_seconds=ANALYSIS_POLL_SECONDS,
                        label="Playlist detection",
                        on_wait=lambda elapsed: (write_diagnostic(f"playlist detection still running after {elapsed:.0f}s"), self.events.put(("status", f"Reading playlist… {elapsed:.0f}s elapsed; Cancel is available."))),
                    )
                finally:
                    provider_network.end_primary()
                playlist_info, job_session_cookies = playlist_result
                playlist_info = playlist_info or {"webpage_url": job.url}
                cookie_source_loaded = job.use_cookies
                write_diagnostic(f"playlist detection elapsed_seconds={time.monotonic() - playlist_started:.3f}")
                raw_entries = playlist_info.get("entries") if isinstance(playlist_info, dict) else None
                extracted_playlist = raw_entries is not None
                entries = [entry for entry in (raw_entries or []) if isinstance(entry, dict)]
                if not entries:
                    entries = [{"webpage_url": job.url, "id": playlist_info.get("id"), "title": playlist_info.get("title")}]
                if not extracted_playlist:
                    # A normal video extraction is not a one-item playlist. Do
                    # not use the video's own title/id as playlist authority.
                    playlist_info = playlist_context_from_extraction(playlist_info, job.url)
                if job.single_video_only:
                    requested_video_id = youtube_url_video_id(job.url)
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
                            "webpage_url": clean_single_video_url(job.url),
                            "id": requested_video_id,
                        }
                    ]
                    write_diagnostic(
                        "playlist identity retained for single item: "
                        f"playlist_id={playlist_info.get('id') or playlist_info.get('playlist_id')} "
                        f"video_id={requested_video_id}"
                    )
            total_videos = len(entries)
            if total_videos > 1:
                self._emit_job_log(job, f"Playlist detected: {total_videos} videos.")
                write_diagnostic(f"playlist detected: video_count={total_videos}")
            else:
                self._emit_job_log(job, "Single video detected.")
                write_diagnostic("single video detected")

            all_output_dirs: list[Path] = []
            self.video_output_dirs_by_id = {}

            for video_index, entry in enumerate(entries, start=1):
                primary_intent_active = False
                try:
                    current_video_info = None
                    current_plan = None
                    custom_cover_for_cache: Path | None = None
                    video_url = video_url_from_entry(entry)
                    label = f"Video {video_index} of {total_videos}"
                    raise_for_control_requests()
                    self.events.put(("status", f"{label} — analyzing source formats"))
                    self._emit_job_log(job, f"{label}: URL {video_url}")
                    put_stage_progress(video_index, total_videos, 0.0, 0.10, 0.0)
                    provider_network.begin_primary(raise_for_control_requests)
                    primary_intent_active = True

                    preflight_opts: dict[str, Any] = {
                        "quiet": True,
                        "skip_download": True,
                        "noplaylist": True,
                        "extract_flat": False,
                        "logger": QueueLogger(None, diagnostic_prefix="preflight yt-dlp"),
                        "socket_timeout": 30,
                        "retries": 5,
                        "fragment_retries": 5,
                        "extractor_retries": 5,
                        "ignore_no_formats_error": True,
                    }
                    apply_ytdlp_cookie_options(preflight_opts, use_cookies=job.use_cookies, cookie_file=job.cookie_file, cookie_browser=job.cookie_browser)
                    if cookie_source_loaded:
                        preflight_opts.pop("cookiefile", None)
                        preflight_opts.pop("cookiesfrombrowser", None)
                    ffmpeg_for_preflight = self._find_ffmpeg()
                    if ffmpeg_for_preflight:
                        preflight_opts["ffmpeg_location"] = ytdlp_ffmpeg_location(ffmpeg_for_preflight)
                    deno = self._find_deno()
                    write_diagnostic(f"{label} preflight runtime path: ffmpeg={ffmpeg_for_preflight}")
                    write_diagnostic(f"{label} preflight runtime path: deno={deno}")
                    apply_youtube_runtime_options(preflight_opts, deno_path=deno)
                    if deno:
                        write_diagnostic(f"{label} preflight Deno/bundled-EJS enabled")
                    else:
                        write_diagnostic(f"{label} preflight Deno/EJS disabled: no deno runtime found")
                    log_options(f"{label} preflight", preflight_opts)

                    def analyze_source_formats() -> tuple[dict[str, Any] | None, tuple[Any, ...]]:
                        write_diagnostic(f"{label} analysis start")
                        analysis_started = time.monotonic()
                        def extract() -> tuple[Any, tuple[Any, ...]]:
                            with ytdlp_module.YoutubeDL(preflight_opts) as ydl:
                                seed_ytdlp_session_cookies(ydl, job_session_cookies)
                                extracted = ydl.extract_info(video_url, download=False)
                                return extracted, snapshot_ytdlp_session_cookies(ydl)

                        extracted, session_cookies = run_tracked_ytdlp_operation(
                            extract,
                            control_check=raise_for_control_requests,
                        )
                        write_diagnostic(f"{label} analysis completed elapsed_seconds={time.monotonic() - analysis_started:.3f}")
                        return (extracted if isinstance(extracted, dict) else None, session_cookies)

                    preflight_result = run_cancellable_blocking_step(
                        lambda: provider_network.run_primary(analyze_source_formats),
                        video_blocking_step_cancelled,
                        timeout_seconds=ANALYSIS_TIMEOUT_SECONDS,
                        poll_seconds=ANALYSIS_POLL_SECONDS,
                        label=f"{label} source analysis",
                        on_wait=lambda elapsed, label=label: (write_diagnostic(f"{label} analysis still running after {elapsed:.0f}s"), self.events.put(("status", f"{label} — analyzing source formats ({elapsed:.0f}s elapsed); Cancel is available."))),
                    )
                    preflight_info, preflight_session_cookies = preflight_result
                    job_session_cookies = preflight_session_cookies
                    cookie_source_loaded = job.use_cookies
                    if not isinstance(preflight_info, dict):
                        raise RuntimeError(f"{label}: YouTube source analysis did not return metadata")
                    preflight_info = mark_metadata_output_type(
                        apply_playlist_context(preflight_info, entry, playlist_info, job.url, video_index),
                        job.output_type,
                    )
                    if job.output_type == OutputType.MP3:
                        plan: ExportPlan | AudioExportPlan = build_mp3_export_plan(preflight_info, job.mp3_settings)
                    else:
                        plan = build_auto_export_plan(preflight_info, mode=job.export_mode, max_height=max_height)
                        if job.export_mode == ExportMode.MANUAL_OVERRIDE:
                            plan = apply_manual_export_settings(plan, job.manual_settings)
                            self._emit_job_log(job, f"{label}: Manual Override settings {plan.video_bitrate_kbps} kbps video + {plan.audio_bitrate_kbps} kbps audio, {plan.audio_sample_rate} Hz, {plan.audio_channels} channel(s), x264 preset {plan.x264_preset}.")
                    current_plan = plan
                    current_video_info = build_encoding_summary_metadata(preflight_info, plan)
                    self.events.put(("job_metadata", {"job": job, "info": current_video_info}))
                    self._emit_job_log(job, f"{label}: selected format {plan.format_selector}")
                    if isinstance(plan, AudioExportPlan):
                        self._emit_job_log(job, f"{label}: selected highest-quality audio source {plan.audio_codec} ~{plan.source_audio_kbps:.0f} kbps.")
                        self._emit_job_log(job, f"{label}: MP3 target {plan.audio_bitrate_kbps} kbps CBR; cover art {'embedded' if plan.embed_cover_art else 'not embedded'}.")
                    else:
                        self._emit_job_log(job, f"{label}: selected video {plan.output_height}p {plan.video_codec} ~{plan.source_video_kbps:.0f} kbps; selected audio {plan.audio_codec} ~{plan.source_audio_kbps:.0f} kbps.")
                        target_label = "Manual target" if job.export_mode == ExportMode.MANUAL_OVERRIDE else "Auto CBR target"
                        self._emit_job_log(job, f"{label}: {target_label} {plan.video_bitrate_kbps} kbps video + {plan.audio_bitrate_kbps} kbps audio.")
                    for warning in plan.warnings:
                        self._emit_job_log(job, f"WARNING: {label}: {warning}")
                    put_stage_progress(video_index, total_videos, 0.0, 0.10, 1.0)

                    existing_ffprobe = self._find_ffprobe()
                    existing_output = (
                        find_valid_existing_output(
                            job.output_dir,
                            current_video_info,
                            job.output_type,
                            existing_ffprobe,
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
                            expected_duration_seconds=_float_or_none(current_video_info.get("duration")),
                            control_check=raise_for_control_requests,
                        )
                        if existing_ffprobe
                        else None
                    )
                    if existing_output is not None:
                        existing_path, existing_probe = existing_output
                        remember_video_output_dir(current_video_info, existing_path.parent)
                        current_video_info = build_encoding_summary_metadata(
                            current_video_info,
                            plan,
                            output_path=existing_path,
                            ffprobe_data=existing_probe,
                            validation_status="Validated existing output",
                        )
                        self.events.put(("job_metadata", {"job": job, "info": current_video_info}))
                        self.events.put(
                            (
                                "history_record",
                                {
                                    "job": job,
                                    "info": current_video_info,
                                    "output_dir": str(existing_path.parent),
                                },
                            )
                        )
                        all_output_dirs.append(existing_path.parent)
                        self.events.put(("download_folders", sorted(set(all_output_dirs))))
                        outcome = outcome.combined_with(DownloadOutcome(success_count=1))
                        self._emit_job_log(
                            job,
                            f"{label}: already downloaded and valid; reused {existing_path}.",
                        )
                        if job.output_type == OutputType.MP3:
                            try:
                                cached_thumbnail = save_cached_thumbnail_image(current_video_info)
                                if cached_thumbnail is not None:
                                    self._emit_job_log(job, f"{label}: refreshed private Library artwork cache")
                            except Exception as exc:
                                outcome = outcome.combined_with(DownloadOutcome(sidecar_failure_count=1))
                                self._emit_job_log(job, f"WARNING: {label}: existing MP3 is valid, but Library artwork could not be refreshed: {exc}")
                        if job.write_info_json:
                            try:
                                write_compact_video_metadata(existing_path.parent, current_video_info, job.tags)
                            except Exception as exc:
                                outcome = outcome.combined_with(DownloadOutcome(sidecar_failure_count=1))
                                self._emit_job_log(job, f"WARNING: {label}: existing media is valid, but compact metadata could not be refreshed: {exc}")
                        if job.write_thumbnail:
                            try:
                                save_thumbnail_image(existing_path.parent, current_video_info)
                            except Exception as exc:
                                outcome = outcome.combined_with(DownloadOutcome(sidecar_failure_count=1))
                                self._emit_job_log(job, f"WARNING: {label}: existing media is valid, but its separate thumbnail could not be refreshed: {exc}")
                        put_stage_progress(video_index, total_videos, 0.10, 0.90, 1.0)
                        self.events.put(("status", f"{label} complete — existing valid output"))
                        continue

                    staging_dir = create_staging_dir(job.output_dir)
                    try:
                        ffmpeg = self._find_ffmpeg()
                        if not ffmpeg:
                            required_output = "MP3 audio" if job.output_type == OutputType.MP3 else "H.264 / AAC MP4 video"
                            raise RuntimeError(f"FFmpeg is required to create the {required_output} output.")
                        ydl_opts = self._build_ydl_options(job, staging_dir=staging_dir, format_selector=plan.format_selector)
                        ydl_opts["noplaylist"] = True
                        # Preflight already loaded the selected cookie source. Reuse
                        # its in-memory session jar instead of reopening a browser
                        # profile or cookies.txt for the immediately following run.
                        ydl_opts.pop("cookiefile", None)
                        ydl_opts.pop("cookiesfrombrowser", None)
                        log_options(f"{label} download", ydl_opts)
                        self._active_progress_context = (video_index, total_videos, 0.10, 0.40)
                        self.events.put(("status", f"{label} — downloading"))
                        self._emit_job_log(job, f"{label}: downloading")
                        download_started = time.monotonic()

                        def download_preflight_result() -> tuple[Any, tuple[Any, ...]]:
                            with ytdlp_module.YoutubeDL(ydl_opts) as ydl:
                                downloaded_info = process_download_from_preflight(
                                    ydl,
                                    preflight_info,
                                    session_cookies=preflight_session_cookies,
                                    control_check=raise_for_control_requests,
                                )
                                return downloaded_info, snapshot_ytdlp_session_cookies(ydl)

                        info, job_session_cookies = provider_network.run_primary(download_preflight_result)
                        provider_network.end_primary()
                        primary_intent_active = False
                        write_diagnostic(f"{label} download and yt-dlp post-processing elapsed_seconds={time.monotonic() - download_started:.3f}")
                        self._active_progress_context = None
                        raise_for_control_requests()
                        if not isinstance(info, dict):
                            raise RuntimeError(f"{label}: download did not return metadata")
                        info = mark_metadata_output_type(
                            apply_playlist_context(info, entry, playlist_info, job.url, video_index),
                            job.output_type,
                        )
                        if current_video_info and current_video_info.get("vodforge_encoding_summary"):
                            info["vodforge_encoding_summary"] = current_video_info["vodforge_encoding_summary"]
                        current_video_info = info
                        self.events.put(("job_metadata", {"job": job, "info": info}))
                        put_stage_progress(video_index, total_videos, 0.10, 0.40, 1.0)

                        expected_extension = ".mp3" if job.output_type == OutputType.MP3 else ".mp4"
                        staged_media = collect_staged_media_files(
                            staging_dir,
                            info,
                            expected_extension=expected_extension,
                        )
                        if not staged_media:
                            raise RuntimeError(
                                f"{label}: yt-dlp completed without producing the expected {expected_extension} file."
                            )

                        if job.output_type == OutputType.MP3 and job.mp3_settings.custom_cover_art_path is not None:
                            raise_for_control_requests()
                            prepared_cover = prepare_custom_cover_art(job.mp3_settings.custom_cover_art_path, staging_dir)
                            for _staged_info, staged_mp3 in staged_media:
                                embed_custom_mp3_cover_art(
                                    staged_mp3,
                                    prepared_cover,
                                    ffmpeg,
                                    control_check=raise_for_control_requests,
                                )
                            raise_for_control_requests()
                            custom_cover_for_cache = prepared_cover
                            self._emit_job_log(job, f"{label}: embedded custom cover art ({job.mp3_settings.custom_cover_art_path.name})")

                        ffprobe = self._find_ffprobe() or _ffprobe_for_ffmpeg(ffmpeg)
                        if not ffprobe:
                            raise RuntimeError(f"{label}: FFprobe is required to validate the final output.")

                        validated_staged: list[tuple[dict[str, Any], Path, dict[str, Any]]] = []
                        if isinstance(plan, ExportPlan):
                            total_mp4 = len(staged_media)
                            for encode_index, (staged_info, staged_mp4) in enumerate(staged_media, start=1):
                                raise_for_control_requests()
                                self.events.put(("status", f"{label} — transcoding"))
                                encoder_label = "NVIDIA NVENC GPU" if job.use_nvenc else "CPU libx264"
                                self._emit_job_log(job, f"{label}: FFmpeg command started ({encode_index}/{total_mp4}) using {encoder_label}")
                                write_diagnostic(f"{label} ffmpeg command: {build_vod_ffmpeg_command(ffmpeg, staged_mp4, transcode_temp_paths(staged_mp4)[0], video_bitrate_kbps=plan.video_bitrate_kbps, audio_bitrate_kbps=plan.audio_bitrate_kbps, audio_sample_rate=plan.audio_sample_rate, audio_channels=plan.audio_channels, x264_preset=plan.x264_preset, use_nvenc=job.use_nvenc)}")
                                put_stage_progress(video_index, total_videos, 0.50, 0.40, (encode_index - 1) / total_mp4)
                                transcode_started = time.monotonic()
                                transcode_to_vod_streaming_settings(
                                    staged_mp4,
                                    ffmpeg,
                                    plan=plan,
                                    duration_seconds=_float_or_none(staged_info.get("duration") or info.get("duration")),
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
                                write_diagnostic(f"{label} transcode elapsed_seconds={time.monotonic() - transcode_started:.3f}")
                                self._emit_job_log(job, f"{label}: transcoded staged VODForge output")
                        else:
                            self.events.put(("status", f"{label} — MP3 encoded"))

                        self.events.put(("status", f"{label} — validating output"))
                        validation_started = time.monotonic()
                        for staged_info, staged_path in staged_media:
                            raise_for_control_requests()
                            probe_data = validate_output_artifact(
                                staged_path,
                                job.output_type,
                                ffprobe,
                                expected_duration_seconds=_float_or_none(staged_info.get("duration") or info.get("duration")),
                                require_audio=True,
                                control_check=raise_for_control_requests,
                            )
                            validated_staged.append((staged_info, staged_path, probe_data))
                        raise_for_control_requests()
                        write_diagnostic(f"{label} artifact validation elapsed_seconds={time.monotonic() - validation_started:.3f}")

                        commit_started = time.monotonic()
                        packaged_paths = package_downloaded_media_from_staging(
                            staging_dir,
                            job.output_dir,
                            info,
                            expected_extension=expected_extension,
                            staged_media=[(staged_info, staged_path) for staged_info, staged_path, _probe in validated_staged],
                            control_check=raise_for_control_requests,
                        )
                        write_diagnostic(f"{label} atomic output commit elapsed_seconds={time.monotonic() - commit_started:.3f}")
                        output_dirs = sorted({path.parent for path in packaged_paths})
                        all_output_dirs.extend(output_dirs)
                        self.events.put(("download_folders", sorted(set(all_output_dirs))))
                        for packaged_path in packaged_paths:
                            self._emit_job_log(job, f"{label}: packaged media file {packaged_path}")
                        output_paths = [path for path in packaged_paths if path.suffix.lower() == expected_extension]
                        primary_output = output_paths[0] if output_paths else None
                        if primary_output is None:
                            raise RuntimeError(
                                f"{label}: validated output could not be committed to the destination."
                            )
                        ffprobe_data = validated_staged[0][2]
                        if isinstance(plan, AudioExportPlan):
                            self._emit_job_log(job, f"{label}: created {plan.audio_bitrate_kbps} kbps MP3 output {primary_output.name}")
                        put_stage_progress(video_index, total_videos, 0.50, 0.40, 1.0)
                        self._emit_job_log(job, f"{label}: validated {primary_output.name} before atomic commit")
                        info = build_encoding_summary_metadata(
                            info,
                            plan,
                            output_path=primary_output,
                            ffprobe_data=ffprobe_data,
                            validation_status="Validated",
                        )
                        current_video_info = info
                        self.events.put(("job_metadata", {"job": job, "info": info}))
                        outcome = outcome.combined_with(DownloadOutcome(success_count=len(output_paths)))
                        if job.output_type == OutputType.MP3:
                            try:
                                cached_thumbnail = (
                                    save_custom_cached_thumbnail_image(info, custom_cover_for_cache)
                                    if custom_cover_for_cache is not None
                                    else save_cached_thumbnail_image(info)
                                )
                                if cached_thumbnail is not None:
                                    artwork_source = "custom cover" if custom_cover_for_cache is not None else "YouTube thumbnail"
                                    self._emit_job_log(job, f"{label}: cached {artwork_source} privately for Forge and Library")
                            except Exception as exc:
                                outcome = outcome.combined_with(DownloadOutcome(sidecar_failure_count=1))
                                write_diagnostic(f"{label} private thumbnail cache failed: {type(exc).__name__}: {exc}")
                                self._emit_job_log(job, f"WARNING: {label}: the MP3 is complete, but its Library artwork could not be cached.")
                        if primary_output is not None:
                            self.events.put(
                                (
                                    "history_record",
                                    {
                                        "job": job,
                                        "info": info,
                                        "output_dir": str(primary_output.parent),
                                    },
                                )
                            )
                        if job.write_info_json:
                            try:
                                metadata_path = write_compact_video_metadata(resolved_video_output_dir(job.output_dir, info), info, job.tags)
                                self._emit_job_log(job, f"{label}: saved compact video metadata {metadata_path}")
                            except Exception as exc:
                                outcome = outcome.combined_with(DownloadOutcome(sidecar_failure_count=1))
                                write_diagnostic(f"{label} compact metadata write failed: {type(exc).__name__}: {exc}")
                                self._emit_job_log(job, f"WARNING: {label}: media is valid, but compact metadata could not be saved: {exc}")
                        if job.write_thumbnail:
                            try:
                                thumb_path = save_thumbnail_image(resolved_video_output_dir(job.output_dir, info), info)
                                if thumb_path:
                                    self._emit_job_log(job, f"{label}: saved thumbnail {thumb_path}")
                            except Exception as exc:
                                outcome = outcome.combined_with(DownloadOutcome(sidecar_failure_count=1))
                                write_diagnostic(f"{label} thumbnail write failed: {type(exc).__name__}: {exc}")
                                self._emit_job_log(job, f"WARNING: {label}: media is valid, but its separate thumbnail could not be saved: {exc}")
                        put_stage_progress(video_index, total_videos, 0.90, 0.10, 1.0)
                        result_label = "MP3 audio" if job.output_type == OutputType.MP3 else "MP4 video"
                        self.events.put(("status", f"{label} complete — {result_label}"))
                        self._emit_job_log(job, f"{label} complete — {result_label}")
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
                    if self.cancel_requested:
                        raise RuntimeError("Download cancelled by user") from exc
                    if self.skip_url_requested:
                        issue = "URL skipped by user"
                    elif self.skip_video_requested:
                        issue = "Video skipped by user"
                    else:
                        issue = format_ytdlp_user_error(exc)
                    if "cancelled" in issue.lower():
                        raise
                    if "url skipped" in issue.lower():
                        self.skip_url_requested = False
                        self.skip_video_requested = False
                        outcome = outcome.combined_with(DownloadOutcome(skipped_count=1))
                        emit_item_terminal("Skipped", "URL skipped by user", current_video_info, current_plan, video_url)
                        self._emit_job_log(job, f"{label}: skipped URL by user.")
                        break
                    if total_videos <= 1 and "video skipped" not in issue.lower():
                        raise
                    if current_video_info is not None:
                        self.events.put((
                            "job_metadata",
                            {"job": job, "info": build_failed_encoding_summary_metadata(current_video_info, current_plan, issue)},
                        ))
                    write_diagnostic(f"{label} failed but playlist will continue: {type(exc).__name__}: {exc}")
                    if "video skipped" in issue.lower():
                        outcome = outcome.combined_with(DownloadOutcome(skipped_count=1))
                        emit_item_terminal("Skipped", "Video skipped by user", current_video_info, current_plan, video_url)
                        self._emit_job_log(job, f"{label}: skipped by user; continuing to next video.")
                    else:
                        outcome = outcome.combined_with(DownloadOutcome(failure_count=1))
                        emit_item_terminal("Failed", issue, current_video_info, current_plan, video_url)
                        append_batch_failure_report(BATCH_FAILURE_REPORT_PATH, video_url, issue)
                        self._emit_job_log(job, f"WARNING: {label} failed; continuing to next video. Failure report: {BATCH_FAILURE_REPORT_PATH}")
                    self.skip_video_requested = False
                    continue
                finally:
                    if primary_intent_active:
                        provider_network.end_primary()

            if outcome.success_count == 0:
                if outcome.failure_count:
                    raise RuntimeError(
                        f"No valid {job.output_type.value} output was produced; "
                        f"{outcome.failure_count} item(s) failed. Failure report: {BATCH_FAILURE_REPORT_PATH}"
                    )
                if emit_done:
                    self.events.put(("stopped", f"{job.output_type.value} run stopped without producing an output."))
                return outcome
            if emit_done:
                if outcome.failure_count or outcome.skipped_count or outcome.sidecar_failure_count:
                    self.events.put((
                        "partial",
                        f"{job.output_type.value} completed with issues — {outcome.success_count} valid output(s), "
                        f"{outcome.failure_count} failed, {outcome.skipped_count} skipped, "
                        f"{outcome.sidecar_failure_count} optional sidecar failure(s).",
                    ))
                else:
                    self.events.put(("done", f"{job.output_type.value} download complete — {outcome.success_count} valid output(s)."))
            return outcome
        except Exception as exc:
            self._active_progress_context = None
            if current_video_info is not None:
                self.events.put((
                    "job_metadata",
                    {
                        "job": job,
                        "info": build_failed_encoding_summary_metadata(
                            current_video_info,
                            current_plan,
                            format_ytdlp_user_error(exc),
                        ),
                    },
                ))
            user_error = format_ytdlp_user_error(exc)
            write_diagnostic(f"download worker error: {type(exc).__name__}: {exc}")
            if "cancelled" in user_error.lower() and not re_raise:
                self.events.put(("stopped", "Download cancelled. No incomplete output was committed."))
                return outcome
            if "url skipped" in user_error.lower() and not re_raise:
                self.skip_url_requested = False
                self.skip_video_requested = False
                self.events.put(("stopped", "URL skipped. No incomplete output was committed."))
                return outcome
            if re_raise:
                raise
            self.events.put(("error", f"{user_error}\n\nDiagnostics log: {DIAGNOSTICS_LOG_PATH}"))
            return outcome

    def _build_ydl_options(self, job: DownloadJob, staging_dir: Path, format_selector: str | None = None) -> dict[str, Any]:
        if job.output_type == OutputType.MP3:
            use_youtube_cover = (
                job.mp3_settings.embed_cover_art
                and job.mp3_settings.custom_cover_art_path is None
            )
            postprocessors: list[dict[str, Any]] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": str(job.mp3_settings.bitrate_kbps),
                },
            ]
            if job.mp3_settings.embed_metadata:
                postprocessors.append({"key": "FFmpegMetadata", "add_chapters": True, "add_metadata": True})
            if use_youtube_cover:
                postprocessors.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
            selected_format = format_selector or "bestaudio/best"
            write_thumbnail = use_youtube_cover
            postprocessor_args = self._metadata_args(job.tags) if job.mp3_settings.embed_metadata else {}
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
                postprocessors.append({"key": "FFmpegMetadata", "add_chapters": True, "add_metadata": True})
            if job.embed_thumbnail:
                postprocessors.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
            selected_format = (format_selector or QUALITY_OPTIONS[job.quality_label]) + "/best"
            write_thumbnail = job.write_thumbnail or job.embed_thumbnail
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
            "progress_hooks": [self._progress_hook],
            "logger": QueueLogger(self.events),
            "embed_infojson": False,
            "postprocessor_args": postprocessor_args,
            "concurrent_fragment_downloads": 1,
            "retries": 15,
            "fragment_retries": 15,
            "extractor_retries": 5,
            "retry_sleep_functions": {"http": lambda n: min(2 * n, 15), "fragment": lambda n: min(2 * n, 15)},
            "ignore_no_formats_error": True,
        }
        if job.output_type == OutputType.MP4:
            opts["merge_output_format"] = "mp4"
        ffmpeg = self._find_ffmpeg()
        if ffmpeg:
            opts["ffmpeg_location"] = ytdlp_ffmpeg_location(ffmpeg)
        deno = self._find_deno()
        apply_youtube_runtime_options(opts, deno_path=deno)
        apply_ytdlp_cookie_options(opts, use_cookies=job.use_cookies, cookie_file=job.cookie_file, cookie_browser=job.cookie_browser)
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
        # Apply extra keywords specifically to FFmpegMetadata's output command.
        # yt-dlp normalizes postprocessor argument keys to lowercase.
        return {"metadata+ffmpeg_o": ["-metadata", f"keywords={','.join(tags)}"]}

    def _progress_hook(self, data: dict[str, Any]) -> None:
        if self.cancel_requested:
            raise RuntimeError("Download cancelled by user")
        if self.skip_url_requested:
            raise RuntimeError("URL skipped by user")
        if self.skip_video_requested:
            raise RuntimeError("Video skipped by user")
        status = data.get("status")
        if status == "downloading":
            now = time.monotonic()
            last_event_at = getattr(self, "_last_progress_event_at", 0.0)
            downloaded = data.get("downloaded_bytes") or 0
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            if now - last_event_at < PROGRESS_EVENT_INTERVAL_SECONDS and not (total and downloaded >= total):
                return
            self._last_progress_event_at = now
            self.events.put(("progress_determinate", None))
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
            self.events.put(("status", "Download finished; finalizing output…"))

    def _pump_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "job_log":
                    if isinstance(payload, dict) and isinstance(payload.get("job"), DownloadJob):
                        self._append_job_log(payload["job"], str(payload.get("line") or ""))
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
                    if hasattr(self, "focus_run_status_var"):
                        status_text = str(payload)
                        eta = status_text.partition(" ETA ")[2]
                        if eta:
                            self.focus_run_status_var.set(f"{self.progress_var.get():.0f}%  /  ETA {eta}")
                elif kind == "metadata":
                    if isinstance(payload, dict):
                        self._display_metadata(payload)
                elif kind == "job_metadata":
                    if (
                        isinstance(payload, dict)
                        and isinstance(payload.get("job"), DownloadJob)
                        and isinstance(payload.get("info"), dict)
                    ):
                        metadata_job = payload["job"]
                        active_metadata_job = self._active_run_for_metadata_event(metadata_job)
                        if active_metadata_job is not None:
                            self._display_metadata(payload["info"], active_job=active_metadata_job)
                        else:
                            write_diagnostic(
                                f"ignored stale run metadata event for run_id={metadata_job.run_id}"
                            )
                elif kind == "thumbnail_preview_result":
                    if isinstance(payload, dict):
                        self._display_thumbnail_preview_result(payload)
                elif kind == "queued_preview":
                    if isinstance(payload, dict) and isinstance(payload.get("job"), DownloadJob) and isinstance(payload.get("info"), dict):
                        queued_job = payload["job"]
                        if any(item is queued_job for item in self.pending_jobs):
                            queued_job.preview_info = dict(payload["info"])
                            if hasattr(self, "focus_run_deck"):
                                self._refresh_focus_run_deck()
                            if self._focus_selected_run_id == queued_job.run_id:
                                record = next(
                                    (
                                        candidate
                                        for candidate in self._focus_run_records()
                                        if candidate.get("run_id") == queued_job.run_id
                                    ),
                                    None,
                                )
                                if record is not None:
                                    self._display_focus_queued_job_snapshot(record, queued_job)
                elif kind == "history_record":
                    if isinstance(payload, dict) and isinstance(payload.get("info"), dict):
                        output_dir = str(payload.get("output_dir") or "").strip()
                        if output_dir:
                            history_job = payload.get("job")
                            owning_job = (
                                self._active_run_for_metadata_event(history_job)
                                if isinstance(history_job, DownloadJob)
                                else None
                            )
                            self._record_download_history(
                                payload["info"],
                                Path(output_dir),
                                owning_job=owning_job,
                            )
                elif kind == "item_terminal":
                    if (
                        isinstance(payload, dict)
                        and isinstance(payload.get("job"), DownloadJob)
                        and isinstance(payload.get("info"), dict)
                    ):
                        self._archive_item_terminal_job(payload["job"], payload["info"])
                elif kind == "metadata_fetch_done":
                    if hasattr(self, "preview_metadata_button"):
                        self.preview_metadata_button.config(state="normal")
                elif kind == "metadata_error":
                    if self.__dict__.get("_closing", False):
                        self._append_log(f"Metadata preview ended during application close: {payload}")
                    else:
                        self.status_var.set("Metadata preview failed")
                        self._append_log(f"ERROR: {payload}")
                        messagebox.showerror(APP_NAME, str(payload))
                elif kind == "runtime_error":
                    self._append_log(f"ERROR: {payload}")
                    self.download_button.config(state="disabled")
                elif kind == "download_folders":
                    if isinstance(payload, list):
                        self.last_output_dirs = [Path(path) for path in payload]
                elif kind == "update_check_result":
                    if not self.__dict__.get("_closing", False) and isinstance(payload, ReleaseInfo):
                        self._show_update_result(payload)
                elif kind == "update_ready":
                    if not self.__dict__.get("_closing", False) and isinstance(payload, (Path, MacUpdatePlan)):
                        self._install_downloaded_update(payload)
                elif kind == "update_check_error":
                    if self.__dict__.get("_closing", False):
                        write_diagnostic(f"update check ended during application close: {payload}")
                        continue
                    silent = self.update_check_silent
                    self.update_check_silent = False
                    self._schedule_auto_update_check()
                    self.update_button.config(state="normal")
                    self._set_focus_update_state("Check updates", THEME["subtle"])
                    if silent:
                        write_diagnostic(f"automatic update check failed: {payload}")
                    else:
                        self.status_var.set("Could not check for updates.")
                        messagebox.showinfo(APP_NAME, str(payload))
                elif kind == "cloud_seen_result":
                    if isinstance(payload, dict) and payload.get("success") is True:
                        state = self.installation_state
                        install_id = str(payload.get("install_id") or "")
                        if state is not None and install_id == state.install_id:
                            try:
                                self.installation_state = mark_cloud_seen_confirmed(self.installation_state_path, install_id)
                                write_diagnostic("Cloud early-access impression confirmed once for this installation")
                            except (InstallationIdentityError, OSError) as exc:
                                write_diagnostic(f"Cloud impression was accepted but local confirmation could not be saved: {exc}")
                elif kind == "first_launch_result":
                    if isinstance(payload, dict) and payload.get("success") is True:
                        state = self.installation_state
                        install_id = str(payload.get("install_id") or "")
                        if state is not None and install_id == state.install_id:
                            try:
                                self.installation_state = mark_first_launch_confirmed(self.installation_state_path, install_id)
                                write_diagnostic("first successful launch confirmed once for this installation")
                            except (InstallationIdentityError, OSError) as exc:
                                write_diagnostic(f"first launch was accepted but local confirmation could not be saved: {exc}")
                elif kind == "done":
                    self._finish_run_ui(str(payload), "Completed", "Complete  /  Ready to open in Library", progress=100)
                elif kind == "partial":
                    self._finish_run_ui(str(payload), "Partial", "Completed with issues  /  Valid files are in Library", progress=100)
                elif kind == "stopped":
                    self._finish_run_ui(str(payload), "Stopped", "Stopped  /  No incomplete output was committed")
                elif kind == "error":
                    if self.__dict__.get("_closing", False):
                        self._append_log(f"ERROR during application close: {payload}")
                        continue
                    failed_job = self.active_job
                    if failed_job is not None:
                        self._append_job_log(failed_job, f"ERROR: {payload}")
                    else:
                        self._append_log(f"ERROR: {payload}")
                    self._archive_active_terminal_job("Failed", str(payload))
                    self.progress_var.set(0)
                    self.status_var.set("Failed")
                    messagebox.showerror(APP_NAME, str(payload))
                    self.download_button.config(state="normal")
                    self.cancel_button.config(state="disabled")
                    self.skip_video_button.config(state="disabled")
                    self.skip_url_button.config(state="disabled")
                    if hasattr(self, "focus_transfer_var"):
                        if self._focus_follows_active_run():
                            self.focus_transfer_var.set("Run failed  /  Review Activity for details")
                        self.focus_run_status_var.set("Failed")
                        if self._focus_follows_active_run():
                            self.focus_percent_var.set("Failed")
                        self._refresh_focus_run_deck()
                    if not self._launch_next_pending_job() and hasattr(self, "focus_transfer_var"):
                        self._set_focus_run_controls_visible(False)
                        self._refresh_focus_run_deck()
        except queue.Empty:
            pass
        self.after(100, self._pump_events)

    def _finish_run_ui(self, message: str, run_status: str, transfer_text: str, *, progress: float | None = None) -> None:
        finished_job = self.active_job
        if finished_job is not None:
            self._append_job_log(finished_job, message)
            self._persist_job_activity_to_history(finished_job)
        else:
            self._append_log(message)
        if run_status == "Stopped" and not (finished_job is not None and finished_job.item_terminal_emitted):
            self._archive_active_terminal_job(run_status, message)
        elif run_status in {"Completed", "Partial"}:
            self._archive_active_completed_job(run_status, message)
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
        if not self._launch_next_pending_job() and self.__dict__.get("focus_transfer_var") is not None:
            self._set_focus_run_controls_visible(False)
            self._refresh_focus_run_deck()

    def _append_log(self, line: str) -> None:
        self._append_log_widget(self.log, line)
        if self.__dict__.get("_persist_activity", False):
            append_activity_log(line)

    def _emit_job_log(self, job: DownloadJob, line: str) -> None:
        self.events.put(("job_log", {"job": job, "line": line}))

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
    ytdlp_module = load_yt_dlp()
    if ytdlp_module is None:
        write_diagnostic(f"yt-dlp import failed: {YTDLP_IMPORT_ERROR}")
        print(f"yt-dlp import failed: {YTDLP_IMPORT_ERROR}")
        print(f"Diagnostics log: {DIAGNOSTICS_LOG_PATH}")
        return 2
    write_diagnostic(f"yt-dlp version: {getattr(ytdlp_module.version, '__version__', 'unknown')}")
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

        extracted = run_tracked_ytdlp_operation(extract)
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
    video_infos = iter_video_infos(info) if isinstance(info, dict) else []
    video_count = len(video_infos)
    format_count = len(info.get("formats") or []) if isinstance(info, dict) else 0
    write_diagnostic(f"debug-preflight success: id={(info or {}).get('id') if isinstance(info, dict) else None} videos={video_count} formats={format_count}")
    print(f"DEBUG_PREFLIGHT_OK videos={video_count} formats={format_count}")
    for video_info in video_infos:
        try:
            plan = build_auto_export_plan(video_info, mode=ExportMode.AUTO_CBR, max_height=DEFAULT_MAX_HEIGHT)
        except Exception as exc:
            print(f"DEBUG_PREFLIGHT_SELECTION_FAILED id={video_info.get('id') or 'unknown'}: {type(exc).__name__}: {exc}")
            continue
        exposed_heights = [
            fmt.get("height")
            for fmt in video_info.get("formats") or []
            if isinstance(fmt, dict) and isinstance(fmt.get("height"), int) and not _is_none_codec(fmt.get("vcodec"))
        ]
        print(
            f"DEBUG_PREFLIGHT_SELECTION id={video_info.get('id') or 'unknown'} "
            f"exposed_max_height={max(exposed_heights) if exposed_heights else 'unknown'} "
            f"selected={plan.format_selector} output={plan.output_width or 'unknown'}x{plan.output_height or 'unknown'}"
        )
        try:
            audio_plan = build_mp3_export_plan(video_info)
        except Exception as exc:
            print(f"DEBUG_PREFLIGHT_AUDIO_FAILED id={video_info.get('id') or 'unknown'}: {type(exc).__name__}: {exc}")
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
    if _normalized_numeric_version(ytdlp_version) != _normalized_numeric_version(PINNED_YTDLP_VERSION):
        raise RuntimeError(
            f"yt-dlp version {ytdlp_version} does not match pinned {PINNED_YTDLP_VERSION}"
        )

    ejs_module = importlib.import_module("yt_dlp_ejs")
    ejs_version = str(getattr(ejs_module, "version", "unknown"))
    if _normalized_numeric_version(ejs_version) != _normalized_numeric_version(PINNED_YTDLP_EJS_VERSION):
        raise RuntimeError(
            f"yt-dlp-ejs version {ejs_version} does not match pinned {PINNED_YTDLP_EJS_VERSION}"
        )

    resources_module = importlib.import_module("importlib.resources")
    solver_root = resources_module.files("yt_dlp_ejs.yt.solver")
    verified_resources: list[str] = []
    for resource_name in YTDLP_EJS_SOLVER_RESOURCES:
        resource = solver_root.joinpath(resource_name)
        if not resource.is_file() or not resource.read_bytes():
            raise RuntimeError(f"yt-dlp-ejs solver resource is missing or empty: {resource_name}")
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
        except Exception as exc:
            _runtime_smoke_output(f"{name}={path} execution_failed={type(exc).__name__}: {exc}")
            failures.append(name)
        else:
            _runtime_smoke_output(f"{name}={path} version={version}")
    try:
        ytdlp_version, ejs_version, solver_resources = _smoke_ytdlp_stack()
    except Exception as exc:
        _runtime_smoke_output(f"yt-dlp-stack=failed error={type(exc).__name__}: {exc}")
        failures.append("yt-dlp-stack")
    else:
        _runtime_smoke_output(
            f"yt-dlp={ytdlp_version} yt-dlp-ejs={ejs_version} "
            f"solver_resources={','.join(solver_resources)}"
        )
    _runtime_smoke_output(f"diagnostics={DIAGNOSTICS_LOG_PATH}")
    if failures:
        _runtime_smoke_output(f"VODFORGE_RUNTIME_SMOKE_FAILED dependencies={','.join(failures)}")
        return 1
    _runtime_smoke_output("VODFORGE_RUNTIME_SMOKE_OK")
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
