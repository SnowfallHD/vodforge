from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

import yt_downloader.run_state as run_state_module
from yt_downloader.models import (
    DownloadJob,
    ExportMode,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)
from yt_downloader.process_lifecycle import terminate_recorded_children
from yt_downloader.run_state import (
    INTERRUPTED_FAILURE_MESSAGE,
    ActiveRunStore,
    RunStateError,
    deserialize_download_job,
    recover_interrupted_run,
    serialize_download_job,
)


def _job(tmp_path: Path) -> DownloadJob:
    return DownloadJob(
        url="https://user:password@www.youtube.com/watch?v=abc123&token=secret#private",
        urls=["https://www.youtube.com/watch?v=abc123&list=playlist"],
        output_dir=tmp_path,
        output_type=OutputType.MP4,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=True,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=True,
        embed_metadata=False,
        write_info_json=True,
        tags=["safe", "https://example.test/?token=secret#fragment"],
        use_cookies=True,
        cookie_file=tmp_path / "cookies.txt",
        cookie_browser="chrome:Default",
        preview_info={"id": "abc123", "title": "A title", "uploader": "Creator"},
        run_id="run-1",
    )


def test_job_recovery_contract_excludes_secrets_and_cookie_authority(
    tmp_path: Path,
) -> None:
    payload = serialize_download_job(_job(tmp_path))
    text = repr(payload)

    assert "password" not in text
    assert "secret" not in text
    assert "fragment" not in text
    assert "cookies.txt" not in text
    assert "chrome:Default" not in text

    recovered = deserialize_download_job(payload)
    assert recovered.url == "https://www.youtube.com/watch?v=abc123"
    assert recovered.use_cookies is False
    assert recovered.cookie_file is None
    assert recovered.cookie_browser is None


def test_job_recovery_preserves_output_profile_origin_and_local_cover_art(
    tmp_path: Path,
) -> None:
    cover = tmp_path / "cover.jpg"
    job = _job(tmp_path)
    job.origin_run_id = "previous-run"
    job.mp3_settings = Mp3ExportSettings(
        bitrate_kbps=256,
        sample_rate="48000",
        channels="2",
        embed_metadata=True,
        embed_cover_art=True,
        custom_cover_art_path=cover,
    )

    recovered = deserialize_download_job(serialize_download_job(job))

    assert recovered.origin_run_id == "previous-run"
    assert recovered.mp3_settings.custom_cover_art_path == cover


