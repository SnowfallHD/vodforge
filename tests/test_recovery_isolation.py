"""Independent durable ownership boundaries: preserved resources are not an active slot."""

import json
from dataclasses import replace

import pytest

from tests.test_run_identity import make_job
from yt_downloader.run_state import ActiveRunStore, RunStateError


def interrupted(tmp_path):
    store = ActiveRunStore(tmp_path / "state" / "active-run.json")
    job = replace(
        make_job(tmp_path / "output"),
        preview_info={
            "id": "abc123",
            "title": "Recover this video",
            "channel": "Creator",
            "playlist_title": "Collection",
            "thumbnail": "https://example.test/thumb.jpg",
        },
    )
    store.begin(job)
    stage = job.output_dir / ".vfstage" / "owned"
    stage.mkdir(parents=True)
    (stage / "video.part").write_bytes(b"private partial")
    store.add_staging_dir(job.run_id, stage)
    return store, job, stage


def test_begin_cannot_replace_an_unresolved_active_execution(tmp_path):
    store, job, stage = interrupted(tmp_path)
    before = store.path.read_bytes()
    with pytest.raises(RunStateError):
        store.begin(replace(job, run_id="new"))
    assert store.path.read_bytes() == before
    assert (stage / "video.part").read_bytes() == b"private partial"


def test_detached_recovery_is_durable_before_active_slot_reuse(tmp_path):
    store, job, stage = interrupted(tmp_path)
    store.prepare_recovery()
    records = ActiveRunStore(store.path).recovery_records()
    assert len(records) == 1
    assert records[0]["job"]["run_id"] == job.run_id
    assert records[0]["ownership"]["staging_dirs"] == [str(stage)]
    assert records[0]["recovery_state"] == "pending"
    assert records[0]["job"]["preview_info"]["playlist_title"] == "Collection"
    store.claim_recovery(job.run_id)
    store.finish_recovery(job.run_id, "failed", "Permission denied; files preserved.")
    store.begin(replace(job, run_id="new"))  # same source/output/channel is safe
    assert store.load()["job"]["run_id"] == "new"
    assert store.recovery_records()[0]["ownership"]["staging_dirs"] == [str(stage)]
    assert (stage / "video.part").read_bytes() == b"private partial"


def test_crash_after_claim_never_automatically_retries_again(tmp_path):
    store, job, _ = interrupted(tmp_path)
    store.prepare_recovery()
    store.claim_recovery(job.run_id)
    reopened = ActiveRunStore(store.path)
    reopened.prepare_recovery()
    assert reopened.recovery_records()[0]["recovery_state"] == "failed"
    assert not reopened.pending_recovery_jobs()
    reopened.retry_recovery(job.run_id)
    assert [j.run_id for j in reopened.pending_recovery_jobs()] == [job.run_id]


def test_cancel_preserves_partial_and_late_result_cannot_undo_it(tmp_path):
    store, job, stage = interrupted(tmp_path)
    store.prepare_recovery()
    token = store.claim_recovery(job.run_id)
    store.cancel_recovery(job.run_id)
    assert not store.finish_recovery(job.run_id, "ready", "Ready", token=token)
    assert store.recovery_records()[0]["recovery_state"] == "cancelled"
    assert (stage / "video.part").read_bytes() == b"private partial"
    assert not store.clear(job.run_id, terminal_only=True)


@pytest.mark.parametrize("overlap", ["same", "descendant", "pool", "sibling"])
def test_new_output_may_not_enter_an_unresolved_staging_resource(tmp_path, overlap):
    store, job, stage = interrupted(tmp_path)
    store.prepare_recovery()
    store.claim_recovery(job.run_id)
    store.finish_recovery(job.run_id, "failed", "Preserved")
    destination = {
        "same": stage,
        "descendant": stage / "nested",
        "pool": stage.parent,
        "sibling": stage.parent / "another",
    }[overlap]
    with pytest.raises(RunStateError):
        store.begin(replace(job, run_id="new", output_dir=destination))
    assert store.recovery_records()[0]["ownership"]["staging_dirs"] == [str(stage)]


@pytest.mark.parametrize("terminal", [True, False])
def test_terminal_or_finished_cannot_discard_unresolved_resources(tmp_path, terminal):
    store, job, stage = interrupted(tmp_path)
    store.child_started(999991, ["ffmpeg", str(stage)], birth_time=123)
    if terminal:
        store.mark_terminal("Stopped", "Cancelled download")
    else:
        assert store.clear(job.run_id)
    assert store.load()["state"] == "idle"
    record = store.recovery_records()[0]
    assert record["recovery_state"] == "failed"
    assert record["ownership"]["children"][0]["pid"] == 999991
    assert (stage / "video.part").read_bytes() == b"private partial"
    store.begin(replace(job, run_id="separate-new-job"))
    assert not store.clear(job.run_id, terminal_only=True)


