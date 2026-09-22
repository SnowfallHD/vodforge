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


@pytest.mark.parametrize(
    "variant",
    ["opaque", "transparent", "other-format", "short-buffer", "unsized-buffer"],
)
def test_native_bitmap_snapshot_preserves_pixels_and_detaches_ownership(
    monkeypatch, variant
):
    import io
    import sys

    from PIL import Image

    colors = [
        (230, 20, 40, 255),
        (10, 220, 70, 255),
        (30, 60, 240, 255),
        (200, 150, 20, 255),
    ]
    if variant == "transparent":
        colors[0] = (230, 20, 40, 128)
    expected = Image.new("RGBA", (2, 2))
    expected.putdata(colors)
    raw = bytearray(
        bytes(colors[0])
        + bytes(colors[1])
        + b"pad!"
        + bytes(colors[2])
        + bytes(colors[3])
        + b"pad!"
    )
    if variant == "short-buffer":
        raw = raw[:3]
    encoded = io.BytesIO()
    expected.save(encoded, format="PNG")
    encodings = []

    def encode(*_args):
        encodings.append(True)
        return encoded.getvalue()

    rep = SimpleNamespace(
        pixelsWide=lambda: 2,
        pixelsHigh=lambda: 2,
        bytesPerRow=lambda: 12,
        bitsPerSample=lambda: 8,
        samplesPerPixel=lambda: 4,
        bitsPerPixel=lambda: 32,
        bitmapFormat=lambda: 1 if variant == "other-format" else 0,
        isPlanar=lambda: False,
        bitmapData=lambda: object() if variant == "unsized-buffer" else memoryview(raw),
        representationUsingType_properties_=encode,
    )
    monkeypatch.setitem(
        sys.modules, "AppKit", SimpleNamespace(NSBitmapImageFileTypePNG=4)
    )
    from yt_downloader.platforms.macos.surfaces import _bitmap_rep_image

    image = _bitmap_rep_image(rep)
    raw[:] = bytes(len(raw))
    assert image.tobytes() == expected.tobytes(), (
        "Returned image borrowed mutable native storage"
    )
    assert len(encodings) == (0 if variant == "opaque" else 1)


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
for name in ("platforms.macos.windowing", "platforms.macos.player_overlay", "platforms.windows.video_host", "platforms.windows.update_recovery", "platforms.macos.surfaces", "platforms.macos.filesystem", "platforms.windows.surfaces", "platforms.windows.filesystem", "platforms.windows.windowing", "platforms.windows.dialogs", "platforms.windows.processes"):
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
        "source_line": 2,
        "source_scope": "first_party_frame",
    }
    assert "sentinel" not in str(detail)
    namespace["__name__"] = "yt_downloader.platforms.macos.private_user_module"
    try:
        namespace["fail"]()
    except RuntimeError as error:
        assert _first_party_location(error) == {}


@pytest.mark.parametrize("size", [(1, 40), (40, 1), (4000, 4000)])
def test_optional_capture_rejects_invalid_geometry_before_platform_call(
    size, monkeypatch
):
    from yt_downloader.platforms.windows import surfaces

    monkeypatch.setattr(platform_module, "is_windows", lambda: True)
    monkeypatch.setattr(platform_module, "is_macos", lambda: False)
    monkeypatch.setattr(
        surfaces,
        "capture_own_widget",
        lambda *_args: pytest.fail("Invalid capture reached native adapter"),
    )
    widget = SimpleNamespace(winfo_width=lambda: size[0], winfo_height=lambda: size[1])
    assert platform_module.capture_own_widget(widget) is None
