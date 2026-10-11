"""Real Qt producers with original consent, durable outbox and private-content checks."""

from __future__ import annotations

import json
import time
from threading import Event

import pytest

from tests.test_presentation_diagnostics import real_owner
from tests.test_qt_scene_port import qt_app, saved
from yt_downloader.analytics_consent import AnalyticsConsentOwner
from yt_downloader.app import ProviderNetworkCoordinator
from yt_downloader.product_telemetry import _load_outbox
from yt_downloader.qt_quick import main as qt_main
from yt_downloader.qt_quick import metadata_preview as preview_module

pytestmark = pytest.mark.usefixtures("production_telemetry_contract")


def bridge_fixture(tmp_path, monkeypatch, *, permitted=True):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    monkeypatch.setenv("HOME", str(app_dir))
    monkeypatch.setenv("LOCALAPPDATA", str(app_dir))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = qt_main.Bridge(None)
    telemetry = real_owner(tmp_path / "telemetry", permitted=permitted)
    bridge._analytics.telemetry = telemetry
    return bridge, telemetry


def rows(telemetry, tmp_path, feature):
    assert telemetry.shutdown(2)
    payloads = [
        event.public_payload()
        for event in _load_outbox(tmp_path / "telemetry/events.json")
    ]
    encoded = json.dumps(payloads)
    assert (
        "PRIVATE" not in encoded
        and str(tmp_path) not in encoded
        and "https://" not in encoded
    )
    return [row for row in payloads if row.get("feature") == feature]


def wait_preview(preview):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if preview.poll():
            return
        time.sleep(0.005)
    raise AssertionError("Preview worker did not settle")


def begin_preview(preview):
    return preview.begin(
        "https://example.com/PRIVATE",
        qt_main.OutputType.MP4,
        ignore_playlists=True,
        cookie_source=qt_main.CookieSource.PUBLIC,
        cookie_file=None,
        cookie_browser=None,
        ffmpeg=None,
        deno=None,
    )


@pytest.mark.parametrize("permitted", [True, False])
def test_file_navigation_reports_each_view_without_private_path(
    tmp_path, monkeypatch, permitted
):
    bridge, telemetry = bridge_fixture(tmp_path, monkeypatch, permitted=permitted)
    try:
        folder_path = tmp_path / "PRIVATE-library"
        folder_path.mkdir()
        record = saved(folder_path, "PRIVATE title", "MP4")
        record["vodforge_retry_job"] = {"output_dir": str(tmp_path)}
        bridge._runtime.history = [record]
        bridge.navigateLibrary("folders")
        model = bridge.libraryFolders
        folder = next(row for row in model["components"] if row["kind"] == "folder")
        assert bridge.openLibraryFolderComponent(folder["key"])
        bridge.navigateLibraryFolders("all")
        bridge.navigateLibraryFolders("issues")
        actual = rows(telemetry, tmp_path, "archive")
        assert [row["action"] for row in actual] == (
            ["folders", "folder_opened", "all_media", "issues"] if permitted else []
        )
        if permitted:
            assert actual[-1]["dimensions"]["archive_mode"] == "issues"
    finally:
        bridge.close()


@pytest.mark.parametrize("result", ["success", "timeout", "empty", "empty_dict"])
def test_preview_reports_actual_settlement_with_bounded_cause(
    tmp_path, monkeypatch, result
):
    telemetry = real_owner(tmp_path / "telemetry")
    preview = preview_module.QtMetadataPreview(ProviderNetworkCoordinator())
    preview.product_telemetry = telemetry

    def fetch(*_args, **_kwargs):
        if result == "timeout":
            raise TimeoutError("PRIVATE source and cookie detail")
        if result == "empty_dict":
            return {}
        return (
            {"entries": []}
            if result == "empty"
            else {"id": "PRIVATE", "title": "PRIVATE"}
        )

    monkeypatch.setattr(preview_module, "fetch_metadata_preview", fetch)
    try:
        assert begin_preview(preview)
        wait_preview(preview)
        assert preview.phase == ("complete" if result == "success" else "failed")
        assert not preview.poll()
        actual = rows(telemetry, tmp_path, "library_action_operation")
        assert [row["action"] for row in actual] == [
            "requested",
            "admitted",
            "completed" if result == "success" else "rejected",
        ]
        assert len({row["dimensions"]["operation_id"] for row in actual}) == 1
        assert [row["dimensions"]["operation_step"] for row in actual] == [
            "1",
            "2",
            "3",
        ]
        if result == "timeout":
            assert actual[-1]["failure_detail"]["failure_code"] == "timeout"
            assert actual[-1]["failure_detail"]["stage"] == "analysis"
        elif result in {"empty", "empty_dict"}:
            assert actual[-1]["failure_detail"]["stage"] == "analysis"
    finally:
        preview.close()
        telemetry.shutdown(2)


