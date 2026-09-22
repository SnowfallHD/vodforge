"""Exercise the production player poll/seek/close path with a controlled provider."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from tests.test_libvlc_backend import make_backend
from yt_downloader.media_player_ui import MediaPlayerWindow
from yt_downloader.playback_backend import PlaybackSnapshot
from yt_downloader.playback_progress import PlaybackProgressOwner
from yt_downloader.playback_progress_binding import PlaybackProgressBinding

ROW = {"id": "PRIVATE-id", "webpage_url": "https://youtube.com/watch?v=PRIVATE-id"}


def fixture_player(tmp_path, saved=60, clock=None, observer=None):
    path = tmp_path / "PRIVATE-video.mp4"
    path.write_bytes(b"controlled provider media")
    owner = PlaybackProgressOwner(tmp_path / "watch-progress.json")
    if saved is not None:
        session = owner.begin(ROW)
        owner.observe(session, PlaybackSnapshot(path, "Playing", saved, 100, 0))
        owner.retire(session)
    backend, provider = make_backend()
    backend.load(path, duration=100)
    events = []
    record = observer or (
        lambda action, _diagnostic=None, **fields: events.append((action, fields))
    )
    binding = PlaybackProgressBinding(
        owner,
        ROW,
        snapshot=backend.snapshot,
        seek=backend.seek,
        observe=record,
        **({"clock": lambda: clock[0]} if clock is not None else {}),
    )
    player = object.__new__(MediaPlayerWindow)
    player.playback = backend
    player._bound_playback = backend
    player._bound_media = backend.snapshot
    player._progress_binding = binding
    player._last_snapshot = None
    player._operation_play_observed = False
    player._on_feature = Mock()
    player._on_operation = record
    player.time_var = Mock()
    player.status_var = Mock()
    player.play_button = Mock()
    player._update_timeline_value = Mock()
    player._refresh_previews = Mock()
    player._drain_previews = Mock()
    player._closed = False
    player._shortcut_bindings = []
    player._autoplay_after_id = player._poll_after_id = None
    player._stage_render_after_id = player._surface_owner = None
    player._on_closed = None
    player.popup = Mock()
    player.previews = Mock()
    return player, backend, provider, owner, events


def actions(events):
    return [action for action, _ in events]


def test_actual_player_poll_resumes_once_then_close_survives_restart(tmp_path):
    player, backend, provider, owner, events = fixture_player(tmp_path)
    for _ in range(4):
        player._present_snapshot(backend.snapshot)
    assert not provider.player.seek_calls
    assert owner.resume_position(ROW) == 60
    backend.play()
    player._present_snapshot(backend.snapshot)
    assert provider.player.seek_calls == [60000]
    assert "resume_completed" not in actions(events)
    player._present_snapshot(backend.snapshot)
    provider.player.time = 63500
    player._present_snapshot(backend.snapshot)
    player.close()
    player.close()
    fresh = PlaybackProgressOwner(owner.path)
    fresh.load()
    assert fresh.resume_position(ROW) == 63.5
    assert actions(events).count("resume_completed") == 1
    assert actions(events).count("progress_saved") == 1
    assert provider.player.seek_calls == [60000]


def test_delayed_seek_requires_later_readback_and_preserves_startup_position(tmp_path):
    player, backend, provider, owner, events = fixture_player(tmp_path)
    provider.player.set_time = lambda value: provider.player.seek_calls.append(value)
    backend.play()
    for _ in range(10):
        player._present_snapshot(backend.snapshot)
    assert owner.resume_position(ROW) == 60
    assert provider.player.seek_calls == [60000]
    assert "resume_completed" not in actions(events)
    provider.player.time = 60100
    player._present_snapshot(backend.snapshot)
    assert "resume_completed" in actions(events)


@pytest.mark.parametrize("failure", ["rejected", "exception", "timeout"])
def test_failed_resume_never_overwrites_saved_progress(tmp_path, failure):
    clock = [100.0]
    player, backend, provider, owner, events = fixture_player(tmp_path, clock=clock)

    def seek(_value):
        if failure == "exception":
            raise OSError("PRIVATE provider detail")
        return -1 if failure == "rejected" else None

    provider.player.set_time = seek
    backend.play()
    player._present_snapshot(backend.snapshot)
    clock[0] += 6
    player._present_snapshot(backend.snapshot)
    player.close()
    fresh = PlaybackProgressOwner(owner.path)
    fresh.load()
    assert fresh.resume_position(ROW) == 60
    assert actions(events).count("resume_failed") == 1
    assert "resume_completed" not in actions(events)
    assert "progress_saved" not in actions(events)
    assert "PRIVATE" not in str(events)


def test_manual_seek_before_play_cancels_automatic_resume(tmp_path):
    player, backend, provider, owner, events = fixture_player(tmp_path)
    player._seek_to(0)
    backend.play()
    player._present_snapshot(backend.snapshot)
    assert provider.player.seek_calls == [0]
    assert owner.resume_position(ROW) == 0
    assert (
        "resume_cancelled",
        {"dimensions": {"resume_reason": "manual_seek"}},
    ) in events


def test_manual_seek_after_timeout_recovers_progress_recording(tmp_path):
    clock = [1.0]
    player, backend, provider, owner, _events = fixture_player(tmp_path, clock=clock)
    original = provider.player.set_time
    provider.player.set_time = lambda _: None
    backend.play()
    player._present_snapshot(backend.snapshot)
    clock[0] = 7
    player._present_snapshot(backend.snapshot)
    assert player._progress_binding.notice
    provider.player.set_time = original
    player._seek_to(12)
    player._present_snapshot(backend.snapshot)
    assert not player._progress_binding.notice
    assert owner.resume_position(ROW) == 12


def test_changed_edit_starts_fresh_without_wrong_seek(tmp_path):
    player, backend, provider, owner, events = fixture_player(tmp_path)
    provider.player.length = 20000
    backend.play()
    player._present_snapshot(backend.snapshot)
    assert provider.player.seek_calls == []
    assert owner.for_record(ROW).duration == 20
    assert owner.resume_position(ROW) == 0
    assert (
        "resume_cancelled",
        {"dimensions": {"resume_reason": "media_changed"}},
    ) in events


@pytest.mark.parametrize("before_play", [True, False])
def test_close_while_resume_pending_preserves_saved_point(tmp_path, before_play):
    player, backend, provider, owner, events = fixture_player(tmp_path)
    provider.player.set_time = lambda _: None
    if not before_play:
        backend.play()
        player._present_snapshot(backend.snapshot)
    player.close()
    assert owner.resume_position(ROW) == 60
    assert ("resume_cancelled", {"dimensions": {"resume_reason": "closed"}}) in events
    assert "progress_saved" not in actions(events)


def test_stale_player_cannot_seek_or_retire_another_active_item(tmp_path):
    player, backend, provider, owner, _events = fixture_player(tmp_path)
    next_record = {"id": "next", "webpage_url": "https://youtube.com/watch?v=next"}
    current = owner.begin(next_record)
    backend.play()
    player._present_snapshot(backend.snapshot)
    player.close()
    assert not provider.player.seek_calls
    assert owner.is_active(current)
    assert owner.resume_position(ROW) == 60


def test_foreign_media_snapshot_cannot_acknowledge_or_save(tmp_path):
    player, _backend, provider, owner, events = fixture_player(tmp_path)
    player._present_snapshot(
        PlaybackSnapshot(Path("/another.mp4"), "Playing", 60, 100, 0)
    )
    assert not provider.player.seek_calls
    assert owner.resume_position(ROW) == 60
    assert not events or "resume_completed" not in actions(events)


def test_completion_is_durable_and_next_open_starts_at_beginning(tmp_path):
    player, backend, provider, owner, _events = fixture_player(tmp_path, saved=None)
    backend.play()
    player._present_snapshot(backend.snapshot)
    provider.player.time = 100000
    provider.player.state = provider.State.Ended
    player._present_snapshot(backend.snapshot)
    player.close()
    fresh = PlaybackProgressOwner(owner.path)
    fresh.load()
    assert fresh.for_record(ROW).completed
    assert fresh.resume_position(ROW) == 0


def test_save_failure_is_reported_without_claiming_durability(tmp_path, monkeypatch):
    import yt_downloader.playback_progress as module

    player, backend, _provider, owner, events = fixture_player(tmp_path, saved=None)

    def denied(*_args):
        raise OSError("PRIVATE disk location")

    monkeypatch.setattr(module, "write_private_bytes", denied)
    backend.play()
    player._present_snapshot(backend.snapshot)
    player.close()
    assert "progress_save_failed" in actions(events)
    assert "progress_saved" not in actions(events)
    assert not owner.path.exists()


def test_optional_observer_exception_does_not_stop_resume_or_close(tmp_path):
    def unavailable(*_args, **_kwargs):
        raise RuntimeError("PRIVATE sink")

    player, backend, provider, owner, _events = fixture_player(
        tmp_path, observer=unavailable
    )
    # Core player events are owned by the application's protected observer.
    player._on_operation = Mock()
    backend.play()
    player._present_snapshot(backend.snapshot)
    player._present_snapshot(backend.snapshot)
    player.close()
    assert provider.player.seek_calls == [60000]
    assert owner.resume_position(ROW) == 60


@pytest.mark.usefixtures("production_telemetry_contract")
@pytest.mark.parametrize("case", ["resumed", "timed_out", "denied"])
def test_actual_progress_producer_reaches_consent_gated_private_outbox(
    tmp_path, monkeypatch, case
):
    import json
    import uuid

    from tests.test_history_diagnostics import make_app, payloads

    holder = make_app(tmp_path, monkeypatch, consent=case != "denied")
    operation = str(uuid.uuid4())

    def record(action, diagnostic=None, dimensions=None):
        holder.product_telemetry.record_operation(
            "playback_operation",
            action,
            operation_key=operation,
            failure_detail=diagnostic,
            dimensions=dimensions,
        )

    clock = [1.0]
    player, backend, provider, _owner, _events = fixture_player(
        tmp_path, clock=clock, observer=record
    )
    if case == "timed_out":
        provider.player.set_time = lambda _: None
    backend.play()
    player._present_snapshot(backend.snapshot)
    clock[0] = 7.0
    player._present_snapshot(backend.snapshot)
    player.close()
    events = payloads(holder)
    if case == "denied":
        assert events == []
        return
    names = [event["action"] for event in events]
    assert "resume_requested" in names
    assert ("resume_completed" in names) == (case == "resumed")
    assert ("progress_saved" in names) == (case == "resumed")
    if case == "timed_out":
        failed = next(event for event in events if event["action"] == "resume_failed")
        assert failed["dimensions"]["resume_reason"] == "seek_timeout"
    assert "PRIVATE" not in json.dumps(events)
    assert str(tmp_path) not in json.dumps(events)
    assert all("position" not in event["dimensions"] for event in events)
