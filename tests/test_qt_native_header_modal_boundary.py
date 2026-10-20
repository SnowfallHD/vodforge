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
    from yt_downloader.qt_quick import main as qt_main

    monkeypatch.setattr(qt_main, "_system_reduced_motion", lambda: False)
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
    main.setProperty("nativeHeaderInputReady", True)
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
                "host_screen": [0, 0, width, 44],
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


def test_unallocated_native_row_blocks_pointer_until_current_allocation(child_header):
    app, bridge, main, header, child, _boundary = child_header
    main.setProperty("nativeHeaderInputReady", False)
    settle(app, header)
    click(child, header, "navigationButton_Library")
    settle(app, header)
    assert bridge.selection == "Forge"
    assert not header.isEnabled()
    main.setProperty("nativeHeaderInputReady", True)
    settle(app, header)
    click(child, header, "navigationButton_Library")
    settle(app, header)
    assert bridge.selection == "Library"


@pytest.mark.parametrize("route", ["Forge", "Library", "Watch", "Activity"])
def test_header_material_distinguishes_rest_hover_and_held_press(
    child_header, route, tmp_path
):
    app, bridge, _main, header, child, _boundary = child_header
    bridge.selectHome(route)
    settle(app, header)
    button = visual_item(header, "navigationButton_" + route)
    faces = [
        item
        for item in button.childItems()
        if str(item.property("source")).startswith(
            "PySide6.QtCore.QUrl('image://vodforge/button/"
        )
    ]
    if not faces:
        faces = [
            item
            for item in button.childItems()
            if hasattr(item.property("source"), "toString")
            and item.property("source")
            .toString()
            .startswith("image://vodforge/button/")
        ]
    assert len(faces) == 1

    def state():
        return faces[0].property("source").toString().split("/")[6]

    QTest.mouseMove(child, QPoint(2, 55))
    settle(app, header)
    child.grabWindow().save(str(tmp_path / (route + "-rest.png")))
    assert state() == "normal", (
        "Selected route must not impersonate a held or hover face"
    )
    point = center(header, "navigationButton_" + route)
    QTest.mouseMove(child, point)
    settle(app, header)
    assert button.property("hovered") and state() == "hover"
    child.grabWindow().save(str(tmp_path / (route + "-hover.png")))
    try:
        QTest.mousePress(child, Qt.LeftButton, pos=point)
        settle(app, header)
        assert state() == "pressed"
        child.grabWindow().save(str(tmp_path / (route + "-pressed.png")))
    finally:
        QTest.mouseRelease(child, Qt.LeftButton, pos=point)
    settle(app, header)
    assert bridge.selection == route and state() == "hover"
    QTest.mouseMove(child, QPoint(2, 55))
    settle(app, header)
    assert state() == "normal"


def test_fullscreen_content_inset_glides_with_live_pointer_geometry(child_header):
    app, bridge, main, header, child, _boundary = child_header
    from PySide6.QtCore import QPointF

    main.resize(1440, 900)
    child.setGeometry(20, 0, 1400, 44)
    main.setProperty("nativeHeaderWidth", 1400)

    def publish(leading, origin=0):
        main.setProperty(
            "nativeRowPacket",
            {
                "schema_version": 1,
                "width": 1400,
                "height": 44,
                "host_screen": [origin, 0, 1400, 44],
                "leading": leading,
                "reserve": leading,
                "fullscreen": True,
                "state": "controls-visible" if leading else "controls-hidden",
                "body_slot_height": 44,
            },
        )

    publish(0)
    settle(app, header)
    body = main.findChild(QObject, "headerGeometrySlot").parentItem()
    bounds = (body.x(), body.y(), body.width(), body.height())
    publish(89)
    QTest.qWait(45)
    current = header.property("nativeHeaderInset")
    assert 0 < current < 89, "Own content shift must interpolate instead of snapping"
    anchor = header.property("nativeContentScreenX")
    child.setGeometry(37, 0, 1400, 44)
    publish(72, 17)  # Same screen destination; moving aperture must not restart it.
    assert header.property("nativeContentScreenX") == anchor
    assert header.property("nativeHeaderInset") == max(0, anchor - 17)
    values = [anchor]
    for route in ("Library", "Watch", "Activity", "Forge"):
        button = visual_item(header, "navigationButton_" + route)
        point = button.mapToScene(
            QPointF(button.width() / 2, button.height() / 2)
        ).toPoint()
        QTest.mouseClick(child, Qt.LeftButton, pos=point)
        app.processEvents()
        assert bridge.selection == route, (
            "Painted moving control and pointer geometry diverged"
        )
        QTest.qWait(32)
        values.append(header.property("nativeContentScreenX"))
    QTest.qWait(130)
    values.append(header.property("nativeContentScreenX"))
    assert values == sorted(values) and values[-1] == 89
    assert (body.x(), body.y(), body.width(), body.height()) == bounds
    main.setProperty("nativeHeaderReducedMotion", True)
    publish(0)
    app.processEvents()
    assert header.property("nativeHeaderInset") == 0