@pytest.mark.parametrize("context", ["denied", "regranted", "closed", "sink_failed"])
def test_delayed_preview_keeps_original_consent_and_never_revives_closed_work(
    tmp_path, monkeypatch, context
):
    telemetry = real_owner(tmp_path / "telemetry", permitted=context != "denied")
    preview = preview_module.QtMetadataPreview(ProviderNetworkCoordinator())
    started, release = Event(), Event()

    def fetch(*_args, **_kwargs):
        started.set()
        assert release.wait(2)
        return {"id": "PRIVATE"}

    monkeypatch.setattr(preview_module, "fetch_metadata_preview", fetch)
    preview.product_telemetry = telemetry
    if context == "sink_failed":

        class Broken:
            def bind_operation(self, *_args, **_kwargs):
                raise OSError("PRIVATE sink error")

        preview.product_telemetry = Broken()
    try:
        assert begin_preview(preview)
        assert started.wait(1)
        if context in {"denied", "regranted"}:
            consent = AnalyticsConsentOwner(tmp_path / "telemetry")
            if context == "regranted":
                consent.choose(False)
                telemetry.set_enabled(False)
            consent.choose(True)
            telemetry.set_enabled(True)
        if context == "closed":
            preview.close()
        release.set()
        if context != "closed":
            wait_preview(preview)
            assert preview.phase == "complete"
        actual = rows(telemetry, tmp_path, "library_action_operation")
        assert [row["action"] for row in actual] == (
            ["requested", "admitted", "cancelled"] if context == "closed" else []
        )
    finally:
        release.set()
        preview.close()
        telemetry.shutdown(2)


@pytest.mark.parametrize("outcome", ["resume", "timeout", "provider_failed"])
def test_player_resume_is_correlated_and_stale_generation_cannot_complete(
    tmp_path, monkeypatch, outcome
):
    bridge, telemetry = bridge_fixture(tmp_path, monkeypatch)
    try:
        record = saved(tmp_path, "PRIVATE title", "MP4")
        path = tmp_path / "PRIVATE media.mp4"
        path.write_bytes(b"controlled provider input")
        record["vodforge_output_path"] = str(path)
        bridge._runtime.history = [record]
        previous = bridge._playback_progress.begin(record)
        from yt_downloader.playback_backend import PlaybackSnapshot

        bridge._playback_progress.observe(
            previous, PlaybackSnapshot(path, "Playing", 40, 100, 80)
        )
        bridge._playback_progress.retire(previous)
        assert bridge.openLibraryItem(0)
        generation = bridge._playback_generation
        bridge.observePlayback(0, 100, "Playing", generation)
        if outcome == "resume":
            bridge.observePlayback(40, 100, "Playing", generation)
        elif outcome == "timeout":
            binding = bridge._playback_binding
            assert binding is not None
            binding._requested_at -= 6
            bridge.observePlayback(0, 100, "Playing", generation)
        else:
            bridge.observePlayback(0, 100, "Failed", generation)
            bridge.observePlayback(100, 100, "Ended", generation)
        bridge.observePlayback(100, 100, "Ended", generation - 1)
        bridge.closePlayback()
        bridge.closePlayback()
        actual = rows(telemetry, tmp_path, "playback_operation")
        actions = [row["action"] for row in actual]
        assert actions[:4] == ["requested", "ready", "started", "resume_requested"]
        assert (
            actions.count(
                "resume_completed" if outcome == "resume" else "resume_failed"
            )
            == 1
        )
        assert "completed" not in actions
        assert actions.count("closed") == 1
        assert len({row["dimensions"]["operation_id"] for row in actual}) == 1
        if outcome == "provider_failed":
            assert actions.count("failed") == 1
            assert (
                actual[actions.index("failed")]["failure_detail"]["stage"] == "playback"
            )
        if outcome == "timeout":
            assert (
                next(row for row in actual if row["action"] == "resume_failed")[
                    "dimensions"
                ]["resume_reason"]
                == "seek_timeout"
            )
    finally:
        bridge.close()


