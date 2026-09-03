from __future__ import annotations

from yt_downloader.media_player_ui import format_playback_time, heatmap_buckets


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
