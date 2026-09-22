"""Hover previews cannot seek, retain stale results or leave decoders behind."""

import subprocess
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_media_preview import FakeProcess
from yt_downloader.media_preview import MediaPreviewOwner
from yt_downloader.playback_backend import MediaPlayerError
from yt_downloader.player_hover_preview import PlayerHoverPreview
from yt_downloader.player_presentation_ui import PlayerPresentationMixin

PNG = b"\\x89PNG\\r\\n\\x1a\\n".decode("unicode_escape").encode("latin1") + b"fixture"


def wait_result(owner, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = owner.poll()
        if result is not None:
            return result
        time.sleep(0.005)
    raise AssertionError("preview did not settle")


def make_preview(tmp_path):
    path = tmp_path / "private.mp4"
    path.write_bytes(b"media")
    calls = []

    def popen(command, **kwargs):
        calls.append(command)
        return FakeProcess(output=PNG)

    owner = MediaPreviewOwner(ffmpeg="/trusted/ffmpeg", popen=popen)
    owner.load(path)
    return owner, path, calls


def test_preview_cache_is_bounded_and_reuses_only_the_loaded_file(tmp_path):
    owner, path, calls = make_preview(tmp_path)
    for second in range(30):
        assert owner.preview_png(second) == PNG
    assert len(owner._cache) == 24
    assert owner.preview_png(29) == PNG and len(calls) == 30
    owner.load(path)
    owner.preview_png(29)
    assert len(calls) == 31
    assert owner._registry.processes == set()
    owner.shutdown()
    assert not owner._cache


def test_cached_preview_cannot_survive_source_replacement(tmp_path):
    owner, path, calls = make_preview(tmp_path)
    owner.preview_png(1)
    path.write_bytes(b"different media")
    with pytest.raises(MediaPlayerError, match="changed"):
        owner.preview_png(1)
    assert len(calls) == 1


def test_expected_source_mismatch_cannot_launch_a_decoder(tmp_path):
    owner, path, calls = make_preview(tmp_path)
    with pytest.raises(MediaPlayerError, match="cancelled"):
        owner.preview_png(1, expected_path=path.with_name("different.mp4"))
    assert calls == []


@pytest.mark.parametrize("position", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_preview_position_is_rejected_before_decoder(tmp_path, position):
    owner, _, calls = make_preview(tmp_path)
    with pytest.raises(MediaPlayerError):
        owner.preview_png(position)
    assert calls == []


def test_cancelled_active_preview_is_reaped_before_next_decoder(tmp_path):
    entered = threading.Event()

    class Pending(FakeProcess):
        def communicate(self, timeout):
            entered.set()
            raise subprocess.TimeoutExpired("preview", timeout)

    path = tmp_path / "media.mp4"
    path.write_bytes(b"media")
    process = Pending()
    owner = MediaPreviewOwner(ffmpeg="ffmpeg", popen=lambda *a, **k: process)
    owner.load(path)
    cancel = threading.Event()
    outcomes = []

    def run():
        try:
            owner.preview_png(1, cancel=cancel)
        except MediaPlayerError:
            outcomes.append("cancelled")

    worker = threading.Thread(target=run)
    worker.start()
    assert entered.wait(1)
    cancel.set()
    worker.join(2)
    assert not worker.is_alive() and outcomes == ["cancelled"]
    assert process.poll() is not None and not owner._registry.processes


def test_only_latest_hover_intent_is_published(tmp_path):
    path = tmp_path / "media.mp4"
    path.write_bytes(b"media")
    started = threading.Event()
    calls = []

    def extract(second, *, cancel, expected_path):
        assert expected_path == path
        calls.append(second)
        if second == 1:
            started.set()
            assert cancel.wait(1)
            raise MediaPlayerError("cancelled")
        return PNG

    hover = PlayerHoverPreview(SimpleNamespace(preview_png=extract), debounce=0)
    hover.request(path, 1)
    assert started.wait(1)
    hover.request(path, 8)
    assert wait_result(hover) == (8, PNG)
    assert calls == [1, 8]
    hover.close()


def test_hover_hide_and_close_fence_results_and_new_work(tmp_path):
    path = tmp_path / "media.mp4"
    path.write_bytes(b"media")
    started = threading.Event()

    def extract(second, *, cancel, expected_path):
        started.set()
        assert cancel.wait(1)
        return PNG

    hover = PlayerHoverPreview(SimpleNamespace(preview_png=extract), debounce=0)
    hover.request(path, 1)
    assert started.wait(1)
    hover.hide()
    hover.close()
    hover.request(path, 2)
    hover._worker.join(1)
    assert not hover._worker.is_alive()
    assert hover.poll() is None


@pytest.mark.parametrize(
    "data",
    [
        b"not png",
        b"\\x89PNG\\r\\n\\x1a\\n".decode("unicode_escape").encode("latin1")
        + b"x" * (256 * 1024),
    ],
    ids=["invalid-signature", "oversized-corrupt-png"],
)
def test_invalid_or_excessive_hover_image_is_not_published(tmp_path, data):
    path = tmp_path / "media.mp4"
    path.write_bytes(b"media")
    hover = PlayerHoverPreview(
        SimpleNamespace(preview_png=lambda *a, **k: data), debounce=0
    )
    hover.request(path, 1)
    assert wait_result(hover) == (1, None)
    hover.close()


def test_hover_request_never_seeks_and_same_second_keeps_visible_image(tmp_path):
    hover = Mock()
    player = SimpleNamespace(
        _hover_preview=hover,
        _native_overlay=Mock(),
        playback=SimpleNamespace(
            snapshot=SimpleNamespace(path=tmp_path / "media.mp4", duration=100),
            seek=Mock(),
        ),
    )
    PlayerPresentationMixin._handle_hover_preview(player, "hover_fraction", 0.501)
    PlayerPresentationMixin._handle_hover_preview(player, "hover_fraction", 0.509)
    assert player._native_overlay.show_hover.call_count == 1
    player.playback.seek.assert_not_called()
    PlayerPresentationMixin._handle_hover_preview(player, "hover_end", None)
    hover.hide.assert_called_once()


def test_hidden_details_do_not_launch_moments_preview_work():
    from yt_downloader.media_player_ui import MediaPlayerWindow

    state = SimpleNamespace(
        _closed=False, preview_labels=[Mock()], embedded=True, _details_visible=False
    )
    MediaPlayerWindow._refresh_previews(state, None)
    state.preview_labels[0].configure.assert_not_called()


@pytest.mark.parametrize("hover_cancel", [False, True])
def test_shutdown_during_process_startup_reaps_late_child_without_communicating(
    tmp_path, hover_cancel
):
    entered, release = threading.Event(), threading.Event()
    process = FakeProcess(output=PNG)
    process.communicate = Mock(side_effect=AssertionError("late decoder ran"))
    path = tmp_path / "media.mp4"
    path.write_bytes(b"media")

    def spawn(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return process

    owner = MediaPreviewOwner(ffmpeg="ffmpeg", popen=spawn)
    owner.load(path)
    cancelled = threading.Event() if hover_cancel else None
    outcomes = []

    def run():
        try:
            owner.preview_png(1, cancel=cancelled)
        except MediaPlayerError:
            outcomes.append("cancelled")

    worker = threading.Thread(target=run)
    worker.start()
    assert entered.wait(1)
    owner.shutdown()
    # Shutdown returns while process creation remains blocked.
    assert not release.is_set()
    release.set()
    worker.join(2)
    assert not worker.is_alive() and outcomes == ["cancelled"]
    process.communicate.assert_not_called()
    assert process.poll() is not None and not owner._registry.processes


@pytest.mark.parametrize(
    "duration,expected", [(40, 39.999), (0.3, 0.299), (40.25, 40.249)]
)
def test_right_edge_hover_requests_a_frame_before_end_boundary(
    tmp_path, duration, expected
):
    hover = Mock()
    player = SimpleNamespace(
        _hover_preview=hover,
        _native_overlay=Mock(),
        playback=SimpleNamespace(
            snapshot=SimpleNamespace(path=tmp_path / "media.mp4", duration=duration)
        ),
    )
    PlayerPresentationMixin._handle_hover_preview(player, "hover_fraction", 1.0)
    assert hover.request.call_args.args[1] == pytest.approx(expected)
    assert int(hover.request.call_args.args[1]) < duration