@pytest.mark.parametrize("scene_dx", [108, -108])
def test_passive_enter_uses_current_surface_not_ancestor_coordinates(
    child_header, scene_dx
):
    from PySide6.QtGui import QEnterEvent

    app, _bridge, _main, header, child, _boundary = child_header
    label = "Forge" if scene_dx > 0 else "Library"
    item = visual_item(header, "navigationButton_" + label)
    local = QPointF(center(header, "navigationButton_" + label))
    global_pos = QPointF(child.mapToGlobal(local.toPoint()))
    inherited = local + QPointF(scene_dx, 4)
    event = QEnterEvent(inherited, inherited, global_pos)
    QCoreApplication.sendEvent(child, event)
    settle(app, header)
    assert item.property("hovered") is True
    other = visual_item(
        header, "navigationButton_" + ("Library" if label == "Forge" else "Forge")
    )
    assert other.property("hovered") is False


@pytest.mark.parametrize("origin", [(96, 4), (-230, -40), (0, 0)])
def test_enter_current_mapping_survives_allocation_and_fractional_pointer(
    child_header, origin
):
    from PySide6.QtGui import QEnterEvent

    app, _bridge, _main, header, child, _boundary = child_header
    child.setPosition(QPoint(*origin))
    local = QPointF(center(header, "navigationButton_Forge")) + QPointF(0.25, -0.25)
    base = local.toPoint()
    global_pos = QPointF(child.mapToGlobal(base)) + local - QPointF(base)
    event = QEnterEvent(local + QPointF(108, 4), local + QPointF(108, 4), global_pos)
    delivered = []
    item = visual_item(header, "navigationButton_Forge")
    item.activated.connect(lambda: delivered.append(True))
    QCoreApplication.sendEvent(child, event)
    settle(app, header)
    assert item.property("hovered") is True
    assert delivered == []
    QCoreApplication.sendEvent(child, QEvent(QEvent.Leave))
    settle(app, header)
    assert item.property("hovered") is False


def test_enter_keeps_ready_modal_and_retired_guards(child_header):
    from PySide6.QtGui import QEnterEvent

    app, _bridge, main, header, child, boundary = child_header
    point = QPointF(center(header, "navigationButton_Forge"))
    global_pos = QPointF(child.mapToGlobal(point.toPoint()))

    def event():
        return QEnterEvent(point + QPointF(108, 4), point + QPointF(108, 4), global_pos)

    item = visual_item(header, "navigationButton_Forge")
    main.setProperty("nativeHeaderInputReady", False)
    QCoreApplication.sendEvent(child, event())
    settle(app, header)
    assert item.property("hovered") is False
    main.setProperty("nativeHeaderInputReady", True)
    popup = main.findChild(QObject, "downloadSettingsPopup")
    popup.setProperty("visible", True)
    assert not main.property("menuNavigationAllowed")
    QCoreApplication.sendEvent(child, event())
    settle(app, header)
    assert item.property("hovered") is False
    popup.setProperty("visible", False)
    QCoreApplication.sendEvent(child, event())
    settle(app, header)
    assert item.property("hovered") is True
    boundary.close()
    assert boundary.eventFilter(child, event()) is True


