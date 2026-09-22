"""Execute real scene routing and the callbacks drawn by those renderers."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from yt_downloader import library_scene_layout, watch_scene_ui
from yt_downloader.library_scene_ui import LibraryScene
from yt_downloader.watch_ui import WatchView


class Painter:
    def __init__(self, view):
        self.view = view

    def button(self, _x, _y, _width, label, callback, **_options):
        self.view.buttons[label] = callback

    def link(self, _x, _y, label, callback, **_options):
        self.view.buttons[label] = callback

    def text(self, *_args, **_options):
        pass

    def icon(self, *_args, **_options):
        pass


def records(count=67):
    return tuple(
        {
            "id": str(i),
            "title": f"Video {i:03}",
            "channel": f"Channel {i:03}",
            "channel_id": f"channel-{i}",
            "playlist_id": f"playlist-{i}",
            "playlist_title": f"Playlist {i:03}",
            "vodforge_user_category": f"Collection {i:03}",
            "vodforge_output_dir": f"/saved/{i}",
            "vodforge_output_type": "MP4",
        }
        for i in range(count)
    )


def drawing_state(route):
    state = SimpleNamespace(
        _records=records(),
        _route=route,
        _scene_route=route,
        _page=0,
        _sort="recent",
        _query="",
        _filter="",
        _group_key="",
        _group_kind="",
        _category="",
        _channel="",
        _selected_playlist="",
        _playlist_is_collection=False,
        _selected=set(),
        _selection_mode=False,
        _start_selection=Mock(),
        _targets=[],
        _context_targets=[],
        _open_item_menu=Mock(),
        _button_images=[],
        _button_labels=[],
        _rendered_count=0,
        _matching_count=0,
        _card_width=210,
        _card_height=118,
        _presentation_rendered=set(),
        _progress_for=None,
        _browse_heading=Mock(),
        _browse_footer=Mock(),
        search=SimpleNamespace(get=lambda: ""),
        winfo_toplevel=lambda: SimpleNamespace(),
        canvas=Mock(bbox=Mock(return_value=None)),
        _depth=Mock(),
        _search_field=Mock(),
        _project_search_backdrop=Mock(),
        buttons={},
        drawn=[],
        _fit=lambda text, *_args: text,
        _surface=lambda *_args, **_kwargs: None,
        _center=lambda *_args, **_kwargs: None,
        _artwork_image=lambda *_args, **_kwargs: None,
        _on_play=Mock(),
        _scene_start_queue=Mock(),
        _on_details=Mock(),
        _on_usage=Mock(),
        _action=Mock(),
        _group_menu=Mock(),
        _toggle_selection=Mock(),
        show_details=Mock(),
        _clear_selection=Mock(),
        _sort_menu=Mock(),
        _filter_menu=Mock(),
        _clear_filters=Mock(),
        _queue_render=Mock(),
        _presentation_change=Mock(),
        _paint_focus=Mock(),
        _artwork_request=Mock(),
        _presentation_settle=Mock(),
    )
    # The drawing-only fixture has no Tk widgets; native tests exercise SceneRail.
    state._scene_strip = lambda _key, _items, _kind, y, _width: y + 180
    state._scene_projection = watch_scene_ui.WatchSceneMixin._scene_projection.__get__(
        state
    )
    state._scene_media_window = (
        watch_scene_ui.WatchSceneMixin._scene_media_window.__get__(state)
    )
    state._scene_items_window = (
        watch_scene_ui.WatchSceneMixin._scene_items_window.__get__(state)
    )
    state._scene_route_key = watch_scene_ui.WatchSceneMixin._scene_route_key.__get__(
        state
    )
    state._remember_scene_anchor = (
        watch_scene_ui.WatchSceneMixin._remember_scene_anchor.__get__(state)
    )
    for name in (
        "_catalog_route_key",
        "_catalog_item_key",
        "_remember_catalog_anchor",
        "_catalog_rows",
    ):
        setattr(
            state,
            name,
            getattr(library_scene_layout.LibrarySceneLayout, name).__get__(state),
        )
    state._reset_catalog_viewport = LibraryScene._reset_catalog_viewport.__get__(state)
    state.canvas.canvasy.return_value = 0
    state.canvas.winfo_height.return_value = 800
    return state


def library_view(route):
    state = drawing_state(route)
    for name in (
        "_saved",
        "_matching_media",
        "_groups",
        "_counts",
        "_change_page",
        "_group_open",
    ):
        setattr(state, name, getattr(LibraryScene, name).__get__(state))
    state._is_audio = LibraryScene._is_audio
    for name in (
        "_browse",
        "_categories",
        "_toolbar",
        "_paging_controls",
        "_empty_panel",
        "_checkbox",
        "_duration",
        "_pill",
    ):
        setattr(
            state,
            name,
            getattr(library_scene_layout.LibrarySceneLayout, name).__get__(state),
        )
    state.navigate = lambda route: setattr(state, "_route", route)

    def media(p, index, row, *bounds):
        state.drawn.append(index)
        library_scene_layout.LibrarySceneLayout._media_card(
            state, p, index, row, *bounds
        )

    def group(p, item, kind, *bounds):
        state.drawn.append(item.videos[0].indices[0])
        library_scene_layout.LibrarySceneLayout._collection_card(
            state, p, item, kind, *bounds
        )

    state._media_card = media
    state._collection_card = group
    state.render = lambda: state._browse(Painter(state), 1116)
    return state


def watch_view(route):
    state = drawing_state(route)
    state.canvas.yview.return_value = (0.0, 1.0)
    for name in (
        "_render_streaming_scene",
        "_scene_heading",
        "_scene_pager",
        "_scene_open",
        "show_home",
    ):
        setattr(
            state, name, getattr(watch_scene_ui.WatchSceneMixin, name).__get__(state)
        )
    state._change_page = WatchView._change_page.__get__(state)
    state._scene_media = lambda p, video, *_bounds: state.drawn.append(video.indices[0])
    state._scene_single_video = lambda p, video, y, _width: (
        state.drawn.append(video.indices[0]) or y + 280
    )
    state._scene_channel = lambda p, channel, *_bounds: state.drawn.append(
        channel.videos[0].indices[0]
    )
    state._scene_playlist = lambda p, rail, *_bounds: state.drawn.append(
        rail.videos[0].indices[0]
    )
    state.render = lambda: state._render_streaming_scene(1116, 5)
    return state


def visit_all(state):
    found = []
    for _ in range(20):
        state.drawn = []
        state.buttons = {}
        state._targets = []
        state.render()
        assert len(state.drawn) <= 25
        found.extend(state.drawn)
        if "Next" not in state.buttons:
            break
        state.buttons["Next"]()
    assert sorted(found) == list(range(len(state._records)))
    assert len(found) == len(set(found))
    if state._page:
        before = state._page
        state.buttons["Previous"]()
        assert state._page == before - 1


@pytest.mark.parametrize("route", ["all", "channels", "playlists", "collections"])
def test_library_continuous_renderer_reaches_all_records_and_returns_to_start(
    monkeypatch, route
):
    monkeypatch.setattr(library_scene_layout, "ScenePainter", Painter)
    state = library_view(route)
    found = set()
    for top in range(0, 16000, 300):
        state.canvas.canvasy.return_value = top
        state.drawn = []
        state.render()
        found.update(state.drawn)
        assert len(state.drawn) <= 35
    assert found == set(range(len(state._records)))
    state.canvas.canvasy.return_value = 0
    state.drawn = []
    state.render()
    assert state.drawn[0] == 0


@pytest.mark.parametrize("route", ["channels", "playlists", "collections"])
def test_watch_continuous_group_renderer_reaches_all_records(monkeypatch, route):
    monkeypatch.setattr(watch_scene_ui, "ScenePainter", Painter)
    state = watch_view(route)
    found = set()
    for top in range(0, 4000, 200):
        state.canvas.canvasy.return_value = top
        state.drawn = []
        state.render()
        assert len(state.drawn) <= 55
        found.update(state.drawn)
        assert "Next" not in state.buttons
    assert found == set(range(len(state._records)))
    state.canvas.canvasy.return_value = 0
    state.drawn = []
    state.render()
    assert state.drawn[0] == 0


def test_continuous_truncation_negative_control_is_detected(monkeypatch):
    monkeypatch.setattr(watch_scene_ui, "ScenePainter", Painter)
    state = watch_view("playlists")
    original = state._scene_items_window
    state._scene_items_window = lambda p, items, y, columns, kind: original(
        p, items[:48], y, columns, kind
    )
    found = set()
    for top in range(0, 4000, 200):
        state.canvas.canvasy.return_value = top
        state.drawn = []
        state.render()
        found.update(state.drawn)
    assert found != set(range(len(state._records)))


def test_library_group_card_routes_to_exact_membership_after_scrolling():
    state = library_view("playlists")
    state.canvas.canvasy.return_value = 2300
    state.render()
    assert 48 in state.drawn
    # The first target is the first collection's actual open callback.
    group_open = next(
        callback
        for _box, callback in state._targets
        if getattr(callback, "func", None) == state._group_open
        and "playlist-48" in str(callback.args)
    )
    group_open()
    assert state._route == "all" and state._page == 0
    assert [i for i, _row in state._matching_media()] == [48]


def test_library_filter_change_clamps_real_render_to_nonempty_page():
    state = library_view("all")
    state._page = 3
    state._filter = "Collection 066"
    state.render()
    assert state.drawn == [66] and state._page == 0


def test_watch_personal_collection_callback_keeps_collection_membership(monkeypatch):
    monkeypatch.setattr(watch_scene_ui, "ScenePainter", Painter)
    view = watch_view("collections")
    from yt_downloader.watch_library import watch_rails

    rail = watch_rails(view._records, collection_mode=True)[48]
    view._scene_open("playlist", playlist=rail.key)
    view.drawn = []
    view.render()
    assert view.drawn == [48]


def test_removed_watch_playlist_does_not_fall_back_to_unrelated_videos(monkeypatch):
    monkeypatch.setattr(watch_scene_ui, "ScenePainter", Painter)
    view = watch_view("playlist")
    view._selected_playlist = "missing-playlist"
    view.render()
    assert view.drawn == []


@pytest.mark.parametrize("route", ["watch", "library", "forge", "activity"])
def test_top_level_navigation_has_an_obvious_home_without_overwriting_internal_restoration(
    route,
):
    from yt_downloader.app import DownloaderApp

    state = SimpleNamespace(
        _archive_overlay=object(),
        _archive_cancel_playback=Mock(),
        focus_watch=SimpleNamespace(show_home=Mock()),
        library_scene=SimpleNamespace(navigate=Mock()),
        _select_focus_view=Mock(),
    )
    DownloaderApp._navigate_focus_view(state, route)
    state._select_focus_view.assert_called_once_with(route)
    if route in {"watch", "library"}:
        state._archive_cancel_playback.assert_called_once()
    else:
        state._archive_cancel_playback.assert_not_called()
    if route == "watch":
        state.focus_watch.show_home.assert_called_once()
        state.library_scene.navigate.assert_not_called()
    elif route == "library":
        state.library_scene.navigate.assert_called_once_with("home")
        state.focus_watch.show_home.assert_not_called()
    else:
        state.focus_watch.show_home.assert_not_called()
        state.library_scene.navigate.assert_not_called()


def test_actual_back_to_watch_control_keeps_its_complete_label(monkeypatch):
    from yt_downloader import scene_components

    texts = []
    view = drawing_state("videos")
    view._records = ()
    view.show_home = Mock()
    view._scene_heading = watch_scene_ui.WatchSceneMixin._scene_heading.__get__(view)
    view._fit = lambda value, allocation, _lines, _font: (
        value if len(value) * 7 <= allocation else "..."
    )
    view.canvas.create_text.side_effect = lambda *_args, **kwargs: (
        texts.append(kwargs["text"]) or len(texts)
    )
    monkeypatch.setattr(
        scene_components.ImageTk, "PhotoImage", lambda *_a, **_k: object()
    )
    watch_scene_ui.WatchSceneMixin._render_streaming_scene(view, 700, 2)
    assert "Back to Watch" in texts
    assert "..." not in texts


@pytest.mark.parametrize("view", ["forge", "library", "watch", "activity"])
def test_keyboard_search_preserves_query_and_view_until_user_edits(view):
    from yt_downloader.app import DownloaderApp

    entry = SimpleNamespace(focus_set=Mock(), selection_range=Mock())
    state = SimpleNamespace(
        _global_search_field=SimpleNamespace(entry=entry),
        _global_search_var=SimpleNamespace(get=lambda: "existing query"),
        _focus_selected_view=view,
        _archive_usage=Mock(),
    )
    assert DownloaderApp._focus_global_search(state) == "break"
    entry.focus_set.assert_called_once()
    entry.selection_range.assert_called_once_with(0, "end")
    assert state._global_search_var.get() == "existing query"
    assert state._focus_selected_view == view
    state._archive_usage.assert_called_once_with(
        "watch" if view == "watch" else "library", "search_focused"
    )


def test_watch_continuous_media_window_reaches_all_items_and_returns_to_start(
    monkeypatch,
):
    monkeypatch.setattr(watch_scene_ui, "ScenePainter", Painter)
    state = watch_view("videos")
    found = set()
    for top in range(0, 4000, 300):
        state.canvas.canvasy.return_value = top
        state.drawn = []
        state.render()
        assert len(state.drawn) <= 40
        found.update(state.drawn)
    assert found == set(range(len(state._records)))
    state.canvas.canvasy.return_value = 0
    state.drawn = []
    state.render()
    assert state.drawn[0] == 0
    assert "Next" not in state.buttons


def test_horizontal_row_usage_is_bounded_to_current_visit():
    state = SimpleNamespace(_scene_rails={"recent": object()}, _on_usage=Mock())
    for _ in range(100):
        watch_scene_ui.WatchSceneMixin._scene_catalog_scroll_used(state)
    state._on_usage.assert_called_once_with("watch", "catalog_scrolled")
    state._closed = True
    state._scene_catalog_scroll_seen = False
    watch_scene_ui.WatchSceneMixin._scene_catalog_scroll_used(state)
    assert state._on_usage.call_count == 1


def test_home_rails_keep_collections_between_recent_and_playlists(monkeypatch):
    state = watch_view("home")
    state._scene_hero = lambda *_args: 300
    state._scene_strip = lambda key, items, kind, y, width: (
        state.drawn.append((key, len(items))) or y + 180
    )
    monkeypatch.setattr(watch_scene_ui, "ScenePainter", Painter)
    state.render()
    assert state.drawn == [
        ("recent", 67),
        ("collections", 67),
        ("playlists", 67),
        ("channels", 67),
    ]


def test_watch_back_restores_search_scope_and_scroll_after_playlist_navigation():
    view = watch_view("channel")
    query = ["saved title"]
    view.search = SimpleNamespace(
        get=lambda: query[0], set=lambda text: query.__setitem__(0, text)
    )
    view._channel = "creator"
    view.canvas.yview.return_value = (0.42, 0.6)
    view._render = Mock()
    view._scene_open("playlist", playlist="playlist-1")
    assert query[0] == "" and view._channel == "creator"
    assert watch_scene_ui.WatchSceneMixin._scene_back_label(view) == "Back to results"
    watch_scene_ui.WatchSceneMixin._scene_back(view)
    assert query[0] == "saved title"
    assert view._scene_route == "channel" and view._channel == "creator"
    view.canvas.yview_moveto.assert_called_with(0.42)


def test_global_search_display_follows_active_view_without_reapplying_filters():
    from yt_downloader.app import DownloaderApp

    value = ["old display"]
    calls = []
    state = SimpleNamespace(
        _focus_selected_view="watch",
        focus_watch=SimpleNamespace(search=SimpleNamespace(get=lambda: "")),
        library_search_var=SimpleNamespace(get=lambda: "library query"),
    )

    def set_text(text):
        value[0] = text
        calls.append(text)
        DownloaderApp._global_library_search(state)

    state._global_search_var = SimpleNamespace(get=lambda: value[0], set=set_text)
    DownloaderApp._sync_global_search_from_view(state, "watch")
    assert value[0] == "" and calls == [""]
    DownloaderApp._sync_global_search_from_view(state, "library")
    assert calls == [""]
    state._focus_selected_view = "library"
    DownloaderApp._sync_global_search_from_view(state, "library")
    assert value[0] == "library query" and not state._global_search_syncing
