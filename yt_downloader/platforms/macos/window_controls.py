"""Load the packaged AppKit window-control owner without native Python callbacks.

The library is produced explicitly by the Mac build recipes. App startup never
compiles code, searches for a helper, or changes process security permissions.
"""

from __future__ import annotations

import ctypes
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

_POINTER = ctypes.c_void_p
_LIBRARY = Path(__file__).with_name("libvodforge_fullscreen.dylib")


@lru_cache(maxsize=1)
def _library():
    try:
        library = ctypes.CDLL(str(_LIBRARY))
    except Exception as exc:
        exc.__dict__["native_window_stage"] = "load_library"
        exc.__dict__["native_window_reason"] = (
            "library_open_failed" if _LIBRARY.is_file() else "file_missing"
        )
        raise
    signatures = {
        "vf_window_controls_abi_version": (ctypes.c_uint, []),
        "vf_window_controls_diagnostic_reason": (ctypes.c_int, []),
        "vf_window_controls_diagnostic_geometry": (ctypes.c_double, [ctypes.c_uint]),
        "vf_window_controls_create": (
            _POINTER,
            [_POINTER, ctypes.c_double, ctypes.c_double],
        ),
        "vf_window_controls_reconcile": (ctypes.c_int, [_POINTER]),
        "vf_window_controls_status": (ctypes.c_int, [_POINTER]),
        "vf_window_controls_destroy": (ctypes.c_int, [ctypes.POINTER(_POINTER)]),
    }
    try:
        for name, (result, arguments) in signatures.items():
            function = getattr(library, name)
            function.restype = result
            function.argtypes = arguments
        if library.vf_window_controls_abi_version() != 2:
            raise RuntimeError("Incompatible native window-control helper")
    except Exception as exc:
        exc.__dict__["native_window_stage"] = "bind_abi"
        exc.__dict__["native_window_reason"] = (
            "export_missing" if isinstance(exc, AttributeError) else "abi_mismatch"
        )
        raise
    return library


class WindowControls:
    """Bind native ownership to one Qt window and release it exactly once."""

    def __init__(self, window: Any, native_pointer: int) -> None:
        self._window = window
        window._native_header_diagnostic = {"stage": "load_library"}
        try:
            self._library = _library()
        except Exception as exc:
            window._native_header_diagnostic = {
                "stage": getattr(exc, "native_window_stage", "load_library"),
                "exception_class": type(exc).__name__,
                "helper_exists": _LIBRARY.is_file(),
                "reason": getattr(exc, "native_window_reason", "library_open_failed"),
            }
            raise
        self._handle = _POINTER()
        if not native_pointer:
            window._native_header_diagnostic = {"stage": "native_receiver"}
            raise RuntimeError("Native window-control receiver is unavailable")
        # Match the established compact header's optical traffic-light inset.
        # The native owner preserves measured system spacing and refuses any
        # target that does not fit all three existing parent bounds.
        window._native_header_diagnostic = {"stage": "native_create"}
        self._handle.value = self._library.vf_window_controls_create(
            native_pointer, 18.0, 18.0
        )
        if not self._handle.value:
            reasons = (
                "success",
                "wrong_thread",
                "invalid_args",
                "appearance_unavailable",
                "content_invalid",
                "button_invalid",
                "parent_invalid",
                "target_invalid",
                "target_outside_parent",
                "identity_changed",
                "setter_exception",
                "native_exception",
                "support_transaction_refused",
            )
            reason = self._library.vf_window_controls_diagnostic_reason()
            values = [
                self._library.vf_window_controls_diagnostic_geometry(i)
                for i in range(40)
            ]
            window._native_header_diagnostic = {
                "stage": "native_create",
                "reason": reasons[reason] if 0 <= reason < len(reasons) else "unknown",
                "geometry": [
                    v if math.isfinite(v) and abs(v) <= 1e7 else None for v in values
                ],
            }
            raise RuntimeError("Native window-control layout was not admitted")
        try:
            window._native_header_diagnostic = {"stage": "connect_destroyed"}
            window.destroyed.connect(self.close)
        except Exception:
            self.close()
            raise

    @property
    def closed(self) -> bool:
        return not self._handle.value

    def close(self, *_destroyed) -> None:
        if self.closed:
            return
        # The compiled owner checks the GUI thread before touching AppKit and
        # invalidates this handle before releasing its exact native receivers.
        if self._library.vf_window_controls_destroy(ctypes.byref(self._handle)) != 1:
            raise RuntimeError("Native window controls require GUI-thread closure")
        try:
            self._window.destroyed.disconnect(self.close)
        except (RuntimeError, TypeError):
            pass  # Qt may already be destroying the signal's parent.
