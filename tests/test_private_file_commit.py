"""Private document replacement keeps prior accepted intent until full commit."""

import errno
import os
import stat
from contextlib import contextmanager

import pytest

from yt_downloader import private_files


@pytest.mark.parametrize("fault", ["partial", "short", "flush", "fsync", "replace"])
def test_precommit_failure_keeps_old_document_and_cleans_own_stage(
    tmp_path, monkeypatch, fault
):
    path = tmp_path / "document.json"
    private_files.write_private_bytes(path, b"previous valid document")
    real_open = private_files.open_private_binary_file

    @contextmanager
    def faulty_open(target, **kwargs):
        with real_open(target, **kwargs) as stream:

            class Fault:
                def fileno(self):
                    return stream.fileno()

                def write(self, data):
                    if fault in {"partial", "short"}:
                        stream.write(data[:4])
                        stream.flush()
                        if fault == "partial":
                            raise OSError(errno.ENOSPC, "fixture disk full")
                        return 4
                    return stream.write(data)

                def flush(self):
                    if fault == "flush":
                        raise OSError(errno.EIO, "fixture flush failure")
                    return stream.flush()

            yield Fault()

    monkeypatch.setattr(private_files, "open_private_binary_file", faulty_open)

    def fail(*a, **kw):
        raise OSError(errno.EIO, "fixture commit failure")

    if fault == "fsync":
        monkeypatch.setattr(os, "fsync", fail)
    if fault == "replace":
        monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        private_files.write_private_bytes(path, b"new replacement document")
    assert path.read_bytes() == b"previous valid document"
    assert list(tmp_path.iterdir()) == [path]


def test_document_replacement_and_append_keep_private_permissions(tmp_path):
    path = tmp_path / "document"
    private_files.write_private_bytes(path, b"first")
    private_files.write_private_bytes(path, b"second")
    with private_files.open_private_binary_file(path) as stream:
        stream.write(b"+append")
    assert path.read_bytes() == b"second+append"
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.skipif(
    os.name == "nt", reason="Windows does not expose POSIX directory fsync"
)
def test_directory_sync_failure_reports_uncertain_commit_without_destroying_document(
    tmp_path, monkeypatch
):
    path = tmp_path / "document"
    private_files.write_private_bytes(path, b"old")
    sync = os.fsync

    def fail_directory(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(errno.EIO, "fixture directory sync failure")
        return sync(fd)

    monkeypatch.setattr(os, "fsync", fail_directory)
    with pytest.raises(OSError):
        private_files.write_private_bytes(path, b"complete new document")
    assert path.read_bytes() == b"complete new document"
    assert list(tmp_path.iterdir()) == [path]


def test_changed_destination_is_not_overwritten(tmp_path, monkeypatch):
    path = tmp_path / "document"
    private_files.write_private_bytes(path, b"old")
    real_sync = os.fsync

    def change_after_file_sync(fd):
        result = real_sync(fd)
        if stat.S_ISREG(os.fstat(fd).st_mode):
            other = tmp_path / "other"
            other.write_bytes(b"new independent owner")
            os.replace(other, path)
        return result

    monkeypatch.setattr(os, "fsync", change_after_file_sync)
    with pytest.raises(OSError):
        private_files.write_private_bytes(path, b"stale candidate")
    assert path.read_bytes() == b"new independent owner"
    assert list(tmp_path.iterdir()) == [path]


def test_nonregular_destination_is_refused(tmp_path):
    path = tmp_path / "directory"
    path.mkdir()
    with pytest.raises(OSError):
        private_files.write_private_bytes(path, b"no")
    assert path.is_dir()


@pytest.mark.skipif(
    os.name == "nt", reason="No symlink privilege changes for this test"
)
def test_redirect_destination_is_refused(tmp_path):
    target = tmp_path / "target"
    target.write_bytes(b"untouched")
    path = tmp_path / "document"
    path.symlink_to(target)
    with pytest.raises(OSError):
        private_files.write_private_bytes(path, b"no")
    assert target.read_bytes() == b"untouched" and path.is_symlink()
