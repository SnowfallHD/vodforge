"""Use the native macOS title controls within Qt Quick's compact header."""

from __future__ import annotations

import sys
from collections.abc import Callable
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
        # A top-level Qt view sits in AppKit's private NSThemeFrame. That
        # frame does not support arbitrary sibling views. Keep the readable
        # opaque fallback unless the sibling owner is the public content view.
        if parent is None or parent != native.contentView():
            window.setProperty("backgroundOpacity", 1.0)
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
        window.setProperty("backgroundOpacity", 0.88)
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


class _PresentationRetirement:
    """Retire one native presentation window after asynchronous Space exit."""

    def __init__(self, window: Any, allowed: Callable[[], bool], native: Any) -> None:
        from AppKit import NSWindowDidExitFullScreenNotification
        from Foundation import NSNotificationCenter, NSOperationQueue

        self._window = window
        self._allowed = allowed
        self._native = native
        self._closed = False
        self._center = NSNotificationCenter.defaultCenter()
        # Keep both the block and observer alive until the bridge closes.
        self._callback: Any = lambda _notification: self.retire()
        self._observer = self._center.addObserverForName_object_queue_usingBlock_(
            NSWindowDidExitFullScreenNotification,
            native,
            NSOperationQueue.mainQueue(),
            self._callback,
        )

    def retire(self) -> None:
        from AppKit import NSWindowStyleMaskFullScreen

        try:
            if (
                not self._closed
                and self._allowed()
                and not self._window.isVisible()
                and not self._native.styleMask() & NSWindowStyleMaskFullScreen
                and self._native.isVisible()
            ):
                # Qt hide can already be a no-op while Cocoa finishes exit and
                # remaps its window. Do not close/destroy the reusable player.
                self._native.orderOut_(None)
        except RuntimeError:
            # A queued native notification can outlive its Qt wrapper.
            return

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                self._center.removeObserver_(self._observer)
            finally:
                self._observer = None
                self._callback = None


def watch_presentation_retirement(
    window: Any, allowed: Callable[[], bool]
) -> _PresentationRetirement | None:
    """Observe only the supplied Cocoa window, without global window lookup."""
    if sys.platform != "darwin":
        return None
    from PySide6.QtGui import QGuiApplication

    if QGuiApplication.platformName() != "cocoa":
        return None
    try:
        import objc

        view = objc.objc_object(c_void_p=int(window.winId()))
        native = view.window()
        if native is not None:
            return _PresentationRetirement(window, allowed, native)
    except Exception:  # noqa: BLE001 - Qt hide remains the fallback if AppKit refuses
        return None
    return None
