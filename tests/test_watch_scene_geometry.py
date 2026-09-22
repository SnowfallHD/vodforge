"""Exercise production scene drawing with variable text metrics and small viewports."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from yt_downloader.watch_library import WatchChannel, WatchVideo
from yt_downloader.watch_scene_ui import WatchSceneMixin


class MeasuredPainter:
    def __init__(self, title_height, description_height):
        self.title_height = title_height
        self.description_height = description_height
        self.boxes = {}
        self.texts = []
        self.buttons = []
        self.chip_box = None

    def text(self, x, y, value, **options):
        height = (
            self.title_height
            if options.get("bold") and options.get("size", 0) >= 24
            else self.description_height
            if value == "Description"
            else 18
        )
        item = len(self.boxes) + 1
        self.boxes[item] = (x, y, x + options.get("width", 120), y + height)
        self.texts.append((value, self.boxes[item]))
        return item

    def chips(self, x, y, labels, maximum_width, **_options):
        self.chip_box = (x, y, x + maximum_width, y + 25)

    def button(self, x, y, width, label, callback, **options):
        self.buttons.append(
            (label, (x, y, x + width, y + options.get("height", 44)), callback)
        )


def state(painter, resume):
    canvas = Mock()
    canvas.bbox.side_effect = painter.boxes.get
    return SimpleNamespace(
        _records=[
            {
                "title": "Title",
                "description": "Description",
                "channel_description": "Description",
            }
        ],
        _presentation_rendered=set(),
        _observe_hero=Mock(),
        _progress_for=lambda _row: (
            SimpleNamespace(completed=False, position=20, duration=100, fraction=0.2)
            if resume
            else None
        ),
        canvas=canvas,
        _depth=Mock(),
        _artwork_image=Mock(return_value=object()),
        _play_hero=Mock(),
        _on_play=Mock(),
        _scene_start_queue=Mock(),
        _on_details=Mock(),
        _scene_more=Mock(),
        _channel_profile=lambda _row: {},
    )


def assert_buttons_contained_and_separate(painter, width, height):
    for _label, box, _callback in painter.buttons:
        assert 0 <= box[0] < box[2] <= width
        assert 0 <= box[1] < box[3] < height
    for i, (_, first, _) in enumerate(painter.buttons):
        for _, second, _ in painter.buttons[i + 1 :]:
            assert (
                first[2] <= second[0]
                or second[2] <= first[0]
                or first[3] <= second[1]
                or second[3] <= first[1]
            )


@pytest.mark.parametrize("width", [340, 720, 1364])
@pytest.mark.parametrize("title_height", [42, 100])
@pytest.mark.parametrize("description_height", [18, 50])
@pytest.mark.parametrize("resume", [False, True])
def test_actual_watch_hero_keeps_wrapped_copy_progress_and_controls_apart(
    width, title_height, description_height, resume
):
    p = MeasuredPainter(title_height, description_height)
    view = state(p, resume)
    bottom = WatchSceneMixin._scene_hero(
        view, p, WatchVideo("one", "Title", (0,)), "Playlist", width
    )
    title = next(box for value, box in p.texts if value == "Title")
    description = next(box for value, box in p.texts if value == "Description")
    assert title[3] + 10 <= p.chip_box[1]
    assert p.chip_box[3] + 10 <= description[1]
    assert description[2] <= width - 36
    first_button_y = min(box[1] for _, box, _ in p.buttons)
    if resume:
        track_y = view.canvas.create_line.call_args_list[0].args[1]
        assert description[3] + 20 <= track_y
        assert track_y + 20 <= first_button_y
    else:
        assert description[3] + 20 <= first_button_y
    assert_buttons_contained_and_separate(p, width, bottom - 24)
    p.buttons[0][2]()
    view._play_hero.assert_called_once_with(0)
    view._artwork_image.assert_called_once_with(
        view._records[0], hero_size=(width, bottom - 24)
    )


@pytest.mark.parametrize("width", [340, 720, 1364])
@pytest.mark.parametrize("title_height", [42, 100])
@pytest.mark.parametrize("description_height", [18, 50])
def test_actual_channel_header_keeps_avatar_wrapped_copy_counts_and_actions_apart(
    width, title_height, description_height
):
    p = MeasuredPainter(title_height, description_height)
    view = state(p, False)
    channel = WatchChannel(
        key="key", name="Title", videos=(WatchVideo("one", "Video", (0,)),)
    )
    bottom = WatchSceneMixin._scene_channel_header(view, p, channel, width, ())
    title = next(box for value, box in p.texts if value == "Title")
    description = next(box for value, box in p.texts if value == "Description")
    count = next(box for value, box in p.texts if value.startswith("1 video"))
    assert title[3] + 10 <= description[1]
    assert description[3] + 12 <= count[1]
    assert count[3] + 12 <= min(
        box[1] for label, box, _ in p.buttons if not label.startswith("Back to")
    )
    assert title[2] <= width - 32 and description[2] <= width - 32
    assert title[0] >= 144 or title[1] >= 166
    assert_buttons_contained_and_separate(p, width, bottom - 28)
    next(callback for label, _box, callback in p.buttons if label == "Play Channel")()
    view._scene_start_queue.assert_called_once_with(channel.videos, "channel")
    assert "Shuffle" not in [label for label, _, _ in p.buttons]


@pytest.mark.parametrize("width", [720, 1364])
@pytest.mark.parametrize("has_collection", [False, True])
def test_single_video_home_draws_one_feature_and_compact_playlist_channel_sections(
    monkeypatch, width, has_collection
):
    from tests.test_scene_navigation import drawing_state
    from yt_downloader import watch_scene_ui

    view = drawing_state("home")
    view._records = view._records[:1]
    if not has_collection:
        view._records[0].pop("vodforge_user_category", None)
    view._scene_heading = WatchSceneMixin._scene_heading.__get__(view)
    view._scene_strip = Mock(side_effect=lambda _key, _items, _kind, y, _width: y + 180)
    view._scene_hero = Mock(return_value=380)
    view._scene_small_library = WatchSceneMixin._scene_small_library.__get__(view)
    view._scene_open = Mock()
    view._scene_playlist = Mock()
    view._scene_channel = Mock()
    view._scene_media = Mock()
    painter = SimpleNamespace(text=Mock(), link=Mock())
    monkeypatch.setattr(watch_scene_ui, "ScenePainter", lambda _view: painter)
    WatchSceneMixin._render_streaming_scene(view, width, 5)
    view._scene_hero.assert_called_once()
    view._scene_playlist.assert_called_once()
    view._scene_channel.assert_called_once()
    view._scene_media.assert_not_called()
    headings = [call.args[2] for call in painter.text.call_args_list]
    assert headings == (["Collections"] if has_collection else []) + [
        "Playlists",
        "Channels",
    ]
    if has_collection:
        assert view._scene_strip.call_args.args[0] == "collections"
        assert len(view._scene_strip.call_args.args[1]) == 1
    else:
        view._scene_strip.assert_not_called()
    playlist = view._scene_playlist.call_args.args
    channel = view._scene_channel.call_args.args
    if width >= 800:
        assert playlist[3] == channel[3]
        assert playlist[2] + playlist[4] + 20 <= channel[2]
    else:
        assert playlist[3] + 136 < channel[3]
    assert channel[2] + channel[4] <= width


@pytest.mark.parametrize("width", [340, 720, 1364])
@pytest.mark.parametrize("title_height", [30, 72])
@pytest.mark.parametrize("description_height", [18, 50])
def test_actual_single_episode_card_has_readable_copy_and_owned_actions(
    width, title_height, description_height
):
    p = MeasuredPainter(title_height, description_height)
    view = state(p, False)
    view._records[0].update(
        channel="A very long creator name that cannot fit in the metadata line " * 5,
        duration=451965,
        vodforge_output_type="Original Audio",
    )
    view._scene_route, view._selected_playlist = "playlist", "one"
    view._on_usage = Mock()
    view._play_regions, view._targets = [], []
    view.canvas.find_all.return_value = ()
    bottom = WatchSceneMixin._scene_single_video(
        view, p, WatchVideo("one", "Title", (0,)), 100, width
    )
    title = next(box for value, box in p.texts if value == "Title")
    description = next(box for value, box in p.texts if value == "Description")
    assert title[3] + 20 <= description[1]
    metadata = next(value for value, _box in p.texts if "Original Audio" in value)
    # Essential facts survive truncation of the shared single-video line.
    assert metadata.startswith("125:32:45  \u00b7  Original Audio  \u00b7  ")
    assert description[3] + 18 <= p.buttons[0][1][1]
    assert title[2] < width and description[2] < width
    assert_buttons_contained_and_separate(p, width, bottom - 24)
    p.buttons[0][2]()
    p.buttons[1][2]()
    view._scene_start_queue.assert_called_once_with(
        (WatchVideo("one", "Title", (0,)),), "playlist"
    )
    view._on_details.assert_called_once_with(0)
    assert view._play_regions[0] == view._targets[0][0]
    WatchSceneMixin._scene_single_video(
        view, p, WatchVideo("one", "Title", (0,)), 100, width
    )
    view._on_usage.assert_called_once_with("watch", "singleton_shown")


@pytest.mark.parametrize("route", ["playlist", "channel"])
def test_single_episode_browse_uses_feature_card_without_repeated_recent_item(
    monkeypatch, route
):
    from tests.test_scene_navigation import drawing_state
    from yt_downloader import watch_scene_ui
    from yt_downloader.watch_library import watch_channels, watch_rails

    view = drawing_state(route)
    view._records = view._records[:1]
    view._channel = watch_channels(view._records)[0].key if route == "channel" else ""
    view._selected_playlist = watch_rails(view._records)[0].key
    view._scene_channel_header = Mock(return_value=278)
    view._scene_heading = WatchSceneMixin._scene_heading.__get__(view)
    view._scene_open = Mock()
    view._scene_playlist = Mock()
    view._scene_single_video = Mock(return_value=800)
    view._scene_media = Mock()
    view.show_home = Mock()
    painter = SimpleNamespace(text=Mock(), link=Mock(), button=Mock())
    monkeypatch.setattr(watch_scene_ui, "ScenePainter", lambda _view: painter)
    WatchSceneMixin._render_streaming_scene(view, 1364, 5)
    view._scene_single_video.assert_called_once()
    view._scene_media.assert_not_called()
    assert "Recently Added" not in [
        call.args[2] for call in painter.text.call_args_list
    ]


@pytest.mark.parametrize("width", [268, 380, 620])
@pytest.mark.parametrize("output_type", ["MP4", "Original Audio"])
@pytest.mark.parametrize("duration", ["12:45", "125:12:45"])
def test_actual_hero_chips_reserve_format_and_duration_after_long_names(
    monkeypatch, width, output_type, duration
):
    from tkinter import font as tkfont

    from yt_downloader import scene_components

    texts = []
    canvas = Mock()
    canvas.create_text.side_effect = lambda *_a, **kw: (
        texts.append(kw["text"]) or len(texts)
    )
    view = SimpleNamespace(
        canvas=canvas,
        _button_images=[],
        _fit=lambda value, allocation, _lines, _font: (
            value
            if len(value) * 7 <= allocation
            else value[: max(0, allocation // 7 - 3)] + "..."
        ),
    )
    monkeypatch.setattr(
        tkfont,
        "Font",
        lambda **_kw: SimpleNamespace(measure=lambda value: len(value) * 7),
    )
    monkeypatch.setattr(
        scene_components.ImageTk, "PhotoImage", lambda *_a, **_kw: object()
    )
    scene_components.ScenePainter(view).chips(
        36,
        132,
        [
            "An exceptionally long channel name " * 12,
            "A very long playlist name " * 12,
            output_type,
            duration,
        ],
        width,
        reserve_tail=2,
    )
    assert output_type in texts
    assert duration in texts
    assert 2 <= len(texts) <= 4
    for call in canvas.create_text.call_args_list:
        assert 36 <= call.args[0] <= width + 36
