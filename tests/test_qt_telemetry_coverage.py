"""Real Qt producers with original consent, durable outbox and private-content checks."""

from __future__ import annotations

import json
import time
from threading import Event

import pytest
from PySide6.QtGui import QGuiApplication

from tests.test_presentation_diagnostics import real_owner
from tests.test_qt_scene_port import saved
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
    QGuiApplication.instance() or QGuiApplication([])
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
