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


@pytest.fixture
def native_owner_rig(tmp_path, monkeypatch):
    """Real public Qt windows, fake only the explicit native host ABI."""
    import os
    from types import SimpleNamespace

    from PySide6 import QtCore, QtGui, QtQuick
    from shiboken6 import isValid

    from yt_downloader.qt_quick import mac_header

    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    read_fd, write_fd = os.pipe()
    os.set_blocking(read_fd, False)
    state = {
        "pending": False,
        "flags": 1 | 2 | 32,
        "bound": False,
        "rect": None,
        "refuse_height": False,
        "partial_bind": False,
        "refuse_unbind": False,
        "stale_pointer": False,
        "current": True,
        "mismatch": False,
        "notify_update": False,
    }
    rig = SimpleNamespace(
        app=app,
        bridge=bridge,
        engine=engine,
        window=window,
        header=window.findChild(QObject, "focusHeader"),
        events=[],
        state=state,
        owner=None,
        surface=None,
        boundary=None,
        notifier=None,
        host=None,
        drains=0,
    )
    rig.original_parent = rig.header.parentItem()

    def reparented(*_):
        if isValid(rig.header) and rig.header.parentItem() is rig.original_parent:
            rig.events.append("header-restored")

    rig.header.parentChanged.connect(reparented)
    RealWindow, RealNotifier = QtQuick.QQuickWindow, QtCore.QSocketNotifier

    class Surface(RealWindow):
        def __init__(self, parent=None):
            assert parent is window, "Qt surface must be logically parented to main"
            super().__init__(parent)
            rig.surface = self
            rig.events.append("surface-created")

        def setParent(self, *_):
            raise AssertionError("No setParent repair loop is permitted")

        def show(self):
            assert not state["bound"], "show must precede native binding"
            rig.events.append("show")
            return super().show()

        def winId(self):
            value = int(super().winId())
            return value + int(state["stale_pointer"])

        def destroy(self):
            assert self.parent() is window, "Main parent must survive Qt destroy"
            assert not state["bound"], "Native unbind must precede Qt destroy"
            rig.events.append("qt-destroy")
            return super().destroy()

    class Notifier(RealNotifier):
        def __init__(self, *args):
            super().__init__(*args)
            rig.notifier = self

        def setEnabled(self, enabled):
            if not enabled:
                assert rig.boundary is None or rig.boundary.retired
                rig.events.append("notifier-retired")
            return super().setEnabled(enabled)

    real_boundary = mac_header.create_header_input_boundary

    def boundary(main, surface):
        result = real_boundary(main, surface)
        rig.boundary = result
        close = result.close

        def retire():
            close()
            rig.events.append("input-retired")

        result.close = retire
        return result

    class Host:
        view = 1234
        descriptor = read_fd
        closed = False

        def __init__(self, pointer, height, gutter, minimum):
            assert pointer == 61 and min(height, minimum) > 0 and gutter >= 0
            rig.host = self
            rig.events.append("host-created")

        def drain(self):
            rig.drains += 1
            try:
                return len(os.read(read_fd, 64))
            except BlockingIOError:
                return 0

        def snapshot(self):
            # Cocoa-style absolute screen rectangles are independently derived
            # from the real main allocation plus the requested local child rect.
            w, h = window.width(), window.height()
            x, y, cw, ch = state["rect"] or (90, 6, 980, 44)
            values = list(geometry()) + [math.nan] * 32
            values[10:12] = [cw, ch]
            values[27:31] = [100 + x, 200 + h - y - ch, cw, ch]
            values[62:66] = [100, 200, w, h]
            values[82:86] = [
                100 + x + int(state["mismatch"]) * 8,
                200 + h - y - ch,
                cw,
                ch,
            ]
            values[94:98] = [100, 200, w, h]
            flags = 1 if state["pending"] else state["flags"]
            if state["bound"]:
                flags |= 256 | 1024
                if state["current"]:
                    flags |= 512
            return 1, flags, tuple(values)

        def set_height(self, height):
            assert height > 0
            if state["refuse_height"]:
                raise RuntimeError("Native height refused")

        def bind_child(self, pointer, rect):
            assert rig.surface.isVisible(), "Native bind requires prior Qt show"
            assert rig.surface.parent() is window
            assert pointer == int(rig.surface.winId())
            assert rig.events.index("show") < len(rig.events)
            rig.events.append("bind")
            state["rect"], state["bound"] = tuple(rect), True
            if state["partial_bind"]:
                raise RuntimeError("Partial native bind refused")

        def update_child(self, pointer, rect):
            assert pointer == int(rig.surface.winId())
            assert rig.surface.parent() is window
            rig.events.append("update")
            state["rect"] = tuple(rect)
            if state["notify_update"]:
                os.write(write_fd, b"u")

        def unbind_child(self, _pointer):
            assert rig.boundary.retired
            assert not rig.notifier.isEnabled()
            assert (
                not isValid(rig.header)
                or rig.header.parentItem() is rig.original_parent
            )
            rig.events.append("unbind-refused" if state["refuse_unbind"] else "unbind")
            if state["refuse_unbind"]:
                raise RuntimeError("Native detach refused")
            state["bound"] = False

        def close(self):
            if self.closed:
                return
            assert not state["bound"]
            assert (
                rig.surface is None
                or not isValid(rig.surface)
                or "qt-destroy" in rig.events
            )
            rig.events.append("host-close")
            self.closed = True
            os.close(read_fd)
            os.close(write_fd)

    monkeypatch.setattr(QtQuick, "QQuickWindow", Surface)
    monkeypatch.setattr(QtCore, "QSocketNotifier", Notifier)
    monkeypatch.setattr(mac_header, "HeaderHost", Host)
    monkeypatch.setattr(mac_header, "create_header_input_boundary", boundary)

    def foreign_forbidden(*_):
        raise AssertionError("Foreign Qt parenting is forbidden")

    monkeypatch.setattr(QtGui.QWindow, "fromWinId", foreign_forbidden)

    def make(mutation=None):
        cls = mac_header.IntegratedHeader
        if mutation:
            import inspect

            source = inspect.getsource(cls)
            if mutation == "foreign-parent":
                source = source.replace("QQuickWindow(window)", "QQuickWindow()")
            elif mutation == "show-after-bind":
                source = source.replace("self._surface.show()", "pass")
                source = source.replace(
                    "self._child_bound = True",
                    "self._child_bound = True\n            self._surface.show()",
                )
            elif mutation == "missing-input-retire":
                source = source.replace("self._input_boundary.close()", "pass")
            scope = dict(vars(mac_header))
            exec(compile(source, "<header-owner-negative-control>", "exec"), scope)  # noqa: S102 - isolated mutation oracle
            cls = scope["IntegratedHeader"]
        rig.owner = cls(window, 61)
        return rig.owner

    rig.make = make
    rig.notify = lambda: os.write(write_fd, b"n")

    def settle():
        for _ in range(8):
            app.processEvents()

    rig.settle = settle
    try:
        yield rig
    finally:
        state["refuse_unbind"] = state["refuse_height"] = False
        retained = rig.owner or getattr(window, "_native_window_controls", None)
        if retained is not None and not retained.closed:
            retained.close()
        if isValid(window):
            _close(bridge, engine, window)
        else:
            if isValid(engine):
                engine.deleteLater()
            bridge.close()
        for descriptor in (read_fd, write_fd):
            try:
                os.close(descriptor)
            except OSError:
                pass


