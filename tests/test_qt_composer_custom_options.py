"""Quick Options retains its liquid morph and shared manual settings bindings."""

import time

import pytest
from PySide6.QtCore import QObject, QPointF, Qt
from PySide6.QtTest import QTest

from tests.test_qt_all_runs_hover_seam import run_scene  # noqa: F401


def wait_for_reveal(selector, target):
    deadline = time.monotonic() + 2
    while selector.property("reveal") != target and time.monotonic() < deadline:
        QTest.qWait(20)
    assert selector.property("reveal") == target


def descendants(item):
    yield item
    for child in item.childItems():
        yield from descendants(child)


def test_custom_remains_in_shared_form_and_keeps_dialog_centered(run_scene):  # noqa: F811
    _app, bridge, window, _button, _popup = run_scene
    bridge.setExportMode("Everyday")
    popup = window.findChild(QObject, "optionsMenu")
    popup.open()
    QTest.qWait(100)
    menu = popup
    custom = next(
        item
        for item in descendants(menu.property("contentItem"))
        if item.property("label") == "Custom"
    )
    point = custom.mapToScene(QPointF(custom.width() / 2, custom.height() / 2))
    QTest.mouseClick(window, Qt.LeftButton, pos=point.toPoint())
    QTest.qWait(350)
    assert popup.property("visible")
    assert bridge.exportMode == "Manual Override"
    assert (
        abs(popup.property("x") + popup.property("width") / 2 - window.width() / 2) < 1
    )
    manual = window.findChild(QObject, "composerManualMp4")
    assert manual.isVisible() and manual.width() > 200
    assert popup.property("height") <= window.height() - popup.property("y")


@pytest.fixture
def motion_scene(monkeypatch, request):
    from yt_downloader.qt_quick import main

    reduced_motion = request.param
    monkeypatch.setattr(main, "_system_reduced_motion", lambda: reduced_motion)
    return request.getfixturevalue("run_scene"), reduced_motion


@pytest.mark.parametrize("motion_scene", [False, True], indirect=True)
def test_custom_dropdown_morphs_and_summary_tracks_rate_control(motion_scene):
    scene, reduced_motion = motion_scene
    _app, bridge, window, _button, _popup = scene
    bridge.setExportMode("Manual Override")
    popup = window.findChild(QObject, "optionsMenu")
    popup.open()
    QTest.qWait(300)
    manual = window.findChild(QObject, "composerManualMp4")
    selector = manual.findChild(QObject, "manualRateControlSelector")
    # Record each transition value instead of sampling after a wall-clock wait:
    # a loaded CI event loop can return from qWait after the animation ends.
    reveal_values = []

    def record_reveal():
        reveal_values.append(selector.property("reveal"))

    selector.revealChanged.connect(record_reveal)
    try:
        selector.setProperty("expanded", True)
        wait_for_reveal(selector, 1)
    finally:
        selector.revealChanged.disconnect(record_reveal)
    if reduced_motion:
        assert reveal_values == [1.0]
    else:
        assert any(0 < value < 1 for value in reveal_values), reveal_values
    bridge.setManualValue("manual_rate_control", "CBR")
    bridge.setManualValue("manual_video_bitrate", "8000")
    QTest.qWait(20)
    assert bridge.manualValues["manual_video_bitrate"] == "8000"
    assert popup.property("visible")
    selector.setProperty("expanded", False)
    wait_for_reveal(selector, 0)


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
        wait_for_reveal(rate, 1)
        QTest.qWait(40)
        assert manual.property("gridColumns") in {1, 2}
        assert popup.property("height") <= window.height() - popup.property("y")
        viewport = scroll.property("contentItem")
        maximum = max(0, viewport.property("contentHeight") - viewport.height())
        viewport.setProperty(
            "contentY",
            min(
                maximum,
                max(
                    0,
                    preset.mapToItem(viewport, 0, 0).y()
                    + viewport.property("contentY")
                    - viewport.height() / 2,
                ),
            ),
        )
        QTest.qWait(40)
        bottom = preset.mapToScene(QPointF(0, preset.height())).y()
        assert bottom <= scroll.mapToScene(QPointF(0, scroll.height())).y() + 1
        assert viewport.property("contentWidth") <= viewport.width() + 1
        for control in (rate, audio, preset):
            assert (
                control.mapToItem(manual, QPointF(control.width(), 0)).x()
                <= manual.width() + 1
            )


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


