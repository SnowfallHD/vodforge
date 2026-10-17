"""Native macOS window ownership without executable Python bridge callbacks."""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable
from typing import Any

from yt_downloader.platforms.macos.native_runtime import class_pointer, send

_FULL_SIZE_CONTENT = 1 << 15
_FULL_SCREEN = 1 << 14
_POINTER = ctypes.c_void_p
_UNSIGNED = ctypes.c_ulong


class _NativeWindow:
    def __init__(self, pointer: int) -> None:
        self.pointer = pointer

    def styleMask(self):
        return send(self.pointer, b"styleMask", _UNSIGNED)

    def setStyleMask_(self, value):
        send(self.pointer, b"setStyleMask:", None, (_UNSIGNED,), value)

    def titleVisibility(self):
        return send(self.pointer, b"titleVisibility", ctypes.c_long)

    def setTitleVisibility_(self, value):
        send(self.pointer, b"setTitleVisibility:", None, (ctypes.c_long,), value)

    def titlebarAppearsTransparent(self):
        return send(self.pointer, b"titlebarAppearsTransparent", ctypes.c_bool)

    def setTitlebarAppearsTransparent_(self, value):
        send(
            self.pointer,
            b"setTitlebarAppearsTransparent:",
            None,
            (ctypes.c_bool,),
            value,
        )

    def toolbar(self):
        return send(self.pointer, b"toolbar", _POINTER)

    def setToolbar_(self, toolbar):
        send(self.pointer, b"setToolbar:", None, (_POINTER,), toolbar)

    def setToolbarStyle_(self, style):
        send(self.pointer, b"setToolbarStyle:", None, (ctypes.c_long,), style)

    def isVisible(self):
        return send(self.pointer, b"isVisible", ctypes.c_bool)

    def orderOut_(self, sender):
        send(self.pointer, b"orderOut:", None, (_POINTER,), sender)

    def retain(self):
        send(self.pointer, b"retain", _POINTER)

    def release(self):
        send(self.pointer, b"release", None)


def _native_window(window: Any) -> _NativeWindow | None:
    # Qt's Cocoa WId is the exact owned NSView, not a global app/window lookup.
    pointer = send(int(window.winId()), b"window", _POINTER)
    return _NativeWindow(pointer) if pointer else None


def _new_toolbar() -> int:
    string = send(class_pointer(b"NSString"), b"alloc", _POINTER)
    string = send(
        string,
        b"initWithUTF8String:",
        _POINTER,
        (ctypes.c_char_p,),
        b"VODForge.QtMainHeader",
    )
    if not string:
        raise RuntimeError("Native toolbar identifier allocation failed")
    toolbar = None
    try:
        toolbar = send(class_pointer(b"NSToolbar"), b"alloc", _POINTER)
        toolbar = send(toolbar, b"initWithIdentifier:", _POINTER, (_POINTER,), string)
        if not toolbar:
            raise RuntimeError("Native toolbar allocation failed")
        send(toolbar, b"setAllowsUserCustomization:", None, (ctypes.c_bool,), False)
        send(toolbar, b"setShowsBaselineSeparator:", None, (ctypes.c_bool,), False)
        return toolbar
    except Exception:
        if toolbar:
            send(toolbar, b"release", None)
        raise
    finally:
        send(string, b"release", None)


def integrate_qt_main_window(window: Any) -> bool:
    """Extend the QQuickWindow behind traffic lights using public scalar calls."""
    if sys.platform != "darwin":
        return False
    from PySide6.QtGui import QGuiApplication

    if QGuiApplication.platformName() != "cocoa":
        return False
    native = None
    original_toolbar = None
    toolbar = None
    try:
        native = _native_window(window)
        if native is None:
            return False
        original_style = native.styleMask()
        original_visibility = native.titleVisibility()
        original_transparency = native.titlebarAppearsTransparent()
        original_toolbar = native.toolbar()
        if original_toolbar:
            send(original_toolbar, b"retain", _POINTER)
        toolbar = _new_toolbar()
        native.setStyleMask_(original_style | _FULL_SIZE_CONTENT)
        native.setTitleVisibility_(1)  # NSWindowTitleHidden
        native.setTitlebarAppearsTransparent_(True)
        native.setToolbar_(toolbar)
        native.setToolbarStyle_(3)  # NSWindowToolbarStyleUnified
        # Native frost remains an optional cosmetic capability. The actual Qt
        # top-level parent is a private NSThemeFrame, not a supported sibling
        # owner. Keep the established readable artwork fallback without asking
        # PyObjC to register executable struct wrappers on hardened Intel.
        window.setProperty("backgroundOpacity", 1.0)
        return True
    except Exception:  # noqa: BLE001 - preserve the usable Qt window
        if native is not None and "original_style" in locals():
            try:
                native.setToolbar_(original_toolbar)
                native.setTitlebarAppearsTransparent_(original_transparency)
                native.setTitleVisibility_(original_visibility)
                native.setStyleMask_(original_style)
            except Exception:  # noqa: BLE001 - teardown can reject rollback
                return False
        return False
    finally:
        if toolbar:
            send(toolbar, b"release", None)
        if original_toolbar:
            send(original_toolbar, b"release", None)


class _PresentationRetirement:
    """Retire the exact hidden presentation after asynchronous native Space exit.

    The Qt timer owns callback lifetime; no Foundation block/Python native
    callback is registered. Every tick rechecks current visibility and intent.
    """

    def __init__(self, window: Any, allowed: Callable[[], bool], native: Any) -> None:
        from PySide6.QtCore import QTimer

        self._window = window
        self._allowed = allowed
        self._native = native
        self._closed = False
        self._timer = None
        # The Qt window can release its NSWindow during asynchronous teardown.
        # Hold this exact receiver until our timer has been stopped/disconnected.
        native.retain()
        try:
            self._timer = QTimer(window)
            self._timer.setInterval(100)
            self._timer.timeout.connect(self.retire)
            window.destroyed.connect(self.close)
            self._timer.start()
        except Exception:
            self.close()
            raise

    def retire(self) -> None:
        try:
            if (
                not self._closed
                and self._allowed()
                and not self._window.isVisible()
                and not self._native.styleMask() & _FULL_SCREEN
                and self._native.isVisible()
            ):
                self._native.orderOut_(None)
        except RuntimeError:
            # Queued Qt work may outlive the native wrapper during teardown.
            return

    def close(self, *_destroyed) -> None:
        if not self._closed:
            self._closed = True
            try:
                if self._timer is not None:
                    self._timer.stop()
                    self._timer.timeout.disconnect(self.retire)
                    self._timer.deleteLater()
            except RuntimeError:
                pass  # The parent QWindow already destroyed its timer.
            finally:
                try:
                    self._window.destroyed.disconnect(self.close)
                except (RuntimeError, TypeError):
                    pass
                finally:
                    self._native.release()


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
        native = _native_window(window)
        if native is not None:
            return _PresentationRetirement(window, allowed, native)
    except Exception:  # noqa: BLE001 - Qt hide remains the fallback
        return None
    return None
