"""Actual shared QML header geometry and exact public-native measurement guards."""

import math

import pytest
from PySide6.QtCore import QObject, QPointF, Qt
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from shiboken6 import getCppPointer

from tests.test_qt_interaction_invariants import _close, _launch
from tests.test_qt_scene_port import polish_scene, visual_item
from yt_downloader.qt_quick.mac_header import measured_layout


def geometry():
    values = [math.nan] * 66
    values[10:12] = [980, 44]
    values[27:31] = [-1420, 850, 980, 44]
    values[62:66] = [-1510, 100, 1100, 800]
    values[61] = 0
    for start, x in ((31, -1500), (41, -1480), (51, -1460)):
        values[start : start + 2] = [1, 1]
        values[start + 6 : start + 10] = [x, 865, 12, 12]
    return tuple(values)


def test_public_header_measurement_uses_own_content_and_real_button_extent():
    values = geometry()
    shown = measured_layout(1 | 2 | 16 | 32, values)
    assert shown["relative_x"] == shown["reserve"] == 90
    assert shown["relative_y"] == 6
    assert shown["leading"] == 0  # Host is already to the right of real controls.
    assert shown["revealed"]
    overlap = list(values)
    overlap[27] = -1490
    assert measured_layout(1 | 2 | 32, tuple(overlap))["leading"] == 42
    assert measured_layout(1 | 2 | 16 | 128, tuple(overlap))["leading"] == 0
    assert measured_layout(1 | 2 | 16, values)["revealed"] is None
    assert measured_layout(1 | 16, values)["relative_y"] is None
    for bad in ((), values[:62]):
        with pytest.raises(RuntimeError):
            measured_layout(1, bad)
    with pytest.raises(RuntimeError):
        measured_layout(0, values)
    invalid = list(values)
    invalid[10] = math.nan
    with pytest.raises(RuntimeError):
        measured_layout(1, tuple(invalid))


@pytest.mark.parametrize("size", [(820, 560), (1100, 740), (1440, 900)])
@pytest.mark.parametrize("style", ["shadow", "concave"])
def test_actual_header_overlay_preserves_body_and_scroll_in_every_route(
    tmp_path, monkeypatch, size, style
):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        window.resize(*size)
        window.setProperty("nativeHeaderStyle", style)
        window.setProperty("nativeHeaderAttached", True)
        window.setProperty("nativeHeaderWidth", size[0] - 2 * window.property("gutter"))
        window.setProperty("nativeHeaderReserve", 82)
        header = window.findChild(QObject, "focusHeader")
        body = window.findChild(QObject, "headerGeometrySlot").parentItem()

        def settle():
            for _ in range(4):
                app.processEvents()
                polish_scene(window.contentItem())

        def snapshot():
            result = {}
            for item in [body, *body.findChildren(QObject)]:
                if hasattr(item, "mapToScene"):
                    pt = item.mapToScene(QPointF(0, 0))
                    result[getCppPointer(item)[0]] = (
                        pt.x(),
                        pt.y(),
                        item.width(),
                        item.height(),
                    )
                if item.metaObject().indexOfProperty("contentY") >= 0:
                    result[("scroll", getCppPointer(item)[0])] = item.property(
                        "contentY"
                    )
            return result

        for route in ("Forge", "Library", "Watch", "Activity"):
            bridge.selectHome(route)
            settle()
            before = snapshot()
            for revealed, inset in ((True, 91), (False, 0)):
                window.setProperty("nativeHeaderRevealed", revealed)
                window.setProperty("nativeHeaderLeadingInset", inset)
                QTest.qWait(160)
                settle()
                assert snapshot() == before
            assert header.parentItem() is window.contentItem()
            # These are real production QML properties, not a generated mock.
            assert header.property("nativeHeaderInset") == pytest.approx(0, abs=0.1)
    finally:
        _close(bridge, engine, window)


