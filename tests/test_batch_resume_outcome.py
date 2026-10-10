"""Finished child outcomes survive interruption without reprocessing URLs."""

import queue

import pytest

from tests.test_run_identity import make_job
from yt_downloader import app as app_module
from yt_downloader.app import DownloadWorkerCore, _download_batch_terminal_event
from yt_downloader.models import DownloadOutcome
from yt_downloader.run_state import deserialize_download_job, serialize_download_job


@pytest.mark.parametrize(
    "prior",
    [
        DownloadOutcome(failure_count=1),
        DownloadOutcome(skipped_count=1),
        DownloadOutcome(success_count=2, sidecar_failure_count=1),
    ],
)
def test_prior_batch_issue_survives_saved_checkpoint(tmp_path, monkeypatch, prior):
    job = make_job(tmp_path)
    job.batch_mode = True
    job.urls = ["https://example.com/first", "https://example.com/second"]
    job.url = job.urls[0]
    job.completed_batch_items = 1
    job.batch_outcome = prior
    resumed = deserialize_download_job(serialize_download_job(job))
    worker = DownloadWorkerCore()
    worker.events = queue.Queue()
    worker.cancel_requested = False
    monkeypatch.setattr(worker, "_emit_job_log", lambda *args: None)
    monkeypatch.setattr(app_module, "write_diagnostic", lambda *args: None)
    visited = []

    def download(child, **kwargs):
        visited.append(child.url)
        return DownloadOutcome(success_count=1)

    monkeypatch.setattr(worker, "_download_worker_single", download)
    result = worker._coordinate_download_batch(resumed, resumed.urls)
    assert visited == ["https://example.com/second"]
    assert result.outcome == prior.combined_with(DownloadOutcome(success_count=1))
    assert _download_batch_terminal_event(result, 2)[0] == "partial"
    finished = [
        event[1]
        for event in list(worker.events.queue)
        if event[0] == "batch_item" and event[1]["finished"]
    ]
    assert finished[-1]["outcome"] == result.outcome


def test_all_processed_resume_resolves_saved_outcome(tmp_path, monkeypatch):
    job = make_job(tmp_path)
    job.urls = ["https://example.com/first", "https://example.com/second"]
    job.completed_batch_items = 2
    job.batch_outcome = DownloadOutcome(success_count=1, failure_count=1)
    worker = DownloadWorkerCore()
    worker.events = queue.Queue()
    monkeypatch.setattr(
        worker,
        "_download_worker_single",
        lambda *args, **kwargs: pytest.fail("Completed URL processed twice"),
    )
    worker._download_worker(job)
    terminal = worker.events.get_nowait()
    assert terminal[0] == "partial"
    assert "1 valid output(s)" in terminal[1] and "1 failed" in terminal[1]


@pytest.mark.parametrize("value", [-1, True, "1", 1_000_001])
def test_invalid_saved_batch_outcome_is_rejected(tmp_path, value):
    from yt_downloader.run_state import RunStateError

    payload = serialize_download_job(make_job(tmp_path))
    payload["batch_outcome"] = {"failure_count": value}
    with pytest.raises(RunStateError):
        deserialize_download_job(payload)


def test_older_job_without_batch_counts_loads(tmp_path):
    payload = serialize_download_job(make_job(tmp_path))
    payload.pop("batch_outcome", None)
    assert deserialize_download_job(payload).batch_outcome == DownloadOutcome()
