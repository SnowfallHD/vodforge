"""Import producers report durable outcomes with bounded, content-free data."""

import pytest

from yt_downloader.telemetry_features import validate_dimensions


def test_scene_route_dimension_rejects_user_content():
    assert validate_dimensions({"scene_route": "playlists"}) == {
        "scene_route": "playlists"
    }
    with pytest.raises(ValueError):
        validate_dimensions({"scene_route": "My private collection"})
