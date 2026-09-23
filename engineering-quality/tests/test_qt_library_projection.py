"""The Qt Library projection must retain the source record for Play."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtGui import QGuiApplication

from yt_downloader.qt_quick import main as qt_main


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
            self.history = records
            self.activity: list[dict[str, str]] = []
            self.active_job = None

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
    finally:
        bridge.close()
        application.processEvents()
