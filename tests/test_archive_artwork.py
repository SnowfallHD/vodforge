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
        assert red.convert("RGB").getpixel((53, 30)) == (255, 0, 0)
        assert blue.convert("RGB").getpixel((53, 30)) == (0, 0, 255)
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
            assert initial.convert("RGB").getpixel((53, 30)) == (255, 0, 0)
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
            assert refreshed.convert("RGB").getpixel((53, 30)) == (0, 0, 255)
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


def test_responsive_artwork_discards_inflight_pixels_and_reloads_requested_size(
    tmp_path, photo
):
    bitmap = tmp_path / "thumbnail.png"
    Image.new("RGB", (640, 360), "blue").save(bitmap)
    entered, release = threading.Event(), threading.Event()
    calls = []

    def path(_row):
        calls.append(threading.get_ident())
        if len(calls) == 1:
            entered.set()
            assert release.wait(2)
        return bitmap

    surface = Surface(path)
    row = saved(tmp_path / "clip.mp4")
    try:
        surface._artwork_image(row)
        surface._artwork_request()
        assert entered.wait(2)
        surface._artwork_resize((280, 157))
        release.set()
        wait_until(lambda: not surface._artwork_owner._results.empty())
        surface._artwork_poll()
        assert not surface._artwork_images
        wait_until(lambda: not surface._artwork_owner._results.empty())
        surface._artwork_poll()
        assert surface._artwork_image(row).size == (280, 157)
        assert all(thread != threading.get_ident() for thread in calls)
    finally:
        release.set()
        surface._artwork_close()
        surface._artwork_owner._thread.join(2)


def test_hero_and_card_share_bounded_worker_without_reusing_different_pixels(
    tmp_path, photo
):
    bitmap = tmp_path / "thumbnail.png"
    Image.new("RGB", (1280, 720), "red").save(bitmap)
    surface = Surface(lambda row: bitmap)
    row = saved(tmp_path / "clip.mp4")
    try:
        surface._artwork_begin()
        surface._artwork_image(row)
        surface._artwork_image(row, hero_size=(900, 220))
        surface._artwork_request()
        wait_until(lambda: not surface._artwork_owner._results.empty())
        surface._artwork_poll()
        card = surface._artwork_image(row)
        hero = surface._artwork_image(row, hero_size=(900, 220))
        assert card.size == (106, 60) and hero.size == (900, 220)
        assert hero.mode == card.mode == "RGBA"
        assert hero.getpixel((880, 80))[0] > hero.getpixel((20, 80))[0]
        assert hero.getpixel((450, 20))[0] > hero.getpixel((450, 200))[0]
        assert card.getpixel((0, 0))[3] < 100
        assert card.getpixel((53, 30)) == (255, 0, 0, 255)
        for width in range(20):
            surface._artwork_resize((200 + width, 120))
            surface._artwork_begin()
            surface._artwork_image(row, hero_size=(900 + width, 220))
        # One still-valid cached hero plus the current unresolved size; none
        # of the other 18 requested sizes may accumulate specifications.
        assert len(surface._artwork_images) == 1
        assert len(surface._artwork_wanted) == 1
        assert set(surface._artwork_specs) == (
            set(surface._artwork_images) | set(surface._artwork_wanted)
        )
    finally:
        surface._artwork_close()
        surface._artwork_owner._thread.join(2)


def test_large_hero_preserves_source_detail_instead_of_enlarging_small_decode(
    tmp_path, photo
):
    from PIL import ImageDraw, ImageStat

    path = tmp_path / "sharp.png"
    source = Image.new("RGB", (3000, 700), "black")
    draw = ImageDraw.Draw(source)
    for x in range(0, 3000, 8):
        draw.rectangle((x, 0, x + 3, 699), fill="white")
    source.save(path)
    surface = Surface(lambda row: path)
    row = saved(tmp_path / "clip.mp4")
    try:
        surface._artwork_begin()
        surface._artwork_image(row, hero_size=(3000, 700))
        surface._artwork_request()
        wait_until(lambda: not surface._artwork_owner._results.empty())
        surface._artwork_poll()
        hero = surface._artwork_image(row, hero_size=(3000, 700))
        # The readable fade is nearly transparent here. Four-pixel line pairs
        # must retain contrast; a 1280px intermediate destroys this source detail.
        patch = hero.convert("RGB").crop((2800, 60, 2920, 100))
        assert min(ImageStat.Stat(patch).stddev) > 105
    finally:
        surface._artwork_close()
        surface._artwork_owner._thread.join(2)


