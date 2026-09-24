"""Qt Library removal must keep its confirmed owner and durable history."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QSignalSpy

from yt_downloader.history import HistoryError, history_archive_owner, load_history
from yt_downloader.qt_quick import main as qt_main


@pytest.fixture
def bridge(tmp_path: Path, monkeypatch: Any) -> qt_main.Bridge:
    app = QGuiApplication.instance() or QGuiApplication([])
    media = tmp_path / "saved.mp4"
    media.write_bytes(b"media remains")
    record = {
        "id": "saved-one",
        "title": "Saved",
        "vodforge_output_type": "MP4",
        "vodforge_output_dir": str(tmp_path),
        "vodforge_output_path": str(media),
        "chapters": [
            {"start_time": 3, "end_time": 6, "title": "Opening"},
            {"start_time": -1, "end_time": 4, "title": "Invalid"},
        ],
        "heatmap": [
            {"start_time": 0, "end_time": 3, "value": 0.5},
            {"start_time": 3, "end_time": 6, "value": float("nan")},
        ],
    }

    class Runtime:
        def __init__(self) -> None:
            self.recovery = object()
            self.recovery_notice = None
            self.history_path = tmp_path / "history.json"
            self.history = [record]
            self.active_job = None
            self.queued: list[Any] = []
            self.activity: list[Any] = []

        def resume_queued(self) -> None:
            pass

        def close(self) -> None:
            pass

    class LocalRuntime:
        def close(self) -> None:
            pass

    monkeypatch.setattr(qt_main, "DownloadRuntime", Runtime)
    monkeypatch.setattr(qt_main, "LocalConversionRuntime", LocalRuntime)
    monkeypatch.setattr(
        qt_main, "settings_file_path", lambda: tmp_path / "settings.json"
    )
    subject = qt_main.Bridge(None)
    yield subject
    subject.close()
    app.processEvents()


def test_removal_commits_exact_saved_card_without_deleting_media(
    bridge: qt_main.Bridge,
) -> None:
    item = bridge._runtime.history[0]
    media = Path(item["vodforge_output_path"])
    owner = history_archive_owner(item)
    assert bridge.prepareLibraryRemoval(owner)
    assert bridge.confirmLibraryRemoval()
    assert bridge._runtime.history == []
    assert load_history(bridge._runtime.history_path) == []
    assert media.read_bytes() == b"media remains"


def test_removing_saved_card_preserves_another_active_staging_owner(
    bridge: qt_main.Bridge,
) -> None:
    item = bridge._runtime.history[0]
    root = Path(item["vodforge_output_dir"]) / ".vfstage"
    active = root / "another-active-run"
    active.mkdir(parents=True)
    sentinel = active / "in-progress.part"
    sentinel.write_bytes(b"owned by another run")

    assert bridge.prepareLibraryRemoval(history_archive_owner(item))
    assert bridge.confirmLibraryRemoval()
    assert sentinel.read_bytes() == b"owned by another run"
    assert bridge._runtime.history == []


def test_removal_refuses_changed_owner_and_failed_durable_commit(
    bridge: qt_main.Bridge, monkeypatch: Any
) -> None:
    item = bridge._runtime.history[0]
    owner = history_archive_owner(item)
    assert bridge.prepareLibraryRemoval(owner)
    item["title"] = "Changed while confirmation was open"
    assert not bridge.confirmLibraryRemoval()
    assert len(bridge._runtime.history) == 1

    assert bridge.prepareLibraryRemoval(owner)

    def fail_save(_path: Path, _rows: list[dict[str, Any]]) -> None:
        raise HistoryError("durable write failed")

    monkeypatch.setattr(qt_main, "save_history", fail_save)
    assert not bridge.confirmLibraryRemoval()
    assert len(bridge._runtime.history) == 1


def test_removal_refuses_new_queued_owner_after_confirmation(
    bridge: qt_main.Bridge,
) -> None:
    item = bridge._runtime.history[0]
    owner = history_archive_owner(item)
    assert bridge.prepareLibraryRemoval(owner)
    item["vodforge_queued_run_id"] = "run-one"
    bridge._runtime.queued = [type("Job", (), {"run_id": "run-one"})()]
    assert not bridge.confirmLibraryRemoval()
    assert len(bridge._runtime.history) == 1


def test_watch_uses_bounded_saved_chapters_and_shared_seek(
    bridge: qt_main.Bridge,
) -> None:
    requested = QSignalSpy(bridge.playbackSeekRequested)
    bridge.openLibraryItem(0)
    assert bridge.playbackChapters == [
        {"start_time": 3.0, "end_time": 6.0, "title": "Opening"}
    ]
    assert bridge.playbackHeatmap == [
        {"start_time": 0.0, "end_time": 3.0, "value": 0.5}
    ]
    assert not bridge.seekPlaybackChapter(1)
    assert bridge.seekPlaybackChapter(0)
    assert requested.count() == 1
    assert requested.at(0)[0] == 3.0
    bridge.manualPlaybackSeek(2.0)
    assert requested.count() == 2
    assert requested.at(1)[0] == 2.0
