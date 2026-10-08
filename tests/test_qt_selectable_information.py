"""Read-only selection/copy and local input ownership in informational surfaces."""

from itertools import count

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QKeySequence, QWheelEvent
from PySide6.QtQml import QQmlComponent
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch
from tests.test_qt_library_details_copy import detail  # noqa: F401
from tests.test_qt_scene_port import saved, visual_item
from yt_downloader.qt_quick import main

_WHEEL_TIMESTAMPS = count(1)


@pytest.fixture
def information(tmp_path, monkeypatch):
    app, bridge, engine, window = _launch(
        tmp_path, monkeypatch, [saved(tmp_path, "Fixture", "MP4")]
    )
    bridge.select("Library")
    component = QQmlComponent(engine)
    component.setData(
        b"""import QtQuick
import QtQuick.Controls
import "."
Rectangle {
    width: 420; height: 300; color: theme.bg
    visible: bridge.selection === "Library"
    property int buttonActivations: 0
    ScrollView {
        id: outer; objectName: "selectionOuter"; width: 400; height: 240
        contentHeight: 1000
        VerticalScrollChain { nestedScrollView: outer }
        Column {
            width: outer.availableWidth
            ScrollView {
                id: inner; objectName: "selectionInner"; width: 380; height: 120
                VerticalScrollChain { nestedScrollView: inner }
                SelectableText {
                    objectName: "selectionInformation"; width: inner.availableWidth
                    font.pixelSize: 16
                    text: "Meaningful fixture title and a path /fictional/output.mp4.\\n".repeat(35)
                }
            }
            StoneButton {
                objectName: "selectionSiblingButton"; label: "Details"; width: 100; height: 40
                onActivated: buttonActivations += 1
            }
            Item { width: 1; height: 840 }
        }
    }
}""",
        QUrl.fromLocalFile(
            str(main.SOURCE / "yt_downloader/qt_quick/selection-probe.qml")
        ),
    )
    holder = component.create()
    assert holder is not None, component.errors()
    holder.setParentItem(window.contentItem())
    holder.setPosition(QPointF(40, 110))
    holder.setZ(1000)
    QTest.qWait(100)
    text = holder.findChild(QQuickItem, "selectionInformation")
    yield app, bridge, window, holder, text
    holder.deleteLater()
    _close(bridge, engine, window)
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def position(item, x, y):
    point = item.mapToScene(QPointF(x, y))
    return QPoint(round(point.x()), round(point.y()))


def test_drag_selection_and_standard_copy_do_not_edit_or_navigate(information):
    app, bridge, window, holder, text = information
    original = text.property("text")
    app.clipboard().setText("sentinel")
    QTest.mousePress(window, Qt.LeftButton, pos=position(text, 3, 9))
    QTest.mouseMove(window, position(text, 180, 9))
    QTest.mouseRelease(window, Qt.LeftButton, pos=position(text, 180, 9))
    QTest.qWait(50)
    selection = text.property("selectedText")
    assert selection and selection != original
    assert text.hasActiveFocus()
    assert window.property("editingText")
    QTest.keySequence(window, QKeySequence(QKeySequence.StandardKey.Copy))
    assert app.clipboard().text() == selection
    QTest.keyClick(window, Qt.Key_X)
    assert text.property("text") == original
    assert text.property("readOnly")
    assert bridge.selection == "Library"
    assert holder.property("buttonActivations") == 0


def test_sibling_button_still_receives_first_pointer_activation(information):
    _app, _bridge, window, holder, text = information
    text.forceActiveFocus()
    text.selectAll()
    button = holder.findChild(QQuickItem, "selectionSiblingButton")
    QTest.mouseClick(window, Qt.LeftButton, pos=position(button, 40, 20))
    assert holder.property("buttonActivations") == 1


