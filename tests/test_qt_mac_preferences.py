"""Exercise native preference admission without importing Python AppKit."""

import builtins
import ctypes
import importlib

import pytest

from yt_downloader.qt_quick import mac_preferences, main


@pytest.mark.parametrize("preference", [False, True])
def test_preference_uses_native_calls_without_python_appkit(monkeypatch, preference):
    imports = builtins.__import__

    def no_python_bridge(name, *args, **kwargs):
        assert name not in {"AppKit", "objc", "Foundation"}
        return imports(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_python_bridge)
    dynamic_import = importlib.import_module

    def no_dynamic_bridge(name, *args, **kwargs):
        assert name not in {"AppKit", "objc", "Foundation"}
        return dynamic_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", no_dynamic_bridge)
    monkeypatch.setattr(mac_preferences.sys, "platform", "darwin")
    calls = []

    def send(receiver, selector, restype):
        calls.append((receiver, selector, restype))
        return 22 if selector == b"sharedWorkspace" else preference

    monkeypatch.setattr(
        mac_preferences.native,
        "class_pointer",
        lambda name: 11 if name == b"NSWorkspace" else 0,
    )
    monkeypatch.setattr(mac_preferences.native, "send", send)
    assert main._system_reduced_motion() is preference
    assert calls == [
        (11, b"sharedWorkspace", ctypes.c_void_p),
        (22, b"accessibilityDisplayShouldReduceMotion", ctypes.c_bool),
    ]


def test_nonmac_does_not_load_native_libraries(monkeypatch):
    monkeypatch.setattr(mac_preferences.sys, "platform", "win32")
    monkeypatch.setattr(
        mac_preferences.native, "class_pointer", lambda _: pytest.fail("loaded")
    )
    assert not mac_preferences.system_reduced_motion()


@pytest.mark.parametrize("missing", ["class", "workspace", "library"])
def test_unavailable_native_preference_fails_closed(monkeypatch, missing):
    monkeypatch.setattr(mac_preferences.sys, "platform", "darwin")
    calls = []

    def class_pointer(_):
        if missing == "library":
            raise OSError("framework unavailable")
        return 0 if missing == "class" else 11

    monkeypatch.setattr(mac_preferences.native, "class_pointer", class_pointer)
    monkeypatch.setattr(
        mac_preferences.native, "send", lambda *args: calls.append(args) or 0
    )
    assert not mac_preferences.system_reduced_motion()
    assert len(calls) == (1 if missing == "workspace" else 0)