def test_active_run_store_is_private_and_failed_state_survives_restart(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state" / "active-run.json"
    store = ActiveRunStore(path)
    store.begin(_job(tmp_path))
    failed = store.mark_failed()

    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert failed.terminal_status == "Failed"
    assert failed.terminal_message == INTERRUPTED_FAILURE_MESSAGE
    assert ActiveRunStore(path).load_failed_job() is not None


def test_stopped_terminal_state_survives_restart_until_library_removal(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state" / "active-run.json"
    store = ActiveRunStore(path)
    store.begin(_job(tmp_path))

    stopped = store.mark_terminal("Stopped", "Cancelled before analysis")

    assert stopped.terminal_status == "Stopped"
    restarted = ActiveRunStore(path)
    recovered = restarted.load_terminal_jobs()
    assert [job.run_id for job in recovered] == ["run-1"]
    assert recovered[0].terminal_status == "Stopped"
    assert recovered[0].terminal_message == "Cancelled before analysis"

    restarted.clear("run-1")
    assert restarted.load() is None


def test_recovery_stops_only_bound_child_then_cleans_stage(tmp_path: Path) -> None:
    stage = tmp_path / ".vfstage" / "deadbeef"
    stage.mkdir(parents=True)
    (stage / "source.mp4").write_bytes(b"partial")
    store = ActiveRunStore(tmp_path / "active-run.json")
    store.begin(_job(tmp_path))
    store.add_staging_dir("run-1", stage)
    store.child_started(4321, ["/bundle/ffmpeg", "-i", str(stage / "source.mp4")])
    terminated: list[int] = []

    recovered = recover_interrupted_run(
        store,
        cleanup_staging=lambda paths: [_remove_tree(path) for path in paths],
        terminate_children=lambda children, paths: terminate_recorded_children(
            children,
            paths,
            command_reader=lambda _pid: f"/bundle/ffmpeg -i {stage}/source.mp4",
            pid_terminator=lambda pid: terminated.append(pid) is None or True,
        ),
        owner_command_reader=lambda _pid: None,
    )

    assert len(recovered) == 1
    assert recovered[0].terminal_status == "Failed"
    assert terminated == [4321]
    assert not stage.exists()


def _remove_tree(path: Path) -> bool:
    for child in path.iterdir():
        child.unlink()
    path.rmdir()
    return False


def test_recovery_fails_closed_for_unrelated_or_reused_pid(tmp_path: Path) -> None:
    stage = tmp_path / ".vfstage" / "deadbeef"
    stage.mkdir(parents=True)
    store = ActiveRunStore(tmp_path / "active-run.json")
    store.begin(_job(tmp_path))
    store.add_staging_dir("run-1", stage)
    store.child_started(4321, ["/bundle/ffmpeg", "-i", str(stage / "source.mp4")])
    terminated: list[int] = []

    with pytest.raises(RunStateError, match="Refusing to stop PID"):
        recover_interrupted_run(
            store,
            cleanup_staging=lambda _paths: None,
            terminate_children=lambda children, paths: terminate_recorded_children(
                children,
                paths,
                command_reader=lambda _pid: "/usr/bin/python unrelated.py",
                pid_terminator=lambda pid: terminated.append(pid) is None or True,
            ),
            owner_command_reader=lambda _pid: None,
        )

    assert terminated == []
    assert stage.exists()
    assert store.load()["state"] == "active"  # type: ignore[index]


def test_recovery_refuses_to_touch_a_run_owned_by_a_live_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = tmp_path.resolve() / ".vfstage" / "deadbeef"
    stage.mkdir(parents=True)
    store = ActiveRunStore(tmp_path / "active-run.json")
    store.begin(_job(tmp_path))
    store.add_staging_dir("run-1", stage)
    monkeypatch.setattr(run_state_module.os, "getpid", lambda: 999_999)

    with pytest.raises(RunStateError, match="Another live process"):
        recover_interrupted_run(
            store,
            terminate_children=lambda _children, _paths: pytest.fail(
                "must not terminate another app's children"
            ),
            cleanup_staging=lambda _paths: pytest.fail(
                "must not clean another app's staging"
            ),
            owner_command_reader=lambda _pid: "/Applications/VODForge.app/VODForge",
        )

    assert stage.exists()


def test_recovery_rejects_staging_outside_the_recorded_output_root(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / ".vfstage" / "outside"
    store = ActiveRunStore(tmp_path / "active-run.json")
    store.begin(_job(tmp_path))
    store.add_staging_dir("run-1", outside)

    with pytest.raises(RunStateError, match="outside its selected output root"):
        recover_interrupted_run(store, owner_command_reader=lambda _pid: None)


def test_library_removal_or_retry_can_clear_recovered_failure(tmp_path: Path) -> None:
    store = ActiveRunStore(tmp_path / "active-run.json")
    store.begin(_job(tmp_path))
    store.mark_failed()

    store.clear("run-1")

    assert store.load() is None


def test_recovered_failure_survives_a_later_active_run(tmp_path: Path) -> None:
    store = ActiveRunStore(tmp_path / "active-run.json")
    first = _job(tmp_path)
    store.begin(first)
    store.mark_failed()
    second = _job(tmp_path)
    second.run_id = "run-2"

    store.begin(second)
    store.clear("run-2")

    recovered = store.load_failed_jobs()
    assert [job.run_id for job in recovered] == ["run-1"]
    assert recovered[0].terminal_status == "Failed"


def test_ordered_queue_survives_restart_and_active_failure(tmp_path: Path) -> None:
    path = tmp_path / "active-run.json"
    store = ActiveRunStore(path)
    active = _job(tmp_path)
    first = _job(tmp_path)
    first.run_id = "queued-1"
    first.url = "https://www.youtube.com/watch?v=queued1"
    first.urls = [first.url]
    second = _job(tmp_path)
    second.run_id = "queued-2"
    second.url = "https://www.youtube.com/watch?v=queued2"
    second.urls = [second.url]

    store.begin(active, [first, second])
    store.mark_failed()

    restarted = ActiveRunStore(path)
    assert [job.run_id for job in restarted.load_queued_jobs()] == [
        "queued-1",
        "queued-2",
    ]
    assert restarted.load_failed_job().run_id == "run-1"  # type: ignore[union-attr]


def test_queue_promotion_is_one_durable_transition(tmp_path: Path) -> None:
    path = tmp_path / "active-run.json"
    store = ActiveRunStore(path)
    first = _job(tmp_path)
    first.run_id = "queued-1"
    second = _job(tmp_path)
    second.run_id = "queued-2"
    store.replace_queue([first, second])

    store.begin(first, [second])

    payload = store.load()
    assert payload is not None
    assert payload["state"] == "active"
    assert payload["job"]["run_id"] == "queued-1"
    assert [record["run_id"] for record in payload["queued_jobs"]] == ["queued-2"]


def test_queue_supersession_atomically_removes_recovered_failure(
    tmp_path: Path,
) -> None:
    path = tmp_path / "active-run.json"
    store = ActiveRunStore(path)
    failed = _job(tmp_path)
    failed.run_id = "failed-old"
    store.begin(failed)
    store.mark_failed("injected interrupted run")
    replacement = _job(tmp_path)
    replacement.run_id = "queued-new"

    store.replace_queue(
        [replacement],
        superseded_run_id=failed.run_id,
    )

    assert store.load_failed_jobs() == []
    assert [job.run_id for job in store.load_queued_jobs()] == ["queued-new"]


def test_launch_supersession_atomically_replaces_recovered_failure(
    tmp_path: Path,
) -> None:
    path = tmp_path / "active-run.json"
    store = ActiveRunStore(path)
    failed = _job(tmp_path)
    failed.run_id = "failed-old"
    store.begin(failed)
    store.mark_failed("injected interrupted run")
    replacement = _job(tmp_path)
    replacement.run_id = "active-new"

    store.begin(replacement, superseded_run_id=failed.run_id)

    payload = store.load()
    assert payload is not None
    assert payload["state"] == "active"
    assert payload["job"]["run_id"] == "active-new"
    assert store.load_failed_jobs() == []


def test_finishing_active_run_preserves_queued_jobs(tmp_path: Path) -> None:
    path = tmp_path / "active-run.json"
    store = ActiveRunStore(path)
    active = _job(tmp_path)
    queued = _job(tmp_path)
    queued.run_id = "queued-1"
    store.begin(active, [queued])

    store.clear(active.run_id)

    payload = store.load()
    assert payload is not None
    assert payload["state"] == "idle"
    assert [job.run_id for job in store.load_queued_jobs()] == ["queued-1"]


def test_removing_queued_run_does_not_disturb_active_owner(tmp_path: Path) -> None:
    path = tmp_path / "active-run.json"
    store = ActiveRunStore(path)
    active = _job(tmp_path)
    queued = _job(tmp_path)
    queued.run_id = "queued-1"
    store.begin(active, [queued])

    store.clear(queued.run_id)

    payload = store.load()
    assert payload is not None
    assert payload["state"] == "active"
    assert payload["job"]["run_id"] == active.run_id
    assert store.load_queued_jobs() == []
