from __future__ import annotations

import threading
from types import MethodType, SimpleNamespace

import pytest

from tests.test_archive_models import saved
from yt_downloader.archive_library_ui import ArchiveLibraryMixin
from yt_downloader.archive_paths import ArchivePath
from yt_downloader.archive_work import ArchiveWorkResult


class Variable:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


def owner():
    events = []
    app = SimpleNamespace(
        _archive_worker=SimpleNamespace(busy=True, poll=lambda: None),
        _archive_commit_active=False,
        _focus_selected_view="watch",
        _closing=False,
        _media_player_launch_generation=0,
        _archive_work_deadline=0.0,
        _archive_work_timeout=None,
        _archive_work_cancel=None,
        _archive_callback=None,
        status_var=Variable(),
        _archive_status=Variable(),
        after=lambda *args: "after-token",
        product_telemetry=SimpleNamespace(
            record_operation=lambda *args, **kwargs: events.append((args, kwargs))
        ),
    )
    for name in (
        "_archive_observe",
        "_archive_retire_pending_playback",
        "_archive_request_playback",
        "_archive_poll",
    ):
        setattr(app, name, MethodType(getattr(ArchiveLibraryMixin, name), app))
    from yt_downloader.app import DownloaderApp

    app._record_playback_operation = MethodType(
        DownloaderApp._record_playback_operation, app
    )
    return app, events


@pytest.mark.parametrize("origin", ["library", "watch"])
@pytest.mark.parametrize("after_wait", ["current", "removed", "cancelled"])
def test_latest_play_intent_survives_readiness_with_current_authority(
    origin, after_wait
):
    app, events = owner()
    app._focus_selected_view = origin
    first = saved("/a/first.mp4", video="first")
    last = saved("/a/last.mp4", video="last")
    app._archive_request_playback(first)
    app._archive_request_playback(last)
    pending = app._archive_pending_playback
    assert pending["origin"] == origin
    assert [event[0][1] for event in events] == ["requested", "cancelled", "requested"]
    assert all(event[1]["dimensions"]["playback_origin"] == origin for event in events)
    # Changes after the click are authoritative when readiness arrives.
    current = {**last, "title": "Current metadata"}
    app.metadata_items = [first, current] if after_wait != "removed" else [first]
    launched = []
    app._archive_request_playback = lambda info, **kwargs: launched.append(
        (info, kwargs)
    )
    if after_wait == "cancelled":
        app._archive_retire_pending_playback()
    app._archive_worker.busy = False
    app._archive_poll()
    if after_wait == "current":
        assert launched[0][0] is current
        assert launched[0][1]["accepted"]["operation"] == pending["operation"]
        assert [event[0][1] for event in events].count("requested") == 2
    else:
        assert not launched
        assert events[-1][0][1] == "cancelled"
    assert not app.__dict__.get("_archive_pending_playback")


@pytest.mark.parametrize("action", ["check", "open"])
@pytest.mark.parametrize(
    "state", ["present", "missing", "cancelled", "selection_changed"]
)
def test_location_producer_reports_actual_outcome_without_relabeling_new_selection(
    tmp_path, monkeypatch, action, state
):
    import yt_downloader.archive_library_ui as module

    folder = tmp_path / "private-name"
    if state != "missing":
        folder.mkdir()
    path = ArchivePath.parse(str(folder))
    app, events = owner()
    app._archive_context_path = path
    received = []
    app._archive_submit = lambda kind, work, done, **kw: (
        received.append((work, done, kw)) or True
    )
    effects = []
    monkeypatch.setattr(
        module, "open_system_path", lambda native: effects.append(native)
    )
    ArchiveLibraryMixin._archive_location_request(app, path, action)
    work, done, _kwargs = received[0]
    cancelled = threading.Event()
    if state == "cancelled":
        cancelled.set()
    if state == "selection_changed":
        app._archive_context_path = ArchivePath.parse(str(tmp_path / "other"))
        app._archive_status.set("new selection")
    value = work(cancelled)
    done(ArchiveWorkResult(1, "location", value=value))
    expected = (
        "missing"
        if state == "missing"
        else "cancelled"
        if state == "cancelled"
        else "opened"
        if action == "open"
        else "available"
    )
    assert events[-1][1]["dimensions"]["archive_result"] == expected
    assert effects == (
        [folder]
        if action == "open" and state in {"present", "selection_changed"}
        else []
    )
    assert "private-name" not in repr(events)
    if state == "selection_changed":
        assert app._archive_status.value == "new selection"


def test_retired_event_pump_cannot_schedule_another_callback():
    import queue

    from yt_downloader.app import DownloaderApp

    scheduled = []
    app = SimpleNamespace(
        _event_pump_closed=True,
        events=queue.Queue(),
        _pump_events=lambda: None,
        _dispatch_ui_event=lambda event: pytest.fail(
            "Retired owner dispatched an event"
        ),
        after=lambda *args: scheduled.append(args),
    )
    DownloaderApp._pump_events(app)
    assert scheduled == []


