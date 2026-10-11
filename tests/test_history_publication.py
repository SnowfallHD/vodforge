"""A successful media file does not imply its history write also succeeded."""

from copy import deepcopy
from unittest.mock import Mock

import pytest

from yt_downloader import library_history as app_module
from yt_downloader.history import HistoryError, upsert_history
from yt_downloader.library_annotations import LibraryAnnotation, LibraryAnnotationsOwner
from yt_downloader.library_history import LibraryHistory


def state(tmp_path):
    return LibraryHistory(tmp_path / "history.json")


def record(tmp_path, title="Completed media"):
    return {
        "id": "same-media",
        "title": title,
        "webpage_url": "https://example.test/same-media",
        "vodforge_output_type": "MP4",
        "vodforge_output_path": str(tmp_path / "completed.mp4"),
    }


def test_new_history_failure_keeps_saved_media_and_does_not_publish_row(
    tmp_path, monkeypatch
):
    view = state(tmp_path)
    media = tmp_path / "completed.mp4"
    media.write_bytes(b"completed media")
    monkeypatch.setattr(
        app_module,
        "save_history",
        Mock(side_effect=HistoryError("Controlled full disk")),
    )
    with pytest.raises(HistoryError):
        view.record(record(tmp_path), tmp_path)
    assert view.download_history == [] and not view.history_path.exists()
    assert media.read_bytes() == b"completed media"


def test_retry_after_failed_history_write_publishes_one_durable_row(
    tmp_path, monkeypatch
):
    view = state(tmp_path)
    save = app_module.save_history
    monkeypatch.setattr(
        app_module, "save_history", Mock(side_effect=HistoryError("Controlled failure"))
    )
    with pytest.raises(HistoryError):
        view.record(record(tmp_path), tmp_path)
    monkeypatch.setattr(app_module, "save_history", save)
    view.record(record(tmp_path), tmp_path)
    assert len(view.download_history) == 1 and view.history_path.is_file()
    assert view.download_history[0]["title"] == "Completed media"


def test_existing_row_update_failure_preserves_previous_row_and_annotations(
    tmp_path, monkeypatch
):
    view = state(tmp_path)
    view.download_history = upsert_history([], record(tmp_path, "Old title"), tmp_path)
    app_module.save_history(view.history_path, view.download_history)
    before = deepcopy(view.download_history)
    disk = view.history_path.read_bytes()
    annotations = LibraryAnnotationsOwner(tmp_path / "annotations.json")
    annotations.replace(
        "saved-owner", LibraryAnnotation("My note", ("My tag",), "Trips")
    )
    personal = annotations.path.read_bytes()
    monkeypatch.setattr(
        app_module, "save_history", Mock(side_effect=HistoryError("Controlled failure"))
    )
    with pytest.raises(HistoryError):
        view.record(record(tmp_path, "Updated title"), tmp_path)
    assert view.download_history == before and view.history_path.read_bytes() == disk
    assert annotations.path.read_bytes() == personal


def test_existing_row_successful_update_does_not_duplicate_the_owner(tmp_path):
    view = state(tmp_path)
    view.record(record(tmp_path, "Old title"), tmp_path)
    view.record(record(tmp_path, "Updated title"), tmp_path)
    assert (
        len(view.download_history) == 1
        and view.download_history[0]["title"] == "Updated title"
    )


def test_history_recovery_block_still_prevents_admission(tmp_path, monkeypatch):
    view = state(tmp_path)
    view.blocked = True
    save = Mock()
    monkeypatch.setattr(app_module, "save_history", save)
    with pytest.raises(HistoryError):
        view.record(record(tmp_path), tmp_path)
    save.assert_not_called()
    assert view.download_history == []


def test_active_archive_commit_still_defers_through_existing_journal(tmp_path):
    from yt_downloader.history import pending_history_path, sanitize_history_record

    view = state(tmp_path)
    item = record(tmp_path)
    view.defer(
        "record",
        lambda: view.record(item, tmp_path),
        mutation={"kind": "record", "record": sanitize_history_record(item, tmp_path)},
    )
    assert view.download_history == []
    assert pending_history_path(view.history_path).is_file()
    assert view.flush()
    assert len(view.download_history) == 1
