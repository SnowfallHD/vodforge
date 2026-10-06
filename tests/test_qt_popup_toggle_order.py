"""Popup toggle order: use pointer and keyboard delivery, not direct activation."""

import pytest
from PySide6.QtCore import QObject, QPoint, Qt
from PySide6.QtTest import QTest

from tests.test_qt_click_reliability import center
from tests.test_qt_interaction_invariants import _close, _launch
from tests.test_qt_scene_port import saved
from yt_downloader.qt_quick.input_trace import InputTrace


def click(window, item):
    QTest.mouseMove(window, center(item))
    QTest.mouseClick(window, Qt.LeftButton, pos=center(item))
    QTest.qWait(40)


@pytest.mark.parametrize("dismissal", ["trigger", "escape", "choice"])
def test_category_trigger_closes_after_text_field_focus_open(
    tmp_path, monkeypatch, dismissal
):
    _app, bridge, engine, window = _launch(
        tmp_path, monkeypatch, [saved(tmp_path, "Fixture", "MP4")]
    )
    trace = None
    try:
        owner = bridge.collectionPicker["videos"][0]["owner"]
        assert bridge.createCollection("Travel", [owner])
        assert bridge.openAnnotationOwner(owner)
        dialog = window.findChild(QObject, "libraryAnnotationPopup")
        dialog.open()
        QTest.qWait(80)
        field = window.findChild(QObject, "annotationCategoryInput")
        arrow = window.findChild(QObject, "annotationCategoryButton")
        menu = window.findChild(QObject, "annotationCategoryMenu")
        states = []
        focus_states = []
        field.activeFocusChanged.connect(
            lambda: focus_states.append(
                (field.hasActiveFocus(), str(field.property("focusReason")))
            )
        )
        menu.visibleChanged.connect(
            lambda: states.append(bool(menu.property("visible")))
        )
        trace = InputTrace(window)
        trace.watch_action(arrow, "fixture_action")
        trace.watch_popup(menu, "fixture_popup")
        click(window, field)
        assert menu.property("visible")
        if dismissal == "trigger":
            click(window, arrow)
        elif dismissal == "escape":
            QTest.keyClick(window, Qt.Key_Escape)
            QTest.qWait(40)
        else:
            from tests.test_qt_interaction_invariants import _visual_descendants

            choice = next(
                item
                for item in _visual_descendants(menu.property("contentItem"))
                if item.property("label") == "Travel"
            )
            click(window, choice)
            assert field.property("text") == "Travel"
        assert not menu.property("visible"), (states, focus_states, trace.snapshot())
        assert dialog.property("visible"), (
            dismissal,
            states,
            focus_states,
            trace.snapshot(),
        )
        click(window, arrow)
        assert menu.property("visible")
        click(window, arrow)
        assert not menu.property("visible"), (states, focus_states, trace.snapshot())
        QTest.keyClick(window, Qt.Key_Escape)
        QTest.qWait(40)
        assert not dialog.property("visible")
    finally:
        if trace:
            trace.stop()
        _close(bridge, engine, window)


def test_collections_hover_trigger_second_click_remains_closed(tmp_path, monkeypatch):
    _app, bridge, engine, window = _launch(
        tmp_path, monkeypatch, [saved(tmp_path, "Fixture", "MP4")]
    )
    try:
        bridge.select("Library")
        bridge.navigateLibrary("all")
        QTest.qWait(80)
        click(window, window.findChild(QObject, "libraryFilterButton"))
        trigger = window.findChild(QObject, "libraryCollectionsFilterButton")
        popup = window.findChild(QObject, "libraryCollectionsSubmenu")
        QTest.mouseMove(window, center(trigger))
        QTest.qWait(40)
        assert popup.property("visible")
        click(window, trigger)
        assert not popup.property("visible")
        click(window, trigger)
        assert popup.property("visible")
        click(window, trigger)
        assert not popup.property("visible")
    finally:
        _close(bridge, engine, window)


@pytest.mark.parametrize(
    "trigger_name,popup_name",
    [
        ("forgeOptionsButton", "optionsMenu"),
        ("headerSettingsButton", "downloadSettingsPopup"),
    ],
)
def test_trigger_close_survives_leave_and_return_during_same_press(
    tmp_path, monkeypatch, trigger_name, popup_name
):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        QTest.qWait(80)
        trigger = window.findChild(QObject, trigger_name)
        popup = window.findChild(QObject, popup_name)
        popup.setProperty("modal", False)
        click(window, trigger)
        assert popup.property("visible")
        position = center(trigger)
        QTest.mousePress(window, Qt.LeftButton, pos=position)
        app.processEvents()
        assert not popup.property("visible")
        assert popup.property("dismissedByTriggerPress")
        QTest.mouseMove(window, QPoint(2, 2))
        app.processEvents()
        assert bridge.isPointerPressed()
        QTest.mouseMove(window, position)
        QTest.mouseRelease(window, Qt.LeftButton, pos=position)
        QTest.qWait(40)
        assert not popup.property("visible")
        click(window, trigger)
        assert popup.property("visible")
    finally:
        _close(bridge, engine, window)


