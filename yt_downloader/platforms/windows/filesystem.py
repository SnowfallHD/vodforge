from __future__ import annotations

import sys
from pathlib import Path


def file_change_time_ns(descriptor: int) -> int:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class BasicInfo(ctypes.Structure):
        _fields_ = [
            ("creation", ctypes.c_longlong),
            ("access", ctypes.c_longlong),
            ("write", ctypes.c_longlong),
            ("change", ctypes.c_longlong),
            ("attributes", wintypes.DWORD),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    query = kernel.GetFileInformationByHandleEx
    query.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    query.restype = wintypes.BOOL
    info = BasicInfo()
    # FileBasicInfo=0. Borrow the caller's handle; never close or reopen it here.
    handle = msvcrt.get_osfhandle(descriptor)  # type: ignore[attr-defined]
    if not query(handle, 0, ctypes.byref(info), ctypes.sizeof(info)):
        raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
    return int(info.change) * 100 - 11_644_473_600_000_000_000


def system_trash_available() -> bool:
    from send2trash.win.modern import send2trash

    return callable(send2trash) and sys.getwindowsversion().major >= 10  # type: ignore[attr-defined]


def trash_file(path: Path) -> str | None:
    from send2trash.win.modern import send2trash

    send2trash(str(path))
    return None
