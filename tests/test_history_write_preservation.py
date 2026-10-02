from pathlib import Path

import pytest

from yt_downloader.history import HistoryError, load_history, save_history


@pytest.mark.parametrize(
    "damaged",
    [
        b"broken json",
        b'{"schema_version":999,"items":[]}',
        b'{"schema_version":1,"items":{}}',
        b"\xff",
    ],
)
def test_corruption_after_successful_load_blocks_later_history_write(tmp_path, damaged):
    path = tmp_path / "download-history.json"
    save_history(path, [])
    cached = load_history(path)
    path.write_bytes(damaged)
    with pytest.raises(HistoryError):
        save_history(path, cached)
    assert path.read_bytes() == damaged
    assert not path.with_name(f".{path.name}.tmp").exists()


def test_unreadable_existing_history_blocks_write(tmp_path, monkeypatch):
    path = tmp_path / "download-history.json"
    save_history(path, [])
    original = path.read_bytes()
    read = Path.read_text

    def denied(target, *args, **kwargs):
        if target == path:
            raise PermissionError("fictional inaccessible ledger")
        return read(target, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", denied)
    with pytest.raises(HistoryError):
        save_history(path, [])
    assert path.read_bytes() == original


def test_absent_and_valid_existing_history_allow_normal_writes(tmp_path):
    path = tmp_path / "download-history.json"
    save_history(path, [])
    save_history(path, [])
    assert load_history(path) == []
