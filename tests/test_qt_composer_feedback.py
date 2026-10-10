"""Composer feedback geometry and execution ownership."""

import pytest
from PySide6.QtCore import QObject, QPointF, QUrl
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
    notice_origin = notice.mapToItem(window.contentItem(), QPointF(0, 0))
    assert notice_origin.x() == pytest.approx(expected_x, abs=1)
    assert notice_origin.y() >= bottom.y()
    assert notice_origin.y() + notice.property("height") <= height - 18
    assert not notice.property("modal")


@pytest.mark.parametrize("batch", [False, True])
def test_admitted_run_preparing_is_not_notice(
    feedback_scene, tmp_path, monkeypatch, batch
):
    app, bridge, window = feedback_scene
    bridge._timer.stop()
    monkeypatch.setattr(runtime_module.threading, "Thread", DormantThread)
    job = make_job(tmp_path)
    if batch:
        source_list = tmp_path / "sources.txt"
        source_list.write_text(job.url + "\nhttps://example.com/two\n")
        bridge.loadBatchUrl(QUrl.fromLocalFile(str(source_list)))
    spy = QSignalSpy(bridge.operationFeedback)
    assert bridge.submit(job.url, "MP4")
    app.processEvents()
    assert spy.count() == 0
    from PySide6.QtTest import QTest

    QTest.qWait(300)  # The prior list-loaded notice retracts through its animation.
    selected = window.property("selectedForgeRun")
    assert selected["kind"] == "active"
    assert "Preparing" in selected["status"]
    assert not window.findChild(QObject, "operationNotice").property("visible")
    bridge._settings_writable = False
    assert not bridge.submit(job.url, "MP4")
    assert spy.count() == 1
    assert "Settings" in spy.at(0)[0]
    assert window.property("selectedForgeRun")["status"] == selected["status"]


def test_notice_retains_page_geometry_and_retracts(feedback_scene):
    from PySide6.QtCore import QElapsedTimer
    from PySide6.QtTest import QTest

    def wait_for_animation(predicate):
        deadline = QElapsedTimer()
        deadline.start()
        while not predicate() and deadline.elapsed() < 2000:
            QTest.qWait(10)
        assert predicate()

    _app, bridge, window = feedback_scene
    QTest.qWait(100)
    composer = window.findChild(QObject, "forgeCommandRow")
    original = (composer.x(), composer.y(), composer.width(), composer.height())
    hero = window.findChild(QObject, "forgeHeroArtwork")
    hero_origin = hero.mapToItem(window.contentItem(), QPointF(0, 0))
    notice = window.findChild(QObject, "operationNotice")
    # Exercise animation independently of the runner's accessibility preference.
    # Observe actual frames: a fixed sleep can miss the intermediate state when
    # the event loop returns late on a busy hosted builder.
    notice.setProperty("reducedMotion", False)
    frames = []
    notice.revealChanged.connect(lambda: frames.append(notice.property("reveal")))
    bridge.operationFeedback.emit("Choose an output folder")
    wait_for_animation(lambda: notice.property("reveal") == 1)
    assert any(0 < value < 1 for value in frames)
    assert notice.property("reveal") == pytest.approx(1)
    assert notice.width() < composer.width()
    assert original == (composer.x(), composer.y(), composer.width(), composer.height())
    assert hero.mapToItem(window.contentItem(), QPointF(0, 0)) == hero_origin
    frames.clear()
    notice.setProperty("expanded", False)
    wait_for_animation(lambda: not notice.isVisible())
    assert any(0 < value < 1 for value in frames)
    assert not notice.isVisible()
    assert original == (composer.x(), composer.y(), composer.width(), composer.height())
    assert hero.mapToItem(window.contentItem(), QPointF(0, 0)) == hero_origin


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


