"""Observer sensitivity tests and interrupted, separated-click journeys."""

import json

import pytest
from PySide6.QtCore import QObject, QPoint, Qt, QUrl
from PySide6.QtQml import QQmlComponent
from PySide6.QtTest import QTest

from tests.test_qt_click_reliability import center
from tests.test_qt_interaction_invariants import _close, _launch
from tests.test_qt_scene_port import saved
from yt_downloader.qt_quick.input_trace import InputTrace


def record_types(trace, kind):
    return [row for row in trace.snapshot()["records"] if row["kind"] == kind]


@pytest.fixture
def traced(tmp_path, monkeypatch):
    app, bridge, engine, window = _launch(
        tmp_path, monkeypatch, [saved(tmp_path, "PRIVATE TITLE sentinel", "MP4")]
    )
    bridge.select("Library")
    bridge.navigateLibrary("all")
    QTest.qWait(80)
    button = window.findChild(QObject, "librarySelectButton")
    trace = InputTrace(window)
    trace.watch_action(button, "library_select")
    trace.watch_popup(window.findChild(QObject, "libraryFilterPopup"), "library_filter")
    yield app, bridge, engine, window, button, trace
    trace.stop()
    _close(bridge, engine, window)


def click(window, button):
    # Default QTest delay separates timestamps beyond double-click interval.
    QTest.mouseClick(window, Qt.LeftButton, pos=center(button))
    QTest.qWait(20)


def test_trace_records_delivery_grab_focus_and_exact_action_without_contents(traced):
    app, _bridge, _engine, window, button, trace = traced
    button.forceActiveFocus()
    point = center(button)
    QTest.mousePress(window, Qt.LeftButton, pos=point)
    app.processEvents()
    held = record_types(trace, "settled")[-1]
    assert held["grabber"]["action_owner"] == "library_select"
    assert held["focus"]["action_owner"] == "library_select"
    assert held["geometric_candidates"][0]["action_owner"] == "library_select"
    QTest.mouseRelease(window, Qt.LeftButton, pos=point)
    app.processEvents()
    assert [row["event"] for row in record_types(trace, "window_delivery")] == [
        "press",
        "release",
    ]
    assert [row["action"] for row in record_types(trace, "action")] == [
        "library_select"
    ]
    assert record_types(trace, "settled")[-1]["grabber"] is None
    assert record_types(trace, "target_delivery"), trace.snapshot()
    payload = json.dumps(trace.snapshot())
    for forbidden in (
        "PRIVATE",
        "Fixture",
        "librarySelectButton",
        "/Users/",
        "http",
        "label",
        "text",
    ):
        assert forbidden not in payload


@pytest.mark.parametrize("missed_clicks", [1, 3])
def test_trace_detects_persistent_swallowed_separated_clicks_and_recovery(
    traced, missed_clicks
):
    _app, _bridge, engine, window, button, trace = traced
    component = QQmlComponent(engine)
    component.setData(
        b"""import QtQuick
        MouseArea { objectName: "PRIVATE URL https://secret.invalid/media";
                    anchors.fill: parent; z: 10000; hoverEnabled: true }
    """,
        QUrl(),
    )
    blocker = component.create()
    assert blocker is not None, component.errors()
    blocker.setParentItem(window.contentItem())
    try:
        for _ in range(missed_clicks):
            click(window, button)
        assert button.property("label") == "Select"
        assert len(record_types(trace, "window_delivery")) == 2 * missed_clicks
        assert record_types(trace, "action") == []
        assert record_types(trace, "target_delivery") == []
        press = [
            row
            for row in record_types(trace, "window_delivery")
            if row["event"] == "press"
        ]
        assert len(press) == missed_clicks
        assert all(
            row["geometric_candidates"][0]["action_owner"] is None for row in press
        )
        assert all(
            any(
                hit["action_owner"] == "library_select"
                for hit in row["geometric_candidates"]
            )
            for row in press
        )
        assert "PRIVATE" not in json.dumps(trace.snapshot())
        blocker.setVisible(False)
        click(window, button)
        assert button.property("label") == "Done"
        assert len(record_types(trace, "action")) == 1
    finally:
        blocker.setParentItem(None)
        blocker.deleteLater()