def test_same_actual_header_moves_to_second_qt_surface_and_routes_real_clicks(
    tmp_path, monkeypatch
):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    header = window.findChild(QObject, "focusHeader")
    parent = header.parentItem()
    other = QQuickWindow()
    other.resize(1000, 100)
    other.show()
    try:
        header.setParentItem(other.contentItem())
        window.setProperty("nativeHeaderSurface", other)
        window.setProperty("nativeHeaderWidth", 1000)
        window.setProperty("nativeHeaderAttached", True)
        for _ in range(5):
            app.processEvents()
            polish_scene(header)
        assert header.window() is other
        assert window.findChildren(QObject, "focusHeader") == [header]
        button = visual_item(header, "navigationButton_Library")
        point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
        QTest.mouseClick(other, Qt.LeftButton, Qt.NoModifier, point.toPoint())
        app.processEvents()
        assert bridge.selection == "Library"
        button = visual_item(header, "headerSettingsButton")
        point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
        QTest.mouseClick(other, Qt.LeftButton, Qt.NoModifier, point.toPoint())
        app.processEvents()
        popup = window.findChild(QObject, "downloadSettingsPopup")
        assert popup.property("visible")
        assert window.property("nativeHeaderSurface") is other
    finally:
        header.setParentItem(parent)
        window.setProperty("nativeHeaderAttached", False)
        window.setProperty("nativeHeaderSurface", None)
        other.close()
        other.deleteLater()
        _close(bridge, engine, window)


@pytest.mark.parametrize("pending_attachment", [False, True])
@pytest.mark.parametrize("height_refused", [False, True])
def test_event_driven_owner_reparents_once_and_retires_notifier_before_fd_close(
    tmp_path, monkeypatch, pending_attachment, height_refused
):
    import os

    from PySide6.QtGui import QWindow

    from yt_downloader.qt_quick import mac_header

    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    events = []
    read_fd, write_fd = os.pipe()
    os.set_blocking(read_fd, False)
    state = {
        "flags": 1 | 2 | 32,
        "geometry": geometry(),
        "current": 1,
        "refuse_height": False,
        "refuse_close": False,
    }
    if pending_attachment:
        state["flags"] = 1
    foreign = QWindow()
    owner = None

    class Host:
        view = 1234
        descriptor = read_fd

        def __init__(self, pointer, height, gutter, minimum):
            assert pointer == 61 and height > 0 and gutter >= 0 and minimum > 0
            events.append("create")

        def drain(self):
            try:
                return len(os.read(read_fd, 64))
            except BlockingIOError:
                return 0

        def snapshot(self):
            return state["current"], state["flags"], state["geometry"]

        def set_height(self, height):
            assert height > 0
            if state["refuse_height"]:
                raise RuntimeError("Foreign native owner replaced header")

        def close(self):
            assert owner is None or not owner._notifier.isEnabled()
            if state["refuse_close"]:
                state["refuse_close"] = False
                events.append("close_refused")
                raise RuntimeError("Native child teardown pending")
            events.append("close")
            os.close(read_fd)
            os.close(write_fd)

    monkeypatch.setattr(mac_header, "HeaderHost", Host)
    monkeypatch.setattr(
        QWindow, "fromWinId", lambda pointer: foreign if pointer == 1234 else None
    )
    header = window.findChild(QObject, "focusHeader")
    original_parent = header.parentItem()
    try:
        owner = mac_header.IntegratedHeader(window, 61)
        if pending_attachment:
            assert header.parentItem() is original_parent
            assert not window.property("nativeHeaderAttached")
            assert window._native_header_diagnostic["stage"] == "native_header_pending"
            state["flags"] = 1 | 2 | 32
            os.write(write_fd, b"1")
            for _ in range(5):
                app.processEvents()
        assert header.window() is owner._surface
        assert window.property("nativeHeaderAttached")
        assert window.property("nativeHeaderReserve") == 90
        state["flags"] = 1 | 2 | 16 | 128
        os.write(write_fd, b"1")
        for _ in range(5):
            app.processEvents()
        assert window.property("nativeHeaderLeadingInset") == 0
        assert not window.property("nativeHeaderRevealed")
        assert window.property("nativeHeaderReserve") == 90
        # Unknown controls preserve the preceding measured state, not a guess.
        state["flags"] = 1 | 2 | 16
        window.setProperty("nativeHeaderLeadingInset", 35)
        os.write(write_fd, b"1")
        for _ in range(5):
            app.processEvents()
        assert window.property("nativeHeaderLeadingInset") == 35
        if height_refused:
            state["refuse_height"] = True
            with pytest.raises(RuntimeError, match="Foreign native owner"):
                owner.update_height()
            assert (
                window._native_header_diagnostic["stage"]
                == "native_header_height_refused"
            )
        if not pending_attachment and not height_refused:
            state["refuse_close"] = True
            with pytest.raises(RuntimeError, match="Native child teardown pending"):
                owner.close()
            assert owner.retired and not owner.closed
            owner.synchronize()  # No reads of the retained FD after Qt retirement.
        owner.close()
        owner.close()
        owner.synchronize()  # Already queued delivery is inert after teardown.
        assert header.parentItem() is original_parent
        assert not window.property("nativeHeaderAttached")
        assert window.property("nativeHeaderSurface") is None
        assert events == (
            ["create", "close_refused", "close"]
            if not pending_attachment and not height_refused
            else ["create", "close"]
        )
    finally:
        if owner is not None:
            owner.close()
        _close(bridge, engine, window)


