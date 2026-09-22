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
    assert any("1 video" in text for text in texts)
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
    assert set(window._detail_targets.values()) == {
        "chapters",
        "info",
        "source",
        "output",
        "notes",
        "moments",
    }
    assert not hasattr(window, "_info_notebook")
    assert all(
        section.winfo_ismapped() for section in window._information_sections.values()
    )
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
    back = next(w for w in buttons if str(w.cget("text")) == "Back to Library")
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


@pytest.mark.parametrize("size", ["1100x600", "1440x900"])
def test_native_copy_menu_separates_personal_source_and_retains_opened_owner(
    application, tmp_path, monkeypatch, size
):
    from yt_downloader.history import history_annotation_owner, save_history
    from yt_downloader.library_annotations import LibraryAnnotation

    app = application
    monkeypatch.setattr(app, "_load_thumbnail_preview", lambda *a, **k: None)
    rows = []
    for kind, extension in (("MP4", "mp4"), ("MP3", "mp3")):
        path = tmp_path / kind / ("media." + extension)
        path.parent.mkdir()
        path.write_bytes(b"synthetic not played")
        row = saved(path, video="shared-video", kind=kind, playlist="shared-playlist")
        row.update(
            title=kind + " version",
            description="Source " + kind + "\nLast line",
            tags=["provider", kind],
            thumbnail="https://example.invalid/" + extension + ".jpg",
        )
        rows.append(row)
        app.library_annotations.replace(
            history_annotation_owner(row),
            LibraryAnnotation(
                note="PRIVATE " + kind + "\nPersonal last line",
                tags=("personal", kind),
                category=kind,
            ),
        )
    app.download_history = rows
    save_history(app.history_path, rows)
    before = app.history_path.read_bytes()
    app._reconcile_library_projection()
    app.library_output_type_var.set("All")
    app.video_tree.navigate(None, mode="all")
    app.geometry(size)
    pump(app, 0.2)
    copied = []
    monkeypatch.setattr(app, "clipboard_clear", lambda: copied.clear())
    monkeypatch.setattr(app, "clipboard_append", copied.append)
    menus = []
    monkeypatch.setattr(tk.Menu, "tk_popup", lambda menu, *a, **k: menus.append(menu))
    for kind in ("MP4", "MP3"):
        index = next(
            i
            for i, row in enumerate(app.metadata_items)
            if row["title"] == kind + " version"
        )
        other = 1 - index
        app.video_tree.see(str(index))
        app.video_tree.selection_set(str(index))
        app._display_selected_metadata(index)
        pump(app)
        app._show_library_actions_menu()
        menu = menus[-1]
        entries = {
            menu.entrycget(i, "label"): i
            for i in range(menu.index("end") + 1)
            if menu.type(i) not in ("separator", "tearoff")
        }
        # Real Tcl callbacks must retain the menu's owner even when the current
        # inspector now presents the other saved variant's personal annotation.
        app.video_tree.selection_set(str(other))
        app._display_selected_metadata(other)
        pump(app)
        for label, expected in (
            ("Copy source description", "Source " + kind + "\nLast line"),
            ("Copy source tags", "provider, " + kind),
            ("Copy your note", "PRIVATE " + kind + "\nPersonal last line"),
            ("Copy your tags", "personal, " + kind),
            ("Copy thumbnail URL", "https://example.invalid/" + kind.lower() + ".jpg"),
            (
                "Copy YouTube URL",
                "https://www.youtube.com/watch?v=shared-video&list=shared-playlist",
            ),
        ):
            menu.invoke(entries[label])
            pump(app, 0.02)
            assert copied == [expected]
        opened, confirmations = [], []
        monkeypatch.setattr(
            app,
            "_open_existing_saved_folder",
            lambda path, opened=opened: opened.append(str(path)),
        )
        monkeypatch.setattr(
            "yt_downloader.app.messagebox.askyesno",
            lambda _title, text, confirmations=confirmations, **_kwargs: (
                confirmations.append(text) or False
            ),
        )
        menu.invoke(entries["Open saved location"])
        menu.invoke(entries["Remove from Library…"])
        assert opened == [str(rows[index]["vodforge_output_dir"])]
        assert len(confirmations) == 1 and kind + " version" in confirmations[0]
        # Removing the original owner from the current projection while its
        # native menu stays open must not redirect either action.
        saved_projection = app.metadata_items
        app.metadata_items = tuple(
            row for i, row in enumerate(saved_projection) if i != index
        )
        opened.clear()
        confirmations.clear()
        menu.invoke(entries["Open saved location"])
        menu.invoke(entries["Remove from Library…"])
        assert opened == [] and confirmations == []
        app.metadata_items = saved_projection
        menu.destroy()
    assert app.history_path.read_bytes() == before


