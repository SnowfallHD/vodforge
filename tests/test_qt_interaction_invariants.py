"""Rendered cross-surface regressions for the Qt interaction controls."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication, QEvent, QObject
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


def test_current_folder_opens_its_selected_location_and_explains_relink(
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
        assert open_button.property("label") == "Open location"
        assert relink_button.property("label") == "Change folder location…"
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
        bridge.selectHome("Library")
        bridge.navigateLibrary("all")
        app.processEvents()
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
        QTest.mouseMove(window, card.mapToScene(card.boundingRect().center()).toPoint())
        app.processEvents()
        assert card.property("hovered") is True
        assert card.property("artworkFaceInset") == 9
        assert artwork.x() == 9
        assert artwork.width() == card.width() - 18
    finally:
        _close(bridge, engine, window)


def test_completed_download_remains_in_run_deck_ahead_of_old_stopped_run(
    tmp_path, monkeypatch
):
    app, bridge, engine, window = _launch(
        tmp_path, monkeypatch, [saved(tmp_path, "Just finished", "MP4")]
    )
    try:
        stopped = make_job(tmp_path)
        stopped.preview_info = {"title": "Old stopped run"}
        stopped.terminal_status = "Stopped"
        bridge._runtime.recovered = [stopped]
        bridge.selectHome("Forge")
        app.processEvents()
        records = bridge.runDeck["records"]
        assert [item["kind"] for item in records[:2]] == ["completed", "terminal"]
        assert bridge.forgeSelection["title"] == "Just finished"
        assert bridge.forgeSelection["status"].startswith("Completed")
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
