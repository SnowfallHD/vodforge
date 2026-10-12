"""Owner-bound completed actions from both rendered Run Deck entry points."""

from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Qt
from PySide6.QtTest import QTest

from tests.test_qt_click_reliability import center
from tests.test_qt_interaction_invariants import _close, _launch
from tests.test_qt_overflow_action_pointer import _items, _record
from tests.test_qt_scene_port import saved, visual_item
from yt_downloader.qt_quick import main as qt_main


def open_menu(app, window, entry):
    if entry == "deck":
        trigger = visual_item(window.contentItem(), "runDeckAction_0")
        QTest.mouseClick(window, Qt.LeftButton, pos=center(trigger))
    else:
        trigger = window.findChild(QObject, "allRunsButton")
        QTest.mouseMove(window, center(trigger))
        QTest.qWait(160)
        popup = window.findChild(QObject, "allRunsPopup")
        assert popup.property("visible")
        card = next(
            item
            for item in _items(popup.property("contentItem"))
            if isinstance(_record(item), dict)
            and _record(item).get("kind") == "completed"
        )
        QTest.mouseClick(window, Qt.RightButton, pos=center(card))
    app.processEvents()
    QTest.qWait(160)
    popup = window.findChild(QObject, "runActionsPopup")
    assert popup.property("visible")
    return popup


@pytest.mark.parametrize("entry", ["deck", "all"])
@pytest.mark.parametrize("action", ["Play", "Show in Library", "Show in Folder"])
def test_completed_menu_routes_exact_saved_owner(tmp_path, monkeypatch, entry, action):
    row = saved(tmp_path, "Chosen", "MP4")
    Path(row["vodforge_output_path"]).write_bytes(b"private fixture")
    other = saved(tmp_path, "Other", "MP4")
    Path(other["vodforge_output_path"]).write_bytes(b"other fixture")
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [row, other])
    calls = []
    monkeypatch.setattr(bridge, "openLibraryItem", lambda index: calls.append(index))
    monkeypatch.setattr(
        qt_main.QDesktopServices,
        "openUrl",
        lambda url: calls.append(url.toLocalFile()) or True,
    )
    try:
        bridge._timer.stop()
        window.resize(1400, 900)
        QTest.qWait(120)
        popup = open_menu(app, window, entry)
        selected = window.findChild(QObject, "forgeRunDeck").property("selectedRecord")
        if hasattr(selected, "toVariant"):
            selected = selected.toVariant()
        chosen = next(
            r
            for r in bridge._runtime.history
            if qt_main.history_archive_owner(r) == selected["owner"]
        )
        buttons = {
            item.property("label"): item
            for item in popup.findChildren(QObject)
            if item.property("label") and item.property("visible")
        }
        assert {
            "Play",
            "Show in Library",
            "Show in Folder",
            "View Activity",
        } <= buttons.keys()
        button = buttons[action]
        assert button.property("enabled")
        QTest.mouseClick(window, Qt.LeftButton, pos=center(button))
        app.processEvents()
        assert not popup.property("visible")
        if action == "Play":
            assert calls == [bridge._runtime.history.index(chosen)]
        elif action == "Show in Library":
            assert bridge.selection == "Library"
            assert bridge.libraryDetail["owner"] == selected["owner"]
        else:
            assert calls == [str(Path(chosen["vodforge_output_path"]).parent)]
        assert Path(row["vodforge_output_path"]).read_bytes() == b"private fixture"
        assert Path(other["vodforge_output_path"]).read_bytes() == b"other fixture"
    finally:
        _close(bridge, engine, window)


@pytest.mark.parametrize("entry", ["deck", "all"])
def test_missing_media_keeps_library_and_activity_without_play_or_folder(
    tmp_path, monkeypatch, entry
):
    row = saved(tmp_path, "Missing", "MP4")
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [row])
    try:
        bridge._timer.stop()
        window.resize(1400, 900)
        QTest.qWait(120)
        popup = open_menu(app, window, entry)
        buttons = {
            item.property("label"): item
            for item in popup.findChildren(QObject)
            if item.property("label") and item.property("visible")
        }
        assert not buttons["Play"].property("enabled")
        assert not buttons["Show in Folder"].property("enabled")
        assert buttons["Show in Library"].property("enabled")
        assert buttons["View Activity"].property("enabled")
        QTest.mouseClick(window, Qt.LeftButton, pos=center(buttons["Show in Library"]))
        app.processEvents()
        assert bridge.selection == "Library"
        assert bridge.libraryDetail["owner"]
        assert not Path(row["vodforge_output_path"]).exists()
    finally:
        _close(bridge, engine, window)


@pytest.mark.parametrize("action", ["Play", "Show in Library", "Show in Folder"])
def test_open_menu_cannot_route_replaced_owner(tmp_path, monkeypatch, action):
    row = saved(tmp_path, "Original", "MP4")
    other = saved(tmp_path, "Replacement", "MP4")
    for record in (row, other):
        Path(record["vodforge_output_path"]).write_bytes(b"preserved fixture")
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [row, other])
    calls = []
    monkeypatch.setattr(bridge, "openLibraryItem", lambda index: calls.append(index))
    monkeypatch.setattr(
        qt_main.QDesktopServices, "openUrl", lambda url: calls.append(url) or True
    )
    try:
        bridge._timer.stop()
        window.resize(1400, 900)
        QTest.qWait(120)
        popup = open_menu(app, window, "deck")
        selected = window.findChild(QObject, "forgeRunDeck").property("selectedRecord")
        if hasattr(selected, "toVariant"):
            selected = selected.toVariant()
        bridge._runtime.history = [
            record
            for record in (row, other)
            if qt_main.history_archive_owner(record) != selected["owner"]
        ]
        button = next(
            item
            for item in popup.findChildren(QObject)
            if item.property("label") == action and item.property("visible")
        )
        QTest.mouseClick(window, Qt.LeftButton, pos=center(button))
        app.processEvents()
        assert calls == []
        assert bridge.selection == "Forge"
        assert "changed" in bridge.status or "unavailable" in bridge.status
        for record in (row, other):
            assert (
                Path(record["vodforge_output_path"]).read_bytes()
                == b"preserved fixture"
            )
    finally:
        _close(bridge, engine, window)


def test_saved_folder_open_failure_reports_without_data_change(tmp_path, monkeypatch):
    row = saved(tmp_path, "Saved", "MP4")
    path = Path(row["vodforge_output_path"])
    path.write_bytes(b"preserved fixture")
    _app, bridge, engine, window = _launch(tmp_path, monkeypatch, [row])
    try:
        monkeypatch.setattr(qt_main.QDesktopServices, "openUrl", lambda url: False)
        bridge.openLibraryFolder(qt_main.history_archive_owner(row))
        assert bridge.status == "The saved media folder could not be opened."
        assert path.read_bytes() == b"preserved fixture"
        assert bridge._runtime.history == [row]
    finally:
        _close(bridge, engine, window)
