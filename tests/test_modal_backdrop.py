from yt_downloader.modal_backdrop import backdrop_rects


def test_scrim_covers_entire_background_but_not_modal():
    bands = backdrop_rects(1000, 700, 200, 180, 600, 340)
    assert sum(w * h for _, _, w, h in bands) == 1000 * 700 - 600 * 340
    for x in range(0, 1000, 10):
        for y in range(0, 700, 10):
            coverage = sum(a <= x < a + w and b <= y < b + h for a, b, w, h in bands)
            assert coverage == (0 if 200 <= x < 800 and 180 <= y < 520 else 1)