@pytest.mark.parametrize(
    "native_error,category,reason",
    [
        (1, "resource", "unknown"),
        (2, "format", "unsupported_format"),
        (3, "network", "network"),
        (4, "access_denied", "permission_denied"),
        (99, "unknown", "unknown"),
    ],
)
def test_native_playback_error_is_closed_and_never_serializes_provider_text(
    tmp_path, monkeypatch, native_error, category, reason
):
    bridge, telemetry = bridge_fixture(tmp_path, monkeypatch)
    try:
        path = tmp_path / "PRIVATE.mp4"
        path.write_bytes(b"input")
        record = saved(tmp_path, "PRIVATE", "MP4")
        record["vodforge_output_path"] = str(path)
        bridge._runtime.history = [record]
        assert bridge.openLibraryItem(0)
        generation = bridge._playback_generation
        bridge.observePlayback(0, 0, "Failed", generation, native_error)
        bridge.observePlayback(0, 0, "Failed", generation, native_error)
        bridge.closePlayback()
        actual = rows(telemetry, tmp_path, "playback_operation")
        assert [e["action"] for e in actual] == ["requested", "failed", "closed"]
        assert actual[1]["dimensions"]["qt_media_error"] == category
        assert actual[1]["failure_detail"]["reason"] == reason
        assert "processing_bucket" in actual[1]["dimensions"]
    finally:
        bridge.close()


def test_repeated_navigation_counts_visits_without_replacing_engagement(
    tmp_path, monkeypatch
):
    bridge, telemetry = bridge_fixture(tmp_path, monkeypatch)
    try:
        bridge.navigateLibraryFolders("all")
        bridge.navigateLibraryFolders("issues")
        bridge.navigateLibraryFolders("all")
        actual = rows(telemetry, tmp_path, "navigation_operation")
        assert [e["dimensions"]["navigation_action"] for e in actual] == [
            "all_media",
            "issues",
            "all_media",
        ]
        assert len({e["dimensions"]["operation_id"] for e in actual}) == 3
    finally:
        bridge.close()


def test_automatic_check_starts_during_active_work_and_retries_only_updater_busy(
    tmp_path, monkeypatch
):
    bridge, _telemetry = bridge_fixture(tmp_path, monkeypatch)
    scheduled = []
    monkeypatch.setattr(
        qt_main.QTimer, "singleShot", lambda delay, callback: scheduled.append(delay)
    )
    from types import SimpleNamespace

    runtime = bridge._runtime
    bridge._runtime = SimpleNamespace(busy=True, active_job=object())
    calls = []
    monkeypatch.setattr(bridge._updates, "check", lambda **kw: calls.append(kw) or True)
    bridge._auto_check_updates()
    assert calls == [{"automatic": True}]
    assert scheduled == [6 * 60 * 60 * 1000]
    bridge._updates.busy = True
    bridge._auto_check_updates()
    assert calls == [{"automatic": True}]
    assert scheduled[-1] == 30 * 1000
    bridge._runtime = runtime
    bridge.close()


@pytest.mark.parametrize("permitted", [True, False])
@pytest.mark.parametrize("terminal", ["Ended", "Failed"])
def test_legacy_player_terminal_engagement_survives_operation_tracking(
    tmp_path, monkeypatch, permitted, terminal
):
    bridge, telemetry = bridge_fixture(tmp_path, monkeypatch, permitted=permitted)
    try:
        record = saved(tmp_path, "PRIVATE title", "MP4")
        path = tmp_path / "PRIVATE.mp4"
        path.write_bytes(b"controlled provider input")
        record["vodforge_output_path"] = str(path)
        bridge._runtime.history = [record]
        assert bridge.openLibraryItem(0)
        generation = bridge._playback_generation
        bridge.observePlayback(0, 100, "Playing", generation)
        bridge.observePlayback(100, 100, terminal, generation - 1)
        bridge.observePlayback(100, 100, terminal, generation)
        bridge.observePlayback(100, 100, terminal, generation)
        if terminal == "Failed":
            bridge.observePlayback(100, 100, "Ended", generation)
        actual = rows(telemetry, tmp_path, "player")
        assert [event["action"] for event in actual] == (
            ["completed" if terminal == "Ended" else "failed"] if permitted else []
        )
    finally:
        bridge.close()


