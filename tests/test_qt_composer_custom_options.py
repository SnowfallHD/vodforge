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
    assert popup.property("height") <= min(540, window.height() - 39)


def test_custom_dropdown_morphs_and_summary_tracks_rate_control(run_scene):  # noqa: F811
    _app, bridge, window, _button, _popup = run_scene
    bridge.setExportMode("Manual Override")
    popup = window.findChild(QObject, "optionsMenu")
    popup.open()
    QTest.qWait(300)
    manual = window.findChild(QObject, "composerManualMp4")
    selector = manual.findChild(QObject, "manualRateControlSelector")
    selector.setProperty("expanded", True)
    QTest.qWait(80)
    assert 0 < selector.property("reveal") < 1
    QTest.qWait(200)
    assert selector.property("reveal") == 1
    bridge.setManualValue("manual_rate_control", "CBR")
    bridge.setManualValue("manual_video_bitrate", "8000")
    QTest.qWait(20)
    summary = window.findChild(QObject, "composerCustomSummaryValues")
    assert "8000 kbps video" in summary.property("text")
    selector.setProperty("expanded", False)
    QTest.qWait(300)
    assert selector.property("reveal") == 0


def test_custom_single_column_scrolls_with_expanded_choices(run_scene):  # noqa: F811
    _app, bridge, window, _button, _popup = run_scene
    bridge.setExportMode("Manual Override")
    popup = window.findChild(QObject, "optionsMenu")
    popup.open()
    manual = window.findChild(QObject, "composerManualMp4")
    scroll = window.findChild(QObject, "composerManualScroll")
    rate = manual.findChild(QObject, "manualRateControlSelector")
    audio = manual.findChild(QObject, "manualAudioCodecSelector")
    preset = manual.findChild(QObject, "manualPresetSelector")
    for width, height in ((1400, 900), (820, 560)):
        window.resize(width, height)
        rate.setProperty("expanded", True)
        QTest.qWait(350)
        assert manual.property("gridColumns") == 1
        assert abs(rate.mapToScene(QPointF()).x() - audio.mapToScene(QPointF()).x()) < 1
        assert (
            rate.mapToScene(QPointF(0, rate.height())).y()
            < audio.mapToScene(QPointF()).y()
        )
        assert popup.property("height") <= min(540, window.height() - 39)
        viewport = scroll.property("contentItem")
        maximum = max(0, viewport.property("contentHeight") - viewport.height())
        viewport.setProperty("contentY", maximum)
        QTest.qWait(40)
        bottom = preset.mapToScene(QPointF(0, preset.height())).y()
        assert bottom <= scroll.mapToScene(QPointF(0, scroll.height())).y() + 1
        assert viewport.property("contentWidth") <= viewport.width() + 1


def test_rate_control_hides_unused_field_and_preserves_values(run_scene):  # noqa: F811
    _app, bridge, window, _button, _popup = run_scene
    bridge.setExportMode("Manual Override")
    window.findChild(QObject, "optionsMenu").open()
    manual = window.findChild(QObject, "composerManualMp4")
    crf = manual.findChild(QObject, "manualCrfGroup")
    cbr = manual.findChild(QObject, "manualCbrGroup")
    bridge.setManualValue("manual_crf", "23")
    bridge.setManualValue("manual_video_bitrate", "8000")
    for mode in ("CBR", "Quality", "CBR"):
        bridge.setManualValue("manual_rate_control", mode)
        QTest.qWait(30)
        assert crf.isVisible() == (mode == "Quality")
        assert cbr.isVisible() == (mode == "CBR")
        assert str(bridge.manualValues["manual_crf"]) == "23"
        assert str(bridge.manualValues["manual_video_bitrate"]) == "8000"
