"""Metadata preview uses the shared provider operation and Qt's transient UI state."""

from __future__ import annotations

import time
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from typing import Any, Self

from PySide6.QtGui import QGuiApplication

from yt_downloader import app as app_module
from yt_downloader.models import OutputType
from yt_downloader.qt_quick import main as qt_main
from yt_downloader.qt_quick import metadata_preview as preview_module


def test_shared_metadata_preview_is_provider_gated_and_metadata_only(monkeypatch):
    captured: dict[str, Any] = {}

    class YoutubeDL:
        def __init__(self, options: dict[str, Any]) -> None:
            captured.update(options)

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def extract_info(self, url: str, *, download: bool) -> dict[str, Any]:
            assert url == "https://www.youtube.com/watch?v=abcdefghijk"
            assert download is False
            return {"id": "abcdefghijk", "title": "Example"}

    class Gate:
        def run_preview(self, step: Any, *, should_abort: Any) -> tuple[bool, Any]:
            assert not should_abort()
            captured["gated"] = True
            return True, step()

    monkeypatch.setattr(
        app_module, "load_yt_dlp", lambda: SimpleNamespace(YoutubeDL=YoutubeDL)
    )
    monkeypatch.setattr(
        app_module, "run_tracked_ytdlp_operation", lambda step, **_kw: step()
    )
    result = app_module.fetch_metadata_preview(
        "https://www.youtube.com/watch?v=abcdefghijk",
        OutputType.MP3,
        ignore_playlists=True,
        cookie_inputs=(False, None, None),
        ffmpeg=None,
        deno=None,
        logger=object(),
        coordinator=Gate(),
        should_abort=lambda: False,
    )
    assert captured["gated"] is True
    assert captured["skip_download"] is True
    assert captured["noplaylist"] is True
    assert result == {
        "id": "abcdefghijk",
        "title": "Example",
        "vodforge_output_type": "MP3",
    }


def test_qt_preview_is_transient_then_admits_one_canonical_job(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    (tmp_path / "Downloads").mkdir()
    QGuiApplication.instance() or QGuiApplication([])
    monkeypatch.setattr(
        preview_module,
        "fetch_metadata_preview",
        lambda *_args, **_kwargs: {
            "id": "abcdefghijk",
            "title": "Shared preview",
            "webpage_url": "https://www.youtube.com/watch?v=abcdefghijk",
            "vodforge_output_type": "MP4",
        },
    )
    bridge = qt_main.Bridge(None)
    try:
        source = "https://www.youtube.com/watch?v=abcdefghijk"
        assert bridge.previewMetadata(source, "MP4")
        assert bridge.forgePreview["phase"] == "loading"
        assert bridge._runtime.history == []
        for _ in range(100):
            bridge._pump()
            if bridge.forgePreview["phase"] == "complete":
                break
            time.sleep(0.01)
        assert bridge.forgePreview["phase"] == "complete"
        assert bridge.forgePreview["title"] == "Shared preview"
        assert bridge.runDeck["records"][0]["kind"] == "preview"
        assert bridge._runtime.history == []
        bridge.navigateLibraryFolders("activity")
        preview_card = next(
            item
            for item in bridge.libraryFolders["components"]
            if item["kind"] == "activity" and item["title"] == "Shared preview"
        )
        assert bridge.openLibraryFolderComponent(preview_card["key"])
        assert bridge.selection == "Forge"
        assert bridge.forgePreview["title"] == "Shared preview"

        started, release = Event(), Event()

        def delayed_preview(*_args: Any, **_kwargs: Any) -> dict[str, str]:
            started.set()
            assert release.wait(timeout=1)
            return {
                "id": "bbbbbbbbbbb",
                "title": "Later preview",
                "webpage_url": "https://www.youtube.com/watch?v=bbbbbbbbbbb",
                "vodforge_output_type": "MP4",
            }

        monkeypatch.setattr(preview_module, "fetch_metadata_preview", delayed_preview)
        assert bridge.previewMetadata(
            "https://www.youtube.com/watch?v=bbbbbbbbbbb", "MP4"
        )
        assert started.wait(timeout=1)
        assert bridge.openPreviewOwner(preview_card["key"])
        release.set()
        for _ in range(100):
            bridge._pump()
            if any(
                item["title"] == "Later preview" for item in bridge.runDeck["records"]
            ):
                break
            time.sleep(0.01)
        assert bridge.forgePreview["title"] == "Shared preview"
        assert any(
            item["title"] == "Later preview" for item in bridge.runDeck["records"]
        )

        admitted = []

        def accept(job: Any) -> Any:
            admitted.append(job)
            bridge._runtime.active_job = job
            return job

        monkeypatch.setattr(bridge._runtime, "start_job", accept)
        assert bridge.startPreviewDownload()
        assert len(admitted) == 1
        assert admitted[0].preview_info["title"] == "Shared preview"
        assert admitted[0].preview_source_owner
        assert bridge.forgePreview["phase"] == "idle"
        assert bridge._runtime.history == []
    finally:
        bridge.close()
