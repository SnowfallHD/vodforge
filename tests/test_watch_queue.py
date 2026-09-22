"""Queue intent, real producer privacy and generation-safe playback handoffs."""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_archive_models import saved
from tests.test_archive_ui_owners import owner as pending_app
from tests.test_presentation_diagnostics import real_owner
from yt_downloader.app import DownloaderApp
from yt_downloader.player_related import player_related_plan
from yt_downloader.product_telemetry import _load_outbox
from yt_downloader.watch_library import watch_rails
from yt_downloader.watch_queue import QueueContinuity, WatchQueueOwner, queue_media_key
from yt_downloader.watch_scene_ui import WatchSceneMixin

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


def record(number, output="MP4"):
    return dict(
        saved(f"/PRIVATE/{number}.mp4", video=str(number), playlist="PRIVATE playlist"),
        vodforge_output_type=output,
        playlist_index=number if isinstance(number, int) else 1,
    )


class Queue:
    def __init__(self, rows=None, observer=None):
        self.rows = rows if rows is not None else [record(1), record(2), record(3)]
        self.opens, self.scheduled, self.events = [], [], []
        self.unavailable = Mock()
        self.owner = WatchQueueOwner(
            records=lambda: self.rows,
            open_record=lambda row, token: self.opens.append((row, token)),
            schedule=self.scheduled.append,
            observe=observer
            or (lambda *event, **extra: self.events.append((*event, extra))),
            unavailable=self.unavailable,
            shuffle=lambda keys: keys.reverse(),
        )

    def start(self, **kwargs):
        self.owner.start(
            [queue_media_key(row) for row in self.rows], kind="playlist", **kwargs
        )

    def attach(self):
        player = object()
        row, token = self.opens[-1]
        self.owner.attach(player, row, token)
        return player

    def finish(self, player=None, continuity=None):
        player = player or self.attach()
        self.owner.present(player, "Playing")
        self.owner.present(player, "Ended", continuity=continuity)
        self.scheduled.pop(0)()

    @property
    def actions(self):
        return [e[0] for e in self.events]


def test_queue_keys_match_watch_source_keys():
    rows = [record(1), record(1, "MP3"), record(2)]
    assert {queue_media_key(r) for r in rows} == {
        v.key for rail in watch_rails(rows) for v in rail.videos
    }


def test_playlist_order_deduplicates_variants_and_resolves_preferred_output():
    q = Queue([record(2, "MP3"), record(1), record(2, "Original audio"), record(2)])
    q.start()
    assert q.opens[0][0]["id"] == "2"
    assert q.opens[0][0]["vodforge_output_type"] == "MP4"
    assert q.owner.remaining_keys == (queue_media_key(record(1)),)
    q.finish()
    assert q.opens[-1][0]["id"] == "1"
    q.finish()
    assert q.owner.token is None and len(q.opens) == 2
    assert q.actions == ["requested", "started", "advanced", "completed"]


def test_advance_resolves_latest_canonical_record_after_reorder():
    q = Queue()
    q.start()
    q.rows[:] = [
        dict(record(3), title="updated"),
        dict(record(2), title="latest"),
        record(1),
    ]
    q.finish()
    assert q.opens[-1][0]["title"] == "latest"


def test_shuffle_uses_one_complete_permutation_without_repeats():
    q = Queue()
    q.start(shuffled=True)
    q.finish()
    q.finish()
    q.finish()
    assert [r["id"] for r, _ in q.opens] == ["3", "2", "1"]
    assert {e[2]["queue_order"] for e in q.events} == {"shuffle"}


@pytest.mark.parametrize(
    "status", ["Paused", "Stopped", "Ready", "Opening", "Buffering"]
)
def test_only_provider_end_after_playing_can_advance(status):
    q = Queue()
    q.start()
    player = q.attach()
    q.owner.present(player, "Playing")
    q.owner.present(player, status)
    assert len(q.opens) == 1 and not q.scheduled


def test_ended_before_any_play_does_not_claim_success():
    q = Queue()
    q.start()
    q.owner.present(q.attach(), "Ended")
    assert q.actions == ["requested", "failed"]
    assert not q.scheduled and q.owner.token is None


