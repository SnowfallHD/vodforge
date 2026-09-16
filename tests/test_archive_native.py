"""Real Tk archive/Watch and embedded-player host contracts.

Provider behavior uses the existing controlled VLC fixture here; real codec,
audio and packaged playback remain distinct acceptance tiers.
"""

from __future__ import annotations

import os
import time
import tkinter as tk
from types import SimpleNamespace

import pytest

from tests.test_archive_models import saved
from tests.test_libvlc_backend import make_backend
from tests.test_native_thumbnail_rendering import application as _application
from yt_downloader.archive_browser_ui import ArchiveBrowser
from yt_downloader.archive_paths import ArchivePath
from yt_downloader.media_player_ui import MediaPlayerWindow

application = _application

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="native display required"
)


def pump(app, seconds=0.12):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.update()
        time.sleep(0.005)


def seed(app, tmp_path, count=9):
    rows = []
    for index in range(count):
        rows.append(
            {
                **saved(
                    tmp_path / f"series-{index // 4}" / f"media-{index}" / "clip.mp4",
                    video=f"video-{index}",
                    playlist=f"Series {index // 4}",
                    channel=f"Creator {index // 8}",
                ),
                "description": "A full description " * 50,
                "vodforge_user_note": "Personal note retained",
                "duration": 100,
            }
        )
    app.download_history = rows
    app._reconcile_library_projection()
    pump(app)
    return rows


@pytest.mark.parametrize("size", ["1100x600", "1440x900"])
def test_archive_is_folder_browser_and_keeps_full_ancestry(application, tmp_path, size):
    app = application
    rows = seed(app, tmp_path)
    app.geometry(size)
    app._select_focus_view("library")
    assert isinstance(app.video_tree, ArchiveBrowser)
    app.video_tree.model.reveal(0)
    app.video_tree.selection_set("0")
    app._display_selected_metadata(0)
    app._archive_inspector_expanded = True
    app._apply_focus_layout(force=True)
    pump(app)
    expected = ArchivePath.parse(rows[0]["vodforge_output_dir"])
    assert app._archive_context_path == expected
    assert app._archive_parent_paths[-1] == expected
    assert str(expected) in app._archive_path_text.get("1.0", "end")
    assert app.focus_archive_inspector.winfo_ismapped()
    assert not any(isinstance(widget, tk.Toplevel) for widget in app.winfo_children())
    assert len(app.video_tree._boxes) <= 48


def test_watch_singleton_keyboard_and_saved_variant_count(application, tmp_path):
    app = application
    rows = seed(app, tmp_path, count=1)
    app.download_history[0]["title"] = "Long playlist video title " * 20
    app._reconcile_library_projection()
    app.focus_watch.set_records(app.metadata_items)
    app._select_focus_view("watch")
    pump(app)
    watch = app.focus_watch
    texts = [
        watch.canvas.itemcget(item, "text")
        for item in watch.canvas.find_all()
        if watch.canvas.type(item) == "text"
    ]
    assert any("1 downloaded video" in text for text in texts)
    assert "Play" in texts and "View in Library" in texts
    plays = []
    watch._on_play = plays.append
    watch._render()
    watch.canvas.focus_force()
    watch._keyboard_target = 0
    watch._activate_target()
    assert plays == [0]
    watch._navigate("channels")
    pump(app)
    assert any(
        "Creator" in watch.canvas.itemcget(item, "text")
        for item in watch.canvas.find_all()
        if watch.canvas.type(item) == "text"
    )
    watch._navigate("channels", rows[0]["channel"])
    pump(app)
    assert watch.heading_var.get() == rows[0]["channel"]


def test_singleton_measured_text_does_not_overlap_controls(application, tmp_path):
    app = application
    seed(app, tmp_path, count=1)
    app.download_history[0]["title"] = "Very long video title " * 40
    app.download_history[0]["description"] = "Long description content " * 100
    app._reconcile_library_projection()
    app.focus_watch.set_records(app.metadata_items)
    app.geometry("1100x600")
    app._select_focus_view("watch")
    pump(app)
    canvas = app.focus_watch.canvas
    text = [
        (canvas.itemcget(item, "text"), canvas.bbox(item))
        for item in canvas.find_all()
        if canvas.type(item) == "text"
    ]
    play_box = next(bounds for label, bounds in text if label == "Play")
    title_box = next(bounds for label, bounds in text if label.startswith("Very long"))
    description_box = next(
        bounds for label, bounds in text if label.startswith("Long description")
    )
    assert title_box[3] <= description_box[1]
    assert description_box[3] < play_box[1]


