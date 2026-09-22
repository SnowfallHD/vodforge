from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from yt_downloader.watch_library import watch_channels, watch_media_summary, watch_rails
from yt_downloader.watch_scene_ui import WatchSceneMixin


def rows(kinds, *, same_source=False, separate_playlists=False):
    return tuple(
        {
            "id": "source" if same_source else str(i),
            "title": "Saved item",
            "channel": "Creator",
            "channel_id": "creator",
            "webpage_url": "https://example.test/"
            + ("source" if same_source else str(i)),
            "playlist_id": str(i) if separate_playlists else "playlist",
            "playlist_title": "Playlist " + str(i)
            if separate_playlists
            else "Playlist",
            "vodforge_output_dir": f"/saved/{i}",
            "vodforge_output_type": kind,
        }
        for i, kind in enumerate(kinds)
    )


@pytest.mark.parametrize(
    ("kinds", "same", "label", "heading"),
    [
        (("MP4",), False, "1 video", "All Videos"),
        (("MP4", "MP4"), False, "2 videos", "All Videos"),
        (("MP3",), False, "1 track", "All Audio"),
        (("MP3", "MP3"), False, "2 tracks", "All Audio"),
        (("M4A", "Original Audio"), False, "2 tracks", "All Audio"),
        (("MP3", "MP4"), False, "2 items", "All Media"),
        (("MP3", "MP3"), True, "1 track", "All Audio"),
        (("MP4", "MP4"), True, "1 video", "All Videos"),
        (("MP3", "MP4"), True, "1 item", "All Media"),
    ],
)
def test_actual_channel_projection_counts_unique_sources_and_all_saved_kinds(
    kinds, same, label, heading
):
    records = rows(kinds, same_source=same, separate_playlists=True)
    channel = watch_channels(records)[0]
    summary = watch_media_summary(records, channel.videos)
    assert summary.label == label
    assert summary.heading == heading
    assert sorted({i for video in channel.videos for i in video.indices}) == list(
        range(len(records))
    )


@pytest.mark.parametrize(
    ("kinds", "label", "heading"),
    [
        (("MP3", "MP3"), "2 tracks", "All Audio"),
        (("MP3", "MP4"), "2 items", "All Media"),
        (("MP4", "MP4"), "2 videos", "All Videos"),
    ],
)
def test_actual_watch_cards_header_and_browse_heading_use_shared_media_truth(
    monkeypatch, kinds, label, heading
):
    from tests.test_scene_navigation import drawing_state
    from yt_downloader import watch_scene_ui

    records = rows(kinds)
    texts = []
    painter = SimpleNamespace(
        text=lambda _x, _y, value, **_kw: texts.append(value) or len(texts),
        icon=Mock(),
        button=Mock(),
        link=Mock(),
    )
    state = drawing_state("channel")
    state._records = records
    state.canvas.bbox.return_value = (0, 0, 300, 80)
    state._navigate = Mock()
    state._channel_profile = lambda _row: {}
    state._scene_open = Mock()
    channel = watch_channels(records)[0]
    rail = watch_rails(records)[0]
    WatchSceneMixin._scene_playlist(state, painter, rail, 0, 0, 260)
    assert label in texts
    texts.clear()
    WatchSceneMixin._scene_channel(state, painter, channel, 0, 0, 260)
    assert label in texts
    texts.clear()
    WatchSceneMixin._scene_channel_header(state, painter, channel, 1380, (rail,))
    assert any(value.startswith(label + "  ") for value in texts)
    state._channel = channel.key
    state._scene_channel_header = Mock(return_value=278)
    state._scene_heading = WatchSceneMixin._scene_heading.__get__(state)
    state._scene_media = Mock()
    state._scene_playlist = Mock()
    monkeypatch.setattr(watch_scene_ui, "ScenePainter", lambda _view: painter)
    texts.clear()
    WatchSceneMixin._render_streaming_scene(state, 1380, 5)
    assert heading in texts


