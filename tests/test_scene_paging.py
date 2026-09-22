import pytest

from yt_downloader.scene_paging import scene_page


@pytest.mark.parametrize(
    "total,limit", [(0, 25), (1, 25), (48, 25), (49, 20), (1001, 25)]
)
def test_bounded_pages_visit_every_record_once(total, limit):
    values = tuple(range(total))
    count = scene_page(values, 0, limit).count
    pages = [scene_page(values, index, limit) for index in range(count)]
    assert all(len(page.items) <= limit for page in pages)
    assert tuple(item for page in pages for item in page.items) == values
    assert all(page.total == total for page in pages)


def test_filter_replacement_clamps_page_without_leaving_blank_stale_page():
    assert scene_page(["only"], 99, 25).items == ("only",)
    assert scene_page(["only"], 99, 25).index == 0
    assert scene_page(["only"], -99, 25).index == 0
    with pytest.raises(ValueError):
        scene_page(["only"], 0, 0)


@pytest.mark.parametrize("count", [0, 1, 100, 20000])
@pytest.mark.parametrize("columns", [1, 3, 5])
def test_virtual_rows_cover_first_middle_end_and_remain_bounded(count, columns):
    from yt_downloader.scene_paging import visible_scene_rows

    height, stride, origin = 800, 210, 100
    rows = (count + columns - 1) // columns
    for top in (0, rows * stride / 2, max(0, rows * stride - height), 0):
        first, last = visible_scene_rows(count, columns, stride, origin, top, height)
        assert 0 <= first <= last <= rows
        assert last - first <= 7
        if count and top == 0:
            assert first == 0 and last > 0
        if count and top == max(0, rows * stride - height):
            assert last == rows


def test_virtual_rows_reject_invalid_geometry_and_clamp_removed_tail():
    from yt_downloader.scene_paging import visible_scene_rows

    for columns, stride in ((0, 20), (1, 0)):
        with pytest.raises(ValueError):
            visible_scene_rows(100, columns, stride, 0, 0, 800)
    assert visible_scene_rows(3, 1, 200, 0, 999999, 800) == (2, 3)


@pytest.mark.parametrize(
    "top,height,expected",
    [
        (0, 600, (0, 0)),
        (0, 669, (0, 0)),
        (0, 670, (0, 1)),
        (700, 200, (0, 1)),
        (969, 200, (1, 1)),
    ],
)
def test_zero_overscan_row_admission_tracks_actual_viewport(top, height, expected):
    from yt_downloader.scene_paging import visible_scene_rows

    assert visible_scene_rows(4, 4, 300, 669, top, height, overscan=0) == expected
