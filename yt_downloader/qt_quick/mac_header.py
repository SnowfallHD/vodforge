"""Put the single existing Qt header into its exact public AppKit toolbar view."""

from __future__ import annotations

import math
from typing import Any, ClassVar

from yt_downloader.platforms.macos.header_host import HeaderHost
from yt_downloader.qt_quick.mac_header_packet import NativeRowRefused, packet


def create_header_input_boundary(main: Any, surface: Any):
    """Keep the main overlay authoritative across this owner's exact Qt surface.

    Qt imports stay lazy for non-GUI runtime and package import checks. One
    existing gate decides admission; no popup list or input diagnostics persist.
    """
    from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF, Qt
    from PySide6.QtGui import QEnterEvent, QMouseEvent, QWheelEvent
    from shiboken6 import isValid

    class HeaderInputBoundary(QObject):
        TYPES: ClassVar[set] = {
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseButtonDblClick,
            QEvent.Type.MouseMove,
            QEvent.Type.Wheel,
        }

        def __init__(self, main, surface):
            super().__init__(surface)
            self.main = main
            self.surface = surface
            self.owned = False
            self.retired = False
            self.cancelled_gesture = False
            self._mapping_enter = False
            surface.installEventFilter(self)
            self.main.menuNavigationAllowedChanged.connect(self._gate_changed)
            self.main.nativeHeaderInputReadyChanged.connect(self._gate_changed)
            self._gate_changed()

        def eventFilter(self, watched, event):
            if watched is not self.surface:
                return False
            if event.type() == QEvent.Type.Enter:
                try:
                    return self._enter(event)
                except RuntimeError:
                    return True
            if event.type() in {
                QEvent.Type.WindowDeactivate,
                QEvent.Type.Hide,
                QEvent.Type.Close,
            }:
                if self.owned:
                    self.owned = False
                    self.cancelled_gesture = True
                return False
            if event.type() not in self.TYPES:
                return False
            if self.retired or not isValid(self.main) or (not isValid(self.surface)):
                return True
            try:
                if not bool(self.main.property("nativeHeaderInputReady")):
                    self.owned = False
                    self.cancelled_gesture = True
                    return True
                if not self.main.isVisible() or not self.surface.isVisible():
                    self.owned = False
                    return True
                press = event.type() in {
                    QEvent.Type.MouseButtonPress,
                    QEvent.Type.MouseButtonDblClick,
                }
                if self.cancelled_gesture:
                    if event.type() == QEvent.Type.MouseButtonPress:
                        self.cancelled_gesture = False
                    else:
                        if (
                            event.type() == QEvent.Type.MouseButtonRelease
                            and event.buttons() == Qt.NoButton
                        ):
                            self.cancelled_gesture = False
                        return True
                if press and (not bool(self.main.property("menuNavigationAllowed"))):
                    self.owned = True
                gated_passive = event.type() in {
                    QEvent.Type.MouseMove,
                    QEvent.Type.Wheel,
                } and (not bool(self.main.property("menuNavigationAllowed")))
                if not self.owned and (not gated_passive):
                    return False
                global_pos = event.globalPosition()
                base = global_pos.toPoint()
                local = (
                    QPointF(self.main.mapFromGlobal(base)) + global_pos - QPointF(base)
                )
                if event.type() == QEvent.Type.Wheel:
                    forwarded = QWheelEvent(
                        local,
                        global_pos,
                        event.pixelDelta(),
                        event.angleDelta(),
                        event.buttons(),
                        event.modifiers(),
                        event.phase(),
                        event.inverted(),
                        event.source(),
                        event.pointingDevice(),
                    )
                else:
                    forwarded = QMouseEvent(
                        event.type(),
                        local,
                        local,
                        global_pos,
                        event.button(),
                        event.buttons(),
                        event.modifiers(),
                        event.source(),
                        event.pointingDevice(),
                    )
                forwarded.setTimestamp(event.timestamp())
                QCoreApplication.sendEvent(self.main, forwarded)
                if (
                    event.type() == QEvent.Type.MouseButtonRelease
                    and event.buttons() == Qt.NoButton
                ):
                    self.owned = False
                event.accept()
                return True
            except RuntimeError:
                self.owned = False
                return True

        def _enter(self, event):
            # Cocoa can report Enter in the ancestor NSWindow's coordinates
            # after the exact Qt view is embedded in the toolbar. Move and
            # press already use the child. Keep one current scene mapping.
            if self.retired or not isValid(self.main) or not isValid(self.surface):
                return True
            if not self.main.property(
                "nativeHeaderInputReady"
            ) or not self.main.property("menuNavigationAllowed"):
                return True
            if not self.main.isVisible() or not self.surface.isVisible():
                return True
            if self._mapping_enter:
                return False
            global_pos = event.globalPosition()
            base = global_pos.toPoint()
            local = (
                QPointF(self.surface.mapFromGlobal(base)) + global_pos - QPointF(base)
            )
            if event.position() != local or event.scenePosition() != local:
                mapped = QEnterEvent(local, local, global_pos, event.pointingDevice())
                mapped.setTimestamp(event.timestamp())
                self._mapping_enter = True
                try:
                    QCoreApplication.sendEvent(self.surface, mapped)
                finally:
                    self._mapping_enter = False
                event.accept()
                return True
            return False

        def _gate_changed(self):
            if self.retired or not isValid(self.main) or (not isValid(self.surface)):
                return
            try:
                if not bool(self.main.property("menuNavigationAllowed")) or not bool(
                    self.main.property("nativeHeaderInputReady")
                ):
                    QCoreApplication.sendEvent(self.surface, QEvent(QEvent.Type.Leave))
            except RuntimeError:
                pass

        def close(self):
            if self.retired:
                return
            self.retired = True
            self.owned = False
            self.cancelled_gesture = False
            if isValid(self.main):
                try:
                    self.main.menuNavigationAllowedChanged.disconnect(
                        self._gate_changed
                    )
                    self.main.nativeHeaderInputReadyChanged.disconnect(
                        self._gate_changed
                    )
                except (RuntimeError, TypeError):
                    pass
            if isValid(self.surface):
                self.surface.removeEventFilter(self)

    return HeaderInputBoundary(main, surface)


