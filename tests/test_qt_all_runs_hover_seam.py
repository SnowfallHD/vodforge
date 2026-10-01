"""Synthetic offscreen pointer checks; not native macOS acceptance evidence."""

import pytest
from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QMetaObject,
    QObject,
    QPoint,
    QPointF,
    Qt,
)
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from tests.test_qt_scene_port import make_job, qt_app, qt_main, saved, visual_item


@pytest.fixture
def run_scene(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    QQuickStyle.setStyle("Basic")
    bridge = qt_main.Bridge(None)
    bridge._engagement.presented_welcome()
    bridge._runtime.history = [saved(tmp_path, "One", "MP4")]
    bridge._runtime.active_job = make_job(tmp_path)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    window.show()
    app.processEvents()
    QTest.mouseMove(window, QPoint(2, 2))
    QTest.qWait(120)
    button = window.findChild(QObject, "allRunsButton")
    popup = window.findChild(QObject, "allRunsPopup")
    yield app, bridge, window, button, popup
    window.close()
    engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    bridge.close()


def move(window, point):
    QTest.mouseMove(window, QPoint(round(point.x()), round(point.y())))
    QTest.qWait(160)  # Longer than the auto-close timer, including popup padding.


def test_edge_touch_and_held_face_across_padding_and_seam(run_scene):
    _app, _bridge, window, button, popup = run_scene
    face = button.findChild(QObject, "allRunsTriggerFace")
    center = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
    move(window, center)
    assert popup.property("visible")
    assert button.property("held")
    assert "/pressed/" in face.property("source").toString()
    content = popup.property("contentItem")
    bottom = content.mapToScene(
        QPointF(0, content.height() + popup.property("padding"))
    ).y()
    top = button.mapToScene(QPointF(0, 0)).y()
    assert bottom == pytest.approx(top, abs=0.01)
    # Repeated crossings include the frame's 9px padding, excluded previously.
    for dy in (-1, -5, -9, -1, 0, 1, -1, 1):
        move(window, QPointF(center.x(), top + dy))
        assert popup.property("visible")
        assert button.property("held")
        assert "/pressed/" in face.property("source").toString()
    move(window, QPointF(2, 2))
    assert not button.property("hovered")
    for _ in range(20):
        if not popup.property("visible"):
            break
        QTest.qWait(50)
    assert not popup.property("visible")
    assert not button.property("held")
    assert "/normal/" in face.property("source").toString()


def test_click_navigates_without_another_press_face_or_toggle(run_scene):
    app, bridge, window, button, popup = run_scene
    face = button.findChild(QObject, "allRunsTriggerFace")
    point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
    move(window, point)
    before = face.property("source")
    QTest.mousePress(
        window, Qt.LeftButton, Qt.NoModifier, QPoint(round(point.x()), round(point.y()))
    )
    app.processEvents()
    assert face.property("source") == before
    assert popup.property("visible")
    QTest.mouseRelease(
        window, Qt.LeftButton, Qt.NoModifier, QPoint(round(point.x()), round(point.y()))
    )
    app.processEvents()
    assert bridge.selection == "Library"
    assert not popup.property("visible")


@pytest.mark.parametrize("gesture", ["ellipsis", "right_click"])
def test_overflow_actions_keep_owner_and_anchor_alive(run_scene, gesture):
    app, bridge, window, button, popup = run_scene
    center = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
    move(window, center)
    card = visual_item(popup.property("contentItem"), "allRunsCard_0")
    assert card.property("showActions")
    owner = card.property("record")["runId"]
    selection = bridge.selection
    if gesture == "ellipsis":
        action = card.findChild(QObject, "allRunsAction")
        QMetaObject.invokeMethod(action, "activated")
    else:
        point = card.mapToScene(QPointF(card.width() / 2, card.height() / 2))
        QTest.mouseClick(
            window,
            Qt.RightButton,
            Qt.NoModifier,
            QPoint(round(point.x()), round(point.y())),
        )
    app.processEvents()
    actions = window.findChild(QObject, "runActionsPopup")
    assert actions.property("visible")
    assert bridge.selection == selection
    # Moving into the actions must not retire the overflow delegate/anchor.
    content = actions.property("contentItem")
    move(window, content.mapToScene(QPointF(20, 20)))
    assert popup.property("visible")
    assert actions.property("visible")
    assert card.property("record")["runId"] == owner


@pytest.mark.parametrize("side", ["top", "bottom", "tight"])
def test_window_edge_clamping_keeps_edge_contact(run_scene, side):
    app, _bridge, window, _button, popup = run_scene
    # A fixed window-space surface avoids the Forge ColumnLayout rearranging
    # the synthetic anchor as another layout child.
    parent = QQuickItem(window.contentItem())
    parent.setWidth(window.width())
    parent.setHeight(300)
    popup.setProperty("parent", parent)
    anchor = QQuickItem(parent)
    anchor.setWidth(120)
    anchor.setX(parent.width() - 120)
    if side == "top":
        anchor.setY(2)
        anchor.setHeight(24)
    elif side == "bottom":
        anchor.setY(parent.height() - 26)
        anchor.setHeight(24)
    else:
        anchor.setY(20)
        anchor.setHeight(parent.height() - 40)
    popup.setProperty("anchorItem", anchor)
    popup.open()
    assert QMetaObject.invokeMethod(popup, "reposition")
    app.processEvents()
    y, height = popup.property("y"), popup.property("height")
    assert y >= 0
    assert y + height <= parent.height()
    assert y + height == pytest.approx(anchor.y(), abs=0.01) or y == pytest.approx(
        anchor.y() + anchor.height(), abs=0.01
    )
    assert popup.property("x") >= 0
    assert popup.property("x") + popup.property("width") <= parent.width()
    if side == "tight":
        assert height == pytest.approx(20)
    popup.close()
    anchor.deleteLater()
    parent.deleteLater()
