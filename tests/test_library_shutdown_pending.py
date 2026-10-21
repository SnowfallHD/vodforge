"""Ordinary close stays visible while an owned filesystem read cannot stop yet."""

import os
import threading
import time

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch
from yt_downloader.qt_quick.library_files import QtLibraryFiles


@pytest.mark.parametrize("result_event", [True, False])
@pytest.mark.parametrize("quit_route", ["window", "application"])
def test_close_waits_visibly_for_real_blocked_read_then_finishes(
    tmp_path, monkeypatch, result_event, quit_route
):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    read_fd, write_fd = os.pipe()
    entered = threading.Event()

    def work():
        entered.set()
        os.read(read_fd, 1)
        if result_event:
            bridge._files.events.put(("error", "Cancelled at the safe file boundary"))

    try:
        assert bridge._files._start(work, "fictional-blocked-library-read")
        assert entered.wait(2)
        bridge._pump()  # Observe admission even if a worker later exits without a result.
        start = time.monotonic()
        if quit_route == "application":
            bridge._window = window  # Same binding as the real main() owner.
            QCoreApplication.sendEvent(app, QEvent(QEvent.Type.Quit))
        else:
            window.close()
        app.processEvents()
        assert time.monotonic() - start < 1
        assert window.isVisible(), (
            "Owned blocked file work must not silently outlive the window"
        )
        assert window.property("closePending")
        assert bridge._files.cancelled.is_set() and bridge.libraryFileRunning
        assert not bridge._closed and "Waiting" in bridge.status
        assert bridge._files.worker.daemon is False
        os.write(write_fd, b"x")
        bridge._files.worker.join(2)
        assert not bridge._files.busy
        for _ in range(10):
            bridge._pump()
            app.processEvents()
            QTest.qWait(10)
        assert not window.isVisible()
    finally:
        if bridge._files.busy:
            os.write(write_fd, b"x")
            bridge._files.worker.join(2)
        os.close(read_fd)
        os.close(write_fd)
        _close(bridge, engine, window)


def test_bounded_close_reports_pending_without_disowning_worker(tmp_path):
    from types import SimpleNamespace

    joins = []
    worker = SimpleNamespace(
        is_alive=lambda: True, join=lambda timeout: joins.append(timeout), daemon=False
    )
    owner = QtLibraryFiles(tmp_path / "history.json")
    owner.worker = worker
    assert owner.close() is False
    assert owner.worker is worker and worker.daemon is False
    assert owner.cancelled.is_set() and joins == [10]
    assert "Waiting" in owner.status
