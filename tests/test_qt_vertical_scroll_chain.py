"""Offscreen event-delivery regression; this does not prove native macOS input."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from itertools import count

import pytest
from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QInputDevice, QPointingDevice, QWheelEvent
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow

QML_DIR = Path(__file__).resolve().parents[1] / "yt_downloader" / "qt_quick"


_WHEEL_TIMESTAMPS = count(1)


@pytest.fixture
def scroll_scene():
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        b"""
import QtQuick
import QtQuick.Controls
Window {
    width: 400; height: 300; visible: true
    ScrollView {
        id: outer; objectName: "outer"; anchors.fill: parent
        contentHeight: 1000
        VerticalScrollChain { nestedScrollView: outer }
        Column {
            width: outer.availableWidth
            ScrollView {
                id: inner; objectName: "inner"; width: 350; height: 120
                contentHeight: 500
                VerticalScrollChain { nestedScrollView: inner }
                Text { width: 320; height: 500; text: "Description" }
            }
            Item { width: 350; height: 880 }
        }
    }
}
""",
        QUrl.fromLocalFile(str(QML_DIR / "ScrollChainRegression.qml")),
    )
    window = component.create()
    assert isinstance(window, QQuickWindow), [
        error.toString() for error in component.errors()
    ]
    for _ in range(5):
        app.processEvents()
    outer = window.findChild(QObject, "outer").property("contentItem")
    inner_view = window.findChild(QObject, "inner")
    inner = inner_view.property("contentItem")
    yield app, window, outer, inner_view, inner
    window.close()
    window.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("pixels", [True, False])
@pytest.mark.parametrize(
    "start,delta,expected_inner,expected_outer",
    [
        (100, -80, 180, 0),  # inner can still move
        (360, -80, 380, 0),  # edge-reaching gesture stays inner
        (380, -80, 380, 0),  # overflowing field keeps pointer ownership
        (20, 80, 0, 0),  # edge-reaching gesture stays inner
        (0, 80, 0, 0),  # overflowing field keeps pointer ownership
        (380, 80, 300, 0),  # reversal at bottom stays inner
        (0, -80, 80, 0),  # reversal at top stays inner
    ],
)
def test_vertical_event_routes_once(
    scroll_scene, pixels, start, delta, expected_inner, expected_outer
):
    app, window, outer, inner_view, inner = scroll_scene
    # Keep the nested view under the pointer while giving the page room both ways.
    outer.setProperty("contentY", 0)
    inner.setProperty("contentY", start)
    # Translate the inner visual position when testing upward page movement.
    if delta > 0:
        outer.setProperty("contentY", 100)
        inner_view.setProperty("y", 100)
    before = outer.property("contentY")
    point = inner_view.mapToScene(QPointF(40, 40))
    event = QWheelEvent(
        point,
        point,
        QPoint(0, delta) if pixels else QPoint(),
        QPoint() if pixels else QPoint(0, delta * 120 // 80),
        Qt.NoButton,
        Qt.NoModifier,
        Qt.ScrollUpdate,
        False,
    )
    event.setTimestamp(next(_WHEEL_TIMESTAMPS))
    QGuiApplication.sendEvent(window, event)
    app.processEvents()
    assert inner.property("contentY") == pytest.approx(expected_inner)
    assert outer.property("contentY") - before == pytest.approx(expected_outer)


def test_no_overflow_and_horizontal_trackpad(scroll_scene):
    app, window, outer, inner_view, inner = scroll_scene
    inner_view.setProperty("contentHeight", 100)
    point = inner_view.mapToScene(QPointF(40, 40))
    trackpad = QPointingDevice(
        "Test trackpad",
        47,
        QInputDevice.DeviceType.TouchPad,
        QPointingDevice.PointerType.Finger,
        QInputDevice.Capability.Position,
        1,
        0,
    )

    def send(dx, dy, phase):
        event = QWheelEvent(
            point,
            point,
            QPoint(dx, dy),
            QPoint(),
            Qt.NoButton,
            Qt.NoModifier,
            phase,
            False,
            Qt.MouseEventNotSynthesized,
            trackpad,
        )
        event.setTimestamp(next(_WHEEL_TIMESTAMPS))
        QGuiApplication.sendEvent(window, event)
        app.processEvents()

    send(-3, -53, Qt.ScrollBegin)
    send(-4, -61, Qt.ScrollMomentum)
    assert inner.property("contentY") == 0
    assert outer.property("contentY") == pytest.approx(114)
    before = outer.property("contentY")
    send(-80, 0, Qt.ScrollUpdate)
    assert outer.property("contentY") == before


def test_production_vertical_seams():
    detail = (QML_DIR / "LibraryDetail.qml").read_text(encoding="utf-8")
    inspector = (QML_DIR / "LibraryFolderInspector.qml").read_text(encoding="utf-8")
    assert "VerticalScrollChain { nestedScrollView: descriptionScroll }" in detail
    for name in ("filePanel", "issuePanel", "tagsScroll", "descriptionScroll"):
        assert f"VerticalScrollChain {{ nestedScrollView: {name} }}" in inspector


def test_outer_edge_does_not_replay_delta(scroll_scene):
    app, window, outer, inner_view, inner = scroll_scene
    inner.setProperty("contentY", 380)
    outer.setProperty("contentY", 680)
    inner_view.setProperty("y", 680)
    point = inner_view.mapToScene(QPointF(40, 40))
    event = QWheelEvent(
        point,
        point,
        QPoint(0, -80),
        QPoint(),
        Qt.NoButton,
        Qt.NoModifier,
        Qt.ScrollUpdate,
        False,
    )
    event.setTimestamp(next(_WHEEL_TIMESTAMPS))
    QGuiApplication.sendEvent(window, event)
    app.processEvents()
    assert inner.property("contentY") == 380
    assert outer.property("contentY") == 680


@pytest.mark.parametrize("at_top", [False, True])
def test_phase_gesture_and_new_begin_stay_in_overflowing_field(scroll_scene, at_top):
    app, window, outer, inner_view, inner = scroll_scene
    if at_top:
        outer.setProperty("contentY", 100)
        inner_view.setProperty("y", 100)
    inner.setProperty("contentY", 20 if at_top else 360)
    point = inner_view.mapToScene(QPointF(40, 40))
    delta = 80 if at_top else -80
    before = outer.property("contentY")

    def send(dy, phase):
        event = QWheelEvent(
            point,
            point,
            QPoint(0, dy),
            QPoint(),
            Qt.NoButton,
            Qt.NoModifier,
            phase,
            False,
        )
        event.setTimestamp(next(_WHEEL_TIMESTAMPS))
        QGuiApplication.sendEvent(window, event)
        app.processEvents()

    send(delta, Qt.ScrollBegin)
    send(delta, Qt.ScrollUpdate)
    send(0, Qt.ScrollEnd)
    send(delta, Qt.ScrollMomentum)
    assert outer.property("contentY") == before
    assert inner.property("contentY") == (0 if at_top else 380)
    send(delta, Qt.ScrollBegin)
    assert outer.property("contentY") == before


def test_mouse_pause_and_reversal_stay_local(scroll_scene):
    app, window, outer, inner_view, inner = scroll_scene
    inner.setProperty("contentY", 360)
    point = inner_view.mapToScene(QPointF(40, 40))

    def send(dy):
        event = QWheelEvent(
            point,
            point,
            QPoint(),
            QPoint(0, dy * 120 // 80),
            Qt.NoButton,
            Qt.NoModifier,
            Qt.NoScrollPhase,
            False,
        )
        event.setTimestamp(next(_WHEEL_TIMESTAMPS))
        QGuiApplication.sendEvent(window, event)
        app.processEvents()

    send(-80)
    send(-80)
    assert outer.property("contentY") == 0
    send(80)
    assert inner.property("contentY") == 300
    send(-80)
    from PySide6.QtTest import QTest

    QTest.qWait(250)
    send(-80)
    assert outer.property("contentY") == 0


@pytest.mark.parametrize("at_top", [False, True])
@pytest.mark.parametrize("pixels", [False, True])
@pytest.mark.parametrize("content_height", [0, 100, 120])
def test_nonoverflow_after_prior_scroll_passes_without_bump(
    scroll_scene, at_top, pixels, content_height
):
    app, window, outer, inner_view, inner = scroll_scene
    outer.setProperty("contentY", 100)
    inner_view.setProperty("y", 100)
    inner.setProperty("contentY", 20 if at_top else 360)
    point = inner_view.mapToScene(QPointF(40, 40))
    delta = 80 if at_top else -80

    def send(phase):
        event = QWheelEvent(
            point,
            point,
            QPoint(0, delta) if pixels else QPoint(),
            QPoint() if pixels else QPoint(0, delta * 120 // 80),
            Qt.NoButton,
            Qt.NoModifier,
            phase,
            False,
        )
        event.setTimestamp(next(_WHEEL_TIMESTAMPS))
        QGuiApplication.sendEvent(window, event)
        app.processEvents()

    send(Qt.ScrollBegin)
    assert outer.property("contentY") == 100
    inner_view.setProperty("contentHeight", content_height)
    app.processEvents()
    send(Qt.ScrollUpdate)
    assert outer.property("contentY") == pytest.approx(100 - delta)


def test_fast_long_momentum_and_pause_never_escape_field(scroll_scene):
    from PySide6.QtTest import QTest

    app, window, outer, inner_view, inner = scroll_scene
    inner.setProperty("contentY", 360)
    point = inner_view.mapToScene(QPointF(40, 40))

    def send(delta, phase):
        event = QWheelEvent(
            point,
            point,
            QPoint(0, delta),
            QPoint(),
            Qt.NoButton,
            Qt.NoModifier,
            phase,
            False,
        )
        event.setTimestamp(next(_WHEEL_TIMESTAMPS))
        QGuiApplication.sendEvent(window, event)
        app.processEvents()

    send(-1200, Qt.ScrollBegin)
    for _ in range(50):
        send(-1200, Qt.ScrollUpdate)
    QTest.qWait(250)
    for _ in range(20):
        send(-1200, Qt.ScrollMomentum)
    send(0, Qt.ScrollEnd)
    send(-1200, Qt.ScrollBegin)
    assert inner.property("contentY") == 380
    assert outer.property("contentY") == 0
    send(80, Qt.ScrollUpdate)
    assert inner.property("contentY") == 300
    assert outer.property("contentY") == 0


def test_moving_pointer_outside_field_scrolls_page(scroll_scene):
    app, window, outer, _inner_view, inner = scroll_scene
    inner.setProperty("contentY", 380)
    point = QPointF(380, 200)
    event = QWheelEvent(
        point,
        point,
        QPoint(0, -80),
        QPoint(),
        Qt.NoButton,
        Qt.NoModifier,
        Qt.ScrollUpdate,
        False,
    )
    event.setTimestamp(next(_WHEEL_TIMESTAMPS))
    QGuiApplication.sendEvent(window, event)
    app.processEvents()
    assert outer.property("contentY") == 80
    assert inner.property("contentY") == 380


def test_content_growing_gains_local_scroll_ownership(scroll_scene):
    app, window, outer, inner_view, inner = scroll_scene
    inner_view.setProperty("contentHeight", 100)
    point = inner_view.mapToScene(QPointF(40, 40))

    def send():
        event = QWheelEvent(
            point,
            point,
            QPoint(0, -80),
            QPoint(),
            Qt.NoButton,
            Qt.NoModifier,
            Qt.ScrollUpdate,
            False,
        )
        event.setTimestamp(next(_WHEEL_TIMESTAMPS))
        QGuiApplication.sendEvent(window, event)
        app.processEvents()

    send()
    assert outer.property("contentY") == 80
    outer.setProperty("contentY", 0)
    inner_view.setProperty("contentHeight", 500)
    app.processEvents()
    send()
    assert outer.property("contentY") == 0
    assert inner.property("contentY") == 80


def test_keyboard_scroll_still_reaches_focused_field(scroll_scene):
    from PySide6.QtTest import QTest

    app, window, outer, inner_view, inner = scroll_scene
    inner_view.forceActiveFocus(Qt.TabFocusReason)
    app.processEvents()
    QTest.keyClick(window, Qt.Key_Down)
    app.processEvents()
    assert inner.property("contentY") > 0
    assert outer.property("contentY") == 0
