"""Detail canvas allocations keep embedded consumers in the same window units."""

import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from yt_downloader.library_detail_layout import LibraryDetailLayout
from yt_downloader.ui_layout import WindowLogicalMetrics


@pytest.mark.parametrize("scale", [1, 2])
@pytest.mark.parametrize("width", [360, 720, 1100])
def test_scaled_fact_text_stays_before_copy_and_retains_canonical_role(scale, width):
    root = SimpleNamespace(_vodforge_logical_metrics=WindowLogicalMetrics(scale, True))
    canvas = Mock(find_all=Mock(return_value=()), bbox=Mock(return_value=None))
    owner = SimpleNamespace(
        winfo_toplevel=lambda: root,
        canvas=canvas,
        _depth=Mock(),
        _targets=[],
        _action=Mock(),
        _copy_value=Mock(),
    )
    text = []
    buttons = []
    p = SimpleNamespace(
        icon=Mock(),
        text=lambda *a, **k: text.append((a, k)),
        button=lambda *a, **k: buttons.append((a, k)),
    )
    LibraryDetailLayout._detail_panel(
        owner,
        p,
        10,
        20,
        width,
        "Output",
        "file",
        [("Saved Location", "C:/QA/" + ("long/" * 8), "folder")],
        0,
    )
    value = next((a, k) for a, k in text if a[2].startswith("C:/QA/"))
    copy = buttons[0]
    assert value[1]["font_scale"] == scale and value[1]["size"] == 14
    assert value[0][0] + value[1]["width"] <= copy[0][0] - 12 * scale
    assert copy[1]["unit_scale"] == scale


@pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="explicit native run required",
)
@pytest.mark.parametrize("dpi", [96, 192])
def test_detail_fonts_requested_children_and_mutation(
    dpi, request, monkeypatch, tmp_path
):
    import tkinter as tk
    import tkinter.font as tkfont
    from pathlib import Path

    from tests.test_archive_native import pump
    from tests.test_matte_native import save_native_capture
    from tests.test_scene_navigation import records
    from yt_downloader.archive_browser import archive_row_owner
    from yt_downloader.scene_components import ScenePainter, scene_font
    from yt_downloader.ui_layout import install_window_logical_metrics

    original = tk.Tk.__init__

    def admitted(self, *a, **k):
        original(self, *a, **k)
        install_window_logical_metrics(self, dpi=dpi)

    monkeypatch.setattr(tk.Tk, "__init__", admitted)
    app = request.getfixturevalue("application")
    app.geometry("1480x900")
    pump(app)
    scene = app.library_scene
    scale = dpi // 96
    rows = list(records(2))
    rows[0].update(
        title="Detail QA title",
        description="A measured description.",
        vodforge_user_tags=["Travel", "QA"],
    )
    scene.set_records(rows)
    scene.show_details(0)
    pump(app)
    scene._detail_versions = tuple(
        (archive_row_owner(row), f"Version {n + 1}") for n, row in enumerate(rows)
    )
    scene._render()
    pump(app)
    canvas = scene.canvas

    def assert_title():
        item = next(
            i
            for i in canvas.find_all()
            if canvas.type(i) == "text"
            and canvas.itemcget(i, "text") == "Detail QA title"
        )
        configured = canvas.itemcget(item, "font")
        assert int(canvas.tk.splitlist(configured)[1]) == -32 * scale
        actual = tkfont.Font(root=app, font=configured)
        expected = tkfont.Font(
            root=app, font=scene_font(32, bold=True, font_scale=scale)
        )
        assert actual.metrics("linespace") == expected.metrics("linespace")

    if scale > 1:
        original_text = ScenePainter.text

        def omit_units(self, *a, **k):
            k["font_scale"] = 1
            return original_text(self, *a, **k)

        with monkeypatch.context() as fault:
            fault.setattr(ScenePainter, "text", omit_units)
            scene._render()
            pump(app)
            with pytest.raises(AssertionError):
                assert_title()
        scene._render()
        pump(app)
    assert_title()
    assert int(canvas.tk.splitlist(scene._tag_entry.cget("font"))[1]) == -14 * scale
    for child in (scene._version_choice, scene._tag_entry):
        item = next(
            i
            for i in canvas.find_all()
            if canvas.type(i) == "window" and canvas.itemcget(i, "window") == str(child)
        )
        allocated = int(float(canvas.itemcget(item, "height")))
        assert allocated >= child.winfo_reqheight()
        y = canvas.coords(item)[1]
        extent = float(canvas.cget("scrollregion").split()[-1])
        canvas.yview_moveto(y / extent)
        pump(app)
        assert child.winfo_ismapped()
        assert child.winfo_height() >= child.winfo_reqheight()
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    canvas.yview_moveto(0)
    pump(app)
    save_native_capture(canvas, out / f"detail-{dpi}-title.png")
    canvas.yview_moveto(1)
    pump(app)
    save_native_capture(canvas, out / f"detail-{dpi}-facts.png")


from tests.test_native_thumbnail_rendering import application  # noqa: F401
