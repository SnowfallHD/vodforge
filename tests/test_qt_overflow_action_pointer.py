"""Settled offscreen pointer coverage, separate from native acceptance evidence."""

from dataclasses import replace

from PySide6.QtCore import QObject, QPoint, QPointF, Qt
from PySide6.QtTest import QTest

from tests.test_qt_all_runs_hover_seam import move, run_scene  # noqa: F401
from tests.test_qt_scene_port import make_job, saved


def _items(item):
    yield item
    for child in item.childItems():
        yield from _items(child)


def _record(item):
    value = item.property("record")
    return value.toVariant() if hasattr(value, "toVariant") else value


def _center(item):
    return item.mapToScene(QPointF(item.width() / 2, item.height() / 2))


def _click(window, point, button):
    QTest.mouseClick(
        window, button, Qt.NoModifier, QPoint(round(point.x()), round(point.y()))
    )


def test_overflow_fifth_owner_right_click_retry_admits_exact_run(
    run_scene,
    tmp_path,  # noqa: F811 - imported pytest fixture
):
    app, bridge, window, trigger, overflow = run_scene
    # Freeze background refresh for a deterministic populated ordering; the real
    # Bridge retry slot and durable admission path remain in use.
    bridge._timer.stop()
    runtime = bridge._runtime
    active = runtime.active_job
    active.url = "https://www.youtube.com/watch?v=active-other"
    active.urls = [active.url]
    runtime.recovery.begin(active, [])
    failed = make_job(tmp_path)
    failed.preview_info = {"title": "Fictional retry forge"}
    failed.terminal_status = "Failed"
    after = [
        replace(failed, run_id=f"after-{i}", preview_info={"title": f"After {i}"})
        for i in range(10)
    ]
    for job in [failed, *after]:
        runtime.recovery.terminal_attempt(job, "Failed", "Fixture failure")
    runtime.recovered = [failed, *after]
    runtime.history = [saved(tmp_path, f"Saved {i}", "MP4") for i in range(3)]
    bridge.historyChanged.emit()
    bridge.activityChanged.emit()
    app.processEvents()
    assert len(bridge.runDeck["records"]) == 15
    assert bridge.runDeck["records"][4]["runId"] == failed.run_id

    move(window, _center(trigger))
    assert overflow.property("visible")
    card = next(
        item
        for item in _items(overflow.property("contentItem"))
        if isinstance(_record(item), dict)
        and _record(item).get("runId") == failed.run_id
    )
    listing = window.findChild(QObject, "allRunsScrollView")
    listing.setProperty("contentY", max(0, card.y() - 150))
    QTest.qWait(200)
    # Select the exact owner with a physical right click, not a direct signal.
    _click(window, _center(card), Qt.RightButton)
    app.processEvents()
    actions = window.findChild(QObject, "runActionsPopup")
    assert actions.property("visible")
    QTest.qWait(200)
    retry = next(
        item
        for item in _items(actions.property("contentItem"))
        if item.property("label") == "Retry run"
    )
    activations = []
    retry.activated.connect(lambda: activations.append(True))
    move(window, _center(retry))
    # Hover can reposition the popup: only its fresh settled center is a valid
    # click target. A transient snapshot's stale coordinates prove no failure.
    app.processEvents()
    _click(window, _center(retry), Qt.LeftButton)
    app.processEvents()

    assert activations == [True]
    assert not actions.property("visible")
    assert runtime.active_job is active
    assert len(runtime.queued) == 1
    successor = runtime.queued[0]
    assert successor.run_id != failed.run_id
    assert successor.origin_run_id == failed.run_id
    assert successor.retry_of_run_id == (failed.execution_run_id or failed.run_id)
    durable = runtime.recovery.store.load_queued_jobs()
    assert [job.run_id for job in durable] == [successor.run_id]
    assert durable[0].origin_run_id == failed.run_id
    assert durable[0].retry_of_run_id == successor.retry_of_run_id
