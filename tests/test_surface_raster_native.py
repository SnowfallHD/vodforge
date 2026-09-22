"""Native surface fidelity and ownership, independent of layout screenshots."""

from __future__ import annotations

import gc
import os
import sys
import tkinter as tk

import pytest
from PIL import Image, ImageChops, ImageStat, ImageTk

from tests.test_archive_native import application as _application
from tests.test_archive_native import pump
from yt_downloader import platform_services
from yt_downloader.ui_chrome import CanvasSurfaceCache, layered_surface_image
from yt_downloader.ui_theme import THEME

application = _application
pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="Mac native surface rendering required",
)


@pytest.mark.parametrize("selected", [False, True])
def test_retina_surface_preserves_regions_and_retires_native_name(
    application, selected
):
    from AppKit import NSImage

    app = application
    popup = tk.Toplevel(app)
    canvas = tk.Canvas(
        popup, width=320, height=210, bg=THEME["bg"], bd=0, highlightthickness=0
    )
    canvas.pack()
    popup.geometry("+120+100")
    pump(app)
    bitmap = layered_surface_image(
        280,
        170,
        fill=THEME["panel"],
        edge=THEME["accent"] if selected else THEME["border"],
        illumination=0.28 if selected else 0.07,
    )
    ordinary = ImageTk.PhotoImage(bitmap, master=canvas)
    item = canvas.create_image(20, 20, image=ordinary, anchor="nw")
    canvas.create_text(
        40,
        55,
        anchor="nw",
        text="Readable title 123",
        fill=THEME["text"],
        font=("Arial", 18),
    )
    pump(app)
    before = platform_services.capture_own_widget(canvas)
    native, size = platform_services.create_surface_image(canvas, bitmap, 2)
    assert canvas.tk.call("image", "type", str(native)) == "nsimage"
    name = canvas.tk.call(str(native), "cget", "-source")
    assert NSImage.imageNamed_(name) is None, "Temporary native name leaked"
    assert size >= 280 * 170 * 4 * 4
    canvas.itemconfigure(item, image=native)
    pump(app)
    after = platform_services.capture_own_widget(canvas)
    assert before is not None and after is not None
    difference = ImageChops.difference(before, after)
    assert max(ImageStat.Stat(difference).mean) < 1.0
    assert max(high for _low, high in difference.getextrema()) <= 32
    for region in [
        (20, 20, 50, 50),
        (20, 175, 50, 190),
        (25, 25, 295, 28),
        (50, 80, 270, 160),
        (38, 52, 240, 80),
    ]:
        assert max(ImageStat.Stat(difference.crop(region)).mean) < 2.0
    canvas.delete(item)
    image_name = str(native)
    del native
    gc.collect()
    assert image_name not in canvas.tk.call("image", "names")
    popup.destroy()


def test_surface_fallback_and_scale_change_keep_cache_bounded(application, monkeypatch):
    from yt_downloader import ui_chrome

    app = application
    canvas = tk.Canvas(app, width=320, height=210)
    owner = CanvasSurfaceCache(canvas)
    monkeypatch.setattr(ui_chrome, "surface_backing_scale", lambda _: 1)
    first = owner.draw((0, 0, 240, 160))
    first_name = canvas.itemcget(first, "image")
    assert canvas.tk.call("image", "type", first_name) == "photo"
    monkeypatch.setattr(ui_chrome, "surface_backing_scale", lambda _: 2)
    second = owner.draw((0, 0, 240, 160))
    second_name = canvas.itemcget(second, "image")
    assert first_name != second_name
    assert canvas.tk.call("image", "type", second_name) == "nsimage"
    assert owner.cached_bytes <= 8 * 1024 * 1024
    assert owner.bytes >= 240 * 160 * 4 * (1 + 4)
    owner.clear()
    gc.collect()
    assert first_name not in canvas.tk.call("image", "names")
    assert second_name not in canvas.tk.call("image", "names")
    canvas.destroy()