def test_options_stay_open_until_done_with_shared_selectors(run_scene):  # noqa: F811
    _app, bridge, window, _button, _popup = run_scene
    popup = window.findChild(QObject, "optionsMenu")
    popup.open()
    QTest.qWait(100)
    for mode in ("Streaming", "Manual Override", "Everyday"):
        bridge.setExportMode(mode)
        bridge.setQuality("1080p Full HD")
        QTest.qWait(30)
        assert popup.property("visible")
    assert bridge.exportMode == "Everyday" and bridge.quality == "1080p Full HD"
    close = window.findChild(QObject, "composerOptionsCloseButton")
    QTest.mouseClick(
        window,
        Qt.LeftButton,
        pos=close.mapToScene(QPointF(close.width() / 2, close.height() / 2)).toPoint(),
    )
    QTest.qWait(100)
    assert not popup.property("visible")


def test_dropdown_expansion_reveals_bottom_without_scrolling_visible_choices(run_scene):  # noqa: F811
    _app, bridge, window, _button, _popup = run_scene
    window.resize(1000, 700)
    bridge.setExportMode("Manual Override")
    popup = window.findChild(QObject, "optionsMenu")
    popup.open()
    QTest.qWait(350)
    manual = window.findChild(QObject, "composerManualMp4")
    scroll = window.findChild(QObject, "composerManualScroll")
    viewport = scroll.property("contentItem")
    rate = manual.findChild(QObject, "manualRateControlSelector")
    rate.setProperty("expanded", True)
    QTest.qWait(350)
    assert viewport.property("contentY") >= 0
    rate.setProperty("expanded", False)
    QTest.qWait(300)
    preset = manual.findChild(QObject, "manualPresetSelector")
    viewport.setProperty(
        "contentY", max(0, viewport.property("contentHeight") - viewport.height())
    )
    preset.setProperty("expanded", True)
    QTest.qWait(400)
    assert viewport.property("contentY") >= 0
    assert (
        viewport.property("contentY")
        <= max(0, viewport.property("contentHeight") - viewport.height()) + 1
    )
    bottom = preset.mapToScene(QPointF(0, preset.height())).y()
    assert bottom <= viewport.mapToScene(QPointF(0, viewport.height())).y() + 1
    assert popup.property("visible")


@pytest.mark.parametrize("motion_scene", [False, True], indirect=True)
def test_quick_custom_surface_morphs_without_opening_settings(motion_scene):
    scene, reduced_motion = motion_scene
    _app, bridge, window, _button, _popup = scene
    bridge.setExportMode("Everyday")
    popup = window.findChild(QObject, "optionsMenu")
    popup.open()
    QTest.qWait(300)
    initial_width = popup.property("width")
    values = []
    popup.customRevealChanged.connect(
        lambda: values.append(popup.property("customReveal"))
    )
    bridge.setExportMode("Manual Override")
    QTest.qWait(350)
    assert popup.property("customReveal") == 1
    assert popup.property("width") > initial_width
    assert not window.findChild(QObject, "downloadSettingsPopup").property("visible")
    if reduced_motion:
        assert values == [1.0]
    else:
        assert any(0 < value < 1 for value in values)
    bridge.setExportMode("Everyday")
    QTest.qWait(350)
    assert popup.property("customReveal") == 0
    assert popup.property("width") == pytest.approx(initial_width)
