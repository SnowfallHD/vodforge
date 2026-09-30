"""Cross-owner Qt scene projections used by Library, Watch and the Run Deck."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QEventLoop,
    QObject,
    QPoint,
    QPointF,
    QSize,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QInputDevice,
    QPointingDevice,
    QWheelEvent,
)
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtQml import QQmlComponent
from PySide6.QtTest import QTest

from tests.test_library_media_recovery import _job, _missing_record
from tests.test_quality_e2e import _isolated_launch
from tests.test_run_identity import make_job
from yt_downloader.app import cached_thumbnail_path
from yt_downloader.export_planning import EXPORT_MODES
from yt_downloader.history import history_archive_owner
from yt_downloader.library_annotations import LibraryAnnotation, LibraryAnnotationsError
from yt_downloader.library_artwork_source import ArtworkAsset
from yt_downloader.models import ExportMode
from yt_downloader.playback_backend import PlaybackSnapshot
from yt_downloader.playback_progress import PlaybackProgressOwner, WatchedProgress
from yt_downloader.playback_progress_binding import PlaybackProgressBinding
from yt_downloader.qt_quick import main as qt_main
from yt_downloader.qt_quick.artwork import QtArtwork, thumbnail_path
from yt_downloader.qt_quick.scene_projection import library_scene, watch_scene
from yt_downloader.run_state import RunStateError
from yt_downloader.support_diagnostics import FailureContext
from yt_downloader.ui_theme import THEME
from yt_downloader.whats_new import NativePreview

_QT_TEST_APP: QGuiApplication | None = None


def qt_app() -> QGuiApplication:
    """Keep Qt's application wrapper alive across scene tests and worker teardown."""
    global _QT_TEST_APP
    if _QT_TEST_APP is None:
        _QT_TEST_APP = QGuiApplication.instance() or QGuiApplication([])
    return _QT_TEST_APP


def visual_item(root, name: str):
    """Find a Repeater delegate through its visual parent hierarchy."""
    if root.objectName() == name:
        return root
    for child in root.childItems():
        if found := visual_item(child, name):
            return found
    return None


def saved(path: Path, name: str, kind: str, *, category: str = "") -> dict:
    return {
        "id": name,
        "title": name,
        "channel": "One channel",
        "playlist_id": "one-playlist",
        "playlist_title": "One playlist",
        "vodforge_output_dir": str(path),
        "vodforge_output_path": str(path / f"{name}.{kind.lower()}"),
        "vodforge_output_type": kind,
        "vodforge_user_category": category,
    }


def test_qt_library_group_card_counts_saved_variants_like_tk(tmp_path):
    records = [saved(tmp_path, "One", "MP4"), saved(tmp_path, "One", "MP3")]
    groups = library_scene(records, "home")["groups"]
    assert len(groups) == 1
    group = groups[0]
    assert group["count"] == 2
    assert group["videoCount"] == group["audioCount"] == 1
    assert group["summary"] == "2 items · 1 video · 1 audio"
    assert len(set(group["owners"])) == 2
    assert watch_scene(records, "home")["playlists"][0]["count"] == 1


def test_unfiled_video_stays_in_videos_without_becoming_a_playlist(tmp_path):
    named = saved(tmp_path, "Named", "MP4")
    unfiled = {
        **saved(tmp_path, "Star Wars export", "MP4"),
        "playlist_id": None,
        "playlist_title": None,
    }
    records = [named, unfiled]
    playlists = library_scene(records, "playlists")
    videos = library_scene(records, "videos")
    watch = watch_scene(records, "videos")
    assert playlists["counts"]["playlists"] == 1
    assert [group["title"] for group in playlists["groups"]] == ["One playlist"]
    assert {item["title"] for item in videos["media"]} == {"Named", "Star Wars export"}
    assert {item["title"] for item in watch["videos"]} == {"Named", "Star Wars export"}


