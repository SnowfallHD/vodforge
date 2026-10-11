"""Qt startup retains damaged ledgers and blocks new durable work."""

import pytest

from tests.worker_fixtures import _worker_test_job
from yt_downloader.history import pending_history_path, save_history
from yt_downloader.qt_quick import runtime as module
from yt_downloader.run_state import RunStateError


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
