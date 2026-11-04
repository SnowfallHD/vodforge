"""The app-owned dropdown owner reuses liquid motion without resizing hit bounds."""

import pytest
from PySide6.QtCore import QObject
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch


def wait_until(condition, what, timeout_ms=2000):
    """Poll instead of fixed waits: slow (software-rendered CI) runners start
    and finish animations at different times, but must pass through the same
    states."""
    waited = 0
    while not condition():
        if waited >= timeout_ms:
            raise AssertionError(f"Timed out waiting for {what}")
        QTest.qWait(5)
        waited += 5


def midway(popup):
    return popup.property("visible") and 0 < popup.property("reveal") < 1


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
            wait_until(lambda: midway(popup), "the open animation part-way")
        width, height = popup.property("width"), popup.property("height")
        wait_until(
            lambda: popup.property("reveal") == 1, "the open animation to finish"
        )
        assert (popup.property("width"), popup.property("height")) == (width, height)
        popup.close()
        if reduced:
            QTest.qWait(5)
            assert not popup.property("visible")
        else:
            wait_until(lambda: midway(popup), "the close animation part-way")
            partway = popup.property("reveal")
            popup.open()
            assert popup.property("reveal") == partway, "Reopening cannot snap to zero"
            wait_until(lambda: popup.property("reveal") == 1, "the reopen to finish")
            popup.close()
            wait_until(lambda: not popup.property("visible"), "the popup to close")
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
        wait_until(
            lambda: popup.property("visible") and popup.property("reveal") == 1,
            "the popup to open",
        )
        if dismissal == "escape":
            QTest.keyClick(window, Qt.Key_Escape)
        else:
            press_trigger()
        wait_until(lambda: midway(popup), "the exit animation part-way")
        press_trigger()
        # A new click during the exit must reopen without the popup ever
        # disappearing in between.
        closed_in_between = []

        def reopened():
            if not popup.property("visible"):
                closed_in_between.append(True)
            return popup.property("reveal") == 1 and not popup.property(
                "exitInProgress"
            )

        wait_until(reopened, "the popup to reopen")
        assert not closed_in_between, "A new click during exit must reopen"
        press_trigger()
        wait_until(lambda: not popup.property("visible"), "the popup to close")
    finally:
        _close(bridge, engine, window)
