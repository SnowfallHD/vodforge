"""Cross-owner Qt scene projections used by Library, Watch and the Run Deck."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QSize, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtMultimedia import QMediaPlayer

from tests.test_quality_e2e import _isolated_launch
from tests.test_run_identity import make_job
from yt_downloader.export_planning import EXPORT_MODES
from yt_downloader.history import history_archive_owner
from yt_downloader.library_annotations import LibraryAnnotationsError
from yt_downloader.library_artwork_source import ArtworkAsset
from yt_downloader.playback_progress import WatchedProgress
from yt_downloader.qt_quick import main as qt_main
from yt_downloader.qt_quick.artwork import QtArtwork
from yt_downloader.qt_quick.scene_projection import library_scene, watch_scene
from yt_downloader.support_diagnostics import FailureContext
from yt_downloader.whats_new import NativePreview


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


def test_qt_library_group_menu_selects_every_saved_variant(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = QGuiApplication.instance() or QGuiApplication([])
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


def test_qt_settings_extra_tags_reach_existing_download_job(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    QGuiApplication.instance() or QGuiApplication([])
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


def test_qt_appearance_refreshes_shared_material_and_saved_palette(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = QGuiApplication.instance() or QGuiApplication([])
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    try:
        window = engine.rootObjects()[0]
        original = window.property("color")
        before = bridge._theme_materials.requestImage(
            "button/120/40/normal/0/r0", QSize(), QSize()
        )
        assert bridge.setAppearance("Cobalt", bridge.customAccent)
        for _ in range(5):
            app.processEvents()
        assert bridge.themeRevision == 1
        assert window.property("color") != original
        after = bridge._theme_materials.requestImage(
            "button/120/40/normal/0/r1", QSize(), QSize()
        )
        assert before != after
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
    QGuiApplication.instance() or QGuiApplication([])
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
        assert bridge.playbackUrl.toLocalFile() == str(tmp_path / "Second.mp4")
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
    QGuiApplication.instance() or QGuiApplication([])
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
        bridge.returnLibraryDetails()
        assert not bridge.saveLibraryDescription(owners[0], "Closed detail")
        assert not bridge.editLibraryTag(owners[0], "Closed detail", False)
    finally:
        bridge.close()


def test_qt_folder_browser_uses_shared_model_and_preserves_version_context(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    QGuiApplication.instance() or QGuiApplication([])
    video = saved(tmp_path, "Same source", "MP4")
    audio = saved(tmp_path, "Same source", "MP3")
    video["webpage_url"] = audio["webpage_url"] = "https://example.com/same"
    bridge = qt_main.Bridge(None)
    try:
        bridge._runtime.history = [video, audio]
        bridge.navigateLibrary("folders")
        root = bridge.libraryFolders
        assert root["mode"] == "folders"
        assert len(root["locations"]) == 1
        assert len(root["highlights"]) == 1
        assert bridge.openLibraryFolderComponent(root["locations"][0]["key"])
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
        assert bridge.libraryFolders["path"] != folder["path"]
        bridge.navigateLibraryFolders("all")
        assert bridge.libraryFolders["mode"] == "all"
    finally:
        bridge.close()


def test_qt_folder_inspector_follows_tk_selection_and_compact_detail(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = QGuiApplication.instance() or QGuiApplication([])
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
        assert round(inspector.property("width")) == 380
        assert bridge.libraryFolders["selectedKey"] == media["key"]
        assert (
            round(
                window.findChild(QObject, "libraryFolderDetailsPanel").property(
                    "height"
                )
            )
            == 360
        )
        panel = window.findChild(QObject, "libraryFolderDetailsPanel")
        folder_viewport = window.findChild(QObject, "libraryFolderViewport")
        assert (
            abs(
                panel.mapToItem(None, 0, panel.height()).y()
                - folder_viewport.mapToItem(None, 0, folder_viewport.height()).y()
            )
            <= 2
        )
        window.findChild(QObject, "libraryFolderDescriptionTab").activated.emit()
        app.processEvents()
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
    app = QGuiApplication.instance() or QGuiApplication([])
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
    app = QGuiApplication.instance() or QGuiApplication([])
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    try:
        window = engine.rootObjects()[0]
        scene = window.findChild(QObject, "watchPlayerScene")
        assert window.findChild(QObject, "watchMediaPlayer") is not None
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
    finally:
        window.close()
        app.processEvents()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
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
    app = QGuiApplication.instance() or QGuiApplication([])
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
    app = QGuiApplication.instance() or QGuiApplication([])
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
    app = QGuiApplication.instance() or QGuiApplication([])
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
    assert ("Second", (1100, 400), "media") in artwork_calls
    assert ("First", (160, 160), "avatar") in artwork_calls
    group = watch_scene(
        records, "group", artwork, scene["channels"][0]["key"], "channel"
    )
    assert group["groupAvatar"] == "First-avatar"
    assert group["groupBanner"] == "First-banner"


def test_qt_artwork_reuses_shared_owner_and_publishes_only_completed_local_asset(
    tmp_path, monkeypatch
):
    output = tmp_path / "media.mp4"
    output.write_bytes(b"media fixture")
    image = tmp_path / "thumb.jpg"
    image.write_bytes(b"image fixture")
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


def test_qt_import_uses_shared_inspection_and_commits_before_reporting_success(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = QGuiApplication.instance() or QGuiApplication([])
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
    QGuiApplication.instance() or QGuiApplication([])
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
    QGuiApplication.instance() or QGuiApplication([])
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
    QGuiApplication.instance() or QGuiApplication([])
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
    app = QGuiApplication.instance() or QGuiApplication([])
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


def test_qt_run_deck_saved_actions_bind_exact_library_owner(tmp_path, monkeypatch):
    from PySide6.QtQuickControls2 import QQuickStyle

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = QGuiApplication.instance() or QGuiApplication([])
    QQuickStyle.setStyle("Basic")
    first = saved(tmp_path, "First", "MP4")
    second = saved(tmp_path, "Second", "MP4")
    first["webpage_url"] = "https://www.youtube.com/watch?v=abcdefghijk"
    second["webpage_url"] = "https://www.youtube.com/watch?v=lmnopqrstuv"
    second["vodforge_run_activity"] = ["Saved output validated"]
    bridge = qt_main.Bridge(None)
    bridge._runtime.history = [first, second]
    engine = qt_main.create_engine(bridge)
    try:
        window = engine.rootObjects()[0]
        app.processEvents()
        deck = window.findChild(QObject, "forgeRunDeck")
        popup = window.findChild(QObject, "runActionsPopup")
        assert deck is not None and popup is not None
        first_record = bridge.runDeck["records"][0]
        second_record = bridge.runDeck["records"][1]
        first_owner = first_record["owner"]
        second_owner = second_record["owner"]
        assert first_record["hasYoutubeUrl"]
        deck.showActions(first_record)
        app.processEvents()
        view = next(
            item
            for item in popup.findChildren(QObject)
            if item.property("label") == "View in Library"
        )
        view.activated.emit()
        app.processEvents()
        assert bridge.selection == "Library"
        assert bridge.libraryDetail["owner"] == first_owner

        bridge.select("Forge")
        assert bridge.selectRunRecord(second_record["selectionKey"])
        app.processEvents()
        assert (
            window.findChild(QObject, "forgeSelectedTitle").property("text") == "Second"
        )
        assert bridge.forgeActivity["technical"] == "Saved output validated"
        deck.showActions(second_record)
        app.processEvents()
        copy = next(
            item
            for item in popup.findChildren(QObject)
            if item.property("label") == "Copy YouTube URL"
        )
        copy.activated.emit()
        app.processEvents()
        assert QGuiApplication.clipboard().text() == qt_main.canonical_youtube_url(
            second
        )

        deck.showActions(first_record)
        app.processEvents()
        remove = next(
            item
            for item in popup.findChildren(QObject)
            if item.property("label") == "Remove from Library…"
        )
        remove.activated.emit()
        app.processEvents()
        assert bridge._pending_library_removal[0] == first_owner
        removal_popup = window.findChild(QObject, "libraryRemovalConfirmation")
        assert removal_popup is not None
        assert removal_popup.property("visible") is True
        removal_popup.close()
        bridge.cancelLibraryRemoval()
        bridge._runtime.history = [second]
        assert not bridge.copySavedYoutubeUrl(first_owner)
        assert not bridge.openLibraryDetails(first_owner)
        assert second_owner == history_archive_owner(second)
    finally:
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        bridge.close()


def test_qt_run_selection_drives_forge_snapshot_and_retires_missing_record(
    tmp_path, monkeypatch
):
    from dataclasses import replace

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = QGuiApplication.instance() or QGuiApplication([])
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


def test_qt_library_detail_keeps_full_long_description_scrollable(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = QGuiApplication.instance() or QGuiApplication([])
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
    qml_sources = [path.read_text() for path in qml_root.glob("*.qml")]
    assert qml_sources
    assert all("background: Rectangle" not in source for source in qml_sources)
    assert all(
        not re.search(r"(?<!Stone)\b(?:ToolButton|RoundButton|Button)\s*\{", source)
        for source in qml_sources
    )
    image = qt_main.Materials().requestImage("field/600/600/normal", QSize(), QSize())
    assert (image.width(), image.height()) == (600, 600)


def test_qt_activity_log_uses_existing_private_persistence(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    QGuiApplication.instance() or QGuiApplication([])
    bridge = qt_main.Bridge(None)
    try:
        bridge._append_activity_line("Current run changed")
        assert "Current run changed" in bridge.activityLog
        assert "Current run changed" in bridge._activity_log_path.read_text()
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
    app = QGuiApplication.instance() or QGuiApplication([])
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
    QGuiApplication.instance() or QGuiApplication([])
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


def test_qt_player_replaces_provider_and_tags_each_open(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = QGuiApplication.instance() or QGuiApplication([])
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
    QGuiApplication.instance() or QGuiApplication([])
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
        assert bridge.supportContext == {"diagnostics": "", "videoUrl": ""}
    finally:
        bridge.close()


def test_qt_editorial_projects_all_shared_feature_previews_and_acknowledges(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    QGuiApplication.instance() or QGuiApplication([])
    source = Path(qt_main.__file__).with_name("FeaturePreview.qml").read_text()
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
    app = QGuiApplication.instance() or QGuiApplication([])
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        assert bridge.openWelcomeTour()
        popup = window.findChild(QObject, "editorialPopup")
        popup.open()
        popup.setProperty("index", 1)
        app.processEvents()
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
        popup.setProperty("index", 2)
        preview.setProperty("activityStep", 6)
        preview.setProperty("technical", True)
        app.processEvents()
        assert preview.property("previewKey") == "welcome-activity"
        assert "selected format 270+251" in preview.findChild(
            QObject, "featurePreviewActivityText"
        ).property("text")
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
    app = QGuiApplication.instance() or QGuiApplication([])
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
    app = QGuiApplication.instance() or QGuiApplication([])
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
        buttons = {
            item.property("label"): item
            for item in manual.findChildren(QObject)
            if item.property("label") is not None
        }
        assert "medium  ▾" in buttons
        buttons["medium  ▾"].activated.emit()
        assert bridge.manualValues["manual_preset"] == "slow"
        bridge.setManualValue("manual_preset", "ultrafast")
        buttons = {
            item.property("label"): item
            for item in manual.findChildren(QObject)
            if item.property("label") is not None
        }
        buttons["ultrafast  ▾"].activated.emit()
        assert bridge.manualValues["manual_preset"] == "superfast"
        window.setWidth(820)
        app.processEvents()
        assert columns.property("columns") == 1
        assert manual.property("visible")
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
    app = QGuiApplication.instance() or QGuiApplication([])
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
        editor = window.findChild(QObject, "libraryCollectionPopup")
        assert editor.property("visible") is True
        annotation_owners = ["run:first-run", "run:second-run"]
        assert editor.property("selectedOwners").toVariant() == annotation_owners
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
    QGuiApplication.instance() or QGuiApplication([])
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


def test_qt_library_home_limits_recent_cards_to_current_column_capacity(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = QGuiApplication.instance() or QGuiApplication([])
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
        assert repeater.property("count") == 4
        window.setWidth(820)
        app.processEvents()
        assert repeater.property("count") == 2
        window.setWidth(1400)
        app.processEvents()
        assert repeater.property("count") == 5
        assert len(bridge.libraryScene["media"]) == 5
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
    app = QGuiApplication.instance() or QGuiApplication([])
    bridge = qt_main.Bridge(None)
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
    app = QGuiApplication.instance() or QGuiApplication([])
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.select("Library")
        app.processEvents()
        scene = window.findChild(QObject, "libraryBrowseScene")
        collections = window.findChild(QObject, "libraryCollectionsEmptyPanel")
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
        assert collections.property("visible")
        assert not media.property("visible")
        assert collections.property("actions")

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
    app = QGuiApplication.instance() or QGuiApplication([])
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


def test_qt_shared_header_matches_tk_measured_compact_height(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = QGuiApplication.instance() or QGuiApplication([])
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.select("Library")
        for width, height, margin, nav_x, search_x in (
            (820, 560, 12, 148, 584),
            (1100, 740, 20, 290, 757),
            (1180, 790, 20, 330, 837),
        ):
            window.resize(width, height)
            for _ in range(3):
                app.processEvents()
            header = window.findChild(QObject, "focusHeader")
            nav = window.findChild(QObject, "navigationRow")
            brand = window.findChild(QObject, "brandRow")
            search = window.findChild(QObject, "globalSearchField")
            scene = window.findChild(QObject, "libraryBrowseScene")
            assert (
                round(header.mapToItem(None, 0, 0).x()),
                round(header.mapToItem(None, 0, 0).y()),
            ) == (margin, 5)
            assert round(header.height()) == 44
            assert round(brand.mapToItem(None, 0, 0).x()) == margin + 82
            assert round(nav.mapToItem(None, 0, 0).x()) == nav_x
            assert round(nav.mapToItem(None, 0, 0).y()) == 5
            assert abs(search.mapToItem(None, 0, 0).x() - search_x) <= 2
            assert round(scene.mapToItem(None, 0, 0).y()) == 54
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
    app = QGuiApplication.instance() or QGuiApplication([])
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
    app = QGuiApplication.instance() or QGuiApplication([])
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
    app = QGuiApplication.instance() or QGuiApplication([])
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
    app = QGuiApplication.instance() or QGuiApplication([])
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
    app = QGuiApplication.instance() or QGuiApplication([])
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
    "route,role", [("channels", "avatar"), ("playlists", "playlist")]
)
def test_qt_library_group_routes_window_cards_and_artwork(
    tmp_path, monkeypatch, route, role
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    app = QGuiApplication.instance() or QGuiApplication([])
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
            if card.width() == flow.property("cardWidth") and card.height() == 192
        ]
        assert any(y < viewport.height() and y + 192 > 0 for y in card_positions), (
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
    QGuiApplication.instance() or QGuiApplication([])
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
    app = QGuiApplication.instance() or QGuiApplication([])
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
