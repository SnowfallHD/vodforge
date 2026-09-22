"""Live all-theme/all-tab probes, independent of the renderer's declared status."""

import os
import sys
from pathlib import Path

import pytest
from PIL import ImageTk

from tests.test_archive_native import application as _application
from tests.test_archive_native import pump, seed
from yt_downloader.ui_theme import THEME, THEME_NAMES, theme_palette_snapshot

application = _application
pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="Mac native display required",
)


def save_native_capture(widget, path):
    """Preserve physical pixels independently from the logical preview helper."""
    import json

    from yt_downloader.platforms.macos.surfaces import _bitmap_rep_image
    from yt_downloader.platforms.macos.windowing import _native_window

    root = widget.winfo_toplevel()
    native = _native_window(root)
    view = native.contentView()
    bounds = view.bounds()
    rep = view.bitmapImageRepForCachingDisplayInRect_(bounds)
    view.cacheDisplayInRect_toBitmapImageRep_(bounds, rep)
    bitmap = _bitmap_rep_image(rep)
    sx, sy = bitmap.width / bounds.size.width, bitmap.height / bounds.size.height
    x, y = (
        widget.winfo_rootx() - root.winfo_rootx(),
        widget.winfo_rooty() - root.winfo_rooty(),
    )
    capture = bitmap.crop(
        (
            round(x * sx),
            round(y * sy),
            round((x + widget.winfo_width()) * sx),
            round((y + widget.winfo_height()) * sy),
        )
    )
    capture.save(path)
    path.with_suffix(".json").write_text(
        json.dumps(
            {
                "logical_size": [widget.winfo_width(), widget.winfo_height()],
                "physical_size": list(capture.size),
                "capture_scale": [sx, sy],
                "window_backing_scale": float(native.backingScaleFactor()),
                "resampled": False,
                "capture": "NSView bitmapImageRepForCachingDisplayInRect; own app view only",
            },
            indent=2,
        )
        + "\n"
    )
    if widget is root:
        capture.crop((0, 0, min(capture.width, 1400), min(capture.height, 440))).save(
            path.with_name(path.stem + "-detail.png")
        )
    return capture


def test_all_theme_tabs_and_open_settings_refresh(application, tmp_path, monkeypatch):
    from yt_downloader.platform_services import capture_own_widget

    app = application
    from yt_downloader.settings_store import load_settings

    app.settings_persistence.path = tmp_path / "matte-settings.json"
    changes = []
    monkeypatch.setattr(
        app.product_telemetry,
        "record_feature",
        lambda feature, action, **kwargs: changes.append((feature, action, kwargs)),
    )
    seed(app, tmp_path, count=1)
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    out.mkdir(parents=True, exist_ok=True)
    hashes = set()
    app.geometry("1200x760+80+80")
    for name in THEME_NAMES:
        app.appearance_theme_var.set(name)
        app.custom_accent_var.set("#ba9850")
        app._request_live_theme()
        pump(app, 0.15)
        app.settings_persistence.flush()
        persisted = load_settings(app.settings_persistence.path)
        assert persisted["appearance_theme"] == name
        assert persisted["custom_accent"] == "#ba9850"
        hashes.add(
            save_native_capture(
                app._focus_header_mark_label,
                out / (name.replace(" ", "-") + "-mark-native.png"),
            ).tobytes()
        )
        for tab in ("forge", "library", "watch", "activity"):
            app._select_focus_view(tab)
            pump(app, 0.7)
            assert app._view_transition._overlay is None
            assert app._focus_views[tab].winfo_ismapped()
            assert app._focus_header_mark_label.winfo_ismapped()
            capture = capture_own_widget(app)
            assert capture is not None
            capture.save(out / (name.replace(" ", "-") + "-" + tab + ".png"))
            save_native_capture(
                app, out / (name.replace(" ", "-") + "-" + tab + "-native.png")
            )
        for canvas in (app.library_scene.canvas, app.focus_watch.canvas):
            owner = canvas._matte_backdrop
            assert owner.identity == theme_palette_snapshot()
            assert len(canvas.find_withtag("matte-decoration")) == 1
            builds = owner.builds
            photo = owner.photo
            for width in range(720, 1000, 20):
                canvas.event_generate("<Configure>", width=width, height=500)
            assert owner.builds == builds
            assert owner.photo is photo
        app._show_focus_settings()
        pump(app, 0.15)
        dialog = app._focus_settings_dialog
        assert dialog is not None
        assert dialog.pro_button.winfo_exists()
        capture = capture_own_widget(dialog.popup)
        assert capture is not None
        capture.save(out / (name.replace(" ", "-") + "-settings.png"))
        save_native_capture(
            dialog.popup, out / (name.replace(" ", "-") + "-settings-native.png")
        )
        dialog.close()
        pump(app, 0.15)
    assert len(hashes) == len(THEME_NAMES)
    assert (
        len([entry for entry in changes if entry[:2] == ("appearance", "changed")])
        == len(THEME_NAMES) - 1
    )
    app.appearance_theme_var.set("Violet")
    app._request_live_theme()


