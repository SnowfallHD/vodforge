import io
import json
import time
from dataclasses import replace
from threading import Event

import pytest
from PIL import Image

from tests.test_qt_scene_port import qt_app
from tests.test_run_identity import make_job
from yt_downloader.qt_quick import sidecar_recovery as recovery
from yt_downloader.qt_quick.main import Bridge

MESSAGE = (
    "MP4 completed with issues — 1 valid output(s), 0 failed, 0 skipped, "
    "2 optional sidecar failure(s). Keep the valid files. Review Technical "
    "details for each issue and its next step."
)


def fixture(tmp_path):
    media = tmp_path / "video.mp4"
    media.write_bytes(b"validated media must never be encoded or replaced")
    job = replace(
        make_job(tmp_path),
        write_thumbnail=True,
        terminal_status="Partial",
        terminal_message=MESSAGE,
    )
    info = {
        "id": "fixture",
        "title": "same",
        "vodforge_run_id": job.run_id,
        "vodforge_output_type": "MP4",
        "vodforge_output_path": str(media),
        "vodforge_output_dir": str(tmp_path),
        "thumbnail": "https://i.ytimg.com/vi/fixture/default.jpg",
        "vodforge_encoding_summary": {"output": {"Validation status": "Validated"}},
    }
    (tmp_path / "metadata.json").write_text(json.dumps({"id": "fixture"}))
    return job, info, media


def image_bytes():
    stream = io.BytesIO()
    Image.new("RGB", (32, 18), "blue").save(stream, "JPEG")
    return stream.getvalue()


