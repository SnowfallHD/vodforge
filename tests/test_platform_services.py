from __future__ import annotations

from pathlib import Path

import pytest

from yt_downloader.platform_services import (
    choose_output_directory,
    hidden_window_subprocess_kwargs,
    open_path,
    output_directory_failure_guidance,
)


def test_hidden_window_subprocess_policy_is_empty_off_windows():
    assert hidden_window_subprocess_kwargs("darwin") == {
        "startupinfo": None,
        "creationflags": 0,
    }


def test_output_picker_routes_to_one_platform_owner():
    calls: list[tuple[str, str]] = []

    assert (
        choose_output_directory(
            "/initial",
            platform_name="linux",
            standard_picker=lambda path: (
                calls.append(("standard", path)) or "/standard"
            ),
            windows_picker=lambda path: calls.append(("windows", path)) or "/windows",
        )
        == "/standard"
    )
    assert (
        choose_output_directory(
            "/initial",
            platform_name="win32",
            standard_picker=lambda path: (
                calls.append(("standard", path)) or "/standard"
            ),
            windows_picker=lambda path: calls.append(("windows", path)) or "/windows",
        )
        == "/windows"
    )
    assert calls == [("standard", "/initial"), ("windows", "/initial")]


def test_output_picker_failure_guidance_keeps_windows_network_path_help():
    assert "\\\\server\\share" in output_directory_failure_guidance("win32")
    assert "type or paste" in output_directory_failure_guidance("linux")


def test_macos_folder_open_uses_the_absolute_system_executable(tmp_path: Path):
    commands: list[list[str]] = []
    folder = tmp_path / "folder"

    open_path(
        folder,
        platform_name="darwin",
        popen=commands.append,
    )

    assert folder.is_dir()
    assert commands == [["/usr/bin/open", str(folder)]]


def test_linux_folder_open_resolves_xdg_open_once_before_launch(tmp_path: Path):
    opener = tmp_path / "bin" / "xdg-open"
    opener.parent.mkdir()
    opener.write_text("#!/bin/sh\n", encoding="utf-8")
    opener.chmod(0o700)
    commands: list[list[str]] = []
    folder = tmp_path / "folder"

    open_path(
        folder,
        platform_name="linux",
        popen=commands.append,
        which=lambda _name: str(opener),
    )

    assert commands == [[str(opener.resolve()), str(folder)]]


@pytest.mark.parametrize("resolved", [None, "xdg-open"])
def test_linux_folder_open_rejects_missing_or_relative_opener(
    tmp_path: Path,
    resolved: str | None,
):
    commands: list[list[str]] = []

    with pytest.raises(RuntimeError, match="trusted system folder opener"):
        open_path(
            tmp_path / "folder",
            platform_name="linux",
            popen=commands.append,
            which=lambda _name: resolved,
        )

    assert commands == []


def test_windows_folder_open_uses_startfile_without_a_subprocess(tmp_path: Path):
    opened: list[Path] = []
    folder = tmp_path / "folder"

    open_path(
        folder,
        platform_name="win32",
        popen=lambda _command: pytest.fail("Windows must not start a shell opener"),
        startfile=opened.append,
    )

    assert opened == [folder]


def test_named_native_adapters_import_without_loading_foreign_native_libraries():
    """Import dispatch never initializes the other OS's native runtime."""
    import subprocess
    import sys

    script = """
import importlib
import importlib.abc
import subprocess  # Standard library probes msvcrt availability itself.
import sys
class ForeignNativeImport(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        forbidden = {"AppKit", "Foundation", "objc", "Quartz"} if sys.platform == "win32" else {"msvcrt", "win32api", "win32gui"}
        if fullname.split(".")[0] in forbidden:
            raise AssertionError("foreign native import: " + fullname)
sys.meta_path.insert(0, ForeignNativeImport())
for name in ("platforms.windows.video_host", "platforms.windows.update_recovery", "platforms.macos.filesystem", "platforms.windows.surfaces", "platforms.windows.filesystem", "platforms.windows.windowing", "platforms.windows.dialogs", "platforms.windows.processes"):
    importlib.import_module("yt_downloader." + name)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_relocated_native_failure_keeps_closed_diagnostic_label():
    from yt_downloader.failure_diagnostics import _first_party_location

    namespace = {"__name__": "yt_downloader.platforms.macos.player_overlay"}
    exec(  # noqa: S102 - fixed synthetic traceback fixture
        compile(
            "def fail():\n    raise RuntimeError('private-path-sentinel')\n",
            "private-file-sentinel",
            "exec",
        ),
        namespace,
    )
    try:
        namespace["fail"]()
    except RuntimeError as error:
        detail = _first_party_location(error)
    assert detail == {
        "source_module": "player_overlay_macos",
        "source_trace": "player_overlay_macos:2",
        "source_line": 2,
        "source_scope": "first_party_frame",
    }
    assert "sentinel" not in str(detail)
    namespace["__name__"] = "yt_downloader.platforms.macos.private_user_module"
    try:
        namespace["fail"]()
    except RuntimeError as error:
        assert _first_party_location(error) == {}


def test_qt_failure_location_keeps_closed_module_without_private_context():
    from yt_downloader.failure_diagnostics import _first_party_location

    namespace = {"__name__": "yt_downloader.qt_quick.local_conversion"}
    exec(  # noqa: S102 - fixed synthetic traceback fixture
        compile(
            "def fail():\n    raise RuntimeError('private-path-sentinel')\n",
            "private-file-sentinel",
            "exec",
        ),
        namespace,
    )
    try:
        namespace["fail"]()
    except RuntimeError as error:
        detail = _first_party_location(error)
    assert detail == {
        "source_module": "qt_quick.local_conversion",
        "source_trace": "qt_quick.local_conversion:2",
        "source_line": 2,
        "source_scope": "first_party_frame",
    }
    assert "sentinel" not in str(detail)
    namespace["__name__"] = "yt_downloader.qt_quick.private_user_module"
    try:
        namespace["fail"]()
    except RuntimeError as error:
        assert _first_party_location(error) == {}
