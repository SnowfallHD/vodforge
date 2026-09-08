from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import yt_downloader.app as app_module
import yt_downloader.platform_services as platform_module
from yt_downloader.app import DownloaderApp
from yt_downloader.platform_services import (
    choose_output_directory,
    hidden_window_subprocess_kwargs,
    install_native_quit_handler,
    open_path,
    output_directory_failure_guidance,
)


@pytest.mark.parametrize("accepted", [False, True])
def test_native_foreground_targets_wrapper_once_and_respects_refusal(
    monkeypatch, accepted
):
    import ctypes

    calls = []

    def ancestor(hwnd, flag):
        calls.append(("ancestor", hwnd, flag))
        return 12345

    def foreground(hwnd):
        calls.append(("foreground", hwnd))
        return accepted

    def flash(pointer):
        info = pointer._obj
        assert info.cbSize == ctypes.sizeof(info)
        calls.append(("flash", info.hwnd, info.dwFlags, info.uCount, info.dwTimeout))
        return False  # The native result is previous activation, not success.

    monkeypatch.setattr(platform_module, "is_windows", lambda: True)
    monkeypatch.setattr(platform_module, "is_macos", lambda: False)
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: SimpleNamespace(
            GetAncestor=ancestor, SetForegroundWindow=foreground, FlashWindowEx=flash
        ),
        raising=False,
    )
    root = SimpleNamespace(lift=lambda: calls.append("lift"), winfo_id=lambda: 42)
    assert platform_module.request_window_foreground(root) is accepted
    expected = ["lift", ("ancestor", 42, 2), ("foreground", 12345)]
    if not accepted:
        expected.append(("flash", 12345, 2, 3, 0))
    assert calls == expected


@pytest.mark.parametrize("modern", [True, False])
def test_macos_activation_uses_supported_appkit_api(monkeypatch, modern):
    import sys

    calls = []
    application = SimpleNamespace(
        respondsToSelector_=lambda selector: modern and selector == "activate",
        activate=lambda: calls.append("activate"),
        activateIgnoringOtherApps_=lambda flag: calls.append(("legacy", flag)),
        isActive=lambda: True,
    )
    monkeypatch.setattr(platform_module, "is_macos", lambda: True)
    monkeypatch.setitem(
        sys.modules,
        "AppKit",
        SimpleNamespace(
            NSApplication=SimpleNamespace(sharedApplication=lambda: application)
        ),
    )
    assert platform_module.request_window_foreground(
        SimpleNamespace(lift=lambda: calls.append("lift"))
    )
    assert calls == ["lift", "activate" if modern else ("legacy", True)]


def test_native_quit_routes_only_macos_application_menu_through_callback():
    registered: list[tuple[str, object]] = []
    root = type(
        "Root",
        (),
        {
            "createcommand": lambda _self, name, callback: registered.append(
                (name, callback)
            )
        },
    )()
    callback = lambda: None

    assert install_native_quit_handler(root, callback, platform_name="darwin") is True
    assert registered == [("::tk::mac::Quit", callback)]
    assert install_native_quit_handler(root, callback, platform_name="linux") is False
    assert registered == [("::tk::mac::Quit", callback)]


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
