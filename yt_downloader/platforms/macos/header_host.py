"""Explicit packaged native header ABI; no startup compilation or callbacks."""

from __future__ import annotations

import ctypes
from functools import lru_cache
from pathlib import Path

_POINTER = ctypes.c_void_p
_LIBRARY = Path(__file__).with_name("libvodforge_fullscreen.dylib")


@lru_cache(maxsize=1)
def _library():
    library = ctypes.CDLL(str(_LIBRARY))
    signatures = {
        "abi_version": (ctypes.c_uint, []),
        "create": (_POINTER, [_POINTER] + [ctypes.c_double] * 3),
        "view": (_POINTER, [_POINTER]),
        "state": (ctypes.c_int, [_POINTER]),
        "geometry": (ctypes.c_double, [_POINTER, ctypes.c_uint]),
        "flags": (ctypes.c_uint, [_POINTER]),
        "event_fd": (ctypes.c_int, [_POINTER]),
        "drain": (ctypes.c_int, [_POINTER]),
        "set_height": (ctypes.c_int, [_POINTER, ctypes.c_double]),
        "destroy": (ctypes.c_int, [ctypes.POINTER(_POINTER)]),
    }
    for suffix, (result, arguments) in signatures.items():
        function = getattr(library, "vf_header_host_" + suffix)
        function.restype, function.argtypes = result, arguments
    if library.vf_header_host_abi_version() != 1:
        raise RuntimeError("Incompatible native header host")
    return library


class HeaderHost:
    """One exact native toolbar generation. The descriptor is borrowed."""

    def __init__(self, pointer: int, height: float, gutter: float, minimum: float):
        self._handle = _POINTER()
        self._library = _library()
        self._handle.value = self._library.vf_header_host_create(
            pointer, height, gutter, minimum
        )
        if not self._handle.value:
            raise RuntimeError("Native header host refused creation")

    @property
    def closed(self):
        return not self._handle.value

    @property
    def view(self):
        return self._library.vf_header_host_view(self._handle)

    @property
    def descriptor(self):
        return self._library.vf_header_host_event_fd(self._handle)

    def drain(self):
        return self._library.vf_header_host_drain(self._handle)

    def snapshot(self):
        state = self._library.vf_header_host_state(self._handle)
        flags = self._library.vf_header_host_flags(self._handle)
        values = tuple(
            self._library.vf_header_host_geometry(self._handle, index)
            for index in range(66)
        )
        return state, flags, values

    def set_height(self, height):
        if self._library.vf_header_host_set_height(self._handle, height) != 1:
            raise RuntimeError("Native header height ownership changed")

    def close(self):
        if (
            not self.closed
            and self._library.vf_header_host_destroy(ctypes.byref(self._handle)) != 1
        ):
            raise RuntimeError(
                "Native header teardown refused; retain its exact handle"
            )
