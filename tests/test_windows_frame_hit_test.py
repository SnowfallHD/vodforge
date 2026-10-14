"""Native caption and resize ownership is shared by main and player frames."""

import pytest

from yt_downloader.qt_quick.windows_windowing import frame_hit_test


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 2])
@pytest.mark.parametrize("size", [(1100, 740), (780, 480)])
def test_frame_edges_controls_and_drag_region(scale, size):
    width, height = (round(v * scale) for v in size)
    border, header = round(8 * scale), round(32 * scale)
    points = [
        (0, 0, 13),
        (width - 1, 0, 14),
        (0, height - 1, 16),
        (width - 1, height - 1, 17),
        (width // 2, 0, 12),
        (width // 2, height - 1, 15),
        (0, height // 2, 10),
        (width - 1, height // 2, 11),
        (width // 2, header // 2, 2),
        (width - round(69 * scale), header // 2, 9),
        (width - round(23 * scale), header // 2, 1),
        (width - round(115 * scale), header // 2, 1),
        (width // 2, header + 5, 1),
    ]
    for x, y, expected in points:
        assert frame_hit_test(x, y, width, height, border, header, False) == expected
    assert frame_hit_test(0, height // 2, width, height, border, header, True) == 1
    assert frame_hit_test(width // 2, 0, width, height, border, header, True) == 2


def test_non_windows_owner_is_unchanged():
    import sys

    from yt_downloader.qt_quick.windows_windowing import integrate_windows_frames

    if sys.platform != "win32":
        assert integrate_windows_frames(None) is None
