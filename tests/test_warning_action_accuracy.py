"""Auditor-derived desired warning/action regressions; no GUI or network."""

import errno
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def test_local_missing_media_never_offers_fabricated_youtube_recovery(tmp_path):
    from PySide6.QtCore import QUrl

    from yt_downloader.history import upsert_history
    from yt_downloader.library_media_recovery import LibraryMediaRecoveryOwner
    from yt_downloader.library_media_recovery_prompt import (
        library_media_recovery_prompt,
    )
    from yt_downloader.qt_quick.main import Bridge

    record = {
        "id": "local-0123456789abcdef",
        "title": "My local clip",
        "channel": "Local media",
        "vodforge_run_id": "import-0123456789abcdef",
        "vodforge_output_type": "MP4",
        "vodforge_output_path": str(tmp_path / "missing.mp4"),
        "vodforge_encoding_summary": {
            "source": {"Source": "Imported from this computer"},
            "output": {},
            "warnings": [],
        },
    }
    row = upsert_history([], record, tmp_path)[0]
    recovery = LibraryMediaRecoveryOwner()
    plan = recovery.plan(row)
    prompt = library_media_recovery_prompt(plan)
    assert plan.kind == "local" and prompt.primary_action == "none"
    assert "Find file" in prompt.message
    bridge = SimpleNamespace(
        _missing_plan=plan,
        _current_missing_record=lambda: row,
        _media_recovery=recovery,
        setOutputFormat=Mock(),
        outputPathChanged=Mock(),
        exportModeChanged=Mock(),
        select=Mock(),
        sourcePrepared=Mock(),
        statusChanged=Mock(),
    )
    assert not Bridge.openMissingInForge(bridge, QUrl.fromLocalFile(str(tmp_path)))
    bridge.sourcePrepared.emit.assert_not_called()
    assert "redownload" not in prompt.primary_label.lower()


def test_reserved_destination_has_ownership_specific_guidance(tmp_path):
    from tests.test_run_identity import make_job
    from yt_downloader.run_state import (
        ActiveRunStore,
        RunStateError,
        run_admission_failure_message,
    )

    store = ActiveRunStore(tmp_path / "state.json")
    job = make_job(tmp_path / "out")
    stage = job.output_dir / ".vfstage" / "owned"
    stage.mkdir(parents=True)
    store.begin(job)
    store.add_staging_dir(job.run_id, stage)
    store.prepare_recovery()
    before = store.path.read_bytes()
    with pytest.raises(RunStateError) as error:
        store.assert_output_available(stage.parent)
    assert "protected by an interrupted run" in str(error.value)
    message = run_admission_failure_message(error.value)
    assert "protected" in message and "Issues" in message
    assert "disk space" not in message
    assert store.path.read_bytes() == before


@pytest.mark.parametrize("code", [errno.ENOSPC, errno.EACCES])
def test_update_known_storage_failure_preserves_prerequisite(
    tmp_path, monkeypatch, code
):
    from yt_downloader.qt_quick import update_session as module
    from yt_downloader.updates import ReleaseInfo

    monkeypatch.setattr(module, "application_data_dir", lambda: tmp_path)

    def fail(*a, **kw):
        raise OSError(code, "fixture update cache failure")

    monkeypatch.setattr(module, "download_verified_update", fail)
    release = ReleaseInfo(
        "0.2.7", "v0.2.7", "Fixture", "https://example.invalid", "", ""
    )
    session = module.QtUpdateSession("0.2.6")
    session.stage = "download"
    session.busy = True
    session._download_worker(release)
    events = list(session.events.queue)
    detail = events[-1][1][1]
    assert detail.reason == (
        "disk_full" if code == errno.ENOSPC else "permission_denied"
    )
    session.poll()
    assert session.recovery and not session.busy
    assert ("space" if code == errno.ENOSPC else "access") in session.status
    assert "update cache" in session.status


@pytest.mark.parametrize("failure", ["missing_file", "missing_probe"])
def test_import_retains_per_file_actionable_reason(tmp_path, monkeypatch, failure):
    import threading

    from PySide6.QtCore import QUrl

    from yt_downloader import library_import
    from yt_downloader.qt_quick.main import Bridge

    path = tmp_path / "local.mp4"
    if failure == "missing_probe":
        path.write_bytes(b"fixture")
    monkeypatch.setattr(library_import, "find_runtime_executable", lambda _: None)
    with pytest.raises((OSError, ValueError, RuntimeError)) as caught:
        library_import.inspect_local_media(path, threading.Event())
    assert str(caught.value)
    captured = []

    def submit(kind, work):
        captured.append(work(threading.Event()))
        return 1

    bridge = SimpleNamespace(
        _import_pending=False,
        _relink=SimpleNamespace(active=False),
        _file_action_busy=False,
        _runtime=SimpleNamespace(
            recovery_notice=None, active_job=None, busy=False, queued=[]
        ),
        _local_running=False,
        _import_work=SimpleNamespace(submit=submit),
        _analytics=SimpleNamespace(telemetry=None),
        importBusyChanged=Mock(),
        statusChanged=Mock(),
    )
    assert Bridge.importMedia(bridge, [QUrl.fromLocalFile(str(path))])
    assert captured[0][0] == []
    assert len(captured[0][1]) == 1
    detail = captured[0][1][0]
    assert detail.name == path.name
    assert (
        "no longer" if failure == "missing_file" else "inspection component"
    ) in detail.message
    assert str(tmp_path) not in detail.message


@pytest.mark.parametrize(
    "reason,phrase",
    [
        ("disk_full", "disk space"),
        ("permission_denied", "permissions"),
        ("source_unavailable", "source"),
        ("rate_limited", "Wait"),
        ("dependency_missing", "component"),
    ],
)
def test_download_category_guidance_has_matching_remedy(reason, phrase):
    from yt_downloader.download_error_presentation import FAILURE_GUIDANCE

    assert phrase in FAILURE_GUIDANCE[reason]


@pytest.mark.parametrize(
    "kind,phrase,action",
    [("unavailable", "Reconnect", "none"), ("ambiguous", "more than one", "none")],
)
def test_missing_media_uncertainty_does_not_offer_redownload(kind, phrase, action):
    from yt_downloader.library_media_recovery import LibraryMediaRecoveryPlan
    from yt_downloader.library_media_recovery_prompt import (
        library_media_recovery_prompt,
    )

    message = library_media_recovery_prompt(LibraryMediaRecoveryPlan(kind, None))
    assert phrase in message.heading and message.primary_action == action


@pytest.mark.parametrize("identity", ["local-" + "a" * 64, "local_" + "b" * 32])
def test_local_identity_never_synthesizes_a_provider_source(tmp_path, identity):
    from yt_downloader.download_service import canonical_youtube_url
    from yt_downloader.history import upsert_history
    from yt_downloader.library_media_recovery import LibraryMediaRecoveryOwner

    row = upsert_history(
        [],
        {
            "id": identity,
            "title": "Local",
            "vodforge_output_type": "MP4",
            "vodforge_output_path": str(tmp_path / "missing.mp4"),
        },
        tmp_path,
    )[0]
    assert canonical_youtube_url(row) is None
    assert LibraryMediaRecoveryOwner().plan(row).kind == "local"


def test_similarly_named_real_provider_identity_is_not_a_local_hash():
    from yt_downloader.download_service import canonical_youtube_url

    assert (
        canonical_youtube_url({"id": "local-abcde"})
        == "https://www.youtube.com/watch?v=local-abcde"
    )
