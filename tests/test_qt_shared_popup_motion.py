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
