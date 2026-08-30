from __future__ import annotations

from pathlib import Path

import pytest

import yt_downloader.app as app_module
import yt_downloader.platform_services as platform_module
from yt_downloader.app import DownloaderApp
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


def test_hidden_window_subprocess_policy_is_shared_on_windows(
    monkeypatch: pytest.MonkeyPatch,
):
    class StartupInfo:
        dwFlags = 4

    monkeypatch.setattr(
        platform_module.subprocess, "STARTUPINFO", StartupInfo, raising=False
    )
    monkeypatch.setattr(
        platform_module.subprocess, "STARTF_USESHOWWINDOW", 8, raising=False
    )
    monkeypatch.setattr(
        platform_module.subprocess, "CREATE_NO_WINDOW", 16, raising=False
    )

    options = hidden_window_subprocess_kwargs("win32")

    assert isinstance(options["startupinfo"], StartupInfo)
    assert options["startupinfo"].dwFlags == 12
    assert options["creationflags"] == 16


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


def test_downloader_app_delegates_folder_opening_to_the_platform_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    opened: list[Path] = []
    monkeypatch.setattr(app_module, "open_system_path", opened.append)

    DownloaderApp._open_path(tmp_path / "folder")

    assert opened == [tmp_path / "folder"]