@pytest.mark.parametrize("permitted", [True, False])
def test_successful_copy_engagement_contains_no_private_text_and_rejects_stale_owner(
    tmp_path, monkeypatch, permitted
):
    from yt_downloader.history import history_archive_owner

    bridge, telemetry = bridge_fixture(tmp_path, monkeypatch, permitted=permitted)
    try:
        record = saved(tmp_path, "PRIVATE title", "MP4")
        record["description"] = "PRIVATE source description"
        bridge._runtime.history = [record]
        owner = history_archive_owner(record)
        bridge._library_detail_owner = owner
        bridge._library_scene_route = "detail"
        assert not bridge.copyLibraryText("stale-owner", "description")
        assert not bridge.copyLibraryText(owner, "tags")
        assert bridge.copyLibraryText(owner, "description")
        assert bridge.copyLibraryText(owner, "description")
        assert bridge.editLibraryTag(owner, "PRIVATE tag", False)
        assert bridge.copyLibraryText(owner, "tags")
        assert bridge.copyLibraryText(owner, "note", "PRIVATE unsaved note")
        actual = rows(telemetry, tmp_path, "library")
        assert [event["action"] for event in actual] == (
            [
                "source_description_copied",
                "personal_tags_copied",
                "personal_note_copied",
            ]
            if permitted
            else []
        )
        assert bridge._annotations.annotation_for(owner).note == ""
    finally:
        bridge.close()


@pytest.mark.parametrize("permitted", [True, False])
def test_clipboard_location_and_youtube_source_track_only_success_without_values(
    tmp_path, monkeypatch, permitted
):
    from yt_downloader.history import history_archive_owner

    bridge, telemetry = bridge_fixture(tmp_path, monkeypatch, permitted=permitted)
    try:
        record = saved(tmp_path, "PRIVATE title", "MP4")
        record["webpage_url"] = "https://www.youtube.com/watch?v=abcdefghijk"
        path = tmp_path / "PRIVATE.mp4"
        path.write_bytes(b"controlled fixture")
        record["vodforge_output_path"] = str(path)
        bridge._runtime.history = [record]
        bridge._playback_record = record
        owner = history_archive_owner(record)
        assert not bridge.copyPlayerSourceUrl("stale-owner")
        bridge.copyLibraryPath("stale-owner")
        assert bridge.copyPlayerSourceUrl(owner)
        bridge.copyLibraryPath(owner)
        assert telemetry.shutdown(2)
        actual = [
            event.public_payload()
            for event in _load_outbox(tmp_path / "telemetry/events.json")
        ]
        assert "PRIVATE" not in json.dumps(actual)
        assert "https://" not in json.dumps(actual)
        pairs = [(event.get("feature"), event.get("action")) for event in actual]
        assert pairs == (
            [("library", "youtube_url_copied"), ("archive", "location_copied")]
            if permitted
            else []
        )
    finally:
        bridge.close()


