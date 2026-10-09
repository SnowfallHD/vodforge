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


def _descendants(item):
    for child in item.childItems():
        yield child
        yield from _descendants(child)


def test_primary_action_and_selected_tab_are_visibly_distinct(tmp_path, monkeypatch):
    from PySide6.QtGui import QColor

    from yt_downloader.ui_theme import THEME

    _app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        download = window.findChild(QObject, "forgeDownloadButton")
        options = window.findChild(QObject, "forgeOptionsButton")
        assert download.property("primary") and not options.property("primary")

        def face(button):
            return next(
                item
                for item in button.childItems()
                if item.property("presentationRole") == "control"
                and "/button/" in item.property("source").toString()
            )

        # The accent colour is drawn by the shared raised/inset material owner.
        assert "/normal/1/primary/" in face(download).property("source").toString()
        assert "/primary" not in face(options).property("source").toString()
        point = center(download)
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, point)
        QTest.qWait(30)
        assert "/pressed/1/primary/" in face(download).property("source").toString()
        away = QPoint(5, window.height() - 5)
        QTest.mouseMove(window, away)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, away)
        QTest.qWait(30)
        assert "/pressed/" not in face(download).property("source").toString()
        caption = next(
            item
            for item in _descendants(download)
            if item.objectName() == "stoneButtonCaption"
        )
        # Dark text on the filled accent face, never accent text on a dark face.
        assert caption.property("color") == QColor(THEME["bg"])
        for selected in ("Library", "Forge"):
            bridge.select(selected)
            QTest.qWait(30)
            for section in ("Forge", "Library", "Watch", "Activity"):
                bar = visual_item(
                    window.contentItem(), "navigationSelectedBar_" + section
                )
                assert bar.property("visible") == (section == selected)
    finally:
        _close(bridge, engine, window)


def test_completed_run_offers_next_actions_and_hides_unrecorded_facts(
    tmp_path, monkeypatch
):
    _app, bridge, engine, window = _launch(
        tmp_path, monkeypatch, [saved(tmp_path, "Fixture", "MP4")]
    )
    try:
        window.resize(1400, 900)
        QTest.qWait(100)
        selection = bridge.forgeSelection
        assert selection["kind"] == "completed" and selection["owner"]
        actions = window.findChild(QObject, "forgeCompletedActions")
        assert actions.property("visible")
        assert actions.property("owner") == selection["owner"]
        play = window.findChild(QObject, "forgeCompletedPlay")
        assert play.property("primary") and play.property("label") == "Play"
        assert window.findChild(QObject, "forgeCompletedShowInFolder").property(
            "visible"
        )
        # The summary omits facts the file never recorded and says how many.
        rows = bridge.forgeSelectedFacts["rows"]
        missing = sum(row["value"] == "Not recorded" for row in rows)
        assert missing > 0
        details = visual_item(window.contentItem(), "forgeSourceDetails")
        shown = [
            item.property("text")
            for item in _descendants(details)
            if item.property("visible") and item.property("text")
        ]
        assert "Not recorded" not in shown
        note = next(
            item
            for item in _descendants(details)
            if item.objectName() == "forgeUnrecordedNote"
        )
        assert note.property("visible")
        assert note.property("text").startswith(f"{missing} detail")
        # Show in Library opens this exact item's Library page.
        show = window.findChild(QObject, "forgeCompletedShowInLibrary")
        QTest.mouseClick(window, Qt.LeftButton, pos=center(show))
        QTest.qWait(50)
        assert bridge.selection == "Library"
        assert bridge.libraryDetail["owner"] == selection["owner"]
    finally:
        _close(bridge, engine, window)


def test_run_without_saved_output_keeps_status_text_and_no_next_actions(
    tmp_path, monkeypatch
):
    _app, _bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        QTest.qWait(50)
        assert not window.findChild(QObject, "forgeCompletedActions").property(
            "visible"
        )
    finally:
        _close(_bridge, engine, window)


def test_primary_face_preserves_original_contour_in_every_state():
    from yt_downloader.ui_chrome import action_button_image

    for state in ("normal", "hover", "pressed", "disabled", "focus"):
        for density in (1, 2):
            primary = action_button_image(
                131, 44, accent=False, state=state, density=density, primary=True
            )
            original = action_button_image(
                131, 44, accent=False, state=state, density=density
            )
            # Lighting changes color only, never silhouette or shadow support.
            assert (
                primary.getchannel("A").tobytes() == original.getchannel("A").tobytes()
            )
