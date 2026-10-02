"""Composer feedback geometry and execution ownership."""

import pytest
from PySide6.QtCore import QObject, QPointF
from PySide6.QtTest import QSignalSpy

from tests import test_qt_inspector_actions as inspector_actions
from tests.test_qt_runtime_event_ownership import DormantThread
from tests.test_run_identity import make_job
from yt_downloader.qt_quick import runtime as runtime_module

feedback_scene = inspector_actions.scene


@pytest.mark.parametrize("width,height", [(720, 620), (1100, 740), (1440, 900)])
def test_notice_tracks_composer_bounds(feedback_scene, width, height):
    app, bridge, window = feedback_scene
    window.setWidth(width)
    window.setHeight(height)
    bridge.operationFeedback.emit(
        "Settings need attention before a download can start."
    )
    for _ in range(8):
        app.processEvents()
    notice = window.findChild(QObject, "operationNotice")
    composer = window.findChild(QObject, "forgeCommandRow")
    destination = window.findChild(QObject, "forgeDestinationField")
    origin = composer.mapToItem(window.contentItem(), QPointF(0, 0))
    bottom = destination.mapToItem(
        window.contentItem(), QPointF(0, destination.height())
    )
    expected_x = max(
        10,
        min(
            width - notice.property("width") - 10,
            origin.x() + (composer.width() - notice.property("width")) / 2,
        ),
    )
    assert notice.property("x") == pytest.approx(expected_x, abs=1)
    assert notice.property("y") >= bottom.y()
    assert notice.property("y") + notice.property("height") <= height - 18
    assert not notice.property("modal")


def test_admitted_run_preparing_is_not_notice(feedback_scene, tmp_path, monkeypatch):
    app, bridge, window = feedback_scene
    bridge._timer.stop()
    monkeypatch.setattr(runtime_module.threading, "Thread", DormantThread)
    job = make_job(tmp_path)
    spy = QSignalSpy(bridge.operationFeedback)
    assert bridge.submit(job.url, "MP4")
    app.processEvents()
    assert spy.count() == 0
    selected = window.property("selectedForgeRun")
    assert selected["kind"] == "active"
    assert "Preparing" in selected["status"]
    assert not window.findChild(QObject, "operationNotice").property("visible")
    bridge._settings_writable = False
    assert not bridge.submit(job.url, "MP4")
    assert spy.count() == 1
    assert "Settings" in spy.at(0)[0]
    assert window.property("selectedForgeRun")["status"] == selected["status"]
