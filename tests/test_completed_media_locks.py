"""Synthetic Windows sharing errors; no native Windows or provider calls."""

import pytest

from tests.test_metadata_helpers import (
    _worker_test_app,
    _worker_test_export_plan,
    _worker_test_job,
)
from yt_downloader import app as app_module
from yt_downloader import safe_output


def sharing_error(code=32):
    error = PermissionError("synthetic file held by another process")
    error.winerror = code
    return error


@pytest.mark.parametrize("folder", ["Downloads", "OneDrive - Synthetic/Downloads"])
def test_transient_sharing_error_retries_same_verified_commit(
    tmp_path, monkeypatch, folder
):
    root = tmp_path / folder
    root.mkdir(parents=True)
    source = tmp_path / "finished.mp4"
    source.write_bytes(b"validated media")
    original = safe_output._commit_windows
    calls = []

    def commit(*args):
        calls.append(args[3])
        if len(calls) == 1:
            raise sharing_error()
        return original(*args)

    monkeypatch.setattr(safe_output.os, "supports_dir_fd", set())
    monkeypatch.setattr(safe_output, "_commit_windows", commit)
    if hasattr(safe_output, "time"):
        monkeypatch.setattr(safe_output.time, "sleep", lambda _: None)
    target = root / "Creator" / "finished.mp4"
    assert (
        safe_output.commit_file_beneath(source, root, target, replace_existing=False)
        == target
    )
    assert calls == [target, target]
    assert target.read_bytes() == b"validated media"
    assert not source.exists()


@pytest.mark.parametrize(
    "code,preserve,phase",
    [
        (32, True, "commit"),
        (33, True, "commit"),
        (5, False, "commit"),
        (32, False, "validation"),
    ],
)
def test_failed_commit_retains_only_validated_sharing_locked_media(
    tmp_path, monkeypatch, code, preserve, phase
):
    monkeypatch.setattr(app_module, "load_yt_dlp", lambda: object())
    monkeypatch.setattr(app_module, "write_diagnostic", lambda _: None)
    worker = _worker_test_app()
    info = {
        "id": "synthetic",
        "title": "Synthetic",
        "webpage_url": "https://example.invalid/synthetic",
    }
    worker._expand_download_source = lambda *a, **kw: (
        app_module._ExpandedDownloadSource(playlist_info={}, entries=[info])
    )
    worker._analyze_download_item = lambda *a, **kw: app_module._AnalyzedDownloadItem(
        preflight_info=info,
        display_info=info,
        plan=_worker_test_export_plan(),
        session_cookies=(),
        cookie_source_loaded=False,
    )
    worker._try_reuse_existing_output = lambda *a, **kw: None
    worker._download_item_to_staging = lambda *a, **kw: (
        app_module._DownloadedStagingItem(
            metadata=info, session_cookies=(), ffmpeg="synthetic"
        )
    )
    media = []

    def prepare(job, item, downloaded, staging, **kw):
        path = staging / "synthetic.mp4"
        path.write_bytes(b"validated finished media")
        media.append(path)
        return app_module._PreparedStagingItem(
            metadata=info,
            staged_media=[(info, path)],
            expected_extension=".mp4",
            ffmpeg="synthetic",
            custom_cover_for_cache=None,
        )

    worker._prepare_staged_download_item = prepare
    worker._transcode_and_validate_staged_media = (
        lambda job, info, plan, staged, ffmpeg, **kw: [
            (info, staged[0][1], {"validated": True})
        ]
    )

    def fail(*a, **kw):
        raise sharing_error(code)

    worker._commit_validated_staged_media = fail
    if phase == "validation":
        worker._transcode_and_validate_staged_media = fail
    outcome = worker._download_worker_single(
        _worker_test_job(tmp_path, url=info["webpage_url"])
    )
    assert outcome.success_count == 0
    retained_logs = [
        str(payload)
        for kind, payload in worker.events.queue
        if "completed media retained" in str(payload)
    ]
    assert bool(retained_logs) is preserve
    assert media[0].exists() is preserve
    if preserve:
        assert media[0].read_bytes() == b"validated finished media"
    assert not list(tmp_path.glob("Creator/*.mp4"))


@pytest.mark.parametrize("code,attempts", [(32, 5), (33, 5), (5, 1)])
def test_commit_retry_is_bounded_and_does_not_retry_access_denial(
    tmp_path, monkeypatch, code, attempts
):
    source = tmp_path / "finished.mp4"
    source.write_bytes(b"finished")
    calls, sleeps = [], []

    def fail(*args, **kwargs):
        calls.append(1)
        raise sharing_error(code)

    monkeypatch.setattr(safe_output, "_commit_file_beneath_once", fail)
    monkeypatch.setattr(safe_output.time, "sleep", sleeps.append)
    with pytest.raises(PermissionError):
        safe_output.commit_file_beneath(source, tmp_path, tmp_path / "output.mp4")
    assert len(calls) == attempts
    assert sum(sleeps) == pytest.approx(1.5 if attempts == 5 else 0)
    assert source.read_bytes() == b"finished"


