"""Qt file actions use the durable exact-file owner with confirmed snapshots."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from yt_downloader.archive_file_operations import delete_files
from yt_downloader.history import history_archive_owner, load_history, save_history
from yt_downloader.qt_quick import library_files as qt_files


def _fixture(tmp_path: Path) -> tuple[qt_files.QtLibraryFiles, dict[str, Any], Path]:
    folder = tmp_path / "saved-item"
    folder.mkdir()
    media = folder / "video.mp4"
    media.write_bytes(b"owned fixture media")
    row = {
        "id": "fixture-id",
        "title": "Fixture",
        "vodforge_output_type": "MP4",
        "vodforge_recorded_at": "2026-09-23T00:00:00+00:00",
        "vodforge_output_path": str(media),
        "vodforge_output_dir": str(folder),
    }
    history = tmp_path / "history.json"
    save_history(history, [row])
    return qt_files.QtLibraryFiles(history), row, media


def _wait(session: qt_files.QtLibraryFiles, phase: str) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        session.poll()
        if session.phase == phase:
            return
        time.sleep(0.01)
    raise AssertionError(f"file session stayed in {session.phase}: {session.status}")


def test_qt_move_uses_exact_file_plan_and_durable_history(tmp_path: Path) -> None:
    session, row, media = _fixture(tmp_path)
    destination = tmp_path / "moved"
    destination.mkdir()
    try:
        assert session.begin(
            "move", history_archive_owner(row), [row], destination=destination
        )
        _wait(session, "preview")
        assert session.eligible
        assert session.confirm([row])
        _wait(session, "done")
        moved = destination / media.parent.name / media.name
        assert moved.read_bytes() == b"owned fixture media"
        assert not media.exists()
        assert load_history(session.history_path)[0]["vodforge_output_path"] == str(
            moved
        )
        assert session.pending == ()
    finally:
        session.close()


def test_qt_file_confirmation_refuses_changed_library(tmp_path: Path) -> None:
    session, row, media = _fixture(tmp_path)
    destination = tmp_path / "moved"
    destination.mkdir()
    try:
        assert session.begin(
            "move", history_archive_owner(row), [row], destination=destination
        )
        _wait(session, "preview")
        assert not session.confirm([dict(row, title="Changed")])
        assert session.phase == "error"
        assert media.read_bytes() == b"owned fixture media"
        assert load_history(session.history_path)[0]["title"] == "Fixture"
    finally:
        session.close()


def test_qt_file_worker_refuses_new_durable_history_after_preview(
    tmp_path: Path,
) -> None:
    session, row, media = _fixture(tmp_path)
    destination = tmp_path / "moved"
    destination.mkdir()
    try:
        assert session.begin(
            "move", history_archive_owner(row), [row], destination=destination
        )
        _wait(session, "preview")
        save_history(session.history_path, [dict(row, title="Durably changed")])
        assert session.confirm([row])
        _wait(session, "error")
        assert media.read_bytes() == b"owned fixture media"
        assert not (destination / media.parent.name).exists()
        assert load_history(session.history_path)[0]["title"] == "Durably changed"
    finally:
        session.close()


def test_qt_trash_commits_only_after_existing_owner_succeeds(
    tmp_path: Path, monkeypatch: Any
) -> None:
    session, row, media = _fixture(tmp_path)
    trash = tmp_path / "fixture-trash"
    trash.mkdir()
    monkeypatch.setattr(qt_files, "system_trash_available", lambda: True)
    original_delete = delete_files

    def use_fixture_trash(*args: Any, **kwargs: Any) -> Any:
        return original_delete(
            *args,
            **kwargs,
            trash=lambda path: str(path.rename(trash / path.name)),
        )

    monkeypatch.setattr(qt_files, "delete_files", use_fixture_trash)
    try:
        assert session.begin("delete", history_archive_owner(row), [row])
        _wait(session, "preview")
        assert session.confirm([row])
        _wait(session, "done")
        assert load_history(session.history_path) == []
        assert not media.exists()
        assert (trash / media.name).read_bytes() == b"owned fixture media"
    finally:
        session.close()


def test_qt_interrupted_move_blocks_and_uses_verified_finish(
    tmp_path: Path, monkeypatch: Any
) -> None:
    session, row, media = _fixture(tmp_path)
    destination = tmp_path / "moved"
    destination.mkdir()
    original_move = qt_files.move_files

    def interrupt_after_history(*args: Any, **kwargs: Any) -> Any:
        def boundary(stage: str) -> None:
            if stage == "history_saved":
                raise OSError("injected interruption")

        return original_move(*args, **kwargs, boundary=boundary)

    monkeypatch.setattr(qt_files, "move_files", interrupt_after_history)
    try:
        assert session.begin(
            "move", history_archive_owner(row), [row], destination=destination
        )
        _wait(session, "preview")
        assert session.confirm([row])
        _wait(session, "recovery")
        assert session.uncertain and session.can_finish
        assert session.recover(finish=True)
        _wait(session, "done")
        assert not session.uncertain and session.pending == ()
        assert not media.exists()
        assert (destination / media.parent.name / media.name).read_bytes() == (
            b"owned fixture media"
        )
    finally:
        session.close()
