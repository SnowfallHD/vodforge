from __future__ import annotations

import json
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


def is_windows(platform_name: str | None = None) -> bool:
    """Return whether the requested or running platform uses Windows behavior."""
    value = sys.platform if platform_name is None else platform_name
    return value.startswith("win")


def is_macos(platform_name: str | None = None) -> bool:
    """Return whether the requested or running platform uses macOS behavior."""
    value = sys.platform if platform_name is None else platform_name
    return value == "darwin"


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
    """Give Windows a stable taskbar identity instead of a Python/Tk fallback."""
    if not is_windows(platform_name):
        return False
    import ctypes

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(  # type: ignore[attr-defined]
        "SnowfallHD.VODForge"
    )
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


def hidden_window_subprocess_kwargs(
    platform_name: str | None = None,
) -> dict[str, Any]:
    """Return the one shared policy for console-free child processes on Windows."""
    startupinfo = None
    creationflags = 0
    if is_windows(platform_name):
        startupinfo = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return {"startupinfo": startupinfo, "creationflags": creationflags}


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
    result = runner(
        ["powershell.exe", "-NoProfile", "-STA", "-Command", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        **hidden_window_subprocess_kwargs("win32"),
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
    platform_name: str | None = None,
    popen: Callable[[list[str]], Any] = subprocess.Popen,
    which: Callable[[str], str | None] = shutil.which,
    startfile: Callable[[Path], Any] | None = None,
) -> None:
    """Open a folder without deferring executable selection to subprocess PATH lookup."""
    path.mkdir(parents=True, exist_ok=True)
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