def test_menu_dismissal_returns_left_sooner_without_speeding_reveal(child_header):
    app, bridge, main, header, child, _boundary = child_header
    main.resize(1440, 900)
    child.setGeometry(20, 0, 1400, 44)

    def publish(leading):
        main.setProperty(
            "nativeRowPacket",
            {
                "schema_version": 1,
                "width": 1400,
                "height": 44,
                "host_screen": [0, 0, 1400, 44],
                "leading": leading,
                "reserve": leading,
                "fullscreen": True,
                "state": "controls-visible" if leading else "controls-hidden",
                "body_slot_height": 44,
            },
        )

    main.setProperty("nativeHeaderReducedMotion", True)
    publish(89)
    settle(app, header)
    main.setProperty("nativeHeaderReducedMotion", False)
    publish(0)
    QTest.qWait(45)
    left = header.property("nativeContentScreenX")
    assert 0 < left < 89
    button = visual_item(header, "navigationButton_Activity")
    at = button.mapToScene(QPointF(button.width() / 2, button.height() / 2)).toPoint()
    QTest.mouseClick(child, Qt.LeftButton, pos=at)
    assert bridge.selection == "Activity"
    QTest.qWait(95)
    assert header.property("nativeContentScreenX") <= 1, (
        "Dismissal must finish sooner than the 220ms reveal"
    )
    publish(89)
    QTest.qWait(140)
    reveal = header.property("nativeContentScreenX")
    assert 1 < reveal < 85, "Keep the liked slower reveal pacing"
    QTest.qWait(120)
    assert header.property("nativeContentScreenX") == 89


@pytest.mark.parametrize("origin", [(20, 4), (10, -44), (99, 4)])
def test_native_passive_route_updates_hover_without_qpa_enter(child_header, origin):
    """Fullscreen AppKit tracking may arrive without a Qt platform Enter."""
    app, bridge, _main, header, child, boundary = child_header
    child.setGeometry(*origin, 1050, 60)
    boundary.native_passive = True
    for index, name in enumerate(("Forge", "Library", "Watch", "Activity")):
        item = visual_item(header, "navigationButton_" + name)
        point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
        boundary.native_pointer(2, point.x(), point.y(), 1.25 + index)
        settle(app, header)
        assert item.property("hovered")
        assert bridge.selection == "Forge", "Passive tracking cannot navigate"
        # A platform Leave from the old logical window cannot clear the current
        # native tracking area's hover. Its exact own exit does clear it.
        QCoreApplication.sendEvent(child, QEvent(QEvent.Leave))
        assert item.property("hovered")
        boundary.native_pointer(3, -10, 20, 1.5 + index)
        settle(app, header)
        assert not item.property("hovered")
    click(child, header, "navigationButton_Library")
    assert bridge.selection == "Library", "Ordinary Qt presses retain ownership"


def test_native_passive_route_respects_modal_readiness_and_retirement(child_header):
    app, bridge, main, header, _child, boundary = child_header
    boundary.native_passive = True
    item = visual_item(header, "navigationButton_Library")
    point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
    boundary.native_pointer(1, point.x(), point.y(), 1)
    settle(app, header)
    assert item.property("hovered")
    main.setProperty("nativeHeaderInputReady", False)
    assert not item.property("hovered")
    boundary.native_pointer(2, point.x(), point.y(), 2)
    assert not item.property("hovered")
    main.setProperty("nativeHeaderInputReady", True)
    popup = main.findChild(QObject, "downloadSettingsPopup")
    popup.setProperty("visible", True)
    assert not main.property("menuNavigationAllowed")
    boundary.native_pointer(2, point.x(), point.y(), 3)
    assert not item.property("hovered")
    popup.setProperty("visible", False)
    boundary.native_pointer(2, point.x(), point.y(), 4)
    settle(app, header)
    assert item.property("hovered")
    boundary.native_pointer(3, -10, 20, 5)
    boundary.close()
    boundary.native_pointer(2, point.x(), point.y(), 6)
    assert not item.property("hovered")
    assert bridge.selection == "Forge"


