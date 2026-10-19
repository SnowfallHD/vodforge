"""Real offscreen Qt lifecycle; only native ABI is mocked. No GUI qualification."""

import math

import pytest
from PySide6.QtCore import QObject
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close
from tests.test_qt_interaction_invariants import _launch as original_launch
from tests.test_qt_scene_port import polish_scene


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


_launch = original_launch


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

        def row_sample(self):
            _, _, g = self.snapshot()
            hx, hy, hw, hh = g[27:31]
            if state.get("short_allocation"):
                hh = 32
            button_x = state.get(
                "button_x", hx + 9 if state.get("controls_inside") else 109
            )
            if state.get("controls_hidden"):
                return {
                    "owner": "unified-toolbar",
                    "current": True,
                    "host_visible": True,
                    "toolbar_owned": True,
                    "delegate_unchanged": True,
                    "full_size": True,
                    "transparent": True,
                    "title_hidden": True,
                    "transition": 0,
                    "fullscreen": bool(state.get("fullscreen")),
                    "host": [hx, hy, hw, hh],
                    "content": list(g[62:66]),
                    "buttons": [
                        {
                            "identity": i + 1,
                            "visibility": "hidden",
                            "visible_screen": [0, 0, 0, 0],
                        }
                        for i in range(3)
                    ],
                }
            if state.get("unallocated"):
                return {
                    "owner": "unified-toolbar",
                    "current": True,
                    "host_visible": False,
                    "toolbar_owned": True,
                    "delegate_unchanged": True,
                    "full_size": True,
                    "transparent": True,
                    "title_hidden": True,
                    "transition": 0,
                    "fullscreen": bool(state.get("fullscreen")),
                    "host": None,
                    "content": list(g[62:66]),
                    "buttons": [
                        {
                            "identity": i + 1,
                            "visibility": "hidden",
                            "visible_screen": [0, 0, 0, 0],
                        }
                        for i in range(3)
                    ],
                }
            return {
                "owner": "unified-toolbar",
                "current": True,
                "host_visible": True,
                "toolbar_owned": True,
                "delegate_unchanged": True,
                "full_size": True,
                "transparent": True,
                "title_hidden": True,
                "transition": state.get("transition", int(state["pending"])),
                "fullscreen": bool(state.get("fullscreen")),
                "host": [hx, hy, hw, hh],
                "content": list(g[62:66]),
                "buttons": [
                    {
                        "identity": i + 1,
                        "visibility": "hidden"
                        if state.get("mixed_controls") and i == 1
                        else "visible",
                        "visible_screen": [button_x + 23 * i, hy + 14, 14, 14],
                    }
                    for i in range(3)
                ],
            }

        def set_background(self, color):
            rig.brand_color = color

        def set_change_callback(self, callback):
            rig.native_callback = callback

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
            if state.pop("callback_during_update", False):
                rig.native_callback()

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


def test_actual_qml_one_packet_body_and_header_ownership(native_owner_rig):
    rig = native_owner_rig
    owner = rig.make()
    assert rig.header.parentItem() is rig.surface.contentItem()
    before = rig.window.property("nativeRowPacket")
    if hasattr(before, "toVariant"):
        before = before.toVariant()
    assert before["host_visible"] is True
    assert before["body_slot_height"] == 44 and before["leading"] == 0
    body = rig.window.findChild(QObject, "headerGeometrySlot").parentItem()
    for route in ["Forge", "Library", "Watch", "Activity"]:
        rig.bridge.selectHome(route)
        rig.settle()
        polish_scene(rig.window.contentItem())
        geometry_before = (body.x(), body.y(), body.width(), body.height())
        next_packet = dict(
            before,
            sequence=before["sequence"] + 1,
            state="controls-hidden",
            fullscreen=True,
            relative_x=0,
        )
        rig.window.setProperty("nativeRowPacket", next_packet)
        rig.settle()
        polish_scene(rig.window.contentItem())
        assert (body.x(), body.y(), body.width(), body.height()) == geometry_before
        assert rig.header.property("nativeHeaderInset") == 0
        rig.window.setProperty("nativeRowPacket", before)
    owner.close()
    assert owner.closed


