from __future__ import annotations

import os
import shutil

# This service accepts only a fixed or resolved executable and never invokes a shell.
import subprocess  # nosec B404
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

APPLICATION_NAME = "VODForge"
RUNTIME_SMOKE_PROBE_TIMEOUT_SECONDS = 60


def file_change_time_ns(descriptor: int, observed: os.stat_result) -> int:
    """Use the owned handle's mutation clock, never Windows path birth time."""
    if os.name == "nt":
        from .platforms.windows.filesystem import file_change_time_ns as native_time

        return native_time(descriptor)
    return observed.st_ctime_ns


def supports_tk_event(widget: Any, sequence: str) -> bool:
    """Parse an event on an unattached Tcl tag without registering a Python callback."""
    import tkinter as tk
    from uuid import uuid4

    # A read-only bind lookup accepts even unknown event names on Tk 8.6.
    # A script binding forces parsing. The private tag is never attached to a
    # widget, so the probe cannot consume input or invoke application callbacks.
    tag = f"VODForgeEventProbe-{uuid4().hex}"
    if widget.tk.call("bind", tag):
        return False  # Never replace or clean up another owner's tag.
    try:
        widget.tk.call("bind", tag, sequence, "break")
    except tk.TclError:
        return False
    finally:
        try:
            widget.tk.call("bind", tag, sequence, "")
        except tk.TclError:
            pass
    return True


def is_windows(platform_name: str | None = None) -> bool:
    """Return whether the requested or running platform uses Windows behavior."""
    value = sys.platform if platform_name is None else platform_name
    return value.startswith("win")


def is_macos(platform_name: str | None = None) -> bool:
    """Return whether the requested or running platform uses macOS behavior."""
    value = sys.platform if platform_name is None else platform_name
    return value == "darwin"


def request_window_foreground(root: Any) -> bool:
    """Request cooperative activation; attention is never successful activation."""
    root.lift()
    if is_macos():
        from .platforms.macos.windowing import request_window_foreground as activate

        return activate(root)
    if is_windows():
        from .platforms.windows.windowing import request_window_foreground as activate

        return activate(root)
    return False


def install_native_quit_handler(
    root: Any,
    callback: Callable[[], None],
    *,
    platform_name: str | None = None,
) -> bool:
    """Route the macOS application-menu Quit action through safe shutdown."""

    if not is_macos(platform_name):
        return False
    root.createcommand("::tk::mac::Quit", callback)
    return True


def diagnostics_dir(
    *,
    platform_name: str | None = None,
    home: Path | None = None,
    local_app_data: str | None = None,
) -> Path:
    """Return the platform's conventional per-user diagnostics directory."""
    home = Path.home() if home is None else home
    if is_windows(platform_name):
        base = (
            local_app_data
            if local_app_data is not None
            else os.environ.get("LOCALAPPDATA")
        )
        if base:
            return Path(base) / APPLICATION_NAME / "logs"
    if is_macos(platform_name):
        return home / "Library" / "Logs" / APPLICATION_NAME
    return home / ".vodforge" / "logs"


def platform_font_families(platform_name: str | None = None) -> tuple[str, str]:
    if is_macos(platform_name):
        return "Helvetica Neue", "Menlo"
    if is_windows(platform_name):
        return "Segoe UI", "Cascadia Mono"
    return "TkDefaultFont", "TkFixedFont"


def focus_view_shortcut_bindings(
    platform_name: str | None = None,
) -> tuple[tuple[str, str], ...]:
    """Return stable real-user shortcuts for the three primary app views."""
    modifier = "Command" if is_macos(platform_name) else "Control"
    return tuple(
        (f"<{modifier}-Key-{index}>", view_name)
        for index, view_name in enumerate(("forge", "library", "activity"), start=1)
    )


def runtime_window_icon_asset(platform_name: str | None = None) -> str | None:
    """Return the runtime window icon, leaving macOS to the bundle ICNS."""
    if is_windows(platform_name):
        return "VODForge.ico"
    if is_macos(platform_name):
        return None
    return "VODForge.png"


