"""Actual Watch projection owner: identity replacement and bounded query caching."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from yt_downloader.watch_scene_ui import WatchSceneMixin


def test_repaint_reuses_projection_but_new_snapshot_retires_identity():
    view = SimpleNamespace(_records=({"id": "one"},))
    rails = ()
    with patch("yt_downloader.watch_scene_ui.watch_rails", return_value=rails) as group:
        first = WatchSceneMixin._scene_projection(view, "", "", False)
        for _ in range(20):
            assert WatchSceneMixin._scene_projection(view, "", "", False) is first
        assert group.call_count == 1
        view._records = ({"id": "replacement"},)
        WatchSceneMixin._scene_projection(view, "", "", False)
        assert group.call_count == 2
        assert len(view._scene_projection_cache) == 1


def test_channel_query_and_collection_projections_remain_separate_and_bounded():
    view = SimpleNamespace(_records=())
    with patch(
        "yt_downloader.watch_scene_ui.watch_rails", Mock(return_value=())
    ) as group:
        for channel, query, collection in (
            ("", "", False),
            ("creator", "", False),
            ("", "title", False),
            ("", "", True),
        ):
            WatchSceneMixin._scene_projection(view, channel, query, collection)
        assert group.call_count == 4
        for index in range(100):
            WatchSceneMixin._scene_projection(view, "", str(index), False)
        assert len(view._scene_projection_cache) == 4
        assert list(view._scene_projection_cache) == [
            ("", str(i), False) for i in range(96, 100)
        ]


def test_annotation_only_replacement_rebuilds_personal_collection():
    base = {
        "id": "one",
        "title": "Saved",
        "vodforge_output_dir": "/saved",
        "vodforge_user_category": "Before",
    }
    view = SimpleNamespace(_records=(base,))
    before, videos_before = WatchSceneMixin._scene_projection(view, "", "", True)
    view._records = ({**base, "vodforge_user_category": "After"},)
    after, videos_after = WatchSceneMixin._scene_projection(view, "", "", True)
    assert before[0].title == "Before" and after[0].title == "After"
    assert videos_before[0].key == videos_after[0].key
    assert len(view._scene_projection_cache) == 1


def test_record_replacement_releases_hidden_scene_projection_before_repaint():
    import gc
    import weakref

    from yt_downloader.watch_ui import WatchView

    class Record(dict):
        pass

    old = Record(id="retired", title="Saved", vodforge_output_dir="/saved")
    reference = weakref.ref(old)
    view = SimpleNamespace(
        _records=(old,),
        _targets=[],
        _presentation_mode_counts={},
        _initial_mode_set=True,
        _artwork_attempted=set(),
        _presentation_change=Mock(),
        _queue_render=Mock(),
    )
    WatchSceneMixin._scene_projection(view, "", "", False)
    del old
    for index in range(30):
        WatchView.set_records(
            view, ({"id": str(index), "vodforge_output_dir": "/saved"},)
        )
        assert not view._scene_projection_cache
        assert "_scene_projection_records" not in vars(view)
    gc.collect()
    assert reference() is None


def test_same_query_reacts_to_title_edit_without_media_membership_change():
    base = {"id": "one", "title": "Before", "vodforge_output_dir": "/saved"}
    view = SimpleNamespace(_records=(base,))
    _, before = WatchSceneMixin._scene_projection(view, "", "After", False)
    assert before == ()
    view._records = ({**base, "title": "After"},)
    _, after = WatchSceneMixin._scene_projection(view, "", "After", False)
    assert len(after) == 1 and after[0].title == "After"


def test_channel_and_collection_filter_use_current_records():
    view = SimpleNamespace(
        _records=(
            {
                "id": "one",
                "title": "First",
                "channel": "Alice",
                "vodforge_output_dir": "/saved",
                "vodforge_user_category": "Travel",
            },
            {
                "id": "two",
                "title": "Second",
                "channel": "Bob",
                "vodforge_output_dir": "/saved",
                "vodforge_user_category": "Music",
            },
        )
    )
    _, first = WatchSceneMixin._scene_projection(view, "Alice", "", False)
    _, second = WatchSceneMixin._scene_projection(view, "Bob", "", False)
    collections, _ = WatchSceneMixin._scene_projection(view, "", "", True)
    assert [item.title for item in first] == ["First"]
    assert [item.title for item in second] == ["Second"]
    assert {rail.title for rail in collections} == {"Travel", "Music"}


def test_library_repaint_cache_tracks_query_sort_and_annotation_replacement():
    from tests.test_scene_navigation import library_view

    view = library_view("all")
    original = view._matching_media()
    assert view._matching_media() is original
    counts = view._counts()
    assert view._counts() is counts
    view._query = "Video 066"
    assert [row["id"] for _, row in view._matching_media()] == ["66"]
    view._query = ""
    view._sort = "title"
    assert view._matching_media() == original
    assert view._saved()[0][1]["id"] == "0"  # sorting never mutates saved order
    view._records = tuple(
        {**row, "vodforge_user_category": "New"} for row in view._records
    )
    view._filter = "New"
    assert len(view._matching_media()) == 67
    assert {group.title for group in view._groups("collections")} == {"New"}
    for i in range(100):
        view._query = str(i)
        view._matching_media()
    assert len(view._projection_cache) <= 12


def test_library_hidden_record_replacement_releases_projection_snapshot():
    import gc
    import weakref

    from tests.test_scene_navigation import library_view
    from yt_downloader.library_scene_ui import LibraryScene

    class Record(dict):
        pass

    view = library_view("all")
    row = Record(id="retired", title="Before", vodforge_output_dir="/saved")
    ref = weakref.ref(row)
    view._records = (row,)
    view._matching_media()
    view._draw_sidebar = Mock()
    del row
    LibraryScene.set_records(view, ({"id": "new", "vodforge_output_dir": "/saved"},))
    gc.collect()
    assert ref() is None
    assert "_projection_snapshot" not in vars(view)
    assert "_projection_cache" not in vars(view)
