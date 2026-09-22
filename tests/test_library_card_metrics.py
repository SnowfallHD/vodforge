"""Measured browse cards preserve canonical text, target and material contracts."""

import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from yt_downloader.scene_components import ScenePainter


@pytest.mark.parametrize("scale", [1, 2])
def test_card_action_geometry_and_font_role_follow_explicit_units(scale):
    canvas = Mock()
    view = SimpleNamespace(canvas=canvas, _depth=Mock(), _button_labels=[], _targets=[])
    painter = ScenePainter(view)
    painter.button(20, 30, 220 * scale, "Play", Mock(), icon="play", unit_scale=scale)
    bounds, _ = view._targets[0]
    assert bounds == (20, 30, 20 + 220 * scale, 30 + 44 * scale)
    assert canvas.create_text.call_args.kwargs["font"][1] == -15 * scale
    assert view._depth.draw.call_args.kwargs["unit_scale"] == scale


@pytest.mark.parametrize("scale", [1, 2])
def test_action_material_retains_units_through_interaction(scale, monkeypatch):
    from yt_downloader import ui_chrome

    canvas = Mock()
    canvas.find_all.return_value = (1,)
    canvas.type.return_value = "image"
    monkeypatch.setattr(ui_chrome, "surface_backing_scale", lambda _: 1)
    producer = Mock()
    monkeypatch.setattr(ui_chrome, "action_button_image", producer)
    images = []

    def image(*a, **k):
        photo = Mock()
        images.append(photo)
        return photo, 10

    monkeypatch.setattr(ui_chrome, "create_surface_image", image)
    owner = ui_chrome.CanvasActionMaterialOwner(canvas)
    base = Mock()
    box = (0, 0, 200 * scale, 44 * scale)
    owner.register(1, box, False, base, unit_scale=scale)
    for pressed in (False, True):
        owner.paint(box, pressed)
        assert producer.call_args.kwargs["unit_scale"] == scale
    owner.focus(box)
    assert producer.call_args.kwargs["unit_scale"] == scale
    owner.focus(None)
    owner.paint(None, False)
    assert canvas.itemconfigure.call_args.kwargs["image"] is base


@pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="explicit native run required",
)
@pytest.mark.parametrize("dpi", [96, 192])
def test_browse_cards_fonts_bounds_and_scrolled_targets(
    dpi, request, monkeypatch, tmp_path
):
    import tkinter as tk
    import tkinter.font as tkfont
    from pathlib import Path

    from tests.test_archive_native import pump
    from tests.test_matte_native import save_native_capture
    from tests.test_scene_navigation import records
    from yt_downloader.scene_components import scene_font
    from yt_downloader.ui_layout import install_window_logical_metrics

    original = tk.Tk.__init__

    def admitted(self, *a, **k):
        original(self, *a, **k)
        install_window_logical_metrics(self, dpi=dpi)

    monkeypatch.setattr(tk.Tk, "__init__", admitted)
    app = request.getfixturevalue("application")
    app.geometry("1480x900")
    app._select_focus_view("library")
    pump(app)
    scene = app.library_scene
    scale = dpi // 96
    scene.set_records(records(25))
    scene.navigate("all")
    pump(app)
    canvas = scene.canvas
    window = scene._catalog_window
    assert window[2] == max(
        1, min(5, (canvas.winfo_width() - 4 + 14 * scale) // (200 * scale))
    )
    scene.canvas.yview_moveto(
        window[4] / float(canvas.cget("scrollregion").split()[-1])
    )
    pump(app)
    labels = {
        canvas.itemcget(i, "text"): i
        for i in canvas.find_all()
        if canvas.type(i) == "text"
    }
    titles = [(name, i) for name, i in labels.items() if name.startswith("Video ")]
    assert titles
    expected = tkfont.Font(root=app, font=scene_font(14, bold=True, font_scale=scale))
    for name, item in titles:
        font = canvas.itemcget(item, "font")
        assert int(canvas.tk.splitlist(font)[1]) == -14 * scale
        observed = tkfont.Font(root=app, font=font)
        assert observed.metrics("linespace") == expected.metrics("linespace")
        assert observed.measure(name) == expected.measure(name)
        assert (
            canvas.bbox(item)[2] - canvas.bbox(item)[0]
            <= float(canvas.itemcget(item, "width")) + 3
        )
    plays = [
        b for b, i, *_ in scene._button_labels if canvas.itemcget(i, "text") == "Play"
    ]
    assert plays and all(b[3] - b[1] == 44 * scale for b in plays)
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    save_native_capture(canvas, out / f"cards-{dpi}-all.png")
    # Route replacement preserves model membership and collection typography.
    scene.navigate("channels")
    pump(app)
    assert scene._catalog_window[3] == 212 * scale
    labels = {
        canvas.itemcget(i, "text"): i
        for i in canvas.find_all()
        if canvas.type(i) == "text"
    }
    channel = [i for text, i in labels.items() if text.startswith("Channel ")]
    assert channel
    assert all(
        int(canvas.tk.splitlist(canvas.itemcget(i, "font"))[1]) == -14 * scale
        for i in channel
    )
    save_native_capture(canvas, out / f"cards-{dpi}-channels.png")
    scene.set_records([])
    scene.navigate("home")
    pump(app)
    save_native_capture(canvas, out / f"cards-{dpi}-empty.png")


from tests.test_native_thumbnail_rendering import application  # noqa: F401
