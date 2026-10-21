"""Independent audit regressions: protected bytes and late owned children."""

import json
import subprocess
import threading

import pytest

from yt_downloader import archive_file_operations as ops
from yt_downloader.history import history_archive_owner
from yt_downloader.media_preview import MediaPreviewOwner
from yt_downloader.playback_backend import MediaPlayerError


@pytest.mark.parametrize(
    "stage", ["before_history", "before_source_cleanup", "source_retired"]
)
@pytest.mark.parametrize("mutation", ["remove", "replace"])
def test_move_destination_loss(tmp_path, stage, mutation):
    folder = tmp_path / "source"
    folder.mkdir()
    source = folder / "video.mp4"
    source.write_bytes(b"unique original content")
    item = {
        "id": "fixture",
        "title": "Fixture",
        "vodforge_output_type": "MP4",
        "vodforge_output_path": str(source),
        "vodforge_output_dir": str(folder),
        "vodforge_retry_job": {"output_dir": str(tmp_path)},
        "vodforge_recorded_at": "2026-09-17T00:00:00+00:00",
    }
    destination = tmp_path / "destination"
    destination.mkdir()
    history = tmp_path / "history.json"
    ops._save_durable_history(history, [item])
    plan = ops.plan_move_operation([item], [history_archive_owner(item)], destination)
    target = destination / "source" / "video.mp4"
    fired = False

    def boundary(name):
        nonlocal fired
        if name == stage and not fired:
            fired = True
            target.unlink()
            if mutation == "replace":
                target.write_bytes(b"foreign replacement")

    result = ops.move_files(
        plan,
        [item],
        destination,
        history,
        tmp_path / "file-operations",
        boundary=boundary,
    )
    assert fired
    originals = [
        p
        for p in tmp_path.rglob("*")
        if p.is_file() and p.read_bytes() == b"unique original content"
    ]
    if stage == "source_retired":
        assert originals  # Last original bytes remain protected for recovery
        assert result.outcomes[0][1] == "cleanup_pending"
        assert json.loads(result.journal.read_text())["state"] != "completed"
    else:
        assert source in originals
        assert result.outcomes[0][1] == "cleanup_pending"
    if mutation == "replace":
        assert target.read_bytes() == b"foreign replacement"


class Child:
    def __init__(self, refuses):
        self.returncode = None
        self.refuses = refuses
        self.terminate_calls = self.kill_calls = self.communicate_calls = 0

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminate_calls += 1
        if not self.refuses:
            self.returncode = -15
        else:
            raise PermissionError("fixture deny terminate")

    def kill(self):
        self.kill_calls += 1
        if not self.refuses:
            self.returncode = -9
        else:
            raise PermissionError("fixture deny kill")

    def wait(self, timeout):
        if self.returncode is None:
            raise subprocess.TimeoutExpired("fixture", timeout)
        return self.returncode

    def communicate(self, timeout):
        self.communicate_calls += 1
        return b"old preview", b""


@pytest.mark.parametrize("transition", ["shutdown", "switch"])
@pytest.mark.parametrize("refuses", [False, True])
def test_preview_late_popen_child_ownership(tmp_path, transition, refuses):
    old = tmp_path / "old.mp4"
    old.write_bytes(b"old")
    new = tmp_path / "new.mp4"
    new.write_bytes(b"new")
    entered, release = threading.Event(), threading.Event()
    child = Child(refuses)
    diagnostics, errors = [], []

    def popen(*a, **kw):
        entered.set()
        assert release.wait(3)
        return child

    owner = MediaPreviewOwner(
        ffmpeg="unused", popen=popen, diagnostic=diagnostics.append
    )
    owner.load(old)

    def run():
        try:
            owner.preview_png(2, expected_path=old)
        except Exception as exc:  # noqa: BLE001 - capture the thread boundary, then assert the exact failure type
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    try:
        assert entered.wait(2)
        if transition == "shutdown":
            owner.shutdown()
        else:
            owner.load(new)
        release.set()
        worker.join(3)
        assert not worker.is_alive()
        assert len(errors) == 1 and isinstance(errors[0], MediaPlayerError)
        assert not owner._cache and child.communicate_calls == 0
        assert child.terminate_calls == 1
        if refuses:
            assert child.poll() is None
            assert child in owner._registry.processes
            assert any("remains registered" in d for d in diagnostics)
            owner.shutdown()
            assert child.terminate_calls == 2
        else:
            assert child.poll() is not None and not owner._registry.processes
    finally:
        release.set()
        worker.join(3)
        child.refuses = False
        child.terminate()
        owner.shutdown()