def test_embedded_player_owns_child_surface_and_retires_only_its_bindings(
    application, tmp_path
):
    app = application
    seed(app, tmp_path, count=1)
    app._select_focus_view("library")
    app.video_tree.navigate(None, mode="all")
    app.video_tree.selection_set("0")
    old_state = (
        app.video_tree.model.mode,
        app.video_tree.model.selected_owner,
        app.video_tree.model.page,
    )
    host = app._archive_show_overlay(app.focus_library_view)
    backend, module = make_backend()
    media = tmp_path / "fixture.mp4"
    media.write_bytes(b"controlled-provider fixture; not playable-media proof")
    backend.load(media, duration=100)
    preview_calls = []
    previews = SimpleNamespace(
        preview_png=lambda position: preview_calls.append(position),
        shutdown=lambda: preview_calls.append("closed"),
    )
    closed = []
    unrelated = app.bind("<space>", lambda event: None, add="+")
    before_children = set(app.winfo_children())
    window = MediaPlayerWindow(
        app,
        playback=backend,
        previews=previews,
        info={
            **app.metadata_items[0],
            "chapters": [{"start_time": 0, "end_time": 50, "title": "Chapter one"}],
            "heatmap": [{"start_time": 0, "end_time": 100, "value": 0.5}],
        },
        host=host,
        source_details="Source technical field",
        output_details="Requested and measured output",
        on_closed=lambda: (closed.append(True), app._archive_restore_browser()),
    )
    window.show()
    pump(app)
    assert set(app.winfo_children()) == before_children
    assert window.popup.winfo_toplevel() is app
    assert not isinstance(window.popup, tk.Toplevel)
    tabs = [
        window._info_notebook.tab(tab, "text") for tab in window._info_notebook.tabs()
    ]
    assert {"Chapters", "Info", "Source", "Output", "Notes", "Moments"}.issubset(tabs)
    assert len(window.preview_labels) == 5
    assert window._ensure_render_surface()
    surface = window._surface_owner
    assert surface.toplevel is app
    if surface._view is not None:
        assert surface._view.superview() is not None
    window.close()
    window.close()
    pump(app)
    assert app.winfo_exists()
    assert closed == [True]
    assert not surface._bindings
    assert surface._view is None and surface._surface is None
    assert unrelated in app.bind("<space>")
    assert (
        app.video_tree.model.mode,
        app.video_tree.model.selected_owner,
        app.video_tree.model.page,
    ) == old_state
    assert app.video_tree.winfo_ismapped()
    assert module.player.release_calls == 1
    assert "closed" in preview_calls
    app.unbind("<space>", unrelated)


def test_description_remains_accessible_in_compact_inspector(application, tmp_path):
    app = application
    rows = seed(app, tmp_path, count=1)
    app.geometry("1100x600")
    app._select_focus_view("library")
    app.video_tree.selection_set("0")
    app._display_selected_metadata(0)
    app._archive_inspector_expanded = True
    app._apply_focus_layout(force=True)
    app.focus_archive_inspector.select(app.focus_archive_description_tab)
    pump(app)
    assert app.description_text.winfo_ismapped()
    assert app.description_text.winfo_height() > 100
    assert rows[0]["description"].strip() in app.description_text.get("1.0", "end")
    app.description_text.yview_moveto(1)
    assert app.description_text.yview()[1] == 1.0


def test_native_destroy_retires_event_timer_without_tcl_background_error(application):
    app = application
    app.tk.eval(
        "set ::archive_background_errors {}; proc bgerror {message} {lappend ::archive_background_errors $message}"
    )
    timer = app._event_pump_after_id
    startup_timers = tuple(app._startup_after_ids) + (app._update_receipt_after_id,)
    assert timer in app.tk.call("after", "info")
    app._request_application_close()
    deadline = time.monotonic() + 3
    while app.tk.call("info", "commands", ".") and time.monotonic() < deadline:
        app.update()
        time.sleep(0.01)
    assert not app.tk.call("info", "commands", ".")
    assert timer not in app.tk.call("after", "info")
    assert not set(startup_timers).intersection(app.tk.call("after", "info"))
    deadline = time.monotonic() + 0.25
    while time.monotonic() < deadline:
        app.tk.call("update")
        time.sleep(0.01)
    assert not app.tk.call("set", "::archive_background_errors")


