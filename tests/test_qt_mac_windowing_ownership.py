"""Exact public window ownership must not depend on native Python closures."""

import builtins
from types import SimpleNamespace

import pytest

from yt_downloader.qt_quick import mac_windowing


def _cocoa(monkeypatch):
    from PySide6.QtGui import QGuiApplication

    monkeypatch.setattr(mac_windowing.sys, "platform", "darwin")
    monkeypatch.setattr(QGuiApplication, "platformName", lambda: "cocoa")


def _forbid_bridges(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in {"AppKit", "Foundation", "objc"}:
            raise AssertionError("Hardened native path imported Python bridge")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)


@pytest.mark.parametrize("reject_controls", [False, True])
def test_main_header_uses_public_native_owner_and_rolls_back(
    monkeypatch, reject_controls
):
    _cocoa(monkeypatch)
    _forbid_bridges(monkeypatch)
    state = {"style": 7, "title": 0, "transparent": False}
    calls = []
    native = SimpleNamespace(
        pointer=61,
        styleMask=lambda: state["style"],
        titleVisibility=lambda: state["title"],
        titlebarAppearsTransparent=lambda: state["transparent"],
        setStyleMask_=lambda value: state.update(style=value),
        setTitleVisibility_=lambda value: state.update(title=value),
        setTitlebarAppearsTransparent_=lambda value: state.update(transparent=value),
    )
    monkeypatch.setattr(mac_windowing, "_native_window", lambda _: native)
    owner = SimpleNamespace(closed=False, close=lambda: calls.append("close"))

    def controls(window, pointer):
        assert pointer == 61
        calls.append("create")
        if reject_controls:
            raise RuntimeError("Native control layout refused")
        return owner

    monkeypatch.setattr(mac_windowing, "IntegratedHeader", controls)
    properties = {}
    window = SimpleNamespace(
        setProperty=lambda name, value: properties.update({name: value})
    )
    assert mac_windowing.integrate_qt_main_window(window) is not reject_controls
    if reject_controls:
        assert state == {"style": 7, "title": 0, "transparent": False}
        assert not properties
    else:
        assert state == {"style": 7 | (1 << 15), "title": 1, "transparent": True}
        assert properties == {"backgroundOpacity": 1.0}
        assert window._native_window_controls is owner
        # Repeated integration never installs a competing native policy.
        assert mac_windowing.integrate_qt_main_window(window)
    assert calls == ["create"]


def test_native_window_resolves_only_supplied_qt_view(monkeypatch):
    calls = []
    monkeypatch.setattr(mac_windowing, "send", lambda *args: calls.append(args) or 61)
    native = mac_windowing._native_window(SimpleNamespace(winId=lambda: 41))
    assert native.pointer == 61
    assert native.toolbar() == 61
    assert calls == [
        (41, b"window", mac_windowing._POINTER),
        (61, b"toolbar", mac_windowing._POINTER),
    ]


@pytest.mark.parametrize(
    "qt_visible,fullscreen,allowed,expected",
    [
        (False, False, True, 1),
        (False, True, True, 0),
        (True, False, True, 0),
        (False, False, False, 0),
    ],
)
@pytest.mark.parametrize("close_route", ["explicit", "parent_destroyed"])
def test_native_exit_uses_exact_window_and_current_retirement_permission(
    monkeypatch, qt_visible, fullscreen, allowed, expected, close_route
):
    from PySide6 import QtCore

    _cocoa(monkeypatch)
    _forbid_bridges(monkeypatch)
    calls, callbacks, destroyed_callbacks = [], [], []
    signal = SimpleNamespace(
        connect=callbacks.append, disconnect=lambda f: calls.append("disconnect")
    )
    timer = SimpleNamespace(
        setInterval=lambda n: calls.append(("interval", n)),
        timeout=signal,
        start=lambda: calls.append("start"),
        stop=lambda: calls.append("stop"),
        deleteLater=lambda: calls.append("delete"),
    )
    window = SimpleNamespace(
        isVisible=lambda: qt_visible,
        destroyed=SimpleNamespace(
            connect=destroyed_callbacks.append,
            disconnect=lambda _: calls.append("destroy_disconnect"),
        ),
    )
    monkeypatch.setattr(
        QtCore,
        "QTimer",
        lambda parent: timer if parent is window else pytest.fail("wrong owner"),
    )
    native = SimpleNamespace(
        isVisible=lambda: True,
        styleMask=lambda: (1 << 14) if fullscreen else 0,
        orderOut_=lambda _: calls.append("retired"),
        retain=lambda: calls.append("retain"),
        release=lambda: calls.append("release"),
    )
    monkeypatch.setattr(
        mac_windowing, "_native_window", lambda w: native if w is window else None
    )
    permission = {"allowed": allowed}
    hook = mac_windowing.watch_presentation_retirement(
        window, lambda: permission["allowed"]
    )
    assert hook is not None
    assert calls == ["retain", ("interval", 100), "start"]
    callbacks[0]()
    assert calls.count("retired") == expected
    permission["allowed"] = False
    callbacks[0]()
    assert calls.count("retired") == expected
    if close_route == "parent_destroyed":
        destroyed_callbacks[0](window)
    else:
        hook.close()
    hook.close()
    callbacks[0]()  # already queued before timer disconnect must be inert
    assert calls.count("retired") == expected
    assert calls[-5:] == [
        "stop",
        "disconnect",
        "delete",
        "destroy_disconnect",
        "release",
    ]
    assert calls.count("retain") == calls.count("release") == 1