@pytest.mark.parametrize(
    "kind,x,y,timestamp", [(0, 1, 1, 1), (2, float("nan"), 1, 1), (2, 1, 1, -1)]
)
def test_native_passive_route_refuses_malformed_non_action(
    child_header, kind, x, y, timestamp
):
    _app, bridge, _main, _header, _child, boundary = child_header
    with pytest.raises(ValueError, match="Invalid native passive"):
        boundary.native_pointer(kind, x, y, timestamp)
    assert bridge.selection == "Forge"


def test_native_passive_route_keeps_modal_gesture_with_original_main(child_header):
    app, bridge, main, header, child, boundary = child_header
    boundary.native_passive = True
    click(child, header, "headerSettingsButton")
    settle(app, header)
    popup = main.findChild(QObject, "downloadSettingsPopup")
    assert popup.property("visible") and not main.property("menuNavigationAllowed")
    point = center(header, "navigationButton_Library")
    boundary.native_pointer(2, point.x(), point.y(), 1)
    QTest.mousePress(child, Qt.LeftButton, pos=point)
    settle(app, header)
    assert not popup.property("visible")
    QTest.mouseRelease(child, Qt.LeftButton, pos=point)
    settle(app, header)
    assert bridge.selection == "Forge"
    click(child, header, "navigationButton_Library")
    assert bridge.selection == "Library"


@pytest.mark.parametrize("initial_wait", [80, 130])
def test_reveal_target_refinement_preserves_motion_instead_of_restarting(
    child_header, initial_wait
):
    """AppKit's later coherent allocation must not restart a near-moving reveal."""
    app, bridge, main, header, child, _boundary = child_header
    main.resize(1440, 900)
    child.setGeometry(20, 0, 1400, 44)

    def publish(target, origin=0):
        main.setProperty(
            "nativeRowPacket",
            {
                "schema_version": 1,
                "width": 1400,
                "height": 44,
                "host_screen": [origin, 0, 1400, 44],
                "leading": target - origin,
                "reserve": target - origin,
                "fullscreen": True,
                "state": "controls-visible" if target else "controls-hidden",
                "body_slot_height": 44,
            },
        )

    publish(0)
    settle(app, header)
    publish(89)
    QTest.qWait(initial_wait)
    before = header.property("nativeContentScreenX")
    QTest.qWait(32)
    moving = header.property("nativeContentScreenX")
    assert moving - before > 4, "Fixture must refine an actually moving reveal"
    publish(96, 17)
    assert header.property("nativeContentScreenX") == moving
    QTest.qWait(32)
    refined = header.property("nativeContentScreenX")
    assert refined - moving >= (moving - before) * 0.35, (
        "A later native target restarted easing and visibly stalled the reveal",
        before,
        moving,
        refined,
    )
    QTest.qWait(260)
    assert header.property("nativeContentScreenX") == 96
    assert header.property("nativeHeaderInset") == 79
    assert bridge.selection == "Forge", "Geometry refinement cannot navigate"


def test_menu_hide_finishes_before_previous_110ms_pacing(child_header):
    app, _bridge, main, header, child, _boundary = child_header
    main.resize(1440, 900)
    child.setGeometry(20, 0, 1400, 44)

    def publish(target):
        main.setProperty(
            "nativeRowPacket",
            {
                "schema_version": 1,
                "width": 1400,
                "height": 44,
                "host_screen": [0, 0, 1400, 44],
                "leading": target,
                "reserve": target,
                "fullscreen": True,
                "state": "controls-visible" if target else "controls-hidden",
                "body_slot_height": 44,
            },
        )

    main.setProperty("nativeHeaderReducedMotion", True)
    publish(96)
    settle(app, header)
    main.setProperty("nativeHeaderReducedMotion", False)
    publish(0)
    QTest.qWait(95)
    assert header.property("nativeContentScreenX") <= 0.5, (
        "The requested earlier return must finish before the former110ms pacing",
        header.property("nativeContentScreenX"),
    )
