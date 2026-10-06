"""Fixture-only input regressions; synthetic events are not physical acceptance."""

import pytest
from PySide6.QtCore import QObject, QPoint, QPointF, Qt
from PySide6.QtTest import QTest

from tests.test_qt_interaction_invariants import _close, _launch
from tests.test_qt_scene_port import qt_app, saved, visual_item


def center(item):
    point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
    return QPoint(round(point.x()), round(point.y()))


def test_rapid_second_click_activates_selection_toggle(tmp_path, monkeypatch):
    _app, bridge, engine, window = _launch(
        tmp_path, monkeypatch, [saved(tmp_path, "Fixture", "MP4")]
    )
    try:
        bridge.select("Library")
        bridge.navigateLibrary("all")
        QTest.qWait(100)
        button = window.findChild(QObject, "librarySelectButton")
        activations = []
        button.activated.connect(lambda: activations.append(button.property("label")))
        for _ in range(5):
            QTest.mouseDClick(window, Qt.LeftButton, pos=center(button))
            QTest.qWait(30)
            assert button.property("label") == "Select", activations
        assert len(activations) == 10
    finally:
        _close(bridge, engine, window)


@pytest.mark.parametrize(
    "section,trigger_name,popup_name",
    [
        ("Forge", "forgeOptionsButton", "optionsMenu"),
        ("Library", "libraryFilterButton", "libraryFilterPopup"),
        ("Watch", "watchHeroMoreButton", "watchHeroMorePopup"),
        ("Activity", "headerSettingsButton", "downloadSettingsPopup"),
    ],
)
def test_repeated_and_interrupted_popup_gestures(
    tmp_path,
    monkeypatch,
    section,
    trigger_name,
    popup_name,
):
    _app, bridge, engine, window = _launch(
        tmp_path, monkeypatch, [saved(tmp_path, "Fixture", "MP4")]
    )
    try:
        window.resize(1400, 900)
        bridge.select(section)
        if section == "Library":
            bridge.navigateLibrary("all")
        QTest.qWait(150)
        trigger = visual_item(window.contentItem(), trigger_name)
        popup = window.findChild(QObject, popup_name)
        assert trigger is not None and trigger.isVisible()
        for _ in range(3):
            QTest.mouseMove(window, center(trigger))
            QTest.mouseDClick(window, Qt.LeftButton, pos=center(trigger), delay=10)
            QTest.qWait(30)
            assert not popup.property("visible")
            QTest.mouseClick(window, Qt.LeftButton, pos=center(trigger))
            QTest.qWait(30)
            assert popup.property("visible")
            QTest.keyClick(window, Qt.Key_Escape)
            QTest.qWait(30)
            assert not popup.property("visible")
        # Cancel a held button by leaving its bounds, then ensure the next
        # complete click opens once, including after a hidden-scene transition.
        QTest.mousePress(window, Qt.LeftButton, pos=center(trigger))
        QTest.mouseMove(window, QPoint(2, 2))
        QTest.mouseRelease(window, Qt.LeftButton, pos=QPoint(2, 2))
        QTest.qWait(30)
        assert not popup.property("visible")
        bridge.select("Activity" if section != "Activity" else "Forge")
        bridge.select(section)
        QTest.qWait(100)
        QTest.mouseClick(window, Qt.LeftButton, pos=center(trigger))
        QTest.qWait(30)
        assert popup.property("visible")
        popup.close()
    finally:
        _close(bridge, engine, window)


def test_engine_enables_button_traversal_from_text_only_policy(tmp_path, monkeypatch):
    app = qt_app()
    hints = app.styleHints()
    previous = hints.tabFocusBehavior()
    hints.setTabFocusBehavior(Qt.TabFocusTextControls)
    try:
        _app, bridge, engine, window = _launch(
            tmp_path, monkeypatch, [saved(tmp_path, "Fixture", "MP4")]
        )
        try:
            bridge.select("Library")
            bridge.navigateLibrary("all")
            QTest.qWait(100)
            window.findChild(QObject, "headerSearchInput").forceActiveFocus()
            reached = []
            for _ in range(40):
                QTest.keyClick(window, Qt.Key_Tab)
                focus = window.activeFocusItem()
                reached.append(focus.objectName())
                if focus.objectName() == "librarySelectButton":
                    break
            assert "libraryFilterButton" in reached, reached
            assert reached[-1] == "librarySelectButton", reached
            QTest.keyClick(window, Qt.Key_Space)
            assert focus.property("label") == "Done"
            QTest.keyClick(window, Qt.Key_Return)
            assert focus.property("label") == "Select"
            QTest.keyClick(window, Qt.Key_Tab, Qt.ShiftModifier)
            assert window.activeFocusItem().objectName() == "libraryFilterButton"
            QTest.keyClick(window, Qt.Key_Return)
            QTest.qWait(40)
            assert window.findChild(QObject, "libraryFilterPopup").property("visible")
            QTest.keyClick(window, Qt.Key_Escape)
        finally:
            _close(bridge, engine, window)
    finally:
        hints.setTabFocusBehavior(previous)


def test_folder_rows_keep_distinct_double_activation(tmp_path, monkeypatch):
    from pathlib import Path

    from tests.test_qt_interaction_invariants import _visual_descendants

    record = saved(tmp_path, "Fixture", "MP4")
    Path(record["vodforge_output_path"]).write_bytes(b"fixture")
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [record])
    try:
        bridge.select("Library")
        bridge.navigateLibrary("folders")
        for _ in range(100):
            bridge._pump()
            app.processEvents()
            if not bridge.libraryFolders["checkingFolder"]:
                break
            QTest.qWait(20)
        QTest.qWait(100)
        listing = window.findChild(QObject, "libraryFolderList")
        row = next(
            item
            for item in _visual_descendants(listing)
            if item.objectName().startswith("libraryFolderComponent_")
        )
        single, double = [], []
        row.activated.connect(lambda: single.append(True))
        row.doubleActivated.connect(lambda: double.append(True))
        QTest.mouseDClick(window, Qt.LeftButton, pos=center(row))
        QTest.qWait(40)
        assert single == [True]
        assert double == [True]
        assert bridge.libraryFolders["selectedKey"]
        assert bridge.libraryDetail["title"] == "Fixture"
    finally:
        _close(bridge, engine, window)


def test_navigation_hit_faces_and_disabled_action(tmp_path, monkeypatch):
    _app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        for _ in range(3):
            for section in ("Library", "Watch", "Activity", "Forge"):
                button = visual_item(
                    window.contentItem(), "navigationButton_" + section
                )
                for fraction in (0.15, 0.5, 0.85):
                    point = button.mapToScene(
                        QPointF(button.width() * fraction, button.height() / 2)
                    )
                    QTest.mouseClick(
                        window,
                        Qt.LeftButton,
                        pos=QPoint(round(point.x()), round(point.y())),
                    )
                    assert bridge.selection == section
        download = window.findChild(QObject, "forgeDownloadButton")
        download.setEnabled(False)
        activations = []
        download.activated.connect(lambda: activations.append(True))
        QTest.mouseDClick(window, Qt.LeftButton, pos=center(download))
        download.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_Space)
        QTest.keyClick(window, Qt.Key_Return)
        assert activations == []
    finally:
        _close(bridge, engine, window)