def test_initial_native_allocation_pending_until_actual_frame_event(native_owner_rig):
    rig = native_owner_rig
    rig.state["short_allocation"] = True
    owner = rig.make()
    assert not owner.closed and not owner._attached
    assert rig.header.parentItem() is rig.original_parent
    assert not rig.surface.isVisible() and not rig.state["bound"]
    assert (
        rig.window._native_header_diagnostic["stage"]
        == "native_header_pending_allocation"
    )
    rig.state["short_allocation"] = False
    rig.notify()
    rig.settle()
    assert owner._attached and rig.header.parentItem() is rig.surface.contentItem()
    assert rig.window.property("nativeRowPacket")["body_slot_height"] == 44
    assert rig.events.count("show") == rig.events.count("bind") == 1
    owner.close()
    assert owner.closed


def test_native_descriptor_to_attached_signal_to_queued_ready_gate(native_owner_rig):
    from PySide6.QtCore import QThread, QTimer

    rig = native_owner_rig
    rig.state["short_allocation"] = True
    delivered = []

    def callback():
        if (
            rig.owner is not None
            and not rig.owner.closed
            and not rig.owner.retired
            and rig.owner._attached
        ):
            delivered.append(
                (
                    QThread.currentThread() is rig.app.thread(),
                    rig.window.property("nativeRowPacket")["height"],
                )
            )

    def queue():
        QTimer.singleShot(0, callback)

    rig.window.nativeHeaderAttachedChanged.connect(queue)
    owner = rig.make()
    rig.settle()
    assert not owner._attached and not delivered
    rig.notify()
    rig.settle()
    assert not owner._attached and not delivered
    rig.state["short_allocation"] = False
    rig.notify()
    rig.settle()
    assert delivered == [(True, 44)]
    owner.close()
    rig.settle()
    assert delivered == [(True, 44)]


def test_stale_queued_ready_delivery_does_not_admit_short_allocation(native_owner_rig):
    from PySide6.QtCore import QTimer

    rig = native_owner_rig
    rig.state["short_allocation"] = True
    delivered = []

    def callback():
        if (
            rig.owner is not None
            and not rig.owner.closed
            and not rig.owner.retired
            and rig.owner._attached
        ):
            delivered.append(True)

    def queue():
        QTimer.singleShot(0, callback)

    rig.window.nativeHeaderAttachedChanged.connect(queue)
    owner = rig.make()
    queue()
    rig.settle()
    assert not delivered and not owner._attached and not rig.state["bound"]
    owner.close()


def test_initial_missing_aperture_waits_without_binding_then_native_event_attaches(
    native_owner_rig,
):
    rig = native_owner_rig
    # Native ABI double models initial toolbar item not yet inserted by AppKit.
    rig.state["unallocated"] = True
    owner = rig.make()
    assert (
        not owner._attached and not rig.state["bound"] and not rig.surface.isVisible()
    )
    assert (
        rig.window._native_header_diagnostic["stage"]
        == "native_header_pending_allocation"
    )
    assert rig.header.parentItem() is rig.original_parent
    rig.state["unallocated"] = False
    rig.notify()
    rig.settle()
    assert owner._attached and rig.state["bound"]
    owner.close()


def test_current_inside_control_clearance_is_one_packet_and_body_never_reflows(
    native_owner_rig,
):
    from PySide6.QtTest import QSignalSpy

    rig = native_owner_rig
    owner = rig.make()
    body = rig.window.findChild(QObject, "headerGeometrySlot").parentItem()
    spy = QSignalSpy(rig.window.nativeRowPacketChanged)
    for route in ("Forge", "Library", "Watch", "Activity"):
        rig.bridge.selectHome(route)
        rig.settle()
        before = (body.x(), body.y(), body.width(), body.height())
        count = spy.count()
        rig.state["controls_inside"] = True
        rig.state["controls_hidden"] = False
        rig.notify()
        rig.settle()
        packet = rig.window.property("nativeRowPacket")
        assert packet["leading"] == packet["reserve"] == 89
        assert (
            rig.header.property("nativeHeaderInset") == 89 and spy.count() == count + 1
        )
        assert (body.x(), body.y(), body.width(), body.height()) == before
        count = spy.count()
        rig.state["controls_hidden"] = True
        rig.notify()
        rig.settle()
        packet = rig.window.property("nativeRowPacket")
        assert packet["leading"] == packet["reserve"] == 0
        assert (
            rig.header.property("nativeHeaderInset") == 0 and spy.count() == count + 1
        )
        assert (body.x(), body.y(), body.width(), body.height()) == before
    owner.close()


