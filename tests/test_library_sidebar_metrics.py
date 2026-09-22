"""Sidebar unit conversion retains canonical font roles, state and targets."""

import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from yt_downloader.scene_components import ScenePainter, scene_font


@pytest.mark.parametrize("size", [11, 13, 15, 24, 32, 40])
@pytest.mark.parametrize("bold", [False, True])
def test_scaled_font_preserves_canonical_family_and_weight(size, bold):
    ordinary = scene_font(size, bold=bold)
    scaled = scene_font(size, bold=bold, font_scale=2)
    assert scaled == (ordinary[0], ordinary[1] * 2, ordinary[2])


def test_painter_keeps_measured_coordinates_and_explicit_stroke():
    canvas = Mock()
    fit = Mock(return_value="Rendered")
    painter = ScenePainter(SimpleNamespace(canvas=canvas, _fit=fit))
    painter.text(122, 134, "Rendered", size=15, bold=True, width=230, font_scale=2)
    assert fit.call_args.args[-1] == scene_font(15, bold=True, font_scale=2)
    assert canvas.create_text.call_args.args == (122, 134)
    assert canvas.create_text.call_args.kwargs["width"] == 230
    painter.icon("folder", 44, 132, 44, stroke_width=4)
    assert canvas.create_line.call_args.kwargs["width"] == 4


def test_navigation_material_retains_units_through_hover_and_restore(monkeypatch):
    from yt_downloader import ui_chrome

    canvas = Mock()
    canvas.find_all.return_value = (1,)
    canvas.type.return_value = "image"
    monkeypatch.setattr(ui_chrome, "surface_backing_scale", lambda _: 1)
    generated = Mock()
    producer = Mock(return_value=generated)
    monkeypatch.setattr(ui_chrome, "navigation_button_image", producer)
    images = []

    def create(*_args, **_kwargs):
        photo = Mock()
        images.append(photo)
        return photo, 10

    monkeypatch.setattr(ui_chrome, "create_surface_image", create)
    owner = ui_chrome.CanvasActionMaterialOwner(canvas)
    base = Mock()
    bounds = (16, 108, 422, 198)
    owner.register_navigation(
        1, bounds, background="#303030", selected=False, photo=base, unit_scale=2
    )
    for pressed in (False, True):
        owner.paint(bounds, pressed)
        assert producer.call_args.kwargs["unit_scale"] == 2
    owner.focus(bounds)
    assert producer.call_args.kwargs["unit_scale"] == 2
    owner.focus(None)
    owner.paint(None, False)
    assert canvas.itemconfigure.call_args.kwargs["image"] is base


@pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="explicit native run required",
)
@pytest.mark.parametrize("dpi", [96, 192])
def test_sidebar_geometry_font_material_and_scrolled_action(
    dpi, request, monkeypatch, tmp_path
):
    import tkinter as tk
    import tkinter.font as tkfont
    from pathlib import Path

    from tests.test_archive_native import pump
    from tests.test_matte_native import save_native_capture
    from yt_downloader.ui_layout import install_window_logical_metrics

    original = tk.Tk.__init__

    def admitted(self, *args, **kwargs):
        original(self, *args, **kwargs)
        install_window_logical_metrics(self, dpi=dpi)

    monkeypatch.setattr(tk.Tk, "__init__", admitted)
    app = request.getfixturevalue("application")
    app.geometry("1180x640")
    app._select_focus_view("library")
    pump(app)
    scene, scale = app.library_scene, dpi // 96
    canvas = scene.sidebar
    assert canvas.winfo_width() == 226 * scale
    calls = []
    scene._choose_volume = lambda: calls.append("volume")
    scene._draw_sidebar()
    pump(app)
    labels = {
        canvas.itemcget(item, "text"): item
        for item in canvas.find_all()
        if canvas.type(item) == "text"
    }
    font = canvas.itemcget(labels["All Media"], "font")
    declared = canvas.tk.splitlist(font)
    assert int(declared[1]) == -15 * scale
    expected = tkfont.Font(root=app, font=scene_font(15, font_scale=scale))
    observed = tkfont.Font(root=app, font=font)
    assert observed.metrics("linespace") == expected.metrics("linespace")
    assert observed.measure("All Media") == expected.measure("All Media")
    assert canvas.bbox(labels["All Media"])[2] < canvas.winfo_width() - 50 * scale
    assert scene._sidebar_targets[0][0] == (
        8 * scale,
        54 * scale,
        211 * scale,
        99 * scale,
    )
    material = canvas._action_material
    nav = scene._sidebar_targets[1][0]
    assert material.controls[nav][-1] == scale
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    canvas.yview_moveto(0)
    save_native_capture(canvas, out / f"sidebar-{dpi}-resting.png")
    material.paint(nav, False)
    pump(app)
    save_native_capture(canvas, out / f"sidebar-{dpi}-hover.png")
    material.paint(None, False)
    canvas.yview_moveto(1)
    pump(app)
    bounds, callback = scene._sidebar_targets[-1]
    x = (bounds[0] + bounds[2]) // 2
    y = (bounds[1] + bounds[3]) // 2 - canvas.canvasy(0)
    assert 0 <= y <= canvas.winfo_height()
    event = SimpleNamespace(x=x, y=y)
    actions = scene._sidebar_pointer_actions
    assert actions.hit(event)[1] is callback
    actions.press(event)
    actions.release(event)
    actions.release(event)
    assert calls == ["volume"]
    save_native_capture(canvas, out / f"sidebar-{dpi}-storage-reached.png")


# Reuse the maintained isolated DownloaderApp fixture; no user library/services.
from tests.test_native_thumbnail_rendering import application  # noqa: F401