def test_late_child_callbacks_cannot_mutate_successor_execution(tmp_path):
    store = ActiveRunStore(tmp_path / "active-run.json")
    job = make_job(tmp_path / "out")
    store.begin(job)
    old_token = store.load()["execution_token"]
    store.clear(job.run_id)
    store.begin(job)  # even a reused logical run ID has a new execution identity
    store.child_started(
        991,
        ["ffmpeg"],
        run_id=job.run_id,
        token=store.load()["execution_token"],
        birth_time=123,
    )
    before = store.path.read_bytes()
    store.child_started(
        992, ["ffmpeg"], run_id=job.run_id, token=old_token, birth_time=124
    )
    store.child_exited(991, run_id=job.run_id, token=old_token)
    assert store.path.read_bytes() == before


def test_current_item_metadata_survives_restart_without_previous_video_artwork(
    tmp_path,
):
    store, job, _stage = interrupted(tmp_path)
    payload = store.load()
    payload["job"]["batch_mode"] = True
    store._write_unlocked(payload)
    store.update_preview(
        job.run_id,
        {
            "id": "next-video",
            "title": "Actual second video",
            "uploader": "Actual creator",
        },
    )
    store.prepare_recovery()
    preview = store.recovery_records()[0]["job"]["preview_info"]
    assert preview["id"] == "next-video" and preview["title"] == "Actual second video"
    assert preview["playlist_title"] == "Collection"
    assert preview["uploader"] == "Actual creator"
    assert not preview.get("thumbnail") and not preview.get("best_thumbnail")


def settled(tmp_path, *, child: bool):
    """A paused attempt whose startup recovery finished ("ready")."""
    store, job, stage = interrupted(tmp_path)
    if child:
        store.child_started(999992, ["ffmpeg", str(stage)], birth_time=123)
    store.prepare_recovery()
    token = store.claim_recovery(job.run_id)
    assert store.finish_recovery(job.run_id, "ready", "Settled", token=token)
    return store, job, stage


@pytest.mark.parametrize("child", [True, False])
def test_settled_recovery_lists_no_processes_and_resume_frees_its_files(
    tmp_path, child
):
    # Recovery reaching "ready" proved every recorded child gone; a crash during
    # conversion must not leave the old card stuck after Resume.
    store, job, stage = settled(tmp_path, child=child)
    assert store.recovery_records()[0]["ownership"]["children"] == []
    store.begin(replace(job, run_id="resumed"), superseded_run_id=job.run_id)
    assert [j.run_id for j in store.load_terminal_jobs()] == []
    assert (stage / "video.part").exists()  # kept while the resumed run is live
    store.clear("resumed")
    store.release_superseded()
    assert not stage.exists()
    assert not store.path.exists()


@pytest.mark.parametrize("child", [True, False])
def test_removing_a_settled_paused_run_deletes_its_partial_files(tmp_path, child):
    store, job, stage = settled(tmp_path, child=child)
    assert store.holds_settled_partial(job.run_id)
    assert store.clear(job.run_id, terminal_only=True)
    assert not stage.exists()
    assert store.load_terminal_jobs() == []


def test_unsettled_recoveries_stay_protected_from_removal(tmp_path):
    store, job, stage = interrupted(tmp_path)
    store.prepare_recovery()
    assert not store.holds_settled_partial(job.run_id)  # pending
    assert not store.clear(job.run_id, terminal_only=True)
    token = store.claim_recovery(job.run_id)
    assert not store.clear(job.run_id, terminal_only=True)  # in flight
    store.finish_recovery(job.run_id, "failed", "Preserved", token=token)
    assert not store.holds_settled_partial(job.run_id)
    assert not store.clear(job.run_id, terminal_only=True)
    assert (stage / "video.part").read_bytes() == b"private partial"


def test_settled_removal_refuses_staging_outside_its_output(tmp_path):
    store, job, _stage = settled(tmp_path, child=False)
    payload = store.load()
    outside = tmp_path / "elsewhere" / ".vfstage" / "owned"
    outside.mkdir(parents=True)
    payload["recovered_failures"][0]["ownership"]["staging_dirs"] = [str(outside)]
    store.path.write_text(json.dumps(payload))
    assert not store.clear(job.run_id, terminal_only=True)
    assert outside.exists()