def test_archive_real_thumbnail_and_full_location_context_survive_back(
    application, tmp_path
):
    from PIL import Image

    app = application
    folder = tmp_path / "archive" / "Channel" / "Playlist" / "Episode" / "Export"
    folder.mkdir(parents=True)
    Image.new("RGB", (320, 180), "#157cb3").save(folder / "thumbnail.jpeg")
    rows = [saved(folder / "clip.mp4")]
    app.download_history = rows
    app._reconcile_library_projection()
    app._select_focus_view("library")
    app.video_tree.model.reveal(0)
    app.video_tree.selection_set("0")
    app._display_selected_metadata(0)
    pump(app, 0.35)
    app.video_tree._refresh()
    pump(app)
    assert app.video_tree._artwork_images
    assert any(
        app.video_tree.canvas.type(item) == "image"
        for item in app.video_tree.canvas.find_all()
    )
    before = (app.video_tree.model.path, app.video_tree.model.selected_owner)
    app._archive_show_overlay(app.focus_library_view)
    app._archive_restore_browser()
    app.geometry("1100x600")
    app._archive_inspector_expanded = True
    app._apply_focus_layout(force=True)
    app.focus_archive_inspector.select(app.focus_archive_location_tab)
    pump(app)
    assert (app.video_tree.model.path, app.video_tree.model.selected_owner) == before
    assert str(folder) in app._archive_path_text.get("1.0", "end")
    assert [str(path) for path in app._archive_parent_paths][-3:] == [
        str(folder.parent.parent),
        str(folder.parent),
        str(folder),
    ]
    assert app._archive_path_text.winfo_ismapped()
    assert app._archive_ancestors.winfo_ismapped()
    assert app._archive_ancestors.winfo_height() >= 80
    app._archive_location_canvas.yview_moveto(1)
    pump(app)
    assert app._archive_location_canvas.yview()[1] == 1.0


def test_watch_details_reveals_exact_saved_video_and_focus_contract(
    application, tmp_path
):
    from yt_downloader.ui_widgets import _focus_library_table_item

    app = application
    seed(app, tmp_path, count=3)
    app._select_focus_view("watch")
    app._archive_watch_details(2)
    pump(app)
    assert app._focus_selected_view == "library"
    assert app.video_tree.selection() == ("2",)
    _focus_library_table_item(app.video_tree, "1")
    assert app.video_tree.focus_item() == "1"


def test_archive_cards_keep_row_facts_and_page_keys_retain_visible_selection(
    application, tmp_path
):
    app = application
    seed(app, tmp_path, count=51)
    app.download_history[0].update(
        playlist_index=17, duration=100, channel="Exact creator"
    )
    app._reconcile_library_projection()
    app._select_focus_view("library")
    app.video_tree.navigate(None, mode="all")
    pump(app)
    text = [
        app.video_tree.canvas.itemcget(item, "text")
        for item in app.video_tree.canvas.find_all()
        if app.video_tree.canvas.type(item) == "text"
    ]
    assert any("#017" in value and "1:40" in value for value in text)
    assert "Exact creator" in text
    app.video_tree._page(1)
    pump(app)
    selected = int(app.video_tree.selection()[0])
    assert any(
        selected in item.indices for item in app.video_tree.model.page_components
    )
    app.video_tree._page(-1)
    assert (
        int(app.video_tree.selection()[0])
        in app.video_tree.model.page_components[0].indices
    )


def wait_for(app, condition, timeout=3):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "Native fixture did not settle"
        app.update()
        time.sleep(0.005)


def native_descendants(widget):
    yield widget
    for child in widget.winfo_children():
        yield from native_descendants(child)


