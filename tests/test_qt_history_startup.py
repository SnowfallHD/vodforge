"""Qt startup retains damaged ledgers and blocks new durable work."""

import pytest

from tests.worker_fixtures import _worker_test_job
from yt_downloader.history import pending_history_path, save_history
from yt_downloader.qt_quick import runtime as module
from yt_downloader.run_state import RunStateError


@pytest.mark.parametrize(
    "cause", ["invalid_record", "journal_write_failed", "missing_retry_url"]
)
def test_admission_guidance_uses_failure_owner_without_private_error_text(cause):
    from yt_downloader.run_state import run_admission_failure_message

    error = RunStateError("PRIVATE /secret/path https://private.example", cause=cause)
    ledger = run_admission_failure_message(error, history_recovery_required=True)
    assert "Restore compatible Library data" in ledger
    ordinary = run_admission_failure_message(error)
    assert "Restore compatible" not in ordinary
    assert ("valid web link" in ordinary) == (cause == "missing_retry_url")
    assert ("disk space" in ordinary) == (cause != "missing_retry_url")
    for message in (ledger, ordinary):
        assert "PRIVATE" not in message
        assert "/secret/path" not in message
        assert "https://" not in message


@pytest.mark.parametrize(
    "document,raw",
    [
        ("main", b'{"PRIVATE":'),
        ("main", b'{"schema_version":999,"items":[]}'),
        ("pending", b'{"PRIVATE":'),
    ],
)
def test_bridge_damaged_ledger_admission_reports_compatible_restoration(
    tmp_path, monkeypatch, document, raw
):
    from tests.test_qt_scene_port import qt_app
    from yt_downloader.qt_quick import main as qt_main

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    (tmp_path / "Downloads").mkdir()
    path = tmp_path / "history.json"
    damaged = path if document == "main" else pending_history_path(path)
    damaged.write_bytes(raw)
    before = damaged.stat().st_mtime_ns
    monkeypatch.setattr(module, "history_file_path", lambda: path)
    monkeypatch.setattr(module, "run_state_file_path", lambda: tmp_path / "active.json")
    qt_app()
    bridge = qt_main.Bridge(None)
    try:
        assert not bridge.submit("https://example.com/video", "MP4")
        assert "Restore compatible Library data" in bridge.status
        assert "disk space" not in bridge.status
        assert "PRIVATE" not in bridge.status
        assert bridge._runtime.worker is None
        assert damaged.read_bytes() == raw
        assert damaged.stat().st_mtime_ns == before
    finally:
        bridge.close()


@pytest.mark.parametrize(
    "document,raw",
    [
        ("main", b'{"PRIVATE":'),
        ("main", b'{"schema_version":999,"items":[]}'),
        ("pending", b'{"PRIVATE":'),
    ],
)
def test_damaged_history_keeps_runtime_available_but_refuses_new_work(
    tmp_path, monkeypatch, document, raw
):
    path = tmp_path / "history.json"
    damaged = path if document == "main" else pending_history_path(path)
    damaged.write_bytes(raw)
    monkeypatch.setattr(module, "history_file_path", lambda: path)
    monkeypatch.setattr(module, "run_state_file_path", lambda: tmp_path / "active.json")
    runtime = module.DownloadRuntime()
    try:
        assert runtime.history == []
        assert runtime.recovery_notice
        assert "PRIVATE" not in runtime.recovery_notice
        with pytest.raises(RunStateError):
            runtime.start_job(_worker_test_job(tmp_path))
        assert runtime.worker is None
        assert damaged.read_bytes() == raw
    finally:
        runtime.close()


@pytest.mark.parametrize("existing", [False, True])
def test_absent_or_valid_history_retains_normal_admission(
    tmp_path, monkeypatch, existing
):
    path = tmp_path / "history.json"
    if existing:
        save_history(path, [])
    monkeypatch.setattr(module, "history_file_path", lambda: path)
    monkeypatch.setattr(module, "run_state_file_path", lambda: tmp_path / "active.json")
    runtime = module.DownloadRuntime()
    try:
        assert runtime.history == []
        assert runtime.recovery_notice is None
    finally:
        runtime.close()