def test_attach_is_not_playback_started_and_repeated_playing_is_one_event():
    q = Queue()
    q.start()
    player = q.attach()
    assert q.actions == ["requested"]
    q.owner.present(player, "Playing")
    q.owner.present(player, "Playing")
    q.owner.present(player, "Paused")
    q.owner.present(player, "Playing")
    assert q.actions == ["requested", "started"]


def test_duplicate_end_schedules_one_deferred_transition():
    q = Queue()
    q.start()
    player = q.attach()
    q.owner.present(player, "Playing")
    q.owner.present(player, "Ended")
    q.owner.present(player, "Ended")
    assert len(q.opens) == 1 and len(q.scheduled) == 1
    advance = q.scheduled.pop()
    advance()
    advance()
    assert len(q.opens) == 2


@pytest.mark.parametrize("replacement", ["cancel", "new_queue", "jump"])
def test_scheduled_end_cannot_override_newer_intent(replacement):
    q = Queue()
    q.start()
    player = q.attach()
    q.owner.present(player, "Playing")
    q.owner.present(player, "Ended")
    if replacement == "cancel":
        q.owner.cancel()
    elif replacement == "new_queue":
        q.start(shuffled=True)
    else:
        q.owner.jump(queue_media_key(record(3)))
    before = list(q.opens)
    q.scheduled.pop()()
    assert q.opens == before


def test_retired_player_and_old_same_source_token_cannot_end_new_queue():
    q = Queue()
    q.start()
    old_player = q.attach()
    old_record, old_token = q.opens[-1]
    q.start()
    q.owner.attach(old_player, old_record, old_token)
    q.owner.present(old_player, "Playing")
    q.owner.present(old_player, "Ended")
    assert not q.scheduled and q.actions == ["requested", "cancelled", "requested"]
    q.finish()
    assert q.opens[-1][0]["id"] == "2"


def test_provider_failure_stops_queue_without_skipping_to_another_item():
    q = Queue()
    q.start()
    q.owner.present(q.attach(), "Failed")
    assert q.actions == ["requested", "failed"]
    assert len(q.opens) == 1 and q.owner.token is None


@pytest.mark.parametrize("mutation", ["removed", "no_saved_output"])
def test_missing_current_source_stops_truthfully(mutation):
    q = Queue()
    q.start()
    if mutation == "removed":
        q.rows[:] = [q.rows[0], q.rows[2]]
    else:
        q.rows[1] = dict(q.rows[1], vodforge_output_dir="")
    q.finish()
    assert len(q.opens) == 1 and q.owner.token is None
    assert q.actions[-1] == "failed"
    q.unavailable.assert_called_once()


def test_single_video_completes_without_another_open():
    q = Queue([record(1)])
    q.start()
    q.finish()
    assert len(q.opens) == 1
    assert q.actions == ["requested", "started", "completed"]


def test_empty_start_cancels_old_intent_without_fake_request():
    q = Queue()
    q.start()
    q.owner.start([], kind="playlist")
    assert q.actions == ["requested", "cancelled"]


@pytest.mark.parametrize("mode", ["embedded", "fullscreen", "floating"])
@pytest.mark.parametrize("volume", [0, 50, 100])
def test_advance_preserves_actual_volume_mute_memory_and_presentation(mode, volume):
    q = Queue()
    q.start()
    continuity = QueueContinuity(volume, 73, mode)
    q.finish(continuity=continuity)
    assert q.owner.continuity == continuity
    q.owner.cancel()
    assert q.owner.continuity is None


def test_up_next_jump_preserves_remaining_order_and_ignores_nonmembers():
    q = Queue()
    q.start()
    assert not q.owner.jump(queue_media_key(record(99)))
    assert not q.owner.jump(queue_media_key(record(1)))
    assert q.owner.jump(
        queue_media_key(record(3)), continuity=QueueContinuity(0, 68, "floating")
    )
    assert q.opens[-1][0]["id"] == "3" and q.owner.remaining_keys == ()
    assert q.owner.continuity.volume == 0
    q.finish()
    assert len(q.opens) == 2