@pytest.mark.parametrize("permitted", [True, False])
def test_archive_observations_follow_admitted_changes(tmp_path, monkeypatch, permitted):
    from yt_downloader.volume_storage import StorageSnapshot, StorageVolume

    bridge, telemetry = bridge_fixture(tmp_path, monkeypatch, permitted=permitted)
    try:
        records = [
            saved(tmp_path, f"PRIVATE {i}", "MP4") for i in range(qt_main.PAGE_SIZE + 2)
        ]
        bridge._runtime.history = records
        owners = [qt_main.history_archive_owner(record) for record in records]
        assert not bridge.openLibraryDetails("invalid-owner")
        assert bridge.openLibraryDetails(owners[0])
        bridge._detail_versions = [{"owner": owner} for owner in owners[:2]]
        assert not bridge.chooseLibraryVersion("invalid-owner")
        assert bridge.chooseLibraryVersion(owners[1])
        assert bridge.chooseLibraryVersion(owners[1])
        bridge.setLibrarySort("invalid")
        bridge.setLibrarySort("title")
        bridge.setLibrarySort("title")
        bridge.navigateLibraryFolders("all")
        bridge.loadMoreLibraryFolder()
        bridge.loadMoreLibraryFolder()
        assert bridge._folder_browser.page == 1
        volumes = tuple(
            StorageVolume(str(tmp_path / name), "PRIVATE volume")
            for name in ("one", "two")
        )
        snapshot = StorageSnapshot(volumes[0].path, "ready", volumes)
        bridge._storage._snapshot = bridge._storage_snapshot = snapshot
        bridge._storage._selected = snapshot.selected
        bridge.selectStorageVolume("invalid")
        bridge.selectStorageVolume(volumes[1].path)
        bridge.selectStorageVolume(volumes[1].path)
        actual = rows(telemetry, tmp_path, "archive")
        actions = [row["action"] for row in actual]
        for action in (
            "inspector_opened",
            "version_selected",
            "scene_sorted",
            "scene_paged",
            "volume_selected",
        ):
            assert actions.count(action) == (1 if permitted else 0)
    finally:
        bridge.close()


@pytest.mark.parametrize("permitted", [True, False])
def test_retired_watch_detail_intent_is_observed_without_private_owner(
    tmp_path, monkeypatch, permitted
):
    bridge, telemetry = bridge_fixture(tmp_path, monkeypatch, permitted=permitted)
    try:
        bridge.select("Watch")
        assert not bridge.openWatchDetails("PRIVATE retired owner")
        actual = rows(telemetry, tmp_path, "watch")
        assert [row["action"] for row in actual].count("details_retired") == (
            1 if permitted else 0
        )
    finally:
        bridge.close()


@pytest.mark.parametrize(
    "context", ["granted", "denied", "regranted", "blocked", "failed", "replacement"]
)
def test_help_dispatch_retains_original_consent_and_actual_panel_lifecycle(
    tmp_path, monkeypatch, context
):
    bridge, telemetry = bridge_fixture(
        tmp_path, monkeypatch, permitted=context != "denied"
    )
    try:
        bridge.helpMenuShown()
        bridge.prepareHelpAction("feedback")
        bridge.helpMenuClosed()
        if context in {"denied", "regranted"}:
            consent = AnalyticsConsentOwner(tmp_path / "telemetry")
            if context == "regranted":
                consent.choose(False)
                telemetry.set_enabled(False)
            consent.choose(True)
            telemetry.set_enabled(True)
        if context == "blocked":
            bridge._support.busy = True
            assert not bridge.openSupport("feedback")
            bridge._support.busy = False
        elif context == "failed":

            def broken(*_args):
                raise OSError("PRIVATE message and folder")

            monkeypatch.setattr(bridge._support, "open", broken)
            with pytest.raises(OSError):
                bridge.openSupport("feedback")
        else:
            assert bridge.openSupport("feedback")
            bridge.helpPanelShown("review")  # wrong or retired panel cannot settle
            bridge.helpPanelShown("feedback")
            bridge.helpPanelShown("feedback")
            if context == "replacement":
                assert bridge.openSupport("review")
                bridge.helpPanelShown("review")
            assert bridge.closeSupport()
        actual = rows(telemetry, tmp_path, "help_operation")
        actions = [row["action"] for row in actual]
        if context in {"denied", "regranted"}:
            assert not actual
        else:
            terminal = (
                ["blocked", "closed"]
                if context == "blocked"
                else ["failed", "closed"]
                if context == "failed"
                else ["shown", "closed"]
            )
            if context == "replacement":
                assert actions == [
                    "requested",
                    "shown",
                    "selected",
                    "dispatched",
                    "shown",
                    "requested",
                    "dispatched",
                    "replaced",
                    "closed",
                    "shown",
                    "closed",
                ]
            else:
                assert actions == [
                    "requested",
                    "shown",
                    "selected",
                    "dispatched",
                    *terminal,
                ]
                assert len({row["dimensions"]["operation_id"] for row in actual}) == 1
                assert [row["dimensions"]["operation_step"] for row in actual] == [
                    str(i + 1) for i in range(len(actual))
                ]
            if context == "failed":
                assert actual[-2]["failure_detail"]["stage"] == "dispatch"
    finally:
        bridge.close()


