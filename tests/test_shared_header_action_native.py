"""The header consumes one full-size shared action face, including its label."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from tests.test_archive_native import application as _application
from tests.test_archive_native import pump, seed
from yt_downloader.platform_services import capture_own_widget
from yt_downloader.ui_theme import THEME
from yt_downloader.ui_widgets import RoundedIconButton

application = _application
pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="native display required"
)


def _capture(button: RoundedIconButton, path: Path) -> Image.Image:
    image = capture_own_widget(button).convert("RGB")
    image.save(path)
    return image


def _assert_selected_stone_depth(image: Image.Image) -> None:
    """The upper inset shade and lower face must remain distinct on screen."""
    x = image.width // 2
    upper = image.getpixel((x, 6))
    lower = image.getpixel((x, image.height - 10))
    assert sum(lower) - sum(upper) > 30, "Selected face lost its inset depth"


def test_header_material_image_label_and_screen_have_one_owner(
    application, tmp_path, monkeypatch
):
    from yt_downloader import ui_chrome

    app = application
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    out.mkdir(parents=True, exist_ok=True)
    seed(app, tmp_path, count=1)
    app.geometry("1200x760+80+80")
    app._select_focus_view("forge")
    pump(app, 0.2)
    nav = app._focus_nav_buttons["library"]
    assert isinstance(nav, RoundedIconButton)
    assert nav._matte_material_surface is True
    assert nav.cget("text") == "Library"
    assert not nav.cget("selected")
    assert nav.type(nav._background_item) == "image"
    assert nav.type(nav._content_item) == "text"
    assert nav._icon_item is not None and nav.type(nav._icon_item) == "image"
    assert len(nav.find_all()) == 3, "A second border or surround was painted"
    assert tuple(map(int, nav.coords(nav._background_item))) == (0, 0)
    assert (
        nav.tk.call("image", "width", str(nav._background_image)) == nav.winfo_width()
    )
    assert (
        nav.tk.call("image", "height", str(nav._background_image)) == nav.winfo_height()
    )
    nav.event_generate("<ButtonPress-1>", x=10, y=10)
    nav.event_generate("<ButtonRelease-1>", x=-2, y=10)
    pump(app, 0.03)
    assert app._focus_selected_view == "forge", "Outside release activated navigation"
    nav.state(["disabled"])
    nav.invoke()
    assert app._focus_selected_view == "forge", "Disabled navigation activated"
    nav.state(["!disabled"])
    label = nav.bbox(nav._content_item)
    assert label is not None and 0 < label[0] < label[2] < nav.winfo_width()
    idle = _capture(nav, out / "header-library-idle.png")
    corner = idle.getpixel((0, 0))
    assert (
        max(
            abs(a - b)
            for a, b in zip(corner, idle.getpixel((idle.width - 1, 0)), strict=True)
        )
        <= 2
    )

    nav.state(["active"])
    pump(app, 0.07)
    hover = _capture(nav, out / "header-library-hover.png")
    assert ImageChops.difference(idle, hover).getbbox() is not None
    nav.state(["!active"])
    app._select_focus_view("library")
    pump(app, 0.15)
    assert nav.cget("selected")
    selected = _capture(nav, out / "header-library-selected.png")
    assert ImageChops.difference(idle, selected).getbbox() is not None
    _assert_selected_stone_depth(selected)
    assert len(nav.find_all()) == 3

    # A known-bad producer must reach the *screen* through this exact owner.
    original = ui_chrome.action_button_image
    calls = []

    def flat_fault(width, height, **kwargs):
        calls.append((width, height, kwargs))
        return Image.new(
            "RGBA",
            (width * kwargs.get("density", 1), height * kwargs.get("density", 1)),
            "#e04090",
        )

    with monkeypatch.context() as fault:
        fault.setattr(ui_chrome, "action_button_image", flat_fault)
        nav._redraw()
        pump(app, 0.04)
        broken = _capture(nav, out / "header-flat-fault.png")
        assert calls and calls[-1][:2] == (nav.winfo_width(), nav.winfo_height())
        with pytest.raises(AssertionError, match="lost its inset depth"):
            _assert_selected_stone_depth(broken)
        assert ImageChops.difference(selected, broken).getbbox() is not None
    assert ui_chrome.action_button_image is original
    nav._redraw()
    pump(app, 0.04)
    restored = _capture(nav, out / "header-restored.png")
    assert ImageChops.difference(selected, restored).getbbox() is None

    app.appearance_theme_var.set("Cobalt")
    app._request_live_theme()
    pump(app, 0.2)
    rethemed = _capture(nav, out / "header-rethemed.png")
    assert nav.type(nav._background_item) == "image"
    assert len(nav.find_all()) == 3
    assert nav.cget("text") == "Library"
    assert ImageChops.difference(selected, rethemed).getbbox() is not None
    assert tuple(map(int, nav.coords(nav._background_item))) == (0, 0)
    assert (
        nav.tk.call("image", "width", str(nav._background_image)) == nav.winfo_width()
    )
    assert THEME["bg"] != "#e04090"


def test_header_material_stays_full_size_during_compact_resize(application, tmp_path):
    app = application
    seed(app, tmp_path, count=1)
    for width in (1200, 900):
        app.geometry(f"{width}x640+80+80")
        pump(app, 0.2)
        for nav in app._focus_nav_buttons.values():
            assert isinstance(nav, RoundedIconButton)
            assert nav.winfo_ismapped()
            assert (
                nav.tk.call("image", "width", str(nav._background_image))
                == nav.winfo_width()
            )
            assert (
                nav.tk.call("image", "height", str(nav._background_image))
                == nav.winfo_height()
            )
            assert len(nav.find_all()) == 3
            assert (
                nav.winfo_rootx() + nav.winfo_width()
                <= app.winfo_rootx() + app.winfo_width()
            )