@pytest.mark.parametrize("transition", ["shutdown", "switch"])
def test_real_child_returning_after_invalidation_is_reaped(tmp_path, transition):
    import sys

    old = tmp_path / "old.mp4"
    old.write_bytes(b"old")
    new = tmp_path / "new.mp4"
    new.write_bytes(b"new")
    entered, release = threading.Event(), threading.Event()
    children, errors = [], []

    def popen(*a, **kw):
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        children.append(process)
        entered.set()
        assert release.wait(3)
        return process

    owner = MediaPreviewOwner(ffmpeg="unused", popen=popen)
    owner.load(old)

    def run():
        try:
            owner.preview_png(1, expected_path=old)
        except Exception as exc:  # noqa: BLE001 - capture the thread boundary, then assert the exact failure type
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    try:
        assert entered.wait(2) and children[0].poll() is None
        if transition == "shutdown":
            owner.shutdown()
        else:
            owner.load(new)
        release.set()
        worker.join(4)
        assert not worker.is_alive() and children[0].poll() is not None
        assert len(errors) == 1 and isinstance(errors[0], MediaPlayerError)
        assert not owner._registry.processes and not owner._cache
    finally:
        release.set()
        worker.join(4)
        for child in children:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=3)
            if child.stdout:
                child.stdout.close()
        owner.shutdown()


@pytest.mark.parametrize("stage", ["before_history", "history_saved"])
def test_library_move_close_at_publication_reconciles_real_history(
    tmp_path, monkeypatch, stage
):
    from yt_downloader.qt_quick import library_files as ui

    source = tmp_path / "source" / "video.mp4"
    source.parent.mkdir()
    source.write_bytes(b"original")
    destination = tmp_path / "destination"
    destination.mkdir()
    record = {
        "id": "fixture",
        "title": "Fixture",
        "vodforge_output_type": "MP4",
        "vodforge_output_path": str(source),
        "vodforge_output_dir": str(source.parent),
        "vodforge_retry_job": {"output_dir": str(tmp_path)},
    }
    history = tmp_path / "history.json"
    ops._save_durable_history(history, [record])
    owner = ui.QtLibraryFiles(history)
    entered, release = threading.Event(), threading.Event()
    actual_move = ui.move_files

    def boundary(name):
        if name == stage:
            entered.set()
            assert release.wait(3)

    def move(*a, **kw):
        return actual_move(*a, **kw, boundary=boundary)

    monkeypatch.setattr(ui, "move_files", move)
    assert owner.begin(
        "move", history_archive_owner(record), [record], destination=destination
    )
    owner.worker.join(3)
    owner.poll()
    assert owner.phase == "preview"
    assert owner.confirm([record])
    closer = None
    try:
        assert entered.wait(2)
        closer = threading.Thread(target=owner.close)
        closer.start()
        assert owner.cancelled.wait(2)
        release.set()
        closer.join(3)
        assert not closer.is_alive() and not owner.busy
        owner.poll()
        assert owner.phase == "recovery" and owner.pending and owner.uncertain
        assert owner.latest_history == json.loads(history.read_text())["items"]
        assert source.read_bytes() == b"original"
        target = destination / "source" / "video.mp4"
        assert target.read_bytes() == b"original"
        assert owner.latest_history[0]["vodforge_output_path"] == str(target)
    finally:
        release.set()
        if closer:
            closer.join(3)
        owner.close()