def test_synchronous_handoff_does_not_cancel_but_user_close_does():
    q = Queue()
    q.start()
    with q.owner.retiring_player():
        q.owner.player_closed()
    assert q.owner.token is not None
    q.owner.player_closed()
    assert q.owner.token is None and q.actions[-1] == "cancelled"


def test_handoff_guard_is_released_even_if_old_player_close_raises():
    q = Queue()
    q.start()
    with pytest.raises(RuntimeError), q.owner.retiring_player():
        raise RuntimeError("close")
    q.owner.player_closed()
    assert q.owner.token is None


def test_large_queue_observations_are_bounded_and_keep_terminal_outcome():
    q = Queue([record(i) for i in range(105)])
    q.start()
    for _ in range(105):
        q.finish()
    assert q.actions == ["requested", "started", "advanced", "completed"]
    assert {e[2]["item_count_bucket"] for e in q.events} == {"101_plus"}


def test_telemetry_failure_cannot_interrupt_queue():
    q = Queue(observer=Mock(side_effect=RuntimeError("offline")))
    q.start()
    q.finish()
    q.finish()
    q.finish()
    assert len(q.opens) == 3 and q.owner.token is None


def test_only_random_operation_identity_and_bounded_dimensions_leave_producer(tmp_path):
    telemetry = real_owner(tmp_path / "telemetry")
    app = SimpleNamespace(product_telemetry=telemetry)
    q = Queue(
        observer=lambda action, operation, dimensions: (
            DownloaderApp._record_watch_queue_operation(
                app, action, operation, dimensions
            )
        )
    )
    q.start()
    q.finish()
    q.finish()
    q.finish()
    assert telemetry.shutdown(2)
    payload = [
        event.public_payload()
        for event in _load_outbox(tmp_path / "telemetry/events.json")
    ]
    assert [p["action"] for p in payload] == [
        "requested",
        "started",
        "advanced",
        "completed",
    ]
    assert {p["feature"] for p in payload} == {"watch_queue_operation"}
    assert "PRIVATE" not in json.dumps(payload)
    for index, p in enumerate(payload):
        assert uuid.UUID(p["dimensions"]["operation_id"]).version == 4
        assert {
            key: value
            for key, value in p["dimensions"].items()
            if key
            not in {
                "operation_id",
                "operation_step",
                "observation_drop_count",
                "instrumentation",
                "build_revision",
            }
        } == {
            "queue_kind": "playlist",
            "queue_order": "ordered",
            "item_count_bucket": "2_5",
            "queue_position_bucket": ["1", "1", "2_5", "2_5"][index],
            "queue_completed_bucket": ["0", "0", "1", "2_5"][index],
        }


def test_up_next_projection_is_actual_queue_order_and_excludes_unrelated():
    rows = [record(i) for i in range(1, 5)]
    plan = player_related_plan(
        rows, rows[0], [queue_media_key(rows[2]), queue_media_key(rows[1])]
    )
    assert [rows[v.indices[0]]["id"] for v in plan.up_next] == ["3", "2"]
    assert not player_related_plan(rows, rows[0], ()).up_next


def test_watch_queue_dispatch_uses_source_keys_not_view_indices():
    rows = [record(1), record(2)]
    videos = watch_rails(rows)[0].videos
    callback = Mock()
    WatchSceneMixin._scene_start_queue(
        SimpleNamespace(_on_queue=callback), videos, "playlist", True
    )
    callback.assert_called_once_with(tuple(v.key for v in videos), "playlist", True)


@pytest.mark.parametrize("outcome", ["cancelled", "expired", "removed", "newer_queue"])
def test_deferred_open_retires_only_the_queue_that_owned_it(outcome):
    app, _ = pending_app()
    q = Queue()
    app.watch_queue = q.owner
    q.owner._open = lambda row, token: app._archive_request_playback(
        row, queue_token=token
    )
    q.start()
    pending = app._archive_pending_playback
    app.metadata_items = q.rows
    if outcome == "newer_queue":
        q.start(shuffled=True)
        assert q.owner.owns(app._archive_pending_playback["queue_token"])
        assert not q.owner.owns(pending["queue_token"])
        return
    if outcome == "cancelled":
        app._archive_retire_pending_playback()
    else:
        if outcome == "expired":
            pending["deadline"] = 0
        else:
            app.metadata_items = []
            app._archive_worker.busy = False
        app._archive_poll()
    assert q.owner.token is None


