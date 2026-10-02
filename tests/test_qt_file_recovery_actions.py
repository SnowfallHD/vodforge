"""Unverified saved files offer recovery without acquiring deletion authority."""

import time

import pytest
from PySide6.QtCore import QUrl

from tests.test_qt_scene_port import make_job, qt_app, qt_main, saved
from yt_downloader.history import history_archive_owner, save_history
from yt_downloader.qt_quick import library_files


@pytest.mark.parametrize("trash_available", [True, False])
def test_unreachable_saved_path_can_forget_card_without_deleting_files(
    tmp_path, monkeypatch, trash_available
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    item = saved(tmp_path / "Dropbox-like" / "unreachable", "saved", "MP4")
    owner = history_archive_owner(item)
    bridge._runtime.history = [item]
    save_history(bridge._runtime.history_path, [item])
    unrelated = tmp_path / "unrelated.mp4"
    unrelated.write_bytes(b"keep this file")
    monkeypatch.setattr(
        library_files, "system_trash_available", lambda: trash_available
    )
    try:
        started = bridge.startFileAction("delete", owner, QUrl())
        if trash_available:
            assert started
            for _ in range(100):
                bridge._pump()
                if bridge._files.phase == "preview":
                    break
                time.sleep(0.01)
            assert "could not be accessed" in bridge.fileActionStatus
            assert bridge.fileActionReviewOwner == owner
        else:
            assert not started
            assert "Trash is unavailable" in bridge.fileActionStatus
            assert bridge.fileActionReviewOwner == ""
        assert not bridge.fileActionEligible
        assert not bridge.confirmFileAction()
        assert bridge.prepareLibraryRemoval(owner)
        assert bridge.confirmLibraryRemoval()
        assert bridge._runtime.history == []
        assert unrelated.read_bytes() == b"keep this file"
        assert not (tmp_path / "Dropbox-like").exists()
        assert bridge.fileActionReviewOwner == ""
    finally:
        bridge.close()


def test_forge_retry_follows_selected_issue_without_overwriting_other_active_status(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    failed = make_job(tmp_path)
    bridge._runtime.recovery.terminal_attempt(failed, "Failed", "Original failure")
    bridge._runtime.recovered = bridge._runtime.recovery.store.load_terminal_jobs()
    active = make_job(tmp_path)
    bridge._runtime.recovery.begin(active)
    bridge._runtime.active_job = active
    bridge._status = "Downloading active owner"
    feedback = []
    bridge.operationFeedback.connect(feedback.append)
    try:
        bridge.select("Library")
        bridge.navigateLibraryFolders("issues")
        component = bridge.libraryFolders["components"][0]
        assert bridge.selectLibraryFolderComponent(component["key"])
        original_key = bridge._folder_inspector_key
        assert bridge.retryTerminal(failed.run_id)
        retry = bridge._runtime.queued[0]
        assert bridge._issue_run_id == retry.run_id
        assert bridge._folder_inspector_key != original_key
        assert bridge.status == "Downloading active owner"
        assert feedback == ["Added retry to the queue."]
        bridge.select("Library")
        assert bridge.libraryFolderInspector["status"] == "Queued"
        assert not bridge.openInspectorLocation(original_key)
    finally:
        bridge.close()
