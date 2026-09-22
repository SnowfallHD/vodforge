"""Headless image contracts for the actual root loader and live-theme owner."""

from types import SimpleNamespace

import pytest

from yt_downloader import app as module
from yt_downloader.ui_layout import WindowLogicalMetrics


@pytest.mark.parametrize("scale", [1, 2])
@pytest.mark.parametrize("density", [1, 2])
@pytest.mark.parametrize("name,size", [("folder", 18), ("download", 20)])
def test_root_icons_keep_units_and_identity_across_theme(
    scale, density, name, size, monkeypatch
):
    class Photo:
        def __init__(self, bitmap):
            self.bitmap = bitmap.copy()
            self.pastes = 0

        def paste(self, bitmap):
            assert bitmap.size == self.bitmap.size, (
                "Theme recolor changed the image's unit boundary"
            )
            self.bitmap = bitmap.copy()
            self.pastes += 1

    captures = []

    def surface(owner, bitmap, backing, *, logical_size, existing=None):
        captures.append((bitmap.size, backing, logical_size))
        if existing is not None:
            existing.paste(bitmap)
            return existing, 0
        return Photo(bitmap), 0

    monkeypatch.setattr(module, "surface_backing_scale", lambda owner: density)
    monkeypatch.setattr(module, "create_surface_image", surface)
    monkeypatch.setattr(module, "patch_tk_surface_palette", lambda *args: None)
    owner = SimpleNamespace(
        _vodforge_logical_metrics=WindowLogicalMetrics(scale, physical_fonts=True),
        _focus_icon_images={},
        _apply_theme=lambda: None,
    )
    owner.winfo_toplevel = lambda: owner
    old_color, new_color = "#aabbcc", "#ccbbaa"
    image = module.DownloaderApp._load_focus_icon(owner, name, size, old_color)
    assert image is not None
    assert image.bitmap.size == (size * scale * density, size * scale * density)
    assert image.bitmap.getchannel("A").getbbox() is not None
    assert module.DownloaderApp._load_focus_icon(owner, name, size, old_color) is image
    source_path = module.bundled_asset_path(
        f"icons/lucide/{name}-{size * scale * density}.png"
    )
    if not source_path.is_file():
        source_path = module.bundled_asset_path(f"icons/lucide/{name}.png")
    with module.Image.open(source_path) as source:
        expected = module.render_monochrome_icon(
            source, size * scale * density, old_color
        )
    assert image.bitmap.tobytes() == expected.tobytes()
    before = image.bitmap.tobytes()
    module.DownloaderApp._render_live_theme(
        owner, (("icon", old_color),), (("icon", new_color),)
    )
    assert image.pastes == 1
    assert image.bitmap.size == (size * scale * density, size * scale * density)
    assert image.bitmap.tobytes() != before
    assert owner._focus_icon_images == {(name, size, new_color): image}
    assert module.DownloaderApp._load_focus_icon(owner, name, size, new_color) is image
    module.DownloaderApp._render_live_theme(
        owner, (("icon", new_color),), (("icon", old_color),)
    )
    assert image.bitmap.tobytes() == before
    assert image.pastes == 2
    assert (
        captures
        == [
            (
                (size * scale * density, size * scale * density),
                density,
                (size * scale, size * scale),
            )
        ]
        * 3
    )


@pytest.mark.parametrize("scale", [1, 2])
@pytest.mark.parametrize("integrated", [False, True])
def test_root_header_breakpoint_and_spacing_share_control_units(scale, integrated):
    class Label:
        def __init__(self):
            self.mapped = True

        def pack(self, **kwargs):
            self.mapped = True

        def pack_forget(self):
            self.mapped = False

    label = Label()
    compact_events, pads = [], []
    owner = SimpleNamespace(
        _vodforge_logical_metrics=WindowLogicalMetrics(scale, physical_fonts=True),
        _integrated_header=integrated,
        _focus_header_compact=None,
        _focus_brand_labels=[label],
        _global_search_field=SimpleNamespace(
            set_compact=compact_events.append,
            master=SimpleNamespace(
                winfo_reqwidth=lambda: 100, grid_configure=lambda **kwargs: None
            ),
        ),
        _focus_header_mark_label=SimpleNamespace(
            master=SimpleNamespace(winfo_reqwidth=lambda: 40)
        ),
        _focus_nav_row=SimpleNamespace(
            winfo_reqwidth=lambda: 200,
            grid_configure=lambda **kwargs: (
                pads.append(kwargs["padx"]) if "padx" in kwargs else None
            ),
        ),
    )
    owner.winfo_toplevel = lambda: owner
    boundary = (1100 if integrated else 1000) * scale
    module.DownloaderApp._layout_focus_header(owner, boundary - 1)
    assert compact_events == [True] and not label.mapped
    assert pads == [(8 * scale, 8 * scale)]
    module.DownloaderApp._layout_focus_header(owner, boundary - 2)
    assert len(compact_events) == 1
    module.DownloaderApp._layout_focus_header(owner, boundary)
    assert compact_events == [True, False] and label.mapped
    assert pads[-1] == (20 * scale, 12 * scale)


@pytest.mark.parametrize("density", [1, 2])
@pytest.mark.parametrize("placeholder", [False, True])
@pytest.mark.parametrize(
    "source_size,fitted",
    [((1024, 1024), (45, 45)), ((320, 180), (80, 45)), ((180, 320), (25, 45))],
)
def test_run_artwork_uses_backing_pixels_without_rescaling_measured_bounds(
    density, placeholder, source_size, fitted, monkeypatch
):
    source = module.Image.new("RGBA", source_size, "#8844aa")
    captures = []
    monkeypatch.setattr(module, "surface_backing_scale", lambda owner: density)

    def capture(owner, bitmap, scale, *, logical_size):
        captures.append((bitmap.size, scale, logical_size))
        return "owned-image", 0

    monkeypatch.setattr(module, "create_surface_image", capture)
    owner = SimpleNamespace(
        _focus_brand_source_image=source if placeholder else None,
        _focus_thumbnail_source_image=None,
        _focus_active_thumbnail_source_image=None,
    )
    assert (
        module.DownloaderApp._focus_photo_from_source(owner, source, (80, 45), 7)
        == "owned-image"
    )
    logical = (80, 45) if placeholder else fitted
    assert captures == [(tuple(value * density for value in logical), density, logical)]
