"""Source-native visual and control contracts; synthetic records only."""

from __future__ import annotations

import os
from itertools import pairwise
from pathlib import Path

import pytest

from tests.test_archive_native import application as _application
from tests.test_archive_native import pump, seed

application = _application

pytestmark = pytest.mark.skipif(
    os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1", reason="native display required"
)


@pytest.mark.parametrize("size", ["1100x600", "1440x900"])
def test_library_controls_have_subjects_and_details_work_at_both_sizes(
    application, tmp_path, size
):
    app = application
    rows = seed(app, tmp_path)
    rows[0]["title"] = "0"
    app._reconcile_library_projection()
    app.geometry(size)
    app._select_focus_view("library")
    app.video_tree.navigate(None, mode="all")
    app.video_tree.selection_set("0")
    app._display_selected_metadata(0)
    pump(app, 0.3)
    browser = app.video_tree
    assert str(browser.parent_button["text"]) == "Up one folder"
    assert str(browser.parent_button["state"]) == "disabled"
    assert not browser.previous.winfo_ismapped() and not browser.next.winfo_ismapped()
    assert str(browser._nav_buttons["all"]["style"]) == "Archive.FocusNavActive.TButton"
    assert app.focus_library_details_button["text"] == "Show details"
    app.focus_library_details_button.invoke()
    pump(app)
    scene = app.library_scene
    assert scene.winfo_ismapped() and scene._detail_owner
    texts = [
        scene.canvas.itemcget(item, "text")
        for item in scene.canvas.find_all()
        if scene.canvas.type(item) == "text"
    ]
    assert "Source Details" in texts and "Output Details" in texts
    navigation_text = [
        scene.canvas.itemcget(item, "text")
        for item in scene.canvas.find_all()
        if scene.canvas.type(item) == "text" and scene.canvas.bbox(item)[1] < 40
    ]
    assert navigation_text == ["Back to folders"]
    # The visible Back action returns to the folder workspace which opened details.
    box = next(
        bounds
        for bounds, label, _color, _enabled in scene._button_labels
        if scene.canvas.itemcget(label, "text").startswith("Back to")
    )
    next(action for bounds, action in scene._targets if bounds == box)()
    pump(app)
    assert not scene.winfo_ismapped()
    assert not app.focus_archive_inspector.winfo_ismapped()
    assert browser.winfo_ismapped()
    assert browser.selection() == ("0",)
    assert all(bounds[2] - bounds[0] >= 60 for bounds, _item in browser._open_boxes)


@pytest.mark.parametrize("size", ["1100x600", "1440x900"])
def test_watch_real_hero_and_channel_return_controls(application, tmp_path, size):
    app = application
    rows = seed(app, tmp_path, count=17)
    app.geometry(size)
    app._select_focus_view("watch")
    watch = app.focus_watch
    observations, plays = [], []
    watch._on_usage = lambda *args, **dims: observations.append((args, dims))
    watch._on_play = plays.append
    watch._hero_seen_key = ""
    pump(app, 0.3)
    watch._render()
    texts = [
        watch.canvas.itemcget(item, "text")
        for item in watch.canvas.find_all()
        if watch.canvas.type(item) == "text"
    ]
    assert any(rows[0]["channel"] in text for text in texts)
    assert any(rows[0]["title"] in text for text in texts)
    assert watch.search_field._placeholder["text"].strip() == "Search saved videos"
    assert not any(text in {"‹", "›", "↑"} for text in texts)
    watch._targets[0][1]()
    assert plays == [0]
    assert [args[1] for args, _ in observations].count("hero_shown") == 1
    assert any(
        args == ("watch", "hero_played") and dims == {"watch_mode": "playlists"}
        for args, dims in observations
    )
    assert all("video-" not in repr(dims) for _args, dims in observations)
    watch._navigate("channels")
    pump(app)
    watch._navigate("channels", rows[0]["channel"])
    pump(app)
    bounds = next(
        box
        for box, label, _color, _enabled in watch._button_labels
        if watch.canvas.itemcget(label, "text") == "Back to channels"
    )
    next(action for box, action in watch._targets if box == bounds)()
    pump(app)
    assert watch._channel == "" and watch.heading_var.get() == "Watch"
    assert watch._scene_route == "channels"
    assert watch.subtitle_var.get() == "Browse the channels in your library."
    assert watch.search.get() == "" and app._global_search_var.get() == ""
    visible = [
        watch.canvas.itemcget(item, "text")
        for item in watch.canvas.find_all()
        if watch.canvas.type(item) == "text"
    ]
    assert "Channels" in visible
    assert all(any(row["channel"] == text for text in visible) for row in rows)
    assert not watch.back_button.winfo_ismapped()
    assert not watch.previous.winfo_ismapped() and not watch.next.winfo_ismapped()


@pytest.mark.parametrize("size", ["1100x600", "1440x900"])
def test_library_explicit_card_action_and_top_nav_remain_inside_window(
    application, tmp_path, size
):
    app = application
    seed(app, tmp_path)
    app.geometry(size)
    app._select_focus_view("library")
    browser = app.video_tree
    browser.navigate(None, mode="all")
    pump(app, 0.3)
    opened = []
    browser._on_activate = opened.append
    bounds, item = browser._open_boxes[0]
    browser.canvas.event_generate(
        "<Button-1>",
        x=int((bounds[0] + bounds[2]) / 2),
        y=int((bounds[1] + bounds[3]) / 2),
    )
    pump(app)
    assert opened == [item.indices[0]]
    for button in [
        *app._focus_nav_buttons.values(),
        app.focus_library_play_button,
        app.focus_library_details_button,
        app.focus_library_menu_button,
    ]:
        assert button.winfo_ismapped()
        assert button.winfo_rootx() >= app.winfo_rootx()
        assert (
            button.winfo_rootx() + button.winfo_width()
            <= app.winfo_rootx() + app.winfo_width()
        )
        assert str(button["takefocus"]) not in {"0", "false"}


