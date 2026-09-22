"""Displayed-frame reuse must not expand the unused cache or survive retirement."""

import gc
import weakref
from contextlib import nullcontext

import pytest

from yt_downloader import ui_chrome


class Canvas:
    def __init__(self):
        self.items = {}
        self.serial = 0

    def find_all(self):
        return tuple(self.items)

    def create_image(self, *args, image, **kwargs):
        self.serial += 1
        self.items[self.serial] = str(image)
        return self.serial

    def delete(self, item):
        if item == "all":
            self.items.clear()
        else:
            self.items.pop(item, None)


class Image:
    pass


def cache_fixture(monkeypatch):
    scale = [2]
    monkeypatch.setattr(ui_chrome, "surface_backing_scale", lambda _: scale[0])
    monkeypatch.setattr(
        ui_chrome,
        "layered_surface_image",
        lambda width, height, **kwargs: (width, height),
    )
    monkeypatch.setattr(
        ui_chrome,
        "create_surface_image",
        lambda _canvas, bitmap, factor: (
            Image(),
            bitmap[0] * bitmap[1] * 4 * factor**2,
        ),
    )
    canvas = Canvas()
    return canvas, ui_chrome.CanvasSurfaceCache(canvas), scale


def test_oversized_displayed_image_reuses_within_frame_without_evicting_small_cache(
    monkeypatch,
):
    canvas, owner, _scale = cache_fixture(monkeypatch)
    for _ in range(5):
        with owner.frame():
            canvas.delete("all")
            owner.draw((0, 0, 32, 32))
            owner.draw((0, 0, 1600, 1000))
        assert owner.builds == 2
        assert owner.cached_bytes == 32 * 32 * 4 * 4
        assert len(owner._images) == 1
        assert owner.bytes == (32 * 32 + 1600 * 1000) * 4 * 4
        assert not owner._frame_images
    owner.clear()
    assert owner.bytes == owner.cached_bytes == 0
    assert not canvas.items and not owner._displayed_keys


@pytest.mark.parametrize("change", ["size", "scale", "palette", "exception", "clear"])
def test_previous_surface_identity_and_lifetime_end_at_replacement(monkeypatch, change):
    canvas, owner, scale = cache_fixture(monkeypatch)
    item = owner.draw((0, 0, 1600, 1000))
    previous = weakref.ref(owner._displayed[item][0])
    assert owner.cached_bytes == 0
    expectation = (
        pytest.raises(RuntimeError) if change == "exception" else nullcontext()
    )
    with expectation, owner.frame():
        canvas.delete("all")
        assert previous() is not None
        if change == "exception":
            raise RuntimeError("render interrupted")
        if change == "clear":
            owner.clear()
        else:
            if change == "scale":
                scale[0] = 1
            elif change == "palette":
                monkeypatch.setitem(ui_chrome.THEME, "panel", "#123456")
            owner.draw((0, 0, 1700 if change == "size" else 1600, 1000))
            assert owner.builds == 2
    gc.collect()
    assert previous() is None
    assert not owner._frame_images
    owner.clear()
    assert owner.bytes == owner.cached_bytes == 0