def test_stale_readiness_cannot_create_backend_or_attach_to_new_queue(tmp_path):
    app, _ = pending_app()
    q = Queue()
    q.start()
    old = q.owner.token
    q.start()
    app.watch_queue = q.owner
    app._archive_finish_opening = Mock()
    app.playback_engine = Mock()
    DownloaderApp._open_library_player_when_ready(
        app,
        record(1),
        tmp_path / "old.mp4",
        ffmpeg="unused",
        launch_generation=app._media_player_launch_generation,
        deadline=0,
        operation="old",
        queue_token=old,
    )
    app.playback_engine.create_backend.assert_not_called()
    assert q.owner.token is not None


def test_queue_observer_is_bound_once_and_cannot_adopt_later_consent():
    observation = Mock()
    telemetry = SimpleNamespace(bind_operation=Mock(return_value=None))
    app = SimpleNamespace(product_telemetry=telemetry)
    q = Queue(
        observer=lambda action, operation, dimensions: (
            DownloaderApp._record_watch_queue_operation(
                app, action, operation, dimensions
            )
        )
    )
    q.start()
    telemetry.bind_operation.return_value = observation
    q.finish()
    q.finish()
    q.finish()
    assert telemetry.bind_operation.call_count == 1
    observation.record.assert_not_called()
    assert app._watch_queue_observations == {}
    q.start()
    observation.record.assert_called_once()


@pytest.mark.parametrize("missing", ["queue_kind", "queue_order", "item_count_bucket"])
def test_queue_schema_requires_useful_bounded_context(missing):
    from yt_downloader.telemetry_features import validate_operation_fields

    dims = {
        "operation_id": str(uuid.uuid4()),
        "operation_step": "1",
        "instrumentation": "diagnostics_v1",
        "build_revision": "unknown",
        "queue_kind": "playlist",
        "queue_order": "ordered",
        "item_count_bucket": "2_5",
    }
    del dims[missing]
    with pytest.raises(ValueError, match="queue context"):
        validate_operation_fields("watch_queue_operation", dims, "requested")


@pytest.mark.parametrize("mode", ["fullscreen", "floating"])
def test_presentation_restore_waits_for_autoplay_surface_attachment(mode):
    from yt_downloader.media_player_ui import MediaPlayerWindow

    order = []
    state = SimpleNamespace(
        _closed=False,
        _audio_only=False,
        _initial_presentation=mode,
        _toggle=lambda: order.append("attach-and-play"),
        _open_presentation=lambda mode: order.append(mode),
    )
    MediaPlayerWindow._autoplay_ready(state)
    assert order == ["attach-and-play", mode]
    assert "_initial_presentation" not in state.__dict__


def test_closed_player_cannot_restore_queued_presentation():
    from yt_downloader.media_player_ui import MediaPlayerWindow

    state = SimpleNamespace(
        _closed=True,
        _initial_presentation="floating",
        _toggle=Mock(),
        _open_presentation=Mock(),
    )
    MediaPlayerWindow._autoplay_ready(state)
    state._toggle.assert_not_called()
    state._open_presentation.assert_not_called()


def test_audio_successor_explains_main_window_fallback():
    from yt_downloader.media_player_ui import MediaPlayerWindow

    state = SimpleNamespace(
        _closed=False,
        _audio_only=True,
        _initial_presentation="fullscreen",
        _toggle=Mock(),
        _open_presentation=Mock(),
        _set_control_notice=Mock(),
    )
    MediaPlayerWindow._autoplay_ready(state)
    state._open_presentation.assert_not_called()
    state._set_control_notice.assert_called_once_with(
        "This audio item plays in the main window."
    )