@pytest.mark.parametrize("size", ["1100x600", "1440x900"])
def test_destination_text_fits_control_and_preserves_full_path(application, size):
    app = application
    app.geometry(size)
    full_path = "/Volumes/" + "Wide WWW 日本語 location /" * 12 + "Saved videos"
    app.output_var.set(full_path)
    app._select_focus_view("forge")
    pump(app, 0.3)
    pill = app.focus_destination_button
    box = pill.bbox(pill._text_item)
    icon = pill.bbox(pill._icon_item)
    assert box is not None and icon is not None
    assert box[0] >= icon[2] + 5
    assert box[2] <= pill.winfo_width() - 16
    assert "…" in pill.itemcget(pill._text_item, "text")
    assert pill._tooltip.current_text() == full_path
    assert app.focus_output_display_var.get() == full_path
    assert pill.itemcget(pill._text_item, "text").endswith("Saved videos")
    for view in ("library", "watch"):
        app._select_focus_view(view)
        pump(app)
        assert not pill.winfo_ismapped()


def test_watch_keyboard_play_affordance_and_card_hover_retire(application, tmp_path):
    app = application
    seed(app, tmp_path, count=17)
    app._select_focus_view("watch")
    pump(app, 0.3)
    watch = app.focus_watch
    rail = watch._scene_rails["recent"]
    rail.canvas.focus_force()
    rail._focus_index = 0
    rail._paint_focus()
    assert rail.canvas.find_withtag("focus-play")
    assert any(
        rail.canvas.itemcget(item, "text") == "Play"
        for item in rail.canvas.find_withtag("focus-play")
        if rail.canvas.type(item) == "text"
    )
    app._select_focus_view("library")
    app.video_tree.navigate(None, mode="all")
    pump(app)
    browser = app.video_tree
    bounds, component = browser._boxes[0]
    from types import SimpleNamespace

    browser._hover(SimpleNamespace(x=bounds[0] + 10, y=bounds[1] + 10))
    assert browser._hovered_component == component
    browser._leave_hover(None)
    assert browser._hovered_component is None


@pytest.mark.parametrize("size", ["1100x600", "1440x900"])
def test_player_discloses_all_details_without_changing_playback(
    application, tmp_path, size, monkeypatch
):
    from types import SimpleNamespace

    from tests.test_archive_native import make_backend
    from yt_downloader.media_player_ui import MediaPlayerWindow

    app = application
    seed(app, tmp_path)
    app.geometry(size)
    app._select_focus_view("watch")
    host = app._archive_show_overlay(app._focus_views["watch"])
    backend, module = make_backend()
    media = tmp_path / "controlled.mp4"
    media.write_bytes(b"controlled-provider; not playable-media proof")
    backend.load(media, duration=100)
    features = []
    detail_targets = []

    def observe_feature(action, **fields):
        features.append(action)
        if action == "detail_viewed":
            detail_targets.append(fields["dimensions"]["detail_target"])

    player = MediaPlayerWindow(
        app,
        host=host,
        playback=backend,
        previews=SimpleNamespace(
            preview_png=lambda position: None, shutdown=lambda: None
        ),
        info={
            **app.metadata_items[0],
            "chapters": [{"start_time": 0, "end_time": 50, "title": "Beginning"}],
        },
        source_details="Source preserved",
        output_details="Output preserved",
        on_feature=observe_feature,
        on_closed=app._archive_restore_browser,
    )
    try:
        player.show()
        pump(app)
        assert player._details_shell.winfo_ismapped()
        assert not hasattr(player, "_info_notebook")
        assert not hasattr(player, "details_button")
        before = backend.snapshot
        for key in player._information_sections:
            player._select_information_panel(key)
            pump(app, 0.1)
            player._observe_information()
        assert backend.snapshot.status == before.status
        assert backend.snapshot.path == before.path
        assert features.count("detail_viewed") == len(player._information_sections)
        assert set(detail_targets) == {
            "chapters",
            "info",
            "source",
            "output",
            "notes",
            "moments",
        }
        player._select_information_panel("PRIVATE arbitrary widget or title")
        assert features.count("detail_viewed") == len(player._information_sections)
    finally:
        player.close()
        pump(app)
    assert module.player.release_calls == 1


def test_location_short_labels_keep_exact_paths_and_all_recovery_actions(
    application, tmp_path, monkeypatch
):

    from yt_downloader.library_scene_facts import saved_file_path

    app = application
    seed(app, tmp_path, count=1)
    app.geometry("1100x600")
    app._select_focus_view("library")
    app.video_tree.navigate(None, mode="all")
    app.video_tree.selection_set("0")
    app._display_selected_metadata(0)
    app.focus_library_details_button.invoke()
    pump(app, 0.3)
    scene = app.library_scene
    assert scene.winfo_ismapped() and scene._route == "detail"
    expected = str(app.metadata_items[0]["vodforge_output_dir"])
    copies = [
        action
        for _box, action in scene._targets
        if getattr(getattr(action, "func", None), "__name__", "") == "_copy_value"
        and getattr(action, "args", ()) == (expected,)
    ]
    assert copies, "The full saved location keeps its explicit copy action"
    copies[-1]()
    assert app.clipboard_get() == expected

    menus = []
    from yt_downloader import app as app_module

    original = app_module.ContextMenu

    def create_menu(*args, **kwargs):
        menu = original(*args, **kwargs)
        menus.append(menu)
        return menu

    monkeypatch.setattr(app_module, "ContextMenu", create_menu)
    monkeypatch.setattr(original, "tk_popup", lambda *_args: None)
    more = next(
        action
        for _box, action in scene._targets
        if getattr(getattr(action, "func", None), "__name__", "") == "_open_item_menu"
    )
    more()
    root_menu, files, _copy = menus
    entries = {
        files.entrycget(i, "label"): i
        for i in range(files.index("end") + 1)
        if files.type(i) == "command"
    }
    assert "Update file location\u2026" in entries
    assert "Copy file path" in entries
    files.invoke(entries["Copy file path"])
    assert app.clipboard_get() == saved_file_path(app.metadata_items[0])
    # Context actions are native Tcl callbacks and keep the opened item.
    assert any(
        root_menu.entrycget(i, "label") == "Show in Folder"
        for i in range(root_menu.index("end") + 1)
        if root_menu.type(i) == "command"
    )
    scene.return_from_detail()
    pump(app)
    assert app.video_tree.winfo_ismapped()


