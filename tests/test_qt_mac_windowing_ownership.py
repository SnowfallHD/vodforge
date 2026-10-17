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


@pytest.mark.parametrize("reject_toolbar", [False, True])
def test_main_header_uses_public_scalar_calls_and_rolls_back(
    monkeypatch, reject_toolbar
):
    _cocoa(monkeypatch)
    _forbid_bridges(monkeypatch)
    state = {"style": 7, "title": 0, "transparent": False, "toolbar": 51}
    calls = []

    def set_toolbar(value):
        if reject_toolbar and value == 52:
            raise RuntimeError("Native toolbar refused")
        state["toolbar"] = value

    native = SimpleNamespace(
        styleMask=lambda: state["style"],
        titleVisibility=lambda: state["title"],
        titlebarAppearsTransparent=lambda: state["transparent"],
        toolbar=lambda: state["toolbar"],
        setStyleMask_=lambda v: state.update(style=v),
        setTitleVisibility_=lambda v: state.update(title=v),
        setTitlebarAppearsTransparent_=lambda v: state.update(transparent=v),
        setToolbar_=set_toolbar,
        setToolbarStyle_=lambda v: calls.append(("toolbar_style", v)),
    )
    monkeypatch.setattr(
        mac_windowing, "_native_window", lambda _: native, raising=False
    )
    monkeypatch.setattr(mac_windowing, "_new_toolbar", lambda: 52, raising=False)
    monkeypatch.setattr(
        mac_windowing, "send", lambda *args: calls.append(args), raising=False
    )
    properties = {}
    window = SimpleNamespace(setProperty=lambda n, v: properties.update({n: v}))
    assert mac_windowing.integrate_qt_main_window(window) is not reject_toolbar
    if reject_toolbar:
        assert state == {"style": 7, "title": 0, "transparent": False, "toolbar": 51}
        assert not properties
    else:
        assert state == {
            "style": 7 | (1 << 15),
            "title": 1,
            "transparent": True,
            "toolbar": 52,
        }
        assert properties == {"backgroundOpacity": 1.0}
        assert ("toolbar_style", 3) in calls
    assert (51, b"retain", mac_windowing._POINTER) in calls
    assert (51, b"release", None) in calls
    assert (52, b"release", None) in calls


def test_native_window_resolves_only_supplied_qt_view(monkeypatch):
    calls = []
    monkeypatch.setattr(mac_windowing, "send", lambda *args: calls.append(args) or 61)
    native = mac_windowing._native_window(SimpleNamespace(winId=lambda: 41))
    assert native.pointer == 61
    assert calls == [(41, b"window", mac_windowing._POINTER)]


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


@pytest.mark.parametrize("failure", [None, "string", "toolbar", "configuration"])
def test_native_toolbar_owns_identifier_without_autorelease_dependency(
    monkeypatch, failure
):
    calls = []
    monkeypatch.setattr(
        mac_windowing, "class_pointer", lambda name: 11 if name == b"NSString" else 12
    )

    def send(receiver, selector, restype, argtypes=(), *args):
        calls.append((receiver, selector))
        if selector == b"alloc":
            return receiver + 100
        if selector == b"initWithUTF8String:":
            return 0 if failure == "string" else receiver
        if selector == b"initWithIdentifier:":
            assert args == (111,)
            return 0 if failure == "toolbar" else receiver
        if selector == b"setAllowsUserCustomization:" and failure == "configuration":
            raise RuntimeError("Native configuration refused")
        return None

    monkeypatch.setattr(mac_windowing, "send", send)
    if failure is None:
        assert mac_windowing._new_toolbar() == 112
    else:
        with pytest.raises(RuntimeError):
            mac_windowing._new_toolbar()
    assert calls.count((111, b"release")) == (failure != "string")
    assert calls.count((112, b"release")) == (failure == "configuration")
    assert not any(selector == b"stringWithUTF8String:" for _, selector in calls)
