"""New executable writes must round-trip; old nonretryable history stays reviewable."""

import json
import random

import pytest

from tests.test_run_state import _job
from yt_downloader.run_state import ActiveRunStore, RunStateError


@pytest.mark.parametrize("operation", ["begin", "replace_queue"])
@pytest.mark.parametrize(
    "invalid",
    [
        "",
        "file:///private/source.mp3",
        "https://host:bad/video",
        "https://host/video\x00",
        "https://" + "a" * 8200,
    ],
    ids=["missing", "local_file", "invalid_port", "control_character", "oversized"],
)
def test_new_executable_write_rejects_undurable_source_atomically(
    tmp_path, operation, invalid
):
    path = tmp_path / "active-run.json"
    store = ActiveRunStore(path)
    good = _job(tmp_path)
    store.replace_queue([good])
    before = path.read_bytes()
    bad = _job(tmp_path)
    bad.url, bad.urls = invalid, [invalid]
    with pytest.raises(RunStateError):
        if operation == "begin":
            store.begin(bad, [good])
        else:
            store.replace_queue([good, bad])
    assert path.read_bytes() == before


@pytest.mark.parametrize("seed", [713, 1129, 2707])
def test_generated_queue_writer_restart_preserves_order_and_all_or_nothing(
    tmp_path, seed
):
    rng = random.Random(seed)
    path = tmp_path / "active-run.json"
    store = ActiveRunStore(path)
    for trial in range(24):
        jobs = []
        for index in range(rng.randint(1, 6)):
            job = _job(tmp_path)
            job.run_id = f"seed-{seed}-trial-{trial}-job-{index}"
            job.url = f"https://example.test/media/{trial}/{index}"
            job.urls = [job.url]
            jobs.append(job)
        store.replace_queue(jobs)
        # New store instance reads disk rather than the writer's local objects.
        restored = ActiveRunStore(path).load_queued_jobs()
        assert [job.run_id for job in restored] == [job.run_id for job in jobs]
        assert [job.urls for job in restored] == [job.urls for job in jobs]
        before = path.read_bytes()
        jobs[rng.randrange(len(jobs))].urls += [
            rng.choice(["", "file:///private/a", "https://host:bad/"])
        ]
        with pytest.raises(RunStateError):
            store.replace_queue(jobs)
        assert path.read_bytes() == before


@pytest.mark.parametrize(
    "source,state",
    [
        ("https://example.test/media", "retained"),
        ("https://user:PRIVATE@example.test/media?token=PRIVATE#fragment", "sanitized"),
        ("", "missing_original"),
        ("file:///PRIVATE/source.mp3", "unsupported_scheme"),
        ("https://host:bad/path", "invalid_source"),
    ],
)
def test_serialized_source_reason_is_bounded_and_private_input_not_restored(
    tmp_path, source, state
):
    from yt_downloader.run_state import saved_retry_source_state, serialize_download_job

    job = _job(tmp_path)
    job.url, job.urls = source, [source]
    payload = serialize_download_job(job)
    assert payload["retry_source_state"] == state
    assert payload["retry_source_states"] == [state]
    assert saved_retry_source_state(payload) == state
    assert "PRIVATE" not in json.dumps(payload)
    payload.pop("retry_source_state")
    assert saved_retry_source_state(payload) == "legacy_unknown"
    payload["retry_source_state"] = "untrusted PRIVATE value"
    assert saved_retry_source_state(payload) == "legacy_unknown"


def test_rejected_source_link_guidance_matches_actual_launch_refusal(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from yt_downloader import app as app_module
    from yt_downloader.app import DownloaderApp
    from yt_downloader.run_state import RunRecoveryOwner

    job = _job(tmp_path)
    job.url = "file:///PRIVATE/source"
    job.urls = [job.url]
    notices = []
    monkeypatch.setattr(
        app_module.messagebox,
        "showerror",
        lambda _title, message: notices.append(message),
    )
    owner = RunRecoveryOwner(tmp_path / "active-run.json")
    app = SimpleNamespace(run_recovery=owner, pending_jobs=[], active_job=None)
    assert not DownloaderApp._launch_download_job(app, job)
    assert app.active_job is None and app.pending_jobs == []
    assert not owner.store.path.exists()
    assert len(notices) == 1
    message = notices[0].lower()
    assert "link" in message and "paste" in message
    assert "disk" not in message and "PRIVATE" not in notices[0]
    assert job.url == "file:///PRIVATE/source"


def test_tk_journal_write_failure_uses_bounded_admission_guidance(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from yt_downloader import app as app_module
    from yt_downloader.app import DownloaderApp
    from yt_downloader.run_state import RunRecoveryOwner, RunStateError

    job = _job(tmp_path)
    owner = RunRecoveryOwner(tmp_path / "active-run.json")
    notices = []
    monkeypatch.setattr(
        app_module.messagebox,
        "showerror",
        lambda _title, message: notices.append(message),
    )

    def refuse(*_args, **_kwargs):
        raise RunStateError("PRIVATE journal path", cause="write_failed")

    monkeypatch.setattr(owner, "begin", refuse)
    app = SimpleNamespace(run_recovery=owner, pending_jobs=[], active_job=None)
    assert not DownloaderApp._launch_download_job(app, job)
    assert app.active_job is None
    assert notices and "No download was started." in notices[0]
    assert "PRIVATE" not in notices[0]
