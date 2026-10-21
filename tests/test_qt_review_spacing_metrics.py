"""Review boundary: painted activity content and state-stable navigation metrics."""

import os
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QPointF, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch
from tests.test_qt_scene_port import polish_scene, visual_item
from yt_downloader.product_theme import THEME


@pytest.mark.parametrize(
    "size", [(820, 560), (821, 561), (900, 640), (1100, 689), (1100, 740)]
)
def test_activity_dial_has_real_allocation_above_run_deck(tmp_path, monkeypatch, size):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        assert window.minimumHeight() == 584 + (32 if sys.platform == "win32" else 0)
        window.resize(size[0], max(size[1], window.minimumHeight()))
        polish_scene(window.contentItem())
        QTest.qWait(80)
        app.processEvents()
        dial = visual_item(window.contentItem(), "forgeActivityModeSlider")
        heading = visual_item(window.contentItem(), "runDeckHeading")
        deck = visual_item(window.contentItem(), "forgeRunDeck")
        dy = dial.mapToScene(QPointF(0, dial.height())).y()
        hy = heading.mapToScene(QPointF()).y()
        assert dial.height() >= 116
        assert hy - dy >= 12, (size, dy, hy)
        assert deck.mapToScene(QPointF(0, deck.height())).y() <= window.height() + 1
        assert heading.mapToScene(QPointF()).y() >= 0
        assert deck.property("headingTopInset") >= 12
        if folder := os.environ.get("VODFORGE_REVIEW_EVIDENCE_DIR"):
            out = Path(folder)
            out.mkdir(parents=True, exist_ok=True)
            assert window.grabWindow().save(str(out / f"deck-{size[0]}x{size[1]}.png"))
    finally:
        _close(bridge, engine, window)


@pytest.mark.parametrize(
    "theme", ["Violet", "Cobalt", "Jade", "Ember", "Rose", "Custom accent"]
)
def test_top_navigation_color_changes_without_font_or_label_motion(
    tmp_path, monkeypatch, theme
):
    _app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        bridge.setAppearance(theme, "#28896c")
        bridge.selectHome("Forge")
        polish_scene(window.contentItem())
        QTest.qWait(80)
        button = visual_item(window.contentItem(), "navigationButton_Library")
        label = button.findChild(QObject, "stoneButtonCaption")

        def metric():
            font = label.property("font")
            point = label.mapToScene(QPointF())
            return (
                font.weight(),
                font.pixelSize(),
                label.property("implicitWidth"),
                button.width(),
                point.x(),
                point.y(),
            )

        idle = metric()
        assert idle[0] == 400
        window.requestActivate()
        QTest.mouseMove(
            window,
            button.mapToScene(
                QPointF(button.width() / 2, button.height() / 2)
            ).toPoint(),
        )
        QTest.qWait(50)
        assert metric() == idle
        point = button.mapToScene(
            QPointF(button.width() / 2, button.height() / 2)
        ).toPoint()
        QTest.mousePress(window, Qt.LeftButton, pos=point)
        assert metric() == idle
        QTest.mouseRelease(window, Qt.LeftButton, pos=point)
        bridge.selectHome("Library")
        polish_scene(window.contentItem())
        QTest.qWait(80)
        assert metric() == idle
        assert label.property("color") == QColor(THEME["accent"])
        icons = [
            c
            for c in button.findChildren(QObject)
            if c.metaObject().className().startswith("SceneIcon_")
            and c.property("visible")
        ]
        assert icons[0].property("tone") == QColor("#bda0ff")
        if folder := os.environ.get("VODFORGE_REVIEW_EVIDENCE_DIR"):
            out = Path(folder)
            out.mkdir(parents=True, exist_ok=True)
            assert window.grabWindow().save(
                str(out / ("label-" + theme.replace(" ", "-") + ".png"))
            )
    finally:
        _close(bridge, engine, window)