def configure_windows_app_identity(platform_name: str | None = None) -> bool:
    if not is_windows(platform_name):
        return False
    from .platforms.windows.windowing import configure_app_identity

    return configure_app_identity()


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
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    executable = Path(sys.executable) if executable is None else executable
    raw_meipass = getattr(sys, "_MEIPASS", None) if meipass is None else meipass
    meipass = Path(raw_meipass) if raw_meipass else None
    repo_root = Path(__file__).resolve().parents[1] if repo_root is None else repo_root
    names = (
        [f"{tool_name}.exe", tool_name]
        if is_windows(platform_name)
        else [tool_name, f"{tool_name}.exe"]
    )

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
    if is_macos(platform_name):
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


def hidden_window_subprocess_kwargs(platform_name: str | None = None) -> dict[str, Any]:
    if is_windows(platform_name):
        from .platforms.windows.processes import (
            hidden_window_subprocess_kwargs as options,
        )

        return options()
    return {"startupinfo": None, "creationflags": 0}


def choose_windows_output_directory(
    initial_dir: str, *, runner: Any = subprocess.run
) -> str | None:
    from .platforms.windows.dialogs import choose_windows_output_directory as choose

    return choose(initial_dir, runner=runner)


def choose_output_directory(
    initial_dir: str,
    *,
    standard_picker: Callable[[str], str | None],
    platform_name: str | None = None,
    windows_picker: Callable[[str], str | None] = choose_windows_output_directory,
) -> str | None:
    """Route the folder picker without leaking OS policy into the composition root."""
    if is_windows(platform_name):
        return windows_picker(initial_dir)
    return standard_picker(initial_dir)


def output_directory_failure_guidance(platform_name: str | None = None) -> str:
    if is_windows(platform_name):
        return (
            "Windows could not browse that location. VODForge stayed open.\n\n"
            "You can paste a mapped-drive or \\\\server\\share path directly into Output folder."
        )
    return "VODForge could not browse that location. You can type or paste the folder path directly."


def runtime_version_command(tool_name: str, executable: str) -> list[str]:
    return (
        [executable, "--version"] if tool_name == "deno" else [executable, "-version"]
    )


def probe_runtime_version(
    tool_name: str,
    executable: str,
    *,
    timeout_seconds: float = RUNTIME_SMOKE_PROBE_TIMEOUT_SECONDS,
) -> str:
    """Execute a bundled runtime so smoke tests also catch missing dynamic libraries."""
    # The resolved local executable and one fixed version flag remain separate argv entries.
    result = subprocess.run(  # nosec B603
        runtime_version_command(tool_name, executable),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        # Rosetta's first translation of the Intel Deno binary can take around
        # 30 seconds on Apple silicon; keep the release gate bounded above it.
        timeout=timeout_seconds,
        **hidden_window_subprocess_kwargs(),
    )
    return next(
        (line.strip() for line in result.stdout.splitlines() if line.strip()),
        "version output unavailable",
    )


def open_path(
    path: Path,
    *,
    create: bool = True,
    platform_name: str | None = None,
    popen: Callable[[list[str]], Any] = subprocess.Popen,
    which: Callable[[str], str | None] = shutil.which,
    startfile: Callable[[Path], Any] | None = None,
) -> None:
    """Open a folder without deferring executable selection to subprocess PATH lookup."""
    if create:
        path.mkdir(parents=True, exist_ok=True)
    elif not path.is_dir():
        raise OSError("The folder is unavailable.")
    if is_windows(platform_name):
        windows_startfile = (
            getattr(os, "startfile", None) if startfile is None else startfile
        )
        if not callable(windows_startfile):
            raise RuntimeError("The Windows folder opener is unavailable.")
        windows_startfile(path)
        return

    if is_macos(platform_name):
        opener = "/usr/bin/open"
    else:
        resolved = which("xdg-open")
        candidate = Path(resolved) if resolved else None
        if candidate is None or not candidate.is_absolute():
            raise RuntimeError("No trusted system folder opener is available.")
        try:
            resolved_opener = candidate.resolve(strict=True)
        except OSError as exc:
            raise RuntimeError("No trusted system folder opener is available.") from exc
        if not resolved_opener.is_file() or not os.access(resolved_opener, os.X_OK):
            raise RuntimeError("No trusted system folder opener is available.")
        opener = str(resolved_opener)

    popen([opener, str(path)])