@pytest.mark.parametrize("size", ["1100x600", "1440x900"])
def test_cold_folders_overview_paints_each_available_highlight_without_navigation(
    application, tmp_path, size
):
    from PIL import Image

    from yt_downloader.archive_relink import record_fingerprint

    app = application
    app.geometry(size)
    rows = []
    for index in range(5):
        folder = tmp_path / "Archive" / f"Episode {index}"
        folder.mkdir(parents=True)
        Image.new("RGB", (320, 180), (30 + index * 20, 100, 160)).save(
            folder / "thumbnail.jpeg"
        )
        rows.append(saved(folder / "clip.mp4", video=f"cold-{index}"))
    app.download_history = rows
    app._reconcile_library_projection()
    app._select_focus_view("library")
    view = app.video_tree
    assert view.model.mode == "folders" and view.model.path is None

    def painted():
        components = [c for _box, c in view._boxes if c.kind == "media"]
        canvas_images = {
            view.canvas.itemcget(item, "image")
            for item in view.canvas.find_withtag("presentation-artwork")
        }
        return bool(components) and all(
            str(
                view._artwork_images.get(
                    record_fingerprint(dict(view.model.records[c.indices[0]]))
                )
            )
            in canvas_images
            for c in components
        )

    # No refresh, selection, navigation or warm-cache return may be required.
    wait_for(app, painted, timeout=5)
    assert view.model.mode == "folders" and view.model.path is None
    assert len([c for _box, c in view._boxes if c.kind == "media"]) >= 3
    assert view._artwork_displayed


@pytest.mark.parametrize("size", ["1100x600", "1440x900"])
def test_watch_rail_metadata_follows_the_actual_title_without_reserved_blank_line(
    application, tmp_path, size
):
    app = application
    rows = seed(app, tmp_path, count=5)
    rows[0]["title"] = "First saved story"
    extra = saved(
        tmp_path / "audio" / "clip.mp3",
        video="video-0",
        playlist="Series 0",
        channel="Creator 0",
        kind="MP3",
    )
    extra["title"] = rows[0]["title"]
    app.download_history = [*rows, extra]
    app._reconcile_library_projection()
    app.geometry(size)
    app._select_focus_view("watch")
    app.focus_watch._navigate("playlists")
    pump(app, 0.3)
    action = next(
        action
        for _bounds, action in app.focus_watch._targets
        if getattr(getattr(action, "func", None), "__name__", "") == "_scene_open"
        and getattr(action, "keywords", {}).get("playlist")
    )
    action()
    pump(app, 0.3)
    canvas = app.focus_watch.canvas
    texts = [
        (canvas.itemcget(item, "text"), canvas.bbox(item))
        for item in canvas.find_all()
        if canvas.type(item) == "text"
    ]
    title = max(
        (box for text, box in texts if text == "First saved story"),
        key=lambda box: box[1],
    )
    versions = next(box for text, box in texts if "2 saved versions" in text)
    assert 4 <= versions[1] - title[3] <= 12
    assert versions[0] == title[0]
    assert versions[2] - versions[0] <= app.focus_watch._card_width + 2


def test_forge_deck_titles_fit_real_allocations_through_resize(application, tmp_path):
    import tkinter.font as tkfont

    app = application
    rows = seed(app, tmp_path, count=4)
    for index, row in enumerate(rows):
        row["title"] = f"Story {index} — very wide WWW characters 日本語 " * 4
    app.download_history = rows
    app._reconcile_library_projection()
    app._select_focus_view("forge")
    for width in (1100, 1180, 1440, 1100):
        app.geometry(f"{width}x700")
        pump(app, 0.25)
        labels = [
            child
            for tile in app.focus_run_deck.winfo_children()
            for child in tile.winfo_children()
            if isinstance(child, tk.Label)
            and str(child.cget("text")).startswith("Story ")
        ]
        assert len(labels) >= 3
        for label in labels:
            text = str(label.cget("text"))
            font = tkfont.Font(root=app, font=label.cget("font"))
            assert text.endswith("…")
            assert font.measure(text) <= label.winfo_width() - 4


