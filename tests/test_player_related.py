"""Related media retains source identity, current ownership and bounded reachability."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from yt_downloader import player_scene_ui
from yt_downloader.archive_library_ui import ArchiveLibraryMixin
from yt_downloader.player_related import player_related_plan
from yt_downloader.player_scene_ui import PlayerRelatedView, PlayerSceneMixin


def record(name, *, playlist="a", position=1, provider="youtube.com", output="MP4"):
    return {
        "id": name,
        "title": name,
        "channel_id": "channel-a",
        "channel": "Creator",
        "playlist_id": playlist,
        "playlist_title": playlist,
        "playlist_index": position,
        "webpage_url": f"https://{provider}/watch/{name}",
        "vodforge_output_dir": f"/saved/{provider}/{playlist}/{name}/{output}",
        "vodforge_output_type": output,
    }


def ids(plan, rows):
    return [rows[v.indices[0]]["id"] for v in plan.up_next]


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [record("one")],
        [record("one"), record("one", output="MP3")],
        [record("one"), record("one", playlist="b")],
    ],
)
def test_lone_source_has_no_manufactured_related_rows(rows):
    plan = player_related_plan(rows, record("one"))
    assert not plan.up_next and not plan.recent


def test_current_playlist_order_precedes_unrelated_library_order():
    current = record("middle", position=2)
    rows = [
        record("unrelated", playlist="z"),
        record("after", position=3),
        current,
        record("before", position=1),
        record("last", position=4),
    ]
    assert ids(player_related_plan(rows, current), rows) == [
        "after",
        "last",
        "before",
        "unrelated",
    ]


def test_current_item_is_excluded_across_every_playlist_and_variant():
    current = record("same")
    rows = [
        record("same", playlist="b"),
        record("same", output="MP3"),
        current,
        record("other", position=2),
    ]
    plan = player_related_plan(rows, current)
    assert ids(plan, rows) == ["other"]
    assert len(plan.recent) == 2


def test_identical_provider_ids_are_not_merged_across_providers():
    current = record("same")
    rows = [current, record("same", provider="vimeo.com")]
    plan = player_related_plan(rows, current)
    assert len(plan.up_next) == 1
    assert rows[plan.up_next[0].indices[0]]["webpage_url"].startswith(
        "https://vimeo.com"
    )


def test_related_uses_preferred_variant_without_discarding_saved_versions():
    current = record("one")
    rows = [
        current,
        record("two", output="MP3"),
        record("two", output="Original Audio"),
        record("two", output="MP4"),
        record("two", playlist="b", output="MP4"),
    ]
    plan = player_related_plan(rows, current)
    assert len(plan.up_next) == 1
    assert plan.up_next[0].indices == (3, 4, 2, 1)


def test_unsaved_preview_rows_cannot_become_player_suggestions():
    current = record("one")
    rows = [current, {"id": "preview", "title": "Preview"}]
    assert not player_related_plan(rows, current).up_next


def test_recent_order_follows_canonical_history_order():
    rows = [
        record("newest", position=30),
        record("middle", position=20),
        record("oldest", position=10),
    ]
    plan = player_related_plan(rows, rows[-1])
    assert [rows[v.indices[0]]["id"] for v in plan.recent] == [
        "newest",
        "middle",
        "oldest",
    ]


def test_absent_current_owner_still_offers_only_existing_saved_media():
    rows = [record("one"), record("two", playlist="b")]
    assert set(ids(player_related_plan(rows, record("removed")), rows)) == {
        "one",
        "two",
    }


def test_related_shown_is_emitted_once_per_actual_visible_transition():
    state = SimpleNamespace(_related_visible=False, _on_presented=Mock())
    for visible in (False, False, True, True, True):
        PlayerRelatedView._observe_related_presentation(state, visible)
    assert state._on_presented.call_count == 1
    PlayerRelatedView._observe_related_presentation(state, False)
    PlayerRelatedView._observe_related_presentation(state, True)
    assert state._on_presented.call_count == 2


@pytest.mark.parametrize("details", [False, True])
def test_closed_player_cannot_dispatch_or_report_related_action(details):
    state = SimpleNamespace(
        _closed=True,
        _on_feature=Mock(),
        _on_record_details=Mock(),
        _on_related_play=Mock(),
    )
    PlayerSceneMixin._select_related_record(state, record("one"), details=details)
    state._on_feature.assert_not_called()
    state._on_record_details.assert_not_called()
    state._on_related_play.assert_not_called()


@pytest.mark.parametrize("index", [-1, 1, 99])
def test_invalidated_related_index_cannot_dispatch(index):
    state = SimpleNamespace(
        _related_view=SimpleNamespace(_records=[record("one")]),
        _select_related_record=Mock(),
    )
    PlayerSceneMixin._related_index(state, index, details=False)
    state._select_related_record.assert_not_called()


def test_related_selection_uses_latest_canonical_owner_not_old_index_or_copy():
    captured = record("one")
    current = dict(captured, title="Updated title")
    state = SimpleNamespace(
        metadata_items=[record("other"), current],
        status_var=Mock(),
        _play_selected_library_item=Mock(),
    )
    ArchiveLibraryMixin._archive_player_related_play(state, captured)
    state._play_selected_library_item.assert_called_once_with(current)


def test_removed_related_owner_cannot_open_another_record():
    state = SimpleNamespace(
        metadata_items=[record("other")],
        status_var=Mock(),
        _play_selected_library_item=Mock(),
    )
    ArchiveLibraryMixin._archive_player_related_play(state, record("removed"))
    state._play_selected_library_item.assert_not_called()
    state.status_var.set.assert_called_once()


def test_detail_owner_is_resolved_again_after_player_close_reorders_projection():
    captured, other = record("one"), record("other")
    state = SimpleNamespace(
        metadata_items=[captured, other],
        status_var=Mock(),
        _archive_reveal_library_details=Mock(),
    )
    state._archive_cancel_playback = lambda: setattr(
        state, "metadata_items", [other, captured]
    )
    ArchiveLibraryMixin._archive_player_details(state, captured)
    state._archive_reveal_library_details.assert_called_once_with(1)


def test_removed_owner_during_close_cannot_redirect_detail_view():
    captured = record("one")
    state = SimpleNamespace(
        metadata_items=[captured],
        status_var=Mock(),
        _archive_reveal_library_details=Mock(),
    )
    state._archive_cancel_playback = lambda: setattr(
        state, "metadata_items", [record("other")]
    )
    ArchiveLibraryMixin._archive_player_details(state, captured)
    state._archive_reveal_library_details.assert_not_called()


def test_related_page_reaches_every_item_without_unbounded_render(monkeypatch):
    rows = [record(str(i), position=i) for i in range(68)]
    plan = player_related_plan(rows, rows[0])
    state = SimpleNamespace(
        _related_plan=plan,
        _related_section="More to watch",
        _queue_keys=None,
        _section_kind="side",
        _current=rows[0],
        _on_avatar=Mock(),
        _artwork_image=Mock(return_value=None),
        _browse_heading=Mock(),
        _browse_footer=Mock(),
        _card_width=180,
        _card_height=81,
        _open_related=Mock(),
        _scene_heading=lambda p, label, y, width: y + 44,
        _paint_focus=Mock(),
        _artwork_request=Mock(),
        _presentation_settle=Mock(),
        _observe_related_presentation=Mock(),
        canvas=Mock(),
    )
    drawn, pages = [], []
    state._scene_media = lambda p, v, x, y: drawn.append(v.key)
    state._scene_pager = lambda p, y, page: pages.append(page) or y + 44
    monkeypatch.setattr(player_scene_ui, "ScenePainter", lambda _: Mock())
    seen = set()
    for page_index in range(12):
        state._page = page_index
        drawn.clear()
        PlayerRelatedView._render_streaming_scene(state, 980, 2)
        assert len(drawn) <= 10
        seen.update(drawn)
    assert seen == {v.key for v in plan.up_next}
    assert pages[-1].index == 11


def test_closed_player_does_not_rebuild_related_view_on_library_refresh():
    related = Mock()
    state = SimpleNamespace(_related_view=related, _closed=True)
    PlayerSceneMixin.set_library_records(state, [record("one")])
    related.set_records.assert_not_called()


@pytest.mark.parametrize("details", [False, True])
def test_related_producer_reports_bounded_action_without_media_content(details):
    from yt_downloader.telemetry_features import FEATURE_ACTIONS, validate_dimensions

    events = []
    state = SimpleNamespace(
        _closed=False,
        _on_feature=lambda action, **fields: events.append((action, fields)),
        _on_record_details=Mock(),
        _on_related_play=Mock(),
    )
    private = record("Private title and filename")
    PlayerSceneMixin._select_related_record(state, private, details=details)
    action, fields = events[0]
    assert action in FEATURE_ACTIONS["player"]
    assert fields == {} and validate_dimensions(fields) == {}
    assert "Private" not in repr(events)


def test_visible_related_producer_uses_content_free_event():
    from yt_downloader.telemetry_features import FEATURE_ACTIONS

    events = []
    state = SimpleNamespace(_closed=False, _on_feature=events.append)
    PlayerSceneMixin._related_presented(state)
    assert events == ["related_shown"]
    assert events[0] in FEATURE_ACTIONS["player"]


def test_recent_player_row_supplies_all_items_to_shared_horizontal_owner(monkeypatch):
    from tests.test_scene_navigation import drawing_state

    rows = [record(str(i), position=i) for i in range(68)]
    state = drawing_state("videos")
    state._records = tuple(rows)
    state._related_plan = player_related_plan(rows, rows[0])
    state._section_kind, state._related_section, state._queue_keys = "recent", "", None
    state._current = rows[0]
    state._on_avatar = Mock()
    state._open_related = Mock()
    state._scene_heading = lambda p, label, y, width, action=None: y + 44
    state._scene_strip = Mock(return_value=260)
    state._observe_related_presentation = Mock()
    monkeypatch.setattr(player_scene_ui, "ScenePainter", lambda _: Mock())
    PlayerRelatedView._render_streaming_scene(state, 980, 3)
    args = state._scene_strip.call_args.args
    assert args[0] == "recent" and args[1] == state._related_plan.recent
    assert len(args[1]) == 68
