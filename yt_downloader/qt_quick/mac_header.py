"""Put the single existing Qt header into its exact public AppKit toolbar view."""

from __future__ import annotations

import math
from typing import Any

from yt_downloader.platforms.macos.header_host import HeaderHost


def measured_layout(flags: int, geometry: tuple[float, ...]):
    """Convert public screen rectangles, never contentLayoutRect, into header state.

    Coordinates are in points and relative to the exact window's content view;
    neither a global screen height nor a guessed traffic-light width is used.
    """
    if len(geometry) != 66 or not flags & 1:
        raise RuntimeError("Native header ownership is no longer current")
    width, height = geometry[10:12]
    if not all(math.isfinite(v) and 0 < v <= 16384 for v in (width, height)):
        raise RuntimeError("Native header allocation is unavailable")
    host_x, host_y, _, host_h = geometry[27:31]
    content_x, content_y, _, content_h = geometry[62:66]
    rect = (host_x, host_y, host_h, content_x, content_y, content_h)
    screen_ready = bool(flags & 2) and all(
        math.isfinite(v) and abs(v) <= 1e7 for v in rect
    )
    leading = 0.0 if screen_ready and flags & 128 else None
    if screen_ready and flags & 32:
        extents = []
        for start in (31, 41, 51):
            present = geometry[start]
            x, y, w, h = geometry[start + 6 : start + 10]
            if (
                present != 1
                or not all(math.isfinite(v) for v in (x, y, w, h))
                or w <= 0
                or h <= 0
            ):
                break
            # Fullscreen buttons may legitimately belong to AppKit's auxiliary
            # window. Each screen rectangle was converted by its exact window.
            extents.append(x + w - host_x)
        if len(extents) == 3:
            leading = max(0.0, *extents)
    return {
        "width": width,
        "height": height,
        "leading": leading,
        "reserve": max(0.0, host_x - content_x) + leading
        if leading is not None
        else None,
        "revealed": bool(flags & 16 and flags & 32) if leading is not None else None,
        "screen_ready": screen_ready,
        "reduced_motion": geometry[61] == 1,
        "relative_x": host_x - content_x if screen_ready else None,
        "relative_y": content_y + content_h - host_y - host_h if screen_ready else None,
    }


