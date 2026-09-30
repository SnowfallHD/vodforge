"""Rendered cross-surface regressions for the Qt interaction controls."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Property, QCoreApplication, QEvent, QObject, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from tests.test_qt_scene_port import qt_app, saved
from tests.test_run_identity import make_job
from yt_downloader.qt_quick import main as qt_main


def _launch(tmp_path, monkeypatch, records):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = records
    # These interaction journeys start after the separate first-run tour.
    bridge._engagement.presented_welcome()
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    window.show()
    for _ in range(4):
        app.processEvents()
    return app, bridge, engine, window


def _close(bridge, engine, window):
    window.close()
    engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    bridge.close()


def _visual_descendants(item):
    for child in item.childItems():
        yield child
        yield from _visual_descendants(child)


def test_collection_picker_separates_single_media_from_playlist_batches(
    tmp_path, monkeypatch
):
    records = [saved(tmp_path, "First", "MP4"), saved(tmp_path, "Second", "MP3")]
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, records)
    try:
        picker = bridge.collectionPicker
        assert len(picker["videos"]) == 2
        assert len(picker["playlists"]) == 1
        assert len(picker["channels"]) == 1
        assert set(picker["playlists"][0]["owners"]) == {
            item["owner"] for item in picker["videos"]
        }
        bridge.selectHome("Library")
        app.processEvents()
        window.findChild(QObject, "addLibraryCollectionCard").activated.emit()
        for _ in range(4):
            app.processEvents()
        QTest.qWait(40)
        dialog = window.findChild(QObject, "libraryCollectionPopup")
        picker_list = window.findChild(QObject, "collectionPickerList")
        cards = [
            item
            for item in _visual_descendants(picker_list)
            if item.objectName() == "collectionPickerCard"
        ]
        assert dialog.property("visible") is True
        assert len(cards) == 2, (
            picker_list.property("count"),
            picker_list.width(),
            picker_list.height(),
        )
        assert all(
            any(
                item.objectName() == "collectionPickerArtwork"
                for item in _visual_descendants(card)
            )
            for card in cards
        )
        cards[0].activated.emit()
        app.processEvents()
        assert len(dialog.property("selectedOwners").toVariant()) == 1
        playlist_tab = next(
            item
            for item in _visual_descendants(dialog.property("contentItem"))
            if item.property("label") == "Playlists"
        )
        playlist_tab.activated.emit()
        app.processEvents()
        batch = [
            item
            for item in _visual_descendants(picker_list)
            if item.objectName() == "collectionPickerCard"
        ]
        assert len(batch) == 1
        batch[0].activated.emit()
        app.processEvents()
        assert set(dialog.property("selectedOwners").toVariant()) == set(
            picker["playlists"][0]["owners"]
        )
    finally:
        _close(bridge, engine, window)


def test_library_filter_menu_keeps_type_and_collection_choices_separate(
    tmp_path, monkeypatch
):
    records = [
        saved(tmp_path, "Movie", "MP4", category="Travel"),
        saved(tmp_path, "Song", "MP3", category="Travel"),
    ] + [saved(tmp_path, f"Extra {index}", "MP4") for index in range(20)]
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, records)
    try:
        assert bridge.createCollection(
            "Travel", [bridge.collectionPicker["videos"][0]["owner"]]
        )
        bridge.selectHome("Library")
        app.processEvents()
        button = window.findChild(QObject, "libraryFilterButton")
        button.activated.emit()
        app.processEvents()
        menu = window.findChild(QObject, "libraryFilterPopup")
        assert menu.property("visible") is True
        anchor = button.mapToItem(menu.property("parent"), 0, button.height())
        assert abs(menu.property("x") - anchor.x()) < 2
        anchor_top = button.mapToItem(menu.property("parent"), 0, 0).y()
        assert (
            min(
                abs(menu.property("y") - (anchor.y() - 3)),
                abs(menu.property("y") + menu.property("height") - anchor_top - 3),
            )
            < 2
        )
        audio = next(
            item
            for item in _visual_descendants(menu.property("contentItem"))
            if item.property("label") == "Audio"
        )
        audio.activated.emit()
        app.processEvents()
        assert bridge.libraryType == "Audio"
        assert [item["title"] for item in bridge.libraryScene["media"]] == ["Song"]
        button.activated.emit()
        app.processEvents()
        collections = window.findChild(QObject, "libraryCollectionsFilterButton")
        collections.activated.emit()
        app.processEvents()
        QTest.qWait(40)
        submenu = window.findChild(QObject, "libraryCollectionsSubmenu")
        assert submenu.property("visible") is True
        assert submenu.property("x") >= menu.property("x") + menu.property("width") - 8
        assert "Travel" in bridge.libraryCategories
        assert window.findChild(QObject, "libraryCollectionsFilterList").property(
            "count"
        ) == len(bridge.libraryCategories)
        submenu.close()
        menu.close()
        bridge.setLibraryType("All")
        button.activated.emit()
        app.processEvents()
        viewport = window.findChild(QObject, "libraryViewport")
        viewport.property("contentItem").setProperty("contentY", 10000)
        app.processEvents()
        assert viewport.property("contentItem").property("contentY") > 540
        assert menu.property("visible") is False
    finally:
        _close(bridge, engine, window)


def test_library_description_and_notes_share_height_and_copy_current_text(
    tmp_path, monkeypatch
):
    row = saved(tmp_path, "Ocean", "MP4")
    row["description"] = "The reef at dawn"
    row["vodforge_user_tags"] = ["reef", "travel"]
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [row])
    try:
        bridge.selectHome("Library")
        bridge.navigateLibrary("all")
        owner = bridge.libraryScene["media"][0]["owner"]
        assert bridge.openLibraryDetails(owner)
        app.processEvents()
        description = window.findChild(QObject, "libraryDescriptionPanel")
        notes = window.findChild(QObject, "libraryTagsNotesPanel")
        assert abs(description.height() - notes.height()) < 1
        more = next(
            item
            for item in _visual_descendants(window.contentItem())
            if item.property("accessibilityLabel") == "More actions"
        )
        more.activated.emit()
        app.processEvents()
        actions = window.findChild(QObject, "librarySavedActionsPopup")
        trigger_top = more.mapToItem(actions.property("parent"), 0, 0).y()
        assert actions.property("visible") is True
        assert actions.property("y") >= 0
        trigger_bottom = trigger_top + more.height()
        assert (
            actions.property("y") + actions.property("height") <= trigger_top + 4
            or actions.property("y") >= trigger_bottom - 4
        )
        assert bridge.copyLibraryText(owner, "description")
        assert QGuiApplication.clipboard().text() == "The reef at dawn"
        assert bridge.copyLibraryText(owner, "tags")
        assert QGuiApplication.clipboard().text() == "reef, travel"
        bridge.selectHome("Library")
        QTest.qWait(150)
        app.processEvents()
        assert actions.property("visible") is False
        bridge._playback_record = row
        assert bridge.copyLibraryText(owner, "description")
        assert window.findChild(QObject, "playerCopyDescriptionButton") is not None
        assert window.findChild(QObject, "playerCopyTagsButton") is not None
        assert not bridge.copyLibraryText("wrong-owner", "description")
    finally:
        _close(bridge, engine, window)


def test_settings_quality_output_and_help_have_own_button_menus(tmp_path, monkeypatch):
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        window.findChild(QObject, "headerSettingsButton").activated.emit()
        app.processEvents()
        settings = window.findChild(QObject, "downloadSettingsPopup")
        assert settings.property("visible") is True
        quality_button = window.findChild(QObject, "settingsQualityButton")
        output_button = window.findChild(QObject, "settingsOutputModeButton")
        quality = window.findChild(QObject, "settingsQualityMenu")
        output = window.findChild(QObject, "settingsOutputModeMenu")
        quality_button.activated.emit()
        app.processEvents()
        assert quality.property("visible") is True
        assert output.property("visible") is False
        quality.close()
        output_button.activated.emit()
        app.processEvents()
        assert output.property("visible") is True
        assert quality.property("visible") is False
        output.close()
        help_button = next(
            item
            for item in settings.findChildren(QObject)
            if item.property("label") == "Help"
        )
        help_button.activated.emit()
        app.processEvents()
        help_menu = window.findChild(QObject, "helpMenu")
        assert help_menu.property("visible") is True
        assert settings.property("visible") is True
        assert (
            abs(
                help_menu.property("x")
                - help_button.mapToItem(help_menu.property("parent"), 0, 0).x()
            )
            < 4
        )
    finally:
        _close(bridge, engine, window)


def test_current_folder_opens_its_selected_location_without_relink_controls(
    tmp_path, monkeypatch
):
    app, bridge, engine, window = _launch(
        tmp_path, monkeypatch, [saved(tmp_path, "Stored", "MP4")]
    )
    try:
        bridge.selectHome("Library")
        bridge.navigateLibrary("folders")
        root = bridge.libraryFolders
        assert bridge.openLibraryFolderComponent(root["locations"][0]["key"])
        app.processEvents()
        open_button = window.findChild(QObject, "libraryFolderOpenLocationButton")
        relink_button = window.findChild(QObject, "libraryFolderRelinkButton")
        assert open_button.property("visible") is True
        assert open_button.property("label") == "Open this folder"
        assert relink_button is None
        explanation = window.findChild(QObject, "libraryFolderRelinkExplanation")
        assert explanation is None
        opened = []
        monkeypatch.setattr(
            qt_main,
            "QDesktopServices",
            SimpleNamespace(
                openUrl=lambda url: opened.append(url.toLocalFile()) or True
            ),
        )
        open_button.activated.emit()
        assert [Path(path) for path in opened] == [Path(bridge.libraryFolders["path"])]
    finally:
        _close(bridge, engine, window)


def test_saved_media_cards_embed_artwork_in_hover_face(tmp_path, monkeypatch):
    app, bridge, engine, window = _launch(
        tmp_path, monkeypatch, [saved(tmp_path, "Stored", "MP4")]
    )
    try:
        assert QTest.qWaitForWindowExposed(window, 1000)
        bridge.selectHome("Library")
        bridge.navigateLibrary("all")
        QTest.qWait(50)
        repeater = window.findChild(QObject, "libraryMediaRepeater")
        card = next(
            item
            for item in _visual_descendants(repeater.parent())
            if item.property("accessibilityLabel") == "Details for Stored"
        )
        artwork = next(
            item
            for item in _visual_descendants(card)
            if item.objectName() == "libraryMediaArtworkImage"
        )
        assert card.property("artworkFaceInset") == 7
        assert artwork.x() == 7
        assert card.isVisible()
        # Bulk selection also uses the recessed face and must carry its artwork.
        assert card.setProperty("selected", True)
        app.processEvents()
        assert card.property("activeFace") is True
        assert card.property("artworkFaceInset") == 9
        assert artwork.x() == 9
        assert card.setProperty("selected", False)
        app.processEvents()
        assert card.property("artworkFaceInset") == 7
        # Keyboard focus uses the same recessed material face as pointer hover.
        # This drives the rendered face deterministically on offscreen runners.
        card.forceActiveFocus()
        app.processEvents()
        assert card.property("activeFocus") is True
        assert card.property("activeFace") is True
        assert card.property("artworkFaceInset") == 9
        assert artwork.x() == 9
        assert artwork.width() == card.width() - 18
    finally:
        _close(bridge, engine, window)


@pytest.mark.parametrize("status", ["Stopped", "Failed", "Skipped"])
def test_interrupted_download_stays_visible_when_newer_downloads_complete(
    tmp_path, monkeypatch, status
):
    from PIL import Image

    app, bridge, engine, window = _launch(
        tmp_path,
        monkeypatch,
        [saved(tmp_path, "Just finished", "MP4")]
        + [saved(tmp_path, f"Earlier {index}", "MP4") for index in range(4)],
    )
    try:
        requested = []

        def artwork(record, *args):
            requested.append(record["title"])
            path = tmp_path / (record["title"] + ".png")
            if not path.exists():
                Image.new("RGB", (160, 90), "#7197b8").save(path)
            return path.as_uri()

        monkeypatch.setattr(bridge._artwork, "request", artwork)
        stopped = make_job(tmp_path)
        stopped.preview_info = {"title": "Old stopped run"}
        stopped.terminal_status = status
        bridge._runtime.recovered = [stopped]
        bridge.runDeckChanged.emit()
        bridge.selectHome("Forge")
        app.processEvents()
        records = bridge.runDeck["records"]
        assert records[0]["kind"] == "completed"
        assert records[-1]["kind"] == "terminal"
        assert not records[-1]["artwork"]
        deck = window.findChild(QObject, "forgeRunDeck")
        assert [
            item["kind"] for item in deck.property("allRunsRecords").toVariant()[:2]
        ] == ["terminal", "completed"]
        assert "Old stopped run" in requested
        artwork_item = next(
            item
            for item in _visual_descendants(deck)
            if item.objectName() == "runDeckArtwork_0"
        )
        assert Path(artwork_item.property("source").toLocalFile()) == (
            tmp_path / "Old stopped run.png"
        )
        assert [
            item["kind"] for item in deck.property("visibleRecords").toVariant()[:2]
        ] == ["terminal", "completed"]
        assert bridge.forgeSelection["title"] == "Just finished"
        assert bridge.forgeSelection["status"].startswith("Completed")
    finally:
        _close(bridge, engine, window)


def test_folder_navigation_keeps_columns_fixed_while_async_contents_change(
    tmp_path, monkeypatch
):
    import time

    nested = tmp_path / ("A long readable directory name " * 5).strip()
    nested.mkdir()
    record = saved(nested, "Video", "MP4")
    Path(record["vodforge_output_path"]).write_bytes(b"video")
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [record])
    try:
        window.resize(1180, 800)
        bridge.select("Library")
        bridge.navigateLibrary("folders")
        app.processEvents()
        navigation = window.findChild(QObject, "libraryFolderNavigationColumn")
        content = window.findChild(QObject, "libraryFolderContentColumn")
        inspector = window.findChild(QObject, "libraryFolderInspector")

        def geometry():
            return tuple(
                (item.x(), item.width()) for item in (navigation, content, inspector)
            )

        baseline = geometry()
        for target in (nested, tmp_path, nested):
            bridge._folder_browser.navigate(qt_main.ArchivePath.parse(str(target)))
            bridge._queue_folder_listing()
            bridge.historyChanged.emit()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                bridge._pump()
                app.processEvents()
                assert geometry() == baseline
                if not bridge.libraryFolders["checkingFolder"]:
                    break
                QTest.qWait(10)
            assert not bridge.libraryFolders["checkingFolder"]
        assert navigation.width() == 184
        assert inspector.width() == 380
    finally:
        _close(bridge, engine, window)


def test_folder_scan_preserves_known_routes_until_a_verified_result(
    tmp_path, monkeypatch
):
    from yt_downloader.archive_work import ArchiveWorkResult

    nested = tmp_path / "Documents" / "Saved video"
    nested.mkdir(parents=True)
    record = saved(nested, "Video", "MP4")
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [record])
    try:
        monkeypatch.setattr(bridge, "_start_availability_scan", lambda: None)
        monkeypatch.setattr(bridge._availability_work, "poll", lambda: None)
        bridge.select("Library")
        bridge.navigateLibrary("folders")
        bridge._folder_browser.navigate(qt_main.ArchivePath.parse(str(tmp_path)))
        expected = bridge.libraryFolders["components"]
        assert expected
        bridge._queue_folder_listing()
        app.processEvents()
        assert bridge.libraryFolders["components"] == expected
        label = window.findChild(QObject, "libraryFolderEmptyLabel")
        assert not label.property("visible")
        result = ArchiveWorkResult(
            1, "folder_list", {"path": str(tmp_path), "entries": []}
        )
        monkeypatch.setattr(bridge._availability_work, "poll", lambda: result)
        bridge._pump()
        app.processEvents()
        assert not bridge.libraryFolders["checkingFolder"]
        assert bridge.libraryFolders["components"] == []
        assert label.property("visible")
        assert label.property("text") == "This folder is empty."
    finally:
        _close(bridge, engine, window)


@pytest.mark.parametrize("outcome", ["empty", "file", "error"])
def test_folder_loading_feedback_only_appears_for_a_slow_current_navigation(
    tmp_path, monkeypatch, outcome
):
    from yt_downloader.archive_work import ArchiveWorkResult

    nested = tmp_path / "Saved video"
    nested.mkdir()
    record = saved(nested, "Video", "MP4")
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [record])
    try:
        monkeypatch.setattr(bridge, "_start_availability_scan", lambda: None)
        monkeypatch.setattr(bridge._availability_work, "poll", lambda: None)
        bridge.select("Library")
        bridge.navigateLibrary("folders")
        app.processEvents()
        QTest.qWait(60)
        target = nested / "Empty child"
        bridge._folder_browser.navigate(qt_main.ArchivePath.parse(str(target)))
        bridge._queue_folder_listing()
        app.processEvents()
        label = window.findChild(QObject, "libraryFolderEmptyLabel")
        QTest.qWait(40)
        assert bridge.libraryFolders["checkingFolder"]
        assert not label.property("visible"), (
            window.findChild(QObject, "libraryFolderBrowser").property(
                "checkingFolder"
            ),
            window.findChild(QObject, "libraryFolderBrowser").property(
                "showFolderOpening"
            ),
            label.property("text"),
        )
        # Qt timers run on rendered frames, so CI may deliver the timeout later
        # than its 300 ms interval. Retain the no-flash assertion above and wait
        # boundedly for the delayed feedback's actual visible outcome.
        for _ in range(20):
            if label.property("visible"):
                break
            QTest.qWait(50)
        assert label.property("visible")
        assert label.property("text") == "Opening folder…"

        # A second navigation must get its own delay, not inherit the first's.
        target = nested / "Next child"
        bridge._folder_browser.navigate(qt_main.ArchivePath.parse(str(target)))
        bridge._queue_folder_listing()
        app.processEvents()
        QTest.qWait(40)
        assert not label.property("visible")
        result = ArchiveWorkResult(
            2,
            "folder_list",
            {"path": str(target), "entries": [("note.txt", "file", 10)]}
            if outcome == "file"
            else {"path": str(target), "entries": []},
            error="PermissionError" if outcome == "error" else "",
        )
        monkeypatch.setattr(bridge._availability_work, "poll", lambda: result)
        bridge._pump()
        app.processEvents()
        QTest.qWait(330)
        assert not bridge.libraryFolders["checkingFolder"]
        if outcome == "file":
            assert not label.property("visible")
            assert bridge.libraryFolders["components"][0]["title"] == "note.txt"
        else:
            assert label.property("visible")
            assert label.property("text") == (
                "This folder could not be opened."
                if outcome == "error"
                else "This folder is empty."
            )
    finally:
        _close(bridge, engine, window)


@pytest.mark.parametrize("origin", ["library_detail", "folders", "watch_group"])
@pytest.mark.parametrize("playing", [True, False])
def test_player_back_restores_origin_and_mini_close_keeps_that_route(
    tmp_path, monkeypatch, origin, playing
):
    from PySide6.QtMultimedia import QMediaPlayer

    from yt_downloader.app import history_archive_owner

    class Provider(QObject):
        # Keep provider timing independent from the navigation owner under test.
        @Property(int, constant=True)
        def playbackState(self):
            return (
                QMediaPlayer.PlayingState.value
                if playing
                else QMediaPlayer.PausedState.value
            )

        @Slot()
        def stop(self):
            pass

    record = saved(tmp_path, "Return to this item", "MP4")
    Path(record["vodforge_output_path"]).write_bytes(b"media")
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [record])
    try:
        owner = history_archive_owner(record)
        if origin == "watch_group":
            bridge.select("Watch")
            bridge.navigateWatchGroup("channel", "Creator")
            bridge.setWatchSearch("Return")
        else:
            bridge.select("Library")
            bridge.navigateLibrary("folders")
            bridge._folder_browser.navigate(qt_main.ArchivePath.parse(str(tmp_path)))
            if origin == "library_detail":
                assert bridge.openLibraryDetails(owner)
        before = (
            bridge.selection,
            bridge._library_scene_route,
            bridge._library_detail_owner,
            str(bridge._folder_browser.path),
            bridge._watch_scene_route,
            bridge._watch_group_kind,
            bridge._watch_group_key,
            bridge._watch_search,
        )
        assert bridge.openLibraryItem(0)
        app.processEvents()
        assert bridge.selection == "Watch"
        provider = Provider(window)
        window.setProperty("mediaPlayer", provider)
        scene = window.findChild(QObject, "watchPlayerScene")
        scene.closeRequested.emit()
        app.processEvents()
        assert (
            bridge.selection,
            bridge._library_scene_route,
            bridge._library_detail_owner,
            str(bridge._folder_browser.path),
            bridge._watch_scene_route,
            bridge._watch_group_kind,
            bridge._watch_group_key,
            bridge._watch_search,
        ) == before
        assert window.property("miniPlayerActive") is playing
        if playing:
            assert not bridge.playbackUrl.isEmpty()
            window.findChild(QObject, "miniPlayerClose").activated.emit()
            app.processEvents()
            assert bridge.selection == before[0]
            assert bridge._library_detail_owner == before[2]
            assert bridge._watch_scene_route == before[4]
            assert bridge._watch_search == before[7]
        assert bridge.playbackUrl.isEmpty()
    finally:
        _close(bridge, engine, window)


def test_all_media_loads_more_by_scrolling_without_losing_selected_item(
    tmp_path, monkeypatch
):
    records = [saved(tmp_path, f"Video {index:03}", "MP4") for index in range(100)]
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, records)
    try:
        window.resize(1180, 800)
        bridge.select("Library")
        bridge.navigateLibrary("folders")
        bridge.navigateLibraryFolders("all")
        app.processEvents()
        assert len(bridge.libraryFolders["components"]) == 48
        owner = bridge.libraryFolders["components"][0]["key"]
        bridge.selectLibraryFolderComponent(owner)
        app.processEvents()
        viewport = window.findChild(QObject, "libraryFolderViewport")
        flickable = viewport.property("contentItem")
        for count in (96, 100):
            flickable.setProperty(
                "contentY", flickable.property("contentHeight") - flickable.height()
            )
            app.processEvents()
            assert len(bridge.libraryFolders["components"]) == count
            assert bridge.libraryFolders["selectedKey"] == owner
            assert bridge._folder_component(owner) is not None
        assert not any(
            item.property("label") in {"Previous", "Next"}
            for item in _visual_descendants(window.contentItem())
            if item.isVisible()
        )
    finally:
        _close(bridge, engine, window)


def test_watch_organization_category_offers_existing_and_accepts_new(
    tmp_path, monkeypatch
):
    app, bridge, engine, window = _launch(
        tmp_path, monkeypatch, [saved(tmp_path, "Ocean", "MP4")]
    )
    try:
        owner = bridge.collectionPicker["videos"][0]["owner"]
        assert bridge.createCollection("Travel", [owner])
        assert bridge.openAnnotationOwner(owner)
        dialog = window.findChild(QObject, "libraryAnnotationPopup")
        dialog.open()
        app.processEvents()
        window.findChild(QObject, "annotationCategoryButton").activated.emit()
        app.processEvents()
        menu = window.findChild(QObject, "annotationCategoryMenu")
        assert menu.property("visible") is True
        travel = next(
            item
            for item in _visual_descendants(menu.property("contentItem"))
            if item.property("label") == "Travel"
        )
        travel.activated.emit()
        category = window.findChild(QObject, "annotationCategoryInput")
        assert category.property("text") == "Travel"
        category.setProperty("text", "New collection")
        save = next(
            item
            for item in _visual_descendants(dialog.property("contentItem"))
            if item.property("label") == "Save"
        )
        save.activated.emit()
        assert dialog.property("visible") is False
        assert bridge._annotations.annotation_for(owner).category == "New collection"
    finally:
        _close(bridge, engine, window)


@pytest.mark.parametrize("width", [1025, 1600])
@pytest.mark.parametrize("depth", [0, 8])
def test_file_path_trail_is_one_line_with_reachable_hidden_parents(
    tmp_path, monkeypatch, width, depth
):
    from tests.test_qt_scene_port import visual_item

    root = tmp_path / "My saved media"
    nested = root
    for index in range(depth):
        nested /= f"Long descriptive folder name number {index}"
    nested.mkdir(parents=True)
    record = saved(nested, "Video", "MP4")
    record["vodforge_retry_job"] = {"output_dir": str(root)}
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [record])
    try:
        window.resize(width, 800)
        bridge.select("Library")
        bridge.navigateLibrary("folders")
        bridge._folder_browser.navigate(qt_main.ArchivePath.parse(str(nested)))
        bridge._queue_folder_listing()
        bridge.historyChanged.emit()
        QTest.qWait(80)
        trail = window.findChild(QObject, "libraryFolderBreadcrumbs")
        back = window.findChild(QObject, "libraryFolderBackButton")
        assert trail.height() == 32
        assert trail.y() + trail.height() <= back.parentItem().y()
        assert trail.width() <= trail.parentItem().width()
        crumbs = bridge.libraryFolders["breadcrumbs"]
        current = visual_item(
            window.contentItem(), "libraryFolderCrumb_" + crumbs[-1]["key"]
        )
        assert current.property("selected")
        assert current.property("quiet")
        assert not current.property("interactive")
        assert current.width() >= 44
        for item in _visual_descendants(trail):
            if item.objectName().startswith("libraryFolderCrumb_") and item.isVisible():
                assert item.mapToItem(trail, 0, 0).x() >= -1
                assert item.mapToItem(trail, item.width(), 0).x() <= trail.width() + 1
        if depth:
            button = visual_item(window.contentItem(), "libraryFolderAncestorsButton")
            assert button.isVisible()
            button.activated.emit()
            QTest.qWait(40)
            popup = window.findChild(QObject, "libraryFolderAncestorsPopup")
            assert popup.property("visible")
            hidden = crumbs[1]
            ancestor = visual_item(
                window.contentItem(), "libraryFolderAncestor_" + hidden["key"]
            )
            # Popup delegates belong to the overlay's visual tree.
            if ancestor is None:
                ancestor = window.findChild(
                    QObject, "libraryFolderAncestor_" + hidden["key"]
                )
            assert ancestor is not None
            ancestor.activated.emit()
            app.processEvents()
            assert bridge.libraryFolders["path"] == hidden["key"]
            assert not popup.property("visible")
        else:
            back.activated.emit()
            app.processEvents()
            assert bridge.libraryScene["route"] == "home"
    finally:
        _close(bridge, engine, window)


@pytest.mark.parametrize(
    "popup_name", ["libraryFolderAncestorsPopup", "allRunsPopup", "optionsMenu"]
)
def test_floating_surfaces_cast_shadow_outside_unchanged_input_bounds(
    tmp_path, monkeypatch, popup_name
):
    root = tmp_path / "Media"
    nested = root / "Channel" / "Playlist" / "Video"
    nested.mkdir(parents=True)
    record = saved(nested, "Video", "MP4")
    record["vodforge_retry_job"] = {"output_dir": str(root)}
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [record])
    try:
        window.resize(1600, 1000)
        if popup_name == "libraryFolderAncestorsPopup":
            bridge.select("Library")
            bridge.navigateLibrary("folders")
            bridge._folder_browser.navigate(qt_main.ArchivePath.parse(str(nested)))
            bridge._queue_folder_listing()
            bridge.historyChanged.emit()
        # Folder results can change navigationKey and close an open ancestor
        # menu; admit the settled route before comparing consecutive frames.
        for _ in range(100):
            app.processEvents()
            if not bridge._folder_listing_pending:
                break
            QTest.qWait(20)
        assert not bridge._folder_listing_pending
        QTest.qWait(350)
        popup = window.findChild(QObject, popup_name)
        if popup_name == "libraryFolderAncestorsPopup":
            from tests.test_qt_scene_port import visual_item

            visual_item(
                window.contentItem(), "libraryFolderAncestorsButton"
            ).activated.emit()
        else:
            popup.open()
        QTest.qWait(150)
        assert popup.property("visible")
        background = popup.property("background")
        shadow = background.findChild(QObject, "popupElevationShadow")
        assert shadow is not None
        assert shadow.property("sourceSize").width() > 0
        bounds = (popup.property("width"), popup.property("height"))
        origin = background.mapToItem(window.contentItem(), 0, 0)
        x = round(origin.x() + background.width() + 6)
        y = round(origin.y() + background.height() / 2)
        elevated = window.grabWindow()
        assert 0 <= x < elevated.width() and 0 <= y < elevated.height()
        shadow.setProperty("visible", False)
        QTest.qWait(50)
        flat = window.grabWindow()
        assert popup.property("visible")
        assert elevated.pixelColor(x, y).lightness() < flat.pixelColor(x, y).lightness()
        assert bounds == (popup.property("width"), popup.property("height"))
        shadow.setProperty("visible", True)
        popup.close()
        app.processEvents()
        assert not popup.property("visible")
    finally:
        _close(bridge, engine, window)


@pytest.mark.parametrize(
    "menu", ["format", "options", "run", "active", "allruns", "folders"]
)
def test_popup_trigger_click_closes_without_reopening(tmp_path, monkeypatch, menu):
    from PySide6.QtCore import QPoint, Qt

    from tests.test_qt_scene_port import visual_item

    root = tmp_path / "Media"
    nested = root / "Channel" / "Playlist" / "Video"
    nested.mkdir(parents=True)
    record = saved(nested, "Video", "MP4")
    record["vodforge_retry_job"] = {"output_dir": str(root)}
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [record])
    try:
        window.resize(1600, 1000)
        if menu == "active":
            bridge._runtime.active_job = make_job(root)
            bridge.historyChanged.emit()
        if menu == "folders":
            bridge.select("Library")
            bridge.navigateLibrary("folders")
            bridge._folder_browser.navigate(qt_main.ArchivePath.parse(str(nested)))
            bridge._queue_folder_listing()
            bridge.historyChanged.emit()
            for _ in range(100):
                app.processEvents()
                if not bridge._folder_listing_pending:
                    break
                QTest.qWait(20)
        QTest.qWait(350)
        trigger_name, popup_name = {
            "format": ("forgeUrlField", "forgeFormatPopup"),
            "options": ("forgeOptionsButton", "optionsMenu"),
            "run": ("runDeckAction_0", "runActionsPopup"),
            "active": ("runDeckAction_0", "runActionsPopup"),
            "allruns": ("allRunsButton", "allRunsPopup"),
            "folders": ("libraryFolderAncestorsButton", "libraryFolderAncestorsPopup"),
        }[menu]
        trigger = visual_item(window.contentItem(), trigger_name)
        if menu == "format":
            trigger = next(
                item
                for item in _visual_descendants(trigger)
                if item.property("label") == "MP4  ▾"
            )
        popup = window.findChild(QObject, popup_name)
        point = trigger.mapToItem(
            window.contentItem(), trigger.width() / 2, trigger.height() / 2
        )
        position = QPoint(round(point.x()), round(point.y()))
        QTest.mouseMove(window, position)
        QTest.qWait(30)
        states = (
            (False, True, False, True, False)
            if menu == "allruns"
            else (True, False, True, False)
        )
        for click, expected in enumerate(states):
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=position)
            QTest.qWait(50)
            assert popup.property("visible") is expected, (
                click,
                expected,
                position,
                trigger.isVisible(),
                trigger.property("hovered"),
                popup.property("dismissedByTriggerPress"),
            )
            if menu == "active":
                assert (
                    bridge._run_menu_admitted_job is bridge._runtime.active_job
                ) is expected
        # Dismissal elsewhere must allow a new trigger click, rather than leave
        # behind a consumed-click flag from an unrelated outside press.
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=position)
        QTest.qWait(50)
        assert popup.property("visible")
        QTest.keyClick(window, Qt.Key.Key_Escape)
        QTest.qWait(50)
        assert not popup.property("visible")
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=position)
        QTest.qWait(50)
        assert popup.property("visible")
        # Model a real outside-click trajectory. Synthetic clicks can teleport
        # without sending the hover exit that precedes a physical press.
        QTest.mouseMove(window, QPoint(2, 2))
        QTest.qWait(30)
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=QPoint(2, 2))
        QTest.qWait(50)
        assert not popup.property("visible")
        QTest.mouseMove(window, position)
        if menu != "allruns":
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=position)
        QTest.qWait(50)
        assert popup.property("visible")
    finally:
        _close(bridge, engine, window)


def test_explicit_popup_close_does_not_consume_the_next_pointer_activation(
    tmp_path, monkeypatch
):
    from PySide6.QtCore import QPoint, Qt

    from tests.test_qt_scene_port import visual_item

    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        QTest.qWait(100)
        trigger = visual_item(window.contentItem(), "forgeOptionsButton")
        popup = window.findChild(QObject, "optionsMenu")
        point = trigger.mapToItem(
            window.contentItem(), trigger.width() / 2, trigger.height() / 2
        )
        position = QPoint(round(point.x()), round(point.y()))
        QTest.mouseMove(window, position)
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=position)
        QTest.qWait(30)
        assert popup.property("visible")
        # Hold a press across explicit activation, independently of Qt's
        # outside-press dismissal. Both close origins must remain distinct.
        popup.setProperty("closePolicy", 0)
        popup.setProperty("modal", False)
        popup.setProperty("x", 0)
        popup.setProperty("y", window.height() - popup.property("height"))
        QTest.mouseMove(window, QPoint(2, 2))
        QTest.mouseMove(window, position)
        QTest.qWait(30)
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=position)
        assert bridge.isPointerPressed() and trigger.property("hovered")
        trigger.activated.emit()
        app.processEvents()
        assert not popup.property("visible")
        assert not popup.property("dismissedByTriggerPress")
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=QPoint(2, 2))
        QTest.mouseMove(window, position)
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=position)
        QTest.qWait(30)
        assert popup.property("visible")
    finally:
        _close(bridge, engine, window)


@pytest.mark.parametrize("diagnostics", [False, True])
def test_support_consent_is_visible_and_form_fits_its_contents(
    tmp_path, monkeypatch, diagnostics
):
    from PySide6.QtCore import QPoint, Qt

    from yt_downloader.support_diagnostics import FailureContext

    _app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        window.resize(1600, 1000)
        if diagnostics:
            bridge._latest_failure = FailureContext("Bounded sanitized diagnostic")
        assert bridge.openSupport("feedback")
        QTest.qWait(150)
        popup = window.findChild(QObject, "supportPopup")
        consent = window.findChild(QObject, "supportDiagnosticsConsent")
        body = window.findChild(QObject, "supportBody")
        fields = window.findChild(QObject, "supportFields")
        assert consent.property("visible")
        assert consent.property("enabled") is diagnostics
        assert consent.property("checkable")
        assert not consent.property("checked")
        assert consent.property("background") is None
        reply = window.findChild(QObject, "supportReplyConsent")
        assert reply.property("background") is None
        assert not reply.property("checked")
        reply.forceActiveFocus()
        QTest.keyClick(window, Qt.Key.Key_Space)
        assert popup.property("reply")
        QTest.keyClick(window, Qt.Key.Key_Space)
        assert not popup.property("reply")
        assert body.height() <= fields.height() + 1
        if diagnostics:
            point = consent.mapToItem(
                window.contentItem(), consent.width() / 2, consent.height() / 2
            )
            position = QPoint(round(point.x()), round(point.y()))
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=position)
            assert popup.property("includeDiagnostics")
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=position)
            assert not popup.property("includeDiagnostics")
        assert not bridge.supportBusy
    finally:
        _close(bridge, engine, window)


def test_social_utility_opens_only_the_public_account(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(
        qt_main.QDesktopServices,
        "openUrl",
        lambda url: opened.append(url.toString()) or True,
    )
    app, bridge, engine, window = _launch(tmp_path, monkeypatch, [])
    try:
        button = window.findChild(QObject, "headerXButton")
        assert button.property("visible")
        assert button.property("accessibilityLabel") == "VODForge on X"
        assert button.property("quiet")
        button.activated.emit()
        app.processEvents()
        assert opened == ["https://x.com/VODForge"]
    finally:
        _close(bridge, engine, window)