@pytest.mark.parametrize("size", ["1100x600", "1440x900"])
@pytest.mark.parametrize("output_type", ["MP4", "MP3"])
@pytest.mark.parametrize("matching", [False, True])
def test_legacy_relink_review_uses_recorded_format_and_observes_unresolved_count(
    application, tmp_path, size, output_type, matching
):
    from tkinter import ttk

    from yt_downloader.history import (
        load_history,
        sanitize_history_record,
        save_history,
    )
    from yt_downloader.media_player import resolve_library_media_path

    app = application
    app.geometry(size)
    suffix = (
        output_type.lower() if matching else ("mp3" if output_type == "MP4" else "mp4")
    )
    chosen = tmp_path / "selected" / f"chosen.{suffix}"
    chosen.parent.mkdir()
    chosen.write_bytes(b"synthetic candidate; no decoding claim")
    rows = [
        sanitize_history_record(
            {
                "id": "selected",
                "title": "Saved item",
                "vodforge_output_type": output_type,
            },
            tmp_path / "old",
        )
    ]
    save_history(app.history_path, rows)
    app.download_history = load_history(app.history_path)
    app._reconcile_library_projection()
    app._select_focus_view("library")
    app.video_tree.selection_set("0")
    app._display_selected_metadata(0)
    wait_for(app, lambda: not app._archive_worker.busy)
    before = app.history_path.read_bytes()
    events = []
    app._archive_observe = lambda feature, action, key, **dims: events.append(
        (feature, action, key, dims)
    )
    app._archive_begin_relink(None, (0,), exact=str(chosen))
    wait_for(app, lambda: any(event[1] == "verified" for event in events))
    buttons = [
        w for w in native_descendants(app._archive_overlay) if isinstance(w, ttk.Button)
    ]
    apply = next(w for w in buttons if str(w.cget("text")).startswith("Update "))
    back = next(w for w in buttons if str(w.cget("text")) == "Back to Library")
    verified = next(event for event in events if event[1] == "verified")
    assert verified[0] == "archive_relink_operation"
    assert verified[3]["identity_mismatch_count"] == ("0" if matching else "1")
    assert verified[3]["verified_count"] == ("1" if matching else "0")
    assert verified[3]["unresolved_count"] == ("0" if matching else "1")
    assert apply.instate(["disabled"]) == (not matching)
    # Settled review retains its explanation even when no Apply closure owns it.
    import gc

    gc.collect()
    pump(app)
    assert (
        "1 file ready" if matching else "No files ready"
    ) in app._archive_overlay._archive_relink_status.get()
    assert (
        abs(app._archive_overlay.winfo_width() - app.focus_library_view.winfo_width())
        <= 2
    )
    if matching:
        apply.invoke()
        wait_for(app, lambda: not app._archive_commit_active)
        assert resolve_library_media_path(load_history(app.history_path)[0]) == chosen
        assert any(event[1] == "committed" for event in events)
    else:
        assert (
            "file does not match the saved format or details"
            in next(
                w
                for w in native_descendants(app._archive_overlay)
                if isinstance(w, tk.Text)
            )
            .get("1.0", "end")
            .lower()
        )
        apply.invoke()
        assert app.history_path.read_bytes() == before
        back.invoke()
        assert not any(event[1] == "committed" for event in events)
    assert app._archive_overlay is None


@pytest.mark.parametrize("size", ["1100x600", "1440x900"])
@pytest.mark.parametrize("count", [1, 40])
def test_relink_review_fits_one_item_and_scrolls_many_without_losing_paths(
    application, tmp_path, size, count
):
    from tkinter import ttk

    from yt_downloader.history import save_history

    app = application
    app.geometry(size)
    old, new = tmp_path / "old", tmp_path / "selected"
    new.mkdir()
    rows = []
    for index in range(count):
        name = f"Saved story {index:02}.mp4"
        (new / name).write_bytes(b"synthetic review file")
        rows.append(saved(old / name, video=f"review-{index}"))
    app.download_history = rows
    save_history(app.history_path, rows)
    before = app.history_path.read_bytes()
    app._reconcile_library_projection()
    app._select_focus_view("library")
    wait_for(app, lambda: not app._archive_worker.busy)
    app._archive_begin_relink(
        ArchivePath.parse(str(old)), tuple(range(count)), destination=str(new)
    )
    panel = app._archive_overlay
    wait_for(
        app,
        lambda: (
            "file" in panel._archive_relink_status.get()
            and "ready" in panel._archive_relink_status.get()
        ),
    )
    pump(app, 0.3)
    document = next(w for w in native_descendants(panel) if isinstance(w, tk.Text))
    contents = document.get("1.0", "end")
    assert "Saved format:   MP4" in contents and "Selected format:   MP4" in contents
    for index in range(count):
        assert str(old / f"Saved story {index:02}.mp4") in contents
        assert str(new / f"Saved story {index:02}.mp4") in contents
    assert document.tag_ranges("review-title")
    assert document.tag_ranges("review-label")
    surface = panel._archive_relink_review
    assert document.winfo_ismapped() and document.winfo_height() > 100
    assert document.bbox("1.0") is not None
    assert surface.winfo_height() > 140
    assert (
        surface.winfo_rooty() + surface.winfo_height()
        <= panel.winfo_rooty() + panel.winfo_height()
    )
    if count == 1 and size == "1440x900":
        assert surface.winfo_height() < panel.grid_bbox(0, 2, 1, 2)[3] - 60
    if count > 1:
        assert document.yview()[1] < 1
        document.yview_moveto(1)
        pump(app)
        assert document.yview()[1] == 1
    buttons = [w for w in native_descendants(panel) if isinstance(w, ttk.Button)]
    apply = next(w for w in buttons if str(w.cget("text")).startswith("Update "))
    assert str(apply.cget("text")) == (
        "Update location" if count == 1 else f"Update {count} locations"
    )
    assert apply.winfo_ismapped()
    next(w for w in buttons if str(w.cget("text")) == "Back to Library").invoke()
    assert app.history_path.read_bytes() == before


@pytest.fixture(autouse=True)
def legacy_folder_workspace_for_existing_contracts(application):
    """These contracts target the retained folder workspace, not the default scenes."""
    application._library_scene_action("folders", None)
    application.update()