def test_native_item_is_transparent_content_and_has_no_competing_backings(
    native_owner_rig, tmp_path
):
    rig = native_owner_rig
    owner = rig.make()
    rig.surface.requestUpdate()
    QTest.qWait(60)
    rig.settle()
    frame = rig.surface.grabWindow()
    assert not frame.isNull()
    out = tmp_path / "background"
    out.mkdir()
    frame.save(str(out / "native-item.png"))
    # Blank content lane between nav and right utilities: no app surface/border.
    x = round(frame.width() * 0.78)
    y = round(frame.height() / 2)
    color = frame.pixelColor(x, y)
    assert color.alpha() == 0, ("custom item is still painted", x, y, color.getRgb())
    for name in (
        "nativeHeaderShadow",
        "nativeHeaderFlatSurface",
        "nativeHeaderConcaveSurface",
    ):
        assert rig.header.findChild(QObject, name) is None
    assert rig.window.property("nativeRowPacket")["body_slot_height"] == 44
    assert rig.header.parentItem() is rig.surface.contentItem()
    owner.close()


@pytest.mark.parametrize("deferred", [False, True])
def test_factory_preserves_default_visibility_and_explicit_native_startup_defer(
    tmp_path, monkeypatch, deferred
):
    from tests.test_qt_scene_port import qt_app
    from yt_downloader.qt_quick import main as qt_main

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge, defer_visibility=deferred)
    window = engine.rootObjects()[0]
    try:
        assert window.isVisible() is (not deferred)
        if deferred:
            window.show()
            assert window.isVisible()
    finally:
        _close(bridge, engine, window)


@pytest.mark.parametrize("transition", [1, 2])
def test_inflight_native_allocation_does_not_wait_for_fullscreen_did_notification(
    native_owner_rig, transition
):
    rig = native_owner_rig
    owner = rig.make()
    rig.state["transition"] = transition
    rig.state["rect"] = (110, 6, 930, 44)
    rig.notify()
    rig.settle()
    current = rig.window.property("nativeRowPacket")
    assert current["relative_x"] == 110
    assert current["width"] == rig.surface.width() == 930
    owner.close()


def test_native_callback_commits_before_native_allocation_callback_returns(
    native_owner_rig,
):
    rig = native_owner_rig
    owner = rig.make()
    assert callable(getattr(rig, "native_callback", None))
    rig.state["rect"] = (110, 6, 930, 44)
    rig.native_callback()
    # No event-loop pumping: deferred FD-only reconciliation is too late.
    assert rig.window.property("nativeRowPacket")["relative_x"] == 110
    assert rig.surface.width() == 930
    owner.close()
    assert rig.native_callback is None


def test_native_material_uses_same_canonical_brand_color_as_body(native_owner_rig):
    rig = native_owner_rig
    owner = rig.make()
    assert rig.brand_color == rig.window.property("glassSurfaceColor").getRgbF()
    assert rig.brand_color[3] == 1
    owner.close()


def test_reveal_reallocation_keeps_right_edge_and_left_clearance_in_same_turn(
    native_owner_rig,
):
    rig = native_owner_rig
    owner = rig.make()
    rig.state.update(fullscreen=True, button_x=119)
    brand = rig.window.findChild(QObject, "brandRow")
    utility = rig.window.findChild(QObject, "utilitiesRow")
    lefts, rights = [], []
    for x in (10, 17, 27, 46, 66, 84, 94, 96, 84, 46, 10):
        rig.state["rect"] = (x, 6, 1032 - x, 44)
        rig.native_callback()
        polish_scene(rig.surface.contentItem())
        lefts.append(x + brand.x())
        rights.append(x + utility.x() + utility.width())
    assert lefts == pytest.approx([99] * len(lefts))
    assert rights == pytest.approx([1032] * len(rights))
    owner.close()


