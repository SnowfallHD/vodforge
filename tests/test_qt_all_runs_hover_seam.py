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
from PySide6.QtGui import QCursor
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest

from tests.test_qt_scene_port import (
    make_job,
    qt_app,
    qt_main,
    saved,
    settle_popups,
    visual_item,
)


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
    bridge._settings["whats_new_seen"] = qt_main.SHOWCASE_ID
    bridge._runtime.history = [saved(tmp_path, "One", "MP4")]
    bridge._runtime.active_job = make_job(tmp_path)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    bridge._window = window
    window.show()
    app.processEvents()
    # QTest offscreen events do not own the hardware cursor. Mirror their
    # delivered global coordinates only for the public pointer-query oracle.
    window.setProperty("qaPointerPosition", window.mapToGlobal(QPoint(2, 2)))
    monkeypatch.setattr(QCursor, "pos", lambda: window.property("qaPointerPosition"))
    QTest.mouseMove(window, QPoint(2, 2))
    QTest.qWait(120)
    button = window.findChild(QObject, "allRunsButton")
    popup = window.findChild(QObject, "allRunsPopup")
    yield app, bridge, window, button, popup
    window.close()
    engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    bridge.close()


def wait_visible(popup, visible, timeout_ms=2000):
    """Poll for the popup's state: hover timers fire later on slow runners."""
    waited = 0
    while popup.property("visible") != visible:
        if waited >= timeout_ms:
            raise AssertionError(
                f"popup visible={popup.property('visible')}, expected {visible}"
            )
        QTest.qWait(10)
        waited += 10


def move(window, point):
    window.setProperty("qaPointerPosition", window.mapToGlobal(point.toPoint()))
    QTest.mouseMove(window, QPoint(round(point.x()), round(point.y())))
    QTest.qWait(160)  # Longer than the auto-close timer, including popup padding.


def test_edge_touch_and_held_face_across_padding_and_seam(run_scene):
    _app, _bridge, window, button, popup = run_scene
    face = button.findChild(QObject, "allRunsTriggerFace")
    center = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
    move(window, center)
    wait_visible(popup, True)
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
        wait_visible(popup, True)
        assert button.property("held")
        assert "/pressed/" in face.property("source").toString()
    move(window, QPointF(2, 2))
    assert not button.property("hovered")
    for _ in range(20):
        if not popup.property("visible"):
            break
        QTest.qWait(50)
    settle_popups(window)
    wait_visible(popup, False)
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
    wait_visible(popup, True)
    QTest.mouseRelease(
        window, Qt.LeftButton, Qt.NoModifier, QPoint(round(point.x()), round(point.y()))
    )
    app.processEvents()
    assert bridge.selection == "Library"
    settle_popups(window)
    wait_visible(popup, False)


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
    wait_visible(popup, True)
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


def test_hovering_overflow_ellipsis_keeps_listing_open(run_scene):
    _app, _bridge, window, button, popup = run_scene
    move(window, button.mapToScene(QPointF(button.width() / 2, button.height() / 2)))
    card = visual_item(popup.property("contentItem"), "allRunsCard_0")
    action = card.findChild(QObject, "allRunsAction")
    move(window, action.mapToScene(QPointF(action.width() / 2, action.height() / 2)))
    QTest.qWait(250)
    assert action.property("hovered")
    wait_visible(popup, True)


def test_stale_hover_delivery_after_pointer_left_cannot_open(run_scene, monkeypatch):
    from PySide6.QtGui import QCursor

    _app, _bridge, window, button, popup = run_scene
    # A delayed Qt hover can arrive after native resize/capture moved the real
    # pointer elsewhere. Keep the current global position independently away.
    monkeypatch.setattr(QCursor, "pos", lambda: window.mapToGlobal(QPoint(2, 2)))
    move(window, button.mapToScene(QPointF(button.width() / 2, button.height() / 2)))
    assert button.findChild(QObject, "allRunsPointerArea").property("containsMouse")
    assert not button.property("hovered")
    settle_popups(window)
    wait_visible(popup, False)


