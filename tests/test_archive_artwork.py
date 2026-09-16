from __future__ import annotations

import threading
from pathlib import Path

import pytest
from PIL import Image, ImageTk

from tests.test_archive_models import saved
from tests.test_archive_work import wait_until
from yt_downloader.archive_artwork import ArchiveArtworkMixin


class Surface(ArchiveArtworkMixin):
    def __init__(self, path):
        self.canvas = object()
        self.callbacks = {}
        self.refreshes = 0
        self._artwork_setup(path, (106, 60))

    def after(self, _delay, callback):
        token = str(len(self.callbacks) + 1)
        self.callbacks[token] = callback
        return token

    def after_cancel(self, token):
        self.callbacks.pop(token, None)

    def winfo_ismapped(self):
        return True

    def _queue_render(self):
        self.refreshes += 1


@pytest.fixture
def photo(monkeypatch):
    monkeypatch.setattr(ImageTk, "PhotoImage", lambda bitmap, **kwargs: bitmap.copy())


def load(surface, row):
    surface._artwork_begin()
    surface._artwork_image(row)
    surface._artwork_request()
    wait_until(lambda: not surface._artwork_owner._results.empty())
    surface._artwork_poll()
    return surface._artwork_image(row)


def test_shared_artwork_replacement_cannot_reuse_old_owner_pixels(tmp_path, photo):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    Image.new("RGB", (160, 90), "red").save(first / "thumbnail.png")
    Image.new("RGB", (160, 90), "blue").save(second / "thumbnail.png")
    surface = Surface(lambda row: Path(row["vodforge_output_dir"]) / "thumbnail.png")
    try:
        before = saved(first / "clip.mp4")
        after = {
            **before,
            "vodforge_output_dir": str(second),
            "vodforge_output_path": str(second / "clip.mp4"),
        }
        red = load(surface, before)
        blue = load(surface, after)
        assert red.getpixel((53, 30)) == (255, 0, 0)
        assert blue.getpixel((53, 30)) == (0, 0, 255)
        assert surface._artwork_revision == 2
        assert surface.refreshes == 2
        assert red is not blue
    finally:
        surface._artwork_close()
        surface._artwork_owner._thread.join(2)


def test_artwork_decode_is_off_caller_thread_and_closed_owner_rejects_late_pixels(
    tmp_path, photo
):
    bitmap = tmp_path / "thumbnail.png"
    Image.new("RGB", (160, 90), "green").save(bitmap)
    entered, release = threading.Event(), threading.Event()
    threads = []

    def path(_row):
        threads.append(threading.get_ident())
        entered.set()
        release.wait(2)
        return bitmap

    surface = Surface(path)
    row = saved(tmp_path / "clip.mp4")
    surface._artwork_image(row)
    surface._artwork_request()
    assert entered.wait(2)
    surface._artwork_close()
    release.set()
    surface._artwork_owner._thread.join(2)
    surface._artwork_poll()
    assert threads != [threading.get_ident()]
    assert not surface._artwork_images
    assert surface.refreshes == 0
    assert not surface._artwork_owner._thread.is_alive()


def test_foreign_storage_artwork_does_not_probe_local_interpretation(photo):
    import os

    foreign = "/Volumes/Foreign/clip.mp4" if os.name == "nt" else r"Z:\Foreign\clip.mp4"
    surface = Surface(lambda row: pytest.fail("Foreign storage was probed"))
    try:
        assert load(surface, saved(foreign)) is None
    finally:
        surface._artwork_close()
        surface._artwork_owner._thread.join(2)


@pytest.mark.parametrize("change", ["replace", "arrive", "remove"])
def test_visible_artwork_rechecks_same_metadata_after_local_file_change(
    tmp_path, monkeypatch, photo, change
):
    import yt_downloader.archive_artwork as module

    path = tmp_path / "thumbnail.png"
    if change != "arrive":
        Image.new("RGB", (160, 90), "red").save(path)
    surface = Surface(lambda row: path if path.is_file() else None)
    row = saved(tmp_path / "clip.mp4")
    actual_clock = module.time.monotonic
    try:
        initial = load(surface, row)
        if change == "arrive":
            assert initial is None
        else:
            assert initial.getpixel((53, 30)) == (255, 0, 0)
        if change == "remove":
            path.unlink()
        else:
            Image.new("RGB", (160, 90), "blue").save(path)
        monkeypatch.setattr(module.time, "monotonic", lambda: actual_clock() + 31)
        surface._artwork_poll()
        wait_until(lambda: not surface._artwork_owner._results.empty())
        surface._artwork_poll()
        refreshed = surface._artwork_image(row)
        if change == "remove":
            assert refreshed is None
        else:
            assert refreshed.getpixel((53, 30)) == (0, 0, 255)
    finally:
        surface._artwork_close()
        surface._artwork_owner._thread.join(2)


def test_unchanged_visible_artwork_refresh_checks_files_without_decoding_again(
    tmp_path, monkeypatch, photo
):
    import yt_downloader.archive_artwork as module

    path = tmp_path / "thumbnail.png"
    Image.new("RGB", (160, 90), "red").save(path)
    surface = Surface(lambda row: path)
    row = saved(tmp_path / "clip.mp4")
    actual_clock = module.time.monotonic
    try:
        original = load(surface, row)
        refreshes = surface.refreshes
        monkeypatch.setattr(
            Image, "open", lambda *a, **k: pytest.fail("Unchanged image decoded again")
        )
        monkeypatch.setattr(module.time, "monotonic", lambda: actual_clock() + 31)
        surface._artwork_poll()
        wait_until(lambda: not surface._artwork_owner._results.empty())
        surface._artwork_poll()
        assert surface._artwork_image(row) is original
        assert surface.refreshes == refreshes
    finally:
        surface._artwork_close()
        surface._artwork_owner._thread.join(2)


def test_hidden_artwork_owner_does_not_probe_storage(photo):
    surface = Surface(lambda row: pytest.fail("Hidden surface probed storage"))
    try:
        surface.winfo_ismapped = lambda: False
        surface._artwork_image(saved("/synthetic/clip.mp4"))
        surface._artwork_request()
        assert not surface._artwork_owner.busy
        assert not surface._artwork_attempted
    finally:
        surface._artwork_close()
        surface._artwork_owner._thread.join(2)


def test_artwork_batches_visible_requests_and_long_session_caches_are_bounded(
    tmp_path, photo
):
    path = tmp_path / "thumbnail.png"
    Image.new("RGB", (160, 90), "red").save(path)
    surface = Surface(lambda row: path)
    try:
        for page in range(7):
            rows = [saved(tmp_path / f"clip-{page}-{index}.mp4") for index in range(70)]
            surface._artwork_begin()
            for row in rows:
                surface._artwork_image(row)
            assert len(surface._artwork_wanted) == 48
            surface._artwork_request()
            assert surface._artwork_requested_count <= 24
            for _batch in range(2):
                wait_until(lambda: not surface._artwork_owner._results.empty())
                surface._artwork_poll()
            assert len(surface._artwork_images) <= 64
            assert len(surface._artwork_attempted) <= 256
            assert len(surface._artwork_stamps) <= 256
            assert len(surface._artwork_next_check) <= 256
    finally:
        surface._artwork_close()
        surface._artwork_owner._thread.join(2)
    assert not surface._artwork_images and not surface._artwork_next_check
