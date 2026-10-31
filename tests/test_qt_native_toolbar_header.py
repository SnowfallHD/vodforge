"""Main.qml wiring for the AppKit toolbar header (mac_toolbar_header.py).

A stand-in exposes the exact Qt interface of NativeToolbarHeader, so these
tests cover the scene contract on every platform: what the native controls'
events do, what state the scene pushes back, and how the body makes room.
Native drawing and AppKit motion are exercised separately by native QA.
"""

import pytest
from PySide6.QtCore import Property, QMetaObject, QObject, QRectF, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch
from tests.test_qt_scene_port import polish_scene


class FakeToolbar(QObject):
    navActivated = Signal(str)
    xActivated = Signal()
    settingsActivated = Signal()
    searchEdited = Signal(str)
    searchFocusedChanged = Signal()
    xHoveredChanged = Signal()
    geometryChanged = Signal()

    def __init__(self):
        super().__init__()
        self.calls = []
        self.focused = False
        self.hovered = False
        self.chrome = {"fullscreen": False, "transition": 0, "revealed": 0.0, "x": 6.0}

    def settle_focus(self, focused):
        self.focused = focused
        self.searchFocusedChanged.emit()

    @Property(float, notify=geometryChanged)
    def toolbarHeight(self):
        return 52.0

    @Property(QRectF, notify=geometryChanged)
    def settingsAnchor(self):
        return QRectF(1060, 6, 32, 40)

    @Property(QRectF, notify=geometryChanged)
    def xAnchor(self):
        return QRectF(1020, 6, 36, 40)

    @Property(bool, notify=xHoveredChanged)
    def xHovered(self):
        return self.hovered

    @Property(bool, notify=searchFocusedChanged)
    def searchFocused(self):
        return self.focused

    @Slot("QVariantMap")
    def applyTheme(self, colors):
        self.calls.append(("theme", sorted(colors)))

    @Slot(str)
    def setSelection(self, name):
        self.calls.append(("selection", name))

    @Slot(bool, str, str, str)
    def setSearch(self, visible, placeholder, text, label):
        self.calls.append(("search", visible, placeholder, text, label))

    @Slot(bool)
    def setInteractive(self, interactive):
        self.calls.append(("interactive", interactive))

    @Slot("QVariantList")
    def setDim(self, layers):
        self.calls.append(
            ("dim", [layer.name(QColor.NameFormat.HexArgb) for layer in layers])
        )

    @Slot(result="QVariantMap")
    def chromeState(self):
        return dict(self.chrome)

    @Slot(str, result=bool)
    def edit(self, method):
        self.calls.append(("edit", method))
        return True


def _settle(app, window):
    QTest.qWait(60)
    for _ in range(3):
        app.processEvents()
        polish_scene(window.contentItem())


def _scene(tmp_path, monkeypatch):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    window.resize(1100, 740)
    toolbar = FakeToolbar()
    window.setProperty("nativeToolbar", toolbar)
    _settle(app, window)
    return app, bridge, engine, window, toolbar


def test_native_toolbar_replaces_qt_header_and_body_clears_it(tmp_path, monkeypatch):
    _app, bridge, engine, window, toolbar = _scene(tmp_path, monkeypatch)
    try:
        header = window.findChild(QObject, "focusHeader")
        slot = window.findChild(QObject, "headerGeometrySlot")
        assert header.property("visible") is False
        # Body starts exactly at the native toolbar's lower edge.
        assert slot.property("height") == 52 - 5
        assert slot.mapToScene(slot.boundingRect().bottomLeft()).y() == 52
        assert (
            "theme",
            ["accent", "icon", "muted", "selection", "surface", "text"],
        ) in toolbar.calls
        assert ("selection", "Forge") in toolbar.calls
        assert any(c[0] == "search" and c[1] is False for c in toolbar.calls)
    finally:
        _close(bridge, engine, window)


def test_native_toolbar_events_drive_navigation_search_and_settings(
    tmp_path, monkeypatch
):
    app, bridge, engine, window, toolbar = _scene(tmp_path, monkeypatch)
    try:
        toolbar.calls.clear()
        toolbar.navActivated.emit("Library")
        _settle(app, window)
        assert bridge.selection == "Library"
        assert ("selection", "Library") in toolbar.calls
        assert (
            "search",
            True,
            "Search your library…",
            "",
            "Search library",
        ) in toolbar.calls

        toolbar.searchEdited.emit("ocean")
        _settle(app, window)
        assert bridge.activeSearch == "ocean"
        assert toolbar.calls[-1] == (
            "search",
            True,
            "Search your library…",
            "ocean",
            "Search library",
        )

        popup = window.findChild(QObject, "downloadSettingsPopup")
        toolbar.settingsActivated.emit()
        _settle(app, window)
        assert popup.property("visible")
        assert ("interactive", False) in toolbar.calls
        # Like a Qt header press: dismisses the modal popup, does not navigate.
        toolbar.navActivated.emit("Watch")
        _settle(app, window)
        assert not popup.property("visible")
        assert bridge.selection == "Library"
        assert (
            toolbar.calls[-1] == ("interactive", True)
            or ("interactive", True) in toolbar.calls
        )

        toolbar.settingsActivated.emit()
        _settle(app, window)
        assert popup.property("visible")
        toolbar.settingsActivated.emit()  # the same button closes it again
        _settle(app, window)
        assert not popup.property("visible")

        toolbar.navActivated.emit("Watch")
        _settle(app, window)
        assert bridge.selection == "Watch"
        assert toolbar.calls[-1][0] == "search" and toolbar.calls[-1][1] is True
        assert toolbar.calls[-1][2] == "Search saved videos…"
    finally:
        _close(bridge, engine, window)


