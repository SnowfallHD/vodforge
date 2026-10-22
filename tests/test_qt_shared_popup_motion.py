"""The app-owned dropdown owner reuses liquid motion without resizing hit bounds."""

import pytest
from PySide6.QtCore import QObject
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch


@pytest.mark.parametrize("reduced", [False, True])
def test_composer_dropdown_liquid_open_close(tmp_path, monkeypatch, reduced):
    from yt_downloader.qt_quick import main as qt_main

    monkeypatch.setattr(qt_main, "_system_reduced_motion", lambda: reduced)
    _app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        popup = window.findChild(QObject, "forgeFormatPopup")
        trigger = window.findChild(QObject, "forgeFormatButton")
        popup.setProperty("anchorItem", trigger)
        popup.open()
        assert popup.property("liquidMotion") is True
        if reduced:
            QTest.qWait(5)
            assert popup.property("reveal") == 1
        else:
            assert popup.property("reveal") == 0
            QTest.qWait(80)
            assert 0 < popup.property("reveal") < 1
        width, height = popup.property("width"), popup.property("height")
        QTest.qWait(260 if not reduced else 1)
        assert popup.property("reveal") == 1
        assert (popup.property("width"), popup.property("height")) == (width, height)
        popup.close()
        if reduced:
            QTest.qWait(5)
            assert not popup.property("visible")
        else:
            QTest.qWait(40)
            assert popup.property("visible") and 0 < popup.property("reveal") < 1
            midway = popup.property("reveal")
            popup.open()
            assert popup.property("reveal") == midway, "Reopening cannot snap to zero"
            QTest.qWait(260)
            assert popup.property("reveal") == 1
            popup.close()
            QTest.qWait(220)
            assert not popup.property("visible")
    finally:
        _close(bridge, engine, window)


@pytest.mark.parametrize("dismissal", ["escape", "trigger"])
def test_trigger_reopens_during_liquid_exit_without_extra_click(
    tmp_path, monkeypatch, dismissal
):
    from PySide6.QtCore import Qt

    from tests.test_qt_click_reliability import center

    _app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        popup = window.findChild(QObject, "forgeFormatPopup")
        trigger = window.findChild(QObject, "forgeFormatButton")

        def press_trigger():
            QTest.mouseClick(window, Qt.LeftButton, pos=center(trigger))

        press_trigger()
        QTest.qWait(280)
        assert popup.property("visible") and popup.property("reveal") == 1
        if dismissal == "escape":
            QTest.keyClick(window, Qt.Key_Escape)
        else:
            press_trigger()
        QTest.qWait(60)
        assert popup.property("visible") and 0 < popup.property("reveal") < 1
        press_trigger()
        QTest.qWait(300)
        assert popup.property("visible"), "A new click during exit must reopen"
        assert popup.property("reveal") == 1
        assert not popup.property("exitInProgress")
        press_trigger()
        QTest.qWait(220)
        assert not popup.property("visible")
    finally:
        _close(bridge, engine, window)