@pytest.mark.parametrize("size", [(820, 560), (1400, 900)])
def test_primed_hover_is_retired_on_resize_with_pointer_at_corner(
    run_scene, monkeypatch, size
):
    from PySide6.QtGui import QCursor

    _app, _bridge, window, button, popup = run_scene
    move(window, button.mapToScene(QPointF(button.width() / 2, button.height() / 2)))
    wait_visible(popup, True)
    # No Qt move delivery: native resize capture can keep containsMouse stale.
    monkeypatch.setattr(
        QCursor,
        "pos",
        lambda: window.mapToGlobal(QPoint(window.width() - 2, window.height() - 2)),
    )
    for width, height in (size, (1100, 740), size):
        window.resize(width, height)
        QTest.qWait(150)
        settle_popups(window)
        wait_visible(popup, False)
    popup.close()
    window.resize(1100, 740)
    QTest.qWait(150)
    settle_popups(window)
    wait_visible(popup, False)


@pytest.mark.parametrize("primed", [False, True])
def test_held_corner_cross_requires_release_and_new_motion(run_scene, primed):
    _app, bridge, window, button, popup = run_scene
    center = lambda: button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
    if primed:
        move(window, center())
        wait_visible(popup, True)
    corner = QPoint(window.width() - 2, window.height() - 2)
    move(window, QPointF(corner))
    settle_popups(window)
    wait_visible(popup, False)
    QTest.mousePress(window, Qt.LeftButton, pos=corner)
    assert bridge.isPointerPressed()
    move(window, center())
    settle_popups(window)
    wait_visible(popup, False)
    QTest.mouseRelease(window, Qt.LeftButton, pos=center().toPoint())
    QTest.qWait(120)
    settle_popups(window)
    wait_visible(popup, False)
    move(window, center() + QPointF(1, 0))
    wait_visible(popup, True)
    popup.close()
    for size in ((1400, 900), (820, 560), (1100, 740), (820, 560)):
        window.resize(*size)
        QTest.qWait(130)
        settle_popups(window)
        wait_visible(popup, False)
    move(window, center())
    wait_visible(popup, True)


@pytest.mark.parametrize("dismiss", ["resize", "keyboard"])
def test_pending_motion_cannot_reopen_after_geometry_or_dismiss(run_scene, dismiss):
    _app, _bridge, window, button, popup = run_scene
    point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
    move(window, point)
    wait_visible(popup, True)
    # Queue another legitimate move, then invalidate it before the deferred
    # admission callback. Neither resize nor Escape may resurrect that motion.
    point += QPointF(1, 0)
    window.setProperty("qaPointerPosition", window.mapToGlobal(point.toPoint()))
    QTest.mouseMove(window, point.toPoint())
    if dismiss == "resize":
        window.resize(1400, 900)
    else:
        QTest.keyClick(window, Qt.Key_Escape)
    QTest.qWait(160)
    settle_popups(window)
    wait_visible(popup, False)


def test_public_pointer_query_checks_live_rect_visibility_and_stale_item(run_scene):
    _app, bridge, window, button, _popup = run_scene
    point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
    window.setProperty("qaPointerPosition", window.mapToGlobal(point.toPoint()))
    assert bridge.isPointerOverItem(button)
    window.setProperty("qaPointerPosition", window.mapToGlobal(QPoint(2, 2)))
    assert not bridge.isPointerOverItem(button)
    window.setProperty("qaPointerPosition", window.mapToGlobal(point.toPoint()))
    button.setEnabled(False)
    assert not bridge.isPointerOverItem(button)
    button.setEnabled(True)
    item = QQuickItem(window.contentItem())
    item.setWidth(10)
    item.setHeight(10)
    item.setVisible(False)
    assert not bridge.isPointerOverItem(item)
    item.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert not bridge.isPointerOverItem(item)