def test_selected_text_preserves_pointer_owned_scroll(information):
    app, _bridge, window, holder, text = information
    text.forceActiveFocus()
    text.selectAll()
    inner_view = holder.findChild(QObject, "selectionInner")
    inner = inner_view.property("contentItem")
    outer = holder.findChild(QObject, "selectionOuter").property("contentItem")
    inner.setProperty("contentY", inner.property("contentHeight") - inner.height())
    point = inner_view.mapToScene(QPointF(40, 40))
    before = outer.property("contentY")
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
    assert outer.property("contentY") == before
    assert text.property("selectedText") == text.property("text")
    point = holder.mapToScene(QPointF(390, 200))
    outside = QWheelEvent(
        point,
        point,
        QPoint(0, -80),
        QPoint(),
        Qt.NoButton,
        Qt.NoModifier,
        Qt.ScrollUpdate,
        False,
    )
    outside.setTimestamp(next(_WHEEL_TIMESTAMPS))
    QGuiApplication.sendEvent(window, outside)
    app.processEvents()
    assert outer.property("contentY") - before == pytest.approx(80)


def test_route_hides_information_and_retires_its_keyboard_focus(information):
    _app, bridge, window, _holder, text = information
    text.forceActiveFocus()
    text.selectAll()
    bridge.select("Watch")
    QTest.qWait(100)
    assert not text.isVisible()
    assert not text.hasActiveFocus()
    assert not window.property("editingText")


def test_real_library_fact_and_description_use_read_only_selection(detail):  # noqa: F811
    app, bridge, _owner, _engine, window = detail
    before = [dict(row) for row in bridge._runtime.history]
    value = visual_item(window.contentItem(), "libraryFactValue_output_Saved Location")
    assert value.property("selectionEnabled")
    assert value.property("readOnly")
    value.forceActiveFocus()
    value.selectAll()
    QTest.keySequence(window, QKeySequence(QKeySequence.StandardKey.Copy))
    assert app.clipboard().text() == value.property("text")
    assert bridge._runtime.history == before
    description = window.findChild(QObject, "libraryDescriptionText")
    assert description.property("readOnly")
    assert description.property("selectByMouse")
    source = visual_item(window.contentItem(), "libraryFactValue_source_Source URL")
    assert not source.property("selectionEnabled")
    assert not source.property("selectByMouse")


def test_real_library_description_routes_by_current_overflow(detail):  # noqa: F811
    app, bridge, owner, _engine, window = detail
    window.resize(1400, 500)
    bridge._settings["social_invitation_dismissed"] = True
    scroll = window.findChild(QQuickItem, "libraryDescriptionScroll")
    inner = scroll.property("contentItem")
    outer = inner.parentItem()
    while outer is not None and not isinstance(
        outer.property("contentY"), (int, float)
    ):
        outer = outer.parentItem()
    assert outer is not None

    def bring_into_view():
        for _ in range(3):
            app.processEvents()
        center = scroll.mapToScene(QPointF(40, scroll.height() / 2))
        maximum = max(0, outer.property("contentHeight") - outer.height())
        outer.setProperty(
            "contentY",
            max(
                0,
                min(
                    maximum,
                    outer.property("contentY") + center.y() - window.height() / 2,
                ),
            ),
        )
        app.processEvents()
        point = scroll.mapToScene(QPointF(40, scroll.height() / 2))
        assert 0 < point.y() < window.height()
        return point

    def send(point, delta):
        event = QWheelEvent(
            point,
            point,
            QPoint(0, delta),
            QPoint(),
            Qt.NoButton,
            Qt.NoModifier,
            Qt.ScrollUpdate,
            False,
        )
        event.setTimestamp(next(_WHEEL_TIMESTAMPS))
        QGuiApplication.sendEvent(window, event)
        app.processEvents()

    assert bridge.saveLibraryDescription(owner, "Description line.\n" * 100)
    point = bring_into_view()
    assert inner.property("contentHeight") > inner.height()
    inner.setProperty("contentY", inner.property("contentHeight") - inner.height())
    before = outer.property("contentY")
    send(point, -80)
    assert outer.property("contentY") == before

    assert bridge.saveLibraryDescription(owner, "Short description")
    point = bring_into_view()
    assert inner.property("contentHeight") <= inner.height()
    # Upwards has room after bringing the lower description into view.
    before = outer.property("contentY")
    assert before > 0
    send(point, 40)
    assert outer.property("contentY") == pytest.approx(max(0, before - 40))
