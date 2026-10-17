"""Frameless Windows edges must own resize input without stealing client controls.

Rendered dispatch exercises the real shared QML owner on every CI host. The
injected window records the platform admission request; actual OS pointer/resize
behavior is separately qualified against the private Windows package.
"""

from pathlib import Path

import pytest
from PySide6.QtCore import (
    Property,
    QCoreApplication,
    QEvent,
    QObject,
    QPoint,
    Qt,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from tests.test_qt_scene_port import qt_app
from yt_downloader.product_theme import THEME
from yt_downloader.qt_quick import main as qt_main


class Owner(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.state = 2  # Window.Windowed
        self.shown = True
        self.min_width, self.max_width = 100, 2000
        self.min_height, self.max_height = 100, 2000
        self.requests = []
        self.moves = 0
        self.accept = True

    visibility = Property(
        int, lambda s: s.state, lambda s, v: setattr(s, "state", v), notify=changed
    )
    visible = Property(bool, lambda s: s.shown, notify=changed)
    title = Property(str, lambda s: "Fictional resize fixture", constant=True)
    minimumWidth = Property(int, lambda s: s.min_width, notify=changed)
    maximumWidth = Property(int, lambda s: s.max_width, notify=changed)
    minimumHeight = Property(int, lambda s: s.min_height, notify=changed)
    maximumHeight = Property(int, lambda s: s.max_height, notify=changed)

    @Slot(int, result=bool)
    def startSystemResize(self, edges):
        self.requests.append(edges)
        return self.accept

    @Slot(result=bool)
    def startSystemMove(self):
        self.moves += 1
        return True


@pytest.fixture
def frame_scene(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = qt_app()
    engine = QQmlEngine()
    for key, value in {
        "theme": dict(THEME),
        "buttonFontFamily": "Sans Serif",
        "bridge": {"themeRevision": 0},
        "buttonMetrics": {
            name: {
                "height": x.height,
                "fontPixels": x.font_pixels,
                "horizontalPadding": x.horizontal_padding,
                "iconPixels": x.icon_pixels,
            }
            for name, x in qt_main.BUTTON_METRICS.items()
        },
    }.items():
        engine.rootContext().setContextProperty(key, value)
    engine.addImageProvider("vodforge", qt_main.Materials())
    path = Path(qt_main.__file__).with_name("WindowsFrame.qml")
    component = QQmlComponent(engine)
    component.setData(
        path.read_bytes().replace(b'Qt.platform.os === "windows"', b"true"),
        QUrl.fromLocalFile(str(path)),
    )
    window = QQuickWindow()
    window.resize(500, 300)
    owner = Owner()
    frame = component.createWithInitialProperties({"appWindow": owner})
    assert frame is not None, component.errors()
    frame.setParentItem(window.contentItem())
    window.show()
    app.processEvents()
    try:
        yield app, window, frame, owner
    finally:
        window.close()
        frame.setParentItem(None)
        frame.deleteLater()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()


ZONES = [
    ("topLeft", (2, 2), Qt.TopEdge | Qt.LeftEdge, Qt.SizeFDiagCursor),
    ("top", (250, 2), Qt.TopEdge, Qt.SizeVerCursor),
    ("topRight", (498, 2), Qt.TopEdge | Qt.RightEdge, Qt.SizeBDiagCursor),
    ("left", (2, 150), Qt.LeftEdge, Qt.SizeHorCursor),
    ("right", (498, 150), Qt.RightEdge, Qt.SizeHorCursor),
    ("bottomLeft", (2, 298), Qt.BottomEdge | Qt.LeftEdge, Qt.SizeBDiagCursor),
    ("bottom", (250, 298), Qt.BottomEdge, Qt.SizeVerCursor),
    ("bottomRight", (498, 298), Qt.BottomEdge | Qt.RightEdge, Qt.SizeFDiagCursor),
]


@pytest.mark.parametrize("name,position,edges,cursor", ZONES)
def test_real_edge_press_admits_exact_system_resize(
    frame_scene, name, position, edges, cursor
):
    app, window, frame, owner = frame_scene

    def find(item):
        if item.objectName() == "windowResize" + name:
            return item
        return next(
            (
                found
                for child in item.childItems()
                if (found := find(child)) is not None
            ),
            None,
        )

    area = find(frame)
    assert area is not None and area.isVisible()
    assert area.property("cursorShape") == cursor
    QTest.mouseMove(window, QPoint(*position))
    QTest.mousePress(window, Qt.LeftButton, pos=QPoint(*position))
    QTest.mouseRelease(window, Qt.LeftButton, pos=QPoint(*position))
    app.processEvents()
    assert owner.requests == [edges.value]
    assert owner.moves == 0


@pytest.mark.parametrize(
    "state,shown,enabled,fixed",
    [
        (4, True, True, False),
        (5, True, True, False),
        (3, True, True, False),
        (2, False, True, False),
        (2, True, False, False),
        (2, True, True, True),
    ],
)
def test_ineligible_owner_has_no_resize_input(
    frame_scene, state, shown, enabled, fixed
):
    app, window, frame, owner = frame_scene
    owner.state, owner.shown = state, shown
    if fixed:
        owner.max_width, owner.max_height = owner.min_width, owner.min_height
    # Notify the same owner so live window-state changes retire edge input.
    owner.changed.emit()
    frame.setEnabled(enabled)
    app.processEvents()
    for _, position, _, _ in ZONES:
        QTest.mouseClick(window, Qt.LeftButton, pos=QPoint(*position))
    assert owner.requests == []


def test_client_outside_right_button_and_rejected_admission_do_not_resize(frame_scene):
    _app, window, _frame, owner = frame_scene
    for point in [QPoint(250, 150), QPoint(-1, 150), QPoint(501, 150)]:
        QTest.mouseClick(window, Qt.LeftButton, pos=point)
    QTest.mouseClick(window, Qt.RightButton, pos=QPoint(2, 150))
    assert owner.requests == []
    owner.accept = False
    QTest.mouseClick(window, Qt.LeftButton, pos=QPoint(250, 2))
    assert owner.requests == [Qt.TopEdge.value]
    assert owner.moves == 0


def test_title_bar_reveals_the_same_window_backdrop(frame_scene):
    from PySide6.QtGui import QColor

    _app, window, _frame, _owner = frame_scene
    window.setColor(QColor("#ca17bd"))
    window.update()
    QTest.qWait(80)
    image = window.grabWindow()
    assert not image.isNull()
    # Clear of text and caption buttons: this row must retain the window's
    # underlying artwork instead of painting a separate opaque title-bar band.
    assert image.pixelColor(250, 16).name() == "#ca17bd"


@pytest.mark.parametrize(
    "fixed_axis,allowed,blocked",
    [
        ("width", ("bottom", (250, 298), Qt.BottomEdge.value), (2, 150)),
        ("height", ("right", (498, 150), Qt.RightEdge.value), (250, 298)),
    ],
)
def test_one_fixed_axis_keeps_other_axis_resize(
    frame_scene, fixed_axis, allowed, blocked
):
    app, window, _frame, owner = frame_scene
    if fixed_axis == "width":
        owner.max_width = owner.min_width
    else:
        owner.max_height = owner.min_height
    owner.changed.emit()
    app.processEvents()
    QTest.mouseClick(window, Qt.LeftButton, pos=QPoint(*blocked))
    assert owner.requests == []
    _, point, edge = allowed
    QTest.mouseClick(window, Qt.LeftButton, pos=QPoint(*point))
    assert owner.requests == [edge]
