"""Rendered Watch scrolling against disposable empty/populated projections."""

import pytest
from PySide6.QtCore import QObject, QPoint, QPointF, Qt
from PySide6.QtGui import QGuiApplication, QInputDevice, QPointingDevice, QWheelEvent
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch, _visual_descendants
from tests.test_qt_scene_port import saved


def gesture(window, point, *, dx=0, dy=-100, touchpad=False, phase=Qt.ScrollUpdate):
    device = (
        QPointingDevice(
            "Watch fixture trackpad",
            73,
            QInputDevice.DeviceType.TouchPad,
            QPointingDevice.PointerType.Finger,
            QInputDevice.Capability.Position,
            1,
            0,
        )
        if touchpad
        else QPointingDevice.primaryPointingDevice()
    )
    event = QWheelEvent(
        point,
        point,
        QPoint(dx, dy) if touchpad else QPoint(),
        QPoint() if touchpad else QPoint(dx * 120 // 80, dy * 120 // 80),
        Qt.NoButton,
        Qt.NoModifier,
        phase,
        False,
        Qt.MouseEventNotSynthesized,
        device,
    )
    QGuiApplication.sendEvent(window, event)
    QTest.qWait(25)


def populated(tmp_path):
    rows = []
    for index in range(18):
        row = saved(tmp_path, f"Fixture {index}", "MP4")
        row.update(
            channel=f"Channel {index}",
            playlist_id=f"playlist-{index}",
            playlist_title=f"Playlist {index}",
        )
        rows.append(row)
    return rows


@pytest.mark.parametrize("size", [(1280, 900), (900, 560)])
@pytest.mark.parametrize("has_media", [False, True])
@pytest.mark.parametrize("touchpad", [False, True])
def test_watch_scroll_reaches_channels_with_mouse_or_trackpad(
    tmp_path, monkeypatch, size, has_media, touchpad
):
    _app, bridge, engine, window = _launch(
        tmp_path, monkeypatch, populated(tmp_path) if has_media else []
    )
    try:
        window.resize(*size)
        bridge.select("Watch")
        QTest.qWait(150)
        viewport = window.findChild(QObject, "watchViewport")
        page = viewport.property("contentItem")
        if has_media:
            bottom = next(
                item
                for item in _visual_descendants(window.contentItem())
                if item.objectName() == "watchHomeRail_channels"
            )
        else:
            bottom = next(
                item
                for item in _visual_descendants(window.contentItem())
                if item.objectName() == "watchPlaceholderCard"
                and item.property("sectionTitle") == "Channels"
                and item.isVisible()
            )
        assert page.property("contentHeight") > viewport.height(), (
            page.property("contentHeight"),
            viewport.height(),
            bottom.mapToItem(viewport, 0, 0).y(),
            bottom.height(),
        )
        point = viewport.mapToScene(QPointF(100, min(200, viewport.height() / 2)))
        previous = page.property("contentY")
        gesture(window, point, touchpad=touchpad, phase=Qt.ScrollUpdate)
        assert page.property("contentY") == pytest.approx(
            min(previous + 100, page.property("contentHeight") - viewport.height())
        )
        for _ in range(20):
            gesture(
                window,
                point,
                touchpad=touchpad,
                phase=Qt.ScrollMomentum if touchpad else Qt.ScrollUpdate,
            )
        top = bottom.mapToItem(viewport, 0, 0).y()
        assert top >= -1 and top + bottom.height() <= viewport.height() + 1, (
            top,
            bottom.height(),
            viewport.height(),
            page.property("contentHeight"),
            page.property("contentY"),
        )
        before = page.property("contentY")
        gesture(window, point, dy=80, touchpad=touchpad, phase=Qt.ScrollUpdate)
        assert page.property("contentY") < before
    finally:
        _close(bridge, engine, window)


@pytest.mark.parametrize("size", [(1280, 900), (900, 560)])
def test_watch_rail_vertical_gesture_preserves_horizontal_scroll(
    tmp_path, monkeypatch, size
):
    _app, bridge, engine, window = _launch(tmp_path, monkeypatch, populated(tmp_path))
    try:
        window.resize(*size)
        bridge.select("Watch")
        QTest.qWait(150)
        viewport = window.findChild(QObject, "watchViewport")
        page = viewport.property("contentItem")
        rail = next(
            item
            for item in _visual_descendants(window.contentItem())
            if item.objectName() == "watchHomeRail_playlists"
        )
        page.setProperty("contentY", max(0, rail.mapToItem(page, 0, 0).y() - 60))
        QTest.qWait(50)
        point = rail.mapToScene(QPointF(100, 60))
        horizontal = rail.property("contentItem")
        before = horizontal.property("contentX")
        gesture(window, point, dx=-100, dy=0, touchpad=True, phase=Qt.ScrollBegin)
        assert horizontal.property("contentX") == pytest.approx(before + 100)
        before = page.property("contentY")
        x = horizontal.property("contentX")
        gesture(window, point, dx=-12, dy=-80, touchpad=True)
        assert page.property("contentY") == pytest.approx(
            min(before + 80, page.property("contentHeight") - viewport.height()),
            abs=0.5,
        )
        assert horizontal.property("contentX") == pytest.approx(x)
    finally:
        _close(bridge, engine, window)