def test_manual_focus_changes_up_next_back_to_suggestions():
    from yt_downloader.player_scene_ui import PlayerSceneMixin

    related = SimpleNamespace(
        _queue_keys=("old",), _related_section="Up Next", set_records=Mock()
    )
    state = SimpleNamespace(
        _closed=False,
        _queue_keys=("old",),
        _related_view=related,
        _library_records=(record(1), record(2)),
    )
    PlayerSceneMixin.set_queue_keys(state, None)
    assert state._queue_keys is None and related._queue_keys is None
    assert related._related_section == ""
    related.set_records.assert_called_once_with(state._library_records)


def test_presentation_host_is_transferred_after_surface_attachment():
    from yt_downloader.media_player_ui import MediaPlayerWindow

    host = Mock()
    state = SimpleNamespace(
        _closed=False,
        _audio_only=False,
        _initial_presentation="fullscreen",
        _initial_presentation_host=host,
        _toggle=Mock(),
        _open_presentation=Mock(),
    )
    MediaPlayerWindow._autoplay_ready(state)
    state._open_presentation.assert_called_once_with("fullscreen", host)
    host.close.assert_not_called()


def test_retiring_old_provider_prevents_a_second_audio_owner(tmp_path):
    import time

    app, _ = pending_app()
    q = Queue()
    q.start()
    app.watch_queue = q.owner
    app.playback_engine = SimpleNamespace(
        ready=True, failed=False, retiring=True, create_backend=Mock()
    )
    app.after = Mock()
    DownloaderApp._open_library_player_when_ready(
        app,
        record(1),
        tmp_path / "next.mp4",
        ffmpeg="unused",
        launch_generation=app._media_player_launch_generation,
        deadline=time.monotonic() + 10,
        operation="current",
        queue_token=q.owner.token,
    )
    app.playback_engine.create_backend.assert_not_called()
    assert app.after.call_args.args[0] == 50


@pytest.mark.parametrize("cause", ["removed", "unsaved", "provider", "unexpected_end"])
def test_failures_preserve_distinct_bounded_reasons_and_actual_progress(cause):
    q = Queue()
    q.start()
    if cause in {"removed", "unsaved"}:
        if cause == "removed":
            q.rows[:] = [q.rows[0], q.rows[2]]
        else:
            q.rows[1] = dict(q.rows[1], vodforge_output_dir="")
        q.finish()
    else:
        q.owner.present(q.attach(), "Failed" if cause == "provider" else "Ended")
    failure = q.events[-1]
    assert failure[0] == "failed"
    expected = {
        "removed": ("metadata", "source_removed", "2_5", "1"),
        "unsaved": ("metadata", "saved_output_missing", "2_5", "1"),
        "provider": ("provider", "provider_failed", "1", "0"),
        "unexpected_end": ("unexpected_end", "ended_before_playing", "1", "0"),
    }[cause]
    assert (
        tuple(
            failure[2][k]
            for k in (
                "queue_failure_boundary",
                "queue_failure_reason",
                "queue_position_bucket",
                "queue_completed_bucket",
            )
        )
        == expected
    )


@pytest.mark.parametrize(
    "boundary", ["resolve", "dependency", "initialization", "readiness", "load"]
)
def test_opening_failure_is_associated_with_same_queue_and_typed_diagnostic(boundary):
    from yt_downloader.archive_library_ui import ArchiveLibraryMixin
    from yt_downloader.failure_diagnostics import FailureDiagnostic

    q = Queue()
    q.start()
    detail = FailureDiagnostic(
        reason="permission_denied", stage="playback", os_error=13
    )
    app = SimpleNamespace(
        watch_queue=q.owner,
        _archive_opening_operation="opening",
        _archive_opening_queue_token=q.owner.token,
        _archive_playback_origins={},
        _record_playback_operation=Mock(),
    )
    ArchiveLibraryMixin._archive_finish_opening(
        app,
        "opening",
        "failed",
        detail,
        dimensions={"playback_failure_boundary": boundary},
    )
    assert q.events[-1][1] == q.events[0][1]
    assert q.events[-1][2]["queue_failure_boundary"] == boundary
    assert q.events[-1][2]["queue_failure_reason"] == "permission_denied"
    assert q.events[-1][3]["failure_detail"] is detail


