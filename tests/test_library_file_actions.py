"""Worker/UI settlement preserves actual history on uncertain completion."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_archive_file_operations import item, move, move_context
from tests.test_library_restraint import _load_outbox, real_owner
from yt_downloader.archive_observations import operation
from yt_downloader.archive_work import ArchiveWorkResult
from yt_downloader.history import load_history
from yt_downloader.library_file_actions_ui import LibraryFileActionsMixin
from yt_downloader.telemetry_features import FEATURE_ACTIONS, validate_dimensions

# Imported fixtures intentionally exercise the same real, isolated file owner.
__all__ = ["item", "move_context"]
pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


def dialog():
    return SimpleNamespace(
        primary=Mock(),
        secondary=Mock(),
        note=Mock(),
        message=Mock(),
        heading=Mock(),
        exists=lambda: True,
    )


def test_uncertain_worker_result_reloads_authority_before_any_deferred_writer(
    item, move_context
):
    from threading import Event

    cancelled = Event()

    def stop(boundary):
        if boundary == "history_saved":
            cancelled.set()

    result = move(item, move_context, cancelled=cancelled, boundary=stop)
    callbacks = []
    host = SimpleNamespace(
        download_history=[item],
        history_path=move_context[1],
        _archive_worker=SimpleNamespace(busy=False),
        _archive_observe=Mock(),
        _archive_flush_history=Mock(),
        _reconcile_library_projection=Mock(),
        _show_file_recovery=Mock(),
        _archive_submit=lambda kind, work, done, **kwargs: (
            callbacks.append(done) or True
        ),
    )
    popup = dialog()
    LibraryFileActionsMixin._run_library_file_commit(
        host, popup, "move", "operation", Mock()
    )
    callbacks[0](ArchiveWorkResult(1, "file_commit", error="FileOperationUncertain"))
    assert host.download_history == load_history(move_context[1])
    assert (
        host.download_history[0]["vodforge_output_path"]
        == result.records[0]["vodforge_output_path"]
    )
    assert host._archive_file_recovery_blocked and not host._archive_commit_active
    host._archive_flush_history.assert_not_called()
    host._show_file_recovery.assert_called_once()


@pytest.mark.parametrize("permission", ["allowed", "denied", "withdrawn"])
def test_file_observations_obey_consent_and_exclude_file_content(tmp_path, permission):
    telemetry = real_owner(tmp_path, permitted=permission != "denied")
    if permission == "withdrawn":
        telemetry.set_enabled(False)
    import uuid

    key = str(uuid.uuid4())
    for action, dimensions in [
        ("requested", {"file_action": "move", "item_count": "2"}),
        ("started", {"file_action": "move"}),
        ("needs_attention", {"file_action": "move"}),
    ]:
        assert action in FEATURE_ACTIONS["library_file_operation"]
        validate_dimensions(dimensions)
        operation(telemetry, "library_file_operation", action, key, dimensions)
    assert telemetry.shutdown(2)
    events = [
        e
        for e in _load_outbox(tmp_path / "events.json")
        if e.feature == "library_file_operation"
    ]
    assert [event.action for event in events] == (
        ["requested", "started", "needs_attention"] if permission == "allowed" else []
    )
    payload = json.dumps([event.public_payload() for event in events])
    assert str(tmp_path) not in payload
    with pytest.raises(ValueError):
        validate_dimensions({"file_action": "/private/filename.mp4"})


def test_unexpected_observation_failure_cannot_own_file_outcomes():
    observer = SimpleNamespace(
        record_operation=Mock(side_effect=RuntimeError("offline"))
    )
    assert not operation(
        observer,
        "library_file_operation",
        "completed",
        "key",
        {"file_action": "delete", "committed_count": "2"},
    )


def test_second_recovery_click_cannot_release_an_active_commit_lock():
    submitted = []
    host = SimpleNamespace(
        _archive_commit_active=True,
        _archive_worker=SimpleNamespace(busy=False),
        _archive_submit=lambda *args, **kwargs: submitted.append(args),
    )
    LibraryFileActionsMixin._run_library_file_commit(
        host, dialog(), "recovery", "key", Mock()
    )
    assert host._archive_commit_active and submitted == []


@pytest.mark.parametrize("action", ["move", "delete"])
def test_single_file_decision_does_not_start_competing_inspector_work(action):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from yt_downloader.app import DownloaderApp
    from yt_downloader.archive_browser import archive_row_owner

    record = {"id": "selected", "vodforge_output_path": "/saved/selected.mp4"}
    view = SimpleNamespace(
        metadata_items=[record],
        video_tree=Mock(),
        _display_selected_metadata=Mock(),
        _begin_library_file_action=Mock(),
    )
    DownloaderApp._library_scene_action(view, action, 0)
    view._begin_library_file_action.assert_called_once_with(
        action, (archive_row_owner(record),)
    )
    view._display_selected_metadata.assert_not_called()
    view.video_tree.selection_set.assert_not_called()


@pytest.mark.parametrize(
    "permission",
    [
        "allowed",
        "denied",
        "late_grant",
        "regrant",
        "observer_unavailable",
        "observer_failure",
    ],
)
@pytest.mark.parametrize(
    "outcome,transition",
    [
        ("completed", "preview"),
        ("completed", "commit"),
        ("needs_attention", "preview"),
        ("needs_attention", "commit"),
        ("cancelled", "preview"),
        ("inspection_error", "preview"),
        ("inspection_timeout", "preview"),
        ("inspection_closed", "preview"),
    ],
)
def test_file_action_producer_keeps_starting_consent(
    tmp_path, monkeypatch, permission, outcome, transition
):
    from pathlib import Path
    from threading import Event
    from types import MethodType

    from yt_downloader import library_file_actions_ui as module
    from yt_downloader.archive_library_ui import ArchiveLibraryMixin
    from yt_downloader.history import history_archive_owner, save_history

    folder = tmp_path / "PRIVATE media"
    folder.mkdir()
    row = {
        "id": "PRIVATE-id",
        "title": "PRIVATE title",
        "vodforge_recorded_at": "2026-09-17T00:00:00+00:00",
        "vodforge_output_type": "MP4",
        "vodforge_output_path": str(folder / "PRIVATE missing.mp4"),
        "vodforge_output_dir": str(folder),
    }
    history = tmp_path / "history.json"
    save_history(history, [row])
    row = load_history(history)[0]
    telemetry = real_owner(tmp_path)
    if permission in {"denied", "late_grant"}:
        telemetry.set_enabled(False)
    if permission in {"observer_unavailable", "observer_failure"}:
        monkeypatch.setattr(
            telemetry,
            "bind_operation"
            if permission == "observer_unavailable"
            else "record_operation",
            Mock(side_effect=OSError("PRIVATE observer failure")),
        )
    popup = dialog()
    popup.finished = False
    popup.popup = Mock()
    offered, queued = [], []
    popup.offer = lambda label, callback, **kwargs: offered.append(
        (label, callback, kwargs)
    )
    monkeypatch.setattr(module, "FileActionDialog", lambda *args, **kwargs: popup)
    host = SimpleNamespace(
        product_telemetry=telemetry,
        download_history=[row],
        metadata_items=[],
        history_path=history,
        _archive_worker=SimpleNamespace(busy=False),
        _archive_flush_history=Mock(),
        _archive_cancel_work=Mock(),
        _reconcile_library_projection=Mock(),
        _show_file_recovery=Mock(),
        _archive_submit=lambda kind, work, done, **kwargs: (
            queued.append((kind, work, done, kwargs)) or True
        ),
    )
    host._archive_observe = MethodType(ArchiveLibraryMixin._archive_observe, host)
    for name in (
        "_commit_library_files",
        "_run_library_file_commit",
        "_cancel_library_file_dialog",
    ):
        setattr(host, name, MethodType(getattr(LibraryFileActionsMixin, name), host))
    try:
        LibraryFileActionsMixin._begin_library_file_action(
            host, "delete", (history_archive_owner(row),)
        )
        kind, work, done, options = queued.pop(0)
        assert kind == "file_preview"

        def change_permission():
            if permission == "late_grant":
                telemetry.set_enabled(True)
            elif permission == "regrant":
                telemetry.set_enabled(False)
                telemetry.set_enabled(True)

        inspection_failure = outcome.startswith("inspection_")
        if inspection_failure:
            change_permission()
            if outcome == "inspection_error":
                done(SimpleNamespace(value=None, error="PRIVATE unreadable storage"))
            else:
                if outcome == "inspection_closed":
                    popup.exists = lambda: False
                options["on_timeout"]()
            assert not offered and not queued
            if outcome == "inspection_closed":
                popup.message.set.assert_not_called()
            else:
                assert "try again" in popup.message.set.call_args.args[0].lower()
        else:
            done(SimpleNamespace(value=work(Event()), error=None))
            assert offered[-1][0] == "Remove entries" and offered[-1][2]["enabled"]
            if transition == "preview":
                change_permission()
            if outcome == "cancelled":
                host._cancel_library_file_dialog(popup)
                assert not queued
            else:
                offered[-1][1]()
                kind, work, done, _options = queued.pop(0)
                assert kind == "file_commit" and host._archive_commit_active
                if transition == "commit":
                    change_permission()
                if outcome == "needs_attention":
                    done(SimpleNamespace(value=None, error="HistoryError"))
                else:
                    done(SimpleNamespace(value=work(Event()), error=None))
                assert not host._archive_commit_active
        telemetry.shutdown(2)
        events = [
            event
            for event in _load_outbox(tmp_path / "events.json")
            if event.feature == "library_file_operation"
        ]
        expected = (
            ["requested"]
            if outcome == "inspection_closed"
            else ["requested", "needs_attention"]
            if inspection_failure
            else ["requested", "cancelled"]
            if outcome == "cancelled"
            else ["requested", "started", outcome]
        )
        assert [event.action for event in events] == (
            expected if permission == "allowed" else []
        )
        assert load_history(history) == ([] if outcome == "completed" else [row])
        if outcome == "completed":
            assert popup.finished
        payloads = [event.public_payload() for event in events]
        assert "PRIVATE" not in json.dumps(payloads) and str(
            tmp_path
        ) not in json.dumps(payloads)
        if events:
            assert [event.dimensions.get("stage") for event in events] == (
                ["analysis"]
                if outcome == "inspection_closed"
                else ["analysis", "analysis"]
                if inspection_failure or outcome == "cancelled"
                else ["analysis", "commit", "commit"]
            )
            assert len({event.dimensions["operation_id"] for event in events}) == 1
            assert [event.dimensions["operation_step"] for event in events] == [
                str(i + 1) for i in range(len(events))
            ]
            import os

            destination = os.environ.get("VODFORGE_FILE_ACTION_FIXTURE_DIR")
            if (
                destination
                and transition == "preview"
                and outcome != "inspection_closed"
            ):
                output = Path(destination)
                output.mkdir(parents=True, exist_ok=True)
                (output / f"{outcome}.json").write_text(json.dumps(payloads, indent=2))
    finally:
        telemetry.shutdown(2)
