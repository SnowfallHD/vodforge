"""Action feedback cannot replace an executing run's canonical presentation."""

from dataclasses import replace

import pytest
from PySide6.QtCore import QObject
from PySide6.QtTest import QSignalSpy

from tests import test_qt_inspector_actions as inspector_actions
from tests.test_qt_runtime_event_ownership import DormantThread
from tests.test_run_identity import make_job
from yt_downloader.qt_quick import runtime as runtime_module

feedback_scene = inspector_actions.scene


def active_record(bridge):
    return next(row for row in bridge.runDeck["records"] if row["kind"] == "active")


def start_owned(bridge, job):
    bridge._runtime.recovery.begin(job, [])
    bridge._runtime._make_worker(job)
    return bridge._runtime._worker_app.events


@pytest.mark.parametrize("value", ["", "not a URL"])
def test_submit_validation_is_notice_and_keeps_active_run(
    feedback_scene, tmp_path, monkeypatch, value
):
    app, bridge, window = feedback_scene
    bridge._timer.stop()
    monkeypatch.setattr(runtime_module.threading, "Thread", DormantThread)
    sink = start_owned(bridge, make_job(tmp_path))
    sink.put(("status", "Transcoding video 3 of 27"))
    sink.put(("progress", 62))
    bridge._pump()
    spy = QSignalSpy(bridge.operationFeedback)
    assert not bridge.submit(value, "MP4")
    assert spy.count() == 1
    assert "URL" in spy.at(0)[0]
    app.processEvents()
    notice = window.findChild(QObject, "operationNotice")
    assert notice.property("visible")
    assert notice.property("message") == spy.at(0)[0]
    assert active_record(bridge)["status"] == "Transcoding video 3 of 27"
    assert active_record(bridge)["progress"] == 62
    selected = window.property("selectedForgeRun")
    assert selected["status"] == "Transcoding video 3 of 27"
    sink.put(("status", "Finalizing video 3 of 27"))
    bridge._pump()
    assert spy.count() == 1  # worker observations are not action notices
    assert active_record(bridge)["status"] == "Finalizing video 3 of 27"


def test_other_action_and_old_callbacks_do_not_poison_successor(
    feedback_scene, tmp_path, monkeypatch
):
    _app, bridge, _window = feedback_scene
    bridge._timer.stop()
    monkeypatch.setattr(runtime_module.threading, "Thread", DormantThread)
    old = make_job(tmp_path)
    old_sink = start_owned(bridge, old)
    successor = replace(old, preview_info={"title": "Successor"})
    sink = start_owned(bridge, successor)
    sink.put(("status", "Downloading successor"))
    sink.put(("progress", 18))
    bridge._pump()
    spy = QSignalSpy(bridge.operationFeedback)
    bridge.setOutputPath(str(tmp_path / "not-present"))
    assert spy.count() == 1
    old_sink.put(("status", "Old failure"))
    old_sink.put(("progress", 99))
    bridge._pump()
    assert active_record(bridge)["status"] == "Downloading successor"
    assert active_record(bridge)["progress"] == 18
