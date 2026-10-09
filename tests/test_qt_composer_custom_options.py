"""Composer Custom remains open and expands its manual controls on the left."""

from PySide6.QtCore import QObject, QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from tests.test_qt_all_runs_hover_seam import run_scene  # noqa: F401


def descendants(item):
    yield item
    for child in item.childItems():
        yield from descendants(child)


def test_custom_expands_left_column_and_keeps_dialog_centered(run_scene):  # noqa: F811
    app, bridge, window, _button, _popup = run_scene
    bridge.setExportMode("Everyday")
    popup = window.findChild(QObject, "optionsMenu")
    popup.open()
    QTest.qWait(300)
    before = popup.property("width")
    custom = next(
        item
        for item in descendants(popup.property("contentItem"))
        if item.property("label") == "Custom"
    )
    point = custom.mapToScene(QPointF(custom.width() / 2, custom.height() / 2))
    QTest.mouseClick(
        window, Qt.LeftButton, Qt.NoModifier, QPoint(round(point.x()), round(point.y()))
    )
    QTest.qWait(400)
    assert popup.property("visible")
    assert bridge.exportMode == "Manual Override"
    assert popup.property("width") > before
    assert (
        abs(popup.property("x") + popup.property("width") / 2 - window.width() / 2) < 1
    )
    manual = window.findChild(QObject, "composerManualMp4")
    assert manual.isVisible() and manual.width() > 200
    assert manual.mapToScene(QPointF()).x() < custom.mapToScene(QPointF()).x()
    assert 0.8 <= popup.property("surfaceOpacity") < 0.9
    assert popup.property("height") <= max(355, manual.implicitHeight() + 16) + 1
