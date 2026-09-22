"""Mac physical field backing; separate from Windows logical-unit scaling."""

from __future__ import annotations

import json
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pytest

from yt_downloader import ui_chrome
from yt_downloader.platforms.macos.surfaces import _bitmap_rep_image
from yt_downloader.platforms.macos.windowing import _native_window
from yt_downloader.ui_theme import THEME

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="actual Mac native display required",
)


def physical_capture(root):
    view = _native_window(root).contentView()
    bounds = view.bounds()
    rep = view.bitmapImageRepForCachingDisplayInRect_(bounds)
    view.cacheDisplayInRect_toBitmapImageRep_(bounds, rep)
    return _bitmap_rep_image(rep)


def assert_physical_focus(idle, active, restored):
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

    width, height = idle.size
    changed = ImageChops.difference(idle.convert("RGB"), active.convert("RGB"))
    allowed = Image.new("L", idle.size)
    draw = ImageDraw.Draw(allowed)
    # Independent 10-logical-pixel radius and 5-logical-pixel contour allowance,
    # including antialias support. Interior and clipped corners cannot change.
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=20, fill=255)
    # Two logical pixels of finite antialias support, matching the independent
    # 1x contour oracle; a hard rectangular corner remains outside this mask.
    allowed = allowed.filter(ImageFilter.MaxFilter(9))
    draw = ImageDraw.Draw(allowed)
    draw.rounded_rectangle((10, 10, width - 11, height - 11), radius=10, fill=0)
    assert changed.getbbox(), "Missing focus"
    assert (
        ImageChops.multiply(changed, ImageOps.invert(allowed).convert("RGB")).getbbox()
        is None
    ), "Focus escaped rounded contour"
    assert (
        ImageChops.difference(idle.convert("RGB"), restored.convert("RGB")).getbbox()
        is None
    ), "Stale focus"


