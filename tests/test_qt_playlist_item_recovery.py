"""Exercise playlist recovery through its real offline worker and Library controls."""

from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject

from tests.test_qt_scene_port import qt_app
from yt_downloader import download_service as service
from yt_downloader.qt_quick import main as qt_main
from yt_downloader.qt_quick.runtime import DownloadPreferences, DownloadRuntime

_PLAYLIST = "https://www.youtube.com/playlist?list=PLexample"
_GOOD_BEFORE = "goodbefore1"
_FAILED = "faileditem1"
_GOOD_AFTER = "goodafter01"
_ITEM_URL = f"https://www.youtube.com/watch?v={_FAILED}&list=PLexample"


def _settle_worker(runtime):
    assert runtime.worker is not None
    runtime.worker.join(timeout=8)
    assert not runtime.worker.is_alive()
    events = runtime.poll()
    assert runtime.active_job is None
    return [payload for kind, payload in events if kind in {"partial", "done", "error"}]


def test_early_failure_recovers_only_verified_item_after_restart_even_if_report_fails(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    output = tmp_path / "media"
    output.mkdir()
    monkeypatch.setattr(service, "write_diagnostic", lambda *_args: None)
    monkeypatch.setattr(service, "load_yt_dlp", lambda: object())
    monkeypatch.setattr(
        service.DownloadWorkerCore, "_find_ffmpeg", staticmethod(lambda: "fixture")
    )
    monkeypatch.setattr(
        service.DownloadWorkerCore, "_find_deno", staticmethod(lambda: None)
    )

    def watch(video_id):
        return f"https://www.youtube.com/watch?v={video_id}"

    entries = [
        {"id": _GOOD_BEFORE, "title": "Good before", "url": watch(_GOOD_BEFORE)},
        {
            "id": _FAILED,
            "title": "Failed selection",
            "url": _ITEM_URL + "&si=local-secret",
        },
        {"title": "Ambiguous selection", "url": _PLAYLIST, "ie_key": "YoutubeTab"},
        {"id": _GOOD_AFTER, "title": "Good after", "url": watch(_GOOD_AFTER)},
    ]
    playlist_requests = []
    analysis_requests = []
    transfers = []
    report_attempts = []
    missing_audio = True
    wrong_video = False

    def extract_playlist(_ydl, _options, url, **_kw):
        assert url == _PLAYLIST
        playlist_requests.append(url)
        return {"id": "PLexample", "title": "Fixture playlist", "entries": entries}, ()

    def analyze(_ydl, _options, _cookies, url, _label, **_kw):
        analysis_requests.append(url)
        video_id = service.youtube_url_video_id(url)
        info = next(entry for entry in entries if entry.get("id") == video_id)
        formats = (
            []
            if video_id is None or (video_id == _FAILED and missing_audio)
            else [{"format_id": "251", "acodec": "opus", "vcodec": "none", "abr": 128}]
        )
        if video_id == _FAILED and wrong_video:
            video_id = _GOOD_AFTER
        return {"id": video_id, "title": info["title"], "formats": formats}, ()

    def transfer(_ydl, options, info, _cookies, _guard, **_kw):
        video_id = info["id"]
        transfers.append(video_id)
        (Path(options["paths"]["home"]) / f"{video_id}.mp3").write_bytes(
            video_id.encode()
        )
        return info, ()

    def validate(_path, *_args, **_kw):
        return {}

    def fail_report(_path, url, error):
        report_attempts.append((url, str(error)))
        raise PermissionError("fixture failure report is unwritable")

    monkeypatch.setattr(service, "_extract_playlist_source_step", extract_playlist)
    monkeypatch.setattr(service, "_analyze_source_formats_step", analyze)
    monkeypatch.setattr(service, "_download_with_audio_url_refresh", transfer)
    monkeypatch.setattr(service, "_ffprobe_for_ffmpeg", lambda _ffmpeg: "fixture")
    monkeypatch.setattr(service, "validate_output_artifact", validate)
    monkeypatch.setattr(service, "append_batch_failure_report", fail_report)

    runtime = DownloadRuntime()
    try:
        parent = runtime.start(
            _PLAYLIST,
            output,
            "MP3",
            "Everyday",
            preferences=DownloadPreferences(single_video_only=False),
        )
        [partial] = _settle_worker(runtime)
        assert "2 valid output(s), 2 failed" in partial
        assert transfers == [_GOOD_BEFORE, _GOOD_AFTER]
        assert len(report_attempts) == 2
        assert [url for url, _ in report_attempts] == [_ITEM_URL, ""]
        assert all("No usable audio source" in error for _, error in report_attempts)
        assert (
            sum(
                "Could not write the full failure report" in line
                for line in parent.activity_lines
            )
            == 1
        )
        assert not any("Failure report:" in line for line in parent.activity_lines)
        saved = {path: path.read_bytes() for path in output.rglob("*.mp3")}
        assert sorted(saved.values()) == [b"goodafter01", b"goodbefore1"]
    finally:
        runtime.close()

    # Re-open durable state, not the in-memory worker or a synthetic Library row.
    app = qt_app()
    bridge = qt_main.Bridge(None)
    engine = qt_main.create_engine(bridge)
    window = engine.rootObjects()[0]
    try:
        children = {
            job.preview_info["title"]: job
            for job in bridge._runtime.recovered
            if job.exact_item_retry
        }
        verified = children["Failed selection"]
        ambiguous = children["Ambiguous selection"]
        assert verified.url == _ITEM_URL and verified.urls == [_ITEM_URL]
        assert verified.preview_info["playlist_index"] == 2
        assert ambiguous.url == "" and ambiguous.urls == []

        # A forged or accidental manual source cannot bypass the disabled action.
        arbitrary = bridge._runtime.prepare_job(
            watch(_GOOD_AFTER), output, "MP3", "Everyday"
        )
        for unverified_source in (_PLAYLIST, arbitrary.url):
            arbitrary.url = unverified_source
            arbitrary.urls = [unverified_source]
            with pytest.raises(ValueError, match="no verified video link"):
                bridge._runtime.retry_terminal(ambiguous.run_id, current_job=arbitrary)

        window.resize(1100, 760)
        assert bridge.openRunIssues(ambiguous.run_id)
        app.processEvents()
        assert bridge.libraryFolderInspector["retryUnavailable"] is True
        assert (
            "could not confirm this item's link"
            in bridge.libraryFolderInspector["issueMessage"]
        )
        assert "no media formats" in bridge.libraryFolderInspector["issueMessage"]
        retry_button = window.findChild(QObject, "libraryIssueDownload")
        reason = window.findChild(QObject, "libraryIssueReason")
        assert not retry_button.property("visible")
        assert reason.property("visible")
        bridge.setIssueRetrySource(watch(_GOOD_AFTER))
        assert not bridge.downloadSelectedIssue()
        assert bridge._runtime.active_job is None

        assert bridge.openRunIssues(verified.run_id)
        app.processEvents()
        assert retry_button.property("visible")
        assert retry_button.property("label") == "Retry this item"
        assert "YouTube access" not in reason.property("text")
        bridge.setIssueRetryFlag("single_video_only", False)
        assert bridge.libraryFolderInspector["settings"]["single_video_only"] is True
        missing_audio = False

        # Even if the provider resolves the link to another video, only the exact
        # item is eligible to transfer and the failed retry remains exact.
        wrong_video = True
        retry_button.activated.emit()
        [wrong_item] = _settle_worker(bridge._runtime)
        assert "nothing was saved" in wrong_item
        assert transfers == [_GOOD_BEFORE, _GOOD_AFTER]
        verified_again = next(
            job for job in bridge._runtime.recovered if job.exact_item_retry and job.url
        )
        assert verified_again.url == _ITEM_URL
        assert bridge.openRunIssues(verified_again.run_id)
        app.processEvents()
        wrong_video = False
        before = len(analysis_requests)
        retry_button.activated.emit()
        [completed] = _settle_worker(bridge._runtime)
        assert "1 valid output(s)" in completed
        assert playlist_requests == [_PLAYLIST]
        assert analysis_requests[before:] == [_ITEM_URL]
        assert transfers == [_GOOD_BEFORE, _GOOD_AFTER, _FAILED]
        assert {path: path.read_bytes() for path in saved} == saved
        assert sorted(path.read_bytes() for path in output.rglob("*.mp3")) == [
            b"faileditem1",
            b"goodafter01",
            b"goodbefore1",
        ]
        restored = next(row for row in bridge._runtime.history if row["id"] == _FAILED)
        assert restored["playlist_index"] == 2
        assert restored["playlist_title"] == "Fixture playlist"
        assert verified.run_id not in {job.run_id for job in bridge._runtime.recovered}
        assert verified_again.run_id not in {
            job.run_id for job in bridge._runtime.recovered
        }
        assert ambiguous.run_id in {job.run_id for job in bridge._runtime.recovered}
    finally:
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        bridge.close()
