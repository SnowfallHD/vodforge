"""Playlist child terminal events keep their durable retry and Library owner."""

from __future__ import annotations

import uuid
from dataclasses import replace
from pathlib import Path

import pytest

from yt_downloader.library_state import LibraryProjectionOwner
from yt_downloader.models import DownloadJob
from yt_downloader.qt_quick.runtime import DownloadRuntime
from yt_downloader.run_state import RunStateError


def _runtime_with_active_parent(
    tmp_path: Path, monkeypatch
) -> tuple[DownloadRuntime, DownloadJob]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    output = tmp_path / "Downloads"
    output.mkdir()
    runtime = DownloadRuntime()
    parent = runtime.prepare_job(
        "https://www.youtube.com/watch?v=abcdefghijk",
        output,
        "MP4",
        "Everyday",
        batch_mode=True,
    )
    runtime.recovery.begin(parent, [])
    runtime.active_job = parent
    return runtime, parent


def _child(parent: DownloadJob, *, origin: str | None = None) -> DownloadJob:
    return replace(
        parent,
        run_id=uuid.uuid4().hex,
        origin_run_id=parent.run_id if origin is None else origin,
        execution_run_id=parent.run_id,
        urls=[parent.url],
        batch_mode=False,
        terminal_status="Skipped",
        terminal_message="Skipped this playlist item.",
    )


@pytest.mark.parametrize(
    ("kind", "expected"), [("done", True), ("partial", False), ("error", False)]
)
def test_qt_missing_media_completion_feature_requires_completed_recovery(
    tmp_path: Path, monkeypatch, kind: str, expected: bool
) -> None:
    runtime, parent = _runtime_with_active_parent(tmp_path, monkeypatch)
    parent.recovery_reason = "missing_media"

    class Observer:
        def __init__(self):
            self.features = []

        def record(self, *_args, **_kwargs):
            return True

        def record_feature(self, feature, action):
            self.features.append((feature, action))
            return True

    observer = Observer()
    runtime.product_telemetry = observer
    try:
        runtime._finish(kind, "Finished recovery attempt")
        assert (("missing_media", "completed") in observer.features) is expected
    finally:
        runtime.close()


def test_qt_missing_media_completion_is_not_reported_before_durable_finish(
    tmp_path: Path, monkeypatch
) -> None:
    runtime, parent = _runtime_with_active_parent(tmp_path, monkeypatch)
    parent.recovery_reason = "missing_media"

    class Observer:
        def __init__(self):
            self.features = []

        def record(self, *_args, **_kwargs):
            return True

        def record_feature(self, feature, action):
            self.features.append((feature, action))
            return True

    observer = Observer()
    runtime.product_telemetry = observer

    def reject_finish(*_args, **_kwargs):
        raise RunStateError("durable finish refused")

    monkeypatch.setattr(runtime.recovery, "finished", reject_finish)
    try:
        with pytest.raises(RunStateError):
            runtime._finish("done", "Finished recovery attempt")
        assert ("missing_media", "completed") not in observer.features
    finally:
        runtime.close()


def test_qt_playlist_child_is_durable_and_visible_without_ending_parent(
    tmp_path: Path, monkeypatch
) -> None:
    runtime, parent = _runtime_with_active_parent(tmp_path, monkeypatch)
    child = _child(parent)
    info = {"id": "child", "title": "Skipped item"}
    try:
        runtime.events.put(("item_terminal", {"job": child, "info": info}))
        events = runtime.poll()
        assert events[0][0] == "item_terminal"
        assert runtime.active_job is parent
        assert [job.run_id for job in runtime.recovered] == [child.run_id]
        assert runtime.recovered[0].terminal_status == "Skipped"
        assert runtime.recovered[0].preview_info["title"] == "Skipped item"
        assert runtime.recovery.store.load_terminal_jobs()[0].run_id == child.run_id
        assert runtime.activity[0]["status"] == "Skipped"
        assert runtime.activity[0]["title"] == "Skipped item"
        projection = LibraryProjectionOwner().reconcile(
            history_items=runtime.history,
            active_job=runtime.active_job,
            queued_jobs=runtime.queued,
            terminal_jobs=runtime.recovered,
        )
        assert any(
            row.get("vodforge_projection_owner") == f"run:{child.run_id}"
            and row.get("vodforge_terminal_status") == "Skipped"
            for row in projection.rows
        )
    finally:
        runtime.close()


def test_qt_playlist_child_rejects_stale_owner_and_durable_failure(
    tmp_path: Path, monkeypatch
) -> None:
    runtime, parent = _runtime_with_active_parent(tmp_path, monkeypatch)
    try:
        runtime.events.put(
            (
                "item_terminal",
                {"job": _child(parent, origin="other-run"), "info": {"title": "Stale"}},
            )
        )
        assert runtime.poll() == []
        assert runtime.recovered == []

        def refuse(*_args):
            raise RunStateError("durable write refused")

        monkeypatch.setattr(runtime.recovery, "terminal_attempt", refuse)
        runtime.events.put(
            ("item_terminal", {"job": _child(parent), "info": {"title": "Child"}})
        )
        with pytest.raises(RunStateError, match="durable write refused"):
            runtime.poll()
        assert runtime.recovered == []
        assert runtime.recovery.store.load_terminal_jobs() == []
    finally:
        runtime.close()
