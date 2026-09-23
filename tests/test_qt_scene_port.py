"""Cross-owner Qt scene projections used by Library, Watch and the Run Deck."""

from __future__ import annotations

import re
import time
import wave
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QSize, QUrl
from PySide6.QtGui import QGuiApplication

from yt_downloader.export_planning import EXPORT_MODES
from yt_downloader.history import history_archive_owner
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
        assert bridge.openLibraryFolderComponent(media["key"])
        detail = bridge.libraryDetail
        assert detail["fromFolders"] is True
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
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
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