@pytest.mark.parametrize("interruption", ["navigation", "popup", "disable", "ungrab"])
def test_first_separated_click_after_interrupted_selection_press(traced, interruption):
    app, bridge, _engine, window, button, trace = traced
    point = center(button)
    QTest.mousePress(window, Qt.LeftButton, pos=point)
    app.processEvents()
    if interruption == "navigation":
        bridge.select("Watch")
        QTest.qWait(30)
    elif interruption == "popup":
        popup = window.findChild(QObject, "libraryFilterPopup")
        popup.open()
    elif interruption == "disable":
        button.setEnabled(False)
    else:
        window.mouseGrabberItem().ungrabMouse()
    QTest.mouseRelease(window, Qt.LeftButton, pos=QPoint(2, 2))
    QTest.qWait(30)
    if interruption == "navigation":
        bridge.select("Library")
    elif interruption == "popup":
        popup.close()
    elif interruption == "disable":
        button.setEnabled(True)
    QTest.qWait(60)
    assert record_types(trace, "action") == []
    for expected in ("Done", "Select", "Done"):
        click(window, button)
        assert button.property("label") == expected
    assert len(record_types(trace, "action")) == 3


def test_trace_cap_disconnects_without_changing_later_activation(traced):
    _app, _bridge, _engine, window, button, original = traced
    original.stop()
    trace = InputTrace(window, max_records=8)
    trace.watch_action(button, "library_select")
    for _ in range(6):
        click(window, button)
    assert trace.snapshot()["status"] == "record_limit"
    assert len(trace.snapshot()["records"]) == 8
    assert button.property("label") == "Select"
    with pytest.raises(ValueError):
        trace.watch_action(button, "PRIVATE TITLE")


def test_observer_does_not_reintroduce_double_click_suppression(traced):
    _app, _bridge, _engine, window, button, trace = traced
    QTest.mouseDClick(window, Qt.LeftButton, pos=center(button))
    QTest.qWait(30)
    assert button.property("label") == "Select"
    assert len(record_types(trace, "action")) == 2
    assert any(
        row["event"] == "double_press" for row in record_types(trace, "window_delivery")
    )


def test_deadline_disconnects_and_preserves_next_click(traced):
    _app, _bridge, _engine, window, button, original = traced
    original.stop()
    trace = InputTrace(window, seconds=0.02)
    trace.watch_action(button, "library_select")
    QTest.qWait(40)
    assert trace.snapshot()["status"] == "deadline"
    before = trace.snapshot()
    click(window, button)
    assert button.property("label") == "Done"
    assert trace.snapshot() == before


def test_destroyed_dynamic_target_is_retired_without_losing_next_action(traced):
    from PySide6.QtCore import QCoreApplication, QEvent

    _app, _bridge, engine, window, button, trace = traced
    component = QQmlComponent(engine)
    # Keep the dynamic QML component alive through fixture/engine teardown.
    component.setParent(engine)
    component.setData(
        b"""import QtQuick
        Item { x: 600; y: 350; width: 40; height: 40; z: 10000; signal activated()
            MouseArea { anchors.fill: parent; onClicked: parent.activated() }
        }""",
        QUrl(),
    )
    target = component.create()
    target.setParentItem(window.contentItem())
    trace.watch_action(target, "fixture_action")
    click(window, target)
    assert record_types(trace, "action")[-1]["action"] == "fixture_action"
    target.setParentItem(None)
    target.deleteLater()
    QCoreApplication.sendPostedEvents(target, QEvent.DeferredDelete)
    click(window, button)
    assert button.property("label") == "Done"
    assert record_types(trace, "action")[-1]["action"] == "library_select"
    assert trace.snapshot()["records"][-1]["targets"]["fixture_action"] == {
        "destroyed": True
    }
