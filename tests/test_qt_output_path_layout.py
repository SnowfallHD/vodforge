"""Shared path presentation and bottom Selected Item actions retain geometry."""

import os
from pathlib import Path

import pytest
from PySide6.QtCore import QObject

from tests.test_qt_inspector_actions import scene, select_saved  # noqa: F401


@pytest.mark.parametrize("width,height", [(1100, 740), (1400, 900)])
def test_selected_path_tooltip_and_bottom_actions(scene, tmp_path, width, height):  # noqa: F811
    app, bridge, window = scene
    select_saved(bridge, tmp_path)
    window.resize(width, height)
    for _ in range(8):
        app.processEvents()
    inspector = window.findChild(QObject, "libraryFolderInspector")
    path = inspector.findChild(QObject, "libraryInspectorExactLocation")
    header_path = inspector.findChild(QObject, "libraryFolderSelectedLocation")
    assert not header_path.isVisible()
    full_path = "/output/" + "unbroken-segment" * 45 + "/media.mp4"
    path.setProperty("path", full_path)
    tip = path.findChild(QObject, "outputPathTooltip")
    tip.setProperty("visible", True)
    for _ in range(8):
        app.processEvents()
    label = path.findChild(QObject, "outputPathText")
    assert label.property("lineCount") == 1
    assert label.property("truncated")
    assert tip.property("text") == full_path
    assert tip.property("width") <= min(420, width - 32)
    tooltip_text = tip.findChild(QObject, "outputPathTooltipText")
    assert tooltip_text.property("lineCount") > 1
    assert tooltip_text.width() <= 420
    footer = inspector.findChild(QObject, "libraryInspectorActionFooter")
    assert footer.y() + footer.height() == pytest.approx(
        inspector.property("targetPanelBottom"), abs=1
    )
    assert path.height() == 34
    assert not path.findChildren(QObject, "recoveryDetailsScroll")
    capture = os.environ.get("VODFORGE_LAYOUT_CAPTURE_DIR")
    if capture:
        directory = Path(capture)
        directory.mkdir(parents=True, exist_ok=True)
        assert window.grabWindow().save(str(directory / f"selected-{width}.png"))
    bridge.select("Forge")
    app.processEvents()
    forge = window.findChild(QObject, "forgeDestinationField")
    assert forge.findChild(QObject, "outputPathText") is not None
    assert forge.property("path") == bridge.outputPath


def test_forge_path_tooltip_stays_inside_short_window(scene):  # noqa: F811
    app, bridge, window = scene
    window.resize(820, 560)
    bridge.select("Forge")
    field = window.findChild(QObject, "forgeDestinationField")
    field.setProperty("path", "/output/" + "longsegment" * 250)
    tip = field.findChild(QObject, "outputPathTooltip")
    tip.setProperty("visible", True)
    for _ in range(8):
        app.processEvents()
    assert tip.property("width") <= 420
    assert tip.property("height") <= 528
    viewport = tip.property("contentItem")
    assert viewport.property("contentHeight") > viewport.height()
    text = tip.findChild(QObject, "outputPathTooltipText")
    assert text.property("text") == field.property("path")