def test_rendered_qt_menu_selection_search_and_help_use_real_callbacks(
    tmp_path, monkeypatch
):
    from PySide6.QtCore import QMetaObject, QObject, Qt
    from PySide6.QtTest import QTest

    from tests.test_qt_scene_port import visual_item

    bridge, telemetry = bridge_fixture(tmp_path, monkeypatch)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    app = qt_app()
    try:
        bridge._runtime.history = [saved(tmp_path, "PRIVATE title", "MP4")]
        bridge.select("Library")
        app.processEvents()
        scene = window.findChild(QObject, "libraryBrowseScene")
        item = visual_item(window.contentItem(), "librarySelectButton")
        item.activated.emit()
        app.processEvents()
        assert scene.property("selectionMode")
        assert QMetaObject.invokeMethod(scene, "finishSelection", Qt.DirectConnection)
        search = visual_item(window.contentItem(), "headerSearchInput")
        search.forceActiveFocus()
        app.processEvents()
        menu = window.findChild(QObject, "librarySavedActionsPopup")
        assert QMetaObject.invokeMethod(menu, "open", Qt.DirectConnection)
        app.processEvents()
        QMetaObject.invokeMethod(menu, "close", Qt.DirectConnection)
        assert bridge.openSupport("feedback")
        QTest.qWait(30)
        assert window.findChild(QObject, "supportPopup").property("visible")
        library = rows_without_close(tmp_path, "library")
        assert {row["action"] for row in library} >= {
            "selection_started",
            "selection_finished",
            "search_focused",
            "menu_opened",
        }
        help_rows = rows_without_close(tmp_path, "help_operation")
        assert [row["action"] for row in help_rows] == [
            "requested",
            "dispatched",
            "shown",
        ]
        rows(telemetry, tmp_path, "library")  # shared privacy checks
    finally:
        bridge.close()
        window.close()
        engine.deleteLater()
        app.processEvents()


def rows_without_close(tmp_path, feature):
    return [
        event.public_payload()
        for event in _load_outbox(tmp_path / "telemetry/events.json")
        if event.feature == feature
    ]


@pytest.mark.parametrize("permitted", [True, False])
def test_folder_inspector_observes_actual_selection_and_version_change(
    tmp_path, monkeypatch, permitted
):
    from pathlib import Path

    bridge, telemetry = bridge_fixture(tmp_path, monkeypatch, permitted=permitted)
    try:
        video, audio = [
            saved(tmp_path, "PRIVATE title", kind) for kind in ("MP4", "MP3")
        ]
        for record in (video, audio):
            Path(record["vodforge_output_path"]).write_bytes(b"controlled fixture")
            record["webpage_url"] = "https://example.com/PRIVATE-source"
        bridge._runtime.history = [video, audio]
        bridge.select("Library")
        bridge.navigateLibraryFolders("all")
        component = next(
            row for row in bridge.libraryFolders["components"] if row["kind"] == "media"
        )
        assert not bridge.selectLibraryFolderComponent("PRIVATE stale key")
        assert bridge.selectLibraryFolderComponent(component["key"])
        inspector = bridge.libraryFolderInspector
        other = next(
            row["owner"]
            for row in inspector["versions"]
            if row["owner"] != inspector["owner"]
        )
        assert not bridge.chooseLibraryFolderInspectorVersion("PRIVATE stale owner")
        assert bridge.chooseLibraryFolderInspectorVersion(other)
        assert bridge.chooseLibraryFolderInspectorVersion(other)
        assert bridge.libraryFolderInspector["type"] == "MP3"
        actual = rows(telemetry, tmp_path, "archive")
        actions = [row["action"] for row in actual]
        assert actions.count("inspector_opened") == (1 if permitted else 0)
        assert actions.count("version_selected") == (1 if permitted else 0)
    finally:
        bridge.close()


