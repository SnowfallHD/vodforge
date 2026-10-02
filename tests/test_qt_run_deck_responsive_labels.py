"""Offscreen layout regression; native small-window acceptance remains separate."""

import pytest
from PySide6.QtCore import QObject
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from tests.test_qt_all_runs_hover_seam import run_scene  # noqa: F401
from tests.test_qt_scene_port import make_job


def text_items(item):
    for child in item.childItems():
        if child.property("text") is not None:
            yield child
        yield from text_items(child)


@pytest.mark.parametrize("width", [280, 320, 400, 560, 800])
def test_deck_labels_do_not_paint_into_adjacent_controls(run_scene, width):  # noqa: F811
    app, bridge, window, _button, _popup = run_scene
    queued = make_job(bridge._runtime.active_job.output_dir)
    terminal = make_job(bridge._runtime.active_job.output_dir)
    terminal.terminal_status = "Failed"
    bridge._runtime.queued = [queued]
    bridge._runtime.recovered = [terminal]
    bridge.runDeckChanged.emit()
    deck = window.findChild(QObject, "forgeRunDeck")
    host = QQuickItem(window.contentItem())
    host.setWidth(width)
    host.setHeight(139)
    deck.setParentItem(host)
    deck.setWidth(width)
    deck.setHeight(139)
    app.processEvents()
    QTest.qWait(50)
    texts = list(text_items(deck))
    summary = next(
        text for text in texts if text.property("text") == deck.property("workSummary")
    )
    policy = next(
        text for text in texts if text.property("text") == "Runs process one at a time"
    )
    heading = next(text for text in texts if text.property("text") == "RUN DECK")
    button = window.findChild(QObject, "allRunsButton")
    assert heading.x() + heading.width() <= button.x()
    assert summary.x() + summary.width() <= policy.x()
    assert policy.x() + policy.width() <= width + 0.1
    assert summary.property("contentWidth") <= summary.width() + 1.0
    assert heading.property("contentWidth") <= heading.width() + 1.0
    assert button.property("visible")
    assert policy.width() >= policy.property("implicitWidth") - 0.1
