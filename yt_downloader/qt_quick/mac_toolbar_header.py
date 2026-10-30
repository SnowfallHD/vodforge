"""VODForge's macOS header as real AppKit toolbar items.

AppKit draws and positions every header control (header_items.m), so it moves
in the same transaction as the window, menu bar and window buttons when the
window enters fullscreen or the menu bar is revealed. Qt keeps every action:
the native side only queues what the user did; QML applies it through the
signals below and pushes state back through the slots.
"""

from __future__ import annotations

import ctypes
import io
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QRectF, QSocketNotifier, Signal, Slot
from PySide6.QtGui import QColor

from yt_downloader.platforms.macos.header_host import _LIBRARY

_POINTER = ctypes.c_void_p
_ABI_VERSION = 1
# Nine-part materials: logical size, 2x pixels, equal corner caps.
_BUTTON_SIZE = (120, 44)
_FIELD_SIZE = (200, 40)
_CAP = 14
_THEME_ROLES = ("accent", "text", "muted", "icon", "selection", "surface")


@lru_cache(maxsize=1)
def _library():
    library = ctypes.CDLL(str(_LIBRARY))
    signatures = {
        "abi_version": (ctypes.c_uint, []),
        "create": (_POINTER, [_POINTER, ctypes.c_char_p]),
        "event_fd": (ctypes.c_int, [_POINTER]),
        "next_event": (ctypes.c_int, [_POINTER, ctypes.c_char_p, ctypes.c_size_t]),
        "set_color": (ctypes.c_int, [_POINTER, ctypes.c_char_p] + [ctypes.c_double] * 4),
        "set_material": (
            ctypes.c_int,
            [_POINTER, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_size_t]
            + [ctypes.c_double] * 3,
        ),
        "redraw": (ctypes.c_int, [_POINTER]),
        "set_selection": (ctypes.c_int, [_POINTER, ctypes.c_char_p]),
        "set_search": (
            ctypes.c_int,
            [_POINTER, ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p],
        ),
        "set_interactive": (ctypes.c_int, [_POINTER, ctypes.c_int]),
        "focus_search": (ctypes.c_int, [_POINTER]),
        "search_focused": (ctypes.c_int, [_POINTER]),
        "edit": (ctypes.c_int, [_POINTER, ctypes.c_char_p]),
        "anchor": (ctypes.c_int, [_POINTER, ctypes.c_char_p, ctypes.POINTER(ctypes.c_double)]),
        "chrome": (ctypes.c_int, [_POINTER, ctypes.POINTER(ctypes.c_double)]),
        "set_dim": (ctypes.c_int, [_POINTER, ctypes.c_int, ctypes.POINTER(ctypes.c_double)]),
        "height": (ctypes.c_double, [_POINTER]),
        "destroy": (ctypes.c_int, [_POINTER]),
    }
    for suffix, (result, arguments) in signatures.items():
        function = getattr(library, "vf_toolbar_" + suffix)
        function.restype, function.argtypes = result, arguments
    if library.vf_toolbar_abi_version() != _ABI_VERSION:
        raise RuntimeError("Incompatible native toolbar header")
    return library


def _png(image: Any) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def header_materials() -> dict[str, tuple[bytes, tuple[int, int]]]:
    """The exact Qt button/field materials, rendered at 2x for AppKit."""
    from yt_downloader.visual_chrome import action_button_image, field_border_image

    width, height = _BUTTON_SIZE
    materials = {
        "button-" + state: (
            _png(action_button_image(width, height, accent=False, state=state, density=2)),
            _BUTTON_SIZE,
        )
        for state in ("normal", "hover", "pressed")
    }
    width, height = _FIELD_SIZE
    for name, focused in (("field-normal", False), ("field-focus", True)):
        image = field_border_image(width, height, focused=focused, density=2)
        materials[name] = (_png(image), _FIELD_SIZE)
    return materials


def _rgba(value: Any) -> tuple[float, float, float, float]:
    color = value if isinstance(value, QColor) else QColor(str(value))
    if not color.isValid():
        raise ValueError("Invalid header color")
    return color.redF(), color.greenF(), color.blueF(), color.alphaF()


