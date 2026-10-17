"""Native effects may attach only to an AppKit public content owner."""

import sys
from types import SimpleNamespace

import pytest

from yt_downloader.qt_quick.mac_windowing import _install_frosted_backdrop


@pytest.mark.parametrize(
    "parent_kind", ["private_frame", "missing", "public_content", "public_rejected"]
)
def test_backdrop_requires_public_content_parent(monkeypatch, parent_kind):
    calls = []
    frost = SimpleNamespace(
        setMaterial_=lambda *_: None,
        setBlendingMode_=lambda *_: None,
        setState_=lambda *_: None,
        setAppearance_=lambda *_: None,
        setAutoresizingMask_=lambda *_: None,
        removeFromSuperview=lambda: calls.append("removed"),
    )

    def add_public(*args):
        calls.append(("public", args))
        if parent_kind == "public_rejected":
            raise RuntimeError("PRIVATE native insertion refused")

    public = SimpleNamespace(addSubview_positioned_relativeTo_=add_public)
    private = SimpleNamespace(
        addSubview_positioned_relativeTo_=lambda *args: calls.append(("private", args))
    )
    parent = {
        "private_frame": private,
        "missing": None,
        "public_content": public,
        "public_rejected": public,
    }[parent_kind]
    view = SimpleNamespace(superview=lambda: parent, frame=lambda: (0, 0, 100, 80))
    properties = {}
    window = SimpleNamespace(
        setProperty=lambda name, value: properties.update({name: value})
    )
    state = {"opaque": True, "background": "original"}
    native = SimpleNamespace(
        contentView=lambda: public,
        isOpaque=lambda: state["opaque"],
        backgroundColor=lambda: state["background"],
        setOpaque_=lambda value: state.update(opaque=value),
        setBackgroundColor_=lambda value: state.update(background=value),
    )
    monkeypatch.setitem(
        sys.modules,
        "AppKit",
        SimpleNamespace(
            NSAppearance=SimpleNamespace(appearanceNamed_=lambda _: "dark"),
            NSAppearanceNameVibrantDark="dark",
            NSColor=SimpleNamespace(clearColor=lambda: "clear"),
            NSViewHeightSizable=1,
            NSViewWidthSizable=2,
            NSVisualEffectBlendingModeBehindWindow=1,
            NSVisualEffectMaterialSidebar=1,
            NSVisualEffectStateFollowsWindowActiveState=1,
            NSVisualEffectView=SimpleNamespace(
                alloc=lambda: SimpleNamespace(initWithFrame_=lambda _: frost)
            ),
            NSWindowBelow=-1,
        ),
    )
    accepted = _install_frosted_backdrop(window, native, view)
    if parent_kind == "public_content":
        assert accepted
        assert calls == [("public", (frost, -1, view))]
        assert state == {"opaque": False, "background": "clear"}
        assert properties["backgroundOpacity"] == 0.88
    else:
        assert not accepted
        if parent_kind == "public_rejected":
            assert calls == [("public", (frost, -1, view)), "removed"]
        else:
            assert calls == []
        assert state == {"opaque": True, "background": "original"}
        assert properties["backgroundOpacity"] == 1.0
        assert not hasattr(window, "_native_frosted_backdrop")


@pytest.mark.parametrize(
    "qt_visible,fullscreen,allowed,expected",
    [
        (False, False, True, 1),
        (False, True, True, 0),
        (True, False, True, 0),
        (False, False, False, 0),
    ],
)
def test_native_exit_uses_exact_window_and_current_retirement_permission(
    monkeypatch, qt_visible, fullscreen, allowed, expected
):
    from PySide6.QtGui import QGuiApplication

    from yt_downloader.qt_quick import mac_windowing

    monkeypatch.setattr(mac_windowing.sys, "platform", "darwin")
    monkeypatch.setattr(QGuiApplication, "platformName", lambda: "cocoa")
    calls, observers = [], []
    native = SimpleNamespace(
        isVisible=lambda: True,
        styleMask=lambda: 8 if fullscreen else 0,
        orderOut_=lambda sender: calls.append(sender),
    )
    center = SimpleNamespace(
        addObserverForName_object_queue_usingBlock_=lambda name, obj, queue, block: (
            observers.append((name, obj, queue, block)) or "token"
        ),
        removeObserver_=lambda token: calls.append(token),
    )
    monkeypatch.setitem(
        sys.modules,
        "objc",
        SimpleNamespace(objc_object=lambda **_: SimpleNamespace(window=lambda: native)),
    )
    monkeypatch.setitem(
        sys.modules,
        "AppKit",
        SimpleNamespace(
            NSWindowDidExitFullScreenNotification="exit", NSWindowStyleMaskFullScreen=8
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "Foundation",
        SimpleNamespace(
            NSNotificationCenter=SimpleNamespace(defaultCenter=lambda: center),
            NSOperationQueue=SimpleNamespace(mainQueue=lambda: "main"),
        ),
    )
    window = SimpleNamespace(winId=lambda: 5, isVisible=lambda: qt_visible)
    permission = {"allowed": allowed}
    hook = mac_windowing.watch_presentation_retirement(
        window, lambda: permission["allowed"]
    )
    assert hook is not None
    assert observers[0][:3] == ("exit", native, "main")
    observers[0][3](None)
    assert calls == [None] * expected
    hook.close()
    hook.close()
    observers[0][3](None)  # a callback already queued before removal must be inert
    assert calls == [None] * expected + ["token"]


def test_offscreen_retirement_never_resolves_a_native_window(monkeypatch):
    from PySide6.QtGui import QGuiApplication

    from yt_downloader.qt_quick import mac_windowing

    monkeypatch.setattr(QGuiApplication, "platformName", lambda: "offscreen")
    window = SimpleNamespace(
        winId=lambda: pytest.fail("offscreen must not access AppKit")
    )
    assert mac_windowing.watch_presentation_retirement(window, lambda: True) is None
