"""A dedicated Win32 child keeps the video renderer alive between Tk hosts."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any

from ...playback_backend import MediaPlayerError

_windows_ctypes: Any = ctypes


class WindowsVideoHost:
    def __init__(self, parent: int) -> None:
        self._user = _windows_ctypes.WinDLL("user32", use_last_error=True)
        kernel = _windows_ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel.GetModuleHandleW.restype = wintypes.HMODULE
        create = self._user.CreateWindowExW
        create.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            ctypes.c_void_p,
        ]
        create.restype = wintypes.HWND
        self._user.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
        self._user.SetParent.restype = wintypes.HWND
        self._user.MoveWindow.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.BOOL,
        ]
        self._user.MoveWindow.restype = wintypes.BOOL
        self._user.DestroyWindow.argtypes = [wintypes.HWND]
        self._user.DestroyWindow.restype = wintypes.BOOL
        # WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS | WS_CLIPCHILDREN
        self.handle = int(
            create(
                0,
                "STATIC",
                "",
                0x56000000,
                0,
                0,
                1,
                1,
                parent,
                None,
                kernel.GetModuleHandleW(None),
                None,
            )
            or 0
        )
        if not self.handle:
            raise MediaPlayerError("VODForge could not create its video window.")

    def resize(self, width: int, height: int) -> None:
        if self.handle:
            self._user.MoveWindow(
                self.handle, 0, 0, max(1, width), max(1, height), True
            )

    def reparent(self, parent: int) -> None:
        _windows_ctypes.set_last_error(0)
        result = self._user.SetParent(self.handle, parent)
        if not result and _windows_ctypes.get_last_error():
            raise MediaPlayerError("VODForge could not move the video window.")

    def close(self) -> None:
        if self.handle:
            self._user.DestroyWindow(self.handle)
            self.handle = 0
