"""Main-window composition with Tk-owned style and native accessibility."""

from __future__ import annotations

import ctypes
import tkinter as tk
from collections.abc import Callable
from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def _native_root_control() -> Any:
    """Reuse a process-library function, never a window or native view."""
    function = ctypes.CDLL(None).TkMacOSXGetRootControl
    function.argtypes = (ctypes.c_void_p,)
    function.restype = ctypes.c_void_p
    return function


def _native_window(window: tk.Tk) -> Any:
    import objc

    pointer = _native_root_control()(int(window.winfo_id()))
    if not pointer:
        raise RuntimeError("Native main-window view unavailable")
    return objc.objc_object(c_void_p=pointer).window()


def _install_header_toolbar(native: Any) -> None:
    from AppKit import NSToolbar, NSWindowToolbarStyleUnified

    # AppKit owns the traffic-light placement, hit targets and fullscreen
    # transitions. The toolbar contributes native layout, with no extra items.
    toolbar = NSToolbar.alloc().initWithIdentifier_("VODForge.MainHeader")
    toolbar.setAllowsUserCustomization_(False)
    toolbar.setShowsBaselineSeparator_(False)
    native.setToolbar_(toolbar)
    native.setToolbarStyle_(NSWindowToolbarStyleUnified)
    native.setTitlebarAppearsTransparent_(True)


def integrate_main_window(
    window: tk.Tk, title: str, diagnostic: Callable[[str], None]
) -> bool:
    """Call before initial geometry, preserving native controls and AXTitle.

    Tk alone sets styleMask. AppKit hides only the title's visual rendering;
    clearing wm title would remove the accessible window name as well.
    No event monitors, synthetic input, or private event replay are installed.
    """
    window.title(title)
    window._native_toolbar_header = False  # type: ignore[attr-defined]
    if window.tk.call("tk", "windowingsystem") != "aqua":
        return False
    try:
        original = window.attributes("-stylemask")
        styles = tuple(window.tk.splitlist(original))
        native = _native_window(window)
    except Exception:  # noqa: BLE001 - optional native chrome has a normal Tk fallback
        diagnostic("Integrated window header unavailable; using native title bar")
        return False
    try:
        window.attributes(
            "-stylemask", tuple(dict.fromkeys((*styles, "fullsizecontentview")))
        )
    except tk.TclError:
        diagnostic("Integrated window header unavailable; using native title bar")
        return False
    try:
        native.setTitleVisibility_(1)  # NSWindowTitleHidden; title itself is retained.
    except Exception:  # noqa: BLE001 - roll back presentation if the bridge rejects it
        window.attributes("-stylemask", original)
        diagnostic("Integrated window title unavailable; using native title bar")
        return False
    try:
        _install_header_toolbar(native)
        window._native_toolbar_header = True  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - native title bar remains a valid fallback
        try:
            native.setToolbar_(None)
        except Exception:  # noqa: BLE001 - keep the window usable if rollback is rejected
            diagnostic("Native header alignment rollback unavailable")
        diagnostic(
            "Native header alignment unavailable; retaining standard window controls"
        )
    return True


def request_window_foreground(root: Any) -> bool:
    try:
        from AppKit import NSApplication

        application = NSApplication.sharedApplication()
        if application.respondsToSelector_("activate"):
            application.activate()  # Current AppKit cooperative activation API.
        else:
            application.activateIgnoringOtherApps_(True)  # macOS before 14.
        return bool(application.isActive())
    except (ImportError, AttributeError, RuntimeError):
        return False  # Tk focus remains available if the bridge is unavailable.
