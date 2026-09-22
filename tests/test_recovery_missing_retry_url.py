"""A non-retryable saved attempt must not poison unrelated future downloads."""

import json

import pytest

from tests.test_run_state import _job
from yt_downloader.run_state import (
    ActiveRunStore,
    RunRecoveryOwner,
    RunStateError,
    deserialize_download_job,
    serialize_download_job,
)


def _legacy_job(job):
    # Persist the old schema shape directly: a current writer must now reject
    # this input, while the recovery reader must still accept historical data.
    value = serialize_download_job(job)
    value.pop("retry_source_state", None)
    value.pop("retry_source_states", None)
    return value


def _legacy_active(path, job):
    import os

    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "active",
                "owner_pid": os.getpid(),
                "job": _legacy_job(job),
                "staging_dirs": [],
                "children": [],
                "recovered_failures": [],
                "queued_jobs": [],
            }
        )
    )


def _legacy_queue(path, jobs):
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "idle",
                "queued_jobs": [_legacy_job(job) for job in jobs],
            }
        )
    )


@pytest.mark.parametrize("state", ["idle", "failed", "active"])
@pytest.mark.parametrize("url", ["", "file:///PRIVATE/audio.mp3"])
def test_missing_retry_source_preserves_attempt_and_allows_new_run(
    tmp_path, state, url
):
    job = _job(tmp_path)
    job.url = url
    job.urls = []
    path = tmp_path / "active-run.json"
    ActiveRunStore(path)
    _legacy_active(path, job)
    payload = json.loads(path.read_text())
    if state == "idle":
        payload = {
            "schema_version": 1,
            "state": "idle",
            "recovered_failures": [
                {
                    "job": payload["job"],
                    "terminal_status": "Failed",
                    "terminal_message": "Prior attempt",
                }
            ],
            "queued_jobs": [],
        }
    elif state == "failed":
        payload["state"] = "failed"
    path.write_text(json.dumps(payload))
    owner = RunRecoveryOwner(path)
    recovered = owner.recover_at_startup()
    assert len(recovered) == 1 and recovered[0].run_id == job.run_id
    assert recovered[0].url == "" and not recovered[0].urls
    assert owner.recovery_notice is None
    next_job = _job(tmp_path)
    next_job.run_id = "fresh-url-run"
    owner.begin(next_job)
    saved = json.loads(path.read_text())
    assert saved["job"]["run_id"] == "fresh-url-run"
    assert saved["recovered_failures"][0]["job"]["run_id"] == job.run_id
    assert saved["recovered_failures"][0]["job"]["url"] == ""


def test_nonretryable_records_are_not_executable_queue_jobs(tmp_path):
    job = _job(tmp_path)
    job.url = ""
    job.urls = []
    with pytest.raises(RunStateError):
        deserialize_download_job(serialize_download_job(job))


def test_missing_queue_source_is_retained_without_losing_valid_queue(tmp_path):
    good = _job(tmp_path)
    bad = _job(tmp_path)
    bad.run_id = "missing-source"
    bad.url = ""
    bad.urls = []
    path = tmp_path / "active-run.json"
    ActiveRunStore(path)
    _legacy_queue(path, [bad, good])
    owner = RunRecoveryOwner(path)
    terminal, queued = owner.startup_recovery()
    assert [job.run_id for job in terminal] == [bad.run_id]
    assert [job.run_id for job in queued] == [good.run_id]
    payload = json.loads(path.read_text())
    assert payload["recovered_failures"][0]["job"] == _legacy_job(bad)
    assert payload["queued_jobs"] == [_legacy_job(good)]
    # Cold restart retains the same history and no executable missing-source job.
    terminal2, queued2 = RunRecoveryOwner(path).startup_recovery()
    assert [job.run_id for job in terminal2] == [bad.run_id]
    assert [job.run_id for job in queued2] == [good.run_id]


@pytest.mark.parametrize("prior_missing_source", [False, True])
def test_many_local_commits_then_first_url_keep_recovery_owners_separate(
    tmp_path, prior_missing_source
):
    """Real journals/commits; controlled encoder/probe, not a codec qualification."""
    from tests.test_local_audio_video import FakeProcess, _owner
    from yt_downloader.history import load_history, save_history, upsert_history
    from yt_downloader.local_audio_video import new_local_audio_video_request

    path = tmp_path / "active-run.json"
    store = ActiveRunStore(path)
    if prior_missing_source:
        old = _job(tmp_path)
        old.url = ""
        old.urls = []
        store.record_terminal_attempt(old, "Failed", "Previous attempt")
    initial = path.read_bytes() if path.exists() else None
    audio, image = tmp_path / "source.mp3", tmp_path / "still.jpg"
    audio.write_bytes(b"controlled audio")
    image.write_bytes(b"controlled image")
    local = _owner(tmp_path, popen=lambda command, **_: FakeProcess(command))
    history = tmp_path / "history.json"
    for index in range(101):
        request = new_local_audio_video_request(
            audio, image, tmp_path / f"output-{index}"
        )
        result = local.convert(request, on_progress=lambda _: None)
        save_history(
            history,
            upsert_history(
                load_history(history),
                dict(result.history_metadata),
                result.output_path.parent,
            ),
        )
        assert result.output_path.is_file()
        assert (path.read_bytes() if path.exists() else None) == initial
    download = RunRecoveryOwner(path)
    terminal, queued = download.startup_recovery()
    assert len(terminal) == int(prior_missing_source) and not queued
    # Cold restart cannot turn the retained non-retryable entry back into lockout.
    download = RunRecoveryOwner(path)
    download.startup_recovery()
    first = _job(tmp_path)
    first.run_id = "first-url-after-local"
    download.begin(first)
    assert json.loads(path.read_text())["job"]["run_id"] == first.run_id


@pytest.mark.parametrize("fault", ["live_owner", "invalid_staging"])
def test_missing_source_never_waives_cleanup_ownership(tmp_path, fault):
    from yt_downloader.run_state import recover_interrupted_run

    job = _job(tmp_path)
    job.url = ""
    job.urls = []
    path = tmp_path / "active-run.json"
    store = ActiveRunStore(path)
    _legacy_active(path, job)
    payload = json.loads(path.read_text())
    if fault == "live_owner":
        payload["owner_pid"] = 12345
    else:
        payload["staging_dirs"] = [str(tmp_path / "unowned")]
    path.write_text(json.dumps(payload))
    before = path.read_bytes()
    effects = []
    with pytest.raises(RunStateError) as raised:
        recover_interrupted_run(
            store,
            owner_command_reader=lambda _: "unrelated live process",
            cleanup_staging=lambda _: effects.append("cleanup"),
            terminate_children=lambda *_: effects.append("terminate"),
        )
    assert raised.value.cause == fault
    assert effects == [] and path.read_bytes() == before
