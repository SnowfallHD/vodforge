"""Scroll and presentation lifecycle regressions across shared Qt owners."""

import pytest
from PySide6.QtCore import QObject, QPoint, QPointF, Qt
from PySide6.QtGui import QGuiApplication, QWheelEvent
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch
from tests.test_qt_scene_port import saved, visual_item


@pytest.mark.parametrize("held_press", [False, True])
def test_watch_popup_reopens_on_first_click_after_scrolling(
    tmp_path, monkeypatch, held_press
):
    records = [saved(tmp_path, f"Video {i}", "MP4") for i in range(20)]
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, records)
    try:
        window.resize(1400, 740)
        bridge.select("Watch")
        QTest.qWait(150)
        popup = window.findChild(QObject, "watchHeroMorePopup")
        viewport = window.findChild(QObject, "watchViewport")
        page = viewport.property("contentItem")
        trigger = visual_item(window.contentItem(), "watchHeroMoreButton")

        def click():
            point = trigger.mapToItem(
                window.contentItem(), trigger.width() / 2, trigger.height() / 2
            )
            QTest.mouseClick(
                window,
                Qt.MouseButton.LeftButton,
                pos=QPoint(round(point.x()), round(point.y())),
            )
            QTest.qWait(30)

        for _ in range(4):
            click()
            assert popup.property("visible"), (
                popup.property("dismissedByTriggerPress"),
                page.property("contentY"),
            )
            if held_press:
                point = trigger.mapToItem(
                    window.contentItem(), trigger.width() / 2, trigger.height() / 2
                )
                QTest.mousePress(
                    window,
                    Qt.MouseButton.LeftButton,
                    pos=QPoint(round(point.x()), round(point.y())),
                )
            page.setProperty(
                "contentY", page.property("contentHeight") - viewport.height()
            )
            QTest.qWait(150)
            assert not popup.property("visible")
            if held_press:
                QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=QPoint(2, 2))
                app.processEvents()
            page.setProperty("contentY", 0)
            QTest.qWait(150)
            click()
            assert popup.property("visible"), popup.property("dismissedByTriggerPress")
            click()
            assert not popup.property("visible")
    finally:
        _close(bridge, engine, window)


def test_watch_projection_refresh_preserves_scroll_geometry(tmp_path, monkeypatch):
    records = [saved(tmp_path, f"Video {i}", "MP4") for i in range(20)]
    _app, bridge, engine, window = _launch(tmp_path, monkeypatch, records)
    try:
        window.resize(1400, 600)
        bridge.select("Watch")
        QTest.qWait(150)
        viewport = window.findChild(QObject, "watchViewport")
        page = viewport.property("contentItem")
        page.setProperty(
            "contentY", min(500, page.property("contentHeight") - viewport.height())
        )
        QTest.qWait(100)
        before = page.property("contentY")
        changes = []
        page.contentYChanged.connect(lambda: changes.append(page.property("contentY")))
        for _ in range(3):
            bridge.historyChanged.emit()
            QTest.qWait(40)
        assert all(abs(y - before) < 1 for y in changes), (before, changes)
    finally:
        _close(bridge, engine, window)


@pytest.mark.parametrize("route", ["home", "channels", "videos"])
def test_watch_vertical_gesture_remains_monotonic_across_rails_and_rows(
    tmp_path, monkeypatch, route
):
    records = []
    for i in range(100):
        row = saved(tmp_path, f"Video {i}", "MP4")
        row["channel"] = f"Channel {i}"
        row["playlist_id"] = f"playlist-{i}"
        row["playlist_title"] = f"Playlist {i}"
        records.append(row)
    _app, bridge, engine, window = _launch(tmp_path, monkeypatch, records)
    try:
        window.resize(1400, 600)
        bridge.select("Watch")
        bridge.navigateWatch(route)
        QTest.qWait(200)
        viewport = window.findChild(QObject, "watchViewport")
        page = viewport.property("contentItem")
        point = viewport.mapToScene(QPointF(120, viewport.height() / 2))
        changes = []
        page.contentYChanged.connect(lambda: changes.append(page.property("contentY")))
        for direction in [-1, 1]:
            previous = page.property("contentY")
            for tick in range(100):
                wheel = QWheelEvent(
                    point,
                    point,
                    QPoint(0, 23 * direction),
                    QPoint(),
                    Qt.NoButton,
                    Qt.NoModifier,
                    Qt.ScrollUpdate,
                    False,
                )
                changes.clear()
                QGuiApplication.sendEvent(window, wheel)
                QTest.qWait(10)
                for value in changes:
                    assert (value - previous) * direction <= 1, (
                        route,
                        tick,
                        previous,
                        value,
                        changes,
                    )
                    previous = value
                current = page.property("contentY")
                assert (current - previous) * direction <= 1, (
                    route,
                    tick,
                    previous,
                    current,
                )
                previous = current
    finally:
        _close(bridge, engine, window)
