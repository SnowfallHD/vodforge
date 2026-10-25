"""Rendered compact Forge action ownership and reachable layout regressions."""

import pytest
from PySide6.QtCore import QObject, QPointF
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch
from tests.test_qt_optional_sidecar_recovery import fixture
from tests.test_qt_scene_port import polish_scene, visual_item


def settle(app, window):
    for _ in range(4):
        app.processEvents()
        polish_scene(window.contentItem())
    QTest.qWait(100)


@pytest.mark.parametrize("size", [(820, 640), (820, 800), (1100, 640), (1100, 740)])
def test_completed_optional_actions_remain_reachable_across_breakpoints(
    tmp_path, monkeypatch, size
):
    root = tmp_path / "saved"
    root.mkdir()
    job, info, _ = fixture(root)
    app, bridge, engine, window = _launch(tmp_path / "home", monkeypatch, [info])
    bridge._timer.stop()
    bridge._runtime.recovery.terminal_attempt(job, "Partial", job.terminal_message)
    bridge._runtime.recovered = bridge._runtime.recovery.store.load_terminal_jobs()
    assert bridge.selectRunRecord(bridge.runDeck["records"][0]["selectionKey"])
    bridge.historyChanged.emit()
    bridge.runDeckChanged.emit()
    try:
        window.resize(*size)
        settle(app, window)
        primary = window.findChild(QObject, "forgeAdaptivePrimary")
        popup = window.findChild(QObject, "forgeSecondaryPopup")
        buttons = [
            window.findChild(QObject, name)
            for name in (
                "forgeCompletedPlay",
                "forgeCompletedShowInLibrary",
                "forgeCompletedShowInFolder",
                "forgeFailedRetry",
                "forgeFailedIssues",
                "forgeFailedRemove",
            )
        ]
        overflow = window.findChild(QObject, "forgeMoreActions").isVisible()
        for button in buttons[:2]:
            assert button.isVisible() and button.isEnabled(), button.objectName()
            assert button.property("activeFocusOnTab")
            point = button.mapToScene(QPointF(0, 0))
            assert point.x() >= 0 and point.x() + button.width() <= window.width()
            assert point.y() >= 0 and point.y() + button.height() <= window.height()
        assert window.grabWindow().save(
            f"/tmp/vodforge-compact-{size[0]}x{size[1]}.png"
        )
        if overflow:
            assert all(button.parentItem() is primary for button in buttons[:2])
            assert buttons[0].y() == buttons[1].y()
            window.findChild(QObject, "forgeMoreActions").activated.emit()
            settle(app, window)
            assert popup.property("visible")
        displayed = (
            buttons[:2]
            + [
                visual_item(window.contentItem(), button.objectName() + "Overflow")
                for button in buttons[2:]
            ]
            if overflow
            else buttons
        )
        for button in displayed:
            assert button.isVisible() and button.isEnabled(), button.objectName()
            assert button.property("activeFocusOnTab")
            point = button.mapToScene(QPointF(0, 0))
            assert point.x() >= 0 and point.x() + button.width() <= window.width()
            assert point.y() >= 0 and point.y() + button.height() <= window.height()
        popup.close()
        window.resize(1400, 900)
        settle(app, window)
        assert all(
            button.isVisible() and button.parentItem() is not primary
            for button in buttons
        )
        window.resize(*size)
        settle(app, window)
        assert all(button.isVisible() for button in buttons[:2])
        if overflow:
            window.findChild(QObject, "forgeMoreActions").activated.emit()
            settle(app, window)
            retry = visual_item(window.contentItem(), "forgeFailedRetryOverflow")
            retry.setProperty(
                "label", "Retry unavailable optional thumbnail and metadata files"
            )
            settle(app, window)
            assert retry.width() <= popup.property("width")
            assert retry.property("activeFocusOnTab")
            retry.forceActiveFocus()
            assert retry.hasActiveFocus()
    finally:
        _close(bridge, engine, window)


def test_compact_regular_completed_and_running_keep_applicable_actions(
    tmp_path, monkeypatch
):
    from tests.test_run_identity import make_job

    root = tmp_path / "saved"
    root.mkdir()
    _job, info, _media = fixture(root)
    app, bridge, engine, window = _launch(tmp_path / "home", monkeypatch, [info])
    bridge._timer.stop()
    try:
        window.resize(820, 640)
        settle(app, window)
        assert bridge.forgeSelection["kind"] == "completed"
        for name in ("forgeCompletedPlay", "forgeCompletedShowInLibrary"):
            assert window.findChild(QObject, name).isVisible()
        assert not window.findChild(QObject, "forgeFailedRetry").isVisible()
        active = make_job(root)
        bridge._runtime.active_job = active
        bridge._runtime.recovery.begin(active)
        bridge.runningChanged.emit()
        bridge.runDeckChanged.emit()
        assert bridge.selectRunRecord("active:" + active.run_id)
        settle(app, window)
        assert not window.findChild(QObject, "forgeMoreActions").isVisible()
        assert not window.findChild(QObject, "forgeCompletedPlay").isVisible()
        run_actions = window.findChild(QObject, "forgeRunActionsButton")
        assert run_actions.isVisible() and run_actions.isEnabled()
        point = run_actions.mapToScene(QPointF(0, 0))
        assert 0 <= point.x() < window.width()
        assert 0 <= point.y() < window.height()
    finally:
        bridge._runtime.active_job = None
        _close(bridge, engine, window)