def capture_own_widget(widget: Any) -> Any:
    """Capture only an owned view; an unavailable optional effect cannot block navigation."""
    width, height = widget.winfo_width(), widget.winfo_height()
    if width < 2 or height < 2 or width * height > 4_000_000:
        return None
    try:
        if is_macos():
            from .platforms.macos.surfaces import capture_own_widget as capture

            return capture(widget, width, height)
        if is_windows():
            from .platforms.windows.surfaces import capture_own_widget as capture

            return capture(widget, width, height)
    except Exception:  # noqa: BLE001 - optional effect cannot block navigation
        return None
    return None


def system_trash_available() -> bool:
    """Recoverable native backends only; never permanent-delete fallback."""
    try:
        if is_macos():
            from .platforms.macos.filesystem import system_trash_available as available

            return available()
        if is_windows():
            from .platforms.windows.filesystem import (
                system_trash_available as available,
            )

            return available()
    except (ImportError, AttributeError, OSError):
        pass
    return False


def trash_file(path: Path) -> str | None:
    """Trash one authorized file, or fail without permanent deletion."""
    if is_macos():
        from .platforms.macos.filesystem import trash_file as trash

        return trash(path)
    if is_windows() and system_trash_available():
        from .platforms.windows.filesystem import trash_file as trash

        return trash(path)
    raise OSError("System Trash is unavailable for this file.")


def surface_backing_scale(widget: Any) -> int:
    """Native raster backing scale; separate from typography and Tk scaling."""
    if is_macos():
        from .platforms.macos.surfaces import surface_backing_scale as backing_scale

        return backing_scale(widget)
    return 1


def create_surface_image(
    widget: Any,
    bitmap: Any,
    scale: int,
    *,
    logical_size: tuple[int, int] | None = None,
    existing: Any = None,
) -> tuple[Any, int]:
    """Use native pixel backing when supported; preserve common Tk fallback."""
    from PIL import Image, ImageTk

    width, height = logical_size if logical_size is not None else bitmap.size
    if is_macos() and scale > 1:
        from .platforms.macos.surfaces import create_surface_image as native_image

        result = native_image(
            widget, bitmap, scale, logical_size=(width, height), existing=existing
        )
        if result is not None:
            return result
    fallback = (
        bitmap
        if bitmap.size == (width, height)
        else bitmap.resize((width, height), Image.Resampling.LANCZOS)
    )
    if isinstance(existing, ImageTk.PhotoImage) and (
        existing.width(),
        existing.height(),
    ) == (width, height):
        existing.paste(fallback)
        return existing, width * height * 4
    return ImageTk.PhotoImage(fallback, master=widget), width * height * 4


def present_pending_drawing(widget: Any, *, child_canvas_only: bool = False) -> bool:
    """Bounded platform drawing before a shared surface becomes visible."""
    if is_macos():
        from .platforms.macos.surfaces import present_pending_drawing as present

        return present(widget, child_canvas_only=child_canvas_only)
    return True


# Scrolling needs explicit drawing only for embedded child viewports; complete
# destination reveals use the same owner for all widget layouts.
def present_scrolled_canvas(widget: Any) -> None:
    present_pending_drawing(widget, child_canvas_only=True)


def integrate_main_window(
    window: Any, title: str, diagnostic: Callable[[str], None]
) -> bool:
    """Keep common title semantics; native header integration requires Aqua."""
    if window.tk.call("tk", "windowingsystem") != "aqua":
        window.title(title)
        window._native_toolbar_header = False
        return False
    from .platforms.macos.windowing import integrate_main_window as integrate

    return integrate(window, title, diagnostic)
