from __future__ import annotations

from pathlib import Path

import pytest

import yt_downloader.app as app_module
from yt_downloader.app import DownloaderApp
from yt_downloader.platform_services import open_path


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
