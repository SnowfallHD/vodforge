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
