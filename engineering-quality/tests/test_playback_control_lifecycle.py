"""Control-intent/readiness matrix, beyond one reported volume regression.

The real backend is driven through provider delays, resets, pause, seek and replay.
The shared provider fixture avoids introducing a second model of VLC's API.
"""

import threading

import pytest

from tests.test_libvlc_backend import make_backend


@pytest.mark.parametrize("chosen", [0, 1, 37, 100])
@pytest.mark.parametrize("delay_polls", [0, 1, 5])
@pytest.mark.parametrize(
    "transition", ["first_play", "replay", "new_media", "pause_resume"]
)
def test_control_intent_survives_provider_lifecycle(
    tmp_path, chosen, delay_polls, transition
):
    backend, module = make_backend()
    media = tmp_path / "first.mp4"
    media.write_bytes(b"fixture")
    backend.load(media)
    ready = False
    calls = []

    def apply(value):
        calls.append(value)
        if not ready:
            return -1
        module.player.volume = value
        return 0

    module.player.audio_set_volume = apply
    # Several UI changes before readiness: only the latest intent should win.
    for value in (100, 0, chosen):
        assert backend.set_volume(value).volume == value
    backend._playback_started(None)
    backend.play()
    for _ in range(delay_polls):
        assert backend.snapshot.volume == chosen
    ready = True
    assert backend.snapshot.status == "Playing"
    assert module.player.volume == chosen
    if transition == "replay":
        module.player.state = module.State.Ended
        backend.play()
    elif transition == "new_media":
        second = tmp_path / "second.mp3"
        second.write_bytes(b"fixture")
        backend.load(second)
        backend.play()
    elif transition == "pause_resume":
        backend.pause()
        backend.seek(1)
        backend.play()
    # Provider output replacement can occur after a successful setter too.
    module.player.volume = 17 if chosen != 17 else 18
    backend._playback_started(None)
    assert backend.snapshot.volume == chosen
    assert module.player.volume == chosen
    accepted_calls = len(calls)
    for _ in range(5):
        assert backend.snapshot.volume == chosen
    assert len(calls) == accepted_calls, "Stable polls must not flood provider setters"
    backend.shutdown()
    backend._playback_started(None)
    assert backend.snapshot.status == "Closed"


@pytest.mark.parametrize("callback", ["_playback_started", "_playback_failed"])
def test_provider_callbacks_do_not_wait_on_control_thread(callback):
    backend, _ = make_backend()
    with backend._lock:
        worker = threading.Thread(target=getattr(backend, callback), args=(None,))
        worker.start()
        worker.join(0.2)
        blocked = worker.is_alive()
    worker.join(1)
    backend.shutdown()
    assert not blocked, "Provider event thread must not wait on play/stop/control lock"
