"""One conversion boundary for fixed-DPI prototype geometry, fonts and raster."""

from types import SimpleNamespace

import pytest
from PIL import ImageChops

from yt_downloader.ui_chrome import field_border_image
from yt_downloader.ui_layout import (
    WindowLogicalMetrics,
    install_window_logical_metrics,
    window_logical_metrics,
)


def test_default_window_keeps_font_and_geometry():
    window = SimpleNamespace()
    child = SimpleNamespace(winfo_toplevel=lambda: window)
    metrics = window_logical_metrics(child)
    assert metrics.px(34) == 34
    assert metrics.font(("Segoe UI", 11, "bold")) == ("Segoe UI", 11, "bold")


@pytest.mark.parametrize("scale", [1, 2])
def test_timeline_pointer_fraction_uses_scaled_insets_only(scale):
    from yt_downloader.media_player_ui import MediaPlayerWindow

    window = SimpleNamespace(
        _vodforge_logical_metrics=WindowLogicalMetrics(scale, physical_fonts=True)
    )
    seeks, features = [], []
    state = SimpleNamespace(
        timeline=SimpleNamespace(
            winfo_toplevel=lambda: window, winfo_width=lambda: 400
        ),
        _media_intent_current=lambda: True,
        playback=SimpleNamespace(snapshot=SimpleNamespace(duration=200)),
        _seek_to=seeks.append,
        _heatmap=[object()],
        _on_feature=features.append,
    )
    for x in (10 * scale, 200, 400 - 10 * scale):
        MediaPlayerWindow._timeline_clicked(state, SimpleNamespace(x=x, y=0))
    assert seeks == [0, 100, 200]
    assert features == ["heatmap"] * 3
    state._media_intent_current = lambda: False
    MediaPlayerWindow._timeline_clicked(state, SimpleNamespace(x=200, y=0))
    assert seeks == [0, 100, 200]


def test_physical_font_is_independent_of_interpreter_point_scaling():
    metrics = WindowLogicalMetrics(2, physical_fonts=True)
    assert metrics.px(34) == 68
    assert metrics.font(("Segoe UI", 12)) == ("Segoe UI", -32)
    assert metrics.font(("Segoe UI", -16)) == ("Segoe UI", -32)


@pytest.mark.parametrize("dpi,children", [(144, []), (0, []), (192, [object()])])
def test_reject_unsupported_context_or_late_install(dpi, children):
    window = SimpleNamespace(winfo_children=lambda: children)
    with pytest.raises(ValueError):
        install_window_logical_metrics(window, dpi=dpi)
    assert not hasattr(window, "_vodforge_logical_metrics")


@pytest.mark.parametrize("focused", [False, True])
def test_physical_chrome_matches_native_density_rendering_and_detects_unscaled_edges(
    focused,
):
    expected = field_border_image(240, 34, density=2, focused=focused)
    actual = field_border_image(480, 68, unit_scale=2, focused=focused)
    assert actual.size == (480, 68)
    assert (
        ImageChops.difference(actual.convert("RGB"), expected.convert("RGB")).getbbox()
        is None
    )
    assert (
        ImageChops.difference(
            actual.getchannel("A"), expected.getchannel("A")
        ).getbbox()
        is None
    )
    color_only = actual.copy()
    x, y = actual.width // 2, actual.height // 2
    red, green, blue, alpha = color_only.getpixel((x, y))
    color_only.putpixel((x, y), ((red + 1) % 256, green, blue, alpha))
    assert (
        ImageChops.difference(
            actual.getchannel("A"), color_only.getchannel("A")
        ).getbbox()
        is None
    )
    assert (
        ImageChops.difference(
            actual.convert("RGB"), color_only.convert("RGB")
        ).getbbox()
        is not None
    )
    wrong = field_border_image(480, 68, focused=focused)
    assert ImageChops.difference(actual, wrong).convert("RGB").getbbox() is not None


@pytest.mark.parametrize(
    "scale,expected",
    [
        (1, "500x300+650+650"),
        (2, "1000x600+400+500"),
    ],
)
def test_dialog_dimensions_convert_once_but_measured_owner_bounds_do_not(
    scale, expected
):
    from yt_downloader.ui_layout import centered_toplevel_geometry

    owner = SimpleNamespace(
        _vodforge_logical_metrics=WindowLogicalMetrics(scale, physical_fonts=True),
        winfo_rootx=lambda: 100,
        winfo_rooty=lambda: 200,
        winfo_width=lambda: 1600,
        winfo_height=lambda: 1200,
    )
    owner.winfo_toplevel = lambda: owner
    assert centered_toplevel_geometry(owner, 500, 300) == expected


def test_measured_dialog_content_height_is_not_scaled_twice():
    from yt_downloader.ui_layout import centered_toplevel_geometry

    owner = SimpleNamespace(
        _vodforge_logical_metrics=WindowLogicalMetrics(2, physical_fonts=True),
        winfo_rootx=lambda: 100,
        winfo_rooty=lambda: 200,
        winfo_width=lambda: 1600,
        winfo_height=lambda: 1200,
    )
    owner.winfo_toplevel = lambda: owner
    assert (
        centered_toplevel_geometry(owner, 500, 300, height_is_measured=True)
        == "1000x300+400+650"
    )


@pytest.mark.parametrize("owner_scale", [1, 2])
@pytest.mark.parametrize(
    "target_scale,expected", [(1, "500x300+280+260"), (2, "776x552+4+8")]
)
def test_dialog_target_owns_units_and_screen_bounds(
    owner_scale, target_scale, expected
):
    from yt_downloader.ui_layout import centered_toplevel_geometry

    owner = SimpleNamespace(
        _vodforge_logical_metrics=WindowLogicalMetrics(
            owner_scale, physical_fonts=True
        ),
        winfo_rootx=lambda: 100,
        winfo_rooty=lambda: 200,
        winfo_width=lambda: 1600,
        winfo_height=lambda: 1200,
    )
    owner.winfo_toplevel = lambda: owner
    target = SimpleNamespace(
        _vodforge_logical_metrics=WindowLogicalMetrics(
            target_scale, physical_fonts=True
        ),
        winfo_screenwidth=lambda: 800,
        winfo_screenheight=lambda: 600,
    )
    target.winfo_toplevel = lambda: target
    assert centered_toplevel_geometry(owner, 500, 300, target=target) == expected
    measured = centered_toplevel_geometry(
        owner, 500, 300, target=target, height_is_measured=True
    )
    assert measured.split("x")[1].split("+")[0] == "300"
