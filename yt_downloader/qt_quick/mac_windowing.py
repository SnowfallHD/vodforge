"""Use the native macOS title controls within Qt Quick's compact header."""

from __future__ import annotations

import sys
from typing import Any


def integrate_qt_main_window(window: Any) -> bool:
    """Extend the QQuickWindow content behind its native traffic lights."""
    if sys.platform != "darwin":
        return False
    from PySide6.QtGui import QGuiApplication

    if QGuiApplication.platformName() != "cocoa":
        return False
    try:
        import objc
        from AppKit import (
            NSToolbar,
            NSWindowStyleMaskFullSizeContentView,
            NSWindowTitleHidden,
            NSWindowToolbarStyleUnified,
        )

        # Qt's macOS WId is an NSView pointer; AppKit still owns the controls.
        view = objc.objc_object(c_void_p=int(window.winId()))
        native = view.window()
        if native is None:
            return False
        original_style = native.styleMask()
        original_visibility = native.titleVisibility()
        original_transparency = native.titlebarAppearsTransparent()
        original_toolbar = native.toolbar()
        toolbar = NSToolbar.alloc().initWithIdentifier_("VODForge.QtMainHeader")
        toolbar.setAllowsUserCustomization_(False)
        toolbar.setShowsBaselineSeparator_(False)
        native.setStyleMask_(original_style | NSWindowStyleMaskFullSizeContentView)
        native.setTitleVisibility_(NSWindowTitleHidden)
        native.setTitlebarAppearsTransparent_(True)
        native.setToolbar_(toolbar)
        native.setToolbarStyle_(NSWindowToolbarStyleUnified)
        return True
    except Exception:  # noqa: BLE001 - preserve a usable native window on bridge failure
        if "native" in locals() and native is not None:
            try:
                native.setToolbar_(original_toolbar)
                native.setTitlebarAppearsTransparent_(original_transparency)
                native.setTitleVisibility_(original_visibility)
                native.setStyleMask_(original_style)
            except Exception:  # noqa: BLE001 - AppKit may reject rollback during teardown
                return False
        return False
