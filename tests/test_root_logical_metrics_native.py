"""Root integration for admitted window units; no physical-DPI claim."""

import os
import tkinter as tk
from itertools import combinations
from pathlib import Path

import pytest
from PIL import ImageTk

from tests.test_archive_native import pump
from tests.test_matte_native import save_native_capture
from tests.test_native_thumbnail_rendering import application as _application
from yt_downloader.ui_layout import install_window_logical_metrics
from yt_downloader.ui_theme import THEME

application = _application
pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="explicit native run required",
)


@pytest.fixture(params=[None, 192])
def metrics_application(request, monkeypatch):
    dpi = request.param
    original = tk.Tk.__init__

    def admitted_root(self, *args, **kwargs):
        original(self, *args, **kwargs)
        if dpi:
            install_window_logical_metrics(self, dpi=dpi)

    monkeypatch.setattr(tk.Tk, "__init__", admitted_root)
    return request.getfixturevalue("application"), dpi


def test_root_navigation_images_theme_and_header_bounds(metrics_application, tmp_path):
    app, dpi = metrics_application
    scale = 2 if dpi else 1
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    app._select_focus_view("forge")
    pump(app)
    icon = app._load_focus_icon("download", 20, THEME["icon"])
    assert (icon.width(), icon.height()) == (20 * scale, 20 * scale)
    from tests.test_native_thumbnail_rendering import pixels
    from yt_downloader.platform_services import surface_backing_scale

    if surface_backing_scale(app) > 1:
        assert app.tk.call("image", "type", str(icon)) == "nsimage"
    original = pixels(app, icon).tobytes()
    previous, incoming = (("icon", THEME["icon"]),), (("icon", "#335577"),)
    app._render_live_theme(previous, incoming)
    pump(app)
    assert app._load_focus_icon("download", 20, "#335577") is icon
    assert (icon.width(), icon.height()) == (20 * scale, 20 * scale)
    assert pixels(app, icon).tobytes() != original
    app._render_live_theme(incoming, previous)
    pump(app)
    assert pixels(app, icon).tobytes() == original
    for width, height in ((1180, 740), (900, 640)):
        app.geometry(f"{width}x{height}")
        pump(app)
        app._apply_focus_layout(force=True)
        pump(app)
        save_native_capture(app, out / f"root-{dpi or 'default'}-{width}.png")
        for button in app._focus_nav_buttons.values():
            assert button.winfo_ismapped()
            assert button.winfo_rootx() >= app.winfo_rootx()
            assert (
                button.winfo_rootx() + button.winfo_width()
                <= app.winfo_rootx() + app.winfo_width()
            )
            assert (
                button.winfo_rooty() + button.winfo_height()
                <= app.winfo_rooty() + app.winfo_height()
            )
        controls = [
            *app._focus_nav_buttons.values(),
            app._global_search_field,
            app.focus_settings_button,
        ]
        for left, right in combinations(controls, 2):
            assert (
                left.winfo_rootx() + left.winfo_width() <= right.winfo_rootx()
                or right.winfo_rootx() + right.winfo_width() <= left.winfo_rootx()
                or left.winfo_rooty() + left.winfo_height() <= right.winfo_rooty()
                or right.winfo_rooty() + right.winfo_height() <= left.winfo_rooty()
            ), (str(left), str(right), "header controls overlap")
    for name in ("library", "watch", "activity", "forge"):
        app._focus_nav_buttons[name].invoke()
        pump(app)
        assert app._focus_selected_view == name


def test_root_url_children_fit_visible_field(metrics_application, tmp_path):
    app, _dpi = metrics_application
    app._select_focus_view("forge")
    for width, height in ((1180, 740), (900, 640)):
        app.geometry(f"{width}x{height}")
        pump(app)
        app._apply_focus_layout(force=True)
        pump(app)
        box = app.focus_command_box
        for child in (
            app.focus_command_link_label,
            app.focus_url_entry,
            app.focus_output_type_selector,
        ):
            assert child.winfo_ismapped()
            assert child.winfo_height() >= child.winfo_reqheight(), str(child)
            assert child.winfo_rooty() >= box.winfo_rooty()
            assert (
                child.winfo_rooty() + child.winfo_height()
                <= box.winfo_rooty() + box.winfo_height()
            ), (str(child), "URL field clips its child")


