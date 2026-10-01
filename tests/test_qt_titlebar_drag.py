"""Titlebar handoff must not retain a Qt grab after Cocoa consumes mouse-up.

Exercise the production MouseArea, replacing only the native move call. Cocoa's
synchronous drag loop can consume release rather than delivering it to QML.
Geometry-only header tests never exercised this ownership transition. Native
signed-app acceptance remains separate from this offscreen causal regression.
"""

import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QUICK_BACKEND"] = "software"

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QMouseEvent
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow

_APP = None


@pytest.fixture
def header():
    global _APP
    _APP = QGuiApplication.instance() or QGuiApplication([])
    source = (Path(__file__).parents[1] / "yt_downloader/qt_quick/Main.qml").read_text()
    marker = 'objectName: "headerDragArea"'
    start = source.rfind("MouseArea {", 0, source.index(marker))
    depth = 0
    for end in range(start + source[start:].index("{"), len(source)):
        depth += (source[end] == "{") - (source[end] == "}")
        if depth == 0:
            break
    block = source[start : end + 1]
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        (
            """import QtQuick
Item {
    id: window
    width: 400; height: 44
    property int gutter: 0
    property int moves: 0
    property bool moveAccepted: true
    property int clicks: 0
    function startSystemMove() { moves += 1; return moveAccepted }
    Item {
        anchors.fill: parent
        """
            + block
            + """
        MouseArea {
            objectName: "control"
            x: 300; width: 80; height: 44
            onClicked: window.clicks += 1
        }
    }
}
"""
        ).encode(),
        QUrl(),
    )
    root = component.create()
    assert root is not None, component.errors()
    surface = QQuickWindow()
    surface.resize(400, 48)
    root.setParentItem(surface.contentItem())
    surface.show()
    _APP.processEvents()
    yield surface, root
    surface.close()
    root.setParentItem(None)
    root.deleteLater()
    engine.deleteLater()
    _APP.processEvents()


def send(surface, kind, x=100, button=Qt.LeftButton, y=20):
    buttons = button if kind == QEvent.MouseButtonPress else Qt.NoButton
    event = QMouseEvent(
        kind, QPointF(x, y), QPointF(x, y), button, buttons, Qt.NoModifier
    )
    QGuiApplication.sendEvent(surface, event)


@pytest.mark.parametrize("positions", [(100, 100, 100), (100, 180, 240)])
def test_successful_native_handoff_without_qml_release_allows_every_press(
    header, positions
):
    surface, root = header
    # The OS owns these successful drags and consumes each mouse-up. Sending a
    # QML release here would mask the defect, as earlier geometry tests did.
    for expected, x in enumerate(positions, 1):
        send(surface, QEvent.MouseButtonPress, x)
        assert root.property("moves") == expected


def test_rejected_handoff_retains_normal_release_and_next_attempt(header):
    surface, root = header
    root.setProperty("moveAccepted", False)
    send(surface, QEvent.MouseButtonPress)
    send(surface, QEvent.MouseButtonRelease)
    root.setProperty("moveAccepted", True)
    send(surface, QEvent.MouseButtonPress)
    assert root.property("moves") == 2


def test_control_and_non_left_buttons_do_not_start_window_move(header):
    surface, root = header
    send(surface, QEvent.MouseButtonPress, 330)
    send(surface, QEvent.MouseButtonRelease, 330)
    assert root.property("clicks") == 1
    for button in (Qt.RightButton, Qt.MiddleButton):
        send(surface, QEvent.MouseButtonPress, button=button)
        send(surface, QEvent.MouseButtonRelease, button=button)
    assert root.property("moves") == 0


def held_move(surface, x=120):
    event = QMouseEvent(
        QEvent.MouseMove,
        QPointF(x, 20),
        QPointF(x, 20),
        Qt.NoButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    QGuiApplication.sendEvent(surface, event)


def test_rejected_press_retries_on_held_motion_and_retires_qml_press(header):
    surface, root = header
    root.setProperty("moveAccepted", False)
    send(surface, QEvent.MouseButtonPress)
    assert root.property("moves") == 1
    root.setProperty("moveAccepted", True)
    held_move(surface)
    assert root.property("moves") == 2
    _APP.processEvents()
    assert not root.findChild(type(root), "headerDragArea").property("pressed")
    # The OS may consume release after the retry as well.
    send(surface, QEvent.MouseButtonPress, 160)
    assert root.property("moves") == 3


def test_retry_is_retired_on_release_and_never_starts_from_control(header):
    surface, root = header
    root.setProperty("moveAccepted", False)
    send(surface, QEvent.MouseButtonPress)
    send(surface, QEvent.MouseButtonRelease)
    root.setProperty("moveAccepted", True)
    held_move(surface)
    assert root.property("moves") == 1
    send(surface, QEvent.MouseButtonPress, 330)
    held_move(surface, 340)
    send(surface, QEvent.MouseButtonRelease, 340)
    assert root.property("moves") == 1


def test_blank_spacing_above_divider_is_draggable_but_content_below_is_not(header):
    surface, root = header
    send(surface, QEvent.MouseButtonPress, y=45)
    assert root.property("moves") == 1
    send(surface, QEvent.MouseButtonRelease, y=45)
    send(surface, QEvent.MouseButtonPress, y=47)
    assert root.property("moves") == 1
    send(surface, QEvent.MouseButtonRelease, y=47)