def test_jump_does_not_falsely_count_skipped_items_as_completed():
    q = Queue()
    q.start()
    q.owner.jump(queue_media_key(record(3)))
    q.finish()
    assert q.events[-1][2]["queue_completed_bucket"] == "1"


@pytest.mark.parametrize("field", ["queue_failure_boundary", "queue_failure_reason"])
def test_ambiguous_failed_queue_event_is_rejected(field):
    from yt_downloader.telemetry_features import validate_operation_fields

    dims = {
        "operation_id": str(uuid.uuid4()),
        "operation_step": "1",
        "instrumentation": "diagnostics_v1",
        "build_revision": "unknown",
        "queue_kind": "playlist",
        "queue_order": "ordered",
        "item_count_bucket": "2_5",
        "queue_position_bucket": "1",
        "queue_completed_bucket": "0",
        "queue_failure_boundary": "provider",
        "queue_failure_reason": "provider_failed",
    }
    del dims[field]
    with pytest.raises(ValueError, match="failure context"):
        validate_operation_fields("watch_queue_operation", dims, "failed")


def test_presentation_host_closes_underlying_window_once():
    from yt_downloader.player_presentation_ui import PlayerPresentationHost

    window = Mock()
    host = PlayerPresentationHost(window, object(), "fullscreen")
    host.close()
    host.close()
    window.destroy.assert_called_once()


def test_handoff_replaces_old_window_commands_before_next_player_exists():
    from yt_downloader.player_presentation_ui import PlayerPresentationMixin

    window, stage, cancel = Mock(), object(), Mock()
    state = SimpleNamespace(
        _presentation_window=window,
        _presentation_mode="fullscreen",
        _surface_owner=SimpleNamespace(stage=stage),
    )
    host = PlayerPresentationMixin.release_presentation_host(state, cancel)
    assert host.window is window and host.stage is stage and host.mode == "fullscreen"
    assert state._presentation_window is None
    window.protocol.assert_called_once_with("WM_DELETE_WINDOW", cancel)
    assert {call.args[0] for call in window.unbind.call_args_list} == {
        "<space>",
        "<Left>",
        "<Right>",
    }
    window.bind.call_args.args[1](None)
    cancel.assert_called_once()


@pytest.mark.parametrize("outcome", ["cancelled", "failed"])
def test_terminal_opening_closes_held_host_exactly_once(outcome):
    from yt_downloader.archive_library_ui import ArchiveLibraryMixin
    from yt_downloader.player_presentation_ui import PlayerPresentationHost

    q = Queue()
    q.start()
    window = Mock()
    host = PlayerPresentationHost(window, object(), "fullscreen")
    app = SimpleNamespace(
        watch_queue=q.owner,
        _archive_opening_operation="opening",
        _archive_opening_queue_token=q.owner.token,
        _archive_queue_presentation=(q.owner.token, host),
        _archive_playback_origins={},
        _record_playback_operation=Mock(),
    )
    ArchiveLibraryMixin._archive_finish_opening(app, "opening", outcome)
    ArchiveLibraryMixin._archive_finish_opening(app, "opening", outcome)
    window.destroy.assert_called_once()
    assert "_archive_queue_presentation" not in app.__dict__


def test_stale_terminal_callback_cannot_close_new_queue_host():
    from yt_downloader.archive_library_ui import ArchiveLibraryMixin

    q = Queue()
    q.start()
    old = q.owner.token
    q.start()
    host = Mock()
    app = SimpleNamespace(
        watch_queue=q.owner,
        _archive_opening_operation="current",
        _archive_opening_queue_token=q.owner.token,
        _archive_queue_presentation=(q.owner.token, host),
        _archive_playback_origins={},
        _record_playback_operation=Mock(),
    )
    ArchiveLibraryMixin._archive_finish_opening(app, "old", "failed")
    host.close.assert_not_called()
    assert q.owner.token != old


