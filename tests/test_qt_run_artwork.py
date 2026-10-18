"""Early run artwork through real worker metadata and async cache ownership."""

from __future__ import annotations

import io
import threading
import time
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QUrl
from PySide6.QtTest import QSignalSpy

from tests.test_qt_scene_port import qt_app
from tests.test_run_identity import make_job
from yt_downloader.qt_quick import main as qt_main
from yt_downloader.qt_quick.artwork import QtArtwork
from yt_downloader.worker_events import job_info_event


def image_bytes(color="red"):
    output = io.BytesIO()
    Image.new("RGB", (320, 180), color).save(output, format="JPEG")
    return output.getvalue()


def settle(owner):
    deadline = time.monotonic() + 3
    while owner._pending and time.monotonic() < deadline:
        owner.poll()
        time.sleep(0.005)
    assert not owner._pending


def metadata():
    return {
        "id": "abcdefghijk",
        "title": "Fictional early video",
        "webpage_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "thumbnail": "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg",
    }


def test_worker_metadata_run_deck_acquires_before_completion(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    runtime = bridge._runtime
    job = make_job(tmp_path)
    runtime.recovery.begin(job, [])
    runtime.active_job = job
    runtime._reset_active_feedback(job)
    calls = []
    ui_thread = threading.get_ident()

    def download(url, **kwargs):
        assert threading.get_ident() != ui_thread
        calls.append((url, kwargs))
        return image_bytes()

    monkeypatch.setattr(
        "yt_downloader.qt_quick.artwork.download_bounded_url_bytes", download
    )
    try:
        runtime.events.put(job_info_event("job_metadata", job, metadata()))
        runtime.events.put(("status", "Transcoding media"))
        bridge._pump()
        assert bridge.runDeck["visible"][0]["artwork"] == ""
        for _ in range(5):
            _selection = bridge.forgeSelection
        spy = QSignalSpy(bridge.runDeckChanged)
        deadline = time.monotonic() + 3
        while bridge._artwork._pending and time.monotonic() < deadline:
            bridge._pump()
            time.sleep(0.005)
        assert not bridge._artwork._pending
        assert spy.count() > 0  # Actual pump publishes completed local art.
        deck = bridge.runDeck["visible"][0]
        selected = bridge.forgeSelection
        assert deck["artwork"].startswith("file:")
        assert selected["artwork"] == deck["artwork"]
        assert Path(QUrl(deck["artwork"]).toLocalFile()).is_file()
        assert runtime.active_job is job and not runtime.history
        assert len(calls) == 1
        assert calls[0][1] == {
            "source_url": metadata()["webpage_url"],
            "timeout_seconds": 15,
        }
        stale = make_job(tmp_path)
        runtime.events.put(
            job_info_event("job_metadata", stale, {**metadata(), "id": "stale"})
        )
        runtime.poll()
        assert job.preview_info["id"] == metadata()["id"]
    finally:
        runtime.active_job = None
        bridge.close()


def test_run_thumbnail_metadata_bypasses_previous_unavailable(tmp_path, monkeypatch):
    owner = QtArtwork(tmp_path / "artwork")
    calls = []
    monkeypatch.setattr(owner._source, "resolve_asset", lambda *_: None)
    monkeypatch.setattr(
        "yt_downloader.qt_quick.artwork.download_bounded_url_bytes",
        lambda url, **_: calls.append(url) or image_bytes(),
    )
    row = metadata()
    try:
        owner.request({k: v for k, v in row.items() if k != "thumbnail"}, role="run")
        settle(owner)
        owner.request(row, role="run")
        settle(owner)
        assert owner.request(row, role="run").startswith("file:")
        assert calls == [row["thumbnail"]]
    finally:
        owner.close()


def test_run_metadata_changed_during_fetch_discards_stale_publication(
    tmp_path, monkeypatch
):
    owner = QtArtwork(tmp_path / "artwork")
    started, release = threading.Event(), threading.Event()
    calls = []
    row = metadata()
    changed = {**row, "thumbnail": "https://i.ytimg.com/vi/abcdefghijk/new.jpg"}

    def download(url, **_):
        calls.append(url)
        if url == row["thumbnail"]:
            started.set()
            release.wait(2)
        return image_bytes("red" if url == row["thumbnail"] else "blue")

    monkeypatch.setattr(
        "yt_downloader.qt_quick.artwork.download_bounded_url_bytes", download
    )
    try:
        owner.request(row, role="run")
        assert started.wait(1)
        owner.request(changed, role="run")
        release.set()
        settle(owner)
        url = owner.request(changed, role="run")
        assert calls == [row["thumbnail"], changed["thumbnail"]]
        with Image.open(QUrl(url).toLocalFile()) as rendered:
            assert rendered.getpixel((0, 0))[2] > 240
    finally:
        release.set()
        owner.close()


@pytest.mark.parametrize("failure", ["network", "invalid_image"])
def test_failed_run_fetch_is_bounded_retried_and_warm_cache_reused(
    tmp_path, monkeypatch, failure
):
    owner = QtArtwork(tmp_path / "artwork")
    row = metadata()
    calls = []

    def download(url, **_):
        calls.append(url)
        if len(calls) == 1:
            if failure == "network":
                raise OSError("isolated failed fetch")
            return b"not an image"
        return image_bytes()

    monkeypatch.setattr(
        "yt_downloader.qt_quick.artwork.download_bounded_url_bytes", download
    )
    try:
        owner.request(row, role="run")
        settle(owner)
        for _ in range(5):
            assert owner.request(row, role="run") == ""
        assert len(calls) == 1  # No getter-driven unbounded retry.
        # Advance the same established cooldown, without waiting a minute.
        for key in owner._unavailable:
            owner._unavailable[key] = 0
        owner.request(row, role="run")
        settle(owner)
        ready = owner.request(row, role="run")
        assert ready.startswith("file:") and len(calls) == 2
    finally:
        owner.close()
    warm = QtArtwork(tmp_path / "artwork")
    try:
        assert warm.request(row, role="run") == ready
        settle(warm)
        assert warm.request(row, role="run") == ready
        assert len(calls) == 2  # Independent owner reads durable cache, no fetch.
    finally:
        warm.close()


def test_close_during_run_fetch_never_publishes_or_caches(tmp_path, monkeypatch):
    owner = QtArtwork(tmp_path / "artwork")
    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def download(url, **_):
        started.set()
        release.wait(2)
        finished.set()
        return image_bytes()

    monkeypatch.setattr(
        "yt_downloader.qt_quick.artwork.download_bounded_url_bytes", download
    )
    row = metadata()
    try:
        owner.request(row, role="run")
        assert started.wait(1)
        owner.close()
        release.set()
        assert finished.wait(1)
        assert owner.poll() is False
        assert owner.request(row, role="run") == ""
        assert list(tmp_path.rglob("*.jpeg")) == []
    finally:
        release.set()
        owner.close()
