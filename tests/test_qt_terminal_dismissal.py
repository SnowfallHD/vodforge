"""Dismiss recovery presentation while retaining media and durable history."""

from dataclasses import replace

import pytest

from tests.test_run_identity import make_job
from yt_downloader.qt_quick.runtime import DownloadRuntime
from yt_downloader.run_state import RunStateError


def runtime_with_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    runtime = DownloadRuntime()
    failed = make_job(tmp_path)
    runtime.recovery.terminal_attempt(failed, "Failed", "Original failure")
    runtime.recovered = runtime.recovery.store.load_terminal_jobs()
    return runtime, failed


def test_dismiss_terminal_preserves_active_queue_media_history_and_restart(
    tmp_path, monkeypatch
):
    runtime, failed = runtime_with_failure(tmp_path, monkeypatch)
    media = tmp_path / "saved.mp4"
    media.write_bytes(b"saved fixture")
    runtime.history_path.write_text('[{"id":"saved"}]')
    history = runtime.history_path.read_bytes()
    active = replace(make_job(tmp_path), run_id="active")
    queued = replace(make_job(tmp_path), run_id="queued")
    runtime.recovery.begin(active, [queued])
    runtime.active_job = active
    runtime.queued = [queued]
    assert not runtime.dismiss_terminal(active.run_id)
    assert not runtime.dismiss_terminal(queued.run_id)
    assert not runtime.dismiss_terminal("stale")
    assert runtime.dismiss_terminal(failed.run_id)
    assert runtime.active_job is active
    assert runtime.queued == [queued]
    assert runtime.recovery.store.load_terminal_jobs() == []
    assert runtime.recovery.store.load()["job"]["run_id"] == "active"
    assert runtime.recovery.store.load_queued_jobs()[0].run_id == "queued"
    assert media.read_bytes() == b"saved fixture"
    assert runtime.history_path.read_bytes() == history
    assert not runtime.dismiss_terminal(failed.run_id)
    runtime.close()


def test_dismiss_persistence_failure_retains_authoritative_terminal(
    tmp_path, monkeypatch
):
    runtime, failed = runtime_with_failure(tmp_path, monkeypatch)
    before = runtime.recovery.store.path.read_bytes()

    def denied():
        raise RunStateError("fixture persistence denied")

    monkeypatch.setattr(runtime.recovery.store, "_unlink_unlocked", denied)
    with pytest.raises(RunStateError):
        runtime.dismiss_terminal(failed.run_id)
    assert runtime.recovery.store.path.read_bytes() == before
    assert runtime.recovered[0].run_id == failed.run_id
    runtime.close()