@pytest.mark.parametrize("context", ["granted", "denied", "regranted"])
def test_relink_cancellation_observes_request_once_and_actual_cancelled_outcome(
    tmp_path, monkeypatch, context
):
    from pathlib import Path

    from PySide6.QtCore import QUrl

    from tests.test_qt_relink import _settle
    from yt_downloader.history import load_history, save_history
    from yt_downloader.qt_quick import relink as relink_module

    bridge, telemetry = bridge_fixture(
        tmp_path, monkeypatch, permitted=context != "denied"
    )
    entered, release = Event(), Event()
    try:
        old = tmp_path / "PRIVATE old"
        old.mkdir()
        candidate = tmp_path / "PRIVATE new.mp4"
        candidate.write_bytes(b"controlled saved media")
        record = saved(old, "PRIVATE old", "MP4")
        save_history(bridge._runtime.history_path, [record])
        bridge._runtime.history = load_history(bridge._runtime.history_path)
        original = Path(bridge._runtime.history_path).read_bytes()
        owner = qt_main.history_archive_owner(bridge._runtime.history[0])
        assert bridge.beginRelink(owner, QUrl.fromLocalFile(str(candidate)))
        _settle(bridge._relink)
        assert bridge._relink.phase == "preview"

        def interrupted_commit(*_args, cancelled, **_kwargs):
            entered.set()
            assert release.wait(2)
            assert cancelled.is_set()
            raise ValueError("PRIVATE interrupted fixture")

        monkeypatch.setattr(relink_module, "commit_relink", interrupted_commit)
        assert bridge.acceptRelink()
        assert entered.wait(1)
        if context in {"denied", "regranted"}:
            consent = AnalyticsConsentOwner(tmp_path / "telemetry")
            if context == "regranted":
                consent.choose(False)
                telemetry.set_enabled(False)
            consent.choose(True)
            telemetry.set_enabled(True)
        bridge.cancelRelink()
        bridge.cancelRelink()
        assert bridge._relink.phase == "working"
        release.set()
        deadline = time.monotonic() + 2
        while bridge._relink.phase == "working" and time.monotonic() < deadline:
            bridge._pump()
            time.sleep(0.005)
        assert bridge._relink.phase == "cancelled"
        assert Path(bridge._runtime.history_path).read_bytes() == original
        actual = rows(telemetry, tmp_path, "archive_relink_operation")
        actions = [row["action"] for row in actual]
        assert actions.count("cancel_requested") == (1 if context == "granted" else 0)
        assert actions.count("cancelled") == (1 if context == "granted" else 0)
        assert "committed" not in actions
    finally:
        release.set()
        bridge.close()


@pytest.mark.parametrize("permitted", [True, False])
def test_rendered_watch_scroll_reports_input_movement_not_layout_restoration(
    tmp_path, monkeypatch, permitted
):
    from PySide6.QtCore import QObject, QPoint, QPointF, Qt
    from PySide6.QtGui import QGuiApplication, QWheelEvent

    from tests.test_qt_scene_port import visual_item

    bridge, telemetry = bridge_fixture(tmp_path, monkeypatch, permitted=permitted)
    app = qt_app()
    for i in range(18):
        record = saved(tmp_path, f"PRIVATE {i}", "MP4")
        record["playlist_id"] = f"PRIVATE playlist-{i}"
        record["playlist_title"] = f"PRIVATE playlist {i}"
        bridge._runtime.history.append(record)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.selectHome("Watch")
        for _ in range(5):
            app.processEvents()
        rail = visual_item(window.contentItem(), "watchHomeRail_playlists")
        page = window.findChild(QObject, "watchViewport").property("contentItem")
        horizontal = rail.property("contentItem")
        horizontal.setProperty("contentX", 40)
        for _ in range(5):
            app.processEvents()
        assert not rows_without_close(tmp_path, "watch") or not any(
            row["action"] in {"rail_scrolled", "catalog_scrolled"}
            for row in rows_without_close(tmp_path, "watch")
        )
        point = rail.mapToScene(QPointF(120, 60))
        assert 0 < point.y() < window.height(), (point, window.height())
        for dx, dy in ((0, -80), (-80, 0)):
            before = (
                horizontal.property("contentX") if dx else page.property("contentY")
            )
            wheel = QWheelEvent(
                point,
                point,
                QPoint(dx, dy),
                QPoint(),
                Qt.NoButton,
                Qt.NoModifier,
                Qt.ScrollUpdate,
                False,
            )
            QGuiApplication.sendEvent(window, wheel)
            for _ in range(5):
                app.processEvents()
            after = horizontal.property("contentX") if dx else page.property("contentY")
            assert after > before
        search = visual_item(window.contentItem(), "headerSearchInput")
        search.forceActiveFocus()
        app.processEvents()
        actual = rows(telemetry, tmp_path, "watch")
        for action in ("rail_scrolled", "catalog_scrolled", "search_focused"):
            assert [row["action"] for row in actual].count(action) == (
                1 if permitted else 0
            )
    finally:
        bridge.close()
        window.close()
        engine.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("others", [0, 2])
