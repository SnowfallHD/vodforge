"""Native macOS window ownership without executable Python bridge callbacks."""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable
from typing import Any

from yt_downloader.platforms.macos.native_runtime import send
from yt_downloader.platforms.macos.window_controls import WindowControls

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


def integrate_qt_main_window(window: Any) -> bool:
    """Use expanded Qt content and toolbar-free public native window controls."""
    window._native_header_diagnostic = {"stage": "platform"}
    if sys.platform != "darwin":
        return False
    from PySide6.QtGui import QGuiApplication

    window._native_header_diagnostic = {"stage": "platform_plugin"}
    if QGuiApplication.platformName() != "cocoa":
        return False
    existing = getattr(window, "_native_window_controls", None)
    if existing is not None and not existing.closed:
        window._native_header_diagnostic = {"stage": "success"}
        return True
    native = None
    owner = None
    try:
        window._native_header_diagnostic = {"stage": "native_receiver"}
        native = _native_window(window)
        if native is None:
            return False
        original_style = native.styleMask()
        original_visibility = native.titleVisibility()
        original_transparency = native.titlebarAppearsTransparent()
        native.setStyleMask_(original_style | _FULL_SIZE_CONTENT)
        native.setTitleVisibility_(1)  # NSWindowTitleHidden
        native.setTitlebarAppearsTransparent_(True)
        # An empty unified toolbar obscures Qt during entry/reveal and changes
        # traffic-light geometry during exit. The compiled public-button owner
        # supplies alignment without attaching or cycling a toolbar.
        owner = WindowControls(window, native.pointer)
        window.setProperty("backgroundOpacity", 1.0)
        window._native_window_controls = owner
        window._native_header_diagnostic = {"stage": "success"}
        return True
    except Exception as exc:  # noqa: BLE001 - preserve the usable Qt window
        diagnostic = dict(getattr(window, "_native_header_diagnostic", {}))
        diagnostic["exception_class"] = type(exc).__name__
        window._native_header_diagnostic = diagnostic
        if owner is not None:
            try:
                owner.close()
            except RuntimeError:
                # Do not mutate style underneath an owner whose GUI-thread
                # cleanup was refused. Its connected destruction hook remains.
                return False
        if native is not None and "original_style" in locals():
            try:
                native.setTitlebarAppearsTransparent_(original_transparency)
                native.setTitleVisibility_(original_visibility)
                native.setStyleMask_(original_style)
            except Exception:  # noqa: BLE001 - teardown can reject rollback
                return False
        return False


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