def test_qt_navigation_returns_to_previous_route_and_top_tabs_open_home(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    bridge = qt_main.Bridge(None)
    try:
        bridge._runtime.history = [saved(tmp_path, "One", "MP4")]
        bridge.selectHome("Library")
        bridge.navigateLibrary("channels")
        channel = bridge.libraryScene["groups"][0]
        bridge.navigateLibraryGroup(channel["kind"], channel["key"])
        bridge.backLibrary()
        assert bridge.libraryScene["route"] == "channels"
        bridge.backLibrary()
        assert bridge.libraryScene["route"] == "home"
        bridge.navigateLibrary("folders")
        bridge.selectHome("Library")
        assert bridge.libraryScene["route"] == "home"
        bridge.selectHome("Watch")
        bridge.navigateWatch("playlists")
        playlist = bridge.watchScene["playlists"][0]
        bridge.navigateWatchGroup(playlist["kind"], playlist["key"])
        bridge.backWatch()
        assert bridge.watchScene["route"] == "playlists"
        assert bridge.openWatchDetails(playlist["owner"])
        bridge.backLibrary()
        assert bridge.selection == "Watch"
        assert bridge.watchScene["route"] == "playlists"
        bridge.selectHome("Watch")
        assert bridge.watchScene["route"] == "home"
    finally:
        bridge.close()


def test_qt_watch_home_rails_show_groups_across_full_width_and_load_on_scroll(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = []
    for index in range(14):
        item = saved(tmp_path, f"Video {index}", "MP4")
        item["playlist_id"] = f"playlist-{index}"
        item["playlist_title"] = f"Playlist {index}"
        bridge._runtime.history.append(item)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.selectHome("Watch")
        for _ in range(5):
            app.processEvents()

        def descendants(item):
            for child in item.childItems():
                yield child
                yield from descendants(child)

        rail = next(
            item
            for item in descendants(window.contentItem())
            if item.objectName() == "watchHomeRail_playlists"
        )
        repeater = next(
            item
            for item in descendants(rail)
            if item.objectName() == "watchHomeGroupRepeater"
        )
        assert rail.isVisible()
        assert rail.width() > window.width() * 0.7
        assert repeater.property("count") == 6
        flickable = rail.property("contentItem")
        assert flickable.setProperty("contentX", 600)
        for _ in range(5):
            app.processEvents()
        assert 6 < repeater.property("count") < 14
        viewport = window.findChild(QObject, "watchViewport")
        before = viewport.property("contentItem").property("contentY")
        point = rail.mapToScene(QPointF(120, 80))
        wheel = QWheelEvent(
            point,
            point,
            QPoint(),
            QPoint(0, -120),
            Qt.NoButton,
            Qt.NoModifier,
            Qt.ScrollUpdate,
            False,
        )
        QGuiApplication.sendEvent(window, wheel)
        for _ in range(5):
            app.processEvents()
        assert viewport.property("contentItem").property("contentY") > before
        rail_before = flickable.property("contentX")
        for phase, delta in ((Qt.ScrollUpdate, -53), (Qt.ScrollMomentum, -61)):
            swipe = QWheelEvent(
                point,
                point,
                QPoint(delta, 0),
                QPoint(),
                Qt.NoButton,
                Qt.NoModifier,
                phase,
                False,
            )
            QGuiApplication.sendEvent(window, swipe)
            app.processEvents()
        assert abs(flickable.property("contentX") - rail_before - 114) <= 1
        assert viewport.property("contentItem").property("contentY") > before
        page_before = viewport.property("contentItem").property("contentY")
        rail_before = flickable.property("contentX")
        touchpad = QPointingDevice(
            "Regression trackpad",
            47,
            QInputDevice.DeviceType.TouchPad,
            QPointingDevice.PointerType.Finger,
            QInputDevice.Capability.Position,
            1,
            0,
        )
        for phase, dx, dy in (
            (Qt.ScrollBegin, -15, -90),
            (Qt.ScrollMomentum, -45, -12),
        ):
            swipe = QWheelEvent(
                point,
                point,
                QPoint(dx, dy),
                QPoint(),
                Qt.NoButton,
                Qt.NoModifier,
                phase,
                False,
                Qt.MouseEventNotSynthesized,
                touchpad,
            )
            QGuiApplication.sendEvent(window, swipe)
            app.processEvents()
        assert viewport.property("contentItem").property("contentY") > page_before
        assert abs(flickable.property("contentX") - rail_before) <= 1
        loaded_before_tab_change = repeater.property("count")
        bridge.select("Activity")
        app.processEvents()
        bridge.select("Watch")
        app.processEvents()
        assert repeater.property("count") == loaded_before_tab_change
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_activity_opens_at_latest_and_tracks_new_lines(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._activity_log_text = "\n".join(f"event {i}" for i in range(200))
    bridge.activityChanged.emit()
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.selectHome("Activity")
        for _ in range(10):
            app.processEvents()
        viewport = window.findChild(QObject, "activityLogViewport")
        log = window.findChild(QObject, "activityLogText")
        flickable = viewport.property("contentItem")
        assert log.property("text").endswith("event 199")
        assert log.property("cursorPosition") == len(log.property("text"))
        assert (
            abs(
                flickable.property("contentY")
                - (flickable.property("contentHeight") - viewport.height())
            )
            <= 2
        )
        bridge._activity_log_text += "\nevent 200"
        bridge.activityChanged.emit()
        for _ in range(10):
            app.processEvents()
        assert log.property("text").endswith("event 200")
        assert log.property("cursorPosition") == len(log.property("text"))
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_library_group_menu_selects_every_saved_variant(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [
        saved(tmp_path, "One", "MP4"),
        saved(tmp_path, "One", "MP3"),
    ]
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.select("Library")
        app.processEvents()
        scene = window.findChild(QObject, "libraryBrowseScene")
        flow = window.findChild(QObject, "libraryGroupFlow")
        card = next(
            item
            for item in flow.childItems()
            if str(item.property("accessibilityLabel") or "").startswith(
                "One playlist, "
            )
        )
        more = next(
            item
            for item in card.childItems()
            if item.objectName() == "libraryGroupMore"
        )
        more.activated.emit()
        app.processEvents()
        menu = window.findChild(QObject, "libraryGroupMenu")
        assert menu.property("visible")
        window.findChild(QObject, "libraryGroupSelectButton").activated.emit()
        app.processEvents()
        assert not menu.property("visible")
        assert scene.property("selectionMode")
        assert set(scene.property("selectedOwners").toVariant()) == set(
            bridge.libraryScene["groups"][0]["owners"]
        )
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_library_group_cards_remain_visible_across_home_and_group_routes(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [saved(tmp_path, "One", "MP4")]
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.select("Library")
        flow = window.findChild(QObject, "libraryGroupFlow")
        home_slot = window.findChild(QObject, "libraryHomeGroupsSlot")
        route_slot = window.findChild(QObject, "libraryRouteGroupsSlot")
        for route in ("home", "channels", "playlists", "home"):
            bridge.navigateLibrary(route)
            for _ in range(3):
                app.processEvents()
            slot = home_slot if route == "home" else route_slot
            assert slot.isVisible(), route
            assert slot.height() >= 178, route
            assert flow.isVisible(), route
            assert any(
                child.isVisible()
                and child.height() == 178
                and child.property("accessibilityLabel")
                for child in flow.childItems()
            ), route
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_settings_extra_tags_reach_existing_download_job(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    try:
        assert bridge.setExtraTags("  one, two ,, three ")
        assert bridge.extraTags == "  one, two ,, three "
        assert not bridge.setExtraTags("x" * 81)
        assert bridge.extraTags == "  one, two ,, three "
        observed = []

        def intercept_start(*args, **kwargs):
            observed.append(kwargs)
            raise ValueError("intercepted before network work")

        monkeypatch.setattr(bridge._runtime, "start", intercept_start)
        bridge.submit("https://example.com/watch?v=abcdefghijk", "MP4")
        assert observed[0]["tags"] == ["one", "two", "three"]
        job = bridge._runtime.prepare_job(
            "https://example.com/watch?v=abcdefghijk",
            tmp_path,
            "MP4",
            "Everyday",
            tags=observed[0]["tags"],
        )
        assert job.tags == ["one", "two", "three"]
    finally:
        bridge.close()


@pytest.mark.parametrize("cause", ["missing_retry_url", "write_failed"])
def test_qt_unsaved_source_shows_shared_guidance_without_clearing_entry(
    tmp_path, monkeypatch, cause
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    accepted = []
    bridge.sourceAccepted.connect(lambda: accepted.append(True))
    try:

        def refuse(*_args, **_kwargs):
            raise RunStateError(
                "PRIVATE journal path and technical write details",
                cause=cause,
                stage="journal_write",
            )

        monkeypatch.setattr(bridge._runtime, "start", refuse)
        assert not bridge.submit("https://www.youtube.com/watch?v=qtRetry01A", "MP4")
        assert "PRIVATE" not in bridge.status
        assert "No download was started." in bridge.status
        assert ("Paste a valid web link" in bridge.status) == (
            cause == "missing_retry_url"
        )
        assert accepted == []
    finally:
        bridge.close()


def test_qt_appearance_refreshes_shared_material_and_saved_palette(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    try:
        window = engine.rootObjects()[0]
        original = window.property("color")
        before = bridge._theme_materials.requestImage(
            "button/120/40/normal/0/r0", QSize(), QSize()
        )
        before_icon = bridge._theme_materials.requestImage(
            "icon/settings.png/r0", QSize(), QSize()
        )
        before_accent = qt_main.THEME["accent"]
        assert bridge.setAppearance("Cobalt", bridge.customAccent)
        for _ in range(5):
            app.processEvents()
        assert bridge.themeRevision == 1
        assert window.property("color") != original
        after = bridge._theme_materials.requestImage(
            "button/120/40/normal/0/r1", QSize(), QSize()
        )
        after_icon = bridge._theme_materials.requestImage(
            "icon/settings.png/r1", QSize(), QSize()
        )
        assert before != after
        assert before_accent != qt_main.THEME["accent"]
        assert before_icon != after_icon
        for image, expected in (
            (before_icon, before_accent),
            (after_icon, qt_main.THEME["accent"]),
        ):
            pixels = (
                image.pixelColor(x, y)
                for y in range(image.height())
                for x in range(image.width())
            )
            assert (
                next(pixel.name() for pixel in pixels if pixel.alpha() == 255)
                == expected
            )
        assert not bridge.setAppearance("Custom accent", "unsafe")
        assert bridge.appearanceTheme == "Cobalt"
        bridge._save_preferences()
    finally:
        bridge.close()
        del engine
    reopened = qt_main.Bridge(None)
    try:
        assert reopened.appearanceTheme == "Cobalt"
    finally:
        reopened.close()


def test_qt_player_related_uses_saved_variant_owner_and_replaces_selected_media(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    first = saved(tmp_path, "First", "MP4")
    second = saved(tmp_path, "Second", "MP4")
    (tmp_path / "First.mp4").write_bytes(b"fixture one")
    (tmp_path / "Second.mp4").write_bytes(b"fixture two")
    bridge = qt_main.Bridge(None)
    try:
        bridge._runtime.history = [first, second]
        assert bridge.openLibraryItem(0)
        scene = bridge.playerScene
        assert scene["title"] == "First"
        assert [item["title"] for item in scene["upNext"]] == ["Second"]
        assert scene["source"] and scene["output"]
        bridge._runtime.history = [second, first]
        bridge.historyChanged.emit()
        assert bridge.playerScene["title"] == "First"
        assert bridge.playPlayerRelated(scene["upNext"][0]["owner"])
        assert bridge.playerScene["title"] == "Second"
        assert Path(bridge.playbackUrl.toLocalFile()) == tmp_path / "Second.mp4"
        assert not bridge.playPlayerRelated("unknown-saved-owner")
    finally:
        bridge.close()


def test_qt_library_description_uses_current_detail_owner_and_shared_annotations(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    first = saved(tmp_path, "First", "MP4")
    second = saved(tmp_path, "Second", "MP4")
    first["webpage_url"] = "https://example.com/media/first"
    bridge = qt_main.Bridge(None)
    try:
        bridge._runtime.history = [first, second]
        owners = [item["owner"] for item in bridge.collectionCandidates]
        assert bridge.openLibraryDetails(owners[0])
        assert bridge.copyLibraryFact(owners[0], "source", "Channel")
        assert QGuiApplication.clipboard().text() == "One channel"
        assert not bridge.copyLibraryFact(owners[1], "source", "Channel")
        assert not bridge.copyLibraryFact(owners[0], "source", "Unknown")
        opened = []
        monkeypatch.setattr(
            qt_main,
            "QDesktopServices",
            SimpleNamespace(openUrl=lambda url: opened.append(url.toString()) or True),
        )
        assert bridge.openLibrarySource(owners[0])
        assert opened == ["https://example.com/media/first"]
        assert bridge.libraryDetail["userDescription"] is False
        assert not bridge.saveLibraryDescription(owners[1], "Wrong subject")
        assert bridge.saveLibraryDescription(owners[0], "A private description")
        assert bridge.libraryDetail["description"] == "A private description"
        assert bridge.libraryDetail["userDescription"] is True
        assert not bridge.saveLibraryDescription(owners[0], "x" * 10_001)
        assert bridge.editLibraryTag(owners[0], " Travel ", False)
        assert bridge.editLibraryTag(owners[0], "travel", False)
        assert bridge.libraryDetail["tags"] == ["Travel"]
        assert not bridge.editLibraryTag(owners[1], "Wrong subject", False)
        assert not bridge.editLibraryTag(owners[0], "x" * 81, False)
        assert bridge.editLibraryTag(owners[0], "TRAVEL", True)
        assert bridge.libraryDetail["tags"] == []
        assert bridge.saveLibraryNote(owners[0], "A private note")
        assert bridge.libraryDetail["note"] == "A private note"
        assert not bridge.saveLibraryNote(owners[1], "Wrong subject")
        bridge.returnLibraryDetails()
        assert not bridge.saveLibraryDescription(owners[0], "Closed detail")
        assert not bridge.editLibraryTag(owners[0], "Closed detail", False)
        assert not bridge.saveLibraryNote(owners[0], "Closed detail")
    finally:
        bridge.close()


def test_qt_folder_browser_uses_shared_model_and_preserves_version_context(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    video = saved(tmp_path, "Same source", "MP4")
    audio = saved(tmp_path, "Same source", "MP3")
    Path(video["vodforge_output_path"]).write_bytes(b"video")
    Path(audio["vodforge_output_path"]).write_bytes(b"audio")
    video["webpage_url"] = audio["webpage_url"] = "https://example.com/same"
    bridge = qt_main.Bridge(None)
    try:
        bridge._runtime.history = [video, audio]
        bridge.navigateLibrary("folders")
        deadline = time.monotonic() + 2
        while bridge.libraryFolders["checkingFolder"] and time.monotonic() < deadline:
            bridge._pump()
            app.processEvents()
            QTest.qWait(10)
        root = bridge.libraryFolders
        assert root["mode"] == "folders"
        assert len(root["locations"]) == 1
        assert root["path"] == root["locations"][0]["key"]
        folder = bridge.libraryFolders
        assert folder["path"]
        media = next(item for item in folder["components"] if item["kind"] == "media")
        assert media["count"] == 2
        assert bridge.selectLibraryFolderComponent(media["key"])
        assert bridge.libraryFolders["selectedKey"] == media["key"]
        inspector = bridge.libraryFolderInspector
        assert inspector["title"] == "Same source"
        assert len(inspector["versions"]) == 2
        assert bridge.chooseLibraryFolderInspectorVersion(
            inspector["versions"][1]["owner"]
        )
        assert bridge.libraryFolderInspector["type"] == "MP3"
        assert not bridge.chooseLibraryFolderInspectorVersion("stale-owner")
        assert bridge.openSelectedLibraryFolderDetail()
        detail = bridge.libraryDetail
        assert detail["fromFolders"] is True
        assert detail["type"] == "MP3"
        assert len(detail["versions"]) == 2
        assert bridge.chooseLibraryVersion(detail["versions"][1]["owner"])
        assert bridge.libraryDetail["type"] == "MP3"
        assert not bridge.chooseLibraryVersion("stale-owner")
        bridge.returnLibraryDetails()
        assert bridge.libraryScene["route"] == "folders"
        assert bridge.libraryFolders["path"] == folder["path"]
        bridge.upLibraryFolder()
        assert bridge.libraryFolders["path"] == folder["path"]
        bridge.navigateLibraryFolders("all")
        assert bridge.libraryFolders["mode"] == "all"
        assert bridge.libraryFolders["path"] == ""
        assert all(
            row["kind"] == "media" for row in bridge.libraryFolders["components"]
        )
    finally:
        bridge.close()


def test_my_files_breadcrumbs_only_navigate_saved_ancestors(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [
        saved(tmp_path / "channel-a", "One", "MP4"),
        saved(tmp_path / "channel-b", "Two", "MP4"),
    ]
    for row in bridge._runtime.history:
        Path(row["vodforge_output_path"]).parent.mkdir(parents=True)
        Path(row["vodforge_output_path"]).write_bytes(b"video")
    try:
        bridge.select("Library")
        bridge.navigateLibrary("folders")
        deadline = time.monotonic() + 2
        while bridge.libraryFolders["checkingFolder"] and time.monotonic() < deadline:
            bridge._pump()
            app.processEvents()
            QTest.qWait(10)
        root = bridge.libraryFolders
        assert root["path"] == str(tmp_path)
        assert [crumb["label"] for crumb in root["breadcrumbs"]] == [tmp_path.name]
        folder = next(
            item for item in root["components"] if item["title"] == "channel-a"
        )
        assert bridge.openLibraryFolderComponent(folder["key"])
        assert [crumb["label"] for crumb in bridge.libraryFolders["breadcrumbs"]] == [
            tmp_path.name,
            "channel-a",
        ]
        assert not bridge.openLibraryBreadcrumb(str(tmp_path.parent))
        assert bridge.openLibraryBreadcrumb(str(tmp_path))
        assert bridge.libraryFolders["path"] == str(tmp_path)
    finally:
        bridge.close()


def test_folder_issues_are_distinct_from_full_forge_run_deck(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [saved(tmp_path, "Completed", "MP4")]
    (tmp_path / "Completed.mp4").write_bytes(b"saved")
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    bridge._window = window
    try:
        bridge.select("Library")
        bridge.navigateLibrary("folders")
        bridge.navigateLibraryFolders("issues")
        for _ in range(5):
            app.processEvents()
        assert bridge.runDeck["count"] == 1
        assert bridge.libraryFolders["count"] == 0
        assert (
            window.findChild(QObject, "libraryFolderLocationHeading").property("text")
            == "Issues & Recovery"
        )
        assert "Missing saved files" in window.findChild(
            QObject, "libraryFolderActivityExplanation"
        ).property("text")
        assert (
            window.findChild(QObject, "libraryFolderEmptyLabel").property("text")
            == "Nothing needs recovery."
        )
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_missing_saved_media_scans_on_entry_and_refreshes_one_item(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    original = _job(tmp_path)
    original.output_dir.mkdir()
    first = _missing_record(original)
    second = {
        **first,
        "id": "second",
        "title": "Second missing",
        "vodforge_output_path": str(original.output_dir / "Second missing.mp3"),
    }
    bridge._runtime.history = [first, second]
    try:
        bridge.select("Library")
        bridge.navigateLibraryFolders("issues")
        deadline = time.monotonic() + 2
        while (
            bridge.libraryFolders["checkingAvailability"]
            and time.monotonic() < deadline
        ):
            bridge._pump()
            app.processEvents()
            QTest.qWait(10)
        issues = bridge.libraryFolders
        assert not issues["checkingAvailability"]
        assert {row["title"] for row in issues["components"]} == {
            "Missing media",
            "Second missing",
        }
        assert all(row["kind"] == "missing" for row in issues["components"])
        first_issue = next(
            row for row in issues["components"] if row["title"] == "Missing media"
        )
        assert bridge.selectLibraryFolderComponent(first_issue["key"])
        assert bridge.libraryFolderInspector["canRedownload"]
        assert bridge.libraryFolderInspector["settings"]["source"] == original.url
        Path(first["vodforge_output_path"]).write_bytes(b"restored")
        bridge._queue_availability_scan([dict(first)], full=False)
        deadline = time.monotonic() + 2
        while bridge.libraryFolders["count"] != 1 and time.monotonic() < deadline:
            bridge._pump()
            app.processEvents()
            QTest.qWait(10)
        assert [row["title"] for row in bridge.libraryFolders["components"]] == [
            "Second missing"
        ]
        assert bridge.libraryFolderInspector.get("missing") is not True
    finally:
        bridge.close()


def test_missing_file_retry_stays_in_issues_until_saved_file_is_present(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    original = _job(tmp_path)
    original.output_dir.mkdir()
    row = _missing_record(original)
    bridge._runtime.history = [row]
    bridge._runtime._make_worker = lambda job: setattr(
        bridge._runtime, "active_job", job
    )
    try:
        bridge.select("Library")
        bridge.navigateLibraryFolders("issues")
        deadline = time.monotonic() + 2
        while (
            bridge.libraryFolders["checkingAvailability"]
            and time.monotonic() < deadline
        ):
            bridge._pump()
            app.processEvents()
            QTest.qWait(10)
        issue = bridge.libraryFolders["components"][0]
        assert bridge.selectLibraryFolderComponent(issue["key"])
        assert bridge.downloadSelectedIssue()
        active = bridge._runtime.active_job
        assert active is not None and active.run_id != original.run_id
        assert active.recovery_reason == "missing_media"
        assert bridge.selection == "Library"
        assert bridge.libraryFolderInspector["status"] == "Preparing"
        bridge._runtime.events.put(("status", "Downloading media — 2.3 MB/s"))
        bridge._pump()
        assert bridge.libraryFolderInspector["status"] == "Downloading"
        assert bridge.libraryFolders["count"] == 1
        assert (
            sum(
                path is not None
                for path in bridge._folder_browser._all_directories.values()
            )
            == 1
        )
        bridge._runtime.events.put(("error", "Test failure"))
        bridge._pump()
        assert bridge.libraryFolders["count"] == 1
        assert bridge.libraryFolderInspector["status"] == "Failed"
        assert bridge.downloadSelectedIssue()
        Path(row["vodforge_output_path"]).write_bytes(b"recovered")
        bridge._runtime.events.put(("done", "Complete"))
        bridge._pump()
        deadline = time.monotonic() + 2
        while bridge.libraryFolders["count"] and time.monotonic() < deadline:
            bridge._pump()
            app.processEvents()
            QTest.qWait(10)
        assert bridge.libraryFolders["count"] == 0
        assert bridge.selection == "Library"
    finally:
        bridge.close()


def test_missing_legacy_file_can_choose_settings_in_issues(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    original = _job(tmp_path)
    original.output_dir.mkdir()
    row = _missing_record(original)
    row.pop("vodforge_retry_job")
    bridge._runtime.history = [row]
    bridge._runtime._make_worker = lambda job: setattr(
        bridge._runtime, "active_job", job
    )
    try:
        bridge.select("Library")
        bridge.navigateLibraryFolders("issues")
        deadline = time.monotonic() + 2
        while (
            bridge.libraryFolders["checkingAvailability"]
            and time.monotonic() < deadline
        ):
            bridge._pump()
            app.processEvents()
            QTest.qWait(10)
        issue = bridge.libraryFolders["components"][0]
        assert bridge.selectLibraryFolderComponent(issue["key"])
        settings = bridge.libraryFolderInspector["settings"]
        assert settings["source_editable"]
        assert not bridge.downloadSelectedIssue()
        bridge.chooseIssueOutputUrl(QUrl.fromLocalFile(str(original.output_dir)))
        bridge.setIssueRetrySetting("export_mode", ExportMode.EVERYDAY.value)
        bridge.setIssueRetrySetting("quality", "1080p Full HD")
        assert bridge.downloadSelectedIssue()
        assert bridge._runtime.active_job.recovery_reason == "missing_media"
        assert bridge._runtime.active_job.single_video_only
        assert bridge.selection == "Library"
        assert bridge.libraryFolders["count"] == 1
    finally:
        bridge.close()


def test_unavailable_saved_location_is_not_reported_as_a_missing_file(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    monkeypatch.setattr(qt_main, "history_media_file_state", lambda _row: "unavailable")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [saved(tmp_path, "Offline", "MP4")]
    try:
        bridge.select("Library")
        bridge.navigateLibraryFolders("issues")
        deadline = time.monotonic() + 2
        while (
            bridge.libraryFolders["checkingAvailability"]
            and time.monotonic() < deadline
        ):
            bridge._pump()
            app.processEvents()
            QTest.qWait(10)
        assert bridge.libraryFolders["count"] == 0
        assert not bridge.libraryFolders["availabilityError"]
    finally:
        bridge.close()


def test_issue_inspector_retries_with_selected_settings_and_stays_until_success(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    stopped = make_job(tmp_path)
    stopped.terminal_status = "Stopped"
    stopped.preview_info = {"title": "Interrupted sample"}
    bridge._runtime.recovery.terminal_attempt(stopped, "Stopped", "Canceled")
    bridge._runtime.recovered = bridge._runtime.recovery.store.load_terminal_jobs()
    bridge._runtime._make_worker = lambda job: setattr(
        bridge._runtime, "active_job", job
    )
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    bridge._window = window
    try:
        bridge.select("Library")
        bridge.navigateLibraryFolders("issues")
        issue = bridge.libraryFolders["components"][0]
        assert issue["kind"] == "activity"
        assert bridge.selectLibraryFolderComponent(issue["key"])
        assert bridge.selection == "Library"
        assert bridge.libraryFolderInspector["settings"]["output_dir"] == str(tmp_path)
        for name in (
            "libraryIssueInspector",
            "libraryIssueOutputFolder",
            "libraryIssueFormat",
            "libraryIssueMode",
            "libraryIssueQuality",
            "libraryIssueOptions",
            "libraryIssueDownload",
        ):
            assert window.findChild(QObject, name) is not None
        mode_selector = window.findChild(QObject, "libraryIssueModeSelector")
        mode_button = window.findChild(QObject, "libraryIssueMode")
        closed_height = mode_selector.property("height")
        saved_mode = bridge.libraryFolderInspector["settings"]["export_mode"]
        mode_button.activated.emit()
        app.processEvents()
        assert mode_selector.property("expanded")
        assert mode_selector.property("height") > closed_height
        assert bridge.libraryFolderInspector["settings"]["export_mode"] == saved_mode
        mode_option = visual_item(
            mode_selector, "libraryIssueModeSelector_option_Manual Override"
        )
        assert mode_option is not None
        mode_option.activated.emit()
        app.processEvents()
        issue_panel = window.findChild(QObject, "libraryIssueInspector")
        scroll_content = issue_panel.property("contentItem")
        deadline = time.monotonic() + 2
        while scroll_content.property("contentY") <= 0 and time.monotonic() < deadline:
            QTest.qWait(20)
        assert bridge.libraryFolderInspector["settings"]["export_mode"] == (
            "Manual Override"
        )
        assert mode_selector.property("expanded")
        manual_controls = window.findChild(QObject, "libraryIssueManualMp4")
        quality_selector = window.findChild(QObject, "libraryIssueQualitySelector")
        assert manual_controls is not None and manual_controls.property("visible")
        assert quality_selector is not None
        manual_top = manual_controls.mapToItem(issue_panel, QPointF(0, 0)).y()
        assert manual_top < issue_panel.height() * 0.55, (
            issue_panel.property("contentItem").property("contentY"),
            issue_panel.property("contentItem").property("contentHeight"),
            manual_controls.y(),
        )
        assert (
            mode_option.mapToItem(issue_panel, QPointF(0, mode_option.height())).y()
            <= manual_controls.mapToItem(issue_panel, QPointF(0, 0)).y()
            < quality_selector.mapToItem(issue_panel, QPointF(0, 0)).y()
        )
        quality_button = window.findChild(QObject, "libraryIssueQuality")
        options_button = window.findChild(QObject, "libraryIssueOptions")
        quality_button.activated.emit()
        options_button.activated.emit()
        app.processEvents()
        max_scroll = scroll_content.property("contentHeight") - scroll_content.height()
        assert max_scroll > 0
        scroll_content.setProperty("contentY", max_scroll)
        app.processEvents()
        download_button = window.findChild(QObject, "libraryIssueDownload")
        download_top = download_button.mapToItem(issue_panel, QPointF(0, 0)).y()
        download_bottom = download_button.mapToItem(
            issue_panel, QPointF(0, download_button.height())
        ).y()
        assert 0 <= download_top < download_bottom <= issue_panel.height()
        options_button.activated.emit()
        quality_button.activated.emit()
        scroll_content.setProperty("contentY", 0)
        app.processEvents()
        before_scroll = mode_selector.mapToItem(issue_panel, QPointF(0, 0)).y()
        scroll_content.setProperty("contentY", 180)
        app.processEvents()
        assert mode_selector.property("expanded")
        assert mode_selector.mapToItem(issue_panel, QPointF(0, 0)).y() < before_scroll
        assert issue_panel.property("clip") is True
        scroll_content.setProperty("contentY", 0)
        mode_button.activated.emit()
        app.processEvents()
        assert not mode_selector.property("expanded")
        bridge.setIssueRetrySetting("quality", "720p HD")
        app.processEvents()
        assert manual_controls is not None and manual_controls.property("visible")
        original_forge_manual = bridge.manualValues
        preset_selector = manual_controls.findChild(QObject, "manualPresetSelector")
        preset_button = manual_controls.findChild(QObject, "manualPresetButton")
        old_preset = bridge.libraryFolderInspector["settings"]["manual"][
            "manual_preset"
        ]
        preset_button.activated.emit()
        app.processEvents()
        assert preset_selector.property("expanded")
        assert (
            bridge.libraryFolderInspector["settings"]["manual"]["manual_preset"]
            == old_preset
        )
        preset_option = visual_item(preset_selector, "manualPresetSelector_option_slow")
        assert preset_option is not None
        preset_option.activated.emit()
        app.processEvents()
        assert (
            bridge.libraryFolderInspector["settings"]["manual"]["manual_preset"]
            == "slow"
        )
        assert preset_selector.property("expanded")
        preset_button.activated.emit()
        app.processEvents()
        assert not preset_selector.property("expanded")
        bridge.setIssueManualValue("manual_rate_control", "Quality")
        bridge.setIssueManualValue("manual_crf", "99")
        assert not bridge.downloadSelectedIssue()
        assert bridge._runtime.active_job is None
        assert bridge.libraryFolders["count"] == 1
        bridge.setIssueManualValue("manual_crf", "19")
        assert bridge.manualValues == original_forge_manual
        assert bridge.downloadSelectedIssue()
        first = bridge._runtime.active_job
        assert first is not None
        assert first.quality_label == "720p HD"
        assert first.export_mode.value == "Manual Override"
        assert first.manual_settings.video_crf == 19
        assert first.preview_info["vodforge_issue_retry"] is True
        assert bridge.selection == "Library"
        assert bridge.libraryFolders["count"] == 1
        assert bridge.libraryFolderInspector["status"] == "Preparing"
        bridge._runtime.events.put(("status", "Downloading media — 2.3 MB/s"))
        bridge._pump()
        app.processEvents()
        assert bridge.libraryFolderInspector["status"] == "Downloading"
        assert bridge.libraryFolders["components"][0]["detail"] == "Downloading"
        bridge._runtime.events.put(("status", "Video 1 of 1 — transcoding"))
        bridge._pump()
        app.processEvents()
        assert bridge.libraryFolderInspector["status"] == "Transcoding"
        fresh_metadata = {"id": "abc123", "title": "Refreshed metadata"}
        bridge._runtime.recovery.metadata_observed(first, fresh_metadata)
        bridge._runtime.events.put(
            ("job_metadata", {"job": first, "info": fresh_metadata})
        )
        bridge._runtime.poll()
        assert first.preview_info["vodforge_issue_retry"] is True
        persisted = bridge._runtime.recovery.store.load()
        assert persisted is not None
        assert persisted["job"]["preview_info"]["vodforge_issue_retry"] is True
        assert bridge.libraryFolders["count"] == 1
        assert not bridge.downloadSelectedIssue()
        bridge._runtime._finish("error", "Test failure")
        bridge.historyChanged.emit()
        assert bridge.libraryFolders["count"] == 1
        assert bridge.libraryFolderInspector["status"] == "Failed"
        assert bridge.downloadSelectedIssue()
        completed = bridge._runtime.active_job
        assert completed is not None and completed.run_id != first.run_id
        bridge._runtime._finish("done", "Done")
        bridge._runtime.history = [
            {
                **saved(tmp_path, "Interrupted sample", "MP4"),
                "vodforge_run_id": completed.run_id,
            }
        ]
        bridge.historyChanged.emit()
        assert bridge.libraryFolders["count"] == 0
        assert bridge.selection == "Library"
        normal = make_job(tmp_path)
        bridge._runtime.active_job = normal
        bridge.historyChanged.emit()
        assert bridge.libraryFolders["count"] == 0
        app.processEvents()
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_issue_without_saved_source_requires_new_source_in_same_retry_path(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    stopped = make_job(tmp_path)
    stopped.url = ""
    stopped.urls = []
    stopped.terminal_status = "Stopped"
    stopped.preview_info = {"title": "Missing source"}
    bridge._runtime.recovery.terminal_attempt(stopped, "Stopped", "Canceled")
    bridge._runtime.recovered = bridge._runtime.recovery.store.load_terminal_jobs()
    bridge._runtime._make_worker = lambda job: setattr(
        bridge._runtime, "active_job", job
    )
    try:
        bridge.select("Library")
        bridge.navigateLibraryFolders("issues")
        issue = bridge.libraryFolders["components"][0]
        assert bridge.selectLibraryFolderComponent(issue["key"])
        assert bridge.libraryFolderInspector["settings"]["source_editable"]
        assert not bridge.downloadSelectedIssue()
        assert bridge.libraryFolders["count"] == 1
        bridge.setIssueRetrySource("https://www.youtube.com/watch?v=abc123")
        assert bridge.downloadSelectedIssue()
        assert bridge._runtime.active_job.url == (
            "https://www.youtube.com/watch?v=abc123"
        )
        assert bridge.selection == "Library"
        assert bridge.libraryFolders["count"] == 1
    finally:
        bridge.close()


def test_removing_queued_issue_retry_removes_it_from_issues(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    stopped = make_job(tmp_path)
    stopped.terminal_status = "Stopped"
    stopped.preview_info = {"title": "Retry later"}
    bridge._runtime.recovery.terminal_attempt(stopped, "Stopped", "Canceled")
    bridge._runtime.recovered = bridge._runtime.recovery.store.load_terminal_jobs()
    active = make_job(tmp_path)
    active.url = "https://www.youtube.com/watch?v=another"
    active.urls = [active.url]
    bridge._runtime.recovery.begin(active)
    bridge._runtime.active_job = active
    try:
        bridge.select("Library")
        bridge.navigateLibraryFolders("issues")
        assert bridge.selectLibraryFolderComponent(
            bridge.libraryFolders["components"][0]["key"]
        )
        assert bridge.downloadSelectedIssue()
        queued = bridge._runtime.queued[0]
        assert bridge.libraryFolderInspector["status"] == "Queued"
        assert bridge.removeQueued(queued.run_id)
        assert bridge.libraryFolders["count"] == 0
        assert bridge._runtime.recovered == []
        assert bridge._runtime.recovery.store.load_queued_jobs() == []
    finally:
        bridge.close()


def test_qt_folder_inspector_follows_tk_selection_and_compact_detail(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    record = saved(tmp_path, "Selected", "MP4")
    record["description"] = "Visible description for the selected saved item."
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [record]
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        window.resize(1100, 740)
        bridge.select("Library")
        bridge.navigateLibraryFolders("all")
        media = next(
            row for row in bridge.libraryFolders["components"] if row["kind"] == "media"
        )
        app.processEvents()
        assert not window.grabWindow().isNull()
        assert window.findChild(QObject, "libraryFolderBrowser").property(
            "showInspector"
        )
        assert not window.findChild(QObject, "libraryFolderDetailsPanel").property(
            "visible"
        )
        listing = window.findChild(QObject, "libraryFolderList")
        button = next(
            item
            for item in listing.childItems()
            if item.objectName() == "libraryFolderComponent_" + media["key"]
        )
        button.activated.emit()
        app.processEvents()
        inspector = window.findChild(QObject, "libraryFolderInspector")
        assert inspector.property("visible")
        assert window.findChild(QObject, "libraryFolderDetailsPanel").property(
            "visible"
        )
        assert round(inspector.property("width")) == 380
        assert bridge.libraryFolders["selectedKey"] == media["key"]
        panel = window.findChild(QObject, "libraryFolderDetailsPanel")
        open_details = window.findChild(QObject, "libraryFolderOpenDetails")
        assert 130 <= panel.height() <= 240
        assert (
            0
            < panel.mapToItem(None, 0, 0).y()
            - open_details.mapToItem(None, 0, open_details.height()).y()
            < 70
        )
        description_tab = window.findChild(QObject, "libraryFolderDescriptionTab")
        tab_top = description_tab.mapToItem(None, 0, 0).y()
        description_tab.activated.emit()
        app.processEvents()
        assert abs(description_tab.mapToItem(None, 0, 0).y() - tab_top) < 1
        assert panel.height() >= 360
        assert (
            window.findChild(QObject, "libraryFolderDescriptionText").property("text")
            == record["description"]
        )
        assert window.findChild(QObject, "libraryFolderDescriptionHeading").property(
            "visible"
        )

        window.resize(820, 560)
        app.processEvents()
        assert not inspector.property("visible")
        compact = window.findChild(QObject, "libraryFolderCompactDetails")
        assert compact.property("visible")
        selected_owner = bridge.libraryFolderInspector["owner"]
        compact.activated.emit()
        assert bridge.libraryScene["route"] == "detail"
        assert bridge.libraryDetail["owner"] == selected_owner
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_folder_description_attests_real_rendered_visibility(tmp_path, monkeypatch):
    environment, *_ = _isolated_launch(tmp_path)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    title = "A selected archive title with enough words to occupy more than two lines in the inspector rail"
    record = saved(tmp_path / ("very-long-folder-name-" * 5), title, "MP4")
    record["description"] = "Visible description. " * 80
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [record]
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    bridge._window = window
    try:
        window.resize(1100, 740)
        bridge.select("Library")
        bridge.navigateLibraryFolders("all")
        media = next(
            row for row in bridge.libraryFolders["components"] if row["kind"] == "media"
        )
        app.processEvents()
        listing = window.findChild(QObject, "libraryFolderList")
        button = next(
            item
            for item in listing.childItems()
            if item.objectName() == "libraryFolderComponent_" + media["key"]
        )
        button.activated.emit()
        app.processEvents()
        window.findChild(QObject, "libraryFolderDescriptionTab").activated.emit()
        for _ in range(5):
            app.processEvents()
        receipts = list(Path(environment["TMPDIR"]).glob("*library*visibility*.json"))
        assert len(receipts) == 1
        payload = json.loads(receipts[0].read_text(encoding="utf-8"))
        assert payload["verified"], payload
        assert payload["renderer"] == "qt"
        assert title not in receipts[0].read_text(encoding="utf-8")
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_player_presentation_rebinds_one_media_player_to_each_surface(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    try:
        window = engine.rootObjects()[0]
        scene = window.findChild(QObject, "watchPlayerScene")
        assert window.findChild(QObject, "watchMediaPlayer") is not None
        assert scene.property("activeSurfaceName") == "watchVideoSurface"
        assert window.property("playerSurfaceBound")
        presentation = window.findChild(QObject, "watchPresentationWindow")
        assert presentation.property("visible") is False
        assert presentation.close() is True
        assert scene.setProperty("presentationMode", "floating")
        app.processEvents()
        assert presentation.close() is True
        app.processEvents()
        assert scene.property("presentationMode") == "embedded"
        assert scene.property("activeSurfaceName") == "watchVideoSurface"
        assert window.property("playerSurfaceBound")
        assert scene.setProperty("presentationMode", "floating")
        for _ in range(5):
            app.processEvents()
        assert scene.property("activeSurfaceName") == "watchPresentationVideoSurface"
        assert window.property("playerSurfaceBound")
        assert scene.setProperty("presentationMode", "fullscreen")
        for _ in range(5):
            app.processEvents()
        assert scene.property("activeSurfaceName") == "watchPresentationVideoSurface"
        assert window.property("playerSurfaceBound")
        assert scene.setProperty("presentationMode", "embedded")
        for _ in range(5):
            app.processEvents()
        assert scene.property("activeSurfaceName") == "watchVideoSurface"
        assert window.property("playerSurfaceBound")
        assert presentation.property("visible") is False
        assert presentation.close() is True
    finally:
        window.close()
        app.processEvents()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        bridge.close()


def test_qt_player_controls_share_video_surface_at_wide_and_compact_sizes(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    media = saved(tmp_path, "Overlay", "MP4")
    (tmp_path / "Overlay.mp4").write_bytes(b"geometry fixture")
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [media]
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    bridge._window = window
    try:
        assert bridge.openLibraryItem(0)
        stage = window.findChild(QObject, "playerMediaStage")
        overlay = window.findChild(QObject, "embeddedPlayerOverlay")
        assert overlay.parentItem() is stage
        assert window.findChild(QObject, "playerTransportRow") is None
        for name in (
            "playerOverlayPlay",
            "playerOverlayBack10",
            "playerOverlayForward10",
            "playerOverlayMute",
            "playerOverlayVolume",
            "playerOverlaySeek",
            "playerCaptionsButton",
            "playerOverlayOptions",
            "playerOverlayFloating",
            "playerOverlayFullscreen",
        ):
            assert window.findChild(QObject, name) is not None, name
        for width, height in ((1280, 800), (820, 560)):
            window.resize(width, height)
            for _ in range(5):
                app.processEvents()
            assert stage.width() <= stage.parentItem().width()
            assert abs(stage.width() / stage.height() - 16 / 9) < 0.02
            assert 0 <= overlay.y() < stage.height()
            assert overlay.y() + overlay.height() <= stage.height() + 1
            assert overlay.width() == stage.width()
        # Moving over the video must restore controls after their playback
        # timeout; the hidden overlay cannot own that pointer event itself.
        from PySide6.QtTest import QTest

        overlay.setProperty("controlsShown", False)
        app.processEvents()
        assert overlay.property("visible") is False
        stage_center = stage.mapToItem(window.contentItem(), QPointF(60, 60))
        QTest.mouseMove(
            window, QPoint(round(stage_center.x()), round(stage_center.y()))
        )
        app.processEvents()
        assert overlay.property("visible") is True
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


@pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("ffmpeg") is None,
    reason="macOS Qt multimedia fixture requires ffmpeg",
)
def test_qt_library_player_video_click_and_escape_change_real_playback(
    tmp_path, monkeypatch
):
    from PySide6.QtTest import QTest

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    media = saved(tmp_path, "Clickable", "MP4")
    subprocess.run(
        [
            shutil.which("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=15",
            "-t",
            "15",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            str(tmp_path / "Clickable.mp4"),
        ],
        check=True,
        timeout=30,
    )
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [media]
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    bridge._window = window
    window.resize(1280, 800)
    window.show()

    def until(predicate, timeout=5.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            app.processEvents()
            if predicate():
                return True
            time.sleep(0.01)
        return False

    try:
        bridge.selectHome("Library")
        assert bridge.openLibraryItem(0)
        player = lambda: window.property("mediaPlayer")
        assert until(
            lambda: player().property("playbackState") == QMediaPlayer.PlayingState
        )
        stage = window.findChild(QObject, "playerMediaStage")
        point = stage.mapToItem(window.contentItem(), QPointF(stage.width() / 2, 80))
        click = QPoint(round(point.x()), round(point.y()))
        QTest.mouseClick(window, Qt.LeftButton, pos=click)
        assert until(
            lambda: player().property("playbackState") == QMediaPlayer.PausedState
        )
        QTest.mouseClick(window, Qt.LeftButton, pos=click)
        assert until(
            lambda: player().property("playbackState") == QMediaPlayer.PlayingState
        )

        scene = window.findChild(QObject, "watchPlayerScene")
        scene.setProperty("presentationMode", "fullscreen")
        presentation = window.findChild(QObject, "watchPresentationWindow")
        assert until(lambda: presentation.property("visible"))
        QTest.keyClick(presentation, Qt.Key_Escape)
        assert until(lambda: scene.property("presentationMode") == "embedded")
        assert until(lambda: player().property("position") >= 800)
        library_button = next(
            (
                child
                for child in window.findChild(QObject, "navigationRow").childItems()
                if child.objectName() == "navigationButton_Library"
            ),
            None,
        )
        assert library_button is not None
        library_button.activated.emit()
        mini = window.findChild(QObject, "miniPlayer")
        assert until(lambda: mini.property("visible") and bridge.selection == "Library")
        playing_position = player().property("position")
        assert until(lambda: player().property("position") > playing_position + 200)
        drag_from = mini.mapToScene(QPointF(135, 90)).toPoint()
        QTest.mousePress(window, Qt.LeftButton, pos=drag_from)
        for step in range(1, 11):
            QTest.mouseMove(
                window,
                QPoint(
                    round(drag_from.x() + (110 - drag_from.x()) * step / 10),
                    round(drag_from.y() + (110 - drag_from.y()) * step / 10),
                ),
            )
            app.processEvents()
        QTest.mouseRelease(window, Qt.LeftButton, pos=QPoint(110, 110))
        app.processEvents()
        assert window.property("miniPlayerCorner") == 0, (
            mini.x(),
            mini.y(),
            mini.property("visible"),
        )
        assert abs(mini.x() - 16) < 1 and abs(mini.y() - 62) < 1
        QTest.mouseMove(window, mini.mapToScene(QPointF(30, 24)).toPoint())
        assert until(
            lambda: window.findChild(QObject, "miniPlayerPause").property("visible")
        )
        window.findChild(QObject, "miniPlayerPause").activated.emit()
        assert until(
            lambda: player().property("playbackState") == QMediaPlayer.PausedState
        )
        saved_position = player().property("position")
        QTest.mouseClick(
            window, Qt.LeftButton, pos=mini.mapToScene(QPointF(130, 95)).toPoint()
        )
        assert until(lambda: not mini.property("visible") and scene.property("visible"))
        assert abs(player().property("position") - saved_position) < 600
        library_button.activated.emit()
        assert until(lambda: bridge.playbackUrl.isEmpty())
        assert bridge.selection == "Library"
        assert bridge.openLibraryItem(0)
        assert until(
            lambda: (
                window.property("mediaPlayer").property("position")
                >= saved_position - 600
            )
        )
        assert until(
            lambda: player().property("playbackState") == QMediaPlayer.PlayingState
        )
        scene.closeRequested.emit()
        assert until(
            lambda: (
                mini.property("visible")
                and bridge.selection == "Library"
                and bridge.libraryScene["route"] == "home"
            )
        )
        window.findChild(QObject, "miniPlayerClose").activated.emit()
        assert until(
            lambda: bridge.playbackUrl.isEmpty() and not mini.property("visible")
        )
        assert bridge.selection == "Library"
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_closing_mini_player_keeps_visible_watch_home_projection(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    first = saved(tmp_path, "A First", "MP4")
    playing = saved(tmp_path, "Z Played", "MP4")
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [first, playing]
    progress = bridge._playback_progress
    session = progress.begin(playing)
    assert progress.observe(session, PlaybackSnapshot(None, "Playing", 2, 255, 50))
    assert progress.retire(session)
    bridge.selectHome("Watch")
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    bridge._window = window
    try:
        scene = window.findChild(QObject, "watchBrowseScene")
        for _ in range(5):
            app.processEvents()
        assert scene.property("projection")["hero"]["title"] == "Z Played"

        # Playback can advance after Watch's home projection was painted.
        # Closing the mini player must not pick another hero from that new
        # progress snapshot or reset the page the viewer is looking at.
        bridge._playback_url = QUrl.fromLocalFile(str(tmp_path / "Z Played.mp4"))
        bridge.playbackUrlChanged.emit()
        window.setProperty("miniPlayerActive", True)
        for _ in range(5):
            app.processEvents()
        assert window.findChild(QObject, "miniPlayer").property("visible")
        session = progress.begin(playing)
        assert progress.observe(session, PlaybackSnapshot(None, "Ended", 255, 255, 50))
        assert progress.retire(session)
        assert bridge.watchScene["hero"]["title"] == "A First"
        assert scene.property("projection")["hero"]["title"] == "Z Played"

        window.findChild(QObject, "miniPlayerClose").activated.emit()
        for _ in range(5):
            app.processEvents()
        assert bridge.playbackUrl.isEmpty()
        assert bridge.selection == "Watch"
        assert scene.property("route") == "home"
        assert scene.property("projection")["hero"]["title"] == "Z Played"
        bridge.historyChanged.emit()
        app.processEvents()
        assert scene.property("projection")["hero"]["title"] == "A First"
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_player_related_side_and_recent_artwork_rail_follow_later_design(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [saved(tmp_path, str(index), "MP4") for index in range(3)]
    for index in range(3):
        (tmp_path / f"{index}.mp4").write_bytes(b"fixture")
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    bridge._window = window
    try:
        assert bridge.openLibraryItem(0)
        side = window.findChild(QObject, "playerRelatedSide")
        compact = window.findChild(QObject, "playerRelatedCompact")
        recent = window.findChild(QObject, "playerRecentRail")
        stage = window.findChild(QObject, "playerMediaStage")
        stage_column = window.findChild(QObject, "playerStageColumn")
        assert window.findChild(QObject, "watchMoments") is None
        for width, height, side_visible in (
            (1280, 800, True),
            (1920, 1080, True),
            (820, 560, False),
        ):
            window.resize(width, height)
            for _ in range(5):
                app.processEvents()
            assert side.property("visible") is side_visible
            assert compact.property("visible") is not side_visible
            assert recent.property("visible") is True
            assert len(bridge.playerScene["recent"]) == 3
            assert len(bridge.playerScene["upNext"]) == 2
            if side_visible:
                # The recommendation column stays next to the bounded video
                # instead of inheriting unused width from the viewport.
                gap = side.x() - (stage_column.x() + stage.x() + stage.width())
                assert 15 <= gap <= 40
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_player_caption_track_uses_shared_controls_and_safe_fit(
    tmp_path, monkeypatch
):
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("FFmpeg is needed for an actual subtitle track")
    subtitles = tmp_path / "captions.srt"
    subtitles.write_text("1\n00:00:00,000 --> 00:00:02,000\nCaption proof\n")
    media = tmp_path / "captions.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:r=10:d=3",
            "-i",
            str(subtitles),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:s",
            "mov_text",
            "-shortest",
            str(media),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        player = window.findChild(QMediaPlayer, "watchMediaPlayer")
        scene = window.findChild(QObject, "watchPlayerScene")
        player.setSource(QUrl.fromLocalFile(str(media)))
        deadline = time.monotonic() + 5
        while len(player.subtitleTracks()) < 1 and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.02)
        assert len(player.subtitleTracks()) == 1
        bridge._playback_url = QUrl.fromLocalFile(str(media))
        bridge.playbackUrlChanged.emit()
        bridge.select("Watch")
        app.processEvents()
        scene.setProperty("videoFill", True)
        window.findChild(QObject, "playerCaptionsButton").activated.emit()
        app.processEvents()
        popup = window.findChild(QObject, "playerCaptionsMenu")
        assert popup.property("visible")
        repeaters = [
            item
            for item in popup.findChildren(QObject)
            if item.metaObject().className().startswith("QQuickRepeater")
        ]
        assert len(repeaters) == 1
        controls = {
            item.property("label"): item
            for item in [
                *popup.findChildren(QObject),
                *repeaters[0].parent().childItems(),
            ]
            if item.property("label") is not None
        }
        track_label = next(
            label
            for label in controls
            if str(label).endswith("Track 1") or label == "Caption track 1"
        )
        controls[track_label].activated.emit()
        app.processEvents()
        assert player.activeSubtitleTrack() == 0
        assert not scene.property("videoFill")
        player.play()
        caption = window.findChild(QObject, "embeddedCaptionText")
        deadline = time.monotonic() + 4
        while (
            caption.property("text") != "Caption proof" and time.monotonic() < deadline
        ):
            app.processEvents()
            time.sleep(0.02)
        assert caption.property("text") == "Caption proof"
        player.pause()
        window.findChild(QObject, "playerFillButton").activated.emit()
        assert not scene.property("videoFill")
        controls["Captions off"].activated.emit()
        app.processEvents()
        assert player.activeSubtitleTrack() == -1
        assert scene.property("videoFill")
        scene.setProperty("presentationMode", "floating")
        app.processEvents()
        window.findChild(QObject, "presentationCaptionsButton").activated.emit()
        app.processEvents()
        presentation_menu = window.findChild(QObject, "presentationCaptionsMenu")
        assert presentation_menu.property("visible")
        repeater = next(
            item
            for item in presentation_menu.findChildren(QObject)
            if item.metaObject().className().startswith("QQuickRepeater")
        )
        track = next(
            item
            for item in repeater.parent().childItems()
            if str(item.property("label")).endswith("Track 1")
            or item.property("label") == "Caption track 1"
        )
        track.activated.emit()
        player.setPosition(0)
        player.play()
        presentation_caption = window.findChild(QObject, "presentationCaptionText")
        deadline = time.monotonic() + 4
        while (
            presentation_caption.property("text") != "Caption proof"
            and time.monotonic() < deadline
        ):
            app.processEvents()
            time.sleep(0.02)
        assert presentation_caption.property("text") == "Caption proof"
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_bridge_close_stops_polling_and_commits_pending_preferences(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge.setQuality("720p HD")
    assert bridge._timer.isActive() and bridge._save_timer.isActive()
    bridge.close()
    assert not bridge._timer.isActive() and not bridge._save_timer.isActive()
    assert qt_main.load_settings(bridge._settings_path)["quality"] == "720p HD"
    monkeypatch.setattr(bridge._runtime, "poll", lambda: 1 / 0)
    app.processEvents()
    bridge._pump()
    bridge.close()


def test_qt_routes_keep_tk_channel_playlist_collection_and_media_membership(tmp_path):
    records = [
        saved(tmp_path, "Video A", "MP4", category="Travel"),
        saved(tmp_path, "Audio B", "MP3"),
    ]
    homepage = library_scene(records, "home")
    assert homepage["counts"] == {
        "all": 2,
        "channels": 1,
        "playlists": 1,
        "videos": 1,
        "audio": 1,
    }
    assert [row["title"] for row in library_scene(records, "videos")["media"]] == [
        "Video A"
    ]
    assert [row["title"] for row in library_scene(records, "audio")["media"]] == [
        "Audio B"
    ]
    assert [
        row["title"]
        for row in library_scene(records, "all", query="video travel")["media"]
    ] == ["Video A"]
    assert [
        row["title"]
        for row in library_scene(records, "all", category="Travel")["media"]
    ] == ["Video A"]
    assert [
        row["title"] for row in library_scene(records, "all", sort="title")["media"]
    ] == ["Audio B", "Video A"]
    collection = library_scene(records, "collections")["groups"][0]
    assert library_scene(records, "collections", query="travel")["groups"] == [
        collection
    ]
    assert library_scene(records, "collections", query="unknown")["groups"] == []
    selected = library_scene(records, "group", collection["key"], "collection")
    assert selected["groupTitle"] == "Travel"
    assert [row["title"] for row in selected["media"]] == ["Video A"]
    watch = watch_scene(records, "home")
    assert watch["hero"]["title"] == "Audio B"
    assert len(watch["channels"]) == len(watch["playlists"]) == 1
    assert watch["collections"][0]["title"] == "Travel"
    group = watch_scene(
        records,
        "group",
        group_key=watch["collections"][0]["key"],
        group_kind="collection",
    )
    assert group["groupTitle"] == "Travel"
    assert [row["title"] for row in group["videos"]] == ["Video A"]
    assert watch_scene(records, "group", group_key="missing")["videos"] == []
    results = watch_scene(records, "home", query="video a")
    assert results["route"] == "videos"
    assert [row["title"] for row in results["videos"]] == ["Video A"]


def test_qt_watch_group_header_uses_tk_media_summary_and_creator(tmp_path, monkeypatch):
    records = [saved(tmp_path, "Video A", "MP4"), saved(tmp_path, "Audio B", "MP3")]
    home = watch_scene(records, "home")
    playlist = watch_scene(
        records,
        "group",
        group_key=home["playlists"][0]["key"],
        group_kind="playlist",
    )
    channel = watch_scene(
        records,
        "group",
        group_key=home["channels"][0]["key"],
        group_kind="channel",
    )
    assert playlist["groupSubtitle"] == "One channel  ·  2 items saved"
    assert channel["groupCountLabel"] == "2 items  ·  1 playlist"
    profile_channel = watch_scene(
        records,
        "group",
        group_key=home["channels"][0]["key"],
        group_kind="channel",
        channel_profile=lambda _record: {"description": "Saved channel profile"},
    )
    assert profile_channel["groupDescription"] == "Saved channel profile"
    for record in records:
        record["channel_description"] = "Direct description"
    direct_channel = watch_scene(
        records,
        "group",
        group_key=home["channels"][0]["key"],
        group_kind="channel",
        channel_profile=lambda _record: {"description": "Saved channel profile"},
    )
    assert direct_channel["groupDescription"] == "Direct description"
    for record in records:
        record.pop("channel_description")

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = records
    monkeypatch.setattr(
        bridge._artwork,
        "channel_profile",
        lambda _record: {"description": "Saved channel profile"},
    )
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.select("Watch")
        bridge.navigateWatchGroup("playlist", home["playlists"][0]["key"])
        app.processEvents()
        assert (
            window.findChild(QObject, "watchGroupDescription").property("text")
            == playlist["groupSubtitle"]
        )
        bridge.navigateWatchGroup("channel", home["channels"][0]["key"])
        app.processEvents()
        assert (
            window.findChild(QObject, "watchGroupCountLabel").property("text")
            == channel["groupCountLabel"]
        )
        assert (
            window.findChild(QObject, "watchGroupDescription").property("text")
            == "Saved channel profile"
        )
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_watch_uses_shared_variant_identity_and_playback_preference(tmp_path):
    mp3 = saved(tmp_path, "One source", "MP3")
    mp4 = saved(tmp_path, "One source", "MP4")
    mp3["id"] = mp4["id"] = "same-source"
    scene = watch_scene([mp3, mp4], "home")
    assert len(scene["videos"]) == 1
    assert scene["hero"]["type"] == "MP4"


def test_qt_watch_hero_uses_saved_progress_and_role_specific_artwork(tmp_path):
    records = [saved(tmp_path, "First", "MP4"), saved(tmp_path, "Second", "MP4")]
    artwork_calls = []

    def artwork(record, size, role):
        artwork_calls.append((record["title"], size, role))
        return f"{record['title']}-{role}"

    scene = watch_scene(
        records,
        "home",
        artwork=artwork,
        progress_for=lambda record: (
            WatchedProgress(3, 10, 1) if record["title"] == "Second" else None
        ),
    )
    assert scene["hero"]["title"] == "Second"
    assert scene["hero"]["resume"] is True
    assert scene["hero"]["progress"] == 0.3
    assert scene["hero"]["backdrop"] == "Second-media"
    assert ("Second", (320, 180), "media") in artwork_calls
    assert ("Second", (1100, 400), "media") not in artwork_calls
    assert ("First", (160, 160), "avatar") in artwork_calls
    group = watch_scene(
        records, "group", artwork, scene["channels"][0]["key"], "channel"
    )
    assert group["groupAvatar"] == "First-avatar"
    assert group["groupBanner"] == "First-banner"


@pytest.mark.parametrize("direction", ["backward", "forward"])
def test_transport_arrow_and_arc_have_one_connected_silhouette(
    tmp_path, monkeypatch, direction
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    component = QQmlComponent(engine)
    component.setData(
        b'import QtQuick\nRectangle { width: 96; height: 96; color: "black"; '
        b'SceneIcon { objectName: "transportIcon"; anchors.fill: parent; tone: "white" } }',
        QUrl.fromLocalFile(str(Path(qt_main.__file__).with_name("TransportProbe.qml"))),
    )
    probe = component.create()
    try:
        assert probe is not None, component.errorString()
        probe.setParentItem(window.contentItem())
        icon = probe.findChild(QObject, "transportIcon")
        icon.setProperty("name", direction)
        QTest.qWait(150)
        frame = window.grabWindow()
        scale = frame.devicePixelRatio()
        side = round(96 * scale)
        # Ignore the readable central numeral. Every remaining stroke must
        # belong to the same arrow/arc silhouette, not a detached corner.
        pixels = {
            (x, y)
            for x in range(side)
            for y in range(side)
            if frame.pixelColor(x, y).lightness() > 180
            and not (0.28 * side < x < 0.72 * side and 0.38 * side < y < 0.77 * side)
        }
        assert pixels
        components = []
        while pixels:
            pending = [pixels.pop()]
            connected = set(pending)
            while pending:
                x, y = pending.pop()
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        neighbour = (x + dx, y + dy)
                        if neighbour in pixels:
                            pixels.remove(neighbour)
                            connected.add(neighbour)
                            pending.append(neighbour)
            components.append(connected)
        assert len(components) == 1, [len(part) for part in components]
        shape = components[0]
        assert max(x for x, _y in shape) - min(x for x, _y in shape) > side * 0.65
        assert max(y for _x, y in shape) - min(y for _x, y in shape) > side * 0.8
    finally:
        if probe is not None:
            probe.deleteLater()
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


@pytest.mark.parametrize("hidden", [False, True])
def test_retained_watch_hero_tracks_observed_replay_without_rebuilding_rails(
    tmp_path, monkeypatch, hidden
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    first = saved(tmp_path, "A First", "MP4")
    record = saved(tmp_path, "Z Played", "MP4")
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [first, record]
    progress = bridge._playback_progress
    session = progress.begin(record)
    assert progress.observe(session, PlaybackSnapshot(None, "Paused", 246, 255, 80))
    assert progress.retire(session)
    bridge.selectHome("Watch")
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        scene = window.findChild(QObject, "watchBrowseScene")
        app.processEvents()
        projection = scene.property("projection")
        assert projection["hero"]["title"] == "Z Played"
        rail = window.findChild(QObject, "watchHomeRail_playlists")
        label = window.findChild(QObject, "watchHeroProgressLabel")
        assert label is not None
        assert label.property("text") == "4:06 / 4:15"
        bridge._playback_path = tmp_path / "Z Played.mp4"
        bridge._playback_record = record
        bridge._playback_generation = 7
        bridge._playback_binding = PlaybackProgressBinding(
            progress,
            record,
            snapshot=bridge._playback_snapshot(),
            seek=bridge._request_playback_seek,
        )
        if hidden:
            scene.setProperty("visible", False)
        # A provider-confirmed resume, natural end and deliberate replay must
        # update the retained hero, without choosing a different item/rail.
        bridge.observePlayback(0, 255, "Playing", bridge._playback_generation)
        bridge.observePlayback(246, 255, "Playing", bridge._playback_generation)
        bridge.observePlayback(255, 255, "Ended", bridge._playback_generation)
        app.processEvents()
        assert not scene.property("heroProgress")["resume"]
        assert label.property("text") == ""
        bridge.manualPlaybackSeek(0)
        bridge.observePlayback(0, 255, "Playing", bridge._playback_generation)
        assert label.property("text") == ""
        bridge.observePlayback(14, 255, "Playing", bridge._playback_generation)
        bridge.observePlayback(14, 255, "Paused", bridge._playback_generation)
        if hidden:
            scene.setProperty("visible", True)
        app.processEvents()
        assert label.property("text") == "0:14 / 4:15"
        assert scene.property("projection") == projection
        assert window.findChild(QObject, "watchHomeRail_playlists") is rail
        # Retired generations cannot overwrite a later replay position.
        bridge.observePlayback(246, 255, "Playing", bridge._playback_generation - 1)
        app.processEvents()
        assert label.property("text") == "0:14 / 4:15"
        bridge.closePlayback(True)
        reopened = PlaybackProgressOwner(progress.path)
        reopened.load()
        assert reopened.for_record(record).position == 14
        assert not reopened.for_record(record).completed
        assert scene.property("projection") == projection
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_artwork_reuses_shared_owner_and_publishes_only_completed_local_asset(
    tmp_path, monkeypatch
):
    from PIL import Image

    output = tmp_path / "media.mp4"
    output.write_bytes(b"media fixture")
    image = tmp_path / "thumb.jpg"
    Image.new("RGB", (320, 180), "#7197b8").save(image)
    calls = []

    def resolve(record, size, role, cancelled):
        calls.append((record["title"], size, role, cancelled.is_set()))
        return ArtworkAsset(image, "thumbnail")

    owner = QtArtwork(tmp_path / "cache")
    monkeypatch.setattr(owner._source, "resolve_asset", resolve)
    record = saved(tmp_path, "Media", "MP4")
    record["vodforge_output_path"] = str(output)
    try:
        assert owner.request(record) == ""
        deadline = time.monotonic() + 2
        while not owner.poll() and time.monotonic() < deadline:
            time.sleep(0.005)
        assert owner.request(record).startswith("file:")
        assert calls == [("Media", (320, 180), "media", False)]
        assert owner.request(record) == owner.request(record)
        assert owner.request(record, (160, 160), "avatar") == ""
        deadline = time.monotonic() + 2
        while not owner.poll() and time.monotonic() < deadline:
            time.sleep(0.005)
        assert owner.request(record, (160, 160), "avatar").startswith("file:")
        assert calls[-1] == ("Media", (160, 160), "avatar", False)
    finally:
        owner.close()


def test_qt_artwork_close_retires_blocked_file_io_without_process_shutdown_wait(
    tmp_path, monkeypatch
):
    started = threading.Event()
    release = threading.Event()
    called = []
    owner = QtArtwork(tmp_path / "cache")

    def resolve(record, _size, _role, _cancelled):
        called.append(record["title"])
        started.set()
        release.wait(timeout=2)

    monkeypatch.setattr(owner._source, "resolve_asset", resolve)
    try:
        assert owner._owner._thread.daemon
        owner.request(saved(tmp_path, "First", "MP4"))
        assert started.wait(timeout=1)
        owner.request(saved(tmp_path, "Second", "MP4"))
        begun = time.monotonic()
        owner.close()
        assert time.monotonic() - begun < 0.2
        assert owner.poll() is False
        assert owner.request(saved(tmp_path, "Third", "MP4")) == ""
    finally:
        release.set()
    assert called == ["First"]


def test_qt_private_cached_art_survives_blocked_artwork_lane(tmp_path, monkeypatch):
    from PIL import Image

    blocked = threading.Event()
    release = threading.Event()
    owner = QtArtwork(tmp_path / "artwork")
    first = saved(tmp_path, "Uncached media", "MP4")
    second = saved(tmp_path, "Cached media", "MP4")
    path = cached_thumbnail_path(second, data_dir=tmp_path)
    assert path is not None
    path.parent.mkdir(parents=True)
    Image.new("RGB", (640, 360), "#7197b8").save(path)
    from yt_downloader.qt_quick.artwork import circular_avatar_asset

    assert circular_avatar_asset(path, owner._source.cache_dir / "avatars", (160, 160))

    def resolve(record, _size, _role, _cancelled):
        if record["id"] == first["id"]:
            blocked.set()
            release.wait(timeout=2)

    monkeypatch.setattr(owner._source, "resolve_asset", resolve)
    try:
        assert owner.request(first) == ""
        assert blocked.wait(timeout=1)
        for role, size in (
            ("media", (320, 180)),
            ("playlist", (480, 200)),
            ("avatar", (160, 160)),
        ):
            url = owner.request(second, size, role)
            rendered = Path(QUrl(url).toLocalFile())
            if role == "avatar":
                assert rendered != path
                with Image.open(rendered) as avatar:
                    assert avatar.getpixel((0, 0))[3] == 0
                    assert avatar.getpixel((80, 80))[3] > 0
            else:
                assert rendered == path
        assert owner.poll() is False
    finally:
        owner.close()
        release.set()


def test_qt_first_avatar_transform_runs_in_artwork_worker(tmp_path, monkeypatch):
    from PIL import Image

    owner = QtArtwork(tmp_path / "artwork")
    record = saved(tmp_path, "New channel", "MP4")
    image = tmp_path / "thumbnail.jpg"
    Image.new("RGB", (640, 360), "#7197b8").save(image)
    record["preview_thumbnail_path"] = str(image)
    started = threading.Event()
    release = threading.Event()
    ui_thread = threading.get_ident()

    def avatar(_source, _cache_dir, _size):
        assert threading.get_ident() != ui_thread
        started.set()
        release.wait(timeout=2)

    monkeypatch.setattr(
        owner._source, "resolve_asset", lambda *_args: ArtworkAsset(image, "thumbnail")
    )
    monkeypatch.setattr("yt_downloader.qt_quick.artwork.circular_avatar_asset", avatar)
    try:
        assert owner.request(record, (160, 160), "avatar") == ""
        assert started.wait(timeout=1)
        assert (
            owner.state(history_archive_owner(record), (160, 160), "avatar")
            == "pending"
        )
        release.set()
        deadline = time.monotonic() + 2
        while owner._pending and time.monotonic() < deadline:
            owner.poll()
            time.sleep(0.005)
        assert (
            owner.state(history_archive_owner(record), (160, 160), "avatar")
            == "unavailable"
        )
    finally:
        release.set()
        owner.close()


def test_qt_recent_media_artwork_overtakes_queued_group_artwork(tmp_path, monkeypatch):
    owner = QtArtwork(tmp_path / "artwork")
    started = threading.Event()
    release = threading.Event()
    resolved = []

    def resolve(record, _size, role, _cancelled):
        resolved.append((record["title"], role))
        if record["title"] == "First avatar":
            started.set()
            release.wait(timeout=2)

    monkeypatch.setattr(owner._source, "resolve_asset", resolve)
    try:
        owner.request(saved(tmp_path, "First avatar", "MP4"), (160, 160), "avatar")
        assert started.wait(timeout=1)
        for index in range(1, 12):
            owner.request(
                saved(tmp_path, f"Avatar {index}", "MP4"), (160, 160), "avatar"
            )
        for index in range(4):
            owner.request(saved(tmp_path, f"Recent {index}", "MP4"))
        assert len(owner._pending) == 16
        release.set()
        deadline = time.monotonic() + 3
        while owner._pending and time.monotonic() < deadline:
            owner.poll()
            time.sleep(0.005)
        assert not owner._pending
        assert [role for _, role in resolved[:5]] == [
            "avatar",
            "media",
            "media",
            "media",
            "media",
        ]
    finally:
        release.set()
        owner.close()


def test_qt_artwork_completion_does_not_rebuild_watch_media_projection(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [saved(tmp_path, "Saved", "MP4")]
    bridge.select("Watch")
    seen = []
    bridge.historyChanged.connect(lambda: seen.append("history"))
    bridge.watchSceneChanged.connect(lambda: seen.append("watch"))
    bridge.artworkChanged.connect(lambda: seen.append("artwork"))
    monkeypatch.setattr(bridge._artwork, "poll", lambda: True)
    try:
        bridge._pump()
        assert seen == ["artwork"]
        assert bridge.artworkRevision == 1
    finally:
        bridge.close()


def test_qt_artwork_spinner_waits_for_a_slow_request(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    component = QQmlComponent(
        engine,
        QUrl.fromLocalFile(str(Path(qt_main.__file__).with_name("ArtworkImage.qml"))),
    )
    artwork = component.create()
    try:
        assert artwork is not None, component.errorString()
        artwork.setParentItem(window.contentItem())
        artwork.setWidth(160)
        artwork.setHeight(90)
        spinner = artwork.findChild(QObject, "delayedArtworkSpinner")
        assert spinner is not None
        artwork.setProperty("pending", True)
        app.processEvents()
        assert not spinner.isVisible()
        QTest.qWait(340)
        assert spinner.isVisible()
        artwork.setProperty("pending", False)
        app.processEvents()
        assert not spinner.isVisible()
    finally:
        if artwork is not None:
            artwork.deleteLater()
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_inactive_tabs_skip_scene_projection_on_history_refresh(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [saved(tmp_path, "Saved", "MP4")]
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    calls = {"library": 0, "watch": 0}
    original_library = qt_main.library_scene
    original_watch = qt_main.watch_scene

    def library(*args, **kwargs):
        calls["library"] += 1
        return original_library(*args, **kwargs)

    def watch(*args, **kwargs):
        calls["watch"] += 1
        return original_watch(*args, **kwargs)

    monkeypatch.setattr(qt_main, "library_scene", library)
    monkeypatch.setattr(qt_main, "watch_scene", watch)
    try:
        bridge.select("Library")
        app.processEvents()
        calls["library"] = calls["watch"] = 0
        bridge.historyChanged.emit()
        app.processEvents()
        assert calls["library"] > 0
        assert calls["watch"] == 0

        bridge.select("Watch")
        app.processEvents()
        calls["library"] = calls["watch"] = 0
        bridge.historyChanged.emit()
        app.processEvents()
        assert calls["watch"] > 0
        assert calls["library"] == 0
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_artwork_owner_lookup_reuses_snapshot_until_history_changes(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    records = [saved(tmp_path, f"Video {index}", "MP4") for index in range(200)]
    bridge._runtime.history = records
    original = qt_main.history_archive_owner
    owners = [original(record) for record in records[:40]]
    owner_calls = []

    def counted(record):
        owner_calls.append(record)
        return original(record)

    monkeypatch.setattr(qt_main, "history_archive_owner", counted)
    monkeypatch.setattr(bridge._artwork, "request", lambda *_args: "")
    try:
        for owner in owners:
            bridge.mediaArtwork(owner)
        assert len(owner_calls) == 200
        records[0] = saved(tmp_path, "Replacement", "MP4")
        bridge.historyChanged.emit()
        assert bridge.mediaArtwork(owners[0]) == ""
        assert len(owner_calls) == 400
    finally:
        bridge.close()


def test_qt_artwork_reads_existing_shared_thumbnail_cache(tmp_path, monkeypatch):
    image = tmp_path / "cached.jpeg"
    image.write_bytes(b"cached image")
    monkeypatch.setattr(
        "yt_downloader.qt_quick.artwork.existing_cached_thumbnail_path",
        lambda _record, *, data_dir=None: image,
    )
    assert thumbnail_path({"title": "Cached media"}) == image


def test_qt_selected_hero_uses_bounded_shared_thumbnail_fetch(tmp_path, monkeypatch):
    from io import BytesIO

    from PIL import Image

    payload = BytesIO()
    Image.new("RGB", (320, 180), "#7197b8").save(payload, format="JPEG")
    record = {
        "id": "abcdefghijk",
        "title": "Remote media",
        "vodforge_output_type": "MP4",
        "webpage_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "thumbnail": "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg",
    }
    calls = []

    def download(url, *, source_url, timeout_seconds):
        calls.append((url, source_url, timeout_seconds))
        return payload.getvalue()

    monkeypatch.setattr(
        "yt_downloader.qt_quick.artwork.download_bounded_url_bytes", download
    )
    owner = QtArtwork(tmp_path / "artwork")
    monkeypatch.setattr(owner._source, "resolve_asset", lambda *_args: None)
    try:
        assert owner.request(record, role="media") == ""
        deadline = time.monotonic() + 2
        while owner._pending and time.monotonic() < deadline:
            owner.poll()
            time.sleep(0.005)
        assert calls == []
        assert owner.request(record, (304, 171), "hero") == ""
        deadline = time.monotonic() + 2
        while not owner.poll() and time.monotonic() < deadline:
            time.sleep(0.005)
        cached = Path(QUrl(owner.request(record, (304, 171), "hero")).toLocalFile())
        assert cached.is_file()
        assert cached.parent == tmp_path / "thumbnail-cache"
        assert calls == [(record["thumbnail"], record["webpage_url"], 15)]
    finally:
        owner.close()


def test_qt_import_uses_shared_inspection_and_commits_before_reporting_success(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    source = tmp_path / "my-media.mp4"
    source.write_bytes(b"fixture")
    inspected = []

    def inspect(path, cancelled):
        inspected.append((path, cancelled.is_set()))
        return {
            "id": "local-test",
            "title": "My media",
            "channel": "Local media",
            "vodforge_output_path": str(path),
            "vodforge_output_type": "MP4",
        }

    monkeypatch.setattr(qt_main, "inspect_local_media", inspect)
    bridge = qt_main.Bridge(None)
    try:
        assert bridge.importMedia([QUrl.fromLocalFile(str(source))])
        assert bridge.importBusy
        deadline = time.monotonic() + 2
        while bridge.importBusy and time.monotonic() < deadline:
            app.processEvents()
            bridge._pump()
            time.sleep(0.005)
        assert not bridge.importBusy
        assert inspected == [(source, False)]
        assert bridge._runtime.history[0]["title"] == "My media"
        assert bridge._runtime.history[0]["vodforge_output_dir"] == str(tmp_path)
        assert bridge.status == "Added 1 media file to Library."
    finally:
        bridge.close()


def test_qt_saved_collection_is_visible_through_shared_projection(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    try:
        record = saved(tmp_path, "Saved video", "MP4")
        bridge._runtime.history = [record]
        owner = bridge.collectionCandidates[0]["owner"]
        assert bridge.createCollection("Travel", [owner])
        assert bridge.libraryScene["groups"][0]["title"] == "Travel"
        assert bridge.watchScene["collections"][0]["title"] == "Travel"
        assert bridge.libraryScene["media"][0]["category"] == "Travel"
        bridge.setLibrarySearch("Saved")
        assert bridge.libraryScene["route"] == "all"
        assert bridge.openLibraryDetails(owner)
        assert bridge.libraryScene["route"] == "detail"
        assert bridge.libraryDetail["title"] == "Saved video"
        assert bridge.libraryDetail["category"] == "Travel"
        assert bridge.libraryDetail["source"][0]["label"] == "Channel"
        assert bridge.libraryDetail["output"][0]["label"] == "Saved Filename"
        bridge.returnLibraryDetails()
        assert bridge.libraryScene["route"] == "all"
    finally:
        bridge.close()


def test_qt_organization_records_only_durable_changed_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    try:
        bridge._runtime.history = [saved(tmp_path, "First", "MP4")]
        owner = bridge.collectionCandidates[0]["owner"]
        events = []
        monkeypatch.setattr(
            bridge,
            "_record_update_feature",
            lambda feature, action: events.append((feature, action)),
        )
        assert bridge.openAnnotationOwner(owner)
        assert bridge.saveAnnotation("Private note", "private-tag", "Private category")
        assert events == [
            ("organization", "notes_saved"),
            ("organization", "tags_saved"),
            ("organization", "category_saved"),
        ]
        events.clear()
        assert bridge.saveAnnotation("Private note", "private-tag", "Private category")
        assert events == []
        assert not bridge.createCollection("x" * 121, [owner])
        assert events == []
        original = bridge._annotations.replace
        monkeypatch.setattr(
            bridge._annotations,
            "replace",
            lambda *_: (_ for _ in ()).throw(LibraryAnnotationsError("disk failed")),
        )
        assert not bridge.saveAnnotation("Changed", "private-tag", "Private category")
        assert events == []
        monkeypatch.setattr(bridge._annotations, "replace", original)
        assert bridge.createCollection("Travel", [owner])
        assert events == [("organization", "category_saved")]
    finally:
        bridge.close()


@pytest.mark.parametrize("action", ["cancel", "skip_item", "skip_source"])
@pytest.mark.parametrize(
    "transition", ["same", "successor", "finished", "equal_copy", "stale_at_open"]
)
def test_qt_run_menu_cannot_control_successor_execution(
    tmp_path, monkeypatch, action, transition
):
    from dataclasses import replace

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    try:
        original = make_job(tmp_path)
        bridge._runtime.active_job = original
        record = bridge.runDeck["records"][0]
        calls = []
        observations = []
        monkeypatch.setattr(
            qt_main,
            "operation",
            lambda _owner, feature, outcome, _key, dimensions: observations.append(
                (feature, outcome, dimensions)
            ),
        )
        for method in ("cancel", "skip_item", "skip_source"):
            monkeypatch.setattr(
                bridge._runtime,
                method,
                lambda method=method: calls.append(method),
            )
        if transition == "stale_at_open":
            bridge._runtime.active_job = replace(original)
        admitted = bridge.admitRunMenu(record["runId"], record["executionToken"])
        assert admitted is (transition != "stale_at_open")
        if transition == "successor":
            bridge._runtime.active_job = replace(original, run_id="successor")
        elif transition == "finished":
            bridge._runtime.active_job = None
        elif transition == "equal_copy":
            bridge._runtime.active_job = replace(original)
        assert bridge.controlRun(record["runId"], action) is (transition == "same")
        assert calls == ([action] if transition == "same" else [])
        assert observations == [
            (
                "run_control_operation",
                "admitted" if transition == "same" else "rejected",
                {
                    "run_control_action": action,
                    "run_control_origin": "run_menu",
                    "run_control_owner": "current"
                    if transition == "same"
                    else "retired",
                },
            )
        ]
        assert not bridge.controlRun(record["runId"], action)
        assert calls == ([action] if transition == "same" else [])
    finally:
        bridge.close()


def test_qt_rendered_run_menu_uses_admitted_execution(tmp_path, monkeypatch):
    from dataclasses import replace

    from PySide6.QtQuickControls2 import QQuickStyle

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    QQuickStyle.setStyle("Basic")
    bridge = qt_main.Bridge(None)
    original = make_job(tmp_path)
    bridge._runtime.active_job = original
    engine = qt_main.create_engine(bridge)
    try:
        window = engine.rootObjects()[0]
        app.processEvents()
        deck = window.findChild(QObject, "forgeRunDeck")
        popup = window.findChild(QObject, "runActionsPopup")
        assert deck is not None and popup is not None
        calls = []
        monkeypatch.setattr(bridge._runtime, "cancel", lambda: calls.append("cancel"))
        deck.openActiveActions()
        app.processEvents()
        assert popup.property("visible") is True
        action = visual_item(deck, "runDeckAction_0")
        assert action is not None
        for option in popup.findChildren(QObject):
            if option.property("label") and option.property("visible"):
                assert option.width() == pytest.approx(popup.property("availableWidth"))
        for progress in (10, 22, 35):
            bridge._progress = progress
            bridge._status = f"Downloading media — {progress}%"
            bridge.runDeckChanged.emit()
            app.processEvents()
            assert popup.property("visible") is True
            assert visual_item(deck, "runDeckAction_0") == action
        cancel = next(
            item
            for item in popup.findChildren(QObject)
            if item.property("label") == "Cancel run"
        )
        bridge._runtime.active_job = replace(original)
        cancel.activated.emit()
        app.processEvents()
        assert calls == []
        bridge._runtime.active_job = original
        bridge.runDeckChanged.emit()
        deck.openActiveActions()
        app.processEvents()
        assert popup.property("visible") is True
        cancel.activated.emit()
        app.processEvents()
        assert calls == ["cancel"]
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_saved_owner_actions_remain_in_library_after_work_deck_filter(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    first = saved(tmp_path, "First", "MP4")
    second = saved(tmp_path, "Second", "MP4")
    first["webpage_url"] = "https://www.youtube.com/watch?v=abcdefghijk"
    second["webpage_url"] = "https://www.youtube.com/watch?v=lmnopqrstuv"
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [first, second]
    try:
        owners = [row["owner"] for row in bridge.runDeck["records"]]
        assert len(owners) == 2
        assert bridge.openLibraryDetails(owners[0])
        assert bridge.libraryDetail["owner"] == owners[0]
        assert bridge.copySavedYoutubeUrl(owners[1])
        assert QGuiApplication.clipboard().text() == qt_main.canonical_youtube_url(
            second
        )
        bridge._playback_record = first
        assert bridge.copyPlayerSourceUrl(owners[0])
        assert QGuiApplication.clipboard().text() == first["webpage_url"]
        assert not bridge.copyPlayerSourceUrl(owners[1])
        assert bridge.prepareLibraryRemoval(owners[0])
        assert bridge._pending_library_removal[0] == owners[0]
        bridge.cancelLibraryRemoval()
        bridge._runtime.history = [second]
        assert not bridge.openLibraryDetails(owners[0])
        assert not bridge.copySavedYoutubeUrl(owners[0])
        assert owners[1] == history_archive_owner(second)
    finally:
        bridge.close()


def test_run_deck_keeps_interrupted_run_visible_ahead_of_completed_exports(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [
        saved(tmp_path, f"Completed {index}", "MP4") for index in range(5)
    ]
    stopped = make_job(tmp_path)
    stopped.terminal_status = "Stopped"
    stopped.preview_info = {"title": "Canceled retry"}
    bridge._runtime.recovered = [stopped]
    try:
        bridge._runtime.active_job = stopped

        def finish_cancellation():
            bridge._runtime.active_job = None
            return [("stopped", "Stopped")]

        monkeypatch.setattr(bridge._runtime, "poll", finish_cancellation)
        bridge._pump()
        visible = bridge.runDeck["visible"]
        assert visible[0]["kind"] == "terminal"
        assert visible[0]["status"] == "Stopped"
        assert visible[0]["title"] == "Canceled retry"
    finally:
        bridge.close()


def test_run_deck_requests_artwork_for_each_visible_card_after_sorting(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [
        saved(tmp_path, f"Completed {index}", "MP4") for index in range(5)
    ]
    requests = []

    def artwork(record):
        requests.append(record["title"])
        return "file:///visible-artwork.png"

    monkeypatch.setattr(bridge._artwork, "request", artwork)
    try:
        records = bridge.runDeck["records"]
        assert len(records) == 5
        assert len(requests) == 4
        assert all(record["artwork"] for record in records[:4])
        assert records[4]["artwork"] == ""
    finally:
        bridge.close()


def test_run_deck_visible_artwork_paints_from_a_saved_thumbnail(tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    thumbnail = tmp_path / "thumbnail.png"
    Image.new("RGB", (160, 90), "#40b0dc").save(thumbnail)
    record = saved(tmp_path, "Saved thumbnail", "MP4")
    record["preview_thumbnail_path"] = str(thumbnail)
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [record]
    monkeypatch.setattr(
        bridge._artwork,
        "request",
        lambda *_args, **_kwargs: QUrl.fromLocalFile(str(thumbnail)).toString(),
    )
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        deck = window.findChild(QObject, "forgeRunDeck")
        assert deck is not None
        deadline = time.monotonic() + 3
        artwork = visual_item(deck, "runDeckArtwork_0")
        while artwork is None and time.monotonic() < deadline:
            QTest.qWait(30)
            app.processEvents()
            artwork = visual_item(deck, "runDeckArtwork_0")
        assert artwork is not None
        deadline = time.monotonic() + 3
        while artwork.property("waitingForPaint") and time.monotonic() < deadline:
            QTest.qWait(30)
            app.processEvents()
        assert artwork.property("hasArtwork")
        assert not artwork.property("waitingForPaint")
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_forge_simple_activity_shows_saved_steps_after_completion(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    completed = saved(tmp_path, "Completed video", "MP4")
    completed["vodforge_run_activity"] = [
        "Video 1 of 1: selected format 231+251",
        "Video 1 of 1: downloading",
        "Video 1 of 1: FFmpeg command started (1/1) using CPU libx264",
        "Video 1 of 1: validated output.mp4 before atomic commit",
    ]
    bridge._runtime.history = [completed]
    try:
        friendly = bridge.forgeActivity["friendly"]
        assert "Getting video information" in friendly
        assert "Downloading media" in friendly
        assert "Converting media" in friendly
        assert "Checking the output" in friendly
        assert "Download complete" in friendly
        assert "selected format" not in friendly
    finally:
        bridge.close()


def test_qt_run_selection_drives_forge_snapshot_and_retires_missing_record(
    tmp_path, monkeypatch
):
    from dataclasses import replace

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    active = make_job(tmp_path)
    active.preview_info = {"title": "Active source", "uploader": "Creator"}
    queued = replace(active, run_id="queued-run")
    queued.preview_info = {"title": "Queued source", "uploader": "Second creator"}
    bridge._runtime.active_job = active
    bridge._runtime.queued = [queued]
    engine = qt_main.create_engine(bridge)
    try:
        window = engine.rootObjects()[0]
        app.processEvents()
        title = window.findChild(QObject, "forgeSelectedTitle")
        status = window.findChild(QObject, "forgeSelectedStatus")
        assert title.property("text") == "Active source"
        queued_key = next(
            record["selectionKey"]
            for record in bridge.runDeck["records"]
            if record["runId"] == queued.run_id
        )
        assert bridge.selectRunRecord(queued_key)
        app.processEvents()
        assert title.property("text") == "Queued source"
        assert "Queued" in status.property("text")
        assert bridge.forgeActivity["friendly"] == bridge.forgeSelection["status"]
        facts = {
            row["label"]: row["value"] for row in bridge.forgeSelectedFacts["rows"]
        }
        assert facts["Save to"] == str(queued.output_dir)
        assert facts["Status"] == "Queued"
        assert not bridge.selectRunRecord("missing")
        bridge._runtime.queued = []
        bridge.runDeckChanged.emit()
        bridge.activityChanged.emit()
        app.processEvents()
        assert title.property("text") == "Active source"
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        bridge.close()


def test_qt_forge_and_run_deck_use_shared_terminal_progress_tones(
    tmp_path, monkeypatch
):
    from dataclasses import replace

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    jobs = []
    for status in ("Failed", "Stopped", "Skipped"):
        job = replace(make_job(tmp_path), run_id=f"{status.lower()}-run")
        job.terminal_status = status
        job.preview_info = {"title": f"{status} source"}
        jobs.append(job)
    bridge._runtime.recovered = jobs
    bridge.runDeckChanged.emit()
    engine = qt_main.create_engine(bridge)
    try:
        window = engine.rootObjects()[0]
        app.processEvents()
        label = window.findChild(QObject, "forgeSelectedProgressLabel")
        status_label = window.findChild(QObject, "forgeSelectedStatus")
        track = window.findChild(QObject, "forgeSelectedProgress")
        fill = track.findChild(QObject, "runProgressFill")
        assert track.property("height") == pytest.approx(5)
        assert fill.property("width") == pytest.approx(track.property("width"))
        for job in jobs:
            assert bridge.selectRunRecord(f"terminal:{job.run_id}")
            app.processEvents()
            color = QColor(
                THEME["danger" if job.terminal_status == "Failed" else "warning"]
            )
            assert label.property("text") == job.terminal_status
            assert label.property("color") == color
            assert status_label.property("color") == color
            assert fill.property("color") == color
        deck = window.findChild(QObject, "forgeRunDeck")

        def _visual_items(item):
            yield item
            for child in item.childItems():
                yield from _visual_items(child)

        deck_statuses = [
            item for item in _visual_items(deck) if item.objectName() == "runDeckStatus"
        ]
        assert {
            item.property("text"): item.property("color").name()
            for item in deck_statuses
        } == {
            "Failed": QColor(THEME["danger"]).name(),
            "Stopped": QColor(THEME["warning"]).name(),
            "Skipped": QColor(THEME["warning"]).name(),
        }
        bridge._metadata_preview_record = {
            "runId": "failed-preview",
            "phase": "failed",
            "title": "Preview failed",
            "status": "Could not load this source.",
            "type": "MP4",
        }
        bridge.forgePreviewChanged.emit()
        bridge.runDeckChanged.emit()
        assert bridge.selectRunRecord("preview:failed-preview")
        app.processEvents()
        assert label.property("text") == "Failed"
        assert label.property("color") == QColor(THEME["danger"])
        preview_statuses = [
            item for item in _visual_items(deck) if item.objectName() == "runDeckStatus"
        ]
        assert preview_statuses[0].property("color") == QColor(THEME["danger"])
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        bridge.close()


def test_qt_library_detail_keeps_full_long_description_scrollable(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    record = saved(tmp_path, "Long description", "MP4")
    description = "\n".join(
        f"Chapter {index}: preserve this full description in the detail view."
        for index in range(24)
    )
    record["description"] = description
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [record]
    engine = qt_main.create_engine(bridge)
    try:
        window = engine.rootObjects()[0]
        owner = history_archive_owner(record)
        assert bridge.openLibraryDetails(owner)
        bridge.select("Library")
        for _ in range(5):
            app.processEvents()
        body = window.findChild(QObject, "libraryDescriptionText")
        scroll = window.findChild(QObject, "libraryDescriptionScroll")
        heading = window.findChild(QObject, "libraryDescriptionHeading")
        panel = window.findChild(QObject, "libraryDescriptionPanel")
        assert all(item is not None for item in (body, scroll, heading, panel))
        assert body.property("text") == description
        assert body.property("lineCount") > 4
        assert scroll.property("contentHeight") > scroll.property("height")
        assert heading.property("visible") is True
        assert panel.property("height") >= 180
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        bridge.close()


def test_qt_popup_and_navigation_materials_use_shared_renderer():
    qml_root = Path(qt_main.__file__).parent
    qml_sources = [path.read_text(encoding="utf-8") for path in qml_root.glob("*.qml")]
    assert qml_sources
    assert all("background: Rectangle" not in source for source in qml_sources)
    assert all(
        not re.search(r"(?<!Stone)\b(?:ToolButton|RoundButton|Button)\s*\{", source)
        for source in qml_sources
    )
    for path in qml_root.glob("*.qml"):
        if path.name != "StonePopup.qml":
            assert not re.search(r"(?<!\w)Popup\s*\{", path.read_text(encoding="utf-8"))
    image = qt_main.Materials().requestImage("field/600/600/normal", QSize(), QSize())
    assert (image.width(), image.height()) == (600, 600)


def test_qt_activity_log_uses_existing_private_persistence(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    try:
        bridge._append_activity_line("Current run changed")
        assert "Current run changed" in bridge.activityLog
        assert "Current run changed" in bridge._activity_log_path.read_text(
            encoding="utf-8"
        )
        assert bridge._activity_log_path.is_relative_to(tmp_path)
    finally:
        bridge.close()


def test_qt_watch_queue_advances_only_from_current_playback_generation(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    try:
        records = [saved(tmp_path, "First", "MP4"), saved(tmp_path, "Second", "MP4")]
        for record in records:
            Path(record["vodforge_output_path"]).write_bytes(b"media fixture")
        bridge._runtime.history = records
        bridge.setWatchSearch("First")
        assert bridge.watchScene["route"] == "videos"
        assert [row["title"] for row in bridge.watchScene["videos"]] == ["First"]
        bridge.navigateWatch("playlists")
        assert bridge.watchScene["query"] == ""
        bridge.backWatch()
        assert bridge.watchScene["query"] == "First"
        bridge.navigateWatch("home")
        group = bridge.watchScene["playlists"][0]
        bridge.navigateWatchGroup("playlist", group["key"])
        keys = bridge.watchScene["queueKeys"]
        assert len(keys) == 2
        assert bridge.startWatchQueue(keys, "playlist", False)
        first_generation = bridge._playback_generation
        assert bridge.playbackUrl.toLocalFile().endswith("First.mp4")
        bridge.observePlayback(1, 5, "Playing", first_generation)
        bridge.observePlayback(5, 5, "Ended", first_generation)
        app.processEvents()
        assert bridge.playbackUrl.toLocalFile().endswith("Second.mp4")
        assert bridge._watch_queue.token is not None
        bridge.observePlayback(5, 5, "Ended", first_generation)
        assert bridge._watch_queue.token is not None
        second_generation = bridge._playback_generation
        bridge.observePlayback(1, 5, "Playing", second_generation)
        bridge.observePlayback(5, 5, "Ended", second_generation)
        app.processEvents()
        assert bridge._watch_queue.token is None
    finally:
        bridge.close()


def test_qt_watch_navigation_telemetry_uses_only_closed_dimensions(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)

    class Observer:
        def __init__(self):
            self.events = []

        def record_feature(self, feature, action, *, dimensions=None):
            self.events.append((feature, action, dimensions))

    observer = Observer()
    bridge._analytics.telemetry = observer
    try:
        bridge._runtime.history = [saved(tmp_path, "Private title", "MP4")]
        bridge.select("Watch")
        scene = bridge.watchScene
        group = scene["channels"][0]
        bridge.navigateWatchGroup("channel", group["key"])
        bridge.setWatchSearch("Private title")
        assert ("watch", "opened", None) in observer.events
        assert ("watch", "hero_shown", {"watch_mode": "playlists"}) in observer.events
        assert (
            "watch",
            "channel_opened",
            {"watch_mode": "channels"},
        ) in observer.events
        assert ("watch", "searched", None) in observer.events
        assert "Private title" not in repr(observer.events)
    finally:
        bridge._analytics.telemetry = None
        bridge.close()


def test_qt_library_navigation_telemetry_matches_saved_actions_without_user_text(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)

    class Observer:
        def __init__(self):
            self.events = []

        def record_feature(self, feature, action, *, dimensions=None):
            self.events.append((feature, action, dimensions))

    observer = Observer()
    bridge._analytics.telemetry = observer
    try:
        record = saved(tmp_path, "Private title", "MP4", category="News")
        bridge._runtime.history = [record]
        owner = history_archive_owner(record)
        bridge._annotations.replace(owner, LibraryAnnotation(category="News"))
        bridge.select("Library")
        bridge.select("Library")
        bridge.setLibrarySearch("Private title")
        bridge.setLibrarySearch("")
        bridge.setLibraryType("MP4")
        bridge.setLibraryCategory("News")
        assert bridge.openLibraryDetails(owner)
        assert observer.events == [
            ("library", "opened", None),
            ("library", "searched", None),
            ("library", "filtered", None),
            ("library", "filtered", None),
            ("library", "selected", None),
        ]
        assert "Private title" not in repr(observer.events)
    finally:
        bridge._analytics.telemetry = None
        bridge.close()


def test_qt_missing_media_offer_and_durable_library_removal_are_observed(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)

    class Observer:
        def __init__(self):
            self.events = []

        def record_feature(self, feature, action, *, dimensions=None):
            self.events.append((feature, action, dimensions))

    observer = Observer()
    bridge._analytics.telemetry = observer
    try:
        record = saved(tmp_path, "Private title", "MP4")
        bridge._runtime.history = [record]
        assert not bridge.openLibraryItem(0)
        assert observer.events == [
            ("missing_media", "offered", {"input_kind": "single"})
        ]
        owner = history_archive_owner(record)
        assert bridge.prepareLibraryRemoval(owner)
        assert bridge.confirmLibraryRemoval()
        assert not bridge._runtime.history
        assert observer.events[-1] == ("library", "removed", None)
        assert "Private title" not in repr(observer.events)
    finally:
        bridge._analytics.telemetry = None
        bridge.close()


def test_qt_player_replaces_provider_and_tags_each_open(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        assert window.property("mediaPlayer") is not None
        players = []
        for index in range(2):
            record = saved(tmp_path, f"Item {index}", "MP3")
            media_path = tmp_path / f"Item {index}.wav"
            record["vodforge_output_path"] = str(media_path)
            with wave.open(str(media_path), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(8000)
                audio.writeframes(b"\0\0" * 16_000)
            bridge._runtime.history.append(record)
            assert bridge.openLibraryItem(index)
            app.processEvents()
            player = window.property("mediaPlayer")
            assert player.property("generation") == bridge._playback_generation
            players.append(player)
        assert players[0] is not players[1]
        bridge.observePlayback(5, 5, "Ended", players[0].property("generation"))
        assert bridge._playback_generation == players[1].property("generation")
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_help_form_exposes_only_explicit_recent_failure_context(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    try:
        bridge._latest_failure = FailureContext(
            "Bounded recent failure", "https://www.youtube.com/watch?v=8mv2Gonsdog"
        )
        assert bridge.openSupport("feedback")
        assert bridge.supportContext["diagnostics"] == "Bounded recent failure"
        assert bridge.supportContext["videoUrl"].startswith("https://")
        assert not bridge.submitSupport({"reason": "Other", "message": ""})
        assert bridge.supportStatus == "Please enter a message."
        assert bridge.closeSupport()
        assert bridge.openSupport("review")
        assert bridge.supportContext == {
            "diagnostics": "",
            "videoUrl": "",
            "outputFolder": "",
        }
    finally:
        bridge.close()


def test_qt_all_runs_hover_shows_work_above_button_and_click_toggles(
    tmp_path, monkeypatch
):
    from PySide6.QtQuickControls2 import QQuickStyle
    from PySide6.QtTest import QTest

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    QQuickStyle.setStyle("Basic")
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [saved(tmp_path, "One", "MP4")]
    bridge._runtime.active_job = make_job(tmp_path)
    engine = qt_main.create_engine(bridge)
    try:
        window = engine.rootObjects()[0]
        window.show()
        app.processEvents()
        button = window.findChild(QObject, "allRunsButton")
        popup = window.findChild(QObject, "allRunsPopup")
        popup_hover = window.findChild(QObject, "allRunsPopupHover")
        assert button.isVisible()
        assert button.property("label") == "All 2 runs"
        deck_records = (
            window.findChild(QObject, "forgeRunDeck")
            .property("workRecords")
            .toVariant()
        )
        assert len(deck_records) == 2
        assert deck_records[0]["kind"] == "active"
        assert deck_records[1]["kind"] == "completed"
        assert not popup.property("visible")
        button_top = button.mapToScene(QPointF(0, 0)).y()
        center = button.mapToScene(
            QPointF(button.property("width") / 2, button.property("height") / 2)
        )
        QTest.mouseMove(window, QPoint(round(center.x()), round(center.y())))
        app.processEvents()
        assert popup.property("visible")
        content_item = popup.property("contentItem")
        popup_bottom = content_item.mapToScene(
            QPointF(0, content_item.property("height") + popup.property("padding"))
        ).y()
        assert 8 <= popup_bottom - button_top <= 11
        popup_right = content_item.mapToScene(
            QPointF(content_item.property("width") + popup.property("padding"), 0)
        ).x()
        button_right = button.mapToScene(QPointF(button.property("width"), 0)).x()
        assert abs(popup_right - button_right) <= 1
        popup_point = content_item.mapToScene(
            QPointF(
                content_item.property("width") / 2, content_item.property("height") - 2
            )
        )
        QTest.mouseMove(window, QPoint(round(popup_point.x()), round(popup_point.y())))
        QTest.qWait(250)
        assert popup_hover.property("hovered")
        assert popup.property("visible")
        QTest.mouseMove(window, QPoint(2, 2))
        QTest.qWait(500)
        assert not button.property("hovered")
        assert not popup_hover.property("hovered")
        assert not popup.property("visible")
        button.activated.emit()
        app.processEvents()
        assert bridge.selection == "Forge"
        assert popup.property("visible")
        button.activated.emit()
        app.processEvents()
        assert not popup.property("visible")
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_selected_run_beyond_visible_deck_renders_its_hero_artwork(
    tmp_path, monkeypatch
):
    from PIL import Image
    from PySide6.QtQuickControls2 import QQuickStyle

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    QQuickStyle.setStyle("Basic")
    from dataclasses import replace

    long_title = "Media 4 " + "Very long title " * 8
    image = tmp_path / "selected-thumbnail.jpg"
    Image.new("RGB", (320, 180), "#7197b8").save(image)
    jobs = []
    for index in range(10):
        job = replace(make_job(tmp_path), run_id=f"interrupted-{index}")
        job.terminal_status = "Failed"
        job.preview_info = {
            "id": f"media-{index}",
            "title": long_title if index == 9 else f"Media {index}",
            "preview_thumbnail_path": str(image),
            "duration": 124,
        }
        jobs.append(job)
    bridge = qt_main.Bridge(None)
    bridge._runtime.recovered = jobs
    engine = qt_main.create_engine(bridge)
    try:
        window = engine.rootObjects()[0]
        selection = next(
            row for row in bridge.runDeck["records"] if row["title"] == long_title
        )
        assert selection not in bridge.runDeck["visible"]
        popup = window.findChild(QObject, "allRunsPopup")
        popup.open()
        app.processEvents()
        deck = window.findChild(QObject, "forgeRunDeck")
        popup_top = deck.parentItem().mapToScene(QPointF(0, popup.property("y"))).y()
        trigger_top = (
            window.findChild(QObject, "allRunsButton").mapToScene(QPointF(0, 0)).y()
        )
        assert popup_top >= 0
        assert popup_top + popup.property("height") <= window.height()
        assert popup_top + popup.property("height") <= trigger_top + 12
        scroll = window.findChild(QObject, "allRunsScrollView")
        assert scroll.property("contentHeight") > scroll.property("height")
        assert scroll.setProperty(
            "contentY", scroll.property("contentHeight") - scroll.property("height")
        )
        app.processEvents()
        assert scroll.property("contentY") > 0

        def visual_children(item):
            for child in item.childItems():
                yield child
                yield from visual_children(child)

        choices = [
            item
            for item in visual_children(window.contentItem())
            if isinstance(item.property("displayedRecord"), dict)
            and item.property("displayedRecord").get("selectionKey")
            == selection["selectionKey"]
        ]
        assert len(choices) == 1
        caption = choices[0].findChild(QObject, "runDeckCardTitle")
        assert caption is not None
        assert caption.property("width") <= choices[0].property("width")
        assert caption.property("truncated") is True
        assert (
            choices[0].findChild(QObject, "runDeckStatus").property("text") == "Failed"
        )
        deadline = time.monotonic() + 2
        artwork = choices[0].findChild(QObject, "allRunsArtwork")
        while not artwork.property("source").toString() and time.monotonic() < deadline:
            bridge._artwork.poll()
            bridge.runDeckChanged.emit()
            app.processEvents()
            time.sleep(0.005)
        assert artwork.property("source").toString()
        assert popup.property("visible")
        assert scroll.property("contentY") > 0
        choices[0].chosen.emit()
        app.processEvents()
        assert bridge.forgeSelection["selectionKey"] == selection["selectionKey"]
        title = window.findChild(QObject, "forgeSelectedTitle")
        title_right = title.mapToScene(QPointF(title.property("width"), 0)).x()
        assert title.property("width") >= 200
        assert title_right <= window.width() - 60
        assert title.property("truncated") is True
        deadline = time.monotonic() + 2
        while not bridge.forgeSelection["artwork"] and time.monotonic() < deadline:
            bridge._artwork.poll()
            time.sleep(0.005)
        bridge.runDeckChanged.emit()
        app.processEvents()
        assert bridge.forgeSelection["artwork"].startswith("file:")
        hero = window.findChild(QObject, "forgeHeroArtwork")
        media = window.findChild(QObject, "forgeHeroMediaImage")
        assert hero.property("width") >= 150
        assert media.property("visible") is True
        assert bridge.forgeSelection["duration"] == "2:04"
        badge = window.findChild(QObject, "forgeHeroDurationBadge")
        assert badge.property("visible") is True
        assert Path(media.property("source").toLocalFile()).resolve() == image.resolve()
        settled = QEventLoop()
        QTimer.singleShot(100, settled.quit)
        settled.exec()
        facts_viewport = window.findChild(QObject, "forgeSourceDetailsViewport")
        assert facts_viewport.property("clip") is True
        assert facts_viewport.property("contentHeight") > 0
        details = next(
            item
            for item in window.findChildren(QObject, "forgeSourceDetails")
            if item.isVisible()
        )
        rows = [
            item
            for item in details.childItems()
            if isinstance(item.property("modelData"), dict)
        ]
        assert len(rows) >= 2
        for row in rows:
            label, value = [
                item for item in row.childItems() if item.property("text") is not None
            ][:2]
            assert label.property("x") + label.property("width") <= value.property("x")
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_editorial_projects_all_shared_feature_previews_and_acknowledges(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    source = (
        Path(qt_main.__file__)
        .with_name("FeaturePreview.qml")
        .read_text(encoding="utf-8")
    )
    assert all(f'"{preview.value}"' in source for preview in NativePreview)
    bridge = qt_main.Bridge(None)
    try:
        assert bridge.openWelcomeTour()
        assert bridge.editorialHeading == "Welcome to VODForge"
        assert bridge.editorialFinishLabel == "Start using VODForge"
        assert len(bridge.editorialSlides) == 6
        assert bridge.editorialSlides[0]["preview"] == NativePreview.ACTIVITY.value
        bridge.dismissEditorial(False)
        assert bridge.editorialSlides == []

        class Settled:
            welcome_pending = False
            rating_pending = False

        bridge._engagement = Settled()
        bridge._settings["whats_new_seen"] = ""
        monkeypatch.setattr(qt_main, "SHOWCASE_MODE", "did-you-know")
        bridge.checkEditorial(True)
        assert bridge.editorialHeading == "Did you know?"
        assert bridge.editorialFinishLabel == "Try it"
        assert (
            bridge.editorialSlides[0]["preview"]
            == NativePreview.YOUTUBE_ACCESS_EXPANDED.value
        )
        bridge.dismissEditorial(True)
        assert bridge._settings["whats_new_seen"] == qt_main.SHOWCASE_ID
    finally:
        bridge.close()


def test_qt_editorial_original_audio_menu_and_activity_demo_use_live_controls(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        assert bridge.openWelcomeTour()
        popup = window.findChild(QObject, "editorialPopup")
        popup.open()
        app.processEvents()
        assert popup.property("width") == 490
        assert popup.property("height") == 470
        navigation = popup.findChild(QObject, "editorialSlideNavigation")
        previous = popup.findChild(QObject, "editorialPrevious")
        following = popup.findChild(QObject, "editorialNext")
        assert navigation is not None and previous is not None and following is not None
        assert previous.property("label") == "‹"
        assert following.property("label") == "›"
        assert (
            abs(
                navigation.mapToScene(QPointF()).x()
                + navigation.property("width") / 2
                - window.width() / 2
            )
            < 3
        )
        heading = popup.findChild(QObject, "editorialHeadingRegion")
        assert (
            abs(
                heading.mapToScene(QPointF()).x()
                + heading.property("width") / 2
                - window.width() / 2
            )
            < 3
        )
        popup.setProperty("index", 1)
        app.processEvents()
        exhibit = popup.findChild(QObject, "editorialPreviewRegion")
        title = popup.findChild(QObject, "editorialSlideTitle")
        description = popup.findChild(QObject, "editorialSlideDescription")
        assert exhibit.property("y") + exhibit.property("height") <= title.property("y")
        assert title.property("y") + title.property("height") <= description.property(
            "y"
        )
        preview = window.findChild(QObject, "featurePreview")
        assert preview.property("previewKey") == "original-audio"
        options = next(
            item
            for item in preview.findChildren(QObject)
            if item.metaObject().className().startswith("QQuickRepeater")
            and item.property("model") == ["MP4", "MP3", "Original audio"]
        )
        choices = {item.objectName(): item for item in options.parent().childItems()}
        assert all(
            f"featurePreviewFormatOption_{name}" in choices
            for name in ("MP4", "MP3", "Original_audio")
        )
        choices["featurePreviewFormatOption_MP3"].activated.emit()
        app.processEvents()
        assert preview.property("demoFormat") == "MP3"
        assert (
            window.findChild(QObject, "featurePreviewFormatField").property("label")
            == "MP3  ▾"
        )
        popup.setProperty("index", 0)
        app.processEvents()
        activity = preview.findChild(QObject, "featurePreviewActivityLines")
        assert "[success] Download complete" in activity.property("activityText")
        preview.setProperty("activityStep", 11)
        app.processEvents()

        def visual_descendants(item):
            for child in item.childItems():
                yield child
                yield from visual_descendants(child)

        captions = [
            item
            for item in visual_descendants(activity)
            if item.objectName() == "activityLineCaption"
        ]
        assert captions
        assert (
            max(
                caption.mapToScene(QPointF(0, caption.property("height"))).y()
                for caption in captions
                if caption.property("visible")
            )
            < navigation.mapToScene(QPointF()).y()
        )
        rows = activity.childItems()
        emblems = [
            child
            for row in rows
            for group in row.childItems()
            for child in group.childItems()
            if child.objectName() == "activityLineEmblem"
        ]
        assert any(
            "activity-icon/check" in str(icon.property("source")) for icon in emblems
        )
        for row in activity.childItems():
            nested = [
                child for group in row.childItems() for child in group.childItems()
            ]
            divider = next(
                (item for item in nested if item.objectName() == "activityLineDivider"),
                None,
            )
            emblem = next(
                (item for item in nested if item.objectName() == "activityLineEmblem"),
                None,
            )
            caption = next(
                (
                    item
                    for item in row.childItems()
                    if item.objectName() == "activityLineCaption"
                ),
                None,
            )
            if divider is None:
                continue
            assert divider.property("width") == 1
            assert divider.mapToScene(QPointF()).x() < emblem.mapToScene(QPointF()).x()
            assert emblem.mapToScene(QPointF()).x() < caption.mapToScene(QPointF()).x()
        popup.setProperty("index", 2)
        preview.setProperty("activityStep", 6)
        preview.setProperty("technical", True)
        app.processEvents()
        assert preview.property("previewKey") == "welcome-activity"
        assert "selected format 270+251" in activity.property("activityText")
        sliders = preview.findChildren(QObject, "activityModeSlider")
        assert len(sliders) == 1 and sliders[0].property("technical") is True
        sliders[0].selected.emit(False)
        app.processEvents()
        assert preview.property("technical") is False
        popup.setProperty("index", 3)
        app.processEvents()
        library_fields = preview.findChild(QObject, "featurePreviewLibraryFields")
        category = preview.findChild(QObject, "featurePreviewCategory")
        tags = preview.findChild(QObject, "featurePreviewTags")
        notes = preview.findChild(QObject, "featurePreviewNotes")
        assert library_fields.isVisible()
        assert category.property("label") == "Travel  ▾"
        assert tags.property("text") == "mountains, quiet, inspiration"
        assert notes.property("text").startswith("A short film")
        assert (
            category.property("height")
            == tags.property("height")
            == notes.property("height")
            == 38
        )
        assert category.mapToScene(QPointF()).y() < tags.mapToScene(QPointF()).y()
        assert tags.mapToScene(QPointF()).y() < notes.mapToScene(QPointF()).y()
        for field in (tags, notes):
            assert (
                field.property("background")
                .metaObject()
                .className()
                .startswith("StoneField")
            )
        category.activated.emit()
        app.processEvents()
        category_menu = preview.findChild(QObject, "featurePreviewCategoryMenu")
        assert category_menu.property("visible") is True
        category_menu.setProperty("visible", False)
        preview.setProperty("previewKey", "local-video")
        app.processEvents()
        assert preview.findChild(QObject, "featurePreviewLocalVideoFields").isVisible()
        assert (
            preview.findChild(QObject, "featurePreviewLocalAudio").property("text")
            == "Choose an MP3 file"
        )
        assert (
            preview.findChild(QObject, "featurePreviewLocalImage").property("text")
            == "Choose a still image"
        )
        assert (
            preview.findChild(QObject, "featurePreviewLocalProfile")
            .property("label")
            .endswith("▾")
        )
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_forge_activity_and_source_details_keep_shared_layout(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        app.processEvents()
        slider = window.findChild(QObject, "forgeActivityModeSlider")
        assert slider is not None
        assert slider.property("width") == 30
        assert slider.property("height") == 116
        activity = window.findChild(QObject, "forgeActivityLines")
        assert "next run" in activity.property("activityText")
        assert any(
            child.objectName() == "activityLineDivider"
            for row in activity.childItems()
            for group in row.childItems()
            for child in group.childItems()
        )
        details = next(
            item
            for item in window.findChildren(QObject, "forgeSourceDetails")
            if item.isVisible()
        )
        assert details.property("appBridge") is not None
        live_pane = window.findChild(QObject, "forgeLivePane")
        source_viewport = window.findChild(QObject, "forgeSourceDetailsViewport")
        divider = window.findChild(QObject, "forgeDetailsDivider")
        assert abs(live_pane.property("width") - source_viewport.property("width")) <= 1
        assert divider.isVisible()
        assert divider.property("width") == 1
        assert divider.property("height") >= 100
        live_right = live_pane.mapToScene(QPointF(live_pane.property("width"), 0)).x()
        divider_left = divider.mapToScene(QPointF()).x()
        source_left = source_viewport.mapToScene(QPointF()).x()
        assert divider_left - live_right >= 12
        assert source_left - (divider_left + divider.property("width")) >= 12
        window.setWidth(1600)
        app.processEvents()
        assert abs(live_pane.property("width") - source_viewport.property("width")) <= 1
        assert details.property("preview") is False
        assert any(
            "Save to" == row.property("modelData").get("label")
            for row in details.childItems()
            if isinstance(row.property("modelData"), dict)
        )
        details.setProperty(
            "selectedFacts",
            {
                "heading": "",
                "rows": [
                    {"label": "Save to", "value": "/very-long-output-directory" * 30}
                ],
            },
        )
        app.processEvents()
        assert (
            source_viewport.property("contentWidth")
            <= source_viewport.property("availableWidth") + 1
        )
        assert source_viewport.property("contentItem").property("contentX") == 0
        save_row = next(
            row
            for row in details.childItems()
            if isinstance(row.property("modelData"), dict)
            and row.property("modelData").get("label") == "Save to"
        )
        assert save_row.property("width") <= details.property("width") + 1
        slider.selected.emit(True)
        app.processEvents()
        assert activity.property("technical") is True
        bridge._forge_technical = "\n".join(
            ["https://example.invalid/watch?token=" + "a" * 500]
            + [f"technical step {index}" for index in range(50)]
        )
        bridge.activityChanged.emit()
        settled = QEventLoop()
        QTimer.singleShot(100, settled.quit)
        settled.exec()
        assert "technical step 49" in activity.property("activityText")
        viewport = window.findChild(QObject, "forgeActivityViewport")
        assert viewport.property("contentHeight") > viewport.property("height")
        assert (
            viewport.property("contentWidth") <= viewport.property("availableWidth") + 1
        )
        assert viewport.property("contentItem").property("contentX") == 0
        window.setWidth(850)
        app.processEvents()
        assert details.isVisible() is False
        assert divider.isVisible() is False
        action = next(
            item
            for item in window.findChildren(QObject)
            if item.property("label") == "Output details" and item.property("visible")
        )
        action.activated.emit()
        app.processEvents()
        assert window.findChild(QObject, "forgeOutputDetailsPopup").property("visible")
        popup_scroll = window.findChild(QObject, "forgeOutputDetailsScroll")
        assert (
            popup_scroll.property("contentWidth")
            <= popup_scroll.property("availableWidth") + 1
        )
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_output_mode_menu_uses_tk_shared_display_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        popup = window.findChild(QObject, "optionsMenu")
        popup.open()
        app.processEvents()
        labels = [option["label"] for option in bridge.exportModeOptions]
        assert labels == EXPORT_MODES
        assert "Strict Compliance" not in labels
        options = next(
            item
            for item in popup.findChildren(QObject)
            if item.metaObject().className().startswith("QQuickRepeater")
            and item.property("model") == bridge.exportModeOptions
        )
        controls = {
            item.property("label"): item
            for item in options.parent().childItems()
            if item.property("label") is not None
        }
        assert list(controls) == labels
        controls["CTV"].activated.emit()
        app.processEvents()
        assert bridge.exportMode == "Auto CBR"
        assert bridge.exportModeLabel == "CTV"
        bridge.setExportMode("Manual Override")
        assert bridge.exportModeLabel == "Custom"
        assert bridge.describeExportMode("Custom")
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_manual_mp4_fields_stay_in_adaptive_settings_columns(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.setOutputFormat("MP4")
        bridge.setExportMode("Manual Override")
        popup = window.findChild(QObject, "downloadSettingsPopup")
        popup.open()
        app.processEvents()
        columns = window.findChild(QObject, "settingsColumns")
        manual = window.findChild(QObject, "settingsManualMp4")
        assert columns.property("columns") == 2
        assert manual.property("visible")
        preset = manual.findChild(QObject, "manualPresetSelector")
        preset_button = manual.findChild(QObject, "manualPresetButton")
        initial_height = preset.property("height")
        preset_button.activated.emit()
        app.processEvents()
        assert preset.property("expanded")
        assert preset.property("height") > initial_height
        assert bridge.manualValues["manual_preset"] == "medium"
        slow = visual_item(preset, "manualPresetSelector_option_slow")
        assert slow is not None
        slow.activated.emit()
        app.processEvents()
        assert bridge.manualValues["manual_preset"] == "slow"
        assert preset.property("expanded")
        preset_button.activated.emit()
        app.processEvents()
        assert not preset.property("expanded")
        window.setWidth(820)
        app.processEvents()
        assert columns.property("columns") == 1
        assert manual.property("visible")
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_settings_fit_minimum_window_and_access_returns_to_settings(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.setOutputFormat("MP4")
        bridge.setExportMode("Manual Override")
        settings = window.findChild(QObject, "downloadSettingsPopup")
        settings.open()
        app.processEvents()
        left = window.findChild(QObject, "settingsLeftColumn")
        right = window.findChild(QObject, "settingsRightColumn")
        assert abs(left.y() - right.y()) < 1
        assert bridge.nvencAvailable is False
        bridge.setDownloadOption("use_nvenc", True)
        assert bridge.downloadOptions["use_nvenc"] is False
        window.setWidth(820)
        window.setHeight(560)
        app.processEvents()
        assert settings.property("x") >= 30
        assert settings.property("y") >= 60
        assert settings.property("y") + settings.property("height") <= window.height()
        access_button = next(
            item
            for item in settings.findChildren(QObject)
            if str(item.property("label") or "").startswith("YouTube access:")
        )
        access_button.activated.emit()
        for _ in range(3):
            app.processEvents()
        access = window.findChild(QObject, "youtubeAccessPopup")
        assert access.property("visible")
        assert not settings.property("visible")
        bridge.setCookieSource("Browser")
        browser_name = bridge.cookieBrowserOptions[0]
        bridge.setCookieBrowser(browser_name)
        assert bridge.cookieSource == "Browser"
        assert bridge.cookieBrowser == browser_name
        done = next(
            item
            for item in access.findChildren(QObject)
            if item.property("label") == "Done"
        )
        done.activated.emit()
        for _ in range(4):
            app.processEvents()
        assert settings.property("visible")
        options = window.findChild(QObject, "optionsMenu")
        assert options.property("modal")
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_library_compact_browse_controls_keep_import_with_other_actions(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        window.setWidth(820)
        bridge.select("Library")
        bridge.navigateLibrary("videos")
        for _ in range(3):
            app.processEvents()
        toolbar = window.findChild(QObject, "libraryBrowseControls")
        search = window.findChild(QObject, "headerSearchInput")
        buttons = {
            item.property("label"): item
            for item in toolbar.childItems()
            if item.property("label") is not None
        }
        assert search.property("visible")
        assert window.findChild(QObject, "libraryBrowseSearchField") is None
        assert buttons["Import Media"].y() == buttons["Select"].y()
        assert buttons["Import Media"].y() == buttons["Filter"].y()
        assert (
            search.mapToItem(None, 0, 0).y()
            < buttons["Import Media"].mapToItem(None, 0, 0).y()
        )
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_header_search_follows_library_and_watch_without_secondary_fields(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [saved(tmp_path, "Ocean one", "MP4")]
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        search = window.findChild(QObject, "headerSearchInput")
        assert window.findChild(QObject, "watchSavedSearch") is None
        assert window.findChild(QObject, "libraryBrowseSearchField") is None
        bridge.selectHome("Library")
        search.forceActiveFocus()
        for index, key in enumerate((Qt.Key_O, Qt.Key_C, Qt.Key_E, Qt.Key_A, Qt.Key_N)):
            QTest.keyClick(window, key)
            if index == 1:
                # The delayed welcome prompt must not take an editor's focus.
                QTest.qWait(800)
                assert window.property("editingText")
                assert not window.findChild(QObject, "editorialPopup").property(
                    "visible"
                )
        app.processEvents()
        assert search.property("text") == "ocean"
        assert bridge.librarySearch == "ocean"
        assert bridge.libraryScene["route"] == "all"
        bridge.select("Watch")
        app.processEvents()
        assert search.property("text") == ""
        search.forceActiveFocus()
        for key in (Qt.Key_O, Qt.Key_C, Qt.Key_E, Qt.Key_A, Qt.Key_N):
            QTest.keyClick(window, key)
        app.processEvents()
        assert search.property("text") == "ocean"
        assert bridge.watchScene["query"] == "ocean"
        bridge.select("Library")
        app.processEvents()
        assert search.property("text") == "ocean"
        assert bridge.librarySearch == "ocean"
        bridge.selectHome("Library")
        app.processEvents()
        assert search.property("text") == ""
        assert bridge.libraryScene["route"] == "home"
        bridge.navigateLibrary("folders")
        bridge.setActiveSearch("ocean")
        assert bridge.libraryScene["route"] == "all"
        bridge.backLibrary()
        assert bridge.libraryScene["route"] == "folders"
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_library_multi_select_presets_collection_from_visible_owners(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [
        dict(saved(tmp_path, "First", "MP4"), vodforge_run_id="first-run"),
        dict(saved(tmp_path, "Second", "MP3"), vodforge_run_id="second-run"),
    ]
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.select("Library")
        bridge.navigateLibrary("all")
        app.processEvents()
        scene = window.findChild(QObject, "libraryBrowseScene")
        window.findChild(QObject, "librarySelectButton").activated.emit()
        assert scene.property("selectionMode") is True
        owners = [item["owner"] for item in bridge.libraryScene["media"]]
        for owner in owners:
            scene.toggleSelection(owner)
        assert scene.property("selectedOwners").toVariant() == owners
        window.findChild(QObject, "librarySelectionActionsButton").activated.emit()
        app.processEvents()
        popup = window.findChild(QObject, "librarySelectionActionsPopup")
        assert popup.property("visible") is True
        options = next(
            item
            for item in popup.findChildren(QObject)
            if item.metaObject().className().startswith("QQuickRepeater")
        )
        collection = next(
            item
            for item in options.parent().childItems()
            if item.property("label") == "Add to Collection…"
        )
        collection.activated.emit()
        app.processEvents()
        picker = window.findChild(QObject, "libraryCollectionTargetPopup")
        assert picker.property("visible") is True
        annotation_owners = ["run:first-run", "run:second-run"]
        assert picker.property("selectedOwners") == annotation_owners
        editor = window.findChild(QObject, "libraryCollectionPopup")
        assert editor.property("visible") is False
        assert bridge.createCollection("Travel", annotation_owners)
        assert all(
            bridge._annotations.annotation_for(owner).category == "Travel"
            for owner in annotation_owners
        )
        bridge.navigateLibrary("videos")
        assert scene.property("selectedOwners").toVariant() == []
        assert scene.property("selectionMode") is False
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_multi_file_action_requires_all_current_owners_and_no_active_playback(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    records = [saved(tmp_path, "First", "MP4"), saved(tmp_path, "Second", "MP3")]
    owners = [history_archive_owner(row) for row in records]
    bridge._runtime.history = records
    destination = tmp_path / "destination"
    destination.mkdir()
    target = QUrl.fromLocalFile(str(destination))
    try:
        assert not bridge.startFileActions("move", [owners[0], "stale-owner"], target)
        assert bridge._files.phase == "idle"
        bridge._playback_path = tmp_path / "First.mp4"
        assert not bridge.startFileActions("move", owners, target)
        assert bridge._files.phase == "idle"
        bridge._playback_path = None
        assert bridge.startFileActions("move", owners, target)
        assert bridge._files.phase == "checking"
    finally:
        bridge.close()


def test_qt_library_home_shows_all_recent_downloads_without_phantom_rows(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [
        saved(tmp_path, f"Item {index}", "MP4") for index in range(9)
    ]
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.select("Library")
        app.processEvents()
        repeater = window.findChild(QObject, "libraryMediaRepeater")
        assert len(bridge.libraryScene["media"]) == 9
        assert repeater.property("count") == 9
        window.setWidth(820)
        app.processEvents()
        assert 0 < repeater.property("count") <= 9
        window.setWidth(1400)
        app.processEvents()
        assert repeater.property("count") == 9
        flow = window.findChild(QObject, "libraryMediaFlow")
        assert flow.property("totalRows") == 2
        assert abs(flow.height() - (2 * flow.property("rowStride") - 14)) < 1
        bridge.navigateLibrary("all")
        app.processEvents()
        assert repeater.property("count") == 9
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_library_sidebar_and_canvas_follow_tk_parent_bounds(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [
        saved(tmp_path, f"Media {index}", "MP4") for index in range(31)
    ]
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.select("Library")
        for width in (820, 1100, 1180):
            window.setWidth(width)
            app.processEvents()
            shell_margin = 12 if width < 960 else 20
            scene = window.findChild(QObject, "libraryBrowseScene")
            sidebar = window.findChild(QObject, "librarySidebar")
            divider = window.findChild(QObject, "librarySidebarDivider")
            viewport = window.findChild(QObject, "libraryViewport")
            buttons = [
                next(
                    item
                    for item in sidebar.childItems()
                    if item.objectName() == "librarySidebarButton_" + route
                )
                for route in ("all", "channels", "playlists", "videos", "audio")
            ]
            assert round(scene.property("x")) == 0
            assert round(scene.property("width")) == width - 2 * shell_margin
            assert round(sidebar.property("x")) == 0
            assert round(sidebar.property("width")) == 226
            assert round(divider.property("x")) == 226
            assert round(viewport.property("x")) == 247
            assert round(viewport.property("width")) == width - 2 * shell_margin - 247
            assert [
                (round(button.property("x")), round(button.property("y")))
                for button in buttons
            ] == [(8, 54 + index * 49) for index in range(5)]
            assert all(round(button.property("width")) == 203 for button in buttons)
            for route, button in zip(
                ("all", "channels", "playlists", "videos", "audio"), buttons
            ):
                icon = next(
                    item
                    for item in button.childItems()
                    if item.objectName() == "librarySidebarIcon_" + route
                )
                assert round(icon.property("x")) == 14
                assert round(icon.property("y")) == 12
                expected_count = {
                    "all": "31",
                    "channels": "1",
                    "playlists": "1",
                    "videos": "31",
                    "audio": "0",
                }[route]
                badge = next(
                    item
                    for item in button.childItems()
                    if item.property("label") == expected_count
                )
                caption = badge.findChild(QObject, "stoneButtonCaption")
                assert (
                    caption.property("width") >= caption.property("implicitWidth") - 1
                )
                assert caption.property("truncated") is False
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_library_empty_panels_match_tk_routes_and_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.select("Library")
        app.processEvents()
        scene = window.findChild(QObject, "libraryBrowseScene")
        collections = window.findChild(QObject, "libraryCollectionsEmptyPanel")
        group_empty = window.findChild(QObject, "libraryGroupEmptyPanel")
        media = window.findChild(QObject, "libraryMediaEmptyPanel")
        see_all = window.findChild(QObject, "libraryCollectionsSeeAll")
        assert collections.property("visible")
        assert media.property("visible")
        assert not see_all.property("visible")
        assert collections.property("collections")
        assert not media.property("filtered")
        assert not media.property("actions")
        assert round(collections.property("height")) == 232
        assert round(media.property("height")) == 188

        imports = []
        scene.importRequested.connect(lambda: imports.append(True))
        collections.findChild(QObject, "libraryEmptyImportMedia").activated.emit()
        assert imports == [True]
        collections.findChild(QObject, "libraryEmptyGoForge").activated.emit()
        assert bridge.selection == "Forge"

        bridge.select("Library")
        bridge.navigateLibrary("channels")
        app.processEvents()
        assert not collections.property("visible")
        assert group_empty.property("visible")
        assert not media.property("visible")
        assert group_empty.property("actions")
        toolbar = window.findChild(QObject, "libraryBrowseControls")
        assert (
            group_empty.mapToItem(scene, 0, 0).y() > toolbar.mapToItem(scene, 0, 0).y()
        )
        assert window.findChild(QObject, "libraryGroupFlow").height() == 0
        bridge.navigateLibrary("playlists")
        app.processEvents()
        assert group_empty.property("visible")
        assert (
            group_empty.mapToItem(scene, 0, 0).y() > toolbar.mapToItem(scene, 0, 0).y()
        )

        bridge._runtime.history = [saved(tmp_path, "One", "MP4", category="News")]
        bridge.historyChanged.emit()
        bridge.navigateLibrary("home")
        app.processEvents()
        assert see_all.property("visible")
        bridge.setLibraryCategory("News")
        bridge.setLibrarySearch("absent")
        bridge.navigateLibrary("all")
        app.processEvents()
        assert not collections.property("visible")
        assert media.property("visible")
        assert media.property("filtered")
        assert media.property("actions")
        media.findChild(QObject, "libraryEmptyClearFilters").activated.emit()
        app.processEvents()
        assert bridge.librarySearch == ""
        assert bridge.libraryCategory == "All categories"
        assert bridge.libraryScene["route"] == "all"
        assert bridge.libraryScene["media"]
        assert not media.property("visible")
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_watch_empty_home_uses_tk_welcome_and_shared_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.select("Watch")
        app.processEvents()
        scene = window.findChild(QObject, "watchBrowseScene")
        empty = window.findChild(QObject, "watchEmptyScene")
        assert scene.property("emptyHome")
        assert empty.property("visible")
        viewport = window.findChild(QObject, "watchViewport")
        assert round(empty.property("width")) == round(
            viewport.property("availableWidth")
        )
        assert round(empty.childItems()[0].property("height")) == 415
        assert empty.findChild(QObject, "watchEmptyTitle").property("text") == (
            "Nothing to watch yet"
        )
        image_size = QSize()
        emblem = qt_main.Materials().requestImage("watch-welcome", image_size, QSize())
        assert (image_size.width(), image_size.height()) == (256, 218)
        assert not emblem.isNull()
        assert not window.grabWindow().isNull()
        empty.findChild(QObject, "watchEmptyOpenLibrary").activated.emit()
        assert bridge.selection == "Library"
        bridge.select("Watch")
        empty.findChild(QObject, "watchEmptyGoForge").activated.emit()
        assert bridge.selection == "Forge"

        bridge._runtime.history = [saved(tmp_path, "One", "MP4")]
        bridge.historyChanged.emit()
        bridge.select("Watch")
        app.processEvents()
        assert not scene.property("emptyHome")
        assert not empty.property("visible")
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_watch_empty_sections_keep_fresh_placeholders_after_a_download(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:

        def descendants(parent):
            for child in parent.childItems():
                yield child
                yield from descendants(child)

        def visual(name):
            return next(
                item
                for item in descendants(window.contentItem())
                if item.objectName() == name
            )

        def placeholder_count(item):
            return sum(
                child.objectName() == "watchPlaceholderCard"
                for child in descendants(item)
            )

        bridge.select("Watch")
        app.processEvents()
        fresh = window.findChild(QObject, "watchEmptyScene")
        fresh_placeholder_count = placeholder_count(fresh)
        assert fresh_placeholder_count > 0
        assert fresh_placeholder_count % 3 == 0

        unfiled = saved(tmp_path, "Unfiled", "MP4")
        unfiled.update(channel="", playlist_id=None, playlist_title=None)
        bridge._runtime.history = [unfiled]
        bridge.historyChanged.emit()
        app.processEvents()
        assert not fresh.property("visible")
        assert len(bridge.watchScene["videos"]) == 1
        assert not bridge.watchScene["playlists"]
        rail = visual("watchHomeRail_playlists")
        button = visual("watchHomeSeeAll_playlists")
        assert rail.property("visible")
        assert placeholder_count(rail) == fresh_placeholder_count // 3
        assert not button.property("enabled")
        assert bridge.watchScene["channels"]
        assert visual("watchHomeSeeAll_channels").property("enabled")
        assert visual("watchHomeSeeAll_videos").property("enabled")

        filed = saved(tmp_path, "Filed", "MP4")
        bridge._runtime.history.append(filed)
        bridge.historyChanged.emit()
        app.processEvents()
        assert bridge.watchScene["playlists"]
        assert placeholder_count(visual("watchHomeRail_playlists")) == 0
        assert visual("watchHomeSeeAll_playlists").property("enabled")
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_shared_header_keeps_navigation_next_to_brand_on_every_tab(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.select("Library")
        for width, height, margin in (
            (820, 560, 12),
            (1025, 700, 20),
            (1100, 740, 20),
            (1180, 790, 20),
        ):
            window.resize(width, height)
            for _ in range(3):
                app.processEvents()
            header = window.findChild(QObject, "focusHeader")
            nav = window.findChild(QObject, "navigationRow")
            brand = window.findChild(QObject, "brandRow")
            search = window.findChild(QObject, "globalSearchField")
            drag_area = window.findChild(QObject, "headerDragArea")
            scene = window.findChild(QObject, "libraryBrowseScene")
            assert (
                round(header.mapToItem(None, 0, 0).x()),
                round(header.mapToItem(None, 0, 0).y()),
            ) == (margin, 5)
            assert round(header.height()) == 44
            assert drag_area.property("width") == pytest.approx(header.width())
            assert drag_area.property("height") == pytest.approx(header.height())
            native_title_inset = 82 if sys.platform == "darwin" else 0
            assert round(brand.mapToItem(None, 0, 0).x()) == margin + native_title_inset
            assert (
                abs(
                    brand.mapToItem(None, 0, brand.height() / 2).y()
                    - header.mapToItem(None, 0, 22).y()
                )
                <= 0.5
            )
            if width >= 960:
                vod = window.findChild(QObject, "brandVodText")
                forge = window.findChild(QObject, "brandForgeText")
                assert vod.property("text") == "VOD"
                assert forge.property("text") == "Forge"
                assert vod.property("color").name() == qt_main.THEME["accent"]
                assert forge.property("color").name() == "#ffffff"
                assert (
                    abs(
                        vod.mapToItem(None, 0, vod.height() / 2).y()
                        - header.mapToItem(None, 0, 22).y()
                    )
                    <= 1
                )
            expected_nav_x = (
                margin
                + native_title_inset
                + (46 if width < 960 else 150)
                + (4 if width < 960 else 3)
            )
            for tab in ("Forge", "Library", "Watch", "Activity"):
                bridge.selectHome(tab)
                app.processEvents()
                assert abs(nav.mapToItem(None, 0, 0).x() - expected_nav_x) < 0.5
                assert round(nav.mapToItem(None, 0, 0).y()) == 5
            bridge.selectHome("Library")
            app.processEvents()
            assert round(nav.mapToItem(None, 0, 0).y()) == 5
            assert (
                search.mapToScene(QPointF(0, 0)).x()
                >= nav.mapToScene(QPointF(nav.width(), 0)).x() + 8
            )
            assert round(scene.mapToItem(None, 0, 0).y()) == 54
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_header_settings_uses_centered_shared_icon(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        for width in (820, 1180):
            window.resize(width, 740)
            for _ in range(3):
                app.processEvents()
            button = window.findChild(QObject, "headerSettingsButton")
            icon = button.findChild(QObject, "stoneButtonIcon")
            caption = button.findChild(QObject, "stoneButtonCaption")
            assert button.property("accessibilityLabel") == "Settings"
            assert not button.property("label")
            assert not caption.property("visible")
            assert "icon/settings.png" in str(icon.property("source"))
            assert (
                abs(
                    icon.mapToItem(button, icon.width() / 2, icon.height() / 2).x()
                    - button.width() / 2
                )
                <= 0.5
            )
            assert (
                abs(
                    icon.mapToItem(button, icon.width() / 2, icon.height() / 2).y()
                    - button.height() / 2
                )
                <= 0.5
            )
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_library_folders_columns_clear_the_header_divider(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.select("Library")
        bridge.navigateLibrary("folders")
        for width, height in ((1100, 740), (820, 560)):
            window.resize(width, height)
            for _ in range(3):
                app.processEvents()
            browser = window.findChild(QObject, "libraryFolderBrowser")
            columns = window.findChild(QObject, "libraryFolderColumns")
            browse = window.findChild(QObject, "libraryFolderBrowseHeading")
            top = window.findChild(QObject, "libraryFolderTopRow")
            inspector = window.findChild(QObject, "libraryFolderInspectorHeading")
            browser_y = browser.mapToItem(None, 0, 0).y()
            assert abs(columns.mapToItem(None, 0, 0).y() - browser_y - 12) <= 1
            assert browse.mapToItem(None, 0, 0).y() >= browser_y + 12
            assert top.mapToItem(None, 0, 0).y() >= browser_y + 12
            assert browser.property("showInspector") == (width >= 920 and height >= 740)
            assert inspector.property("visible") == (width >= 920 and height >= 740)
        back = window.findChild(QObject, "libraryFolderBackButton")
        assert back.property("visible") is True
        assert back.width() == 72
        back.activated.emit()
        assert bridge.libraryScene["route"] == "home"
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_my_files_starts_at_saved_path_without_recent_export_cards(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    record = saved(tmp_path, "Recent export", "MP4")
    Path(record["vodforge_output_path"]).write_bytes(b"video")
    bridge._runtime.history = [record]
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        window.resize(1100, 740)
        bridge.select("Library")
        bridge.navigateLibrary("folders")
        deadline = time.monotonic() + 2
        while bridge.libraryFolders["checkingFolder"] and time.monotonic() < deadline:
            bridge._pump()
            app.processEvents()
            QTest.qWait(10)
        for _ in range(3):
            app.processEvents()
        assert not window.grabWindow().isNull()
        folders = bridge.libraryFolders
        assert folders["path"] == str(tmp_path)
        assert sum(item["kind"] == "media" for item in folders["components"]) == 1
        listing = window.findChild(QObject, "libraryFolderList")
        pending = list(listing.childItems())
        while pending:
            item = pending.pop()
            assert not item.objectName().startswith("libraryRecentExportCard_")
            pending.extend(item.childItems())
        assert window.findChild(QObject, "libraryFolderOpenLocationButton").property(
            "visible"
        )
        inspector = window.findChild(QObject, "libraryFolderInspector")
        assert inspector.property("visible")
        open_button = window.findChild(QObject, "libraryFolderOpenLocationButton")
        assert (
            open_button.mapToItem(None, 0, 0).x() >= inspector.mapToItem(None, 0, 0).x()
        )
        fallback = window.findChild(QObject, "libraryFolderOverviewFallbackIcon")
        assert fallback.property("visible")
        assert fallback.property("name") == "folder-solid"
        assert fallback.property("width") >= 100
        assert not window.findChild(QObject, "libraryFolderArtworkFrame").property(
            "visible"
        )
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_my_files_empty_saved_location_links_to_existing_recovery(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "home"))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    output = tmp_path / "Downloads" / "Artist"
    output.mkdir(parents=True)
    record = saved(output, "Missing song", "MP4")
    record["webpage_url"] = "https://www.youtube.com/watch?v=abcdefghijk"
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [record]
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        window.resize(1100, 740)
        bridge.select("Library")
        bridge.navigateLibraryFolders("folders")
        deadline = time.monotonic() + 2
        while bridge.libraryFolders["checkingFolder"] and time.monotonic() < deadline:
            bridge._pump()
            app.processEvents()
            QTest.qWait(10)
        app.processEvents()
        assert bridge.libraryFolders["count"] == 0
        assert bridge.libraryFolders["unavailableCount"] == 1
        assert bridge.libraryFolderInspector["unavailableCount"] == 1
        button = window.findChild(QObject, "libraryFolderReviewMissingButton")
        deadline = time.monotonic() + 2
        while button is None and time.monotonic() < deadline:
            app.processEvents()
            QTest.qWait(10)
            button = window.findChild(QObject, "libraryFolderReviewMissingButton")
        assert button is not None
        assert button.property("visible")
        button.activated.emit()
        assert bridge.libraryFolders["mode"] == "issues"
        deadline = time.monotonic() + 2
        while (
            bridge.libraryFolders["checkingAvailability"]
            and time.monotonic() < deadline
        ):
            bridge._pump()
            app.processEvents()
            QTest.qWait(10)
        assert any(
            item["kind"] == "missing" for item in bridge.libraryFolders["components"]
        )
        assert bridge.libraryFolderInspector["issue"]
        assert bridge.libraryFolderInspector["missing"]
        assert bridge.libraryFolderInspector["title"] == "Missing song"
        assert window.findChild(QObject, "libraryIssueFindMovedFile").property(
            "visible"
        )
        assert bridge.copyIssueSource()
        assert QGuiApplication.clipboard().text() == qt_main.canonical_youtube_url(
            record
        )
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_my_files_selects_video_thumbnail_and_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "home"))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    output = tmp_path / "Downloads" / "Artist"
    output.mkdir(parents=True)
    record = saved(output, "Song", "MP4")
    Path(record["vodforge_output_path"]).write_bytes(b"video")
    (output / "thumbnail.jpg").write_bytes(b"image")
    (output / "metadata.json").write_text("{}", encoding="utf-8")
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [record]
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        window.resize(1100, 740)
        bridge.select("Library")
        bridge.navigateLibraryFolders("folders")
        deadline = time.monotonic() + 2
        while bridge.libraryFolders["checkingFolder"] and time.monotonic() < deadline:
            bridge._pump()
            app.processEvents()
            QTest.qWait(10)
        components = bridge.libraryFolders["components"]
        assert not bridge.libraryFolders["checkingFolder"]
        assert {row["title"] for row in components} >= {
            "Song",
            "thumbnail.jpg",
            "metadata.json",
        }
        assert not any(row["title"] == "Song.mp4" for row in components)

        video = next(row for row in components if row["kind"] == "media")
        assert bridge.selectLibraryFolderComponent(video["key"])
        assert bridge.libraryFolderInspector["owner"]
        assert window.findChild(QObject, "libraryFolderOpenDetails").property("visible")
        assert window.findChild(QObject, "libraryFolderOpenLocationButton").property(
            "visible"
        )

        thumbnail = next(row for row in components if row["title"] == "thumbnail.jpg")
        assert bridge.selectLibraryFolderComponent(thumbnail["key"])
        assert bridge.libraryFolderInspector["file"]
        assert bridge.libraryFolderInspector["artwork"].startswith("file:")
        fallback = window.findChild(QObject, "libraryFolderOverviewFallbackIcon")
        assert not fallback.property("visible")
        assert window.findChild(QObject, "libraryFolderFileOpenLocation").property(
            "visible"
        )

        metadata = next(row for row in components if row["title"] == "metadata.json")
        assert bridge.selectLibraryFolderComponent(metadata["key"])
        inspector = bridge.libraryFolderInspector
        assert inspector["isMetadata"]
        assert fallback.property("visible")
        assert fallback.property("name") == "file"
        assert bridge.saveSelectedFolderMetadata(
            inspector["associatedOwner"], "Edited description", "sea, music"
        )
        assert bridge.libraryFolderInspector["description"] == "Edited description"
        assert bridge.libraryFolderInspector["tags"] == ["sea", "music"]
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_forge_composer_matches_tk_control_bounds(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        for (
            width,
            height,
            command_x,
            command_y,
            field_width,
            destination_x,
            destination_width,
        ) in (
            (820, 560, 32, 70, 499, 240, 170),
            (1100, 740, 62, 78, 719, 270, 210),
            (1180, 790, 120, 94, 683, 328, 240),
        ):
            window.resize(width, height)
            for _ in range(3):
                app.processEvents()

            def bounds(name):
                item = window.findChild(QObject, name)
                point = item.mapToItem(None, 0, 0)
                return tuple(
                    round(value)
                    for value in (point.x(), point.y(), item.width(), item.height())
                )

            assert bounds("forgeCommandRow") == (
                command_x,
                command_y,
                width - 2 * command_x,
                48,
            )
            assert bounds("forgeUrlField") == (command_x, command_y, field_width, 48)
            assert bounds("forgeOptionsButton") == (
                command_x + field_width + 12,
                command_y + 1,
                106,
                46,
            )
            assert bounds("forgeDownloadButton") == (
                command_x + field_width + 126,
                command_y + 2,
                131,
                44,
            )
            assert bounds("forgeLocalRow") == (
                command_x,
                command_y + 56,
                width - 2 * command_x,
                44,
            )
            assert bounds("forgeLoadListButton") == (command_x, command_y + 56, 131, 44)
            assert bounds("forgeDestinationField") == (
                destination_x,
                command_y + 61,
                destination_width,
                34,
            )
            assert bounds("forgeCreateVideoButton") == (
                width - command_x - 131,
                command_y + 56,
                131,
                44,
            )
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_library_category_tiles_follow_tk_column_and_content_branches(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.select("Library")
        for width, height, columns, compact in (
            (820, 560, 2, False),
            (1100, 740, 4, True),
            (1180, 790, 4, True),
        ):
            window.resize(width, height)
            for _ in range(3):
                app.processEvents()
            flow = window.findChild(QObject, "libraryCategoryFlow")
            cards = [
                item
                for item in flow.childItems()
                if item.objectName().startswith("libraryCategoryTile_")
            ]
            assert flow.property("columns") == columns
            assert len(cards) == 4
            assert all(item.property("compact") is compact for item in cards)
            assert all(round(item.height()) == 106 for item in cards)
            assert all(
                abs(item.width() - flow.property("cardWidth")) < 1 for item in cards
            )
            assert round(cards[1].x() - cards[0].x() - cards[0].width()) == 14
            assert round(cards[2].y()) == (120 if columns == 2 else 0)
        assert not window.grabWindow().isNull()
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_library_all_media_windows_rows_and_artwork_requests(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [
        saved(tmp_path, f"Item {index:03d}", "MP4") for index in range(200)
    ]
    requested = []
    monkeypatch.setattr(
        bridge._artwork,
        "request",
        lambda record, _size=(320, 180), _role="media": (
            requested.append(record["title"]) or ""
        ),
    )
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.select("Library")
        bridge.navigateLibrary("all")
        app.processEvents()
        flow = window.findChild(QObject, "libraryMediaFlow")
        repeater = window.findChild(QObject, "libraryMediaRepeater")
        viewport = window.findChild(QObject, "libraryViewport")
        assert len(bridge.libraryScene["media"]) == 200
        assert repeater.property("count") < 40
        assert len(set(requested)) < 40
        start_requests = set(requested)
        flickable = viewport.property("contentItem")
        # Keep the scroll within the real content range; an out-of-range
        # programmatic offset is clamped when the detail route reflows.
        scroll_target = min(
            50 * flow.property("rowStride"),
            flickable.property("contentHeight") - viewport.height() - 1,
        )
        assert flickable.setProperty("contentY", scroll_target)
        app.processEvents()
        assert flow.property("firstRow") >= 45
        assert repeater.property("count") < 40
        assert len(set(requested) - start_requests) < 40
        assert set(requested) - start_requests
        scroll_before_detail = flickable.property("contentY")
        owner = bridge.libraryScene["media"][150]["owner"]
        assert bridge.openLibraryDetails(owner)
        app.processEvents()
        bridge.returnLibraryDetails()
        app.processEvents()
        assert abs(flickable.property("contentY") - scroll_before_detail) < 1
        assert flow.property("firstRow") >= 45
        assert flickable.setProperty("contentY", 20 * flow.property("rowStride"))
        bridge.setLibrarySort("title")
        app.processEvents()
        assert flickable.property("contentY") == 0
        bridge.navigateLibrary("channels")
        app.processEvents()
        assert flickable.property("contentY") == 0
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_watch_media_windows_cards_and_restores_back_scroll(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [
        saved(tmp_path, f"Video {index:03d}", "MP4") for index in range(200)
    ]
    requested = []
    monkeypatch.setattr(
        bridge._artwork,
        "request",
        lambda record, _size=(320, 180), _role="media": (
            requested.append((record["title"], _size, _role)) or ""
        ),
    )
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.select("Watch")
        bridge.navigateWatch("videos")
        app.processEvents()
        scene = window.findChild(QObject, "watchBrowseScene")
        flow = window.findChild(QObject, "watchMediaFlow")
        repeater = window.findChild(QObject, "watchMediaRepeater")
        viewport = window.findChild(QObject, "watchViewport")
        assert len(bridge.watchScene["videos"]) == 200
        assert repeater.property("count") < 40
        media_requests = {
            title
            for title, size, role in requested
            if size == (320, 180) and role == "media"
        }
        assert len(media_requests) < 40
        flickable = viewport.property("contentItem")
        assert flickable.setProperty("contentY", 40 * flow.property("rowStride"))
        app.processEvents()
        assert flow.property("firstRow") >= 35
        assert repeater.property("count") < 40
        before = flickable.property("contentY")
        group = bridge.watchScene["playlists"][0]
        bridge.navigateWatchGroup("playlist", group["key"])
        app.processEvents()
        scene.back()
        for _ in range(3):
            app.processEvents()
        assert abs(flickable.property("contentY") - before) < 1
        bridge.navigateWatch("home")
        for _ in range(3):
            app.processEvents()
        assert flickable.property("contentY") == 0
        assert repeater.property("count") <= flow.property("columns")
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


@pytest.mark.parametrize(
    "route,role", [("channels", "avatar"), ("playlists", "playlist")]
)
def test_qt_watch_group_routes_window_cards_and_artwork(
    tmp_path, monkeypatch, route, role
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    records = []
    for index in range(200):
        record = saved(tmp_path, f"Channel video {index:03d}", "MP4")
        record["channel"] = f"Channel {index:03d}"
        record["playlist_id"] = f"playlist-{index:03d}"
        record["playlist_title"] = f"Playlist {index:03d}"
        records.append(record)
    bridge._runtime.history = records
    requested = []
    monkeypatch.setattr(
        bridge._artwork,
        "request",
        lambda record, size=(320, 180), role="media": (
            requested.append((record["title"], size, role)) or ""
        ),
    )
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.select("Watch")
        bridge.navigateWatch(route)
        for _ in range(3):
            app.processEvents()
        routes = window.findChild(QObject, "watchGroupRoutesRepeater")
        columns = [
            item
            for item in routes.parent().childItems()
            if item is not routes and item.isVisible()
        ]
        assert len(columns) == 1
        flow = next(
            item
            for item in columns[0].childItems()
            if item.objectName() == "watchGroupFlow"
        )
        repeater = next(
            item
            for item in flow.childItems()
            if item.objectName() == "watchGroupRepeater"
        )
        viewport = window.findChild(QObject, "watchViewport")
        assert len(bridge.watchScene[route]) == 200
        # The Tk-matched 20 px shell gutter admits four columns here;
        # overscanned visible rows therefore reach exactly 40 cards.
        assert repeater.property("count") <= 40
        group_requests = {
            title for title, _size, request_role in requested if request_role == role
        }
        assert len(group_requests) <= 40
        flickable = viewport.property("contentItem")
        assert flickable.setProperty("contentY", 30 * flow.property("rowStride"))
        for _ in range(3):
            app.processEvents()
        frame = window.grabWindow()
        assert not frame.isNull()
        assert flow.property("firstRow") >= 25
        assert 0 < repeater.property("count") <= 40
        assert any(
            card.mapToItem(viewport, 0, 0).y() < viewport.height()
            and card.mapToItem(viewport, 0, 0).y() + card.height() > 0
            for card in flow.childItems()
            if card.width() == flow.property("cardWidth")
            and card.height() == flow.property("cardHeight")
        )
        group_requests = {
            title for title, _size, request_role in requested if request_role == role
        }
        assert len(group_requests) <= 80
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        bridge.close()


@pytest.mark.parametrize(
    ("surface", "mode", "image_name", "channel"),
    [
        ("Watch", "groups", "watchGroupArtworkImage", False),
        ("Library", "groups", "libraryGroupArtworkImage", False),
        ("Watch", "groups", "watchGroupArtworkImage", True),
        ("Library", "groups", "libraryGroupArtworkImage", True),
        ("Watch", "media", "watchMediaArtworkImage", False),
        ("Library", "media", "libraryMediaArtworkImage", False),
    ],
)
def test_qt_visible_cards_show_resolved_local_artwork(
    tmp_path, monkeypatch, surface, mode, image_name, channel
):
    from PIL import Image

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    image_path = tmp_path / "saved-thumb.jpg"
    Image.new("RGB", (640, 360), "#7197b8").save(image_path)
    record = saved(tmp_path, "Saved group artwork", "MP4")
    record["preview_thumbnail_path"] = str(image_path)
    record["channel"] = "Saved channel" if channel else ""
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [record]
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.select(surface)
        if surface == "Watch":
            bridge.navigateWatch(
                "channels" if channel else "playlists" if mode == "groups" else "videos"
            )
        elif channel:
            bridge.navigateLibrary("channels")
        elif mode == "media":
            bridge.navigateLibrary("all")
        for _ in range(3):
            app.processEvents()
        assert not window.grabWindow().isNull()

        def visual_children(item):
            for child in item.childItems():
                yield child
                yield from visual_children(child)

        images = [
            item
            for item in visual_children(window.contentItem())
            if item.objectName() == image_name
        ]
        assert images
        for image in images:
            assert image.property("inset") == 0
            if not channel:
                assert image.property("cover")
            if not channel:
                inset = image.parentItem().property("artworkFaceInset") or 0
                assert image.x() == inset
                assert image.y() == inset
                assert image.width() == image.parentItem().width() - 2 * inset
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            bridge._pump()
            app.processEvents()
            if any(image.property("source").toLocalFile() for image in images):
                break
            time.sleep(0.005)
        resolved = [
            Path(image.property("source").toLocalFile()).resolve()
            for image in images
            if image.property("source").toLocalFile()
        ]
        assert resolved, (
            surface,
            mode,
            len(bridge._artwork._pending),
            len(bridge._artwork._ready),
            len(bridge._artwork._unavailable),
            [image.property("source").toString() for image in images],
        )
        painted = False
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not painted:
            app.processEvents()
            capture = window.grabWindow()
            for image in images:
                if not image.isVisible() or not image.property("source").toLocalFile():
                    continue
                point = image.mapToItem(
                    window.contentItem(), image.width() / 2, image.height() / 2
                )
                x, y = round(point.x()), round(point.y())
                if not (0 <= x < capture.width() and 0 <= y < capture.height()):
                    continue
                pixel = capture.pixelColor(x, y)
                painted = all(
                    abs(actual - expected) < 30
                    for actual, expected in zip(
                        (pixel.red(), pixel.green(), pixel.blue()),
                        (113, 151, 184),
                        strict=True,
                    )
                )
                if painted:
                    break
            if not painted:
                time.sleep(0.01)
        assert painted, (surface, mode, image_name, channel)
        if channel:
            assert any(path.name.startswith("avatar-") for path in resolved)
            with Image.open(
                next(path for path in resolved if path.name.startswith("avatar-"))
            ) as avatar:
                assert avatar.getpixel((0, 0))[3] == 0
                center = avatar.getpixel((avatar.width // 2, avatar.height // 2))[:3]
                assert all(
                    abs(actual - expected) <= 2
                    for actual, expected in zip(center, (113, 151, 184))
                )
        else:
            assert image_path in resolved
        assert any(image.property("circular") is channel for image in images)
        shown_sources = [image.property("source").toString() for image in images]
        bridge.select("Activity")
        app.processEvents()
        assert [
            image.property("source").toString() for image in images
        ] == shown_sources
        bridge.select(surface)
        app.processEvents()
        assert [
            image.property("source").toString() for image in images
        ] == shown_sources
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        bridge.close()


@pytest.mark.parametrize(
    "route,role", [("channels", "avatar"), ("playlists", "playlist")]
)
def test_qt_library_group_routes_window_cards_and_artwork(
    tmp_path, monkeypatch, route, role
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    records = []
    for index in range(200):
        record = saved(tmp_path, f"Library video {index:03d}", "MP4")
        record["channel"] = f"Channel {index:03d}"
        record["playlist_id"] = f"playlist-{index:03d}"
        record["playlist_title"] = f"Playlist {index:03d}"
        records.append(record)
    bridge._runtime.history = records
    requested = []
    monkeypatch.setattr(
        bridge._artwork,
        "request",
        lambda record, size=(320, 180), request_role="media": (
            requested.append((record["title"], size, request_role)) or ""
        ),
    )
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.select("Library")
        bridge.navigateLibrary(route)
        for _ in range(3):
            app.processEvents()
        flow = window.findChild(QObject, "libraryGroupFlow")
        repeater = window.findChild(QObject, "libraryGroupRepeater")
        viewport = window.findChild(QObject, "libraryViewport")
        assert len(bridge.libraryScene["groups"]) == 200
        assert repeater.property("count") < 40
        group_requests = {
            title for title, _size, owner_role in requested if owner_role == role
        }
        assert len(group_requests) < 40
        flickable = viewport.property("contentItem")
        assert flickable.setProperty("contentY", 30 * flow.property("rowStride"))
        for _ in range(3):
            app.processEvents()
        frame = window.grabWindow()
        assert not frame.isNull()
        assert flow.property("firstRow") >= 25
        assert 0 < repeater.property("count") < 40
        card_positions = [
            card.mapToItem(viewport, 0, 0).y()
            for card in flow.childItems()
            if card.width() == flow.property("cardWidth") and card.height() == 178
        ]
        assert any(y < viewport.height() and y + 178 > 0 for y in card_positions), (
            f"route={route} contentY={flickable.property('contentY')} "
            f"flowY={flow.y()} firstRow={flow.property('firstRow')} "
            f"viewportH={viewport.height()} positions={card_positions[:30]}"
        )
        group_requests = {
            title for title, _size, owner_role in requested if owner_role == role
        }
        assert len(group_requests) < 80
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        bridge.close()


def test_qt_mp3_cover_selection_validates_and_clears_like_tk(tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    try:
        bridge.setMp3Value("mp3_cover_art_mode", "Custom art")
        assert bridge.mp3Values["mp3_cover_art_mode"] == "No Art"
        invalid = tmp_path / "cover.png"
        invalid.write_text("not an image")
        assert not bridge.setMp3CoverUrl(QUrl.fromLocalFile(str(invalid)))
        assert not bridge.mp3CoverAvailable
        assert bridge.mp3Values["mp3_cover_art_mode"] == "No Art"

        Image.new("RGB", (32, 32), "#665588").save(invalid)
        assert bridge.setMp3CoverUrl(QUrl.fromLocalFile(str(invalid)))
        assert bridge.mp3CoverAvailable
        assert bridge.mp3Values["mp3_cover_art_mode"] == "Custom art"
        bridge.setMp3Value("mp3_cover_art_mode", "YouTube art")
        assert bridge.mp3CoverAvailable
        bridge.setMp3Value("mp3_cover_art_mode", "Custom art")
        assert bridge.mp3Values["mp3_cover_art_mode"] == "Custom art"
        bridge.clearMp3Cover()
        assert bridge.mp3Values["mp3_cover_art_mode"] == "No Art"
        assert not bridge.mp3CoverAvailable
        assert invalid.is_file()
    finally:
        bridge.close()


def test_qt_mp3_cover_clear_uses_shared_controls_in_both_settings_surfaces(
    tmp_path, monkeypatch
):
    from PIL import Image

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    bridge.setOutputFormat("MP3")
    cover = tmp_path / "cover.png"
    Image.new("RGB", (32, 32), "#665588").save(cover)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        for popup_name in ("mp3OptionsPopup", "downloadSettingsPopup"):
            assert bridge.setMp3CoverUrl(QUrl.fromLocalFile(str(cover)))
            popup = window.findChild(QObject, popup_name)
            assert popup is not None
            controls = [
                item
                for item in popup.findChildren(QObject)
                if item.property("label") == "Clear"
            ]
            assert len(controls) == 1
            controls[0].activated.emit()
            app.processEvents()
            assert bridge.mp3Values["mp3_cover_art_mode"] == "No Art"
            assert not bridge.mp3CoverAvailable
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        bridge.close()


@pytest.mark.parametrize("width", [1100, 860, 820])
def test_qt_consent_keeps_four_icon_summaries_and_actions_inside_surface(
    tmp_path, monkeypatch, width
):
    from yt_downloader.analytics_consent import ANALYTICS_BENEFITS

    qt_app()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    window.setWidth(width)
    window.show()
    bridge.analyticsPromptRequested.emit()
    try:
        QTest.qWait(150)
        popup = window.findChild(QObject, "analyticsConsentPopup")
        content = popup.property("contentItem")
        grid = visual_item(content, "analyticsBenefits")
        assert grid is not None
        assert grid.property("columns") == (2 if width == 820 else 4)
        grid_position = grid.mapToItem(content, QPointF(0, 0))
        assert abs(grid_position.x() + grid.width() / 2 - content.width() / 2) < 1
        for index, (symbol, label) in enumerate(ANALYTICS_BENEFITS):
            icon = visual_item(content, f"analyticsBenefitIcon_{index}")
            text = visual_item(content, f"analyticsBenefitLabel_{index}")
            assert icon.property("name") == symbol and icon.isVisible()
            assert icon.width() == 36 and icon.height() == 36
            assert text.property("text") == label and text.isVisible()
            assert text.property("lineCount") == 1
            for item in (icon, text):
                position = item.mapToItem(content, QPointF(0, 0))
                assert position.x() >= 0 and position.y() >= 0
                assert position.x() + item.width() <= content.width() + 1
                assert position.y() + item.height() <= content.height() + 1

        def descendants(item):
            yield item
            for child in item.childItems():
                yield from descendants(child)

        actions = [
            item
            for item in descendants(content)
            if item.property("label")
            in {"Privacy details", "No thanks", "Share analytics"}
        ]
        assert len(actions) == 3
        for item in actions:
            assert item.isVisible()
            position = item.mapToItem(content, QPointF(0, 0))
            assert position.y() + item.height() <= content.height() + 1
        assert popup.property("height") < (360 if width == 820 else 310)
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()


def test_qt_support_review_matches_selected_attachments_and_protects_footer(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        window.show()
        window.setWidth(1025)
        window.setHeight(697)
        bridge._latest_failure = FailureContext(
            "Bounded evidence",
            "https://youtu.be/8mv2Gonsdog?token=PRIVATE",
            r"C:\Users\PRIVATE\Videos",
        )
        assert bridge.openSupport("feedback")
        for _ in range(5):
            app.processEvents()
        popup = window.findChild(QObject, "supportPopup")
        consent = window.findChild(QObject, "supportOutputFolderConsent")
        assert consent.isVisible() and not consent.isEnabled()
        assert not popup.property("includeOutputFolder")
        assert (
            bridge.supportAttachmentPreview(False, False, False)
            == "No diagnostic attachments selected."
        )
        popup.setProperty("includeDiagnostics", True)
        app.processEvents()
        assert consent.isEnabled()
        popup.setProperty("includeOutputFolder", True)
        selected = bridge.supportAttachmentPreview(True, True, True)
        assert "PRIVATE" in selected and "token=" not in selected
        from yt_downloader.support_payload import feedback_payload

        payload = feedback_payload(
            reason="Other",
            message="Report",
            context=bridge._latest_failure,
            include_diagnostics=True,
            include_video_url=True,
            include_output_folder=True,
        )
        assert (
            selected
            == payload["diagnostics"]
            + "\n\nYouTube source link: "
            + payload["video_url"]
        )
        assert popup.property("height") <= window.height() - 18
        assert (
            bridge.supportAttachmentPreview(False, False, True)
            == "No diagnostic attachments selected."
        )
        assert bridge.closeSupport()
        assert bridge.openSupport("feedback")
        app.processEvents()
        assert not popup.property("includeOutputFolder")
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