class IntegratedHeader:
    """Event-driven GUI-thread ownership, with teardown before borrowed FD close."""

    def __init__(self, window: Any, native_pointer: int):
        from PySide6.QtCore import QObject, QSocketNotifier, Qt
        from PySide6.QtGui import QColor, QWindow
        from PySide6.QtQuick import QQuickWindow

        self._window = window
        self._host = self._foreign = self._surface = self._notifier = None
        self._closed = False
        self._retired = False
        self._synchronizing = False
        self._attached = False
        self._height_connected = False
        self._destroy_connected = False
        self._header = window.findChild(QObject, "focusHeader")
        if self._header is None:
            raise RuntimeError("Canonical Qt header is unavailable")
        self._parent = self._header.parentItem()
        try:
            window.destroyed.connect(self.close)
            self._destroy_connected = True
            self._host = HeaderHost(
                native_pointer,
                self._header.height(),
                float(window.property("gutter")),
                64,
            )
            if not self._host.view or self._host.descriptor < 0:
                raise RuntimeError("Native header view or descriptor is unavailable")
            self._foreign = QWindow.fromWinId(self._host.view)
            if self._foreign is None:
                raise RuntimeError("Qt refused the exact foreign native header view")
            self._surface = QQuickWindow(self._foreign)
            self._surface.setObjectName("nativeHeaderSurface")
            self._surface.setFlags(
                Qt.WindowType.SubWindow | Qt.WindowType.FramelessWindowHint
            )
            self._surface.setColor(QColor("transparent"))
            self._notifier = QSocketNotifier(
                self._host.descriptor, QSocketNotifier.Type.Read, window
            )
            self._notifier.activated.connect(self.synchronize)
            self._header.heightChanged.connect(self.update_height)
            self._height_connected = True
            self.update_height()
            self.synchronize()
        except Exception:
            try:
                self.close()
            except Exception:
                # Construction has not returned an owner to the caller yet.
                # Keep its exact native handle reachable; do not roll styles
                # back underneath a refused live native generation.
                window._native_window_controls = self
                window._native_header_diagnostic = {
                    "stage": "native_header_teardown_pending"
                }
                raise
            raise

    @property
    def closed(self):
        return self._closed

    def synchronize(self, *_notification):
        if self._retired or self._synchronizing:
            return
        self._synchronizing = True
        try:
            if self._host.drain() < 0:
                raise RuntimeError("Native header event channel closed")
            state, flags, geometry = self._host.snapshot()
            if state != 1:
                raise RuntimeError("Native header generation changed")
            layout = measured_layout(flags, geometry)
            self._surface.resize(round(layout["width"]), round(layout["height"]))
            # The native host contains the gutter after the actual lights. A
            # single shared inset animates brand/navigation; utilities stay right.
            self._window.setProperty("nativeHeaderWidth", layout["width"])
            self._window.setProperty("nativeHeaderFullscreen", bool(flags & 16))
            self._window.setProperty(
                "nativeHeaderReducedMotion", layout["reduced_motion"]
            )
            if layout["leading"] is not None:
                self._window.setProperty("nativeHeaderLeadingInset", layout["leading"])
            if not flags & 16 and layout["reserve"] is not None:
                self._window.setProperty("nativeHeaderReserve", layout["reserve"])
            if layout["revealed"] is not None:
                self._window.setProperty("nativeHeaderRevealed", layout["revealed"])
            if layout["screen_ready"] and not self._attached:
                self._window.setProperty("nativeHeaderSurface", self._surface)
                self._header.setParentItem(self._surface.contentItem())
                self._window.setProperty("nativeHeaderAttached", True)
                self._attached = True
                self.update_height()
                self._surface.show()
            self._window._native_header_diagnostic = {
                "stage": "success" if self._attached else "native_header_pending",
                "flags": flags,
                "layout": layout,
            }
        except Exception as exc:
            self._window._native_header_diagnostic = {
                "stage": "native_header_refused",
                "exception_class": type(exc).__name__,
            }
            self.close()
            raise
        finally:
            self._synchronizing = False

    def update_height(self):
        if not self._retired:
            try:
                self._host.set_height(self._header.height())
            except Exception as exc:
                self._window._native_header_diagnostic = {
                    "stage": "native_header_height_refused",
                    "exception_class": type(exc).__name__,
                }
                self.close()
                raise

    @property
    def retired(self):
        return self._retired

    def close(self, *_destroyed):
        if self._closed:
            return
        if not self._retired:
            self._retired = True
            from shiboken6 import isValid

            # QObject event delivery is retired before native destroy closes the FD.
            if self._notifier is not None and isValid(self._notifier):
                self._notifier.setEnabled(False)
                self._notifier.activated.disconnect(self.synchronize)
                self._notifier.deleteLater()
            if isValid(self._header):
                if self._height_connected:
                    try:
                        self._header.heightChanged.disconnect(self.update_height)
                    except (RuntimeError, TypeError):
                        pass
                    self._height_connected = False
                if self._parent is not None and isValid(self._parent):
                    self._header.setParentItem(self._parent)
            if isValid(self._window):
                self._window.setProperty("nativeHeaderAttached", False)
                self._window.setProperty("nativeHeaderSurface", None)
            # Release Qt's retained foreign NSView before native owner tears it down.
            if self._surface is not None:
                self._surface.hide()
                # Keep its foreign parent through platform destruction: Cocoa's
                # child-window destructor removes the embedded NSView only then.
                self._surface.destroy()
                self._surface.deleteLater()
            if self._foreign is not None:
                self._foreign.destroy()
                self._foreign.deleteLater()
        if self._host is not None:
            self._host.close()
        from shiboken6 import isValid

        if self._destroy_connected and isValid(self._window):
            try:
                self._window.destroyed.disconnect(self.close)
            except (RuntimeError, TypeError):
                pass
            self._destroy_connected = False
        self._closed = True