def test_compact_details_use_bounded_page_and_tabs_keep_one_baseline(
    application, tmp_path
):
    from yt_downloader.library_scene_facts import library_detail_facts

    app = application
    seed(app, tmp_path, count=1)
    app.geometry("1100x600")
    app._select_focus_view("library")
    app.video_tree.navigate(None, mode="all")
    app.video_tree.selection_set("0")
    app._display_selected_metadata(0)
    app.focus_library_details_button.invoke()
    pump(app, 0.3)
    scene = app.library_scene
    for size in ("1100x600", "1440x900"):
        app.geometry(size)
        pump(app, 0.3)
        assert scene.winfo_ismapped() and scene._route == "detail"
        assert not app.focus_archive_inspector.winfo_ismapped()
        assert not app.video_tree.winfo_ismapped()
        canvas = scene.canvas
        assert 600 <= canvas.winfo_width() <= app.winfo_width()
        text_items = [item for item in canvas.find_all() if canvas.type(item) == "text"]
        texts = [canvas.itemcget(item, "text") for item in text_items]
        # The former notebook facts remain in the visible, scrollable detail page.
        assert all(
            label in texts for label in ("Source Details", "Output Details", "Tags")
        )
        for fields in library_detail_facts(app.metadata_items[0]):
            for label, value, _icon in fields:
                assert label in texts
                assert value in texts
        description = next(
            item
            for item in canvas.find_all()
            if canvas.type(item) == "window"
            and canvas.itemcget(item, "window") == str(scene._description_section)
        )
        region = tuple(float(v) for v in canvas.cget("scrollregion").split())
        canvas.yview_moveto(max(0, canvas.bbox(description)[1] - 20) / region[3])
        pump(app, 0.05)
        assert scene._description_section.winfo_ismapped()
        for label in ("Source Details", "Output Details"):
            item = next(
                item for item in text_items if canvas.itemcget(item, "text") == label
            )
            box = canvas.bbox(item)
            region = tuple(float(v) for v in canvas.cget("scrollregion").split())
            canvas.yview_moveto(max(0, box[1] - 20) / region[3])
            pump(app, 0.05)
            assert 0 <= box[1] - canvas.canvasy(0) < canvas.winfo_height()
        canvas.yview_moveto(0)
    scene.return_from_detail()
    pump(app)
    assert app.video_tree.winfo_ismapped()
    assert app.video_tree.selection() == ("0",)


def test_compact_detail_reading_page_preserves_note_and_native_chapter_selection(
    application, tmp_path
):
    from yt_downloader.media_player_ui import ChapterList

    app = application
    seed(app, tmp_path)
    app.geometry("1100x600")
    app._select_focus_view("library")
    app.video_tree.navigate(None, mode="all")
    from yt_downloader.app import ANNOTATION_OWNER_KEY, PROJECTION_OWNER_KEY
    from yt_downloader.library_annotations import LibraryAnnotation

    chosen = app.metadata_items[0]
    owner = str(chosen.get(ANNOTATION_OWNER_KEY) or chosen[PROJECTION_OWNER_KEY])
    app.library_annotations.replace(
        owner, LibraryAnnotation(note="A meaningful saved note. " * 80)
    )
    app._reconcile_library_projection()
    app.video_tree.selection_set("0")
    app._display_selected_metadata(0)
    app._archive_inspector_expanded = True
    app._apply_focus_layout(force=True)
    pump(app, 0.3)
    identity, details = app.focus_archive_identity, app.focus_archive_inspector
    assert identity.winfo_rootx() + identity.winfo_width() <= details.winfo_rootx()
    assert app.focus_thumbnail_wrap.winfo_width() >= 240
    assert app.focus_library_play_button.winfo_ismapped()
    assert app.selected_note_var.get() == app.metadata_items[0]["vodforge_user_note"]
    assert len(app.selected_note_display_var.get()) < len(app.selected_note_var.get())
    app.selected_title_var.set("A long title with wide WWW characters. " * 40)
    app._fit_focus_selected_overview_text()
    pump(app)
    assert app.selected_meta_display_var.get()
    assert "…" in app.selected_title_display_var.get()
    assert (
        app.focus_selected_meta_label.winfo_rooty()
        + app.focus_selected_meta_label.winfo_height()
        <= app.focus_selected_overview.winfo_rooty()
        + app.focus_selected_overview.winfo_height()
    )
    chapters = ChapterList(
        app,
        [
            {"title": "Opening", "start_time": 0},
            {"title": "A second section", "start_time": 12},
        ],
    )
    try:
        chapters.pack()
        pump(app)
        chapters.selection_set(1)
        assert chapters.curselection() == (1,)
        chapters.selection_clear(0, "end")
        assert chapters.curselection() == ()
        assert chapters.item("1", "values") == ("A second section", "0:12")
    finally:
        chapters.destroy()


@pytest.mark.parametrize("button", [2, 3])
@pytest.mark.parametrize("kind", ["media", "activity", "folder"])
def test_secondary_native_pointer_selects_without_primary_action(
    application, tmp_path, button, kind
):
    app = application
    seed(app, tmp_path)
    app.geometry("1100x600")
    app._select_focus_view("library")
    browser = app.video_tree
    activated, navigated, menus = [], [], []
    browser._on_activate = activated.append
    browser._on_select = lambda: None
    browser._on_folder = lambda _path, _indices: None
    browser._on_menu = lambda _event: (
        menus.append(browser.model.selected_index()) or "break"
    )
    if kind == "activity":
        browser.set_records(
            [
                {
                    "id": "preview",
                    "title": "Preview",
                    "webpage_url": "https://example.test/preview",
                }
            ],
            (0,),
        )
    browser.navigate(None, mode="folders" if kind == "folder" else "all")
    pump(app)
    browser.navigate = lambda path: navigated.append(path)
    bounds, component = browser._open_boxes[0]
    assert component.kind == kind
    x, y = int((bounds[0] + bounds[2]) / 2), int((bounds[1] + bounds[3]) / 2)
    before = browser.model.path
    browser.canvas.event_generate(f"<Button-{button}>", x=x, y=y)
    browser.canvas.event_generate(f"<ButtonRelease-{button}>", x=x, y=y)
    pump(app)
    assert activated == [] and navigated == []
    assert browser.model.path == before
    assert menus == ([] if kind == "folder" else [component.indices[0]])
    # The same coordinates must retain their ordinary primary action.
    browser.canvas.event_generate("<Button-1>", x=x, y=y)
    browser.canvas.event_generate("<ButtonRelease-1>", x=x, y=y)
    pump(app)
    assert activated == ([] if kind == "folder" else [component.indices[0]])
    assert navigated == ([component.path] if kind == "folder" else [])
    # Context selection also leaves the item reachable using the keyboard.
    browser.canvas.focus_force()
    browser.canvas.event_generate("<Return>")
    pump(app)
    assert len(navigated if kind == "folder" else activated) == 2


