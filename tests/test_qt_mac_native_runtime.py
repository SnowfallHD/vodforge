"""Foreign-address prototypes must never create executable Python callbacks."""

import ctypes
from types import SimpleNamespace

import pytest

from yt_downloader.platforms.macos import native_runtime as runtime


def test_message_wraps_existing_address_and_exact_signature(monkeypatch):
    calls = []
    native = SimpleNamespace(
        objc_msgSend=ctypes.c_void_p(0x123400),
        sel_registerName=lambda name: calls.append(("selector", name)) or 17,
    )
    monkeypatch.setattr(runtime, "_runtime", lambda: native)

    def prototype(restype, *argtypes):
        calls.append(("signature", restype, argtypes))

        def address(pointer):
            assert isinstance(pointer, int) and not callable(pointer)
            calls.append(("foreign_address", pointer))
            return lambda *args: calls.append(("call", args)) or 23

        return address

    monkeypatch.setattr(ctypes, "CFUNCTYPE", prototype)
    runtime._message.cache_clear()
    try:
        assert runtime.send(11, b"setThing:", ctypes.c_bool, (ctypes.c_long,), 9) == 23
        assert ("foreign_address", 0x123400) in calls
        assert (
            "signature",
            ctypes.c_bool,
            (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long),
        ) in calls
        assert ("call", (11, 17, 9)) in calls
    finally:
        runtime._message.cache_clear()


def test_struct_return_is_refused_before_abi_dispatch(monkeypatch):
    class Rect(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double)]

    monkeypatch.setattr(
        runtime, "_runtime", lambda: pytest.fail("unsafe ABI dispatched")
    )
    with pytest.raises(TypeError, match="Struct-returning"):
        runtime.send(1, b"frame", Rect)


def test_missing_runtime_message_address_is_refused(monkeypatch):
    monkeypatch.setattr(
        runtime, "_runtime", lambda: SimpleNamespace(objc_msgSend=ctypes.c_void_p())
    )
    runtime._message.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="unavailable"):
            runtime._message(ctypes.c_bool, ())
    finally:
        runtime._message.cache_clear()


@pytest.mark.parametrize("kind", ["class", "selector"])
def test_missing_required_class_or_selector_is_refused(monkeypatch, kind):
    monkeypatch.setattr(
        runtime,
        "_runtime",
        lambda: SimpleNamespace(
            objc_getClass=lambda _: 0, sel_registerName=lambda _: 0
        ),
    )
    function = runtime.class_pointer if kind == "class" else runtime.selector_pointer
    with pytest.raises(RuntimeError, match="unavailable"):
        function(b"missing")
