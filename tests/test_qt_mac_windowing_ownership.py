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
