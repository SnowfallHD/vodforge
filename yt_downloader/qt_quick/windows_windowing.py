"""Keep Windows' resize/system/snap owner behind application-painted frames."""

from __future__ import annotations

import sys
from typing import Any


def frame_hit_test(
    x: int, y: int, width: int, height: int, border: int, header: int, maximized: bool
) -> int:
    """Native screen pixels in; signed monitor coordinates are resolved by caller."""
    if not maximized:
        left, right = x < border, x >= width - border
        top, bottom = y < border, y >= height - border
        if top:
            return 13 if left else 14 if right else 12
        if bottom:
            return 16 if left else 17 if right else 15
        if left or right:
            return 10 if left else 11
    if y < header:
        button = 46 * header // 32
        if width - 2 * button <= x < width - button:
            return 9  # HTMAXBUTTON: Windows 11 owns its Snap Layout hover menu.
        if x < width - 3 * button:
            return 2  # HTCAPTION: native drag, double-click and system menu.
    return 1


def integrate_windows_frames(engine: Any) -> Any:
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes as w

    from PySide6.QtCore import QAbstractNativeEventFilter, QTimer
    from PySide6.QtGui import QGuiApplication, QWindow

    if QGuiApplication.platformName() != "windows":
        return None

    api = ctypes.WinDLL("user32", use_last_error=True)
    get_style = (
        api.GetWindowLongPtrW
        if ctypes.sizeof(ctypes.c_void_p) == 8
        else api.GetWindowLongW
    )
    set_style = (
        api.SetWindowLongPtrW
        if ctypes.sizeof(ctypes.c_void_p) == 8
        else api.SetWindowLongW
    )
    get_style.argtypes = [w.HWND, ctypes.c_int]
    get_style.restype = ctypes.c_ssize_t
    set_style.argtypes = [w.HWND, ctypes.c_int, ctypes.c_ssize_t]
    set_style.restype = ctypes.c_ssize_t
    api.SetWindowPos.argtypes = [
        w.HWND,
        w.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        w.UINT,
    ]
    api.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
    api.GetDpiForWindow.argtypes = [w.HWND]
    api.GetDpiForWindow.restype = w.UINT
    api.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, w.UINT]
    api.IsZoomed.argtypes = [w.HWND]
    api.MonitorFromWindow.argtypes = [w.HWND, w.DWORD]
    api.MonitorFromWindow.restype = w.HANDLE

    class MonitorInfo(ctypes.Structure):
        _fields_ = [
            ("size", w.DWORD),
            ("monitor", w.RECT),
            ("work", w.RECT),
            ("flags", w.DWORD),
        ]

    api.GetMonitorInfoW.argtypes = [w.HANDLE, ctypes.POINTER(MonitorInfo)]

    class Frames(QAbstractNativeEventFilter):
        def __init__(self) -> None:
            super().__init__()
            self.windows = [engine.rootObjects()[0]]
            player = self.windows[0].findChild(QWindow, "watchPresentationWindow")
            if player is not None:
                self.windows.append(player)
            # Acquire handles before native dispatch starts: winId() can create
            # a hidden player window and recursively enter this callback.
            self.handles = {int(window.winId()): window for window in self.windows}
            self.max_pressed = None
            for window in self.windows:
                window.visibilityChanged.connect(
                    lambda _state, owner=window: QTimer.singleShot(
                        0, lambda: self.configure(owner)
                    )
                )

        def configure(self, window: Any) -> None:
            hwnd = int(window.winId())
            self.handles = {
                key: value for key, value in self.handles.items() if value is not window
            }
            self.handles[hwnd] = window
            # Frameless rendering must not retire the native lifetime owner.
            style = get_style(hwnd, -16)
            set_style(
                hwnd, -16, style | 0x00CF0000
            )  # caption, thickframe, system, min/max
            api.SetWindowPos(
                hwnd, None, 0, 0, 0, 0, 0x0037
            )  # frame changed, no move/size/activate/z-order

        def nativeEventFilter(self, event_type: Any, message: int) -> tuple[bool, int]:
            msg = w.MSG.from_address(int(message))
            window = self.handles.get(msg.hWnd)
            if window is None:
                return False, 0
            fullscreen = window.visibility() == QWindow.Visibility.FullScreen
            # Qt's frameless mouse adapter consumes nonclient button events.
            # Keep HTMAXBUTTON for the shell's hover flyout, but queue the same
            # maximize/restore action as the QML button outside native dispatch.
            if msg.message == 0x00A1 and msg.wParam == 9 and not fullscreen:
                self.max_pressed = msg.hWnd
                return True, 0
            if msg.message == 0x00A2 and msg.wParam == 9:
                pressed = self.max_pressed == msg.hWnd
                self.max_pressed = None
                if pressed:

                    def toggle() -> None:
                        if (
                            not window.isVisible()
                            or window.visibility() == QWindow.Visibility.FullScreen
                        ):
                            return
                        if window.visibility() == QWindow.Visibility.Maximized:
                            window.showNormal()
                        else:
                            window.showMaximized()

                    QTimer.singleShot(0, toggle)
                return True, 0
            if msg.message in (0x001F, 0x0215, 0x0202, 0x00A2):
                self.max_pressed = None
            if (
                msg.message == 0x0083 and msg.wParam
            ):  # WM_NCCALCSIZE, first RECT in params
                rect = w.RECT.from_address(msg.lParam)
                if api.IsZoomed(msg.hWnd) and not fullscreen:
                    info = MonitorInfo()
                    info.size = ctypes.sizeof(info)
                    if api.GetMonitorInfoW(
                        api.MonitorFromWindow(msg.hWnd, 2), ctypes.byref(info)
                    ):
                        rect.left, rect.top = info.work.left, info.work.top
                        rect.right, rect.bottom = info.work.right, info.work.bottom
                return True, 0
            if msg.message == 0x0084 and not fullscreen:  # WM_NCHITTEST
                rect = w.RECT()
                if not api.GetWindowRect(msg.hWnd, ctypes.byref(rect)):
                    return False, 0
                x = ctypes.c_short(msg.lParam & 0xFFFF).value - rect.left
                y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value - rect.top
                dpi = api.GetDpiForWindow(msg.hWnd) or 96
                border = api.GetSystemMetricsForDpi(
                    32, dpi
                ) + api.GetSystemMetricsForDpi(92, dpi)
                hit = frame_hit_test(
                    x,
                    y,
                    rect.right - rect.left,
                    rect.bottom - rect.top,
                    border,
                    round(32 * window.devicePixelRatio()),
                    bool(api.IsZoomed(msg.hWnd)),
                )
                return True, hit
            return False, 0

    owner = Frames()
    QGuiApplication.instance().installNativeEventFilter(owner)
    for window in owner.windows:
        owner.configure(window)
    engine.destroyed.connect(
        lambda: QGuiApplication.instance().removeNativeEventFilter(owner)
    )
    return owner