@pytest.mark.parametrize("reduced", [False, True])
def test_single_measured_inset_moves_brand_and_navigation_together_not_utilities_or_body(
    tmp_path, monkeypatch, reduced
):
    from yt_downloader.qt_quick import main

    monkeypatch.setattr(main, "_system_reduced_motion", lambda: reduced)
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        window.setProperty("nativeHeaderWidth", 1000)
        window.setProperty("nativeHeaderReserve", 90)
        window.setProperty("nativeHeaderAttached", True)
        window.setProperty("nativeHeaderFullscreen", True)
        header = window.findChild(QObject, "focusHeader")
        brand = window.findChild(QObject, "brandRow")
        navigation = window.findChild(QObject, "navigationRow")
        utilities = window.findChild(QObject, "utilitiesRow")
        slot = window.findChild(QObject, "headerGeometrySlot")
        for _ in range(4):
            app.processEvents()
            polish_scene(window.contentItem())
        gap = navigation.x() - brand.x()
        right = utilities.x() + utilities.width()
        body_top = slot.y() + slot.height()
        samples = []
        for target in (90, 0):
            window.setProperty("nativeHeaderLeadingInset", target)
            for _ in range(12):
                QTest.qWait(16)
                app.processEvents()
                samples.append(header.property("nativeHeaderInset"))
                assert navigation.x() - brand.x() == pytest.approx(gap)
                assert utilities.x() + utilities.width() == pytest.approx(right)
                assert slot.y() + slot.height() == pytest.approx(body_top)
            assert header.property("nativeHeaderInset") == pytest.approx(target)
        if reduced:
            assert all(value in (0, 90) for value in samples)
        else:
            assert any(0 < value < 90 for value in samples)
    finally:
        _close(bridge, engine, window)


def test_constructor_cleanup_refusal_retains_exact_owner_and_destroyed_hook(
    tmp_path, monkeypatch
):
    from PySide6.QtGui import QWindow

    from yt_downloader.qt_quick import mac_header

    _app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    closes = []

    class Host:
        view = 1234
        descriptor = 9

        def __init__(self, *_):
            pass

        def close(self):
            closes.append("close")
            if len(closes) == 1:
                raise RuntimeError("Native child teardown pending")

    monkeypatch.setattr(mac_header, "HeaderHost", Host)
    monkeypatch.setattr(QWindow, "fromWinId", lambda _: None)
    try:
        with pytest.raises(RuntimeError, match="Native child teardown pending"):
            mac_header.IntegratedHeader(window, 61)
        retained = window._native_window_controls
        assert retained.retired and not retained.closed
        assert (
            window._native_header_diagnostic["stage"]
            == "native_header_teardown_pending"
        )
        retained.close()
        assert retained.closed and closes == ["close", "close"]
    finally:
        _close(bridge, engine, window)