@pytest.mark.parametrize(
    "role,size",
    [("media", (1380, 350)), ("avatar", (112, 112)), ("banner", (1380, 250))],
)
def test_actual_artwork_worker_passes_requested_role_and_size_off_ui_thread(
    tmp_path, photo, role, size
):
    path = tmp_path / "actual-source.jpg"
    Image.new("RGB", (1920, 1080), "blue").save(path)
    calls = []
    surface = Surface(lambda _row: pytest.fail("Role source was bypassed"))
    observations = []
    surface._on_usage = lambda _feature, _action, **fields: observations.append(fields)

    def source(record, dimensions, requested_role, cancelled):
        calls.append(
            (
                record["id"],
                dimensions,
                requested_role,
                threading.get_ident(),
                cancelled.is_set(),
            )
        )
        from yt_downloader.library_artwork_source import ArtworkAsset

        return ArtworkAsset(path, "local_frame")

    surface._artwork_source_path = source
    row = saved(tmp_path / "clip.mp4")
    try:
        kwargs = {"hero_size": size} if role != "avatar" else {"tile_size": size}
        surface._artwork_image(row, role=role, **kwargs)
        surface._artwork_request()
        wait_until(lambda: not surface._artwork_owner._results.empty())
        surface._artwork_poll()
        result = surface._artwork_image(row, role=role, **kwargs)
        assert result.size == size
        assert calls[0][:3] == (row["id"], size, role)
        assert calls[0][3] != threading.get_ident()
        assert calls[0][4] is False
        from yt_downloader.telemetry_features import validate_dimensions

        fields = validate_dimensions(observations[0])
        assert fields["artwork_source"] == "local_frame"
        assert fields["artwork_role"] == role
        assert str(tmp_path) not in str(fields)
    finally:
        surface._artwork_close()
        surface._artwork_owner._thread.join(2)


@pytest.mark.parametrize("role", ["media", "banner"])
def test_actual_hero_gradient_protects_muted_copy_on_bright_media(
    tmp_path, photo, role
):
    from yt_downloader.ui_theme import THEME

    path = tmp_path / "bright.jpg"
    Image.new("RGB", (1920, 1080), "white").save(path)
    surface = Surface(lambda _row: path)
    row = saved(tmp_path / "clip.mp4")

    def luminance(rgb):
        values = [v / 255 for v in rgb]
        values = [
            v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values
        ]
        return sum(
            value * weight
            for value, weight in zip(values, (0.2126, 0.7152, 0.0722), strict=True)
        )

    foreground = tuple(int(THEME["muted"][n : n + 2], 16) for n in (1, 3, 5))
    try:
        surface._artwork_image(row, hero_size=(1380, 350), role=role)
        surface._artwork_request()
        wait_until(lambda: not surface._artwork_owner._results.empty())
        surface._artwork_poll()
        image = surface._artwork_image(row, hero_size=(1380, 350), role=role).convert(
            "RGB"
        )
        for x in (36, 300, 500, 656) if role == "media" else (214, 500, 760, 834):
            background = image.getpixel((x, 200))
            assert (luminance(foreground) + 0.05) / (
                luminance(background) + 0.05
            ) >= 4.5
        assert luminance(image.getpixel((1300, 60))) > luminance(
            image.getpixel((100, 60))
        ) * (3 if role == "media" else 2)
    finally:
        surface._artwork_close()
        surface._artwork_owner._thread.join(2)


def test_worker_budget_does_not_delay_unprocessed_artwork_for_thirty_seconds(
    tmp_path, monkeypatch, photo
):
    import yt_downloader.archive_artwork as module

    path = tmp_path / "image.jpg"
    Image.new("RGB", (160, 90), "green").save(path)
    clock = [100.0]
    calls = []

    def source(record):
        calls.append(record["id"])
        if len(calls) == 1:
            clock[0] += 11
        return path

    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    surface = Surface(source)
    records = [
        {**saved(tmp_path / f"{name}.mp4"), "id": name} for name in ("first", "second")
    ]
    try:
        for row in records:
            surface._artwork_image(row)
        surface._artwork_request()
        surface._artwork_owner._thread.join(2)
        assert calls == ["first"]
        surface._artwork_poll()
        surface._artwork_owner._thread.join(2)
        surface._artwork_poll()
        assert calls == ["first", "second"]
        assert all(surface._artwork_image(row) is not None for row in records)
    finally:
        surface._artwork_close()
        if surface._artwork_owner._thread:
            surface._artwork_owner._thread.join(2)