def test_trigger_toggle_during_exit_does_not_poison_next_close(tmp_path, monkeypatch):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        QTest.qWait(80)
        trigger = window.findChild(QObject, "forgeOptionsButton")
        popup = window.findChild(QObject, "optionsMenu")
        popup.setProperty("modal", False)
        component = QQmlComponent(engine)
        component.setParent(engine)
        component.setData(
            b"""import QtQuick
            Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 140 } }
        """,
            QUrl(),
        )
        animation = component.create()
        assert animation is not None, component.errors()
        popup.setProperty("exit", animation)
        click(window, trigger)
        assert popup.property("visible")
        QTest.mousePress(window, Qt.LeftButton, pos=center(trigger))
        app.processEvents()
        assert popup.property("visible")  # exit is in flight
        QTest.mouseRelease(window, Qt.LeftButton, pos=center(trigger))
        QTest.qWait(180)
        assert not popup.property("visible")
        click(window, trigger)
        assert popup.property("visible")
        click(window, trigger)
        QTest.qWait(180)
        assert not popup.property("visible")
    finally:
        _close(bridge, engine, window)


@pytest.mark.parametrize(
    "menu",
    [
        "quality",
        "output",
        "subtitles",
        "theme",
        "help",
        "profile",
        "support-reason",
        "sort",
        "format",
        "mp3",
        "conversion",
        "group",
        "selection",
        "saved-actions",
        "output-details",
    ],
)
def test_dropdown_matrix_repeated_pointer_and_keyboard(tmp_path, monkeypatch, menu):
    from PySide6.QtCore import QPointF

    from tests.test_qt_interaction_invariants import _visual_descendants

    _app, bridge, engine, window = _launch(
        tmp_path, monkeypatch, [saved(tmp_path, "Fixture", "MP4")]
    )
    try:
        window.resize(1600, 1000)
        settings = menu in ("quality", "output", "subtitles", "theme", "help")
        if settings:
            click(window, window.findChild(QObject, "headerSettingsButton"))
        elif menu == "profile":
            click(window, window.findChild(QObject, "forgeCreateVideoButton"))
        elif menu == "support-reason":
            assert bridge.openSupport("feedback")
        elif menu == "sort":
            bridge.select("Library")
            bridge.navigateLibrary("all")
        elif menu in ("group", "selection", "saved-actions"):
            bridge.select("Library")
            if menu != "group":
                bridge.navigateLibrary("all")
            QTest.qWait(80)
            if menu == "selection":
                click(window, window.findChild(QObject, "librarySelectButton"))
                click(window, window.findChild(QObject, "librarySelectionBarSelectAll"))
            elif menu == "saved-actions":
                assert bridge.openLibraryDetails(
                    bridge.libraryScene["media"][0]["owner"]
                )
        elif menu == "output-details":
            window.resize(850, 800)
        elif menu == "mp3":
            bridge.setOutputFormat("MP3")
        QTest.qWait(100)
        names = {
            "quality": "settingsQualityButton",
            "output": "settingsOutputModeButton",
            "subtitles": "translatedSubtitleButton",
            "mp3": "forgeOptionsButton",
            "conversion": "forgeCreateVideoButton",
            "selection": "librarySelectionActionsButton",
            "group": "libraryGroupMore",
        }
        if menu in names:
            trigger = next(
                item
                for item in _visual_descendants(window.contentItem())
                if item.isVisible() and item.objectName() == names[menu]
            )
        elif menu == "saved-actions":
            trigger = next(
                item
                for item in _visual_descendants(window.contentItem())
                if item.isVisible()
                and item.property("accessibilityLabel") == "More actions"
            )
        else:
            label = {
                "output-details": "Output details",
                "theme": bridge.appearanceTheme + "  ▾",
                "help": "Help",
                "profile": bridge.localProfile + "  ▾",
                "support-reason": "Select one…  ▾",
                "sort": "Newest first",
                "format": "MP4  ▾",
            }[menu]
            trigger = next(
                item
                for item in _visual_descendants(window.contentItem())
                if item.isVisible() and item.property("label") == label
            )
        assert trigger is not None and trigger.isVisible()
        if settings and menu != "help":
            body = window.findChild(QObject, "settingsBodyViewport")
            flick = body.property("contentItem")
            origin = trigger.mapToItem(flick, QPointF(0, 0))
            maximum = max(0, flick.property("contentHeight") - flick.height())
            flick.setProperty(
                "contentY",
                min(
                    maximum,
                    max(
                        0, flick.property("contentY") + origin.y() - flick.height() / 2
                    ),
                ),
            )
            QTest.qWait(120)
        click(window, trigger)
        popup = next(
            item
            for item in window.findChildren(QObject)
            if item.property("triggerItem") == trigger and item.property("visible")
        )
        click(window, trigger)
        assert not popup.property("visible"), menu
        for _ in range(3):
            # A complete rapid pair includes both press/release sequences.
            QTest.mouseDClick(window, Qt.LeftButton, pos=center(trigger), delay=10)
            QTest.qWait(30)
            assert not popup.property("visible"), (menu, "rapid pair")
            click(window, trigger)
            assert popup.property("visible"), (menu, "separated open")
            click(window, trigger)
            assert not popup.property("visible"), (menu, "separated close")
        for key in (Qt.Key_Space, Qt.Key_Return):
            trigger.forceActiveFocus(Qt.TabFocusReason)
            QTest.keyClick(window, key)
            QTest.qWait(40)
            assert popup.property("visible"), (menu, "keyboard open")
            QTest.keyClick(window, Qt.Key_Escape)
            QTest.qWait(40)
            assert not popup.property("visible"), (menu, "escape close")
        # A parent close/navigation must not poison the next use of the trigger.
        if settings:
            window.findChild(QObject, "downloadSettingsPopup").close()
            click(window, window.findChild(QObject, "headerSettingsButton"))
        elif menu in ("format", "mp3", "conversion", "sort"):
            section = bridge.selection
            bridge.select("Activity")
            bridge.select(section)
        QTest.qWait(100)
        click(window, trigger)
        assert popup.property("visible"), (menu, "reopen after interruption")
    finally:
        _close(bridge, engine, window)
