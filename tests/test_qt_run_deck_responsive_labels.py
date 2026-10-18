"""Offscreen layout regression; native small-window acceptance remains separate."""

import pytest
from PySide6.QtCore import QObject
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from tests.test_qt_all_runs_hover_seam import run_scene  # noqa: F401
from tests.test_qt_scene_port import make_job
from yt_downloader.button_metrics import BUTTON_METRICS


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


def action_buttons(window):
    inline = [window.findChild(QObject, f"forgeControl{i}") for i in range(3)]
    dropdown = next(
        item
        for item in window.findChildren(QObject)
        if item.property("label") == "Run actions"
    )
    return [item for item in [*inline, dropdown] if item.isVisible()]


@pytest.mark.parametrize("context", ["video", "playlist", "batch", "batch_playlist"])
def test_active_actions_share_deck_header_and_button_metrics(run_scene, context):  # noqa: F811
    from dataclasses import replace

    from PySide6.QtCore import QPointF

    from tests.test_qt_scene_port import polish_scene

    _app, bridge, window, _button, _popup = run_scene
    original = replace(
        bridge._runtime.active_job,
        batch_mode=context.startswith("batch"),
        single_video_only=not context.endswith("playlist"),
    )
    bridge._runtime.active_job = original
    bridge._runtime.events.put(("job_metadata", {"job": original, "info": {}}))
    bridge._pump()
    deck = window.findChild(QObject, "forgeRunDeck")
    all_runs = window.findChild(QObject, "allRunsButton")
    problems = []
    for size in [
        (820, 560),
        (821, 561),
        (900, 640),
        (1100, 689),
        (1100, 690),
        (1100, 740),
        (1400, 900),
        (820, 560),
    ]:
        window.resize(*size)
        polish_scene(window.contentItem())
        QTest.qWait(30)
        heading = next(
            text for text in text_items(deck) if text.property("text") == "RUN DECK"
        )
        hp = heading.mapToScene(QPointF())
        ap = all_runs.mapToScene(QPointF())
        buttons = action_buttons(window)
        assert buttons
        for button in buttons:
            caption = button.findChild(QObject, "stoneButtonCaption")
            assert (
                caption.property("font").pixelSize()
                == BUTTON_METRICS["inline"].font_pixels
            )
            assert button.height() == BUTTON_METRICS["inline"].height
            point = button.mapToScene(QPointF())
            if not (
                point.x() >= hp.x() + heading.width()
                and point.x() + button.width() <= ap.x() + 0.5
                and abs(point.y() - ap.y()) < 0.5
            ):
                problems.append(
                    (size, button.property("label"), "not shared header", point, hp, ap)
                )
            if abs(button.height() - all_runs.height()) > 0.5:
                problems.append(
                    (
                        size,
                        button.property("label"),
                        "height",
                        button.height(),
                        all_runs.height(),
                    )
                )
        assert deck.mapToScene(QPointF(0, deck.height())).y() <= window.height()
    assert not problems, problems


def test_active_action_width_tracks_text_and_falls_back_when_it_cannot_fit(run_scene):  # noqa: F811
    _app, bridge, window, _button, _popup = run_scene
    window.resize(1100, 820)
    QTest.qWait(60)
    inline = window.findChild(QObject, "forgeControl0")
    dropdown = window.findChild(QObject, "forgeRunActionsButton")
    assert inline.isVisible() and not dropdown.isVisible()
    original = inline.property("label")
    original_width = inline.width()
    inline.setProperty("label", "Cancel download and preserve completed files")
    QTest.qWait(30)
    assert inline.width() > original_width
    assert inline.width() == pytest.approx(inline.implicitWidth())
    inline.setProperty("label", "Very long translated action label " * 20)
    QTest.qWait(30)
    assert dropdown.isVisible() and not inline.isVisible()
    assert dropdown.width() == pytest.approx(dropdown.implicitWidth())
    inline.setProperty("label", original)
    QTest.qWait(30)
    assert inline.isVisible() and not dropdown.isVisible()
    assert inline.width() == pytest.approx(original_width)
    bridge._runtime.active_job = None
    bridge.runningChanged.emit()
    bridge.runDeckChanged.emit()
    QTest.qWait(30)
    assert action_buttons(window) == []


@pytest.mark.parametrize("compact", [False, True])
def test_active_cancel_hit_region_uses_exact_current_owner(
    run_scene,  # noqa: F811
    monkeypatch,
    compact,
):
    from dataclasses import replace

    from PySide6.QtCore import QPointF, Qt

    from tests.test_qt_scene_port import polish_scene

    _app, bridge, window, _button, _popup = run_scene
    original = bridge._runtime.active_job
    calls = []
    monkeypatch.setattr(bridge._runtime, "cancel", lambda: calls.append("cancel"))
    window.resize(820 if compact else 1100, 560 if compact else 820)
    QTest.qWait(80)

    def click(item):
        polish_scene(window.contentItem())
        point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
        assert 0 <= point.x() < window.width() and 0 <= point.y() < window.height()
        QTest.mouseClick(window, Qt.LeftButton, pos=point.toPoint())
        QTest.qWait(80)

    if compact:
        dropdown = window.findChild(QObject, "forgeRunActionsButton")
        click(dropdown)
        popup = window.findChild(QObject, "runActionsPopup")
        assert popup.property("visible")
        cancel = window.findChild(QObject, "deckControl0")
        assert cancel.property("label") == "Cancel download"
        bridge._runtime.active_job = replace(original)
        click(cancel)
        assert calls == [], "Retired menu execution must not cancel a successor"
        bridge._runtime.active_job = original
        bridge.runDeckChanged.emit()
        click(dropdown)
        assert popup.property("visible")
        click(cancel)
    else:
        click(window.findChild(QObject, "forgeControl0"))
    assert calls == ["cancel"]