def test_playlist_artwork_retains_image_light_above_readable_caption(tmp_path, photo):
    path = tmp_path / "white-playlist.jpg"
    Image.new("RGB", (1280, 720), "white").save(path)
    surface = Surface(lambda _row: path)
    row = saved(tmp_path / "clip.mp4")
    try:
        surface._artwork_image(row, hero_size=(260, 136), role="playlist")
        surface._artwork_request()
        wait_until(lambda: not surface._artwork_owner._results.empty())
        surface._artwork_poll()
        image = surface._artwork_image(
            row, hero_size=(260, 136), role="playlist"
        ).convert("RGB")
        assert min(image.getpixel((180, 12))) > 180
        from tests.test_matte_theme import contrast
        from yt_downloader.ui_theme import THEME

        caption = "#" + "".join(f"{n:02x}" for n in image.getpixel((24, 85)))
        assert contrast(THEME["text"], caption) >= 7
        assert contrast(THEME["muted"], caption) >= 4.5
        bottom = "#" + "".join(f"{n:02x}" for n in image.getpixel((24, 111)))
        assert contrast(THEME["text"], bottom) >= 7
        assert contrast(THEME["muted"], bottom) >= 4.5
        assert max(image.getpixel((24, 111))) < max(image.getpixel((24, 85)))
    finally:
        surface._artwork_close()
        surface._artwork_owner._thread.join(2)


def test_returning_to_evicted_artwork_reloads_without_waiting_for_retry_timer(
    tmp_path, photo
):
    bitmap = tmp_path / "returning.png"
    Image.new("RGB", (160, 90), "purple").save(bitmap)
    surface = Surface(lambda _row: bitmap)
    row = saved(tmp_path / "clip.mp4")
    try:
        assert load(surface, row) is not None
        key = next(iter(surface._artwork_images))
        surface._artwork_images.pop(key)
        surface._artwork_displayed.clear()
        # A successful image's freshness timer must not suppress cache rehydration.
        assert load(surface, row) is not None
    finally:
        surface._artwork_close()
        surface._artwork_owner._thread.join(2)


def test_default_resize_preserves_explicit_artwork_but_retires_default_pixels(
    tmp_path, photo
):
    path = tmp_path / "distinct.png"
    Image.new("RGB", (200, 200), "red").save(path)
    surface = Surface(lambda row: path)
    row = saved(tmp_path / "clip.mp4")
    try:
        surface._artwork_begin()
        surface._artwork_image(row)
        surface._artwork_image(row, tile_size=(60, 60), role="avatar")
        surface._artwork_image(row, hero_size=(240, 80))
        surface._artwork_request()
        wait_until(lambda: not surface._artwork_owner._results.empty())
        surface._artwork_poll()
        avatar = surface._artwork_image(row, tile_size=(60, 60), role="avatar")
        hero = surface._artwork_image(row, hero_size=(240, 80))
        assert avatar is not None and hero is not None
        surface._artwork_resize((300, 168))
        assert surface._artwork_image(row) is None
        assert surface._artwork_image(row, tile_size=(60, 60), role="avatar") is avatar
        assert surface._artwork_image(row, hero_size=(240, 80)) is hero
        assert surface._artwork_image(row, tile_size=(96, 96), role="avatar") is None
        changed = {**row, "title": "Replaced metadata"}
        assert (
            surface._artwork_image(changed, tile_size=(60, 60), role="avatar") is None
        )
    finally:
        surface._artwork_close()
        surface._artwork_owner._thread.join(2)


def test_live_hero_resize_uses_full_cached_source_without_storage_access(
    tmp_path, photo, monkeypatch
):
    from PIL import ImageDraw

    path = tmp_path / "source.png"
    source = Image.new("RGB", (1600, 500), (200, 40, 40))
    # This marker is cropped out of the original narrow hero, but must return
    # when the wider viewport reveals that part of the actual source.
    ImageDraw.Draw(source).rectangle((1530, 0, 1550, 499), fill="white")
    source.save(path)
    surface = Surface(lambda _row: path)
    row = saved(tmp_path / "clip.mp4")
    try:
        surface._artwork_image(row, hero_size=(900, 400))
        surface._artwork_request()
        wait_until(lambda: not surface._artwork_owner._results.empty())
        surface._artwork_poll()
        first = surface._artwork_image(row, hero_size=(900, 400))
        assert first is not None
        monkeypatch.setattr(
            Image, "open", lambda *_a, **_kw: pytest.fail("Resize accessed storage")
        )
        surface._artwork_resize_active = True
        surface._artwork_begin()
        resized = surface._artwork_image(row, hero_size=(1500, 350))
        assert resized is not None, "Hero vanished while its new size was pending"
        assert resized is not first and resized.size == (1500, 350)
        assert min(resized.convert("RGB").getpixel((1444, 35))) > 220
        assert resized.getpixel((1380, 35))[0] > resized.getpixel((1380, 35))[1] * 3
    finally:
        surface._artwork_close()
        surface._artwork_owner._thread.join(2)