def test_offscreen_native_paths_never_resolve_a_window(monkeypatch):
    from PySide6.QtGui import QGuiApplication

    monkeypatch.setattr(QGuiApplication, "platformName", lambda: "offscreen")
    window = SimpleNamespace(
        winId=lambda: pytest.fail("offscreen accessed native window")
    )
    assert not mac_windowing.integrate_qt_main_window(window)
    assert mac_windowing.watch_presentation_retirement(window, lambda: True) is None


def test_retirement_constructor_failure_releases_retained_native_window(monkeypatch):
    from PySide6 import QtCore

    calls = []
    window = SimpleNamespace(
        destroyed=SimpleNamespace(disconnect=lambda _: None),
    )
    native = SimpleNamespace(
        retain=lambda: calls.append("retain"), release=lambda: calls.append("release")
    )

    def refuse_timer(_):
        raise RuntimeError("QObject already destroyed")

    monkeypatch.setattr(QtCore, "QTimer", refuse_timer)
    with pytest.raises(RuntimeError, match="already destroyed"):
        mac_windowing._PresentationRetirement(window, lambda: True, native)
    assert calls == ["retain", "release"]


@pytest.mark.parametrize("close_refused", [False, True])
def test_main_header_property_failure_closes_owner_before_style_rollback(
    monkeypatch, close_refused
):
    _cocoa(monkeypatch)
    calls = []
    native = SimpleNamespace(
        pointer=61,
        styleMask=lambda: 7,
        titleVisibility=lambda: 0,
        titlebarAppearsTransparent=lambda: False,
        setStyleMask_=lambda value: calls.append(("style", value)),
        setTitleVisibility_=lambda value: calls.append(("title", value)),
        setTitlebarAppearsTransparent_=lambda value: calls.append(
            ("transparent", value)
        ),
    )
    monkeypatch.setattr(mac_windowing, "_native_window", lambda _: native)

    def close():
        calls.append("close")
        if close_refused:
            raise RuntimeError("GUI-thread cleanup refused")

    monkeypatch.setattr(
        mac_windowing, "IntegratedHeader", lambda *args: SimpleNamespace(close=close)
    )

    def refuse_property(*_):
        raise RuntimeError("Qt parent closing")

    assert not mac_windowing.integrate_qt_main_window(
        SimpleNamespace(setProperty=refuse_property)
    )
    if close_refused:
        assert calls[-1] == "close"  # no style mutation under a still-live owner
    else:
        assert calls[-4:] == [
            "close",
            ("transparent", False),
            ("title", 0),
            ("style", 7),
        ]


def test_constructor_retained_native_owner_prevents_unsafe_style_rollback(monkeypatch):
    _cocoa(monkeypatch)
    mutations = []
    native = SimpleNamespace(
        pointer=61,
        styleMask=lambda: 7,
        titleVisibility=lambda: 0,
        titlebarAppearsTransparent=lambda: False,
        setStyleMask_=lambda value: mutations.append(("style", value)),
        setTitleVisibility_=lambda value: mutations.append(("title", value)),
        setTitlebarAppearsTransparent_=lambda value: mutations.append(
            ("transparent", value)
        ),
    )
    monkeypatch.setattr(mac_windowing, "_native_window", lambda _: native)
    retained = SimpleNamespace(closed=False, retired=True)
    window = SimpleNamespace()

    def create(*_):
        window._native_window_controls = retained
        raise RuntimeError("Native teardown refused")

    monkeypatch.setattr(mac_windowing, "IntegratedHeader", create)
    assert not mac_windowing.integrate_qt_main_window(window)
    assert mutations == [("style", 7 | (1 << 15)), ("title", 1), ("transparent", True)]
    assert not mac_windowing.integrate_qt_main_window(window)