def test_shared_control_states_and_runtime_defaults(application, tmp_path):
    import tkinter as tk
    from tkinter import ttk

    from yt_downloader.media_player_ui import PlayerTransportButton, PlayerVolumeControl
    from yt_downloader.platform_services import capture_own_widget
    from yt_downloader.ui_button_contract import ProductButton
    from yt_downloader.ui_widgets import (
        ChoiceDropdown,
        ModernCheckbox,
        ProductEntry,
        RoundedIconButton,
        SegmentedSelector,
        SleekProgressbar,
        SleekScrollbar,
    )

    app = application
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    out.mkdir(parents=True, exist_ok=True)
    for name in THEME_NAMES:
        app.appearance_theme_var.set(name)
        app._request_live_theme()
        popup = tk.Toplevel(app)
        popup.title("Shared matte controls")
        popup.geometry("820x490+160+130")
        popup.configure(bg=THEME["bg"])
        frame = ttk.Frame(popup, padding=28)
        frame.pack(fill="both", expand=True)
        calls = []
        buttons = []
        for i, (label, state) in enumerate(
            [
                ("Primary", ()),
                ("Hover", ("active",)),
                ("Pressed", ("pressed",)),
                ("Focus", ("focus",)),
                ("Disabled", ("disabled",)),
            ]
        ):
            button = ProductButton(
                frame,
                text=label,
                style="Accent.TButton",
                command=lambda calls=calls: calls.append(1),
            )
            button.grid(row=0, column=i, padx=4, pady=12)
            button.state(state)
            buttons.append(button)
        entry = ProductEntry(frame)
        entry.insert(0, "Recessed field")
        entry.grid(row=1, column=0, columnspan=3, sticky="ew", pady=12)
        choice = ChoiceDropdown(
            frame,
            textvariable=tk.StringVar(popup, "MP4"),
            values=("MP4", "MP3"),
            width=12,
        )
        choice.grid(row=1, column=3, columnspan=2, padx=8)
        flag = tk.BooleanVar(popup, True)
        check = ModernCheckbox(frame, text="Selected", variable=flag)
        check.grid(row=2, column=0, columnspan=2, sticky="w", pady=12)
        segment = SegmentedSelector(frame, variable=tk.StringVar(popup, "MP4"))
        segment.grid(row=2, column=2, columnspan=2)
        assert segment._background == THEME["surface"]
        scroll = SleekScrollbar(frame, command=lambda *a: None, orient="horizontal")
        scroll.grid(row=3, column=0, columnspan=5, sticky="ew", pady=12)
        scroll.set(0.1, 0.6)
        assert scroll._thumb_color == THEME["border"]
        progress = SleekProgressbar(frame, value=62)
        progress.grid(row=4, column=0, columnspan=5, sticky="ew", pady=12)
        assert progress._bar_color == THEME["progress"]
        transport_panel = ttk.Frame(frame, style="Panel.TFrame", padding=10)
        transport_panel.grid(row=5, column=0, pady=12)
        transport = PlayerTransportButton(transport_panel, command=lambda: None)
        transport.pack()
        volume = PlayerVolumeControl(
            frame, variable=tk.IntVar(popup, 60), command=lambda value: None
        )
        volume.grid(row=5, column=1, columnspan=2)
        icon = RoundedIconButton(
            frame, image=None, text="+", command=lambda: None, primary=True
        )
        icon.grid(row=5, column=3)
        popup.update()
        pump(app, 0.3)
        # Independent state distinction: no two primary faces may be identical.
        owner = app._product_chrome_owner
        faces = [
            ImageTk.getimage(owner.images[key]).tobytes()
            for key in ("accent", "accent_hover", "pressed", "accent_focus", "disabled")
        ]
        assert len(set(faces)) == 5
        buttons[-1].invoke()
        assert calls == []
        buttons[0].invoke()
        assert calls == [1]
        check.configure(state="disabled")
        before = flag.get()
        check._toggle_from_event(None)
        assert flag.get() == before
        capture = capture_own_widget(popup)
        assert capture is not None
        capture.save(out / (name.replace(" ", "-") + "-controls.png"))
        save_native_capture(
            popup, out / (name.replace(" ", "-") + "-controls-native.png")
        )
        popup.destroy()
    app.appearance_theme_var.set("Violet")
    app._request_live_theme()


