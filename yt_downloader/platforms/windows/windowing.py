from __future__ import annotations

from typing import Any


def flush_pending_window_paint(root: Any, *surfaces: Any) -> bool:
    """Paint the active view/header without touching dormant view subtrees."""
    import _tkinter
    import ctypes
    from ctypes import wintypes

    api = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
    api.RedrawWindow.argtypes = [
        wintypes.HWND,
        ctypes.c_void_p,
        wintypes.HRGN,
        wintypes.UINT,
    ]
    api.RedrawWindow.restype = wintypes.BOOL
    # Let one pending Tk geometry pass commit the responsive positions. A full
    # update_idletasks() drain can recurse through hundreds of decorative
    # projections and freeze the native sizing loop.
    root.tk.dooneevent(_tkinter.IDLE_EVENTS | _tkinter.DONT_WAIT)
    # Existing invalid regions only. Forcing all children to invalidate on
    # every Configure would turn a paint fix into more resize work.
    return all(
        api.RedrawWindow(surface.winfo_id(), None, None, 0x0100 | 0x0080)
        for surface in surfaces
    )


def request_window_foreground(root: Any) -> bool:
    import ctypes
    from ctypes import wintypes

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        hwnd = user32.GetAncestor(root.winfo_id(), 2)  # GA_ROOT: Tk's native wrapper
        if not hwnd:
            return False
        if user32.SetForegroundWindow(hwnd):
            return True

        # Windows may withhold foreground permission after a browser handoff.
        # FLASHW_TRAY is attention only, not activation or an infinite flash loop.
        class FlashInfo(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT),
                ("hwnd", wintypes.HWND),
                ("dwFlags", wintypes.DWORD),
                ("uCount", wintypes.UINT),
                ("dwTimeout", wintypes.DWORD),
            ]

        user32.FlashWindowEx.argtypes = [ctypes.POINTER(FlashInfo)]
        user32.FlashWindowEx.restype = wintypes.BOOL
        info = FlashInfo(ctypes.sizeof(FlashInfo), hwnd, 2, 3, 0)
        user32.FlashWindowEx(ctypes.byref(info))
        return False  # Attention is never reported as successful activation.
    except (AttributeError, OSError):
        return False


def configure_app_identity() -> bool:
    import ctypes

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(  # type: ignore[attr-defined]
        "SnowfallHD.VODForge"
    )
    return True


def enable_prototype_per_monitor_v2() -> None:
    """Explicit fresh-process prototype setup; never called by app startup."""
    import ctypes
    from ctypes import wintypes

    api = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
    api.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    api.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
    if not api.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
        raise OSError(ctypes.get_last_error(), "Fresh-process PMv2 setup rejected")  # type: ignore[attr-defined]


def prototype_window_dpi(root: Any) -> int:
    """Admit actual window and current thread PMv2; no fallback acceptance."""
    import ctypes
    from ctypes import wintypes

    api = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
    api.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    api.GetAncestor.restype = wintypes.HWND
    api.GetWindowDpiAwarenessContext.argtypes = [wintypes.HWND]
    api.GetWindowDpiAwarenessContext.restype = ctypes.c_void_p
    api.GetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    api.AreDpiAwarenessContextsEqual.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    api.AreDpiAwarenessContextsEqual.restype = wintypes.BOOL
    api.GetDpiForWindow.argtypes = [wintypes.HWND]
    api.GetDpiForWindow.restype = wintypes.UINT
    hwnd = api.GetAncestor(root.winfo_id(), 2)
    contexts = (
        api.GetWindowDpiAwarenessContext(hwnd),
        api.GetThreadDpiAwarenessContext(),
    )
    if not hwnd or not all(
        api.AreDpiAwarenessContextsEqual(c, ctypes.c_void_p(-4)) for c in contexts
    ):
        raise RuntimeError("Prototype requires matching window/thread PMv2 contexts")
    dpi = int(api.GetDpiForWindow(hwnd))
    if dpi not in (96, 192):
        raise RuntimeError(f"Unsupported prototype window DPI: {dpi}")
    return dpi
