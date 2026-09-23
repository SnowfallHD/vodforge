"""The Qt Library projection must retain the source record for Play."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QSignalSpy

from yt_downloader.playback_progress import PlaybackProgressOwner
from yt_downloader.qt_quick import main as qt_main
from yt_downloader.settings_store import load_settings


def test_search_and_type_filter_keep_play_bound_to_original_history(
    tmp_path: Path, monkeypatch: Any
) -> None:
    application = QGuiApplication.instance() or QGuiApplication([])
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp3"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    records = [
        {"title": "Studio video", "vodforge_output_type": "MP4"},
        {"title": "Research audio", "vodforge_output_type": "MP3"},
    ]

    class Runtime:
        def __init__(self) -> None:
            self.recovery_notice = None
            self.history_path = tmp_path / "download-history.json"
            self.history = records
            self.activity: list[dict[str, str]] = []
            self.active_job = None
            self.submitted: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

        def start(self, *arguments: Any, **options: Any) -> object:
            self.submitted.append((arguments, options))
            self.active_job = object()
            return self.active_job

        def close(self) -> None:
            pass

    class LocalRuntime:
        def poll(self) -> list[Any]:
            return []

        def close(self) -> bool:
            return True

    monkeypatch.setattr(qt_main, "DownloadRuntime", Runtime)
    monkeypatch.setattr(qt_main, "LocalConversionRuntime", LocalRuntime)
    monkeypatch.setattr(
        qt_main, "settings_file_path", lambda: tmp_path / "settings.json"
    )
    monkeypatch.setattr(
        qt_main,
        "history_output_path",
        lambda record: first if record is records[0] else second,
    )
    bridge = qt_main.Bridge(None)
    try:
        assert bridge.downloadOptions["write_thumbnail"] is True
        assert bridge.downloadOptions["write_info_json"] is True
        assert bridge.downloadOptions["embed_metadata"] is False
        bridge.setDownloadOption("single_video_only", False)
        assert bridge.downloadOptions["single_video_only"] is False
        bridge._save_preferences()
        assert load_settings(tmp_path / "settings.json")["single_video_only"] is False
        playback_requests = QSignalSpy(bridge.playbackRequested)
        bridge.setLibrarySearch("research")
        assert [(item["sourceIndex"], item["title"]) for item in bridge.history] == [
            (1, "Research audio")
        ]
        bridge.setLibraryType("MP4")
        assert bridge.history == []
        bridge.setLibraryType("MP3")
        assert bridge.history[0]["sourceIndex"] == 1
        bridge.openLibraryItem(bridge.history[0]["sourceIndex"])
        assert bridge.playbackUrl.toLocalFile() == str(second)
        assert bridge.selection == "Watch"
        bridge.openLibraryItem(bridge.history[0]["sourceIndex"])
        assert playback_requests.count() == 2
        bridge.observePlayback(2.0, 6.0, "Playing")
        bridge.setExportMode("Auto CBR")
        assert bridge.exportMode == "Auto CBR"
        bridge.setExportMode("Strict Compliance")
        assert bridge.exportMode == "Strict Compliance"
        bridge.setExportMode("Manual Override")
        bridge._settings_writable = True
        bridge.submit("https://example.com/watch?v=example", "MP4")
        assert bridge.status == "Preparing download…"
        assert bridge._runtime.submitted[0][0][6].video_bitrate_kbps == 10000
    finally:
        bridge.close()
        application.processEvents()
    ledger = PlaybackProgressOwner(tmp_path / "watch-progress.json")
    ledger.load()
    assert ledger.for_record(records[1]).position == 2.0
    reopened = qt_main.Bridge(None)
    try:
        seeks = QSignalSpy(reopened.playbackSeekRequested)
        reopened.openLibraryItem(1)
        reopened.observePlayback(0.0, 6.0, "Playing")
        assert seeks.count() == 1
        assert seeks.at(0)[0] == 2.0
    finally:
        reopened.close()