class IntegratedHeader:
    """One main-parent Qt surface, bound to the exact public native toolbar."""

    _BOUND = 256
    _CURRENT = 512
    _FIT = 1024

    def __init__(self, window: Any, native_pointer: int):
        from PySide6.QtCore import QObject, QSocketNotifier, Qt
        from PySide6.QtGui import QColor
        from PySide6.QtQuick import QQuickWindow

        self._window = window
        self._host = self._surface = self._notifier = None
        self._input_boundary = None
        self._child_pointer = 0
        self._child_bound = False
        self._last_rect = None
        self._closed = False
        self._retired = False
        self._synchronizing = False
        self._resynchronize = False
        self._attached = False
        self._body_slot = None
        self._sequence = 0
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
            # A foreign QWindow inside Qt's own NSWindow has local Cocoa geometry.
            # Keep the real main window as Qt's logical parent for global/AX/focus.
            self._surface = QQuickWindow(window)
            self._surface.setObjectName("nativeHeaderSurface")
            self._surface.setFlags(
                Qt.WindowType.SubWindow | Qt.WindowType.FramelessWindowHint
            )
            self._surface.setColor(QColor("transparent"))
            self._input_boundary = create_header_input_boundary(window, self._surface)
            self._notifier = QSocketNotifier(
                self._host.descriptor, QSocketNotifier.Type.Read, window
            )
            self._notifier.activated.connect(self.synchronize)
            # Initial intrinsic height is fixed for this native row.
            self.synchronize()
            self._host.set_change_callback(self._native_changed)
        except Exception:
            try:
                self.close()
            except Exception:
                # Retain the exact native generation when safe teardown refuses.
                window._native_window_controls = self
                window._native_header_diagnostic = {
                    "stage": "native_header_teardown_pending"
                }
                raise
            raise

    @property
    def closed(self):
        return self._closed

    def _place_surface(self, layout):
        from PySide6.QtCore import QObject, QPoint, QRect

        # QWindow.parent() invalidates its returned PySide wrapper when the
        # child is deleted (even though the parent C++ window remains alive).
        # The typed QObject relation verifies the same owner without that rule.
        if QObject.parent(self._surface) is not self._window:
            raise RuntimeError("Qt header lost its exact logical main parent")
        rect = tuple(
            round(layout[key])
            for key in ("relative_x", "relative_y", "width", "height")
        )
        changed = rect != self._last_rect
        if changed:
            self._surface.setGeometry(QRect(*rect))
        if not self._child_pointer:
            # Qt visibility reconciliation can reassert its native parent.
            # Complete it BEFORE binding, never show/setParent as a repair loop.
            self._surface.show()
            self._child_pointer = int(self._surface.winId())
            self._host.bind_child(self._child_pointer, rect)
            self._child_bound = True
        else:
            if int(self._surface.winId()) != self._child_pointer:
                raise RuntimeError("Qt replaced the bound native header view")
            state, flags, _geometry = self._host.snapshot()
            if state != 1 or not flags & self._CURRENT:
                raise RuntimeError("Native header child generation changed")
            if changed or not flags & self._FIT:
                self._host.update_child(self._child_pointer, rect)
        state, flags, geometry = self._host.snapshot()
        required = 1 | self._BOUND | self._CURRENT | self._FIT
        if state != 1 or flags & required != required or len(geometry) != 98:
            raise RuntimeError("Native header child binding is not current and fitted")
        # Independent public native screen geometry must agree with Qt's model.
        # Each native screen rect was converted through its own current window.
        cx, cy, cw, ch = geometry[82:86]
        mx, my, mw, mh = geometry[94:98]
        if not all(math.isfinite(v) for v in (cx, cy, cw, ch, mx, my, mw, mh)):
            raise RuntimeError("Native header global geometry is unavailable")
        if min(cw, ch, mw, mh) <= 0:
            raise RuntimeError("Native header global geometry is empty")
        main_global = self._window.mapToGlobal(QPoint(0, 0))
        actual = self._surface.mapToGlobal(QPoint(0, 0))
        expected = (main_global.x() + cx - mx, main_global.y() + my + mh - cy - ch)
        if max(abs(actual.x() - expected[0]), abs(actual.y() - expected[1])) > 1:
            raise RuntimeError("Qt and native header global coordinates disagree")
        self._last_rect = rect
        return flags

    def _native_changed(self):
        # Called on AppKit's main thread, before its allocation callback returns.
        # Never unwind a Python exception through the C callback boundary.
        try:
            self.synchronize()
        except Exception:  # noqa: BLE001 - no Python exception may cross the C boundary
            return  # synchronize already preserved refusal diagnostics and retired.

    def synchronize(self, *_notification):
        if self._retired:
            return
        if self._synchronizing:
            self._resynchronize = True
            return
        self._synchronizing = True
        try:
            # Child binding can itself emit geometry notifications. Reconcile
            # those in this same transaction, never on a delayed render frame.
            for _ in range(16):
                self._resynchronize = False
                self._synchronize_once()
                if not self._resynchronize or self._retired:
                    break
            else:
                raise RuntimeError("Native header allocation did not converge")
        except Exception as exc:
            self._window._native_header_diagnostic = {
                "stage": "native_header_refused",
                "exception_class": type(exc).__name__,
            }
            self.close()
            raise
        finally:
            self._synchronizing = False

    def _synchronize_once(self):
        try:
            if self._host.drain() < 0:
                raise RuntimeError("Native header event channel closed")
            state, _flags, geometry = self._host.snapshot()
            if state != 1 or len(geometry) != 98:
                raise RuntimeError("Native header generation changed")
            sample = self._host.row_sample()
            color = self._window.property("glassSurfaceColor")
            self._host.set_background(color.getRgbF())
            if self._body_slot is None:
                self._body_slot = self._header.height()
            host_rect = sample.get("host")
            allocated = (
                isinstance(host_rect, (list, tuple))
                and len(host_rect) == 4
                and all(type(v) in (int, float) and math.isfinite(v) for v in host_rect)
                and min(host_rect[2:]) > 0
            )
            native_height = host_rect[3] if allocated else None
            if all(
                sample.get(k) is True
                for k in (
                    "current",
                    "toolbar_owned",
                    "delegate_unchanged",
                    "full_size",
                    "transparent",
                    "title_hidden",
                )
            ) and (
                not allocated
                or not sample.get("host_visible")
                or native_height < self._body_slot
            ):
                # AppKit can briefly unallocate its exact toolbar even after
                # DidEnter/DidExit has reset the transition flag. Keep the
                # native parent instead of retiring into the moving content
                # header. Pending geometry must never admit stale input.
                # Retain the exact owner but do not bind/show the Qt child,
                # publish a packet, shrink policy, or report readiness. An actual
                # native allocation event may complete it; the harness deadline
                # remains the bounded failure boundary. No timer/repair offset.
                self._window._native_header_diagnostic = {
                    "stage": "native_header_pending_allocation",
                    "actual_height": native_height,
                    "required_height": self._body_slot,
                    "sample": sample,
                }
                self._window.setProperty("nativeHeaderInputReady", False)
                return
            self._sequence += 1
            try:
                layout = packet(
                    sample,
                    self._body_slot,
                    self._sequence,
                    float(self._window.property("gutter")),
                )
            except NativeRowRefused:
                # Direct main-thread KVO can observe the three native buttons
                # between their individual setters, or an in-flight reparent
                # between the content and toolbar allocations. Keep the exact
                # owner, publish nothing, and await its next allocation event.
                # Unknown controls/foreign ownership still retire immediately.
                states = {b.get("visibility") for b in sample.get("buttons", [])}
                owned = all(
                    sample.get(k) is True
                    for k in (
                        "current",
                        "toolbar_owned",
                        "delegate_unchanged",
                        "full_size",
                        "transparent",
                        "title_hidden",
                    )
                )
                if owned and (
                    sample.get("transition") in (1, 2)
                    or states == {"visible", "hidden"}
                ):
                    self._window._native_header_diagnostic = {
                        "stage": "native_header_pending_coherent_allocation",
                        "transition": sample.get("transition"),
                    }
                    self._window.setProperty("nativeHeaderInputReady", False)
                    return
                raise
            layout["screen_ready"] = True
            child_flags = self._place_surface(layout)
            # Single QML transaction after native+Qt global binding validation.
            self._window.setProperty("nativeRowPacket", layout)
            if not self._attached:
                self._window.setProperty("nativeHeaderSurface", self._surface)
                self._header.setParentItem(self._surface.contentItem())
                self._window.setProperty("nativeHeaderAttached", True)
                self._attached = True
                # Native height comes from layout policy, not allocated geometry.
            self._window.setProperty("nativeHeaderInputReady", True)
            self._window._native_header_diagnostic = {
                "stage": "success",
                "flags": child_flags,
                "layout": layout,
            }
        except Exception as exc:
            self._window._native_header_diagnostic = {
                "stage": "native_header_refused",
                "exception_class": type(exc).__name__,
            }
            self.close()
            raise

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
        from shiboken6 import isValid

        if not self._retired:
            self._retired = True
            if isValid(self._window):
                self._window.setProperty("nativeHeaderInputReady", False)
            if self._host is not None:
                self._host.set_change_callback(None)
            if self._input_boundary is not None:
                self._input_boundary.close()
                self._input_boundary = None
            # No event delivery may outlive the exact native generation/FD.
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
                # A retired generation is diagnostic evidence, never live QML
                # layout input (including the normal header's body reservation).
                self._window.setProperty("nativeRowPacket", {})
            self._attached = False
            self._last_rect = None
        if self._host is not None and self._child_pointer:
            # A refused bind may retain a partial native generation. Query it
            # before destroying Qt; an unbind refusal retains both live owners.
            bound = self._child_bound
            if not bound:
                _state, flags, _geometry = self._host.snapshot()
                bound = bool(flags & self._BOUND)
            if bound:
                self._host.unbind_child(self._child_pointer)
                self._child_bound = False
        if self._surface is not None:
            if isValid(self._surface):
                # Detach first; hide can reconcile native parenting in Cocoa.
                self._surface.hide()
                self._surface.destroy()
                self._surface.deleteLater()
            self._surface = None
        self._child_pointer = 0
        if self._host is not None:
            self._host.close()
        if self._destroy_connected and isValid(self._window):
            try:
                self._window.destroyed.disconnect(self.close)
            except (RuntimeError, TypeError):
                pass
            self._destroy_connected = False
        self._closed = True