@pytest.mark.parametrize("dpi", [None, 192])
def test_navigation_material_survives_style_reapplication(tmp_path, dpi):
    from tkinter import ttk

    from yt_downloader.ui_button_contract import ProductButton
    from yt_downloader.ui_styles import apply_product_styles

    root = tk.Tk()
    try:
        if dpi:
            install_window_logical_metrics(root, dpi=dpi)
        root.geometry("1200x250+40+40")
        root.configure(bg=THEME["bg"])
        apply_product_styles(root)
        controls = [
            ProductButton(root, text="Library", style=style)
            for style in (
                "FocusNav.TButton",
                "Archive.FocusNav.TButton",
                "Media.FocusNav.TButton",
                "FocusNavActive.TButton",
            )
        ]
        from yt_downloader.ui_layout import window_logical_metrics
        from yt_downloader.ui_theme import FONT_UI, FONT_UI_SMALL

        for control, font in zip(
            controls, (FONT_UI, FONT_UI_SMALL, FONT_UI, FONT_UI), strict=True
        ):
            control.pack(side="left", padx=8)
            actual_font = root.tk.splitlist(
                ttk.Style(root).lookup(control.cget("style"), "font")
            )
            assert int(actual_font[1]) == window_logical_metrics(root).font(font)[1]
        root.focus_force()
        pump(root)
        out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
        before = [
            save_native_capture(
                control, out / f"nav-reapply-{dpi or 'default'}-{i}-before.png"
            )
            for i, control in enumerate(controls)
        ]
        for repeat in range(2):
            apply_product_styles(root)
            pump(root)
            for i, control in enumerate(controls):
                actual = save_native_capture(
                    control, out / f"nav-reapply-{dpi or 'default'}-{i}-{repeat}.png"
                )
                assert actual.size == before[i].size
                assert actual.tobytes() == before[i].tobytes(), (
                    control.cget("style"),
                    "style reapplication changed resting material",
                )
                assert "Product.nav" in str(
                    ttk.Style(root).layout(control.cget("style"))
                ) or "Dpi2." in str(ttk.Style(root).layout(control.cget("style")))
        handles = set(root.tk.call("image", "names"))
        control = controls[0]
        control.state(["focus"])
        pump(root)
        focused = save_native_capture(
            control, out / f"nav-{dpi or 'default'}-focus.png"
        )
        assert focused.tobytes() != before[0].tobytes()
        control.state(["active"])
        pump(root)
        hovered = save_native_capture(
            control, out / f"nav-{dpi or 'default'}-focused-hover.png"
        )
        # Hover intentionally changes foreground text; compare the material
        # band above the glyphs, independently of that semantic color map.
        band = (0, 0, focused.width, focused.height // 5)
        assert hovered.crop(band).tobytes() == focused.crop(band).tobytes()
        control.state(["!focus", "!active"])
        from yt_downloader import ui_theme
        from yt_downloader.ui_theme import apply_theme_selection

        old_palette, old_name = dict(THEME), ui_theme._active_theme_name
        try:
            apply_theme_selection("Cobalt" if old_name != "Cobalt" else "Violet")
            apply_product_styles(root)
            pump(root)
            changed = save_native_capture(
                control, out / f"nav-{dpi or 'default'}-palette.png"
            )
            assert changed.tobytes() != before[0].tobytes()
        finally:
            THEME.clear()
            THEME.update(old_palette)
            ui_theme._active_theme_name = old_name
            apply_product_styles(root)
            pump(root)
        restored = save_native_capture(
            control, out / f"nav-{dpi or 'default'}-restored.png"
        )
        assert restored.tobytes() == before[0].tobytes()
        assert set(root.tk.call("image", "names")) == handles
    finally:
        root.destroy()


def test_root_forge_actions_remain_reachable_at_small_height(
    metrics_application, tmp_path
):
    app, dpi = metrics_application
    app.geometry("900x640")
    app._select_focus_view("forge")
    pump(app)
    app._apply_focus_layout(force=True)
    pump(app)
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    for name in (
        "focus_url_entry",
        "download_button",
        "load_url_list_button",
        "focus_destination_button",
        "local_audio_video_button",
        "focus_details_button",
    ):
        control = getattr(app, name)
        control.focus_force()
        pump(app)
        save_native_capture(app, out / f"forge-{dpi or 'default'}-{name}.png")
        assert control.winfo_ismapped(), name
        assert control.winfo_rooty() >= app.focus_view_stack.winfo_rooty(), name
        assert (
            control.winfo_rooty() + control.winfo_height()
            <= app.winfo_rooty() + app.winfo_height()
        ), name
        assert control.winfo_rootx() >= app.winfo_rootx(), name
        assert (
            control.winfo_rootx() + control.winfo_width()
            <= app.winfo_rootx() + app.winfo_width()
        ), name


def test_root_field_corners_preserve_parent_backdrop(metrics_application, tmp_path):
    """Compare transparent corners to the independently exposed parent pixels."""
    from PIL import Image, ImageChops, ImageFilter

    from yt_downloader import ui_theme
    from yt_downloader.ui_theme import apply_theme_selection, theme_palette_snapshot

    app, dpi = metrics_application
    app.geometry("1180x740")
    app._select_focus_view("forge")
    app.focus_force()
    pump(app)
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    original, original_name = dict(THEME), ui_theme._active_theme_name
    detected_faults = []
    clipping_observations = []
    app.focus_url_entry.configure(insertontime=0)
    try:
        cases = (
            ("Violet", 1180, "idle"),
            ("Cobalt", 900, "hover"),
            ("Cobalt", 1180, "focus"),
            ("Violet", 1180, "leave"),
        )
        for theme, width, state in cases:
            app.geometry(f"{width}x740")
            app.focus_force()
            app.focus_destination_button.event_generate("<Leave>")
            pump(app)
            previous = theme_palette_snapshot()
            apply_theme_selection(theme)
            app._render_live_theme(previous, theme_palette_snapshot())
            pump(app)
            for name in ("focus_command_box", "focus_destination_button"):
                control = getattr(app, name)
                if state == "focus":
                    (
                        app.focus_url_entry if name == "focus_command_box" else control
                    ).focus_force()
                elif state == "hover":
                    control.event_generate("<Enter>")
                pump(app)
                backdrop = control.master._matte_background_canvas
                before = save_native_capture(
                    control,
                    out
                    / f"corner-{dpi or 'default'}-{theme}-{width}-{state}-{name}.png",
                )
                app.tk.call("lower", str(control), str(backdrop))
                pump(app)
                background = save_native_capture(
                    control,
                    out
                    / f"background-{dpi or 'default'}-{theme}-{width}-{state}-{name}.png",
                )
                app.tk.call("raise", str(control), str(backdrop))
                pump(app)
                photo = (
                    app._command_field_material.image
                    if name == "focus_command_box"
                    else control._background_image
                )
                alpha = ImageTk.getimage(photo).getchannel("A")
                assert alpha.getpixel((0, 0)) == 0
                scale = before.width / alpha.width
                # Exclude the one physical pixel interpolation fringe: native
                # photo scaling can mix an adjacent nonzero alpha texel there.
                # Deep transparent corners must still match the parent exactly.
                empty = (
                    alpha.point(lambda a: 255 if a == 0 else 0)
                    .resize(before.size, resample=0)
                    .filter(ImageFilter.MinFilter(3))
                )
                # Native widget clipping can mix the last physical edge pixel
                # with its sibling. Measure that separately from the material.
                material_item = (
                    app._command_field_material.item
                    if name == "focus_command_box"
                    else control._background_item
                )
                control.itemconfigure(material_item, state="hidden")
                pump(app)
                bare = save_native_capture(
                    control,
                    out / f"bare-{dpi or 'default'}-{theme}-{width}-{state}-{name}.png",
                )
                control.itemconfigure(material_item, state="normal")
                pump(app)
                material_delta = ImageChops.difference(
                    before.convert("RGB"), bare.convert("RGB")
                )
                material_corners = ImageChops.multiply(
                    material_delta, Image.merge("RGB", (empty,) * 3)
                )
                assert max(high for _, high in material_corners.getextrema()) <= 1
                clipping_delta = ImageChops.difference(
                    bare.convert("RGB"), background.convert("RGB")
                )
                clipping_corners = ImageChops.multiply(
                    clipping_delta, Image.merge("RGB", (empty,) * 3)
                )
                clipping_observations.append(
                    {
                        "control": name,
                        "theme": theme,
                        "width": width,
                        "state": state,
                        "bare_widget_edge_max_rgb": max(
                            high for _, high in clipping_corners.getextrema()
                        ),
                    }
                )
                # One physical perimeter pixel is a native clipping fringe,
                # observed even with the material image hidden. Interior
                # transparent corners retain the stricter one-level bound.
                empty.paste(0, (0, 0, empty.width, 1))
                empty.paste(0, (0, empty.height - 1, empty.width, empty.height))
                empty.paste(0, (0, 0, 1, empty.height))
                empty.paste(0, (empty.width - 1, 0, empty.width, empty.height))
                difference = ImageChops.difference(
                    before.convert("RGB"), background.convert("RGB")
                )
                masked = ImageChops.multiply(
                    difference, Image.merge("RGB", (empty,) * 3)
                )
                assert max(high for _, high in masked.getextrema()) <= 1, (
                    name,
                    theme,
                    dpi,
                    "transparent corners erase parent backdrop",
                    scale,
                )
                control.itemconfigure("matte-decoration", state="hidden")
                pump(app)
                faulty = save_native_capture(
                    control,
                    out
                    / f"fault-{dpi or 'default'}-{theme}-{width}-{state}-{name}.png",
                )
                delta = ImageChops.difference(
                    faulty.convert("RGB"), background.convert("RGB")
                )
                fault_masked = ImageChops.multiply(
                    delta, Image.merge("RGB", (empty,) * 3)
                )
                detected_faults.append(
                    max(high for _, high in fault_masked.getextrema())
                )
                control.itemconfigure("matte-decoration", state="normal")
                pump(app)
                restored = save_native_capture(
                    control,
                    out
                    / f"restored-{dpi or 'default'}-{theme}-{width}-{state}-{name}.png",
                )
                assert restored.tobytes() == before.tobytes()
            save_native_capture(
                app,
                out / f"corners-root-{dpi or 'default'}-{theme}-{width}-{state}.png",
            )
        # Quiet artwork can legitimately equal the base color at one corner;
        # at least one actual textured target must detect the prior fault.
        assert max(detected_faults) > 1, (dpi, detected_faults)
        import json

        (out / f"corner-native-fringe-{dpi or 'default'}.json").write_text(
            json.dumps(
                {
                    "observations": clipping_observations,
                    "scope": "One physical widget perimeter pixel; measured even with material hidden. Interior corner and material contribution tolerance remain one RGB level.",
                    "fault_max_rgb": detected_faults,
                },
                indent=2,
            )
        )
    finally:
        previous = theme_palette_snapshot()
        THEME.clear()
        THEME.update(original)
        ui_theme._active_theme_name = original_name
        app._render_live_theme(previous, theme_palette_snapshot())
        pump(app)


def test_root_brand_marks_and_placeholder_use_window_and_backing_units(
    metrics_application, tmp_path
):
    from yt_downloader.platform_services import surface_backing_scale
    from yt_downloader.ui_layout import window_logical_metrics

    app, dpi = metrics_application
    # The hero is intentionally hidden below 720 canonical units.
    app.geometry("1480x900" if dpi else "1180x740")
    app._select_focus_view("forge")
    pump(app)
    metrics = window_logical_metrics(app)
    mark = app._focus_header_mark_label.cget("image")
    mark = app.tk.splitlist(mark)[0]
    assert int(app.tk.call("image", "width", mark)) == metrics.px(32)
    assert int(
        app.tk.call("image", "height", str(app._focus_header_name))
    ) == metrics.px(22)
    app._render_focus_thumbnail_surfaces()
    photo = app.focus_active_thumbnail_image
    assert int(app.tk.call("image", "width", str(photo))) == metrics.px(152)
    if surface_backing_scale(app) > 1:
        assert app.tk.call("image", "type", str(photo)) == "nsimage", (
            "Emblem is a low-resolution photo upscale"
        )
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    save_native_capture(
        app._focus_header_mark_label, out / f"brand-mark-{dpi or 'default'}.png"
    )
    save_native_capture(
        app.focus_active_thumbnail_label, out / f"brand-emblem-{dpi or 'default'}.png"
    )


def test_enlarged_forge_scroll_owns_focus_and_pointer_lifecycle(metrics_application):
    app, dpi = metrics_application
    surface = app._focus_forge_surface
    if not dpi:
        assert surface is None
        return
    from yt_downloader import ui_theme
    from yt_downloader.ui_theme import apply_theme_selection

    original, original_name = dict(THEME), ui_theme._active_theme_name
    try:
        for theme, size in (("Violet", "900x640"), ("Cobalt", "1180x640")):
            app.geometry(size)
            app._select_focus_view("forge")
            apply_theme_selection(theme)
            app._render_live_theme(tuple(original.items()), tuple(THEME.items()))
            pump(app)
            app._apply_focus_layout(force=True)
            pump(app)
            assert surface.scrollbar.winfo_ismapped()
            viewport = surface.viewport
            app.focus_settings_button.focus_force()
            pump(app)
            viewport.yview_moveto(0)
            assert app.focus_details_button.winfo_ismapped()
            app.focus_details_button.focus_force()
            pump(app)
            assert viewport.yview()[0] > 0
            assert surface.protected_content_is_visible(app.focus_details_button)
            scrolled = viewport.yview()
            app.focus_settings_button.focus_force()
            pump(app)
            assert viewport.yview() == scrolled, "unrelated header focus moved Forge"
            app.focus_url_entry.focus_force()
            pump(app)
            assert surface.protected_content_is_visible(app.focus_url_entry)
            before = viewport.yview()
            app.focus_url_entry.event_generate("<MouseWheel>", delta=-120)
            pump(app)
            assert viewport.yview()[0] > before[0], (
                "descendant wheel did not reach owner"
            )
            app._select_focus_view("library")
            app._select_focus_view("forge")
            pump(app)
            app.focus_details_button.focus_force()
            pump(app)
            assert surface.protected_content_is_visible(app.focus_details_button)
    finally:
        THEME.clear()
        THEME.update(original)
        ui_theme._active_theme_name = original_name


def test_forge_static_text_and_url_have_scaled_usable_allocation(metrics_application):
    import tkinter.font as tkfont
    from tkinter import ttk

    from yt_downloader.ui_layout import window_logical_metrics
    from yt_downloader.ui_theme import FONT_UI_FAMILY, FONT_UI_SMALL

    app, _dpi = metrics_application
    metrics = window_logical_metrics(app)
    app._select_focus_view("forge")
    for width, height in (
        (820, 560),
        (900, 640),
        (1180, 740),
        (1800, 1100),
        (820, 560),
    ):
        app.geometry(f"{width}x{height}")
        pump(app)
        app._apply_focus_layout(force=True)
        pump(app)
        for widget, role in (
            (app.focus_active_title_label, (FONT_UI_FAMILY, 15, "bold")),
            (app.focus_active_detail_label, FONT_UI_SMALL),
            (app.focus_summary_text, FONT_UI_SMALL),
        ):
            configured = widget.cget("font")
            if not configured:
                configured = ttk.Style(app).lookup(widget.cget("style"), "font")
            actual = tkfont.Font(root=app, font=configured)
            expected = tkfont.Font(root=app, font=metrics.font(role))
            assert actual.metrics("linespace") == expected.metrics("linespace"), str(
                widget
            )
        field = app.focus_url_entry
        font = tkfont.Font(root=app, font=field.cget("font"))
        assert field.winfo_width() >= font.measure("https://example"), (
            "URL editing area collapsed"
        )
        assert app.focus_destination_button.winfo_width() >= metrics.px(170)
        for left, right in combinations(
            (app.focus_command_box, app.focus_options_button, app.download_button), 2
        ):
            assert (
                left.winfo_rootx() + left.winfo_width() <= right.winfo_rootx()
                or right.winfo_rootx() + right.winfo_width() <= left.winfo_rootx()
                or left.winfo_rooty() + left.winfo_height() <= right.winfo_rooty()
                or right.winfo_rooty() + right.winfo_height() <= left.winfo_rooty()
            )

        for control in (
            app.load_url_list_button,
            app.focus_destination_button,
            app.local_audio_video_button,
        ):
            assert control.winfo_rootx() >= app.winfo_rootx()
            assert (
                control.winfo_rootx() + control.winfo_width()
                <= app.winfo_rootx() + app.winfo_width()
            ), str(control)


def test_run_deck_capacity_artwork_and_text_share_units(
    metrics_application, monkeypatch
):
    import tkinter.font as tkfont

    from PIL import Image

    from yt_downloader.platform_services import surface_backing_scale
    from yt_downloader.ui_layout import (
        focus_run_deck_capacity,
        thumbnail_size_within,
        window_logical_metrics,
    )
    from yt_downloader.ui_theme import FONT_UI_SMALL

    app, _dpi = metrics_application
    metrics = window_logical_metrics(app)
    app._select_focus_view("forge")
    records = [
        {
            "kind": "completed",
            "run_id": f"dpi-{i}",
            "title": f"DPI run {i}",
            "status": "Completed",
            "progress": 100,
        }
        for i in range(5)
    ]
    records[0]["preview_thumbnail_image"] = Image.new("RGBA", (180, 320), "#dc143c")
    projections, invoked = [], []
    monkeypatch.setattr(
        app, "_focus_run_records", lambda: projections.append(True) or records
    )
    monkeypatch.setattr(
        app,
        "_focus_activate_run_record",
        lambda record, event: invoked.append(record["run_id"]),
    )
    app._refresh_focus_run_deck()
    pump(app)
    projections.clear()
    for size in ("900x640", "1800x1100", "900x640"):
        app.geometry(size)
        pump(app)
        deck = app.focus_run_deck
        expected_capacity = focus_run_deck_capacity(deck.winfo_width() // metrics.scale)
        assert app._focus_run_deck_rendered_capacity == expected_capacity
        assert len(app._focus_run_thumbnail_images) == expected_capacity
        thumb_width = metrics.px(64 if app._focus_layout == "compact" else 80)
        maximum = (thumb_width, round(thumb_width * 9 / 16))
        for index, image in enumerate(app._focus_run_thumbnail_images):
            expected_size = (
                thumbnail_size_within((180, 320), maximum) if index == 0 else maximum
            )
            assert (image.width(), image.height()) == expected_size
            if surface_backing_scale(app) > 1:
                assert app.tk.call("image", "type", str(image)) == "nsimage"
        expected_font = tkfont.Font(root=app, font=metrics.font(FONT_UI_SMALL))
        for status, _bar in app._focus_run_deck_value_widgets:
            actual = tkfont.Font(root=app, font=status.cget("font"))
            assert actual.metrics("linespace") == expected_font.metrics("linespace")
            assert (
                status.winfo_rootx() + status.winfo_width()
                <= deck.winfo_rootx() + deck.winfo_width()
            )
    assert projections == [], "Geometry replayed history projection"
    app._focus_run_deck_value_widgets[0][0].event_generate("<Button-1>")
    pump(app)
    assert invoked == ["dpi-0"]
    records.clear()
    app._refresh_focus_run_deck()
    pump(app)
    description = next(
        child
        for frame in app.focus_run_deck.winfo_children()
        for child in frame.winfo_children()
        if str(child.cget("text")).startswith("Start with a URL")
    )
    assert int(description.cget("wraplength")) == description.winfo_width()
    assert description.winfo_height() >= description.winfo_reqheight()


def test_settings_content_scales_and_all_modes_fit_its_viewport(
    metrics_application, monkeypatch, tmp_path
):
    import tkinter.font as tkfont
    from tkinter import ttk

    from yt_downloader.models import OutputType
    from yt_downloader.ui_layout import window_logical_metrics
    from yt_downloader.ui_theme import FONT_UI
    from yt_downloader.ui_widgets import ChoiceDropdown, ProductEntry, SegmentedSelector

    app, dpi = metrics_application
    original = tk.Toplevel

    class AdmittedPopup(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if dpi:
                install_window_logical_metrics(self, dpi=dpi)

    monkeypatch.setattr(tk, "Toplevel", AdmittedPopup)
    app._show_focus_settings()
    dialog = app._focus_settings_dialog
    popup = dialog.popup
    metrics = window_logical_metrics(popup)

    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    pump(app)
    title = next(
        w
        for w in descendants(popup)
        if isinstance(w, ttk.Label) and w.cget("text") == "Forge settings"
    )
    expected = tkfont.Font(root=popup, font=metrics.font((FONT_UI[0], 18, "bold")))
    assert tkfont.Font(root=popup, font=title.cget("font")).metrics(
        "linespace"
    ) == expected.metrics("linespace")
    body, viewport = dialog.dialog_surface.body, dialog.dialog_surface.viewport
    done = next(
        w
        for w in descendants(dialog.dialog_surface.footer)
        if isinstance(w, ttk.Button) and w.cget("text") == "Done"
    )
    for width, height in (popup.minsize(), (1180, 900), popup.minsize()):
        popup.geometry(f"{width}x{height}")
        for mode in (OutputType.MP4, OutputType.MP3, OutputType.ORIGINAL):
            dialog.refresh_output_sections(mode)
            pump(app)
            for widget in descendants(body):
                if not widget.winfo_ismapped() or not isinstance(
                    widget, (ttk.Label, ChoiceDropdown, ProductEntry, SegmentedSelector)
                ):
                    continue
                assert widget.winfo_rootx() >= body.winfo_rootx(), str(widget)
                assert (
                    widget.winfo_rootx() + widget.winfo_width()
                    <= body.winfo_rootx() + body.winfo_width()
                ), (str(widget), widget.winfo_width(), body.winfo_width())
                if isinstance(widget, ttk.Label):
                    assert widget.winfo_height() >= widget.winfo_reqheight(), str(
                        widget
                    )
                    if not int(widget.cget("wraplength") or 0):
                        text = str(widget.cget("text"))
                        if text:
                            font = tkfont.Font(root=popup, font=widget.cget("font"))
                            assert (
                                max(font.measure(line) for line in text.splitlines())
                                <= widget.winfo_width()
                            ), (text, widget.winfo_width())
            before = done.winfo_rooty()
            viewport.yview_moveto(1)
            pump(app)
            assert viewport.yview()[1] == 1
            assert done.winfo_rooty() == before
            assert (
                done.winfo_rooty() + done.winfo_height()
                <= popup.winfo_rooty() + popup.winfo_height()
            )
            viewport.yview_moveto(0)
            pump(app)
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    save_native_capture(popup, out / f"settings-{dpi or 'default'}.png")
    if dpi:
        original_font = title.cget("font")
        title.configure(font=(FONT_UI[0], 18, "bold"))
        assert tkfont.Font(root=popup, font=title.cget("font")).metrics(
            "linespace"
        ) != expected.metrics("linespace")
        title.configure(font=original_font)
    done.invoke()
    pump(app)
    assert not popup.winfo_exists()
    assert app._focus_settings_dialog is None