class NativeToolbarHeader(QObject):
    """One AppKit toolbar generation installed on the exact Qt main window."""

    navActivated = Signal(str)
    xActivated = Signal()
    settingsActivated = Signal()
    searchEdited = Signal(str)
    searchFocusedChanged = Signal()
    xHoveredChanged = Signal()
    geometryChanged = Signal()

    def __init__(self, window: Any, native_pointer: int, assets: Path):
        super().__init__(window)
        self._window = window
        self._library = _library()
        self._handle = self._library.vf_toolbar_create(
            native_pointer, str(assets).encode()
        )
        if not self._handle:
            raise RuntimeError("Native toolbar header refused this window")
        self._closed = False
        self._x_hovered = False
        self._search_focused = False
        self._toolbar_height = 0.0
        self._anchors = {name: QRectF() for name in ("settings", "x", "search")}
        self._buffer = ctypes.create_string_buffer(4096)
        try:
            self._notifier = QSocketNotifier(
                self._library.vf_toolbar_event_fd(self._handle),
                QSocketNotifier.Type.Read,
                self,
            )
            self._notifier.activated.connect(self._drain)
            window.destroyed.connect(self.close)
            self.applyTheme({})
            self._refresh_geometry()
        except Exception:
            self.close()
            raise

    # mac_windowing owner protocol
    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def retired(self) -> bool:
        return False

    def _drain(self, *_args) -> None:
        if self._closed:
            return
        while True:
            length = self._library.vf_toolbar_next_event(
                self._handle, self._buffer, len(self._buffer)
            )
            if length == 0:
                return
            if length < 0:
                if len(self._buffer) >= 1 << 20:
                    raise RuntimeError("Native toolbar event exceeds bound")
                self._buffer = ctypes.create_string_buffer(len(self._buffer) * 4)
                continue
            event = json.loads(self._buffer.value.decode())
            self._dispatch(event.get("kind", ""), event.get("value", ""))
            if self._closed:
                return

    def _dispatch(self, kind: str, value: str) -> None:
        if kind == "nav":
            self.navActivated.emit(value)
        elif kind == "x":
            self.xActivated.emit()
        elif kind == "settings":
            self.settingsActivated.emit()
        elif kind == "search":
            self.searchEdited.emit(value)
        elif kind in {"search_focus", "search_blur"}:
            focused = kind == "search_focus"
            if focused != self._search_focused:
                self._search_focused = focused
                self.searchFocusedChanged.emit()
        elif kind == "x_hover":
            hovered = value == "1"
            if hovered:
                self._refresh_geometry()
            if hovered != self._x_hovered:
                self._x_hovered = hovered
                self.xHoveredChanged.emit()
        elif kind == "layout":
            self._refresh_geometry()
        elif kind == "outside_press":
            self._press_dimmed_background()

    def _press_dimmed_background(self) -> None:
        """A press on the dimmed toolbar is a press on the window's dimmed
        background: let Qt's overlay apply each popup's own close policy."""
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QGuiApplication, QMouseEvent

        # Top-left corner: inside the header band, away from popups and anchors.
        local = QPointF(2, 2)
        world = QPointF(self._window.mapToGlobal(local.toPoint()))
        for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            buttons = Qt.MouseButton.LeftButton if kind == QEvent.Type.MouseButtonPress else Qt.MouseButton.NoButton
            event = QMouseEvent(
                kind, local, world, Qt.MouseButton.LeftButton, buttons,
                Qt.KeyboardModifier.NoModifier,
            )
            QGuiApplication.sendEvent(self._window, event)

    def _refresh_geometry(self) -> None:
        if self._closed:
            return
        changed = False
        height = float(self._library.vf_toolbar_height(self._handle))
        if height >= 0 and abs(height - self._toolbar_height) > 0.01:
            self._toolbar_height = height
            changed = True
        rect = (ctypes.c_double * 4)()
        for name in self._anchors:
            if self._library.vf_toolbar_anchor(self._handle, name.encode(), rect):
                anchor = QRectF(rect[0], rect[1], rect[2], rect[3])
                if anchor != self._anchors[name]:
                    self._anchors[name] = anchor
                    changed = True
        if changed:
            self.geometryChanged.emit()

    @Property(float, notify=geometryChanged)
    def toolbarHeight(self) -> float:
        return self._toolbar_height

    @Property(QRectF, notify=geometryChanged)
    def settingsAnchor(self) -> QRectF:
        return self._anchors["settings"]

    @Property(QRectF, notify=geometryChanged)
    def xAnchor(self) -> QRectF:
        return self._anchors["x"]

    @Property(bool, notify=xHoveredChanged)
    def xHovered(self) -> bool:
        return self._x_hovered

    @Property(bool, notify=searchFocusedChanged)
    def searchFocused(self) -> bool:
        return self._search_focused

    @Slot("QVariantMap")
    def applyTheme(self, colors: dict) -> None:
        """Push theme colors and re-render the shared materials."""
        if self._closed:
            return
        from yt_downloader.product_theme import THEME

        for role in _THEME_ROLES:
            value = colors.get(role) or THEME.get("bg" if role == "surface" else role)
            if value is None:
                continue
            if not self._library.vf_toolbar_set_color(
                self._handle, role.encode(), *_rgba(value)
            ):
                raise RuntimeError("Native toolbar refused a theme color")
        for name, (png, (width, height)) in header_materials().items():
            if not self._library.vf_toolbar_set_material(
                self._handle, name.encode(), png, len(png), width, height, _CAP
            ):
                raise RuntimeError("Native toolbar refused a material")
        self._library.vf_toolbar_redraw(self._handle)

    @Slot("QVariantList")
    def setDim(self, layers: list) -> None:
        """Qt's visible modal dim layers (bottom first) to repeat on the toolbar."""
        if self._closed:
            return
        values = [component for layer in layers[:16] for component in _rgba(layer)]
        array = (ctypes.c_double * max(1, len(values)))(*values)
        self._library.vf_toolbar_set_dim(self._handle, len(values) // 4, array)

    @Slot(str)
    def setSelection(self, name: str) -> None:
        if not self._closed:
            self._library.vf_toolbar_set_selection(self._handle, name.encode())

    @Slot(bool, str, str, str)
    def setSearch(self, visible: bool, placeholder: str, text: str, label: str) -> None:
        if not self._closed:
            self._library.vf_toolbar_set_search(
                self._handle,
                int(visible),
                placeholder.encode(),
                text.encode(),
                label.encode(),
            )
            self._refresh_geometry()

    @Slot(bool)
    def setInteractive(self, interactive: bool) -> None:
        if not self._closed:
            self._library.vf_toolbar_set_interactive(self._handle, int(interactive))

    @Slot(result="QVariantMap")
    def chromeState(self) -> dict:
        """AppKit window chrome now: fullscreen, transition (1 entering, 2
        exiting), how far the menu bar has pushed the toolbar down, toolbar x."""
        values = (ctypes.c_double * 4)()
        if self._closed or not self._library.vf_toolbar_chrome(self._handle, values):
            return {"fullscreen": False, "transition": 0, "revealed": 0.0, "x": 0.0}
        state = {
            "fullscreen": bool(values[0]),
            "transition": int(values[1]),
            "revealed": float(values[2]),
            "x": float(values[3]),
        }
        return state

    @Slot(result=bool)
    def focusSearch(self) -> bool:
        return not self._closed and bool(self._library.vf_toolbar_focus_search(self._handle))

    @Slot(str, result=bool)
    def edit(self, method: str) -> bool:
        return not self._closed and bool(self._library.vf_toolbar_edit(self._handle, method.encode()))

    @Slot()
    def close(self, *_args) -> None:
        if self._closed:
            return
        self._closed = True
        notifier = getattr(self, "_notifier", None)
        if notifier is not None:
            notifier.setEnabled(False)
        if self._handle:
            self._library.vf_toolbar_destroy(self._handle)
            self._handle = None
