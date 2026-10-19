"""Actual header/modal pointer ownership across the one integrated Qt surface."""

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch
from tests.test_qt_scene_port import polish_scene, visual_item
from yt_downloader.qt_quick.mac_header import create_header_input_boundary


def settle(app, header):
    QTest.qWait(80)
    for _ in range(3):
        app.processEvents()
        polish_scene(header)


def center(header, name):
    item = visual_item(header, name)
    return item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()


def click(target, header, name):
    QTest.mouseClick(target, Qt.LeftButton, pos=center(header, name))


def test_original_main_overlay_dismisses_and_consumes_same_header_gesture(
    tmp_path, monkeypatch
):
    """Retain only the qualified minimal original-window comparison."""
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    header = window.findChild(QObject, "focusHeader")
    try:
        window.resize(1100, 740)
        settle(app, header)
        settings = visual_item(header, "headerSettingsButton")
        QTest.mouseClick(
            window, Qt.LeftButton, pos=center(header, "headerSettingsButton")
        )
        settle(app, header)
        popup = window.findChild(QObject, "downloadSettingsPopup")
        assert popup.property("visible") and popup.property("modal")
        assert not window.property("menuNavigationAllowed")
        button = visual_item(header, "navigationButton_Library")
        point = button.mapToScene(
            QPointF(button.width() / 2, button.height() / 2)
        ).toPoint()
        QTest.mousePress(window, Qt.LeftButton, pos=point)
        settle(app, header)
        assert not popup.property("visible")
        assert bridge.selection == "Forge"
        QTest.mouseRelease(window, Qt.LeftButton, pos=point)
        settle(app, header)
        assert bridge.selection == "Forge"
        assert settings is not None
    finally:
        _close(bridge, engine, window)