@pytest.mark.parametrize("mode", ["file", "folder"])
@pytest.mark.parametrize("outcome", ["commit", "commit_insert", "cancel", "stale"])
def test_native_relink_review_buttons_preserve_exact_history_and_selection(
    application, tmp_path, mode, outcome
):
    from tkinter import ttk

    from yt_downloader.history import load_history, save_history

    app = application
    destination = tmp_path / "new" / "clip.mp4"
    destination.parent.mkdir()
    destination.write_bytes(b"synthetic retained media")
    old = tmp_path / "old"
    rows = [
        saved(tmp_path / "unrelated" / "other.mp4", video="other"),
        saved(old / "clip.mp4", video="selected"),
    ]
    app.download_history = rows
    save_history(app.history_path, rows)
    app._reconcile_library_projection()
    app._select_focus_view("library")
    if outcome == "commit_insert":
        app.library_search_var.set("selected")
        pump(app)
    app.video_tree.selection_set("1")
    app._display_selected_metadata(1)
    wait_for(app, lambda: not app._archive_worker.busy)
    before = app.history_path.read_bytes()
    events = []
    app._archive_observe = lambda feature, action, key, **dims: events.append(action)
    app._archive_begin_relink(
        ArchivePath.parse(str(old)) if mode == "folder" else None,
        (1,),
        destination=str(destination.parent) if mode == "folder" else "",
        exact=str(destination) if mode == "file" else "",
    )
    wait_for(app, lambda: "verified" in events)
    panel = app._archive_overlay
    buttons = [w for w in native_descendants(panel) if isinstance(w, ttk.Button)]
    apply = next(w for w in buttons if str(w.cget("text")).startswith("Update "))
    back = next(w for w in buttons if str(w.cget("text")) == "Back to archive")
    assert not apply.instate(["disabled"])
    assert (
        apply.winfo_ismapped()
        and apply.winfo_rooty() + apply.winfo_height()
        <= app.winfo_rooty() + app.winfo_height()
    )
    review = next(w for w in native_descendants(panel) if isinstance(w, tk.Text))
    assert str(destination) in review.get("1.0", "end")
    if outcome == "cancel":
        back.invoke()
        assert app._archive_overlay is None
        assert app.history_path.read_bytes() == before
        assert "cancelled" in events
    else:
        if outcome == "stale":
            app.download_history[1]["title"] = "Changed after review"
        apply.invoke()
        if outcome == "commit_insert":
            from yt_downloader.history import upsert_history

            inserted = saved(tmp_path / "newest" / "other.mp4", video="newest")

            def insert_after_commit():
                app.download_history = upsert_history(
                    app.download_history, inserted, inserted["vodforge_output_dir"]
                )
                save_history(app.history_path, app.download_history)

            app._archive_defer_history(
                "native-insert",
                insert_after_commit,
                mutation={"kind": "record", "record": inserted},
            )
        if outcome == "stale":
            assert "stale" in events and apply.instate(["disabled"])
            assert app.history_path.read_bytes() == before
            back.invoke()
        else:
            wait_for(app, lambda: not app._archive_commit_active)
            actual = load_history(app.history_path)
            other = next(row for row in actual if row["id"] == "other")
            selected = next(row for row in actual if row["id"] == "selected")
            assert other["vodforge_output_path"] == rows[0]["vodforge_output_path"]
            assert selected["vodforge_output_path"] == str(destination)
            assert app._archive_overlay is None and "committed" in events
            selected_index = next(
                i for i, row in enumerate(app.metadata_items) if row["id"] == "selected"
            )
            assert app.video_tree.selection() == (str(selected_index),)
            if outcome == "commit_insert":
                assert selected_index == 2
                assert app.library_search_var.get() == "selected"
                assert app.metadata_items[0]["id"] == "newest"
            assert app._archive_context_path == ArchivePath.parse(
                str(destination.parent)
            )
    assert destination.read_bytes() == b"synthetic retained media"
    assert not old.exists()


@pytest.mark.parametrize("choose", ["cancel", "accept"])
def test_native_missing_relinked_media_uses_explicit_saved_profile_recovery(
    application, tmp_path, choose
):
    from tkinter import ttk

    from tests.test_library_media_recovery import _job, _missing_record
    from yt_downloader.history import load_history, save_history

    app = application
    original = _job(tmp_path)
    row = _missing_record(original)
    row.update(
        vodforge_relinked=True,
        vodforge_output_dir=str(tmp_path / "relocated"),
        vodforge_output_path=str(tmp_path / "relocated" / "clip.mp3"),
    )
    app.download_history = [row]
    save_history(app.history_path, [row])
    app.library_output_type_var.set("All")
    app._reconcile_library_projection()
    app._select_focus_view("library")
    wait_for(app, lambda: not app._archive_worker.busy)
    before = app.history_path.read_bytes()
    default_destination = app.output_var.get()
    chosen = tmp_path / "explicit-recovery-base"
    queued = []
    app._pick_output_directory = lambda: str(chosen) if choose == "accept" else ""
    app._start_or_queue_download_job = lambda job, **kwargs: queued.append(job) or True
    app._archive_request_playback(app.metadata_items[0])

    def recovery_button():
        panel = app.__dict__.get("_archive_playback_host")
        if panel is None:
            return None
        return next(
            (
                w
                for w in native_descendants(panel)
                if isinstance(w, ttk.Button)
                and str(w.cget("text")) == "Choose folder and redownload"
            ),
            None,
        )

    wait_for(app, lambda: recovery_button() is not None)
    button = recovery_button()
    assert button.winfo_ismapped()
    button.invoke()
    pump(app)
    assert app._archive_overlay is None
    assert app.output_var.get() == default_destination
    assert not chosen.exists()
    if choose == "cancel":
        assert not queued and app.history_path.read_bytes() == before
    else:
        assert len(queued) == 1
        assert queued[0].output_dir == chosen
        assert queued[0].mp3_settings == original.mp3_settings
        assert queued[0].tags == original.tags
        assert load_history(app.history_path) == []
        assert app._focus_selected_view == "forge"