def test_manual_replacement_retires_unadopted_host_before_storage_wait():
    app, _ = pending_app()
    q = Queue()
    q.start()
    host = Mock()
    app.watch_queue = q.owner
    app._archive_queue_presentation = (q.owner.token, host)
    app._archive_request_playback(record(2))
    host.close.assert_called_once()
    assert q.owner.token is None and app._archive_pending_playback is not None
    assert "_archive_queue_presentation" not in app.__dict__


@pytest.mark.parametrize("rollback_fails", [False, True])
def test_failed_adoption_closes_host_and_restores_surface_or_retires_player(
    rollback_fails,
):
    from yt_downloader.playback_backend import MediaPlayerError
    from yt_downloader.player_presentation_ui import (
        PlayerPresentationHost,
        PlayerPresentationMixin,
    )

    window = Mock()
    host = PlayerPresentationHost(window, object(), "fullscreen")
    surface = SimpleNamespace(
        toplevel=object(),
        stage=object(),
        rehost=Mock(
            side_effect=[
                RuntimeError("handoff"),
                RuntimeError("restore") if rollback_fails else None,
            ]
        ),
    )
    state = SimpleNamespace(
        _closed=False,
        _surface_owner=surface,
        _presentation_window=None,
        close=Mock(),
        _return_presentation=Mock(),
    )
    with pytest.raises(MediaPlayerError):
        PlayerPresentationMixin._open_presentation(state, "fullscreen", host)
    window.destroy.assert_called_once()
    assert host.closed
    assert state.close.called == rollback_fails


def test_cancel_while_next_item_is_waiting_retires_host_and_queue():
    from yt_downloader.archive_library_ui import ArchiveLibraryMixin
    from yt_downloader.player_presentation_ui import PlayerPresentationHost

    app, _ = pending_app()
    q = Queue()
    q.start()
    window = Mock()
    app.watch_queue = q.owner
    app._archive_queue_presentation = (
        q.owner.token,
        PlayerPresentationHost(window, object(), "floating"),
    )
    app._archive_finish_opening = Mock()
    app._archive_cancel_work = Mock()
    app._archive_restore_browser = Mock()
    ArchiveLibraryMixin._archive_cancel_playback(app)
    ArchiveLibraryMixin._archive_cancel_playback(app)
    window.destroy.assert_called_once()
    assert q.owner.token is None


def test_audio_successor_closes_inherited_video_host():
    from yt_downloader.media_player_ui import MediaPlayerWindow

    host = Mock()
    state = SimpleNamespace(
        _closed=False,
        _audio_only=True,
        _initial_presentation="fullscreen",
        _initial_presentation_host=host,
        _toggle=Mock(),
        _open_presentation=Mock(),
        _set_control_notice=Mock(),
    )
    MediaPlayerWindow._autoplay_ready(state)
    host.close.assert_called_once()
    state._open_presentation.assert_not_called()


@pytest.mark.parametrize("interruption", ["cancel", "jump", "replace"])
def test_accepted_end_is_counted_once_before_deferred_advance(interruption):
    q = Queue()
    q.start()
    player = q.attach()
    q.owner.present(player, "Playing")
    q.owner.present(player, "Ended")
    q.owner.present(player, "Ended")  # duplicated provider notification
    pending = q.scheduled.pop(0)
    if interruption == "cancel":
        q.owner.player_closed()
    elif interruption == "replace":
        q.start()
    else:
        assert q.owner.jump(queue_media_key(q.rows[-1]))
    opens = len(q.opens)
    pending()  # retired intent must neither open nor increment again
    assert len(q.opens) == opens
    if interruption == "jump":
        assert q.events[-1][2]["queue_completed_bucket"] == "1"
        q.finish()
        assert q.events[-1][2]["queue_completed_bucket"] == "2_5"
    else:
        terminal = [e for e in q.events if e[0] == "cancelled"][-1]
        assert terminal[2]["queue_completed_bucket"] == "1"
        if interruption == "replace":
            assert q.events[-1][2]["queue_completed_bucket"] == "0"
