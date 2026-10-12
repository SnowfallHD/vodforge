"""Current source adapters preserve durable work, without a widget or GUI launch."""

from dataclasses import replace

from quality_harness.scenarios import _stop_recovered_queue

from tests.test_run_state import _job
from yt_downloader.run_state import ActiveRunStore


def test_restart_adapter_stops_each_queued_job_before_any_provider_preview(tmp_path):
    path = tmp_path / "active.json"
    jobs = [
        replace(_job(tmp_path), run_id=name, preview_info=None)
        for name in ("first", "second")
    ]
    store = ActiveRunStore(path)
    store.replace_queue(jobs)
    projection = _stop_recovered_queue(tmp_path, path, jobs)
    durable = ActiveRunStore(path).load_terminal_jobs()
    assert [(job.run_id, job.terminal_status) for job in durable] == [
        ("first", "Stopped"),
        ("second", "Stopped"),
    ]
    assert ActiveRunStore(path).load_queued_jobs() == []
    assert {row["vodforge_terminal_run_id"] for row in projection.rows} == {
        "first",
        "second",
    }
    assert all(row["vodforge_terminal_status"] == "Stopped" for row in projection.rows)
    assert not projection.receipt.violation_codes