@pytest.mark.parametrize(
    ("kind", "description"),
    [
        ("MP3", "Your saved audio, ready to play."),
        ("Original Audio", "Your saved audio, ready to play."),
        ("MP4", "Your saved video, ready to watch."),
    ],
)
def test_actual_single_item_card_uses_truthful_fallback_copy(kind, description):
    from tests.test_watch_scene_geometry import MeasuredPainter, state

    painter = MeasuredPainter(30, 18)
    view = state(painter, False)
    view._records = rows((kind,))
    view._scene_route, view._selected_playlist = "playlist", "playlist"
    view._on_usage = Mock()
    view._play_regions, view._targets = [], []
    view.canvas.find_all.return_value = ()
    video = watch_rails(view._records)[0].videos[0]
    WatchSceneMixin._scene_single_video(view, painter, video, 0, 1380)
    assert description in [value for value, _box in painter.texts]


@pytest.mark.parametrize(
    ("kinds", "preferred"),
    [
        (("MP3", "MP4"), 1),
        (("Original audio", "MP4"), 1),
        (("MP4", "MP3"), 0),
    ],
)
@pytest.mark.parametrize("separate_playlists", [False, True])
def test_actual_home_and_channel_playback_keep_video_preference_while_retaining_audio_variants(
    monkeypatch, kinds, preferred, separate_playlists
):
    from tests.test_scene_navigation import drawing_state
    from yt_downloader import watch_scene_ui

    records = rows(kinds, same_source=True, separate_playlists=separate_playlists)
    channel = watch_channels(records)[0]
    assert set(channel.videos[0].indices) == {0, 1}
    assert channel.videos[0].indices[0] == preferred
    view = drawing_state("home")
    view._records = records
    view._scene_hero = Mock(return_value=380)
    view._scene_small_library = Mock(return_value=600)
    painter = SimpleNamespace(
        text=Mock(return_value=1), button=Mock(), icon=Mock(), link=Mock()
    )
    monkeypatch.setattr(watch_scene_ui, "ScenePainter", lambda _view: painter)
    WatchSceneMixin._render_streaming_scene(view, 1380, 5)
    assert view._scene_hero.call_args.args[1].indices[0] == preferred
    view.canvas.bbox.return_value = (0, 0, 300, 80)
    view._channel_profile = lambda _row: {}
    WatchSceneMixin._scene_channel_header(
        view, painter, channel, 1380, watch_rails(records)
    )
    play = next(
        call.args[4]
        for call in painter.button.call_args_list
        if call.args[3] == "Play Channel"
    )
    play()
    view._scene_start_queue.assert_called_once_with(channel.videos, "channel")
    assert watch_media_summary(records, channel.videos).label == "1 item"


@pytest.mark.parametrize("selected", ["0", "missing"])
def test_playlist_presentation_counts_match_its_actual_content(monkeypatch, selected):
    from tests.test_scene_navigation import drawing_state
    from yt_downloader import watch_scene_ui

    view = drawing_state("playlist")
    view._records = rows(("MP4", "MP4", "MP4"), separate_playlists=True)
    rails = watch_rails(view._records)
    view._selected_playlist = rails[0].key if selected == "0" else "missing"
    view._scene_single_video = Mock(return_value=300)
    view._scene_media_window = Mock(return_value=300)
    view._scene_heading = Mock(return_value=100)
    painter = SimpleNamespace(text=Mock(return_value=1), button=Mock())
    monkeypatch.setattr(watch_scene_ui, "ScenePainter", lambda _view: painter)
    WatchSceneMixin._render_streaming_scene(view, 1000, 3)
    expected = 1 if selected == "0" else 0
    assert view._presentation_matching == expected
    assert view._presentation_mode_eligible == expected
    if expected:
        assert view._scene_single_video.call_args.args[1] == rails[0].videos[0]
    else:
        assert view._scene_media_window.call_args.args[1] == ()
