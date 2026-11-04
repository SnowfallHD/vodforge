from __future__ import annotations

import os
import shutil

# This service accepts only a fixed or resolved executable and never invokes a shell.
import subprocess  # nosec B404
import sys
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


def is_windows(platform_name: str | None = None) -> bool:
    """Return whether the requested or running platform uses Windows behavior."""
    value = sys.platform if platform_name is None else platform_name
    return value.startswith("win")


def is_macos(platform_name: str | None = None) -> bool:
    """Return whether the requested or running platform uses macOS behavior."""
    value = sys.platform if platform_name is None else platform_name
    return value == "darwin"


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
    return "Sans Serif", "Monospace"


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


# Scrolling needs explicit drawing only for embedded child viewports; complete
# destination reveals use the same owner for all widget layouts.