@pytest.mark.parametrize("pending", [False, True])
def test_event_driven_owner_uses_main_parent_and_exact_order(native_owner_rig, pending):
    rig = native_owner_rig
    rig.state["pending"] = pending
    owner = rig.make()
    if pending:
        assert rig.header.parentItem() is rig.original_parent
        assert not owner._child_pointer and not rig.surface.isVisible()
        assert rig.window._native_header_diagnostic["stage"] == "native_header_pending"
        rig.state["pending"] = False
        rig.notify()
        rig.settle()
    assert rig.surface.parent() is rig.window
    assert rig.header.parentItem() is rig.surface.contentItem()
    assert rig.window.property("nativeHeaderAttached")
    before = list(rig.events)
    rig.settle()
    assert rig.events == before  # No self-sustaining event-loop reconciliation.
    owner.close()
    owner.close()
    owner.synchronize()
    assert owner.closed
    assert rig.header.parentItem() is rig.original_parent
    assert not rig.window.property("nativeHeaderAttached")
    assert rig.window.property("nativeHeaderSurface") is None
    assert rig.events.index("input-retired") < rig.events.index("notifier-retired")
    assert rig.events.index("notifier-retired") < rig.events.index("header-restored")
    assert rig.events.index("header-restored") < rig.events.index("unbind")
    assert (
        rig.events.index("unbind")
        < rig.events.index("qt-destroy")
        < rig.events.index("host-close")
    )