def test_rendered_hover_and_navigation_keep_the_idle_face(
    application, tmp_path, monkeypatch
):
    """Capture own native pixels for the shared concave navigation contract."""
    from PIL import ImageChops

    from yt_downloader.platform_services import capture_own_widget

    app = application
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    out.mkdir(parents=True, exist_ok=True)
    app.geometry("1200x760+80+80")
    seed(app, tmp_path, count=1)
    app._select_focus_view("forge")
    pump(app, 0.3)

    nav = app._focus_nav_buttons["library"]
    nav_idle = capture_own_widget(nav).convert("RGB")
    save_native_capture(nav, out / "nav-idle-physical.png")
    nav.state(["active"])
    pump(app, 0.08)
    nav_hover = capture_own_widget(nav).convert("RGB")
    save_native_capture(nav, out / "nav-hover-physical.png")
    quiet = (max(3, nav_idle.width - 8), nav_idle.height // 2)
    assert (
        max(
            abs(after - before)
            for before, after in zip(
                nav_idle.getpixel(quiet), nav_hover.getpixel(quiet), strict=True
            )
        )
        <= 1
    )
    assert ImageChops.difference(nav_idle, nav_hover).getbbox() is not None
    nav.state(["!active"])

    app._select_focus_view("library")
    pump(app, 0.7)
    nav_button = app._focus_nav_buttons["library"]
    selected_nav = capture_own_widget(nav_button).convert("RGB")
    selected_nav.save(out / "selected-nav.png")
    physical_selected = save_native_capture(
        nav_button, out / "nav-selected-physical.png"
    ).convert("RGB")
    # Selection must span the actual button, not a separate narrower canvas.
    # Independent edge bands require inward dark shading across both halves.
    from PIL import ImageStat

    width, _height = nav_hover.size
    for left, right in ((width // 5, width // 2), (width // 2, width * 4 // 5)):
        before = ImageStat.Stat(nav_idle.crop((left, 1, right, 5))).mean
        after = ImageStat.Stat(nav_hover.crop((left, 1, right, 5))).mean
        assert sum(before) - sum(after) > 3, "Missing continuous upper inner shadow"
    # Selection has persistent depth and semantic icon/text, no accent edge.
    w, h = physical_selected.size
    scale = w / nav_button.winfo_width()
    assert not any(
        physical_selected.getpixel((x, y))[2] - physical_selected.getpixel((x, y))[1]
        > 30
        for y in range(h - round(7 * scale), h)
        for x in range(w)
    )

    nav_button.state(["focus"])
    pump(app, 0.08)
    focused = save_native_capture(nav_button, out / "nav-focused-physical.png")
    assert ImageChops.difference(focused.convert("RGB"), physical_selected).getbbox()
    nav_button.state(["!focus"])
    pump(app, 0.08)

    # A real producer fault removes material depth. The independent upper-band
    # check must reject it even though text, bounds and selection remain valid.
    from yt_downloader import ui_chrome

    with monkeypatch.context() as fault:
        fault.setattr(ui_chrome, "_matte_rim", lambda image, *args, **kwargs: image)
        app._product_chrome_owner._committed = None
        app._product_chrome_owner.request(__import__("tkinter").ttk.Style(app))
        nav_button.state(["focus"])
        pump(app, 0.04)
        nav_button.state(["!focus"])
        pump(app, 0.08)
        flat = save_native_capture(
            nav_button, out / "nav-flat-fault-physical.png"
        ).convert("RGB")
        upper = (round(w * 0.2), round(scale), round(w * 0.8), round(5 * scale))
        assert (
            sum(ImageStat.Stat(flat.crop(upper)).mean)
            > sum(ImageStat.Stat(physical_selected.crop(upper)).mean) + 3
        )
    app._product_chrome_owner._committed = None
    app._product_chrome_owner.request(__import__("tkinter").ttk.Style(app))
    nav_button.state(["focus"])
    pump(app, 0.04)
    nav_button.state(["!focus"])
    pump(app, 0.08)
    restored = save_native_capture(
        nav_button, out / "nav-restored-physical.png"
    ).convert("RGB")
    assert ImageChops.difference(restored, physical_selected).getbbox() is None

    sidebar = app.library_scene.sidebar
    bounds, _action = app.library_scene._sidebar_targets[1]
    material = sidebar._action_material
    photo = material.controls[bounds][-1]()
    assert photo.width() == bounds[2] - bounds[0]
    assert photo.height() == bounds[3] - bounds[1]
    sidebar_idle = capture_own_widget(sidebar).convert("RGB")
    x = bounds[0] + 42
    y = (bounds[1] + bounds[3]) // 2
    sidebar.event_generate("<Motion>", x=x, y=y)
    pump(app, 0.08)
    sidebar_hover = capture_own_widget(sidebar).convert("RGB")
    # The inset groove changes only its narrow contour; navigation content
    # retains the idle page face rather than becoming a filled hover rectangle.
    assert sidebar_idle.getpixel((x, y)) == sidebar_hover.getpixel((x, y))
    assert ImageChops.difference(sidebar_idle, sidebar_hover).getbbox() is not None
    assert not sidebar.find_withtag("pointer-state")
    sidebar.event_generate("<Leave>")

    nav_idle.save(out / "hover-nav-idle.png")
    nav_hover.save(out / "hover-nav-hover.png")
    sidebar_idle.save(out / "hover-sidebar-idle.png")
    sidebar_hover.save(out / "hover-sidebar-hover.png")
    save_native_capture(app, out / "hover-navigation-sidebar-native.png")


def test_shared_primary_paint_perturbation_reaches_ttk_scene_and_poster(
    application, tmp_path, monkeypatch
):
    import tkinter as tk

    from yt_downloader.media_player_ui import PosterPlayButton
    from yt_downloader.platform_services import capture_own_widget
    from yt_downloader.ui_chrome import action_button_image
    from yt_downloader.ui_theme import apply_theme_selection

    app = application
    before = theme_palette_snapshot()
    popup = tk.Toplevel(app)
    poster = PosterPlayButton(popup, command=lambda: None)
    poster.pack()
    seed(app, tmp_path, count=1)
    try:
        monkeypatch.setattr(
            "yt_downloader.ui_chrome.primary_action_color", lambda: "#354a25"
        )
        THEME["accent_dark"] = "#354a25"
        THEME["accent"] = "#a4c981"
        app._render_live_theme(before, theme_palette_snapshot())
        pump(app, 0.3)

        # Independent expected hue direction, not a renderer-generated expected image.
        def green(image):
            pixel = image.convert("RGB").getpixel((image.width // 2, image.height // 2))
            assert pixel[1] > pixel[0] and pixel[1] > pixel[2], pixel

        green(ImageTk.getimage(app._product_chrome_owner.images["accent"]))
        green(ImageTk.getimage(poster._backgrounds[0]))
        scenes = 0
        for tab, scene in (("library", app.library_scene), ("watch", app.focus_watch)):
            app._select_focus_view(tab)
            pump(app, 0.7)
            material = getattr(scene.canvas, "_action_material", None)
            if material:
                bitmap = capture_own_widget(scene.canvas)
                assert bitmap is not None
                scale = bitmap.width / scene.canvas.winfo_width()
                for bounds, (_item, primary, _image) in material.controls.items():
                    x = round(
                        (
                            bounds[0]
                            + (bounds[2] - bounds[0]) / 2
                            - scene.canvas.canvasx(0)
                        )
                        * scale
                    )
                    y = round((bounds[1] + 8 - scene.canvas.canvasy(0)) * scale)
                    if primary and 0 <= x < bitmap.width and 0 <= y < bitmap.height:
                        green(bitmap.crop((x, y, x + 1, y + 1)))
                        scenes += 1
        assert scenes >= 1
        # Known-bad bypass demonstrably fails the expected hue check.
        with pytest.raises(AssertionError):
            green(action_button_image(50, 30, accent=False))
    finally:
        previous = theme_palette_snapshot()
        apply_theme_selection("Violet")
        app._render_live_theme(previous, theme_palette_snapshot())
        popup.destroy()


def test_short_path_stays_inline_and_long_path_expands(application):
    from yt_downloader.detail_ui import FactsText

    doc = FactsText(application, width=1)
    doc.place(x=50, y=70, width=560, height=240)
    doc.request("Save to: /Users/coop/Downloads")
    pump(application, 0.1)
    # Compare actual mapped text positions; slash presence alone must not wrap.
    label = doc.dlineinfo("1.0")
    value = doc.dlineinfo(doc.search("/Users", "1.0"))
    assert label is not None and value is not None
    assert label[1] == value[1]
    doc.request("Save to: /Users/coop/" + "long-directory/" * 30)
    pump(application, 0.1)
    label = doc.dlineinfo("1.0")
    value = doc.dlineinfo(doc.search("/Users", "1.0"))
    assert label is not None and value is not None
    assert value[1] > label[1]
    doc.destroy()


def test_populated_scene_action_roles_and_decoded_media(
    application, tmp_path, monkeypatch
):
    import time

    from PIL import Image, ImageDraw

    from yt_downloader.archive_artwork import ArtworkAsset
    from yt_downloader.platform_services import capture_own_widget

    app = application
    paths = []
    for i in range(12):
        path = tmp_path / f"material-media-{i}.png"
        bitmap = Image.new("RGB", (640, 360), "#196eaa")
        draw = ImageDraw.Draw(bitmap)
        draw.rectangle((320, 0, 639, 359), fill="#d55339")
        draw.ellipse((110 + i * 8, 80, 260 + i * 8, 230), fill="#efd75a")
        bitmap.save(path)
        paths.append(path)
    for scene in (app.library_scene, app.focus_watch):
        monkeypatch.setattr(
            scene,
            "_artwork_source_path",
            lambda row, *_args: ArtworkAsset(
                paths[int(row["id"].split("-")[-1]) % 12], "thumbnail"
            ),
        )
    seed(app, tmp_path, count=12)
    out = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    for theme in ("Violet", "Jade"):
        app.appearance_theme_var.set(theme)
        app._request_live_theme()
        for tab, scene in (("library", app.library_scene), ("watch", app.focus_watch)):
            app._select_focus_view(tab)
            for width in (1200, 820):
                app.geometry(f"{width}x760+80+80")
                pump(app, 0.3)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    pump(app, 0.05)
                    if scene._artwork_images and not scene._artwork_owner.busy:
                        break
                assert scene._artwork_images, "Actual local images must have decoded"
                labels = [
                    (
                        scene.canvas.itemcget(item, "text"),
                        scene.canvas.itemcget(item, "fill"),
                    )
                    for item in scene.canvas.find_all()
                    if scene.canvas.type(item) == "text"
                ]
                links = [
                    color
                    for text, color in labels
                    if text in {"See All", "Add Collection"}
                ]
                assert links and set(links) == {THEME["action"]}
                image = save_native_capture(
                    app, out / f"{theme}-{tab}-populated-{width}-native.png"
                )
                capture_own_widget(app).save(
                    out / f"{theme}-{tab}-populated-{width}.png"
                )
                # Source-media red must remain colored under both material hues.
                red_pixels = sum(
                    r > 140 and r > g * 1.6 and r > b * 1.5
                    for r, g, b in zip(
                        *[iter(image.convert("RGB").tobytes())] * 3, strict=True
                    )
                )
                assert red_pixels > 500
            with monkeypatch.context() as roles:
                roles.setitem(THEME, "action", "#ffcc55")
                scene._render()
                pump(app, 0.1)
                links = [
                    scene.canvas.itemcget(item, "fill")
                    for item in scene.canvas.find_all()
                    if scene.canvas.type(item) == "text"
                    and scene.canvas.itemcget(item, "text")
                    in {"See All", "Add Collection"}
                ]
                assert links and set(links) == {"#ffcc55"}
            scene._render()
    app.appearance_theme_var.set("Violet")
    app._request_live_theme()
