"""Production wrapped callbacks retain control scope only after owner admission."""

from dataclasses import replace

import pytest

from tests.test_qt_scene_port import qt_app
from tests.test_run_identity import make_job
from yt_downloader.qt_quick import main as qt_main
from yt_downloader.qt_quick import runtime as runtime_module


class DormantThread:
    def __init__(self, **kwargs):
        pass

    def start(self):
        pass

    def is_alive(self):
        return False


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    monkeypatch.setattr(runtime_module.threading, "Thread", DormantThread)
    owner = qt_main.Bridge(None)
    try:
        yield owner
    finally:
        owner.close()


def launch(bridge, job):
    bridge._runtime.recovery.begin(job, [])
    bridge._runtime._make_worker(job)
    return bridge._runtime._worker_app.events


def labels(bridge):
    return [row["label"] for row in bridge.runControls]


def test_actual_worker_sink_and_bridge_pump_keep_batch_child_playlist_scope(
    bridge, tmp_path
):
    parent = replace(make_job(tmp_path), batch_mode=True, single_video_only=False)
    sink = launch(bridge, parent)
    playlist = replace(parent, url="https://youtube.com/playlist?list=PLfixture")
    sink.put(("job_metadata", {"job": playlist, "info": {"playlist_id": "PLfixture"}}))
    bridge._pump()
    assert labels(bridge) == ["Skip this video", "Skip playlist", "Stop batch"]
    assert bridge._run_controls.source is playlist
    sink.put(("job_log", {"job": parent, "line": "Starting next source"}))
    bridge._pump()
    assert labels(bridge) == ["Skip this link", "Stop batch"]
    single = replace(
        parent, url="https://youtube.com/watch?v=next", single_video_only=True
    )
    sink.put(("job_metadata", {"job": single, "info": {"playlist_id": "PLfixture"}}))
    bridge._pump()
    assert bridge._run_controls.source is single
    assert labels(bridge) == ["Skip this link", "Stop batch"]


def test_current_single_execution_metadata_can_establish_playlist_scope(
    bridge, tmp_path
):
    job = replace(make_job(tmp_path), single_video_only=False)
    sink = launch(bridge, job)
    assert labels(bridge) == ["Cancel download"]
    sink.put(("job_metadata", {"job": job, "info": {"entries": []}}))
    bridge._pump()
    assert labels(bridge) == ["Skip this video", "Stop playlist"]


def test_stale_same_id_worker_cannot_restore_or_retire_current_control_scope(
    bridge, tmp_path
):
    old = replace(make_job(tmp_path), batch_mode=True, single_video_only=False)
    old_sink = launch(bridge, old)
    current = replace(old)
    sink = launch(bridge, current)
    assert current is not old and current.run_id == old.run_id
    playlist = replace(current, url="https://youtube.com/playlist?list=PLcurrent")
    sink.put(("job_metadata", {"job": playlist, "info": {"playlist_id": "PLcurrent"}}))
    bridge._pump()
    assert labels(bridge) == ["Skip this video", "Skip playlist", "Stop batch"]
    old_sink.put(("job_log", {"job": current, "line": "Late stale parent boundary"}))
    old_sink.put(
        ("job_metadata", {"job": replace(old, single_video_only=True), "info": {}})
    )
    bridge._pump()
    assert bridge._run_controls.source is playlist
    assert bridge._run_controls.info == {"playlist_id": "PLcurrent"}
    assert labels(bridge) == ["Skip this video", "Skip playlist", "Stop batch"]
    sink.put(("job_log", {"job": current, "line": "Admitted next source"}))
    bridge._pump()
    assert labels(bridge) == ["Skip this link", "Stop batch"]
    old_sink.put(("job_metadata", {"job": playlist, "info": {"playlist_id": "PLold"}}))
    bridge._pump()
    assert labels(bridge) == ["Skip this link", "Stop batch"]
    assert bridge._run_control_events.take_context_events() == []


def test_queue_does_not_unwrap_unvalidated_worker_envelopes(bridge, tmp_path):
    job = replace(make_job(tmp_path), batch_mode=True)
    sink = launch(bridge, job)
    payload = {"job": job, "info": {"playlist_id": "PLfixture"}}
    event = ("job_metadata", payload)
    sink.put(event)
    envelope = bridge._run_control_events.get_nowait()
    assert envelope[0] == "worker_event"
    assert bridge._run_control_events.take_context_events() == []
    bridge._run_control_events.put(envelope)
    assert bridge._runtime.poll() == [event]
    retained = bridge._run_control_events.take_context_events()
    assert retained == [event]
    assert retained[0][1] is payload
    assert bridge._run_control_events.take_context_events() == []
