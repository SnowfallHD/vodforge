"""Library caller preserves the scaled search field and following media bounds."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from yt_downloader.library_scene_layout import LibrarySceneLayout
from yt_downloader.ui_layout import WindowLogicalMetrics


@pytest.mark.parametrize("scale", [1, 2])
@pytest.mark.parametrize("width", [340, 520, 720, 1000, 1534])
@pytest.mark.parametrize("route", ["home", "all"])
def test_search_toolbar_couples_allocation_reflow_and_following_content(
    scale, width, route
):
    root = SimpleNamespace(_vodforge_logical_metrics=WindowLogicalMetrics(scale, True))
    canvas = Mock()
    owner = SimpleNamespace(
        winfo_toplevel=lambda: root,
        canvas=canvas,
        _route=route,
        _records=[{}],
        _selection_mode=False,
        _search_field=object(),
        _project_search_backdrop=Mock(),
        _sort="recent",
        _filter="",
        _sort_menu=Mock(),
        _filter_menu=Mock(),
        _start_selection=Mock(),
        navigate=Mock(),
    )
    boxes = []
    painter = SimpleNamespace(
        text=Mock(),
        link=Mock(),
        button=lambda x, y, w, *a, **kw: boxes.append((x, y, x + w, y + 44)),
    )
    end = LibrarySceneLayout._toolbar(owner, painter, width, 80, "Recent downloads")
    call = canvas.create_window.call_args
    x, y = call.args
    w, h = call.kwargs["width"], call.kwargs["height"]
    assert h >= 40 * scale
    assert 0 <= x < x + w <= width
    assert w >= min(200 * scale, width - (66 if route == "home" else 0))
    assert end >= y + h + 20
    for left, top, right, bottom in boxes:
        assert 0 <= left < right <= width
        assert end >= bottom + 20
        assert x + w <= left or right <= x or y + h <= top or bottom <= y
    for index, a in enumerate(boxes):
        for b in boxes[index + 1 :]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


def _native_enabled():
    import os

    return os.environ.get("VODFORGE_NATIVE_UI_TESTS") == "1"


@pytest.mark.skipif(not _native_enabled(), reason="explicit native run required")
@pytest.mark.parametrize("dpi", [96, 192])
def test_real_search_children_fit_caller_allocation(dpi):
    import tkinter as tk

    from yt_downloader.library_search_ui import LibrarySearchField
    from yt_downloader.ui_layout import install_window_logical_metrics

    root = tk.Tk()
    try:
        install_window_logical_metrics(root, dpi=dpi)
        root.geometry("1100x460")
        canvas = tk.Canvas(root, highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        value = tk.StringVar(root)
        field = LibrarySearchField(canvas, variable=value, placeholder="Search media…")
        owner = SimpleNamespace(
            winfo_toplevel=lambda: root,
            canvas=canvas,
            _route="all",
            _records=[{}],
            _selection_mode=False,
            _search_field=field,
            _project_search_backdrop=Mock(),
            _sort="recent",
            _filter="",
            _sort_menu=Mock(),
            _filter_menu=Mock(),
            _start_selection=Mock(),
            navigate=Mock(),
        )
        painter = SimpleNamespace(text=Mock(), link=Mock(), button=Mock())
        for width in (1000, 520, 1000):
            canvas.delete("all")
            end = LibrarySceneLayout._toolbar(owner, painter, width, 30, "All media")
            root.update()
            assert field.winfo_height() >= field.winfo_reqheight()
            entry = field.entry
            linespace = int(
                root.tk.call("font", "metrics", entry.cget("font"), "-linespace")
            )
            assert entry.winfo_height() >= linespace
            assert entry.winfo_y() >= 0
            assert entry.winfo_y() + entry.winfo_height() <= field.winfo_height()
            assert end >= field.winfo_y() + field.winfo_height() + 20
            value.set("café 東京 exact retained query")
            root.update()
            assert entry.get() == value.get()
    finally:
        root.destroy()


@pytest.mark.parametrize("window_xy", [(10, 80), (720, 640), (400, 300)])
def test_search_backdrop_projection_uses_shared_canvas_coordinates(
    monkeypatch, window_xy
):
    from yt_downloader import library_scene_ui as module
    from yt_downloader.library_scene_ui import LibraryScene

    parent = Mock()
    parent._matte_backdrop = SimpleNamespace(item=10)
    parent.type.return_value = "window"
    parent.coords.side_effect = lambda item: (1534, 0) if item == 10 else window_xy
    child = Mock()
    view = SimpleNamespace(
        _closed=False,
        canvas=parent,
        _search_window=20,
        _search_field=SimpleNamespace(
            winfo_ismapped=lambda: True, _chrome=SimpleNamespace(canvas=child)
        ),
    )
    draw = Mock(return_value=SimpleNamespace(item=30))
    monkeypatch.setattr(module, "draw_matte_backdrop", draw, raising=False)
    LibraryScene._project_search_backdrop(view)
    child.coords.assert_called_once_with(30, 1534 - window_xy[0], -window_xy[1])
    # Both objects use parent canvas coordinates: scrolling must not introduce
    # another root/viewport offset or scale either measured coordinate again.
    parent.canvasx.assert_not_called()
    parent.canvasy.assert_not_called()


@pytest.mark.skipif(not _native_enabled(), reason="explicit native run required")
@pytest.mark.parametrize("dpi", [96, 192])
def test_search_corners_match_exposed_canvas_after_move_scroll_and_theme(dpi, tmp_path):
    import os
    import tkinter as tk
    from pathlib import Path

    from PIL import Image, ImageChops, ImageFilter

    from tests.test_archive_native import pump
    from tests.test_matte_native import save_native_capture
    from yt_downloader import ui_theme
    from yt_downloader.library_scene_ui import LibraryScene
    from yt_downloader.library_search_ui import LibrarySearchField
    from yt_downloader.ui_layout import install_window_logical_metrics
    from yt_downloader.ui_materials import draw_matte_backdrop
    from yt_downloader.ui_theme import THEME, apply_theme_selection

    root = tk.Tk()
    original, original_name = dict(THEME), ui_theme._active_theme_name
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    detected = []
    try:
        install_window_logical_metrics(root, dpi=dpi)
        root.geometry("1000x620")
        canvas = tk.Canvas(root, highlightthickness=0, bd=0)
        canvas.pack(fill="both", expand=True)
        value = tk.StringVar(root)
        field = LibrarySearchField(canvas, variable=value, placeholder="Search media…")
        view = SimpleNamespace(
            _closed=False,
            winfo_toplevel=lambda: root,
            canvas=canvas,
            _route="home",
            _records=[{}],
            _selection_mode=False,
            _search_field=field,
            _search_window=None,
            _sort="recent",
            _filter="",
            _sort_menu=Mock(),
            _filter_menu=Mock(),
            _start_selection=Mock(),
            navigate=Mock(),
        )
        view._project_search_backdrop = LibraryScene._project_search_backdrop.__get__(
            view
        )
        chrome = field._chrome.canvas
        draw_matte_backdrop(chrome)
        chrome.bind("<Configure>", view._project_search_backdrop, add="+")
        field.bind("<Configure>", view._project_search_backdrop, add="+")
        field.bind("<Map>", view._project_search_backdrop, add="+")
        painter = SimpleNamespace(text=Mock(), link=Mock(), button=Mock())
        pump(root)
        for index, (theme, route, width, y, scroll) in enumerate(
            (
                ("Violet", "home", 996, 60, 0),
                ("Cobalt", "all", 760, 250, 0),
                ("Violet", "all", 996, 360, 0.18),
            )
        ):
            apply_theme_selection(theme)
            field.apply_theme()
            canvas.delete("all")
            draw_matte_backdrop(canvas)
            view._route = route
            LibrarySceneLayout._toolbar(view, painter, width, y, "Saved media")
            canvas.configure(scrollregion=(0, 0, 996, 1100))
            canvas.yview_moveto(scroll)
            pump(root)
            # The same explicit owner hook used by the production toolbar and
            # child Configure must align the material after every placement.
            x = field.winfo_rootx() - canvas.winfo_rootx()
            top = field.winfo_rooty() - canvas.winfo_rooty()
            assert top >= 0 and top + field.winfo_height() <= canvas.winfo_height()
            prefix = f"search-projection-{dpi}-{index}"
            import json

            (out / f"{prefix}-geometry.json").write_text(
                json.dumps(
                    {
                        "window": canvas.coords(view._search_window),
                        "parent": canvas.coords(canvas._matte_backdrop.item),
                        "child": chrome.coords(chrome._matte_backdrop.item),
                        "field": [
                            field.winfo_x(),
                            field.winfo_y(),
                            field.winfo_width(),
                            field.winfo_height(),
                        ],
                        "chrome": [
                            chrome.winfo_x(),
                            chrome.winfo_y(),
                            chrome.winfo_width(),
                            chrome.winfo_height(),
                        ],
                        "parent_photo": str(canvas._matte_backdrop.photo),
                        "child_photo": str(chrome._matte_backdrop.photo),
                    },
                    indent=2,
                )
            )
            before = save_native_capture(canvas, out / f"{prefix}-before.png")
            scale = before.width / canvas.winfo_width()
            box = tuple(
                round(v * scale)
                for v in (x, top, x + field.winfo_width(), top + field.winfo_height())
            )
            visible = before.crop(box).convert("RGB")
            canvas.itemconfigure(view._search_window, state="hidden")
            pump(root)
            exposed = (
                save_native_capture(canvas, out / f"{prefix}-exposed.png")
                .crop(box)
                .convert("RGB")
            )
            canvas.itemconfigure(view._search_window, state="normal")
            pump(root)
            # Observe the actual displayed image on black/white backgrounds.
            # This supports both native nsimage and photo without regenerating
            # the material or relying on a producer-derived alpha oracle.
            sample = tk.Canvas(
                root,
                width=field.winfo_width(),
                height=field.winfo_height(),
                bd=0,
                highlightthickness=0,
                bg="#000000",
            )
            sample.place(x=0, y=0)
            sample.create_image(0, 0, anchor="nw", image=field._chrome._image)
            sample.tk.call("raise", str(sample))
            pump(root)
            black = save_native_capture(sample, out / f"{prefix}-black.png").convert(
                "RGB"
            )
            sample.configure(bg="#ffffff")
            pump(root)
            white = save_native_capture(sample, out / f"{prefix}-white.png").convert(
                "RGB"
            )
            sample.destroy()
            pump(root)
            transparent = ImageChops.difference(white, black)
            red, green, blue = transparent.split()
            minimum = ImageChops.darker(ImageChops.darker(red, green), blue)
            mask = minimum.point(lambda value: 255 if value == 255 else 0).filter(
                ImageFilter.MinFilter(3)
            )
            assert mask.size == visible.size and mask.getbbox() is not None
            # Existing native clipping evidence isolates a one-physical-pixel
            # perimeter fringe; interior transparent corners remain exact.
            mask.paste(0, (0, 0, mask.width, 1))
            mask.paste(0, (0, mask.height - 1, mask.width, mask.height))
            mask.paste(0, (0, 0, 1, mask.height))
            mask.paste(0, (mask.width - 1, 0, mask.width, mask.height))
            rgb_mask = Image.merge("RGB", (mask,) * 3)
            difference = ImageChops.multiply(
                ImageChops.difference(visible, exposed), rgb_mask
            )
            assert max(high for _, high in difference.getextrema()) <= 1
            chrome.itemconfigure("matte-decoration", state="hidden")
            pump(root)
            fault = (
                save_native_capture(canvas, out / f"{prefix}-fault.png")
                .crop(box)
                .convert("RGB")
            )
            delta = ImageChops.multiply(ImageChops.difference(fault, exposed), rgb_mask)
            detected.append(max(high for _, high in delta.getextrema()))
            chrome.itemconfigure("matte-decoration", state="normal")
            pump(root)
            restored = (
                save_native_capture(canvas, out / f"{prefix}-restored.png")
                .crop(box)
                .convert("RGB")
            )
            assert restored.tobytes() == visible.tobytes()
        assert max(detected) > 1, detected
        view._closed = True
        field.destroy()
        view._project_search_backdrop()
        pump(root)
    finally:
        root.destroy()
        THEME.clear()
        THEME.update(original)
        ui_theme._active_theme_name = original_name