@pytest.mark.parametrize("retirement", ["expired", "metadata", "unavailable"])
def test_live_resize_never_reuses_retired_decoded_source(
    tmp_path, photo, monkeypatch, retirement
):
    import yt_downloader.archive_artwork as module

    path = tmp_path / "source.png"
    Image.new("RGB", (160, 90), "red").save(path)
    surface = Surface(lambda _row: path)
    row = saved(tmp_path / "clip.mp4")
    actual_clock = module.time.monotonic
    try:
        assert load(surface, row) is not None
        if retirement in {"expired", "unavailable"}:
            monkeypatch.setattr(module.time, "monotonic", lambda: actual_clock() + 31)
        if retirement == "metadata":
            row = {**row, "title": "Replacement owner"}
        if retirement == "unavailable":
            path.unlink()
            surface._artwork_poll()
            wait_until(lambda: not surface._artwork_owner._results.empty())
            surface._artwork_poll()
            assert not surface._artwork_source_cache
        surface._artwork_resize_active = True
        surface._artwork_begin()
        assert surface._artwork_image(row, hero_size=(240, 80)) is None
    finally:
        surface._artwork_close()
        surface._artwork_owner._thread.join(2)
    assert not surface._artwork_source_cache and surface._artwork_source_bytes == 0


def test_decoded_artwork_revalidation_refreshes_resize_eligibility(
    tmp_path, photo, monkeypatch
):
    import yt_downloader.archive_artwork as module

    path = tmp_path / "source.png"
    Image.new("RGB", (160, 90), "red").save(path)
    surface = Surface(lambda _row: path)
    row = saved(tmp_path / "clip.mp4")
    actual_clock = module.time.monotonic
    try:
        assert load(surface, row) is not None
        monkeypatch.setattr(module.time, "monotonic", lambda: actual_clock() + 31)
        monkeypatch.setattr(
            Image,
            "open",
            lambda *_a, **_kw: pytest.fail("Unchanged file decoded again"),
        )
        surface._artwork_poll()
        wait_until(lambda: not surface._artwork_owner._results.empty())
        surface._artwork_poll()
        surface._artwork_resize_active = True
        surface._artwork_begin()
        assert surface._artwork_image(row, hero_size=(240, 80)) is not None
    finally:
        surface._artwork_close()
        surface._artwork_owner._thread.join(2)


def test_large_rendered_artwork_remains_available_after_cache_eviction(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(ImageTk, "PhotoImage", lambda bitmap, **kwargs: bitmap)
    surface = Surface(lambda _row: None)
    try:
        first = SimpleNamespace(width=1024, height=1024)
        large = SimpleNamespace(width=5000, height=2000)
        surface._cache_artwork_image("old", first)
        surface._cache_artwork_image("current", large)
        assert list(surface._artwork_images) == ["current"]
        assert surface._artwork_images["current"] is large
        assert surface._artwork_image_bytes == {"current": 40_000_000}
        surface._cache_artwork_image("next", first)
        assert list(surface._artwork_images) == ["next"]
    finally:
        surface._artwork_close()


def test_decoded_artwork_cache_bounds_bytes_and_replacement_accounting():
    from types import SimpleNamespace

    from yt_downloader.archive_artwork import _ArtworkPixels

    surface = Surface(lambda _row: None)
    try:
        for index in range(30):
            source = SimpleNamespace(width=2000, height=2000)
            surface._cache_artwork_source(
                _ArtworkPixels(None, source, (str(index), "media")), index
            )
        assert len(surface._artwork_source_cache) == 5
        assert surface._artwork_source_bytes == 60_000_000
        surface._cache_artwork_source(
            _ArtworkPixels(
                None, SimpleNamespace(width=100, height=100), ("29", "media")
            ),
            30,
        )
        assert surface._artwork_source_bytes == 48_030_000
        surface._cache_artwork_source(
            _ArtworkPixels(
                None, SimpleNamespace(width=5000, height=5000), ("29", "media")
            ),
            31,
        )
        assert ("29", "media") not in surface._artwork_source_cache
        assert surface._artwork_source_bytes == 48_000_000
        surface._cache_artwork_source(
            _ArtworkPixels(None, None, ("skipped", "media")), 32
        )
        assert ("skipped", "media") not in surface._artwork_source_cache
    finally:
        surface._artwork_close()
    assert surface._artwork_source_bytes == 0


def test_worker_result_limits_retained_originals_without_losing_outputs(
    tmp_path, photo
):
    path = tmp_path / "source.png"
    Image.new("RGB", (160, 90), "red").save(path)
    surface = Surface(lambda _row: path)
    try:
        for index in range(24):
            surface._artwork_image(saved(tmp_path / f"{index}.mp4"))
        surface._artwork_request()
        wait_until(lambda: not surface._artwork_owner._results.empty())
        result = surface._artwork_owner.poll()
        assert len(result.value) == 24
        assert all(pixels.bitmap is not None for _, pixels, _ in result.value)
        assert sum(pixels.source is not None for _, pixels, _ in result.value) == 16
    finally:
        surface._artwork_close()
        surface._artwork_owner._thread.join(2)