def test_watch_details_passes_exact_projection_index_to_library_selection():
    selected, views, layout, usage = [], [], [], []
    app = SimpleNamespace(
        metadata_items=[{"id": "first"}, {"id": "second"}],
        _archive_usage=lambda *args: usage.append(args),
        _select_record_in_library=lambda record: selected.append(record),
        _select_focus_view=lambda view: views.append(view),
        _apply_focus_layout=lambda **kwargs: layout.append(kwargs),
    )
    ArchiveLibraryMixin._archive_watch_details(app, 1)
    assert selected == [{"metadata_index": 1}]
    assert views == ["library"] and app._archive_inspector_expanded
    assert layout == [{"force": True}]
    assert usage == [("watch", "details")]


def test_cancelled_recovery_folder_choice_cannot_queue_or_mutate_history(tmp_path):
    from tests.test_library_media_recovery import _job, _missing_record
    from yt_downloader.app import DownloaderApp
    from yt_downloader.library_media_recovery import LibraryMediaRecoveryOwner

    recovery = LibraryMediaRecoveryOwner()
    row = _missing_record(_job(tmp_path))
    row["vodforge_relinked"] = True
    plan = recovery.plan(row)
    assert plan.requires_destination_choice
    app = SimpleNamespace(
        _pick_output_directory=lambda: None,
        library_media_recovery=recovery,
        _start_or_queue_download_job=lambda *a, **kw: pytest.fail(
            "Cancelled recovery queued"
        ),
    )
    DownloaderApp._accept_library_redownload(app, plan)


def test_optional_playback_observation_failure_cannot_prevent_cleanup():
    from yt_downloader.app import DownloaderApp

    def failed(*args, **kwargs):
        raise OSError("unavailable telemetry")

    app = SimpleNamespace(
        product_telemetry=SimpleNamespace(record_operation=failed),
        _archive_playback_origins={"operation": "watch"},
    )
    DownloaderApp._record_playback_operation(app, "operation", "closed")
    assert app._archive_playback_origins == {}


def test_same_exact_embedded_media_refocuses_without_restarting_provider(tmp_path):
    app, events = owner()
    record = saved(tmp_path / "clip.mp4")
    focused = []
    app._media_player_source = tmp_path / "clip.mp4"
    app._media_player_window = SimpleNamespace(
        closed=False,
        focus_existing=lambda: focused.append(True),
        close=lambda: pytest.fail("Same media restarted"),
    )
    app._archive_request_playback(record)
    assert focused == [True]
    assert [event[0][1] for event in events] == ["requested", "focused"]
    assert not app._archive_playback_origins
    assert not app.__dict__.get("_archive_pending_playback")


def test_selected_artwork_replacement_retires_old_pixels_and_remote_request(tmp_path):
    first = saved(tmp_path / "clip.mp4")
    second = {**first, "thumbnail": "https://example.test/new-art.jpg"}
    submitted, rendered, invalidated = [], [], []
    app = SimpleNamespace(
        _archive_worker=SimpleNamespace(busy=False),
        metadata_items=[first],
        video_tree=SimpleNamespace(selection=lambda: ("0",)),
        _archive_submit=lambda kind, work, done: submitted.append((work, done)) or True,
        _render_focus_thumbnail_surfaces=lambda bitmap, **kwargs: rendered.append(
            bitmap
        ),
        _invalidate_thumbnail_request=invalidated.append,
    )
    ArchiveLibraryMixin._archive_selected_artwork(app, 0, first)
    app.metadata_items = [second]
    ArchiveLibraryMixin._archive_selected_artwork(app, 0, second)
    assert len(submitted) == 2
    submitted[0][1](SimpleNamespace(value=("retired pixels", tmp_path / "old.jpg")))
    assert not rendered
    submitted[1][1](SimpleNamespace(value=("current pixels", tmp_path / "new.jpg")))
    assert rendered == ["current pixels"]
    assert invalidated == ["library", "library"]


def test_latest_selected_artwork_waits_for_worker_without_losing_current_owner(
    tmp_path,
):
    app, _events = owner()
    first = saved(tmp_path / "first.mp4")
    last = saved(tmp_path / "last.mp4")
    app._invalidate_thumbnail_request = lambda target: None
    app._archive_submit = lambda *args: pytest.fail("Competing optional work submitted")
    ArchiveLibraryMixin._archive_selected_artwork(app, 0, first)
    ArchiveLibraryMixin._archive_selected_artwork(app, 0, last)
    assert app._archive_pending_artwork
    app.metadata_items = [last]
    app.video_tree = SimpleNamespace(selection=lambda: ("0",))
    received = []
    app._archive_selected_artwork = lambda index, info: received.append(info)
    app._archive_worker.busy = False
    app._archive_poll()
    assert received == [last]
    assert not app._archive_pending_artwork
