from __future__ import annotations

import threading
import time

import pytest

from yt_downloader.archive_work import ArchiveWorkOwner


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "Worker did not reach expected state"
        time.sleep(0.002)


@pytest.mark.parametrize("retire", ["cancel", "close"])
def test_blocked_filesystem_lane_is_bounded_and_late_result_is_retired(retire):
    owner = ArchiveWorkOwner()
    entered, release = threading.Event(), threading.Event()
    effects = []

    def blocked(cancelled):
        entered.set()
        release.wait(2)
        if not cancelled.is_set():
            effects.append("external effect")
        return "private late result"

    try:
        assert owner.submit("availability", blocked) is not None
        assert entered.wait(2)
        thread = owner._thread
        getattr(owner, retire)()
        started = time.monotonic()
        for _ in range(100):
            assert owner.submit("replacement", lambda _: None) is None
        assert time.monotonic() - started < 0.5
        assert owner._thread is thread and thread.is_alive()
        release.set()
        wait_until(lambda: not owner._busy.is_set())
        assert owner.poll() is None
        assert effects == []
        if retire == "cancel":
            assert owner.submit("replacement", lambda _: "current") is not None
            result = []
            wait_until(
                lambda: (
                    bool(result.append(value) or True)
                    if (value := owner.poll())
                    else False
                )
            )
            assert result[0].value == "current"
    finally:
        release.set()
        owner.close()
        owner._thread.join(2)
        assert not owner._thread.is_alive()


def test_worker_failure_uses_closed_error_category_and_next_work_can_succeed():
    owner = ArchiveWorkOwner()

    def fail(_cancelled):
        raise PermissionError("/private/NAS/title?secret=sentinel")

    try:
        owner.submit("availability", fail)
        results = []
        wait_until(
            lambda: (
                bool(results.append(value) or True)
                if (value := owner.poll())
                else False
            )
        )
        assert results[0].error == "PermissionError"
        assert "private" not in repr(results)
        assert owner.submit("next", lambda _: 7) is not None
        wait_until(
            lambda: (
                bool(results.append(value) or True)
                if (value := owner.poll())
                else False
            )
        )
        assert results[1].value == 7
        assert results[1].generation > results[0].generation
    finally:
        owner.close()
        owner._thread.join(2)