@pytest.fixture
def child_header(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("VODFORGE_POSTHOG_ENABLED", "false")
    app, bridge, engine, main = _launch(tmp_path, monkeypatch, [])
    header = main.findChild(QObject, "focusHeader")
    original = header.parentItem()
    child = QQuickWindow(main)
    child.setFlags(Qt.SubWindow | Qt.FramelessWindowHint)
    child.resize(1050, 60)
    child.show()
    header.setParentItem(child.contentItem())
    main.setProperty("nativeHeaderSurface", child)
    main.setProperty("nativeHeaderWidth", 1050)
    main.setProperty("nativeHeaderAttached", True)
    boundary = create_header_input_boundary(main, child)
    settle(app, header)
    try:
        yield app, bridge, main, header, child, boundary
    finally:
        boundary.close()
        header.setParentItem(original)
        main.setProperty("nativeHeaderAttached", False)
        main.setProperty("nativeHeaderSurface", None)
        child.close()
        child.deleteLater()
        _close(bridge, engine, main)


def test_current_packet_centers_route_all_six_header_targets(child_header, monkeypatch):
    """Qt dispatch only: complements native hit mapping, not OS click proof."""
    from PySide6.QtCore import QMetaObject

    from yt_downloader.qt_quick import main as qt_main

    app, bridge, main, header, child, _boundary = child_header
    opened = []
    monkeypatch.setattr(
        qt_main.QDesktopServices,
        "openUrl",
        lambda url: opened.append(url.toString()) or True,
    )
    for index, (leading, width, y, fullscreen) in enumerate(
        [
            (44, 1080, 5, False),
            (10, 1400, -44, True),
            (99, 1400, 5, True),
            (44, 1080, 5, False),
        ]
    ):
        main.resize(width + 40, 740)
        child.setGeometry(20, y, width, 44)
        main.setProperty("nativeHeaderWidth", width)
        main.setProperty(
            "nativeRowPacket",
            {
                "schema_version": 1,
                "width": width,
                "height": 44,
                "leading": leading,
                "reserve": 0,
                "fullscreen": fullscreen,
                "state": "controls-visible",
                "body_slot_height": 44,
            },
        )
        settle(app, header)
        for route in ("Library", "Watch", "Activity", "Forge"):
            click(child, header, "navigationButton_" + route)
            settle(app, header)
            assert bridge.selection == route
            assert not main.findChild(QObject, "downloadSettingsPopup").property(
                "visible"
            )
        QTest.mouseMove(child, center(header, "headerXButton"))
        settle(app, header)
        QTest.mousePress(child, Qt.LeftButton, pos=center(header, "headerXButton"))
        settle(app, header)
        QTest.mouseRelease(child, Qt.LeftButton, pos=center(header, "headerXButton"))
        settle(app, header)
        assert opened == ["https://x.com/VODForge"] * (index + 1)
        assert bridge.selection == "Forge"
        click(child, header, "headerSettingsButton")
        settle(app, header)
        assert main.findChild(QObject, "downloadSettingsPopup").property("visible")
        assert bridge.selection == "Forge" and len(opened) == index + 1
        assert QMetaObject.invokeMethod(main, "closeDownloadSettings")
        settle(app, header)


@pytest.mark.parametrize("release_outside", [False, True])
def test_child_modal_retains_gesture_and_next_fresh_navigation(
    child_header, release_outside
):
    app, bridge, main, header, child, boundary = child_header
    click(child, header, "navigationButton_Library")
    settle(app, header)
    assert bridge.selection == "Library"
    click(child, header, "navigationButton_Forge")
    settle(app, header)
    click(child, header, "headerSettingsButton")
    settle(app, header)
    popup = main.findChild(QObject, "downloadSettingsPopup")
    assert popup.property("visible") and not main.property("menuNavigationAllowed")
    point = center(header, "navigationButton_Library")
    QTest.mousePress(child, Qt.LeftButton, pos=point)
    settle(app, header)
    assert not popup.property("visible") and bridge.selection == "Forge"
    release = QPoint(5, 55) if release_outside else point
    QTest.mouseMove(child, release)
    QTest.mouseRelease(child, Qt.LeftButton, pos=release)
    settle(app, header)
    assert bridge.selection == "Forge" and not boundary.owned
    click(child, header, "navigationButton_Library")
    settle(app, header)
    assert bridge.selection == "Library"


@pytest.mark.parametrize("primed", [False, True])
def test_modal_blocks_new_hover_and_retires_primed_hover(child_header, primed):
    app, _bridge, main, header, child, _boundary = child_header
    if primed:
        QTest.mouseMove(child, center(header, "headerSettingsButton"))
        settle(app, header)
        assert visual_item(header, "headerSettingsButton").property("hovered")
    click(child, header, "headerSettingsButton")
    settle(app, header)
    assert main.findChild(QObject, "downloadSettingsPopup").property("visible")
    assert not visual_item(header, "headerSettingsButton").property("hovered")
    if not primed:
        QTest.mouseMove(child, center(header, "headerXButton"))
        settle(app, header)
        button = visual_item(header, "headerXButton")
        assert not button.property("hovered")
        tooltips = [
            item
            for item in button.findChildren(QObject)
            if item.metaObject().className().startswith("LiquidToolTip")
        ]
        assert tooltips and all(not item.property("visible") for item in tooltips)


class WheelObserver(QObject):
    def __init__(self, main):
        super().__init__()
        self.events = []
        main.installEventFilter(self)

    def eventFilter(self, _watched, event):
        if event.type() == QEvent.Wheel:
            self.events.append(QWheelEvent(event))
        return False


def test_modal_wheel_reaches_original_overlay_with_payload(child_header):
    app, _bridge, main, header, child, _boundary = child_header
    click(child, header, "navigationButton_Library")
    settle(app, header)
    click(child, header, "headerSettingsButton")
    settle(app, header)
    observer = WheelObserver(main)
    pos = QPointF(center(header, "headerSearchInput"))
    global_pos = QPointF(child.mapToGlobal(pos.toPoint()))
    event = QWheelEvent(
        pos,
        global_pos,
        QPoint(0, 7),
        QPoint(0, 120),
        Qt.NoButton,
        Qt.ControlModifier,
        Qt.ScrollUpdate,
        True,
    )
    event.setTimestamp(12345)
    QCoreApplication.sendEvent(child, event)
    settle(app, header)
    assert len(observer.events) == 1
    forwarded = observer.events[0]
    assert forwarded.position() == QPointF(main.mapFromGlobal(global_pos.toPoint()))
    assert forwarded.globalPosition() == global_pos
    assert forwarded.pixelDelta() == event.pixelDelta()
    assert forwarded.angleDelta() == event.angleDelta()
    assert forwarded.modifiers() == event.modifiers()
    assert forwarded.phase() == event.phase()
    assert forwarded.inverted() == event.inverted()
    assert forwarded.source() == event.source()
    assert forwarded.pointingDevice() == event.pointingDevice()
    assert forwarded.timestamp() == event.timestamp()
    assert main.findChild(QObject, "downloadSettingsPopup").property("visible")


@pytest.mark.parametrize("release_elsewhere", [False, True])
def test_cancelled_gesture_fences_old_release_and_accepts_fresh_press(
    child_header, release_elsewhere
):
    app, bridge, _main, header, child, boundary = child_header
    click(child, header, "headerSettingsButton")
    settle(app, header)
    point = center(header, "navigationButton_Library")
    QTest.mousePress(child, Qt.LeftButton, pos=point)
    settle(app, header)
    assert boundary.owned
    QCoreApplication.sendEvent(child, QEvent(QEvent.WindowDeactivate))
    assert boundary.cancelled_gesture and not boundary.owned
    elsewhere = QQuickWindow()
    elsewhere.resize(80, 60)
    elsewhere.show()
    try:
        QTest.mouseRelease(
            elsewhere if release_elsewhere else child, Qt.LeftButton, pos=point
        )
        settle(app, header)
        assert bridge.selection == "Forge"
        assert boundary.cancelled_gesture == release_elsewhere
        QCoreApplication.sendEvent(child, QEvent(QEvent.WindowActivate))
        click(child, header, "navigationButton_Library")
        settle(app, header)
        assert bridge.selection == "Library" and not boundary.cancelled_gesture
    finally:
        elsewhere.close()
        elsewhere.deleteLater()


def test_boundary_close_disconnects_gate_and_removes_exact_filter(
    child_header, monkeypatch
):
    _app, _bridge, main, _header, child, boundary = child_header
    removed = []
    original_remove = child.removeEventFilter

    def remove(item):
        removed.append(item)
        original_remove(item)

    monkeypatch.setattr(child, "removeEventFilter", remove)
    boundary.close()
    boundary.close()
    assert boundary.retired and removed == [boundary]
    assert not boundary.owned and not boundary.cancelled_gesture
    # Signal remains live on main, but the closed boundary must be disconnected.
    main.setProperty("nativeHeaderAttached", False)


@pytest.mark.parametrize("stale", [False, True])
def test_closed_or_deleted_original_owner_refuses_late_input(
    tmp_path, monkeypatch, stale
):
    from shiboken6 import isValid

    app, bridge, engine, main = _launch(tmp_path, monkeypatch, [])
    surface = QQuickWindow()
    surface.resize(80, 60)
    surface.show()

    class TailObserver(QObject):
        def __init__(self):
            super().__init__()
            self.presses = 0

        def eventFilter(self, _watched, event):
            if event.type() == QEvent.MouseButtonPress:
                self.presses += 1
            return False

    tail = TailObserver()
    surface.installEventFilter(tail)
    boundary = create_header_input_boundary(main, surface)
    try:
        main.close()
        if stale:
            engine.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            assert not isValid(main)
        else:
            assert not main.isVisible()
        QTest.mouseClick(surface, Qt.LeftButton, pos=QPoint(10, 10))
        app.processEvents()
        assert tail.presses == 0
    finally:
        boundary.close()
        surface.close()
        surface.deleteLater()
        if isValid(main):
            _close(bridge, engine, main)
        else:
            bridge.close()
