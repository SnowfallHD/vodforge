"""Screen/client/chrome bounds preserve picture aspect and functional controls."""

import pytest

from yt_downloader.qt_quick.player_geometry import (
    clamp_player_origin,
    initial_player_client_size,
)


@pytest.mark.parametrize(
    "aspect,available",
    [(16 / 9, (1440, 900)), (9 / 16, (1440, 1100)), (4 / 3, (700, 600))],
)
def test_initial_geometry_fits_screen_with_native_chrome(aspect, available):
    width, height, overflow = initial_player_client_size(
        780, aspect, available, (16, 39), (450, 104)
    )
    assert width / height == pytest.approx(aspect, abs=0.01)
    assert width >= 450 and height >= 104
    assert width + 16 <= available[0]
    assert height + 39 <= available[1]
    assert not overflow


def test_extreme_portrait_keeps_controls_and_reports_screen_limit():
    width, height, overflow = initial_player_client_size(
        780, 9 / 16, (700, 560), (16, 39), (450, 104)
    )
    assert width == 450
    assert height == 800
    assert overflow


@pytest.mark.parametrize("aspect", [0, -1, float("nan"), float("inf")])
def test_invalid_aspect_refuses_geometry(aspect):
    with pytest.raises(ValueError):
        initial_player_client_size(780, aspect, (1440, 900), (16, 39), (450, 104))


def test_initial_origin_clamps_frame_on_current_screen():
    assert clamp_player_origin(
        (1000, 1000), (100, 50, 700, 600), (8, 31, 8, 8), (500, 300)
    ) == (292, 342)
    assert clamp_player_origin(
        (-100, -100), (100, 50, 700, 600), (8, 31, 8, 8), (500, 300)
    ) == (108, 81)
    # An unavoidable tall minimum leaves its titlebar reachable, not below the screen.
    assert (
        clamp_player_origin((200, 200), (100, 50, 700, 560), (8, 31, 8, 8), (450, 800))[
            1
        ]
        == 81
    )
