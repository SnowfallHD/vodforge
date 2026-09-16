"""Real Tk image outcomes for semantic render reuse and invalidation."""

import gc
import os
import time

import pytest
from PIL import Image, ImageTk

from scripts.focus_ui_preview import isolated_preview_services
from yt_downloader.analytics_startup import AnalyticsStartup
from yt_downloader.app import DownloaderApp
from yt_downloader.engagement_ui import EngagementUI
from yt_downloader.ui_theme import THEME
from yt_downloader.ui_widgets import SegmentedSelector

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="native display required"
)


@pytest.fixture
def application(monkeypatch):
    gc.collect()
    monkeypatch.setattr(AnalyticsStartup, "start", lambda self: None)
    monkeypatch.setattr(EngagementUI, "start", lambda self: None)
    errors = []
    with isolated_preview_services():
        app = DownloaderApp()
        app.report_callback_exception = lambda *error: errors.append(error)
        app.geometry("1180x740")
        app.metadata_items = []
        app._render_metadata_tree(selected_index=None)
        app._select_focus_view("library")
        app.deiconify()
        deadline = time.monotonic() + 0.2
        while time.monotonic() < deadline:
            app.update()
            time.sleep(0.005)
        app._select_focus_view("library")
        app.update()
        try:
            yield app
        finally:
            app._request_application_close()
            deadline = time.monotonic() + 3
            while app.tk.call("info", "commands", ".") and time.monotonic() < deadline:
                app.update()
                time.sleep(0.01)
            closed = not app.tk.call("info", "commands", ".")
            if not closed:
                app.destroy()
            assert closed
            assert not errors


def solid(color):
    return Image.new("RGBA", (320, 180), color)