def test_native_folder_and_media_subjects_are_exclusive(application, tmp_path):
    from tests.test_archive_models import saved
    from yt_downloader.archive_paths import ArchivePath

    app = application
    root = tmp_path / "archive"
    app.download_history = [
        saved(root / "direct.mp4", video="direct"),
        *(saved(root / f"folder{i}" / "clip.mp4", video=f"video{i}") for i in range(3)),
    ]
    app._reconcile_library_projection()
    app.geometry("1440x900")
    app._select_focus_view("library")
    browser = app.video_tree
    browser.navigate(ArchivePath.parse(str(root)), mode="folders")
    browser.selection_set("0")
    app._display_selected_metadata(0)
    pump(app)
    folder_box, folder = next(
        (box, item)
        for box, item in browser._boxes
        if item.kind == "folder" and item.title == "folder1"
    )
    browser.canvas.event_generate(
        "<Button-1>", x=int(folder_box[0] + 20), y=int(folder_box[1] + 20)
    )
    browser.canvas.event_generate(
        "<ButtonRelease-1>", x=int(folder_box[0] + 20), y=int(folder_box[1] + 20)
    )
    pump(app)
    assert browser.selection() == () and browser.model.selected_owner == ""
    assert app.selected_title_var.get() == "folder1"
    assert str(app.focus_library_play_button["state"]) == "disabled"
    assert str(app.focus_library_menu_button["state"]) == "disabled"
    assert not app.focus_library_play_button.winfo_ismapped()
    assert not app.focus_library_menu_button.winfo_ismapped()
    assert app._archive_variant_indices == ()
    assert app.selected_note_var.get() == ""
    assert app._archive_context_path == folder.path
    app._archive_show_inspector()
    app.geometry("1100x600")
    pump(app)
    app.geometry("1440x900")
    pump(app)
    assert app.focus_archive_inspector.winfo_ismapped()
    assert app.focus_archive_inspector.select() == str(app.focus_archive_location_tab)
    assert not app.focus_library_menu_button.winfo_ismapped()
    app._archive_show_inspector()
    browser.canvas.focus_force()
    browser.canvas.event_generate("<Right>")
    pump(app)
    assert browser._selected_folder.title == "folder2"
    assert app.selected_title_var.get() == "folder2"
    # A media affordance in the same folder view replaces folder ownership.
    played = []
    browser._on_activate = played.append
    bounds, media = next(
        (box, item) for box, item in browser._open_boxes if item.kind == "media"
    )
    browser.canvas.event_generate(
        "<Button-1>",
        x=int((bounds[0] + bounds[2]) / 2),
        y=int((bounds[1] + bounds[3]) / 2),
    )
    browser.canvas.event_generate(
        "<ButtonRelease-1>",
        x=int((bounds[0] + bounds[2]) / 2),
        y=int((bounds[1] + bounds[3]) / 2),
    )
    pump(app)
    assert browser._selected_folder is None
    assert browser.selection() == (str(media.indices[0]),)
    assert app.selected_title_var.get() == "direct"
    assert str(app.focus_library_play_button["state"]) == "normal"
    assert str(app.focus_library_menu_button["state"]) == "normal"
    assert app.focus_library_play_button.winfo_ismapped()
    assert app.focus_library_menu_button.winfo_ismapped()
    assert app.focus_library_action_row.pack_slaves() == [
        app.focus_library_play_button,
        app.focus_library_details_button,
        app.focus_library_menu_button,
    ]
    browser.canvas.event_generate("<Return>")
    pump(app)
    assert played == [media.indices[0], media.indices[0]]


def test_library_primary_action_order_survives_width_and_detail_transitions(
    application, tmp_path
):
    app = application
    seed(app, tmp_path)
    app._select_focus_view("library")
    app.video_tree.navigate(None, mode="all")
    app.video_tree.selection_set("0")
    app._display_selected_metadata(0)
    for size, expanded in (
        ("1440x900", False),
        ("1100x600", True),
        ("1440x900", True),
        ("1100x600", False),
        ("1440x900", False),
    ):
        app.geometry(size)
        app._archive_inspector_expanded = expanded
        app._apply_focus_layout(force=True)
        pump(app, 0.2)
        controls = [
            app.focus_library_play_button,
            app.focus_library_details_button,
            app.focus_library_menu_button,
        ]
        visible = [button for button in controls if button.winfo_ismapped()]
        assert visible[0] is app.focus_library_play_button
        positions = [button.winfo_rootx() for button in visible]
        assert positions == sorted(positions)