@pytest.mark.parametrize("selected", [False, True])
def test_surface_transport_compression_preserves_native_pixels(
    application, monkeypatch, tmp_path, selected
):
    """Compare actual native presentation with the old lossless transport."""
    import json
    from pathlib import Path

    app = application
    popup = tk.Toplevel(app)
    canvas = tk.Canvas(
        popup, width=320, height=210, bg=THEME["bg"], bd=0, highlightthickness=0
    )
    canvas.pack()
    popup.geometry("+120+100")
    pump(app)
    bitmap = layered_surface_image(
        280,
        170,
        fill=THEME["panel"],
        edge=THEME["accent"] if selected else THEME["border"],
        illumination=0.28 if selected else 0.07,
    )
    original_save = Image.Image.save

    def old_transport(image, fp, format=None, **params):
        if format == "PNG":
            params["compress_level"] = 6
        return original_save(image, fp, format=format, **params)

    try:
        with monkeypatch.context() as context:
            context.setattr(Image.Image, "save", old_transport)
            before_image, _ = platform_services.create_surface_image(canvas, bitmap, 2)
        item = canvas.create_image(20, 20, image=before_image, anchor="nw")
        canvas.create_text(
            40,
            55,
            text="Readable title 123",
            anchor="nw",
            fill=THEME["text"],
            font=("Arial", 18),
        )
        pump(app)
        before = platform_services.capture_own_widget(canvas)
        after_image, _ = platform_services.create_surface_image(canvas, bitmap, 2)
        assert canvas.tk.call("image", "type", str(before_image)) == "nsimage"
        assert canvas.tk.call("image", "type", str(after_image)) == "nsimage"
        canvas.itemconfigure(item, image=after_image)
        pump(app)
        after = platform_services.capture_own_widget(canvas)
        assert before is not None and after is not None
        difference = ImageChops.difference(before.convert("RGB"), after.convert("RGB"))
        output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        output.mkdir(parents=True, exist_ok=True)
        stem = "transport-selected" if selected else "transport-normal"
        before.save(output / (stem + "-before.png"))
        after.save(output / (stem + "-after.png"))
        (output / (stem + ".json")).write_text(
            json.dumps(
                {
                    "input": "same bitmap; old compression 6 versus current producer",
                    "native_types": ["nsimage", "nsimage"],
                    "difference_bbox": difference.getbbox(),
                    "max_channel_difference": max(
                        high for _low, high in difference.getextrema()
                    ),
                },
                indent=2,
            )
        )
        assert difference.getbbox() is None, "Lossless transport changed native pixels"
    finally:
        popup.destroy()


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("cover_bounds", [(90, 60, 190, 150), (170, 110, 295, 195)])
def test_partial_surface_repaint_preserves_interior_pixels(
    application, tmp_path, native, cover_bounds
):
    """A damaged subregion must not stretch its source across the whole image."""
    import json
    from pathlib import Path

    import Quartz
    from PIL import ImageDraw

    from yt_downloader.platforms.macos.windowing import _native_window

    app = application
    popup = tk.Toplevel(app)
    canvas = tk.Canvas(
        popup, width=320, height=230, bg=THEME["bg"], bd=0, highlightthickness=0
    )
    canvas.pack()
    popup.geometry("+120+100")
    bitmap = Image.new("RGB", (280, 180))
    draw = ImageDraw.Draw(bitmap)
    for y in range(0, 180, 30):
        for x in range(0, 280, 40):
            draw.rectangle(
                (x, y, x + 39, y + 29),
                fill=((x * 3) % 256, (y * 2) % 256, (x + y) % 256),
            )
    pump(app, 0.3)
    photo, _ = (
        platform_services.create_surface_image(canvas, bitmap, 2)
        if native
        else (ImageTk.PhotoImage(bitmap, master=canvas), 0)
    )
    image_type = canvas.tk.call("image", "type", str(photo))
    assert image_type == ("nsimage" if native else "photo"), image_type
    canvas.create_image(20, 20, image=photo, anchor="nw")
    pump(app, 0.3)
    number = int(_native_window(popup).windowNumber())
    bounds = dict(
        next(
            row["kCGWindowBounds"]
            for row in Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionIncludingWindow, number
            )
            if int(row["kCGWindowNumber"]) == number
        )
    )
    offset = (canvas.winfo_rootx() - bounds["X"], canvas.winfo_rooty() - bounds["Y"])

    def capture():
        raw = Quartz.CGWindowListCreateImage(
            Quartz.CGRectNull,
            Quartz.kCGWindowListOptionIncludingWindow,
            number,
            Quartz.kCGWindowImageBoundsIgnoreFraming
            | Quartz.kCGWindowImageNominalResolution,
        )
        assert raw is not None, "Own-window capture unavailable"
        profile = Quartz.CGColorSpaceCopyICCData(Quartz.CGImageGetColorSpace(raw))
        assert profile is not None, "Capture color profile unavailable"
        image = Image.frombytes(
            "RGB",
            (Quartz.CGImageGetWidth(raw), Quartz.CGImageGetHeight(raw)),
            bytes(Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(raw))),
            "raw",
            "BGRX",
            Quartz.CGImageGetBytesPerRow(raw),
        )
        return image, bytes(profile)

    try:
        before, profile = capture()
        cover = canvas.create_rectangle(*cover_bounds, fill="black", outline="")
        pump(app, 0.2)
        canvas.delete(cover)
        pump(app, 0.3)
        after, after_profile = capture()
        assert before.size == after.size and profile == after_profile
        difference = ImageChops.difference(before, after)
        left, top, right, bottom = cover_bounds
        # Flat source-cell interiors are independent of rounded/antialiased edges.
        # Their expected value is their own pre-damage presentation at the same point.
        centers = [
            (20 + x, 20 + y)
            for x in range(20, 280, 40)
            for y in range(15, 180, 30)
            if left + 3 < 20 + x < right - 3 and top + 3 < 20 + y < bottom - 3
        ]
        assert len(centers) >= 2
        patches = [
            (
                round(x + offset[0] - 2),
                round(y + offset[1] - 2),
                round(x + offset[0] + 3),
                round(y + offset[1] + 3),
            )
            for x, y in centers
        ]
        errors = [
            max(high for _low, high in difference.crop(box).getextrema())
            for box in patches
        ]
        output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path))) / (
            f"partial-surface-{'native' if native else 'photo'}-{left}-{top}"
        )
        output.mkdir(parents=True, exist_ok=True)
        before.save(output / "before.png")
        after.save(output / "after.png")
        (output / "receipt.json").write_text(
            json.dumps(
                {
                    "image_type": canvas.tk.call("image", "type", str(photo)),
                    "cover": cover_bounds,
                    "canvas_offset": offset,
                    "interior_patches": patches,
                    "max_channel_differences": errors,
                    "difference_bbox": difference.getbbox(),
                    "input": "Canvas overlay create/delete; own-window server capture",
                    "limits": "Static damage restoration, not continuous resize or physical input.",
                },
                indent=2,
            )
        )
        assert max(errors) <= 2, errors
    finally:
        popup.destroy()


