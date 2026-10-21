"""Media probe results must belong to the same file at publication."""

import json
import os
import threading
from types import SimpleNamespace

import pytest

from yt_downloader import library_import


def probe_result():
    return SimpleNamespace(
        returncode=0,
        stdout=json.dumps(
            {
                "streams": [{"codec_type": "video", "width": 1920, "height": 1080}],
                "format": {"duration": "90"},
            }
        ).encode(),
    )


def replace_same_size_time(path):
    old = path.stat()
    replacement = path.with_suffix(".replacement")
    replacement.write_bytes(b"new-file-bytes")
    os.utime(replacement, ns=(old.st_atime_ns, old.st_mtime_ns))
    replacement.replace(path)
    assert path.stat().st_ino != old.st_ino


def test_replacement_during_probe_rejects_stale_metadata(tmp_path, monkeypatch):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"old-file-bytes")
    monkeypatch.setattr(
        library_import, "find_runtime_executable", lambda _: "fixture-ffprobe"
    )

    def probe(*a, **kw):
        replace_same_size_time(path)
        return probe_result()

    monkeypatch.setattr(library_import.subprocess, "run", probe)
    with pytest.raises(ValueError, match="changed"):
        library_import.inspect_local_media(path, threading.Event())
    assert path.read_bytes() == b"new-file-bytes"


@pytest.mark.parametrize("replace_before_commit", [False, True])
def test_publication_revalidates_inspected_file_without_saving_internal_token(
    tmp_path, monkeypatch, replace_before_commit
):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"old-file-bytes")
    monkeypatch.setattr(
        library_import, "find_runtime_executable", lambda _: "fixture-ffprobe"
    )
    monkeypatch.setattr(
        library_import.subprocess, "run", lambda *a, **kw: probe_result()
    )
    record = library_import.inspect_local_media(path, threading.Event())
    writes = []
    if replace_before_commit:
        replace_same_size_time(path)

    def commit():
        return library_import.commit_imports(
            [],
            [record],
            tmp_path / "history.json",
            save=lambda p, rows: writes.append(rows),
        )

    if replace_before_commit:
        with pytest.raises(ValueError, match="changed"):
            commit()
        assert writes == []
    else:
        rows = commit()
        assert len(rows) == 1 and len(writes) == 1
        assert "_import_fingerprint" not in rows[0]
