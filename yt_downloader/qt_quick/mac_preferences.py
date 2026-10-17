"""Read native preferences without constructing Python Objective-C closures."""

from __future__ import annotations

import ctypes
import sys

from yt_downloader.platforms.macos import native_runtime as native


def system_reduced_motion() -> bool:
    """Read NSWorkspace's public preference; never change OS settings.

    Importing Python AppKit registers struct wrappers using executable libffi
    closures. This preference needs only ordinary, typed native function calls.
    """
    if sys.platform != "darwin":
        return False
    try:
        workspace_class = native.class_pointer(b"NSWorkspace")
        if not workspace_class:
            return False
        workspace = native.send(workspace_class, b"sharedWorkspace", ctypes.c_void_p)
        if not workspace:
            return False
        return bool(
            native.send(
                workspace, b"accessibilityDisplayShouldReduceMotion", ctypes.c_bool
            )
        )
    except (OSError, AttributeError, RuntimeError):
        return False
