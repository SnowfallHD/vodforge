"""Explicit packaged native header ABI; no startup compilation or callbacks."""

from __future__ import annotations

import ctypes
import math
from functools import lru_cache
from pathlib import Path

_POINTER = ctypes.c_void_p
_LIBRARY = Path(__file__).with_name("libvodforge_fullscreen.dylib")


class Snapshot(ctypes.Structure):
    """One public-native generation and geometry transaction, ABI4."""

    _fields_ = [
        ("abi", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("transition", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
        ("host", ctypes.c_uint64),
        ("accessory", ctypes.c_uint64),
        ("delegate", ctypes.c_uint64),
        ("buttons", ctypes.c_uint64 * 3),
        ("geometry", ctypes.c_double * 98),
        ("visible", ctypes.c_double * 12),
        ("visibility", ctypes.c_uint32 * 3),
        ("hostVisible", ctypes.c_uint32),
    ]


@lru_cache(maxsize=1)
def _library():
    library = ctypes.CDLL(str(_LIBRARY))
    signatures = {
        "abi_version": (ctypes.c_uint, []),
        "create": (_POINTER, [_POINTER] + [ctypes.c_double] * 3),
        "view": (_POINTER, [_POINTER]),
        "row_snapshot": (ctypes.c_int, [_POINTER, ctypes.POINTER(Snapshot)]),
        "row_snapshot_size": (ctypes.c_size_t, []),
        "event_fd": (ctypes.c_int, [_POINTER]),
        "drain": (ctypes.c_int, [_POINTER]),
        "set_height": (ctypes.c_int, [_POINTER, ctypes.c_double]),
        "destroy": (ctypes.c_int, [ctypes.POINTER(_POINTER)]),
        "bind_child": (ctypes.c_int, [_POINTER, _POINTER] + [ctypes.c_double] * 4),
        "update_child": (ctypes.c_int, [_POINTER, _POINTER] + [ctypes.c_double] * 4),
        "unbind_child": (ctypes.c_int, [_POINTER, _POINTER]),
    }
    for suffix, (result, arguments) in signatures.items():
        function = getattr(library, "vf_header_host_" + suffix)
        function.restype, function.argtypes = result, arguments
    if (
        library.vf_header_host_abi_version() != 4
        or library.vf_header_host_row_snapshot_size() != ctypes.sizeof(Snapshot)
    ):
        raise RuntimeError("Incompatible native header host")
    return library


class HeaderHost:
    """One exact native toolbar generation. The descriptor is borrowed."""

    def __init__(self, pointer: int, height: float, gutter: float, minimum: float):
        self._row = None
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
        row = Snapshot()
        if (
            self._library.vf_header_host_row_snapshot(self._handle, ctypes.byref(row))
            != 1
        ):
            raise RuntimeError("Unified native row lost exact generation")
        self._row = row
        return 1, row.flags, tuple(row.geometry)

    def row_sample(self):
        r = self._row
        if r is None:
            raise RuntimeError("No current atomic row sample")
        raw_host = list(r.geometry[27:31])
        allocated = all(math.isfinite(v) for v in raw_host) and min(raw_host[2:]) > 0
        return {
            "owner": "unified-toolbar",
            "current": bool(r.flags & 1),
            "host_visible": bool(r.hostVisible),
            "toolbar_owned": bool(r.flags & 1),
            "delegate_unchanged": bool(r.flags & 8),
            "full_size": True,
            "transparent": True,
            "title_hidden": True,
            "transition": r.transition,
            "fullscreen": bool(r.flags & 16),
            "host": raw_host if allocated else None,
            "host_allocated": allocated,
            "content": list(r.geometry[62:66]),
            "buttons": [
                {
                    "identity": r.buttons[i],
                    "visibility": {0: "unknown", 1: "visible", 2: "hidden"}[
                        r.visibility[i]
                    ],
                    "visible_screen": list(r.visible[i * 4 : i * 4 + 4]),
                }
                for i in range(3)
            ],
        }

    def set_height(self, height):
        if self._library.vf_header_host_set_height(self._handle, height) != 1:
            raise RuntimeError("Native header height ownership changed")

    def bind_child(self, pointer: int, rect: tuple[float, float, float, float]):
        if self._library.vf_header_host_bind_child(self._handle, pointer, *rect) != 1:
            raise RuntimeError("Native header child binding refused")

    def update_child(self, pointer: int, rect: tuple[float, float, float, float]):
        if self._library.vf_header_host_update_child(self._handle, pointer, *rect) != 1:
            raise RuntimeError("Native header child ownership changed")

    def unbind_child(self, pointer: int):
        if self._library.vf_header_host_unbind_child(self._handle, pointer) != 1:
            raise RuntimeError("Native header child detach refused; retain exact owner")

    def close(self):
        if (
            not self.closed
            and self._library.vf_header_host_destroy(ctypes.byref(self._handle)) != 1
        ):
            raise RuntimeError(
                "Native header teardown refused; retain its exact handle"
            )