def test_watch_contextual_actions_keep_keyboard_details_and_complete_targets(
    application, tmp_path
):
    from types import SimpleNamespace

    app = application
    rows = seed(app, tmp_path, count=17)
    rows[0]["title"] = "Short title"
    rows[1]["title"] = "A much longer title that needs two lines"
    app._reconcile_library_projection()
    app.geometry("1100x600")
    app._select_focus_view("watch")
    pump(app, 0.3)
    watch = app.focus_watch
    details = []
    watch._on_details = details.append
    watch._render()
    rail = watch._scene_rails["recent"]
    region = tuple(float(v) for v in watch.canvas.cget("scrollregion").split())
    watch.canvas.yview_moveto(rail._y / region[3])
    pump(app)
    assert len(rail._card_actions) >= 2
    assert not any(
        rail.canvas.itemcget(item, "text") == "Details"
        for item in rail.canvas.find_all()
        if rail.canvas.type(item) == "text"
    )
    cover, action = rail._card_actions[0]
    assert (
        0 <= cover[0] < action[0] < action[2] <= cover[2] <= rail.canvas.winfo_width()
    )
    assert cover[1] < action[1] < action[3] < cover[3]
    assert cover[3] <= rail.canvas.winfo_height()
    type(watch)._hover(rail, SimpleNamespace(x=cover[0] + 20, y=cover[1] + 20))
    assert {
        rail.canvas.itemcget(item, "text")
        for item in rail.canvas.find_withtag("hover-play")
        if rail.canvas.type(item) == "text"
    } == {"Play", "Details"}
    rail.canvas.delete("hover-play")
    assert not rail.canvas.find_withtag("hover-play")
    rail.canvas.focus_force()
    rail._focus_index = 0
    rail._focus_detail = True
    rail._paint_focus()
    assert rail.canvas.find_withtag("focus-play")
    rail._activate()
    assert len(details) == 1
    builds = watch._depth.builds
    for _ in range(10):
        watch._render()
    assert watch._depth.builds == builds
    assert watch._depth.cached_bytes <= 8 * 1024 * 1024
    assert len(watch._depth._images) <= 12


def test_category_channel_tile_returns_to_origin_without_hijacking_directory_navigation(
    application, tmp_path
):
    app = application
    seed(app, tmp_path, count=20)
    app.geometry("1100x600")
    app._select_focus_view("watch")
    watch = app.focus_watch
    watch.set_records(
        [{**row, "vodforge_user_category": "Weekend"} for row in app.metadata_items]
    )
    watch._navigate("collections")
    pump(app, 0.3)
    watch.canvas.yview_moveto(1)
    pump(app)
    expected = watch.canvas.yview()[0]
    channel = str(watch._records[0]["channel"])
    watch._navigate("channels", channel)
    pump(app)
    assert watch.back_button["text"] == "‹  Back to browse"
    watch.back_button.invoke()
    pump(app)
    assert watch._mode == "collections" and watch._channel == ""
    assert abs(watch.canvas.yview()[0] - expected) < 0.02
    watch._navigate("channels", channel)
    watch._navigate("channels")
    pump(app)
    assert watch._mode == "channels" and not watch._channel


def test_layered_canvas_keeps_displayed_images_alive_across_cache_eviction(application):
    import tkinter as tk

    from yt_downloader.ui_chrome import CanvasSurfaceCache

    canvas = tk.Canvas(application)
    owner = CanvasSurfaceCache(canvas)
    owner.draw((0, 0, 3400, 440), role="ambient")
    owner.draw((0, 0, 3400, 264), selected=True)
    for width in range(60, 76):
        owner.draw((0, 0, width, 32), role="action")
    live = set(canvas.tk.splitlist(canvas.tk.call("image", "names")))
    missing = [
        canvas.itemcget(item, "image")
        for item in canvas.find_all()
        if canvas.type(item) == "image" and canvas.itemcget(item, "image") not in live
    ]
    assert missing == []
    assert owner.cached_bytes <= 8 * 1024 * 1024
    assert len(owner._images) <= 12
    assert owner.bytes > 8 * 1024 * 1024  # The real displayed scene is counted.
    for generation in range(12):
        canvas.delete("all")
        owner.draw((0, 0, 3400 - generation * 10, 440), role="ambient")
        owner.draw((0, 0, 3400 - generation * 10, 264), selected=True)
        owner.draw((0, 0, 80, 32), role="action")
        assert len(owner._displayed) == 3
        live = set(canvas.tk.splitlist(canvas.tk.call("image", "names")))
        assert all(canvas.itemcget(item, "image") in live for item in canvas.find_all())
        assert owner.cached_bytes <= 8 * 1024 * 1024
    owner.clear()
    assert canvas.find_all() == ()
    assert owner.bytes == owner.cached_bytes == 0
    canvas.destroy()


def test_same_size_neutral_field_refreshes_pixels_and_preserves_live_handle(
    application, monkeypatch
):
    import tkinter as tk

    from PIL import ImageChops

    from yt_downloader import ui_chrome
    from yt_downloader.platform_services import capture_own_widget
    from yt_downloader.ui_chrome import RoundedFieldBorder
    from yt_downloader.ui_theme import THEME

    field = tk.Frame(application, width=260, height=40)
    field.place(x=0, y=0, width=260, height=40)
    owner = RoundedFieldBorder(field)
    pump(application)
    owner.request()
    before_image = owner._image

    def pixels():
        pump(application, 0.05)
        image = capture_own_widget(field)
        assert image is not None
        return image.convert("RGB")

    before = pixels()
    monkeypatch.setitem(THEME, "accent", "#11ee44")
    owner.request()
    assert owner._image is before_image
    # Accent refresh is observed, but the field deliberately keeps neutral edges.
    assert ImageChops.difference(pixels(), before).getbbox() is None
    monkeypatch.setitem(THEME, "surface", "#445566")
    owner.request()
    refreshed = pixels()
    assert ImageChops.difference(refreshed, before).getbbox()
    owner.request(focused=True)
    assert owner._image is before_image
    assert ImageChops.difference(pixels(), refreshed).getbbox()
    owner.request(focused=False)
    assert ImageChops.difference(pixels(), refreshed).getbbox() is None

    # Real producer faults must fail the same rendered RGB contracts. Focus
    # contour/missing/stale negatives live in test_field_density_native.
    recipe = ui_chrome.field_border_image

    def wrong_accent_face(*args, **kwargs):
        image = recipe(*args, **kwargs)
        alpha = image.getchannel("A")
        image.paste(THEME["accent"], (0, 0, image.width, image.height))
        image.putalpha(alpha)
        return image

    with monkeypatch.context() as fault:
        fault.setattr(ui_chrome, "field_border_image", wrong_accent_face)
        fault.setitem(THEME, "accent", "#ee1133")
        owner.request()
        with pytest.raises(AssertionError):
            assert ImageChops.difference(pixels(), refreshed).getbbox() is None
    owner.request()
    assert ImageChops.difference(pixels(), refreshed).getbbox() is None
    with monkeypatch.context() as fault:
        fault.setattr(
            ui_chrome,
            "create_surface_image",
            lambda *args, **kwargs: (kwargs["existing"], 0),
        )
        fault.setitem(THEME, "surface", "#226633")
        owner.request()
        with pytest.raises(AssertionError):
            assert ImageChops.difference(pixels(), refreshed).getbbox()
    field.destroy()