def center(image):
    bitmap = ImageTk.getimage(image).convert("RGB")
    return bitmap.getpixel((bitmap.width // 2, bitmap.height // 2))


def image_pair(app):
    return app.focus_active_thumbnail_image, app.thumbnail_image


def spy_renders(app, monkeypatch):
    calls = []
    render = app._render_focus_thumbnail_image

    def observe(*args, **kwargs):
        result = render(*args, **kwargs)
        calls.append((args, kwargs, result))
        return result

    monkeypatch.setattr(app, "_render_focus_thumbnail_image", observe)
    return calls


@pytest.mark.parametrize("owner", ["thumbnails", "segmented_selector"])
def test_same_visual_intent_preserves_live_image_identity(application, owner):
    app = application
    if owner == "thumbnails":
        app._render_focus_thumbnail_surfaces(solid("#dc143c"), placeholder=True)
        before = image_pair(app)
        for _ in range(20):
            app._render_focus_thumbnail_surfaces()
        assert image_pair(app) == before
        assert center(app.thumbnail_image) == (220, 20, 60)
    else:
        selector = next(
            child
            for frame in app.winfo_children()
            for child in descendants(frame)
            if isinstance(child, SegmentedSelector)
        )
        before = dict(selector._segment_images)
        selected = selector._variable.get()
        for _ in range(20):
            selector._variable.set(selected)
        assert selector._segment_images == before
        for value, image in before.items():
            assert str(selector._labels[value].cget("image")) == str(image)


def descendants(widget):
    yield widget
    for child in widget.winfo_children():
        yield from descendants(child)


def test_position_only_configure_does_not_repeat_thumbnail_rasterization(
    application, monkeypatch
):
    app = application
    event_owner = app.thumbnail_label.master
    width = event_owner.winfo_width()
    app._render_focus_thumbnail_surfaces(library_width=width)
    before = image_pair(app)
    pixels = ImageTk.getimage(before[1]).tobytes()
    calls = spy_renders(app, monkeypatch)
    assert event_owner.winfo_ismapped()
    for position in range(24):
        event_owner.event_generate(
            "<Configure>",
            x=position,
            y=position + 2,
            width=width,
            height=event_owner.winfo_height(),
        )
    assert "<Configure>" in event_owner.bind()
    assert calls == []
    assert image_pair(app) == before
    assert ImageTk.getimage(app.thumbnail_image).tobytes() == pixels


@pytest.mark.parametrize("target", ["active", "library", "both"])
def test_new_source_with_same_dimensions_and_path_updates_requested_owner(
    application, tmp_path, target
):
    app = application
    # A nonexistent source file takes the real Pillow fallback. Its stable path
    # cannot be mistaken for stable decoded pixels.
    path = tmp_path / "stable-owner.png"
    app._render_focus_thumbnail_surfaces(
        solid("#dc143c"), placeholder=False, source_path=path
    )
    app._render_focus_thumbnail_surfaces(
        solid("#0066cc"), placeholder=False, source_path=path, target=target
    )
    assert center(app.focus_active_thumbnail_image) == (
        (0, 102, 204) if target in {"active", "both"} else (220, 20, 60)
    )
    assert center(app.thumbnail_image) == (
        (0, 102, 204) if target in {"library", "both"} else (220, 20, 60)
    )
    before = image_pair(app)
    app._render_focus_thumbnail_surfaces()
    assert image_pair(app) == before


def test_geometry_and_palette_changes_refresh_real_pixels(application, monkeypatch):
    app = application
    app._render_focus_thumbnail_surfaces(
        solid((0, 0, 0, 0)), placeholder=True, library_width=110
    )
    first = app.thumbnail_image
    app._render_focus_thumbnail_surfaces(library_width=220)
    assert app.thumbnail_image.width() > first.width()
    assert app.focus_active_thumbnail_image.width() == 152
    monkeypatch.setitem(THEME, "bg", "#123456")
    monkeypatch.setitem(THEME, "surface", "#654321")
    app._render_focus_thumbnail_surfaces(library_width=220)
    bitmap = ImageTk.getimage(app.thumbnail_image).convert("RGB")
    assert bitmap.getpixel((0, 0)) == (18, 52, 86)
    assert center(app.thumbnail_image) == (101, 67, 33)
    before = image_pair(app)
    app._render_focus_thumbnail_surfaces(library_width=220)
    assert image_pair(app) == before


def test_uncommitted_render_failure_retries_instead_of_becoming_cached(
    application, monkeypatch
):
    app = application
    app._render_focus_thumbnail_surfaces(solid("#dc143c"), placeholder=True)
    render = app._render_focus_thumbnail_image
    attempts = []

    def fail_once(*args, **kwargs):
        attempts.append(True)
        return None if len(attempts) == 1 else render(*args, **kwargs)

    monkeypatch.setattr(app, "_render_focus_thumbnail_image", fail_once)
    app._render_focus_thumbnail_surfaces(
        solid("#0066cc"), placeholder=True, target="library"
    )
    assert center(app.thumbnail_image) == (220, 20, 60)
    app._render_focus_thumbnail_surfaces()
    assert len(attempts) == 4
    assert center(app.thumbnail_image) == (0, 102, 204)
    before = image_pair(app)
    app._render_focus_thumbnail_surfaces()
    assert len(attempts) == 4
    assert image_pair(app) == before


@pytest.mark.parametrize("target", ["active", "library"])
@pytest.mark.parametrize("change", ["cleared_image", "changed_text"])
def test_externally_changed_label_is_repaired_with_unchanged_source(
    application, target, change
):
    app = application
    app._render_focus_thumbnail_surfaces(solid("#dc143c"), placeholder=True)
    label = (
        app.focus_active_thumbnail_label if target == "active" else app.thumbnail_label
    )
    label.configure(
        **(
            {"image": "", "text": "Preview pending"}
            if change == "cleared_image"
            else {"text": "Preview pending"}
        )
    )
    app._render_focus_thumbnail_surfaces()
    assert str(label.cget("image"))
    assert label.cget("text") == ""
    assert center(app.thumbnail_image) == (220, 20, 60)


def test_retired_native_image_resource_cannot_satisfy_render_reuse(
    application, monkeypatch, tmp_path
):
    app = application
    created = []

    def native_resource(_path, size, *, radius):
        # Exercise the production string-image ownership/deletion path with real
        # Tcl photo resources; this is not an AppKit decoder qualification.
        name = str(
            app.tk.call(
                "image", "create", "photo", "-width", size[0], "-height", size[1]
            )
        )
        app.tk.call(name, "put", "#11aa44", "-to", 0, 0, size[0], size[1])
        created.append(name)
        return name

    monkeypatch.setattr(app, "_create_focus_native_image", native_resource)
    app._render_focus_thumbnail_surfaces(
        solid("#11aa44"), placeholder=False, source_path=tmp_path / "source.png"
    )
    before = image_pair(app)
    app._render_focus_thumbnail_surfaces()
    assert image_pair(app) == before
    assert len(created) == 2
    app.tk.call("image", "delete", before[0])
    app._render_focus_thumbnail_surfaces()
    assert len(created) == 4
    current = image_pair(app)
    assert current != before
    names = set(app.tk.splitlist(app.tk.call("image", "names")))
    assert set(current).issubset(names)
    assert not set(before).intersection(names)
    assert app.tk.call(current[1], "get", 1, 1) == (17, 170, 68)
