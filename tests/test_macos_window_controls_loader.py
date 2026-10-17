"""Native receiver ownership and fail-closed packaged ABI admission."""

import ctypes
from types import SimpleNamespace

import pytest

from yt_downloader.platforms.macos import window_controls as owner


class Function:
    def __init__(self, callback):
        self.callback = callback

    def __call__(self, *args):
        return self.callback(*args)


def library(calls, *, version=2, pointer=51, close_allowed=True):
    def destroy(handle):
        calls.append("destroy")
        if not close_allowed:
            return 0
        ctypes.cast(handle, ctypes.POINTER(ctypes.c_void_p))[0] = None
        return 1

    return SimpleNamespace(
        vf_window_controls_abi_version=Function(lambda: version),
        vf_window_controls_diagnostic_reason=Function(lambda: 8),
        vf_window_controls_diagnostic_geometry=Function(
            lambda i: float("nan") if i == 0 else float(i)
        ),
        vf_window_controls_create=Function(
            lambda *args: calls.append(("create", args)) or pointer
        ),
        vf_window_controls_reconcile=Function(lambda _: 1),
        vf_window_controls_status=Function(lambda _: 1),
        vf_window_controls_destroy=Function(destroy),
    )


@pytest.fixture(autouse=True)
def clear_library_cache():
    owner._library.cache_clear()
    yield
    owner._library.cache_clear()


def window(calls, *, reject_connection=False):
    callbacks = []

    def connect(callback):
        if reject_connection:
            raise RuntimeError("Qt parent gone")
        callbacks.append(callback)

    return SimpleNamespace(
        destroyed=SimpleNamespace(
            connect=connect, disconnect=lambda _: calls.append("disconnect")
        )
    ), callbacks


@pytest.mark.parametrize("close_route", ["explicit", "parent_destroyed"])
def test_exact_receiver_is_closed_once_and_late_callback_is_inert(
    monkeypatch, close_route
):
    calls = []
    native = library(calls)
    monkeypatch.setattr(owner.ctypes, "CDLL", lambda path: native)
    parent, callbacks = window(calls)
    controls = owner.WindowControls(parent, 73)
    assert calls == [("create", (73, 18.0, 18.0))]
    assert native.vf_window_controls_create.restype is ctypes.c_void_p
    assert native.vf_window_controls_create.argtypes == [
        ctypes.c_void_p,
        ctypes.c_double,
        ctypes.c_double,
    ]
    assert not controls.closed
    if close_route == "explicit":
        controls.close()
    else:
        callbacks[0](parent)
    controls.close()
    callbacks[0](parent)  # already queued destruction must not reuse native handle
    assert controls.closed
    assert calls.count("destroy") == 1
    assert calls.count("disconnect") == 1


@pytest.mark.parametrize("reason", ["absent", "wrong_abi", "missing_symbol"])
def test_missing_or_incompatible_helper_never_creates_native_owner(monkeypatch, reason):
    calls = []
    native = library(calls, version=1 if reason == "wrong_abi" else 2)
    if reason == "missing_symbol":
        del native.vf_window_controls_destroy

    def load(path):
        assert path == str(owner._LIBRARY)
        if reason == "absent":
            raise OSError("No packaged helper")
        return native

    monkeypatch.setattr(owner.ctypes, "CDLL", load)
    parent, _ = window(calls)
    with pytest.raises((OSError, RuntimeError, AttributeError)):
        owner.WindowControls(parent, 73)
    assert not calls
    assert parent._native_header_diagnostic == {
        "stage": "load_library" if reason == "absent" else "bind_abi",
        "helper_exists": owner._LIBRARY.is_file(),
        "reason": {
            "absent": "library_open_failed"
            if owner._LIBRARY.is_file()
            else "file_missing",
            "wrong_abi": "abi_mismatch",
            "missing_symbol": "export_missing",
        }[reason],
        "exception_class": {
            "absent": "OSError",
            "wrong_abi": "RuntimeError",
            "missing_symbol": "AttributeError",
        }[reason],
    }


@pytest.mark.parametrize("failure", ["null_receiver", "refused_layout", "signal"])
def test_constructor_failure_does_not_leak_an_acquired_owner(monkeypatch, failure):
    calls = []
    native = library(calls, pointer=0 if failure == "refused_layout" else 51)
    monkeypatch.setattr(owner.ctypes, "CDLL", lambda _: native)
    parent, _ = window(calls, reject_connection=failure == "signal")
    with pytest.raises(RuntimeError):
        owner.WindowControls(parent, 0 if failure == "null_receiver" else 73)
    assert calls.count("destroy") == (1 if failure == "signal" else 0)


def test_wrong_thread_close_refusal_preserves_handle_for_gui_cleanup(monkeypatch):
    calls = []
    native = library(calls, close_allowed=False)
    monkeypatch.setattr(owner.ctypes, "CDLL", lambda _: native)
    parent, _ = window(calls)
    controls = owner.WindowControls(parent, 73)
    with pytest.raises(RuntimeError, match="GUI-thread"):
        controls.close()
    assert not controls.closed
    assert "disconnect" not in calls
    # A failed close is not falsely treated as completion; normal GUI cleanup
    # remains possible using the same exact receiver.
    native.vf_window_controls_destroy = library(calls).vf_window_controls_destroy
    controls.close()
    assert controls.closed


def test_null_constructor_preserves_static_bounded_diagnostic(monkeypatch):
    native = library([], pointer=0)
    monkeypatch.setattr(owner.ctypes, "CDLL", lambda _: native)
    parent, _ = window([])
    with pytest.raises(RuntimeError):
        owner.WindowControls(parent, 73)
    assert parent._native_header_diagnostic["reason"] == "target_outside_parent"
    assert parent._native_header_diagnostic["geometry"] == [None] + list(
        map(float, range(1, 40))
    )


@pytest.mark.parametrize("present", [False, True])
def test_library_open_diagnostic_discriminates_exact_fixed_file(
    monkeypatch, tmp_path, present
):
    path = tmp_path / "fixed-helper.dylib"
    if present:
        path.write_bytes(b"diagnostic-only invalid library")
    monkeypatch.setattr(owner, "_LIBRARY", path)

    def fail(_):
        raise OSError("private path and arbitrary loader text must not escape")

    monkeypatch.setattr(owner.ctypes, "CDLL", fail)
    parent, _ = window([])
    with pytest.raises(OSError):
        owner.WindowControls(parent, 73)
    assert parent._native_header_diagnostic == {
        "stage": "load_library",
        "exception_class": "OSError",
        "helper_exists": present,
        "reason": "library_open_failed" if present else "file_missing",
    }
