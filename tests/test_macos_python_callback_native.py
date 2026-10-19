"""Native header callbacks must not allocate executable libffi trampolines."""

from __future__ import annotations

import ctypes
import subprocess
import sys
import weakref
from pathlib import Path
from types import SimpleNamespace

import pytest

from yt_downloader.platforms.macos import header_host


def test_header_callback_registration_does_not_allocate_runtime_trampoline(monkeypatch):
    def forbidden(*_args):
        raise AssertionError("runtime executable callback allocation")

    monkeypatch.setattr(header_host, "_CHANGE_CALLBACK", forbidden, raising=False)
    calls = []
    native = SimpleNamespace(
        vf_header_host_set_python_callback=lambda *args: calls.append(args) or 1
    )
    host = object.__new__(header_host.HeaderHost)
    host._library = native
    host._handle = ctypes.c_void_p(1)
    host._callback = None
    callback = lambda: None
    host.set_change_callback(callback)
    assert len(calls) == 1
    assert calls[0][1] == id(callback)
    host.set_change_callback(None)
    assert len(calls) == 2
    assert calls[1][1] is None


@pytest.fixture(scope="module")
def native_callback_library(tmp_path_factory):
    if sys.platform != "darwin":
        pytest.skip("macOS native callback bridge")
    root = Path(__file__).resolve().parents[1]
    output = tmp_path_factory.mktemp("python-native-callback") / "helper.dylib"
    subprocess.run(
        [
            "xcrun",
            "clang",
            "-dynamiclib",
            "-fno-objc-arc",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-framework",
            "AppKit",
            "-framework",
            "QuartzCore",
            str(root / "yt_downloader/platforms/macos/header_toolbar.m"),
            "-o",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return output


def test_actual_compiled_python_callback_and_reference_lifetime(
    native_callback_library, monkeypatch
):
    monkeypatch.setattr(header_host, "_LIBRARY", native_callback_library)
    header_host._library.cache_clear()
    try:
        appkit = ctypes.CDLL("/System/Library/Frameworks/AppKit.framework/AppKit")
        assert ctypes.c_void_p.in_dll(appkit, "NSApp").value is None
        observed = []
        callback = lambda: observed.append("called")
        ref = weakref.ref(callback)
        api = header_host._python_api()
        library = header_host._library()
        assert (
            library.vf_header_host_python_callback_smoke(
                id(callback), ctypes.byref(api), ctypes.sizeof(api)
            )
            == 1
        )
        assert observed == ["called"]
        del callback
        assert ref() is None
        assert ctypes.c_void_p.in_dll(appkit, "NSApp").value is None
    finally:
        header_host._library.cache_clear()


def test_actual_compiled_python_callback_error_and_invalid_api(
    native_callback_library, monkeypatch
):
    monkeypatch.setattr(header_host, "_LIBRARY", native_callback_library)
    header_host._library.cache_clear()
    try:
        library = header_host._library()
        api = header_host._python_api()

        def raises():
            raise RuntimeError("fictional callback failure")

        assert (
            library.vf_header_host_python_callback_smoke(
                id(raises), ctypes.byref(api), ctypes.sizeof(api)
            )
            == 0
        )
        assert (
            library.vf_header_host_python_callback_smoke(
                None, ctypes.byref(api), ctypes.sizeof(api)
            )
            == 0
        )
        assert (
            library.vf_header_host_python_callback_smoke(
                id(raises), ctypes.byref(api), 1
            )
            == 0
        )
        invalid = header_host.PythonAPI()
        assert (
            library.vf_header_host_python_callback_smoke(
                id(raises), ctypes.byref(invalid), ctypes.sizeof(invalid)
            )
            == 0
        )
        assert (
            library.vf_header_host_set_python_callback(
                None, id(raises), ctypes.byref(api), ctypes.sizeof(api)
            )
            == 0
        )
    finally:
        header_host._library.cache_clear()
