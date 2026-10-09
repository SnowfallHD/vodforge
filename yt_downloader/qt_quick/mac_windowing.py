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
        _install_frosted_backdrop(window, native, view)
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


def _install_frosted_backdrop(window: Any, native: Any, view: Any) -> bool:
    """Place native frost behind Qt; foreground text and controls stay opaque."""
    try:
        from AppKit import (
            NSAppearance,
            NSAppearanceNameVibrantDark,
            NSColor,
            NSViewHeightSizable,
            NSViewWidthSizable,
            NSVisualEffectBlendingModeBehindWindow,
            NSVisualEffectMaterialSidebar,
            NSVisualEffectStateFollowsWindowActiveState,
            NSVisualEffectView,
            NSWindowBelow,
        )

        original_opaque = native.isOpaque()
        original_background = native.backgroundColor()
        parent = view.superview()
        if parent is None:
            return False
        frost = NSVisualEffectView.alloc().initWithFrame_(view.frame())
        frost.setMaterial_(NSVisualEffectMaterialSidebar)
        frost.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        frost.setState_(NSVisualEffectStateFollowsWindowActiveState)
        frost.setAppearance_(NSAppearance.appearanceNamed_(NSAppearanceNameVibrantDark))
        frost.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        parent.addSubview_positioned_relativeTo_(frost, NSWindowBelow, view)
        native.setOpaque_(False)
        native.setBackgroundColor_(NSColor.clearColor())
        window._native_frosted_backdrop = frost
        window.setProperty("backgroundOpacity", 0.72)
        return True
    except Exception:  # noqa: BLE001 - retain an opaque readable window on native failure
        window.setProperty("backgroundOpacity", 1.0)
        try:
            if "frost" in locals():
                frost.removeFromSuperview()
            if "original_opaque" in locals():
                native.setOpaque_(original_opaque)
                native.setBackgroundColor_(original_background)
        except Exception:  # noqa: BLE001 - the opaque Qt artwork remains the fallback
            return False
        return False