def test_edit_menu_routes_to_focused_native_search(tmp_path, monkeypatch):
    app, bridge, engine, window, toolbar = _scene(tmp_path, monkeypatch)
    try:
        menu = next(
            obj
            for obj in window.findChildren(QObject)
            if obj.metaObject().indexOfMethod("edit(QVariant)") >= 0
        )
        toolbar.calls.clear()
        menu.edit("paste")
        assert ("edit", "paste") not in toolbar.calls  # not focused: Qt owns editing
        toolbar.settle_focus(True)
        _settle(app, window)
        menu.edit("paste")
        assert ("edit", "paste") in toolbar.calls
    finally:
        _close(bridge, engine, window)


def _picker(window):
    phases = []
    window.setProperty("pickerTimelineEnabled", True)
    window.pickerTimelinePhase.connect(phases.append)
    return phases


def _close_picker(window):
    dialog = window.findChild(QObject, "outputFolderDialog")
    if dialog:
        QMetaObject.invokeMethod(dialog, "close")


def test_folder_dialog_waits_for_menu_bar_to_settle(tmp_path, monkeypatch):
    """Recorded regression: opening the panel while the fullscreen menu bar
    retreats stalls AppKit's slide (header overlaps the window buttons)."""
    _app, bridge, engine, window, toolbar = _scene(tmp_path, monkeypatch)
    phases = _picker(window)
    try:
        toolbar.chrome = {
            "fullscreen": True,
            "transition": 0,
            "revealed": 24.0,
            "x": 84.0,
        }
        QMetaObject.invokeMethod(window, "openOutputFolderDialog")
        QMetaObject.invokeMethod(window, "openOutputFolderDialog")  # repeat coalesces
        for revealed, x in ((18.0, 60.0), (9.0, 30.0), (2.0, 10.0)):
            QTest.qWait(40)
            toolbar.chrome = {
                "fullscreen": True,
                "transition": 0,
                "revealed": revealed,
                "x": x,
            }
        QTest.qWait(40)
        assert 3 not in phases, "native open began while the menu bar was moving"
        toolbar.chrome = {
            "fullscreen": True,
            "transition": 0,
            "revealed": 0.0,
            "x": 6.0,
        }
        QTest.qWait(40)
        assert 3 not in phases, "opened before the chrome stayed still"
        QTest.qWait(160)
        assert phases.count(3) == 1
    finally:
        _close_picker(window)
        _close(bridge, engine, window)


@pytest.mark.parametrize(
    "chrome",
    [
        {"fullscreen": True, "transition": 0, "revealed": 24.0, "x": 84.0},
        {"fullscreen": True, "transition": 1, "revealed": 0.0, "x": 6.0},
    ],
)
def test_folder_dialog_wait_is_bounded(tmp_path, monkeypatch, chrome):
    _app, bridge, engine, window, toolbar = _scene(tmp_path, monkeypatch)
    phases = _picker(window)
    try:
        toolbar.chrome = chrome  # menu bar held down / fullscreen switch stuck
        QMetaObject.invokeMethod(window, "openOutputFolderDialog")
        QTest.qWait(600)
        assert 3 not in phases
        QTest.qWait(600)
        assert phases.count(3) == 1
    finally:
        _close_picker(window)
        _close(bridge, engine, window)


@pytest.mark.parametrize("fullscreen", [False, True])
def test_folder_dialog_opens_at_once_when_chrome_is_settled(
    tmp_path, monkeypatch, fullscreen
):
    _app, bridge, engine, window, toolbar = _scene(tmp_path, monkeypatch)
    phases = _picker(window)
    try:
        toolbar.chrome = {
            "fullscreen": fullscreen,
            "transition": 0,
            "revealed": 0.0,
            "x": 6.0,
        }
        QMetaObject.invokeMethod(window, "openOutputFolderDialog")
        assert phases.count(3) == 1 and 7 not in phases
    finally:
        _close_picker(window)
        _close(bridge, engine, window)


def test_toolbar_repeats_qt_modal_dim_and_clears_it(tmp_path, monkeypatch):
    app, bridge, engine, window, toolbar = _scene(tmp_path, monkeypatch)
    try:
        popup = window.findChild(QObject, "downloadSettingsPopup")
        toolbar.calls.clear()
        toolbar.settingsActivated.emit()
        _settle(app, window)
        assert popup.property("visible")
        dims = [c[1] for c in toolbar.calls if c[0] == "dim"]
        assert dims and dims[-1], "modal popup open but toolbar not dimmed"
        # Basic style modal dim: palette shadow at 50% alpha.
        assert all(layer.startswith(("#7f", "#80")) for layer in dims[-1])
        QMetaObject.invokeMethod(popup, "close")
        _settle(app, window)
        assert [c[1] for c in toolbar.calls if c[0] == "dim"][-1] == []
    finally:
        _close(bridge, engine, window)


def test_press_on_dimmed_toolbar_is_a_background_press(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from yt_downloader.qt_quick.mac_toolbar_header import NativeToolbarHeader

    app, bridge, engine, window, toolbar = _scene(tmp_path, monkeypatch)
    try:
        popup = window.findChild(QObject, "downloadSettingsPopup")
        toolbar.settingsActivated.emit()
        _settle(app, window)
        assert popup.property("visible")
        NativeToolbarHeader._press_dimmed_background(SimpleNamespace(_window=window))
        _settle(app, window)
        assert not popup.property("visible"), "background press did not dismiss popup"
        assert bridge.selection == "Forge"
        # The dismissing press is not remembered as a Settings-button press:
        # the next Settings click opens the popup again.
        toolbar.settingsActivated.emit()
        _settle(app, window)
        assert popup.property("visible")
    finally:
        _close(bridge, engine, window)