def test_root_library_saved_cards_share_selection_keyboard_and_context_owner(
    application, tmp_path
):
    from types import SimpleNamespace

    app = application
    seed(app, tmp_path, count=8)
    app.geometry("1440x900")
    app._select_focus_view("library")
    browser = app.video_tree
    browser.navigate(None, mode="folders")
    pump(app, 0.3)
    assert any(item.kind == "folder" for _, item in browser._boxes)
    assert not app.focus_library_play_button.winfo_ismapped()
    assert not app.focus_library_menu_button.winfo_ismapped()
    bounds, media = next(
        (box, item) for box, item in browser._boxes if item.kind == "media"
    )
    assert len(browser._boxes) <= 48
    plays, menus = [], []
    browser._on_activate = plays.append
    browser._on_menu = lambda _event: (
        menus.append(browser.model.selected_index()) or "break"
    )
    event = SimpleNamespace(x=bounds[0] + 12, y=bounds[3] - 16)
    browser._click(event)
    pump(app)
    assert browser.selection() == (str(media.indices[0]),)
    assert browser.model.path is None and browser.model.mode == "folders"
    browser._keyboard_activate(None)
    assert plays == [media.indices[0]]
    browser._menu(event)
    assert menus == [media.indices[0]] and plays == [media.indices[0]]
    assert app.selected_title_var.get() == media.title


def test_hidden_watch_artwork_survives_retirement_and_recovers_on_return(
    application, tmp_path
):
    from pathlib import Path

    from PIL import Image

    app = application
    rows = seed(app, tmp_path, count=3)
    for row in rows:
        folder = Path(row["vodforge_output_dir"])
        folder.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (320, 180), "#dd5522").save(folder / "thumbnail.jpeg")
    app.geometry("1440x900")
    app._select_focus_view("watch")
    watch = app.focus_watch
    pump(app, 1.0)
    assert watch._artwork_displayed
    before = set(watch._artwork_displayed)
    app._select_focus_view("library")
    pump(app)
    # A queued hidden render must leave all retained image owners intact.
    watch._render()
    watch._artwork_resize((250, 140))
    names = set(app.tk.splitlist(app.tk.call("image", "names")))
    assert before <= names
    for item in watch.canvas.find_all():
        if watch.canvas.type(item) == "image":
            assert watch.canvas.itemcget(item, "image") in names
    app.geometry("1100x600")
    app._select_focus_view("watch")
    pump(app, 1.0)
    assert watch._artwork_displayed
    assert set(watch._artwork_displayed).isdisjoint(before)
    names = set(app.tk.splitlist(app.tk.call("image", "names")))
    assert all(
        watch.canvas.itemcget(item, "image") in names
        for item in watch.canvas.find_all()
        if watch.canvas.type(item) == "image"
    )


def test_overview_arrows_distinguish_media_from_containing_folder(
    application, tmp_path
):
    app = application
    seed(app, tmp_path, count=3)
    app.geometry("1440x900")
    app._select_focus_view("library")
    browser = app.video_tree
    browser.navigate(None, mode="folders")
    pump(app)
    folders = [item for _, item in browser._boxes if item.kind == "folder"]
    media = [item for _, item in browser._boxes if item.kind == "media"]
    assert len(folders) == 1 and len(media) == 3
    browser.selection_set(str(media[0].indices[0]))
    browser.canvas.focus_force()
    pump(app)
    browser.canvas.event_generate("<Right>")
    pump(app)
    assert browser.selection() == (str(media[1].indices[0]),)
    browser.canvas.event_generate("<Left>")
    pump(app)
    assert browser.selection() == (str(media[0].indices[0]),)
    browser.canvas.event_generate("<Up>")
    pump(app)
    assert browser._selected_folder == folders[0] and browser.selection() == ()
    browser.canvas.event_generate("<Down>")
    pump(app)
    assert browser._selected_folder is None
    # Five highlight columns fit at this width; the third occupied card is
    # horizontally nearest the center of the full-width containing folder.
    assert browser.selection() == (str(media[2].indices[0]),)


def test_compact_timeline_contains_maximum_heatmap_markers_and_endpoint_handle(
    application,
):
    import tkinter as tk
    from functools import partial
    from types import SimpleNamespace

    from yt_downloader.media_player_ui import MediaPlayerWindow

    canvas = tk.Canvas(application, width=380, height=28, bd=0, highlightthickness=0)
    canvas.place(x=0, y=0, width=380, height=28)
    state = SimpleNamespace(
        timeline=canvas,
        _timeline_signature=None,
        _timeline_progress=None,
        _timeline_handle=None,
        playback=SimpleNamespace(snapshot=SimpleNamespace(duration=100, position=0)),
        _chapters=[
            {"start_time": 0, "end_time": 50},
            {"start_time": 100, "end_time": 100},
        ],
        _heatmap=[{"start_time": 0, "end_time": 100, "value": 1.0}],
    )
    state._draw_timeline_base = partial(MediaPlayerWindow._draw_timeline_base, state)
    try:
        for width in (380, 1000):
            canvas.place_configure(width=width)
            pump(application)
            for position in (0, 50, 100):
                snapshot = SimpleNamespace(duration=100, position=position)
                MediaPlayerWindow._update_timeline_value(state, snapshot)
                bounds = canvas.bbox("all")
                assert bounds and 0 <= bounds[0] < bounds[2] <= canvas.winfo_width()
                assert 0 <= bounds[1] < bounds[3] <= canvas.winfo_height(), [
                    (canvas.type(item), canvas.coords(item), canvas.bbox(item))
                    for item in canvas.find_all()
                    if (box := canvas.bbox(item))
                    and (box[1] < 0 or box[3] > canvas.winfo_height())
                ]
    finally:
        canvas.destroy()


