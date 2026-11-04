"""Load the packaged AppKit window-control owner without native Python callbacks.

The library is produced explicitly by the Mac build recipes. App startup never
compiles code, searches for a helper, or changes process security permissions.
"""

from __future__ import annotations

import ctypes
from functools import lru_cache
from pathlib import Path

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