@pytest.fixture
def field_payloads(monkeypatch):
    actual = ui_chrome.create_surface_image
    observed = []

    def checked(widget, bitmap, scale, *, logical_size, existing=None):
        expected = tuple(dimension * scale for dimension in logical_size)
        assert bitmap.size == expected, (
            "Low-resolution payload would be upscaled by native transport"
        )
        assert bitmap.mode == "RGBA"
        assert bitmap.getpixel((0, 0))[3] < 255, "Field lost rounded alpha clipping"
        assert bitmap.getpixel((bitmap.width // 2, bitmap.height // 2))[3] == 255
        observed.append(
            {
                "physical": list(bitmap.size),
                "logical": list(logical_size),
                "scale": scale,
            }
        )
        return actual(
            widget, bitmap, scale, logical_size=logical_size, existing=existing
        )

    monkeypatch.setattr(ui_chrome, "create_surface_image", checked)
    return observed


def test_field_retina_pixels_keep_logical_geometry_and_live_handle(
    tmp_path, monkeypatch, field_payloads
):
    root = tk.Tk()
    root.geometry("360x150+50+60")
    root.configure(bg=THEME["bg"])
    try:
        field = tk.Frame(root, width=280, height=42, bg=THEME["bg"])
        field.place(x=40, y=40, width=280, height=42)
        root.update()
        assert ui_chrome.surface_backing_scale(field) == 2, (
            "This receipt requires actual Retina backing"
        )
        chrome = ui_chrome.RoundedFieldBorder(field)
        chrome.request()
        root.update()
        photo = chrome._image
        name = str(photo)
        baseline_commands = set(root.tk.call("info", "commands"))
        baseline_images = set(root.tk.call("image", "names"))
        idle = physical_capture(root)
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        idle.save(out / "field-idle-physical.png")
        idle.resize((360, 150)).save(out / "field-idle-logical.png")
        details = {
            "logical": [field.winfo_width(), field.winfo_height()],
            "physical_capture": list(idle.size),
            "image_type": root.tk.call("image", "type", name),
        }
        (out / "field-density.json").write_text(json.dumps(details, indent=2))
        assert details["image_type"] == "nsimage", (
            "Retina field still uses a low-density photo backing"
        )
        captures = []
        for state in ((True, False), (False, True), (False, False)):
            chrome.request(*state)
            root.update()
            captures.append(physical_capture(root))
            assert chrome._image is photo and str(chrome._image) == name
            assert set(root.tk.call("info", "commands")) == baseline_commands
            assert set(root.tk.call("image", "names")) == baseline_images
        restored = physical_capture(root)
        from PIL import ImageChops, ImageDraw

        box = (80, 80, 640, 164)
        baseline, focused, final = (
            idle.crop(box),
            captures[0].crop(box),
            restored.crop(box),
        )
        captures[0].save(out / "field-focused-physical.png")
        baseline.save(out / "field-idle-crop.png")
        focused.save(out / "field-focus-crop.png")
        assert_physical_focus(baseline, focused, final)
        assert ImageChops.difference(
            idle.convert("RGB"), captures[1].convert("RGB")
        ).getbbox()
        rectangle = focused.copy()
        ImageDraw.Draw(rectangle).rectangle((0, 0, 559, 83), outline="#ffffff", width=2)
        for active, after in (
            (baseline, final),
            (focused, focused),
            (rectangle, final),
        ):
            with pytest.raises(AssertionError):
                assert_physical_focus(baseline, active, after)
        old_surface = THEME["surface"]
        try:
            THEME["surface"] = "#624155"
            chrome.request()
            root.update()
            assert chrome._image is photo
            assert ImageChops.difference(
                idle.convert("RGB"), physical_capture(root).convert("RGB")
            ).getbbox()
        finally:
            THEME["surface"] = old_surface
            chrome.request()
            root.update()
        assert (
            ImageChops.difference(
                idle.convert("RGB"), physical_capture(root).convert("RGB")
            ).getbbox()
            is None
        )
        # Actual producer mutation: a nominally Retina native image must not
        # silently upscale a 1x field bitmap at the transport boundary.
        original_recipe = ui_chrome.field_border_image

        def low_resolution(*args, **kwargs):
            kwargs["density"] = 1
            return original_recipe(*args, **kwargs)

        with monkeypatch.context() as fault:
            fault.setattr(ui_chrome, "field_border_image", low_resolution)
            with pytest.raises(AssertionError, match="Low-resolution payload"):
                chrome.request(True)
        chrome.request(False)
        assert field_payloads and all(row["scale"] == 2 for row in field_payloads)
        (out / "field-payloads.json").write_text(json.dumps(field_payloads, indent=2))
        field.place_configure(width=300, height=48)
        root.update()
        assert chrome._image is photo and (photo.width(), photo.height()) == (300, 48)
        assert set(root.tk.call("image", "names")) == baseline_images
        field.destroy()
        del photo
        root.update()
        assert name not in root.tk.call("image", "names")
    finally:
        root.destroy()


def test_ttk_field_retina_slice_handles_survive_theme_and_resize(
    tmp_path, field_payloads
):
    root = tk.Tk()
    root.geometry("360x150+50+60")
    root.configure(bg=THEME["bg"])
    previous = dict(THEME)
    try:
        from yt_downloader.ui_styles import apply_product_styles

        # The real app installs styles before mapping its first native window.
        apply_product_styles(root)
        owner = root._product_chrome_owner
        entry = ttk.Entry(root, style="Product.TEntry", takefocus=False)
        entry.place(x=40, y=40, width=280, height=42)
        root.update()
        handles = {key: str(owner.images[key]) for key in ("field", "field_focus")}
        assert all(
            root.tk.call("image", "type", value) == "nsimage"
            for value in handles.values()
        )
        assert all(
            (owner.images[key].width(), owner.images[key].height()) == (28, 28)
            for key in handles
        )
        names = set(root.tk.call("image", "names"))
        before = physical_capture(root)
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        before.save(out / "ttk-field-idle-physical.png")
        for _ in range(4):
            THEME["surface"] = "#624155"
            apply_product_styles(root)
            root.update()
            from PIL import ImageChops

            assert ImageChops.difference(
                before.convert("RGB"), physical_capture(root).convert("RGB")
            ).getbbox()
            THEME.clear()
            THEME.update(previous)
            apply_product_styles(root)
            root.update()
            assert {key: str(owner.images[key]) for key in handles} == handles
            assert set(root.tk.call("image", "names")) == names
        entry.place_configure(width=300)
        root.update()
        assert entry.winfo_width() == 300
        assert {key: str(owner.images[key]) for key in handles} == handles
    finally:
        THEME.clear()
        THEME.update(previous)
        root.destroy()