def test_refused_height_retires_actual_owner(native_owner_rig):
    rig = native_owner_rig
    owner = rig.make()
    rig.state["refuse_height"] = True
    with pytest.raises(RuntimeError, match="Native height refused"):
        owner.update_height()
    assert owner.closed
    assert (
        rig.window._native_header_diagnostic["stage"] == "native_header_height_refused"
    )


@pytest.mark.parametrize("partial", [False, True])
def test_refused_unbind_retains_both_owners_for_retry(native_owner_rig, partial):
    rig = native_owner_rig
    rig.state.update(partial_bind=partial, refuse_unbind=True)
    if partial:
        with pytest.raises(RuntimeError, match="Native detach refused"):
            rig.make()
        owner = rig.window._native_window_controls
    else:
        owner = rig.make()
        with pytest.raises(RuntimeError, match="Native detach refused"):
            owner.close()
    assert owner.retired and not owner.closed
    assert rig.state["bound"] and rig.surface.isVisible()
    assert "qt-destroy" not in rig.events and "host-close" not in rig.events
    drains = rig.drains
    owner.synchronize()
    assert rig.drains == drains
    rig.state["refuse_unbind"] = False
    owner.close()
    assert owner.closed and not rig.state["bound"]


def test_partial_bind_is_detached_before_qt_destroy(native_owner_rig):
    rig = native_owner_rig
    rig.state["partial_bind"] = True
    with pytest.raises(RuntimeError, match="Partial native bind refused"):
        rig.make()
    assert (
        rig.events.index("unbind")
        < rig.events.index("qt-destroy")
        < rig.events.index("host-close")
    )


@pytest.mark.parametrize(
    "failure", ["stale-pointer", "native-generation", "global-mismatch"]
)
def test_bound_child_generation_and_global_geometry_refuse(native_owner_rig, failure):
    rig = native_owner_rig
    owner = rig.make()
    if failure == "native-generation":
        rig.state["current"] = False
    else:
        rig.state["stale_pointer" if failure == "stale-pointer" else "mismatch"] = True
    with pytest.raises(
        RuntimeError, match="replaced|generation changed|coordinates disagree"
    ):
        owner.synchronize()
    assert owner.closed and not rig.state["bound"]


def test_one_external_update_does_not_create_feedback(native_owner_rig):
    rig = native_owner_rig
    owner = rig.make()
    rig.state["rect"] = (96, 6, 984, 44)
    rig.state["notify_update"] = True
    owner.synchronize()
    rig.settle()
    assert rig.events.count("show") == rig.events.count("bind") == 1
    assert rig.events.count("update") == 1
    assert rig.drains <= 3


def test_actual_main_destroy_callback_closes_owned_generation(native_owner_rig):
    from PySide6.QtCore import QCoreApplication, QEvent

    rig = native_owner_rig
    owner = rig.make()
    rig.window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert owner.closed and rig.host.closed


@pytest.mark.parametrize(
    "mutation", ["foreign-parent", "show-after-bind", "missing-input-retire"]
)
def test_owner_boundary_oracles_detect_negative_controls(native_owner_rig, mutation):
    rig = native_owner_rig
    if mutation == "missing-input-retire":
        owner = rig.make(mutation)
        with pytest.raises(AssertionError):
            owner.close()
        # Retain negative evidence, then close the exact real filter for cleanup.
        rig.boundary.close()
        rig.events.append("input-retired")
        # The mutation deliberately interrupted retirement midway. Use the
        # unchanged production cleanup on this exact test owner, not the mutant.
        from yt_downloader.qt_quick import mac_header

        owner._retired = False
        owner._input_boundary = rig.boundary
        mac_header.IntegratedHeader.close(owner)
    else:
        with pytest.raises(AssertionError):
            rig.make(mutation)


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


@pytest.mark.parametrize("style", ["shadow", "concave"])
def test_native_style_comparison_argument_is_closed_and_process_local(style):
    from yt_downloader.qt_quick.main import _argument_parser

    parser = _argument_parser()
    assert parser.parse_args([]).native_header_style == "shadow"
    assert (
        parser.parse_args(["--native-header-style", style]).native_header_style == style
    )
    with pytest.raises(SystemExit) as invalid:
        parser.parse_args(["--native-header-style", "arbitrary"])
    assert invalid.value.code == 2