def test_nested_native_change_finishes_in_same_transaction(native_owner_rig):
    rig = native_owner_rig
    owner = rig.make()
    rig.state.update(rect=(110, 6, 930, 44), callback_during_update=True)
    rig.native_callback()
    assert not owner.closed and not owner._synchronizing
    assert rig.window.property("nativeRowPacket")["width"] == 930
    owner.close()


def test_native_callback_refusal_does_not_unwind_across_native_boundary(
    native_owner_rig,
):
    rig = native_owner_rig
    owner = rig.make()
    callback = rig.native_callback
    rig.state["mismatch"] = True
    callback()
    assert owner.closed and rig.native_callback is None
    assert rig.window._native_header_diagnostic["stage"] == "native_header_refused"
    callback()  # A retired callback cannot regain ownership or schedule work.


def test_direct_native_mixed_button_setters_publish_only_coherent_next_allocation(
    native_owner_rig,
):
    rig = native_owner_rig
    owner = rig.make()
    before = rig.window.property("nativeRowPacket")
    rig.state["mixed_controls"] = True
    rig.native_callback()
    assert not owner.closed and rig.window.property("nativeRowPacket") == before
    assert (
        rig.window._native_header_diagnostic["stage"]
        == "native_header_pending_coherent_allocation"
    )
    rig.state.update(mixed_controls=False, rect=(110, 6, 930, 44))
    rig.native_callback()
    assert rig.window.property("nativeRowPacket")["width"] == 930
    assert rig.window._native_header_diagnostic["stage"] == "success"
    owner.close()


@pytest.mark.parametrize(
    "stage,smoke", [("application", True), ("engine", True), ("application", False)]
)
def test_explicit_smoke_receipts_precede_fallible_qt_startup(
    tmp_path, monkeypatch, capsys, stage, smoke
):
    """A stalled constructor must leave its phase before any cleanup can fail."""
    from types import SimpleNamespace

    from yt_downloader.qt_quick import main as qt_main

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(
        qt_main.sys, "argv", ["VODForge"] + (["--runtime-smoke"] if smoke else [])
    )
    monkeypatch.setattr(qt_main, "runtime_smoke", lambda **_kwargs: 0)
    monkeypatch.setattr(
        qt_main, "QQuickStyle", SimpleNamespace(setStyle=lambda _style: None)
    )
    monkeypatch.setattr(qt_main, "QFont", lambda value: value)

    def application(_argv):
        if stage == "application":
            raise RuntimeError("fictional application stop")
        return SimpleNamespace(
            setApplicationName=lambda _name: None,
            setFont=lambda _font: None,
            aboutToQuit=SimpleNamespace(connect=lambda _slot: None),
        )

    def engine(*_args, **_kwargs):
        raise RuntimeError("fictional engine stop")

    monkeypatch.setattr(qt_main, "QGuiApplication", application)
    monkeypatch.setattr(
        qt_main, "Bridge", lambda _path: SimpleNamespace(close=lambda **_kwargs: None)
    )
    monkeypatch.setattr(qt_main, "create_engine", engine)
    with pytest.raises(RuntimeError, match="fictional .* stop"):
        qt_main.main()
    lines = capsys.readouterr().out.splitlines()
    phases = [line for line in lines if line.startswith("VODFORGE_QT_SMOKE_PHASE ")]
    if not smoke:
        assert phases == []
    else:
        assert "VODFORGE_QT_SMOKE_PHASE application_begin" in phases
        assert ("VODFORGE_QT_SMOKE_PHASE engine_begin" in phases) == (stage == "engine")
        assert "VODFORGE_QT_SMOKE_PHASE engine_returned" not in phases
