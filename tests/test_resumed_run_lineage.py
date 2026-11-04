"""A resumed interrupted run hands its lineage to the retry that replaces it.

Found by the unattended pre-release journey (engineering-quality/runners/
release_journey.py): after an interrupted download was resumed and completed,
the original attempt stayed listed as Paused with a Resume button, and its
partial files stayed in Downloads/.vfstage indefinitely. Its record still held
those files, and holding files exempted it from supersession and from dismissal.
"""

from dataclasses import replace

import pytest

from tests.test_run_identity import make_job
from yt_downloader.run_state import ActiveRunStore


def settled(tmp_path):
    """An interrupted attempt whose recovery settled with partial files kept."""
    store = ActiveRunStore(tmp_path / "state" / "active-run.json")
    job = replace(make_job(tmp_path / "output"), run_id="interrupted")
    store.begin(job)
    stage = job.output_dir / ".vfstage" / "owned"
    stage.mkdir(parents=True)
    (stage / "video.part").write_bytes(b"private partial")
    store.add_staging_dir(job.run_id, stage)
    store.prepare_recovery()
    token = store.claim_recovery(job.run_id)
    assert store.finish_recovery(
        job.run_id, "ready", "Settled; files kept.", token=token
    )
    store.release_recovery_claim(job.run_id, token)
    assert [j.run_id for j in store.load_terminal_jobs()] == [job.run_id]
    return store, job, stage


def resume(store, previous, run_id="successor"):
    successor = replace(previous, run_id=run_id, terminal_status=None)
    store.begin(successor, superseded_run_id=previous.run_id)
    return successor


def test_resume_hides_the_original_attempt_but_keeps_its_files_until_done(tmp_path):
    store, job, stage = settled(tmp_path)
    resume(store, job)
    # The run list no longer offers the original attempt for Resume...
    assert all(j.run_id != job.run_id for j in store.load_terminal_jobs())
    # ...but its partial files stay protected while the successor is unfinished.
    assert (stage / "video.part").read_bytes() == b"private partial"
    assert [r["superseded_by"] for r in store.recovery_records()] == ["successor"]
    assert not store.release_superseded()


def test_completed_successor_releases_the_original_partial_files(tmp_path):
    store, job, stage = settled(tmp_path)
    successor = resume(store, job)
    assert store.clear(successor.run_id)  # what a successful finish does
    assert store.release_superseded()
    assert not stage.exists()
    assert store.recovery_records() == []
    assert store.load_terminal_jobs() == []
    assert not store.path.exists()


def test_a_retried_successor_carries_the_lineage_forward(tmp_path):
    store, job, stage = settled(tmp_path)
    first = resume(store, job, "first")
    store.mark_terminal("Failed", "First retry failed.")
    assert [j.run_id for j in store.load_terminal_jobs()] == ["first"]
    second = replace(first, run_id="second", terminal_status=None)
    store.begin(second, superseded_run_id="first")
    assert [r["superseded_by"] for r in store.recovery_records()] == ["second"]
    assert stage.exists()
    store.clear(second.run_id)
    assert store.release_superseded()
    assert not stage.exists()


def test_queued_retry_links_the_lineage_the_same_way(tmp_path):
    store, job, stage = settled(tmp_path)
    successor = replace(job, run_id="queued-successor", terminal_status=None)
    store.replace_queue(
        [successor], superseded_run_id=job.run_id, successor_run_id=successor.run_id
    )
    assert all(j.run_id != job.run_id for j in store.load_terminal_jobs())
    assert not store.release_superseded()  # still queued
    store.replace_queue([])  # the queued retry was removed
    assert store.release_superseded()
    assert not stage.exists()


def test_startup_releases_files_when_the_successor_finished_during_quit(tmp_path):
    from yt_downloader.run_state import RunRecoveryOwner

    store, job, stage = settled(tmp_path)
    successor = resume(store, job)
    store.clear(successor.run_id)  # finished; release skipped while closing
    assert stage.exists()
    owner = RunRecoveryOwner(store.path)
    owner.prepare_startup()
    assert not stage.exists()


@pytest.mark.parametrize("state", ["failed", "cancelled"])
def test_unsettled_recovery_is_not_handed_over(tmp_path, state):
    store = ActiveRunStore(tmp_path / "state" / "active-run.json")
    job = replace(make_job(tmp_path / "output"), run_id="interrupted")
    store.begin(job)
    stage = job.output_dir / ".vfstage" / "owned"
    stage.mkdir(parents=True)
    store.add_staging_dir(job.run_id, stage)
    store.prepare_recovery()
    token = store.claim_recovery(job.run_id)
    if state == "cancelled":
        store.cancel_recovery(job.run_id)
    else:
        store.finish_recovery(job.run_id, "failed", "Could not verify.", token=token)
    store.release_recovery_claim(job.run_id, token)
    store.begin(replace(job, run_id="successor"), superseded_run_id=job.run_id)
    # Unverified ownership keeps its visible record and its files, as before.
    assert [j.run_id for j in store.load_terminal_jobs()] == [job.run_id]
    assert "superseded_by" not in store.recovery_records()[0]
    store.clear("successor")
    assert not store.release_superseded()
    assert stage.exists()


def test_held_files_outside_their_staging_root_are_never_deleted(tmp_path):
    store, job, _stage = settled(tmp_path)
    successor = resume(store, job)
    payload = store.load()
    outside = tmp_path / "elsewhere" / ".vfstage" / "owned"
    outside.mkdir(parents=True)
    payload["recovered_failures"][0]["ownership"]["staging_dirs"] = [str(outside)]
    store._write_unlocked(payload)
    store.clear(successor.run_id)
    assert not store.release_superseded()
    assert outside.exists()
    assert store.recovery_records()  # still protected for review