@pytest.mark.parametrize("width,height", [(720, 560), (820, 560), (1100, 800)])
def test_long_notice_floats_without_moving_page(feedback_scene, width, height):
    from PySide6.QtCore import QElapsedTimer
    from PySide6.QtTest import QTest

    _app, bridge, window = feedback_scene
    window.setWidth(width)
    window.setHeight(height)
    QTest.qWait(100)
    composer = window.findChild(QObject, "forgeCommandRow")
    before = (composer.x(), composer.y(), composer.width(), composer.height())
    hero = window.findChild(QObject, "forgeHeroArtwork")
    original_hero_y = hero.mapToItem(window.contentItem(), QPointF(0, 0)).y()
    notice = window.findChild(QObject, "operationNotice")
    notice.setProperty("reducedMotion", True)
    bridge.operationFeedback.emit("Settings need review before continuing. " * 20)
    QTest.qWait(100)
    hero_y = hero.mapToItem(window.contentItem(), QPointF(0, 0)).y()
    assert hero_y == pytest.approx(original_hero_y)
    notice_y = notice.mapToItem(window.contentItem(), QPointF(0, 0)).y()
    assert before == (composer.x(), composer.y(), composer.width(), composer.height())
    assert notice_y + notice.height() <= height - 18
    notice.setProperty("expanded", False)
    # Reveal and the containing Qt Quick layout settle on separate event-loop
    # turns. Wait for the measured result rather than sampling after 100 ms.
    deadline = QElapsedTimer()
    deadline.start()
    while (
        abs(hero.mapToItem(window.contentItem(), QPointF(0, 0)).y() - original_hero_y)
        > 1
        and deadline.elapsed() < 2000
    ):
        QTest.qWait(10)
    assert notice.property("reveal") == 0
    assert hero.mapToItem(window.contentItem(), QPointF(0, 0)).y() == pytest.approx(
        original_hero_y, abs=1
    )
    assert before == (composer.x(), composer.y(), composer.width(), composer.height())


def test_compact_notice_overflow_reaches_deck_and_tracks_scroll(feedback_scene):
    from PySide6.QtTest import QTest

    _app, bridge, window = feedback_scene
    window.resize(820, 560)
    QTest.qWait(100)
    viewport = window.findChild(QObject, "forgeViewport")
    flickable = viewport.property("contentItem")
    notice = window.findChild(QObject, "operationNotice")
    notice.setProperty("reducedMotion", True)
    bridge.operationFeedback.emit("Settings need review before continuing. " * 20)
    QTest.qWait(100)
    assert flickable.property("contentY") == 0
    assert flickable.property("contentHeight") > viewport.height()
    before = notice.mapToItem(window.contentItem(), QPointF(0, 0)).y()
    bottom = flickable.property("contentHeight") - flickable.property("height")
    flickable.setProperty("contentY", bottom)
    QTest.qWait(100)
    after = notice.mapToItem(window.contentItem(), QPointF(0, 0)).y()
    assert after == pytest.approx(before - bottom, abs=1)
    deck = window.findChild(QObject, "forgeRunDeck")
    deck_bottom = deck.mapToItem(window.contentItem(), QPointF(0, deck.height())).y()
    viewport_bottom = viewport.mapToItem(
        window.contentItem(), QPointF(0, viewport.height())
    ).y()
    assert deck_bottom <= viewport_bottom + 1


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("terminal", ["stopped", "partial", "error"])
def test_window_close_pauses_active_download_and_retires_after_worker(
    feedback_scene, tmp_path, monkeypatch, batch, terminal
):
    from dataclasses import replace

    from PySide6.QtTest import QTest

    app, bridge, window = feedback_scene
    bridge._timer.stop()
    monkeypatch.setattr(runtime_module.threading, "Thread", DormantThread)
    job = make_job(tmp_path)
    job.batch_mode = batch
    if batch:
        job.urls = [job.url, "https://example.com/second"]
        job.completed_batch_items = 1
    bridge._runtime.start_job(job)
    queued = replace(
        job,
        run_id="queued-at-close",
        url="https://example.com/queued",
        urls=["https://example.com/queued"],
        activity_lines=[],
    )
    bridge._runtime.start_job(queued)
    sink = bridge._runtime._worker_app.events
    window.close()
    app.processEvents()
    assert bridge._runtime._closing
    assert window.isVisible(), "Wait for the active worker before retiring the window"
    sink.put((terminal, "Interrupted while closing"))
    bridge._pump()
    QTest.qWait(50)
    assert not window.isVisible()
    assert bridge._runtime.active_job is None
    assert bridge._runtime.queued == [queued]
    paused = next(
        item for item in bridge._runtime.recovered if item.run_id == job.run_id
    )
    assert paused.terminal_status == "Paused"
    assert paused.completed_batch_items == job.completed_batch_items
