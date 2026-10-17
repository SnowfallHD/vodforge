"""Preserve system Trash results without importing the Python Foundation bridge."""

import builtins
import ctypes
from pathlib import Path

import pytest

from yt_downloader.platforms.macos import filesystem


@pytest.fixture
def native_trash(monkeypatch):
    imports = builtins.__import__

    def no_bridge(name, *args, **kwargs):
        assert name not in {"Foundation", "AppKit", "objc"}
        return imports(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_bridge)
    calls = []
    state = {
        "success": True,
        "result": 70,
        "result_bytes": "/Users/fictional/.Trash/影像 café.mp4".encode(),
        "available": True,
    }
    classes = {
        b"NSAutoreleasePool": 10,
        b"NSFileManager": 20,
        b"NSString": 30,
        b"NSURL": 40,
    }
    monkeypatch.setattr(
        filesystem.native, "class_pointer", lambda name: classes.get(name, 0)
    )
    monkeypatch.setattr(
        filesystem.native,
        "selector_pointer",
        lambda name: 123 if name == filesystem._TRASH_SELECTOR else 0,
    )

    def send(receiver, selector, restype, argtypes=(), *args):
        calls.append((receiver, selector, restype, argtypes, args))
        if selector == b"new":
            return 11
        if selector == b"drain":
            return None
        if selector == b"defaultManager":
            return 21
        if selector == b"respondsToSelector:":
            return state["available"]
        if selector == b"stringWithUTF8String:":
            return 31
        if selector == b"fileURLWithPath:":
            return 41
        if selector == filesystem._TRASH_SELECTOR:
            ctypes.cast(args[1], ctypes.POINTER(ctypes.c_void_p))[0] = state["result"]
            ctypes.cast(args[2], ctypes.POINTER(ctypes.c_void_p))[0] = (
                0 if state["success"] else 99
            )
            return state["success"]
        if selector == b"path":
            return 71
        if selector == b"UTF8String":
            return state["result_bytes"]
        pytest.fail(f"Unexpected selector: {selector!r}")

    monkeypatch.setattr(filesystem.native, "send", send)
    return state, calls, classes


@pytest.mark.parametrize("available", [False, True])
def test_trash_availability_is_native_selector_check(native_trash, available):
    state, calls, _ = native_trash
    state["available"] = available
    assert filesystem.system_trash_available() is available
    check = next(c for c in calls if c[1] == b"respondsToSelector:")
    assert check[2:] == (ctypes.c_bool, (ctypes.c_void_p,), (123,))
    assert calls[-1][1] == b"drain"


def test_trash_unicode_source_and_actual_returned_location(native_trash):
    state, calls, _ = native_trash
    path = Path("/tmp/fictional/影像 café.mp4")
    assert filesystem.trash_file(path) == state["result_bytes"].decode()
    string_call = next(c for c in calls if c[1] == b"stringWithUTF8String:")
    assert string_call[3:] == ((ctypes.c_char_p,), (str(path).encode("utf-8"),))
    action = next(c for c in calls if c[1] == filesystem._TRASH_SELECTOR)
    assert action[2:4] == (
        ctypes.c_bool,
        (
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
        ),
    )
    assert calls[-1][1] == b"drain"


def test_trash_nil_result_retains_none_semantics(native_trash):
    state, calls, _ = native_trash
    state["result"] = None
    assert filesystem.trash_file(Path("/tmp/fictional")) is None
    assert not any(c[1] == b"path" for c in calls)
    assert calls[-1][1] == b"drain"


def test_trash_failure_never_claims_a_move(native_trash):
    state, calls, _ = native_trash
    state["success"] = False
    with pytest.raises(OSError, match="could not move"):
        filesystem.trash_file(Path("/tmp/fictional"))
    assert not any(c[1] == b"path" for c in calls)
    assert calls[-1][1] == b"drain"


def test_trash_unavailable_class_refuses_before_operation(native_trash):
    _, calls, classes = native_trash
    classes.pop(b"NSURL")
    with pytest.raises(OSError, match="unavailable"):
        filesystem.trash_file(Path("/tmp/fictional"))
    assert not any(c[1] == filesystem._TRASH_SELECTOR for c in calls)
    assert calls[-1][1] == b"drain"


def test_trash_nul_source_refuses_before_native_call(native_trash):
    _, calls, _ = native_trash
    with pytest.raises(OSError, match="could not move"):
        filesystem.trash_file(Path("/tmp/fictional\0bad"))
    assert calls == []


def test_trash_unreadable_result_is_not_a_fabricated_path(native_trash):
    state, calls, _ = native_trash
    state["result_bytes"] = None
    with pytest.raises(OSError, match="readable Trash"):
        filesystem.trash_file(Path("/tmp/fictional"))
    assert calls[-1][1] == b"drain"