def test_surface_frame_can_retire_after_its_canvas_is_destroyed(application):
    canvas = tk.Canvas(application)
    owner = CanvasSurfaceCache(canvas)
    owner.draw((0, 0, 240, 160))
    with owner.frame():
        canvas.destroy()
    owner.clear()
    assert owner.bytes == owner.cached_bytes == 0
    assert not owner._displayed_keys and not owner._frame_images


@pytest.mark.parametrize("scale", [1, 2])
@pytest.mark.parametrize("oversized", [False, True])
def test_deleted_surface_is_rebuilt_without_retaining_invalid_frame_image(
    application, monkeypatch, scale, oversized
):
    """Exercise real Tcl deletion for both reusable and frame-borrowed images."""
    from yt_downloader import ui_chrome

    app = application
    canvas = tk.Canvas(app, width=320, height=210)
    owner = CanvasSurfaceCache(canvas)
    monkeypatch.setattr(ui_chrome, "surface_backing_scale", lambda _: scale)
    bounds = (0, 0, 1600, 1400) if oversized else (0, 0, 240, 160)
    item = owner.draw(bounds, role="action-secondary")
    old_name = canvas.itemcget(item, "image")
    old_bytes = owner.bytes
    assert bool(owner.cached_bytes) is not oversized
    survivor = owner.draw((0, 0, 32, 32))
    survivor_name = canvas.itemcget(survivor, "image")
    app.tk.call("image", "delete", old_name)
    with owner.frame():
        canvas.delete("all")
        replacement = owner.draw(bounds, role="action-secondary")
        new_name = canvas.itemcget(replacement, "image")
        assert new_name != old_name
        assert new_name in canvas.tk.call("image", "names")
        again = owner.draw(bounds, role="action-secondary")
        assert canvas.itemcget(again, "image") == new_name
        preserved = owner.draw((0, 0, 32, 32))
        assert canvas.itemcget(preserved, "image") == survivor_name
    assert owner.builds == 3
    assert owner.bytes == old_bytes + owner._displayed[preserved][1]
    assert not owner._frame_images
    owner.clear()
    assert owner.bytes == owner.cached_bytes == 0
    assert new_name not in canvas.tk.call("image", "names")
    canvas.destroy()


def test_surface_reuse_does_not_hide_unrelated_canvas_errors(application, monkeypatch):
    app = application
    canvas = tk.Canvas(app, width=320, height=210)
    owner = CanvasSurfaceCache(canvas)
    bounds = (0, 0, 240, 160)
    item = owner.draw(bounds)
    name = canvas.itemcget(item, "image")

    def fail(*args, **kwargs):
        raise tk.TclError("unrelated canvas failure")

    monkeypatch.setattr(canvas, "create_image", fail)
    with pytest.raises(tk.TclError, match="unrelated canvas failure"):
        owner.draw(bounds)
    assert owner.builds == 1
    assert name in canvas.tk.call("image", "names")
    owner.clear()
    canvas.destroy()
