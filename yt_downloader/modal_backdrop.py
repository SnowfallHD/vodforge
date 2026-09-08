"""Native child scrims dim rendered pixels, never mutate underlying UI state."""

from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from typing import Any


def backdrop_rects(width: int, height: int, x: int, y: int, w: int, h: int):
    """Four nonoverlapping bands leave the modal itself completely untouched."""
    left, top = max(0, x), max(0, y)
    right, bottom = min(width, x + w), min(height, y + h)
    return (
        (0, 0, width, top),
        (0, bottom, width, max(0, height - bottom)),
        (0, top, left, max(0, bottom - top)),
        (right, top, max(0, width - right), max(0, bottom - top)),
    )


class ModalBackdrop:
    def __init__(self, parent: tk.Misc) -> None:
        self.parent = parent
        self.views: list[Any] = []
        self.user32: Any = None
        self.last: tuple | None = None
        try:
            if sys.platform == "darwin":
                import objc
                from AppKit import NSView
                from Quartz import CGColorCreateGenericRGB

                root_control = ctypes.CDLL(None).TkMacOSXGetRootControl
                root_control.argtypes = (ctypes.c_void_p,)
                root_control.restype = ctypes.c_void_p
                pointer = root_control(int(parent.winfo_id()))
                if not pointer:
                    raise RuntimeError("No native content view")
                host = objc.objc_object(c_void_p=pointer)
                for _ in range(4):
                    view = NSView.alloc().initWithFrame_(((0, 0), (0, 0)))
                    view.setWantsLayer_(True)
                    view.layer().setBackgroundColor_(
                        CGColorCreateGenericRGB(0, 0, 0, 0.65)
                    )
                    host.addSubview_(view)
                    self.views.append(view)
            elif sys.platform == "win32":
                from ctypes import wintypes

                self.user32 = ctypes.WinDLL("user32", use_last_error=True)
                create = self.user32.CreateWindowExW
                create.restype = wintypes.HWND
                create.argtypes = (
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
                )
                self.user32.SetLayeredWindowAttributes.argtypes = (
                    wintypes.HWND,
                    wintypes.DWORD,
                    wintypes.BYTE,
                    wintypes.DWORD,
                )
                self.user32.SetWindowPos.argtypes = (
                    wintypes.HWND,
                    wintypes.HWND,
                    ctypes.c_int,
                    ctypes.c_int,
                    ctypes.c_int,
                    ctypes.c_int,
                    wintypes.UINT,
                )
                self.user32.DestroyWindow.argtypes = (wintypes.HWND,)
                for _ in range(4):
                    # Layered child STATIC/BLACKRECT, never a separate OS window.
                    hwnd = create(
                        0x80000,
                        "STATIC",
                        None,
                        0x40000004,
                        0,
                        0,
                        0,
                        0,
                        parent.winfo_id(),
                        None,
                        None,
                        None,
                    )
                    if not hwnd:
                        raise OSError("Could not create modal backdrop")
                    self.views.append(hwnd)
                    if not self.user32.SetLayeredWindowAttributes(hwnd, 0, 166, 2):
                        raise OSError("Could not set backdrop opacity")
        except Exception:  # noqa: BLE001 - presentation must not break consent
            self.close()

    def refresh(self, panel: tk.Misc) -> None:
        snapshot = (
            self.parent.winfo_width(),
            self.parent.winfo_height(),
            panel.winfo_x(),
            panel.winfo_y(),
            panel.winfo_width(),
            panel.winfo_height(),
        )
        if snapshot == self.last:
            return
        self.last = snapshot
        for view, (x, y, w, h) in zip(self.views, backdrop_rects(*snapshot)):
            if self.user32 is not None:
                self.user32.SetWindowPos(view, 0, x, y, w, h, 0x50)
            else:
                host = view.superview()
                native_y = y if host.isFlipped() else host.bounds().size.height - y - h
                view.setFrame_(((x, native_y), (w, h)))

    def close(self) -> None:
        for view in self.views:
            if self.user32 is not None:
                self.user32.DestroyWindow(view)
            else:
                view.removeFromSuperview()
        self.views.clear()
