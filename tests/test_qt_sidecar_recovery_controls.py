"""Actual QML pointer admission; repair I/O invariants live in owner tests."""

import os
import shutil
import subprocess
import time
from pathlib import Path
from threading import Event

import pytest
from PySide6.QtCore import QObject, QPointF, Qt
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch
from tests.test_qt_optional_sidecar_recovery import fixture, image_bytes
from tests.test_qt_scene_port import polish_scene, visual_item
from yt_downloader.qt_quick import main as qt_main
from yt_downloader.qt_quick import sidecar_recovery


def settle(app, window):
    for _ in range(3):
        app.processEvents()
        polish_scene(window.contentItem())
    QTest.qWait(100)


def click(window, item, button=Qt.LeftButton):
    point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
    assert 0 <= point.x() < window.width() and 0 <= point.y() < window.height()
    QTest.mouseClick(window, button, pos=point)


@pytest.mark.parametrize("surface,width", [("forge", 1100), ("deck", 820)])
def test_saved_partial_actual_click_recovers_artwork_without_media_retry(
    tmp_path, monkeypatch, surface, width
):
    # Optional prior-source control is an isolated complete QML copy. It never
    # edits the canonical source or relabels a previous test result.
    if os.environ.get("VODFORGE_TEST_PRIOR_RECOVERY_QML") == "1":
        original = Path(qt_main.__file__)
        copied = tmp_path / "prior-qml"
        shutil.copytree(
            original.parent,
            copied,
            ignore=shutil.ignore_patterns("*.py", "__pycache__"),
        )
        for name in ("Main.qml", "RunDeck.qml"):
            (copied / name).write_bytes(
                subprocess.check_output(
                    ["git", "show", "c7fbc14:yt_downloader/qt_quick/" + name]
                )
            )
        monkeypatch.setattr(qt_main, "__file__", str(copied / "main.py"))
    media_root = tmp_path / "saved"
    media_root.mkdir()
    job, info, media = fixture(media_root)
    original_media = media.read_bytes()
    app, bridge, engine, window = _launch(tmp_path / "home", monkeypatch, [info])
    entered, release = Event(), Event()
    calls = []

    def bounded_fetch(*args, **kwargs):
        calls.append(1)
        entered.set()
        assert release.wait(3), "Test must release its one controlled fetch"
        return image_bytes()

    monkeypatch.setattr(
        sidecar_recovery.service, "download_bounded_url_bytes", bounded_fetch
    )
    monkeypatch.setattr(
        bridge._runtime,
        "retry_terminal",
        lambda *a, **k: pytest.fail("Must not retry media"),
    )
    monkeypatch.setattr(
        bridge._runtime,
        "prepare_job",
        lambda *a, **k: pytest.fail("Must not analyze source"),
    )
    monkeypatch.setattr(bridge._artwork, "request", lambda *a, **k: "")
    bridge._runtime.recovery.terminal_attempt(job, "Partial", job.terminal_message)
    bridge._runtime.recovered = bridge._runtime.recovery.store.load_terminal_jobs()
    bridge.selectRunRecord("terminal:" + job.run_id)
    bridge.historyChanged.emit()
    bridge.runDeckChanged.emit()
    bridge._timer.stop()
    try:
        window.resize(width, 740)
        settle(app, window)
        if surface == "forge":
            retry = window.findChild(QObject, "forgeFailedRetry")
        else:
            deck = window.findChild(QObject, "forgeRunDeck")
            card = visual_item(deck, "runCardContextArea")
            click(window, card, Qt.RightButton)
            settle(app, window)
            assert window.findChild(QObject, "runActionsPopup").property("visible")
            retry = visual_item(window.contentItem(), "runResumeOrRetry")
        assert retry.isVisible() and retry.isEnabled()
        click(window, retry)
        settle(app, window)
        assert entered.wait(0.3), "First click must dispatch artwork repair directly"
        assert not window.findChild(QObject, "forgeRetryPopup").property("visible")
        assert retry.property("label") == "Retry artwork"
        assert bridge._runtime.active_job is None and bridge._runtime.queued == []
        if surface == "forge":
            assert not retry.isEnabled()
            click(window, retry)
            settle(app, window)
            assert calls == [1]
        release.set()
        deadline = time.monotonic() + 3
        while bridge._sidecar_target is not None and time.monotonic() < deadline:
            bridge._pump()
            app.processEvents()
            time.sleep(0.005)
        assert bridge._runtime.recovered == []
        assert (media_root / "thumbnail.jpeg").is_file()
        assert media.read_bytes() == original_media
        assert calls == [1]
        assert [r["kind"] for r in bridge.runDeck["records"]] == ["completed"]
    finally:
        release.set()
        _close(bridge, engine, window)