def test_rendered_related_observation_requires_actual_cards_and_live_owner(
    tmp_path, monkeypatch, others
):
    from PySide6.QtTest import QTest

    bridge, telemetry = bridge_fixture(tmp_path, monkeypatch)
    app = qt_app()
    bridge._runtime.history = [
        saved(tmp_path, f"PRIVATE {i}", "MP4") for i in range(others + 1)
    ]
    for i in range(others + 1):
        (tmp_path / f"PRIVATE {i}.mp4").write_bytes(b"controlled fixture")
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        bridge.recordRelatedShown("PRIVATE stale owner")
        assert not rows_without_close(tmp_path, "player")
        assert bridge.openLibraryItem(0)
        QTest.qWait(40)
        actual = rows(telemetry, tmp_path, "player")
        assert [row["action"] for row in actual].count("related_shown") == (
            1 if others else 0
        )
    finally:
        bridge.close()
        window.close()
        engine.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("available", [True, False])
def test_real_qml_hover_callback_waits_for_visible_ready_frame(
    tmp_path, monkeypatch, available
):
    from PIL import Image
    from PySide6.QtCore import QObject, QUrl
    from PySide6.QtQml import QQmlComponent
    from PySide6.QtTest import QTest

    bridge, telemetry = bridge_fixture(tmp_path, monkeypatch)
    app = qt_app()
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    component = QQmlComponent(engine)
    component.setData(
        b"""
import QtQuick
Item {
    width: 900; height: 220
    QtObject { id: media; property int duration: 100000; property int position: 0; property int playbackState: 1 }
    PlayerOverlay { objectName: "coverageOverlay"; anchors.fill: parent; player: media; volume: 0.5 }
}
""",
        QUrl.fromLocalFile(
            str(qt_main.Path(qt_main.__file__).parent / "TelemetryHoverControl.qml")
        ),
    )
    root = component.create()
    assert root is not None, [error.toString() for error in component.errors()]
    root.setParentItem(window.contentItem())
    overlay = root.findChild(QObject, "coverageOverlay")
    preview = overlay.findChild(QObject, "playerSeekPreview")
    overlay.setProperty("surfaceHovered", True)
    observed = []
    overlay.previewPresented.connect(
        lambda image, ready: observed.append((image, ready))
    )
    try:
        image = ""
        if available:
            file = tmp_path / "PRIVATE_frame.png"
            Image.new("RGB", (32, 18), "blue").save(file)
            image = QUrl.fromLocalFile(str(file)).toString()
        overlay.setProperty(
            "previews",
            [{"image": image, "status": "Ready" if available else "No preview"}],
        )
        QTest.qWait(30)
        assert not preview.property("visible")
        assert observed == []
        # Control only visibility; production Image status and signal run normally.
        preview.setProperty("visible", True)
        QTest.qWait(40)
        assert observed and set(observed) == {(image, available)}
        overlay.setProperty("visible", False)
        observed.clear()
        overlay.setProperty("previews", [{"image": "", "status": "No preview"}])
        QTest.qWait(20)
        assert observed == []
    finally:
        root.deleteLater()
        window.close()
        engine.deleteLater()
        app.processEvents()
        bridge.close()
        telemetry.shutdown(2)
