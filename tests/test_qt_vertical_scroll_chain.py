"""Offscreen event-delivery regression; this does not prove native macOS input."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QInputDevice, QPointingDevice, QWheelEvent
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow

QML_DIR = Path(__file__).resolve().parents[1] / "yt_downloader" / "qt_quick"


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
        (360, -80, 380, 60),  # same event crosses bottom: only remainder
        (380, -80, 380, 80),  # bottom continues onto page
        (20, 80, 0, -60),  # same event crosses top
        (0, 80, 0, -80),  # top continues onto page
        (380, 80, 300, 0),  # reversal at bottom stays inner
        (0, -80, 80, 0),  # reversal at top stays inner
    ],
)
def test_vertical_event_chains_once(
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
    detail = (QML_DIR / "LibraryDetail.qml").read_text()
    inspector = (QML_DIR / "LibraryFolderInspector.qml").read_text()
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
    QGuiApplication.sendEvent(window, event)
    app.processEvents()
    assert inner.property("contentY") == 380
    assert outer.property("contentY") == 700
