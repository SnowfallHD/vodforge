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


def test_notice_morph_retains_composer_geometry_and_retracts(feedback_scene):
    from PySide6.QtTest import QTest

    _app, bridge, window = feedback_scene
    QTest.qWait(100)
    composer = window.findChild(QObject, "forgeCommandRow")
    original = (composer.x(), composer.y(), composer.width(), composer.height())
    bridge.operationFeedback.emit("Choose an output folder")
    notice = window.findChild(QObject, "operationNotice")
    QTest.qWait(100)
    assert 0 < notice.property("reveal") < 1
    QTest.qWait(350)
    assert notice.property("reveal") == pytest.approx(1)
    assert notice.width() < composer.width()
    assert original == (composer.x(), composer.y(), composer.width(), composer.height())
    notice.setProperty("expanded", False)
    QTest.qWait(100)
    assert 0 < notice.property("reveal") < 1
    QTest.qWait(350)
    assert not notice.isVisible()
    assert original == (composer.x(), composer.y(), composer.width(), composer.height())


def test_notice_reduced_motion_and_long_text_clamp(feedback_scene):
    app, bridge, window = feedback_scene
    notice = window.findChild(QObject, "operationNotice")
    notice.setProperty("reducedMotion", True)
    bridge.operationFeedback.emit("Long settings notice " * 80)
    app.processEvents()
    assert notice.property("reveal") == 1
    assert notice.width() <= 440
    assert notice.height() <= 116
    notice.setProperty("expanded", False)
    app.processEvents()
    assert notice.property("reveal") == 0


@pytest.mark.parametrize("preference", [False, True])
def test_system_reduced_motion_reads_mac_preference(monkeypatch, preference):
    from types import SimpleNamespace

    from yt_downloader.qt_quick import main

    workspace = SimpleNamespace(
        accessibilityDisplayShouldReduceMotion=lambda: preference
    )
    appkit = SimpleNamespace(
        NSWorkspace=SimpleNamespace(sharedWorkspace=lambda: workspace)
    )
    monkeypatch.setattr(main.sys, "platform", "darwin")
    monkeypatch.setattr(main.importlib, "import_module", lambda _name: appkit)
    assert main._system_reduced_motion() is preference


def test_system_reduced_motion_unavailable_falls_back(monkeypatch):
    from yt_downloader.qt_quick import main

    def unavailable(_name):
        raise ImportError("not installed")

    monkeypatch.setattr(main.sys, "platform", "darwin")
    monkeypatch.setattr(main.importlib, "import_module", unavailable)
    assert not main._system_reduced_motion()
    monkeypatch.setattr(main.sys, "platform", "win32")
    assert not main._system_reduced_motion()