def test_resize_keeps_event_loop_and_retained_image_owners_live(
    application, tmp_path, monkeypatch
):
    import hashlib
    import importlib
    import json
    import os
    import time
    from pathlib import Path

    from PIL import Image

    app = application
    rows = seed(app, tmp_path, count=12)
    for row in rows:
        directory = Path(row["vodforge_output_dir"])
        directory.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (320, 180), "#8844bb").save(directory / "thumbnail.jpeg")
    sources = {
        name: Path(importlib.import_module("yt_downloader." + name).__file__).resolve()
        for name in (
            "watch_ui",
            "ui_chrome",
            "archive_artwork",
            "archive_browser_ui",
            "app",
            "media_player_ui",
        )
    }
    before = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in sources.items()
    }
    app._select_focus_view("watch")
    watch = app.focus_watch
    pump(app, 0.7)
    times, durations = [time.monotonic()], []
    token = None

    def heartbeat():
        nonlocal token
        times.append(time.monotonic())
        token = app.after(10, heartbeat)

    token = app.after(10, heartbeat)
    original_render = watch._render

    def measured_render():
        start = time.monotonic()
        original_render()
        durations.append(round((time.monotonic() - start) * 1000, 3))

    monkeypatch.setattr(watch, "_render", measured_render)
    try:
        for width in (1100, 1180, 1280, 1440, 1360, 1260, 1160, 1100):
            app.geometry(f"{width}x600")
            pump(app, 0.04)
            names = set(app.tk.splitlist(app.tk.call("image", "names")))
            assert all(
                watch.canvas.itemcget(item, "image") in names
                for item in watch.canvas.find_all()
                if watch.canvas.type(item) == "image"
            )
            assert watch._depth.cached_bytes <= 8 * 1024 * 1024
        pump(app, 0.3)
    finally:
        if token is not None:
            app.after_cancel(token)
    gaps = [round((b - a) * 1000, 3) for a, b in pairwise(times)]
    after = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in sources.items()
    }
    report = {
        "tier": "source-native scripted geometry; not physical drag or packaged FPS",
        "actual_imports": {name: str(path) for name, path in sources.items()},
        "before_sha256": before,
        "after_sha256": after,
        "heartbeat_gaps_ms": gaps,
        "watch_render_ms": durations,
        "width": app.winfo_width(),
        "height": app.winfo_height(),
    }
    output = Path(os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    (output / "watch-resize-responsiveness.json").write_text(
        json.dumps(report, indent=2)
    )
    assert before == after
    assert len(gaps) >= 8 and len(durations) >= 8
    assert max(gaps) < 250


@pytest.mark.parametrize("size", ["1100x600", "1440x900"])
def test_single_saved_video_panel_keeps_channel_heading_outside_its_bounds(
    application, tmp_path, size
):
    app = application
    seed(app, tmp_path, count=1)
    app.geometry(size)
    app._select_focus_view("watch")
    watch = app.focus_watch
    watch.set_records([{**app.metadata_items[0], "vodforge_user_category": "Travel"}])
    watch._navigate("collections")
    pump(app, 0.3)
    # Enter the visible collection card before testing its single saved video.
    open_collection = next(
        action
        for _box, action in watch._targets
        if getattr(getattr(action, "func", None), "__name__", "") == "_scene_open"
        and getattr(action, "keywords", {}).get("playlist")
    )
    open_collection()
    pump(app, 0.3)
    assert watch._scene_route == "playlist"
    assert len(watch._play_regions) == 1
    cover = watch._play_regions[0]
    labels = {
        watch.canvas.itemcget(item, "text"): bounds
        for bounds, item, _color, _enabled in watch._button_labels
    }
    assert "Play" in labels and "View in Library" in labels
    assert cover[0] >= 0 and cover[2] <= watch.canvas.winfo_width()
    for label in ("Play", "View in Library"):
        box = labels[label]
        assert box[0] >= cover[2] or box[1] >= cover[3]
        assert 0 <= box[0] < box[2] <= watch.canvas.winfo_width()
    region = tuple(float(v) for v in watch.canvas.cget("scrollregion").split())
    for box in (cover, labels["Play"], labels["View in Library"]):
        watch.canvas.yview_moveto(max(0, box[1] - 20) / region[3])
        pump(app, 0.05)
        assert 0 <= box[1] - watch.canvas.canvasy(0) < watch.canvas.winfo_height()


@pytest.mark.parametrize("size", ["1100x600", "1440x900"])
def test_duration_badges_fit_actual_ink_and_thumbnail_for_long_recordings(
    application, tmp_path, size
):
    from copy import deepcopy

    app = application
    rows = seed(app, tmp_path, count=9)
    for index, row in enumerate(rows):
        row["duration"] = (220, 3820, 43420)[index % 3]
        row["playlist_index"] = 5000 + index
    before = deepcopy(rows)
    app._reconcile_library_projection()
    app.geometry(size)
    for surface in ("library", "watch"):
        app._select_focus_view(surface)
        if surface == "library":
            app.video_tree.navigate(None, mode="all")
            view = app.video_tree
        else:
            view = app.focus_watch
            view._scene_open("videos")
        pump(app, 0.35)
        canvas = view.canvas
        labels = canvas.find_withtag("media-badge-text")
        plates = canvas.find_withtag("media-badge-plate")
        assert len(labels) == len(plates) and labels
        widths = []
        for label, plate in zip(labels, plates, strict=True):
            ink, box = canvas.bbox(label), canvas.bbox(plate)
            assert ink is not None and box is not None
            assert ink[0] - box[0] >= 7 and box[2] - ink[2] >= 7
            assert ink[1] - box[1] >= 3 and box[3] - ink[3] >= 3
            assert 0 <= box[0] < box[2] <= canvas.winfo_width()
            widths.append(box[2] - box[0])
            if surface == "library":
                parent = next(
                    bounds
                    for bounds, _ in view._boxes
                    if bounds[0] <= box[0]
                    and box[2] <= bounds[2]
                    and bounds[1] <= box[1] <= bounds[3]
                )
                assert box[3] <= parent[1] + view._artwork_size[1] + 6
        assert max(widths) > min(widths)
        assert any("12:03:40" in canvas.itemcget(label, "text") for label in labels)
        if surface == "library":
            assert any("#500" in canvas.itemcget(label, "text") for label in labels)
    assert app.download_history == before


@pytest.mark.parametrize("size", ["1100x600", "1440x900"])
def test_search_keeps_identity_during_focus_typing_clear_and_theme(
    application, tmp_path, size
):
    app = application
    seed(app, tmp_path)
    app.geometry(size)
    for surface in ("library", "watch"):
        app._select_focus_view(surface)
        field = (
            app._global_search_field
            if surface == "watch"
            else app.focus_library_search_field
        )
        field.entry.focus_force()
        pump(app, 0.1)
        assert field._icon_label.winfo_ismapped()
        assert not field._placeholder.winfo_ismapped()
        assert field._search_icon is not None
        assert str(field._search_icon) in app.tk.call("image", "names")
        assert (
            field._icon_label.winfo_rootx() + field._icon_label.winfo_width()
            <= field.entry.winfo_rootx()
        )
        assert (
            field.winfo_rootx() + field.winfo_width()
            <= app.winfo_rootx() + app.winfo_width()
        )
        field.variable.set("PRIVATE search 日本語")
        pump(app, 0.1)
        assert field.entry.get() == "PRIVATE search 日本語"
        assert field._icon_label.winfo_ismapped()
        field.apply_theme()
        assert str(field._search_icon) in app.tk.call("image", "names")
        field.variable.set("")
        field.entry.focus_force()
        pump(app, 0.1)
        assert field._icon_label.winfo_ismapped()
        assert not field._placeholder.winfo_ismapped()


@pytest.fixture(autouse=True)
def legacy_folder_workspace_for_existing_contracts(application):
    """These contracts target the retained folder workspace, not the default scenes."""
    application._library_scene_action("folders", None)
    application.update()


@pytest.mark.parametrize(
    "label,kind",
    [
        ("Help and feedback", "feedback"),
        ("Rate VODForge", "review"),
        ("Welcome tour", "welcome"),
    ],
)
def test_actual_settings_gear_dispatches_direct_panel(
    application, monkeypatch, label, kind
):
    import tkinter as tk

    from yt_downloader.support_ui import SupportPanel
    from yt_downloader.whats_new_ui import WhatsNewPanel

    app = application
    entries = []

    def posted(menu, *_args):
        entries.extend(
            menu.entrycget(i, "label")
            for i in range(menu.index("end") + 1)
            if menu.type(i) == "command"
        )
        index = next(
            i
            for i in range(menu.index("end") + 1)
            if menu.type(i) == "command" and menu.entrycget(i, "label") == label
        )
        app.after_idle(lambda: menu.invoke(index))

    # Exercise the real gear gesture, Tcl menu callback and modal. Native menu
    # posting is replaced only to make the target selection deterministic.
    monkeypatch.setattr(tk.Menu, "tk_popup", posted)
    button = app.focus_settings_button
    button.event_generate("<ButtonPress-1>", x=12, y=12)
    button.event_generate("<ButtonRelease-1>", x=12, y=12)
    pump(app, 0.3)
    assert entries[entries.index("Help and feedback") + 1] == "Rate VODForge"
    panel = app.engagement.panel
    assert panel.frame.winfo_viewable() and app.grab_current() is panel.frame
    assert app.engagement._menu is None
    if kind == "welcome":
        assert isinstance(panel, WhatsNewPanel)
        panel.close(acknowledge=False)
    else:
        assert isinstance(panel, SupportPanel) and panel.kind == kind
        panel.close()
    pump(app)
    assert app.grab_current() is None


def test_locations_names_types_and_identity_survive_label_refresh(
    application, tmp_path
):
    import json

    from tests.test_archive_models import saved
    from yt_downloader.volume_storage import StorageVolume

    app = application
    app.library_scene._storage_changed = None
    browser = app.video_tree
    rows = [
        saved(tmp_path / "Local" / "one.mp4"),
        saved(Path("/Volumes/StudioA/Media/two.mp4")),
        saved(Path("/Volumes/StudioB/Media/three.mp4")),
        saved(Path("/Volumes/NAS/Media/four.mp4")),
        saved(Path("/Volumes/Offline/Media/five.mp4")),
    ]
    browser._on_folder = lambda *_: None
    browser._on_select = lambda: None
    browser._artwork_source_path = lambda *_: None
    browser.set_records(rows, tuple(range(len(rows))))
    volumes = (
        StorageVolume("/", "Macintosh HD", kind="local"),
        StorageVolume("/Volumes/StudioA", "Studio", kind="external"),
        StorageVolume("/Volumes/StudioB", "Studio", kind="external"),
        StorageVolume("/Volumes/NAS", "Media NAS", kind="network"),
    )
    browser.set_storage_volumes(volumes)
    app._library_scene_action("folders", None)
    pump(app, 0.3)
    labels = browser._location_labels.copy()
    assert len(labels) == 5
    assert {v.subtitle.split(" · ")[0] for v in labels.values()} == {
        "Local",
        "External",
        "Network",
        "Type unknown",
    }
    assert len({(v.title, v.subtitle) for v in labels.values()}) == 5
    identity, selected = next(
        (key, value) for key, value in labels.items() if value.title == "Media NAS"
    )
    browser.location_list.selection_set(identity)
    browser._location_selected(None)
    assert browser.model.path == selected.path
    browser.set_storage_volumes(tuple(reversed(volumes)))
    assert browser.location_list.selection() == (identity,)
    assert browser.model.path == selected.path
    assert browser._location_labels[identity].path == selected.path
    for key, label in labels.items():
        assert (
            browser.location_list.item(key, "text")
            == label.title + "\n" + label.subtitle
        )
        assert str(label.path) in label.tooltip
    output = os.environ.get("VODFORGE_NATIVE_EVIDENCE_DIR")
    if output:
        from yt_downloader.platform_services import capture_own_widget

        picture = capture_own_widget(browser.navigation)
        assert picture is not None
        picture.save(Path(output, "locations-sidebar.png"))
        Path(output, "location-labels.json").write_text(
            json.dumps(
                [
                    {
                        "id": key,
                        "title": value.title,
                        "subtitle": value.subtitle,
                        "path": str(value.path),
                    }
                    for key, value in labels.items()
                ],
                indent=2,
            )
        )
