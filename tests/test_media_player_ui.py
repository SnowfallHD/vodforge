from __future__ import annotations

import inspect

from yt_downloader import media_player_ui
from yt_downloader.media_player_ui import (
    PREVIEW_HEIGHT,
    PREVIEW_WIDTH,
    apply_preview_image,
    bounded_content_rows,
    format_playback_time,
    heatmap_buckets,
)


class PreviewLabelSpy:
    def __init__(self) -> None:
        self.options: dict[str, object] = {}

    def configure(self, **options: object) -> None:
        self.options = options


def test_playback_time_formats_compactly() -> None:
    assert format_playback_time(0) == "0:00"
    assert format_playback_time(65.9) == "1:05"
    assert format_playback_time(3661) == "1:01:01"


def test_heatmap_buckets_are_bounded_and_deterministic() -> None:
    points = [
        {"start_time": 0.0, "end_time": 10.0, "value": 0.25},
        {"start_time": 40.0, "end_time": 60.0, "value": 0.9},
    ]
    assert heatmap_buckets(points, 100.0, 5) == (0.25, 0.0, 0.9, 0.0, 0.0)
    assert heatmap_buckets(points, 0.0, 5) == ()


def test_player_detail_surfaces_stay_compact_and_bounded() -> None:
    assert bounded_content_rows(0) == 3
    assert bounded_content_rows(4) == 4
    assert bounded_content_rows(40) == 8
    assert bounded_content_rows("Short note") == 3
    assert bounded_content_rows("x" * 500) == 8


def test_preview_image_replaces_text_dimensions_with_pixel_dimensions() -> None:
    label = PreviewLabelSpy()
    image = object()

    apply_preview_image(label, image)  # type: ignore[arg-type]

    assert label.options == {
        "image": image,
        "text": "",
        "width": PREVIEW_WIDTH,
        "height": PREVIEW_HEIGHT,
    }


def test_player_uses_shared_icon_assets_without_a_fifth_button_role() -> None:
    source = inspect.getsource(media_player_ui.MediaPlayerWindow)

    assert 'load_ui_icon("play"' in source
    assert 'load_ui_icon("pause"' in source
    assert '"volume-2"' in source
    assert 'style="Accent.TButton"' in source
    assert "PlayerIcon.TButton" not in inspect.getsource(media_player_ui)