def test_cancel_during_lock_backoff_stops_before_another_commit(tmp_path, monkeypatch):
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise sharing_error()

    def cancelled():
        raise RuntimeError("synthetic cancellation")

    monkeypatch.setattr(safe_output, "_commit_file_beneath_once", fail)
    with pytest.raises(RuntimeError, match="cancellation"):
        safe_output.commit_file_beneath(
            tmp_path / "source", tmp_path, tmp_path / "out", control_check=cancelled
        )
    assert calls == [1]


def test_retry_rechecks_redirected_parent_before_second_move(tmp_path, monkeypatch):
    root = tmp_path / "output"
    parent = root / "Creator"
    parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"finished")
    original = safe_output._commit_windows
    calls = []

    def first_lock(*args):
        calls.append(1)
        if len(calls) == 1:
            parent.rmdir()
            parent.symlink_to(outside, target_is_directory=True)
            raise sharing_error()
        return original(*args)

    monkeypatch.setattr(safe_output.os, "supports_dir_fd", set())
    monkeypatch.setattr(safe_output, "_commit_windows", first_lock)
    monkeypatch.setattr(safe_output.time, "sleep", lambda _: None)
    with pytest.raises(safe_output.UnsafeOutputPathError, match="redirects"):
        safe_output.commit_file_beneath(source, root, parent / "out.mp4")
    assert source.read_bytes() == b"finished"
    assert not list(outside.iterdir())


def test_existing_target_is_not_overwritten_after_sharing_retry(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"new")
    target = tmp_path / "out.mp4"
    original = safe_output._commit_windows
    calls = []

    def first_lock(*args):
        calls.append(1)
        if len(calls) == 1:
            target.write_bytes(b"existing")
            raise sharing_error()
        return original(*args)

    monkeypatch.setattr(safe_output.os, "supports_dir_fd", set())
    monkeypatch.setattr(safe_output, "_commit_windows", first_lock)
    monkeypatch.setattr(safe_output.time, "sleep", lambda _: None)
    with pytest.raises(FileExistsError):
        safe_output.commit_file_beneath(
            source, tmp_path, target, replace_existing=False
        )
    assert source.read_bytes() == b"new"
    assert target.read_bytes() == b"existing"


def test_forbidden_response_is_not_classified_as_transient_refresh():
    from urllib.error import HTTPError

    error = HTTPError("https://example.invalid/synthetic", 403, "Forbidden", None, None)
    calls = []

    def forbidden():
        calls.append(1)
        raise error

    with pytest.raises(HTTPError):
        app_module.run_with_bounded_transient_retries(forbidden)
    assert calls == [1]


def test_retained_media_is_excluded_from_later_crash_cleanup(tmp_path, monkeypatch):
    from yt_downloader import run_state as state_module
    from yt_downloader.run_state import ActiveRunStore, recover_interrupted_run
    from yt_downloader.safe_output import create_private_staging_directory

    job = _worker_test_job(tmp_path)
    store = ActiveRunStore(tmp_path / "active-run.json")
    store.begin(job)
    retained = create_private_staging_directory(tmp_path)
    finished = retained / "finished.mp4"
    finished.write_bytes(b"validated finished media")
    store.add_staging_dir(job.run_id, retained)
    store.retain_completed_staging_dir(job.run_id, retained)
    incomplete = create_private_staging_directory(tmp_path)
    (incomplete / "partial.mp4").write_bytes(b"incomplete")
    store.add_staging_dir(job.run_id, incomplete)
    monkeypatch.setattr(state_module.os, "getpid", lambda: 999999)
    recover_interrupted_run(
        store, terminate_children=lambda *_: None, owner_command_reader=lambda _: None
    )
    assert finished.read_bytes() == b"validated finished media"
    assert not incomplete.exists()


def test_retention_cannot_detach_other_run_or_live_child_ownership(tmp_path):
    from yt_downloader.run_state import ActiveRunStore, RunStateError
    from yt_downloader.safe_output import create_private_staging_directory

    job = _worker_test_job(tmp_path)
    store = ActiveRunStore(tmp_path / "active-run.json")
    store.begin(job)
    stage = create_private_staging_directory(tmp_path)
    store.add_staging_dir(job.run_id, stage)
    with pytest.raises(RunStateError, match="not owned"):
        store.retain_completed_staging_dir("other-run", stage)
    store.child_started(12345, ["synthetic", str(stage / "partial")])
    with pytest.raises(RunStateError, match="child ownership"):
        store.retain_completed_staging_dir(job.run_id, stage)
    assert store.load()["staging_dirs"] == [str(stage)]