def test_bridge_real_retry_route_repairs_only_artwork_and_coalesces_exact_owner(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = Bridge(None)
    job, info, media = fixture(tmp_path)
    runtime = bridge._runtime
    runtime.history = [info]
    runtime.recovery.terminal_attempt(job, "Partial", MESSAGE)
    runtime.recovered = runtime.recovery.store.load_terminal_jobs()
    before = (
        media.read_bytes(),
        (tmp_path / "metadata.json").read_bytes(),
        json.dumps(runtime.history),
    )
    calls = []
    monkeypatch.setattr(
        recovery.service,
        "download_bounded_url_bytes",
        lambda *a, **k: calls.append(1) or image_bytes(),
    )
    monkeypatch.setattr(
        runtime, "retry_terminal", lambda *a, **k: pytest.fail("media retry forbidden")
    )
    monkeypatch.setattr(
        runtime, "prepare_job", lambda *a, **k: pytest.fail("source analysis forbidden")
    )
    monkeypatch.setattr(bridge._artwork, "request", lambda *a, **k: "")
    try:
        records = bridge.runDeck["records"]
        assert len(records) == 1
        assert records[0]["retrySidecarsOnly"] is True
        assert records[0]["retryLabel"] == "Retry artwork"
        feedback = []
        bridge.operationFeedback.connect(feedback.append)
        assert bridge.openRunIssues(job.run_id) is True
        assert len(bridge._folder_browser.components) == 1
        assert bridge.libraryFolderInspector["sidecarsOnly"] is True
        assert bridge.libraryFolderInspector["retryLabel"] == "Retry artwork"
        assert (
            bridge.libraryFolderInspector["keepLabel"] == "Keep video without thumbnail"
        )
        assert bridge.inspectorRecoveryActions["dismissRunId"] == job.run_id
        assert bridge.inspectorRecoveryActions["canOpenLocation"] is True
        assert bridge.inspectorRecoveryActions["location"] == str(tmp_path)
        assert bridge.downloadSelectedIssue() is True
        assert bridge.status == "Recovering optional files; saved video is unchanged."
        assert feedback[-1] == bridge.status
        assert bridge.retryTerminal(job.run_id) is False  # no queued duplicate
        deadline = time.monotonic() + 3
        while bridge._sidecar_target is not None and time.monotonic() < deadline:
            bridge._pump()
            time.sleep(0.005)
        assert runtime.recovered == []
        assert calls == [1]
        assert (tmp_path / "thumbnail.jpeg").is_file()
        assert before == (
            media.read_bytes(),
            (tmp_path / "metadata.json").read_bytes(),
            json.dumps(runtime.history),
        )
        assert len(bridge.runDeck["records"]) == 1
        assert bridge.runDeck["records"][0]["kind"] == "completed"
    finally:
        bridge.close()


@pytest.mark.parametrize(
    "change",
    ["batch", "incomplete", "truncated", "duplicate", "unvalidated", "symlink"],
)
def test_incomplete_or_ambiguous_evidence_never_admits_sidecar_repair(tmp_path, change):
    job, info, media = fixture(tmp_path)
    history = [info]
    if change == "batch":
        job.batch_mode = True
    if change == "incomplete":
        job.terminal_message = MESSAGE.replace("0 failed", "1 failed")
    if change == "truncated":
        job.terminal_message = MESSAGE[:100]
    if change == "duplicate":
        history.append(dict(info))
    if change == "unvalidated":
        info["vodforge_encoding_summary"] = {}
    if change == "symlink":
        media.rename(tmp_path / "original.mp4")
        media.symlink_to(tmp_path / "original.mp4")
    assert recovery.optional_target(job, history) is None


@pytest.mark.parametrize("stop", ["cancel", "changed_media", "fetch_error"])
def test_delayed_fetch_cannot_write_after_cancellation_or_owner_change(
    tmp_path, monkeypatch, stop
):
    job, info, media = fixture(tmp_path)
    target = recovery.optional_target(job, [info])
    cancelled = Event()

    def fetch(*a, **k):
        if stop == "cancel":
            cancelled.set()
        elif stop == "changed_media":
            media.write_bytes(b"new owner")
        else:
            raise OSError("fixture failure")
        return image_bytes()

    monkeypatch.setattr(recovery.service, "download_bounded_url_bytes", fetch)
    with pytest.raises((RuntimeError, OSError)):
        recovery.repair_sidecars(target, tmp_path / "profile", cancelled)
    assert not (tmp_path / "thumbnail.jpeg").exists()
    assert not (tmp_path / "profile" / "thumbnail-cache").exists()


def test_cached_artwork_avoids_fetch_and_preserves_existing_files(
    tmp_path, monkeypatch
):
    job, info, _media = fixture(tmp_path)
    data_dir = tmp_path / "profile"
    recovery.service.save_cached_thumbnail_bytes(info, image_bytes(), data_dir=data_dir)
    target = recovery.optional_target(job, [info])
    monkeypatch.setattr(
        recovery.service,
        "download_bounded_url_bytes",
        lambda *a, **k: pytest.fail("warm cache must not fetch"),
    )
    assert recovery.repair_sidecars(target, data_dir, Event())
    before = (tmp_path / "thumbnail.jpeg").read_bytes()
    assert recovery.repair_sidecars(target, data_dir, Event())
    assert (tmp_path / "thumbnail.jpeg").read_bytes() == before


@pytest.mark.parametrize(
    "change", ["active", "queued", "stale_history", "missing_media"]
)
def test_bridge_admission_refuses_busy_or_changed_optional_owner(
    tmp_path, monkeypatch, change
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = Bridge(None)
    job, info, media = fixture(tmp_path)
    bridge._runtime.history = [info]
    bridge._runtime.recovered = [job]
    if change == "active":
        bridge._runtime.active_job = replace(job, run_id="other")
    if change == "queued":
        bridge._runtime.queued = [replace(job, run_id="other")]
    if change == "stale_history":
        info["vodforge_run_id"] = "other"
    if change == "missing_media":
        media.unlink()
    monkeypatch.setattr(
        bridge._runtime,
        "retry_terminal",
        lambda *a, **k: pytest.fail("full retry forbidden"),
    )
    try:
        assert bridge.retryTerminal(job.run_id) is False
        assert not bridge._sidecar_work.busy
        assert bridge._runtime.recovered == [job]
    finally:
        bridge._runtime.active_job = None
        bridge._runtime.queued = []
        bridge.close()


def test_missing_metadata_is_recovered_without_replacing_media(tmp_path, monkeypatch):
    job, info, media = fixture(tmp_path)
    (tmp_path / "metadata.json").unlink()
    target = recovery.optional_target(job, [info])
    assert target.label == "Retry files"
    monkeypatch.setattr(
        recovery.service, "download_bounded_url_bytes", lambda *a, **k: image_bytes()
    )
    before = media.read_bytes()
    assert recovery.repair_sidecars(target, tmp_path / "profile", Event())
    assert json.loads((tmp_path / "metadata.json").read_text())["id"] == "fixture"
    assert media.read_bytes() == before


def test_changed_history_after_fetch_refuses_all_writes(tmp_path, monkeypatch):
    job, info, _media = fixture(tmp_path)
    history = [info]
    target = recovery.optional_target(job, history)

    def fetch(*a, **k):
        info["title"] = "changed binding"
        return image_bytes()

    monkeypatch.setattr(recovery.service, "download_bounded_url_bytes", fetch)
    with pytest.raises(RuntimeError):
        recovery.repair_sidecars(
            target,
            tmp_path / "profile",
            Event(),
            current=lambda: recovery.target_current(target, history),
        )
    assert not (tmp_path / "thumbnail.jpeg").exists()
    assert not (tmp_path / "profile").exists()


def test_success_receipt_refuses_deleted_artifact_before_warning_clear(
    tmp_path, monkeypatch
):
    job, info, _media = fixture(tmp_path)
    target = recovery.optional_target(job, [info])
    monkeypatch.setattr(
        recovery.service, "download_bounded_url_bytes", lambda *a, **k: image_bytes()
    )
    receipt = recovery.repair_sidecars(target, tmp_path / "profile", Event())
    assert receipt.unchanged()
    (tmp_path / "thumbnail.jpeg").unlink()
    assert not receipt.unchanged()


def test_failed_fetch_keeps_warning_and_allows_one_explicit_retry(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = Bridge(None)
    job, info, media = fixture(tmp_path)
    bridge._runtime.history = [info]
    bridge._runtime.recovery.terminal_attempt(job, "Partial", MESSAGE)
    bridge._runtime.recovered = bridge._runtime.recovery.store.load_terminal_jobs()
    calls = []

    def fetch(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("controlled unavailable artwork")
        return image_bytes()

    monkeypatch.setattr(recovery.service, "download_bounded_url_bytes", fetch)
    try:
        for attempt in range(2):
            assert bridge.retryTerminal(job.run_id)
            deadline = time.monotonic() + 3
            while bridge._sidecar_target is not None and time.monotonic() < deadline:
                bridge._pump()
                time.sleep(0.005)
            if attempt == 0:
                assert len(bridge._runtime.recovered) == 1
                assert "issue are retained" in bridge.status
                assert not (tmp_path / "thumbnail.jpeg").exists()
        assert len(calls) == 2
        assert bridge._runtime.recovered == []
        assert (
            media.read_bytes() == b"validated media must never be encoded or replaced"
        )
    finally:
        bridge.close()


def test_close_retires_delayed_fetch_without_optional_writes(tmp_path, monkeypatch):
    from threading import Event

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = Bridge(None)
    job, info, _media = fixture(tmp_path)
    bridge._runtime.history = [info]
    bridge._runtime.recovered = [job]
    started, release, finished = Event(), Event(), Event()

    def fetch(*a, **k):
        started.set()
        release.wait(3)
        finished.set()
        return image_bytes()

    monkeypatch.setattr(recovery.service, "download_bounded_url_bytes", fetch)
    try:
        assert bridge.retryTerminal(job.run_id)
        assert started.wait(2)
        bridge.close()
        release.set()
        assert finished.wait(2)
        deadline = time.monotonic() + 2
        while bridge._sidecar_work.busy and time.monotonic() < deadline:
            time.sleep(0.005)
        assert not (tmp_path / "thumbnail.jpeg").exists()
        assert bridge._sidecar_work.poll() is None
        assert bridge._runtime.recovered == [job]
    finally:
        release.set()
        bridge.close()


def test_genuine_partial_batch_retains_saved_card_and_issue(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = Bridge(None)
    job, info, _media = fixture(tmp_path)
    job.batch_mode = True
    bridge._runtime.history = [info]
    bridge._runtime.recovered = [job]
    bridge._runtime.active_job = replace(job, run_id="other-active")
    monkeypatch.setattr(bridge._artwork, "request", lambda *a, **k: "")
    try:
        records = bridge.runDeck["records"]
        assert len([r for r in records if r["kind"] == "completed"]) == 1
        terminal = next(r for r in records if r["kind"] == "terminal")
        assert terminal["retrySidecarsOnly"] is False
        assert terminal["retryEnabled"] is True  # genuine retry may join queue
        assert bridge._runtime.history == [info]
    finally:
        bridge._runtime.active_job = None
        bridge.close()


@pytest.mark.parametrize("summary", [None, [], {"output": None}, {"output": []}])
def test_malformed_legacy_validation_fails_closed(tmp_path, summary):
    job, info, _media = fixture(tmp_path)
    info["vodforge_encoding_summary"] = summary
    assert recovery.optional_target(job, [info]) is None


@pytest.mark.parametrize(
    "field,value",
    [("output_type", "MP3"), ("batch_mode", True), ("single_video_only", False)],
)
def test_changed_eligibility_during_fetch_refuses_writes(
    tmp_path, monkeypatch, field, value
):
    job, info, _media = fixture(tmp_path)
    target = recovery.optional_target(job, [info])

    def fetch(*a, **k):
        setattr(job, field, value)
        return image_bytes()

    monkeypatch.setattr(recovery.service, "download_bounded_url_bytes", fetch)
    with pytest.raises(RuntimeError):
        recovery.repair_sidecars(target, tmp_path / "profile", Event())
    assert not (tmp_path / "thumbnail.jpeg").exists()
    assert not (tmp_path / "profile").exists()


@pytest.mark.parametrize("legacy", [False, True])
def test_saved_completed_rows_survive_optional_issue_coalescing(
    tmp_path, monkeypatch, legacy
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = Bridge(None)
    job, info, media = fixture(tmp_path)
    completed = dict(
        info,
        id="other",
        vodforge_run_id="other-run",
        vodforge_output_path=str(tmp_path / "other.mp4"),
    )
    if legacy:
        completed.pop("vodforge_run_id")
    (tmp_path / "other.mp4").write_bytes(b"other completed media")
    bridge._runtime.history = [info, completed]
    bridge._runtime.recovery.terminal_attempt(job, "Partial", MESSAGE)
    bridge._runtime.recovered = bridge._runtime.recovery.store.load_terminal_jobs()
    monkeypatch.setattr(bridge._artwork, "request", lambda *a, **k: "")
    try:
        records = bridge.runDeck["records"]
        assert len(records) == 2
        assert sum(r["kind"] == "completed" for r in records) == 1
        assert sum(r.get("retrySidecarsOnly", False) for r in records) == 1
        assert len(bridge._projected_library()) == 2
        assert bridge.openRunIssues(job.run_id)
        assert len(bridge._folder_browser.components) == 1
        assert "vodforge_optional_issue_run_id" not in info
        assert "vodforge_optional_issue_run_id" not in completed
        # Dismissing the attempt must leave the saved video available as completed.
        assert bridge.dismissOptionalIssue(
            bridge.inspectorRecoveryActions["selectionKey"]
        )
        assert (
            media.read_bytes() == b"validated media must never be encoded or replaced"
        )
        assert len(bridge._runtime.history) == 2
        assert bridge._runtime.recovery.store.load_terminal_jobs() == []
        records = bridge.runDeck["records"]
        assert len(records) == 2
        assert all(r["kind"] == "completed" for r in records)
    finally:
        bridge.close()


def test_optional_issue_does_not_retry_media_after_saved_file_disappears(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = Bridge(None)
    job, info, media = fixture(tmp_path)
    bridge._runtime.history = [info]
    bridge._runtime.recovered = [job]
    monkeypatch.setattr(bridge._artwork, "request", lambda *a, **k: "")
    monkeypatch.setattr(
        bridge._runtime,
        "retry_terminal",
        lambda *a, **k: pytest.fail("media retry forbidden"),
    )
    try:
        assert bridge.openRunIssues(job.run_id)
        media.unlink()
        assert bridge.downloadSelectedIssue() is False
        assert (
            bridge.dismissOptionalIssue(
                bridge.inspectorRecoveryActions.get("selectionKey", "")
            )
            is False
        )
        assert bridge._runtime.recovered == [job]
    finally:
        bridge.close()


@pytest.mark.parametrize(
    "metadata_missing,thumbnail_missing,expected",
    [
        (False, True, "Keep video without thumbnail"),
        (True, False, "Keep video without metadata file"),
        (True, True, "Keep video without thumbnail and metadata file"),
        (False, False, "Keep saved video"),
    ],
)
def test_keep_intent_names_only_actually_missing_optional_files(
    tmp_path, metadata_missing, thumbnail_missing, expected
):
    job, info, _media = fixture(tmp_path)
    job = replace(job, write_info_json=True)
    if metadata_missing:
        (tmp_path / "metadata.json").unlink()
    if not thumbnail_missing:
        (tmp_path / "thumbnail.jpeg").write_bytes(image_bytes())
    target = recovery.optional_target(job, [info])
    assert target is not None
    assert target.keep_label == expected


def test_keep_video_restores_one_completed_card_after_restart(tmp_path, monkeypatch):
    from yt_downloader.history import save_history

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    qt_app()
    bridge = Bridge(None)
    job, info, media = fixture(tmp_path)
    bridge._runtime.history = [info]
    save_history(bridge._runtime.history_path, [info])
    bridge._runtime.recovery.terminal_attempt(job, "Partial", MESSAGE)
    bridge._runtime.recovered = bridge._runtime.recovery.store.load_terminal_jobs()
    history_path = bridge._runtime.history_path
    before = (
        media.read_bytes(),
        (tmp_path / "metadata.json").read_bytes(),
        history_path.read_bytes(),
    )
    monkeypatch.setattr(bridge._artwork, "request", lambda *a, **k: "")
    try:
        assert len(bridge.runDeck["records"]) == 1
        assert bridge.runDeck["records"][0]["status"] == "Partial"
        assert bridge.openRunIssues(job.run_id)
        assert (
            bridge.libraryFolderInspector["keepLabel"] == "Keep video without thumbnail"
        )
        assert bridge.dismissOptionalIssue(
            bridge.inspectorRecoveryActions["selectionKey"]
        )
        rows = bridge.runDeck["records"]
        assert len(rows) == 1 and rows[0]["kind"] == "completed"
        assert rows[0]["status"] == "Completed  •  MP4"
        assert not (tmp_path / "thumbnail.jpeg").exists()
        assert before == (
            media.read_bytes(),
            (tmp_path / "metadata.json").read_bytes(),
            history_path.read_bytes(),
        )
    finally:
        bridge.close()
    restarted = Bridge(None)
    monkeypatch.setattr(restarted._artwork, "request", lambda *a, **k: "")
    try:
        rows = restarted.runDeck["records"]
        assert len(rows) == 1 and rows[0]["kind"] == "completed"
        assert rows[0]["status"] == "Completed  •  MP4"
        assert restarted._runtime.recovered == []
        restarted.select("Library")
        restarted.navigateLibraryFolders("issues")
        assert not restarted._folder_browser.components
        assert history_path.read_bytes() == before[2]
    finally:
        restarted.close()
