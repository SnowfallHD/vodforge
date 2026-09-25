"""Real isolated filesystem fixtures; these tests never touch user media."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from threading import Event

import pytest

from yt_downloader import archive_file_operations as ops
from yt_downloader.history import history_archive_owner


@pytest.fixture
def item(tmp_path):
    folder = (tmp_path / "item").resolve()
    folder.mkdir()
    media = folder / "video.mp4"
    media.write_bytes(b"fixture media")
    return {
        "id": "fixture-id",
        "title": "Fixture",
        "vodforge_output_type": "MP4",
        "vodforge_recorded_at": "2026-09-17T00:00:00+00:00",
        "vodforge_output_path": str(media),
        "vodforge_output_dir": str(folder),
    }


def plan(record, records=None):
    return ops.plan_file_operation(records or [record], [history_archive_owner(record)])


def test_exact_media_and_proven_companions_only(item):
    folder = ops.Path(item["vodforge_output_dir"])
    (folder / "metadata.json").write_text(json.dumps({"id": item["id"]}))
    (folder / "thumbnail.jpg").write_bytes(b"fixture thumbnail")
    (folder / "personal.txt").write_text("unowned")
    result = plan(item)
    assert result.counts == {"ready": 1}
    assert {a.path.name for a in result.items[0].artifacts} == {
        "video.mp4",
        "metadata.json",
        "thumbnail.jpg",
    }
    assert ops.recheck_file_operation(result, [item]) == result


def test_thumbnail_without_matching_metadata_is_not_claimed(item):
    (ops.Path(item["vodforge_output_dir"]) / "thumbnail.jpg").write_bytes(b"x")
    assert [a.path.name for a in plan(item).items[0].artifacts] == ["video.mp4"]


@pytest.mark.parametrize("mutation", ["removed", "replaced", "changed", "history"])
def test_confirmation_rechecks_identity_and_content(item, mutation):
    result = plan(item)
    media = ops.Path(item["vodforge_output_path"])
    if mutation == "removed":
        media.unlink()
    elif mutation == "replaced":
        media.unlink()
        media.write_bytes(b"replacement")
    elif mutation == "changed":
        media.write_bytes(b"changed data")
    else:
        item["title"] = "updated"
    with pytest.raises(ValueError, match="changed"):
        ops.recheck_file_operation(result, [item])


def test_exact_missing_leaf_differs_from_unreachable_folder(item):
    media = ops.Path(item["vodforge_output_path"])
    media.unlink()
    assert plan(item).counts == {"missing": 1}
    media.parent.rmdir()
    assert plan(item).counts == {"unavailable": 1}


def test_access_error_never_proves_missing(item, monkeypatch):
    def denied(_):
        raise PermissionError("fixture")

    monkeypatch.setattr(ops, "directory_evidence", denied)
    assert plan(item).counts == {"unavailable": 1}


@pytest.mark.parametrize("peer_kind", ["same", "sibling", "legacy"])
def test_hidden_durable_peers_prevent_appropriating_files(item, peer_kind):
    peer = dict(item, id="another")
    if peer_kind == "sibling":
        peer["vodforge_output_path"] = str(
            ops.Path(item["vodforge_output_dir"]) / "other.mp4"
        )
    elif peer_kind == "legacy":
        peer.pop("vodforge_output_path")
    assert plan(item, [item, peer]).counts == {"ambiguous": 1}


@pytest.mark.parametrize("location", ["leaf", "ancestor", "metadata", "thumbnail"])
def test_redirected_paths_never_gain_file_authority(item, location, tmp_path):
    media = ops.Path(item["vodforge_output_path"])
    outside = (tmp_path / "outside").resolve()
    outside.write_bytes(b"untouched")
    if location == "leaf":
        media.unlink()
        media.symlink_to(outside)
    elif location == "ancestor":
        original = media.parent
        moved = original.with_name("renamed")
        original.rename(moved)
        original.symlink_to(moved, target_is_directory=True)
    else:
        if location == "thumbnail":
            (media.parent / "metadata.json").write_text(json.dumps({"id": item["id"]}))
        (
            media.parent
            / ("metadata.json" if location == "metadata" else "thumbnail.jpg")
        ).symlink_to(outside)
    assert plan(item).counts == {"ambiguous": 1}
    assert outside.read_bytes() == b"untouched"


def test_hard_linked_media_is_not_exclusive(item, tmp_path):
    os.link(item["vodforge_output_path"], tmp_path / "also-owned")
    assert plan(item).counts == {"ambiguous": 1}


@pytest.mark.parametrize("content", ['{"id":"someone-else"}', "[]", "broken"])
def test_unowned_or_invalid_metadata_blocks_operation(item, content):
    (ops.Path(item["vodforge_output_dir"]) / "metadata.json").write_text(content)
    assert plan(item).counts == {"ambiguous": 1}


def test_zero_byte_exact_regular_file_is_existing_not_missing(item):
    ops.Path(item["vodforge_output_path"]).write_bytes(b"")
    assert plan(item).counts == {"ready": 1}


def test_cancelled_preflight_and_unknown_owner(item):
    event = Event()
    event.set()
    result = ops.plan_file_operation(
        [item], [history_archive_owner(item)], cancelled=event
    )
    assert result.counts == {"cancelled": 1}
    assert ops.plan_file_operation([item], ["retired"]).counts == {"changed": 1}


def test_ancestor_replacement_invalidates_confirmation(item):
    result = plan(item)
    changed = replace(result.items[0], ancestors=())
    with pytest.raises(ValueError, match="changed"):
        ops.recheck_file_operation(replace(result, items=(changed,)), [item])


@pytest.fixture
def move_context(item, tmp_path):
    destination = (tmp_path / "destination").resolve()
    destination.mkdir()
    history = tmp_path / "history.json"
    ops._save_durable_history(history, [item])
    return destination, history, tmp_path / "file-operations"


def move(item, context, **kwargs):
    return ops.move_files(
        ops.plan_move_operation([item], [history_archive_owner(item)], context[0]),
        [item],
        *context,
        **kwargs,
    )


def test_move_copies_verifies_publishes_then_retires_owned_files(item, move_context):
    folder = ops.Path(item["vodforge_output_dir"])
    (folder / "metadata.json").write_text(json.dumps({"id": item["id"]}))
    (folder / "thumbnail.jpg").write_bytes(b"picture")
    (folder / "personal.txt").write_text("keep")
    original = ops.Path(item["vodforge_output_path"]).read_bytes()
    result = move(item, move_context)
    destination, history, _ = move_context
    output = destination / folder.name / "video.mp4"
    assert result.outcomes == ((history_archive_owner(item), "completed"),)
    assert output.read_bytes() == original
    assert (output.parent / "metadata.json").exists()
    assert (output.parent / "thumbnail.jpg").read_bytes() == b"picture"
    assert not ops.Path(item["vodforge_output_path"]).exists()
    assert (folder / "personal.txt").read_text() == "keep"
    assert result.records[0]["vodforge_output_path"] == str(output)
    assert result.records[0]["vodforge_archive_annotation_owner"]
    assert json.loads(history.read_text())["items"] == list(result.records)
    assert json.loads(result.journal.read_text())["state"] == "completed"


def test_move_never_overwrites_an_existing_item_folder(item, move_context):
    destination, history, _ = move_context
    target = destination / "item"
    target.mkdir()
    (target / "video.mp4").write_bytes(b"other owner")
    before = history.read_bytes()
    result = move(item, move_context)
    assert result.outcomes[0][1] == "conflict"
    assert (target / "video.mp4").read_bytes() == b"other owner"
    assert ops.Path(item["vodforge_output_path"]).read_bytes() == b"fixture media"
    assert history.read_bytes() == before


@pytest.mark.parametrize(
    "fault",
    [
        "destination_claimed",
        "artifact_copied",
        "copies_verified",
        "before_history",
        "history_saved",
        "source_retired",
    ],
)
def test_move_boundary_faults_preserve_a_recoverable_media_copy(
    item, move_context, fault
):
    _, history, _ = move_context
    before = history.read_bytes()

    def fail(boundary):
        if boundary == fault:
            raise OSError("injected boundary failure")

    result = move(item, move_context, boundary=fail)
    receipt = json.loads(result.journal.read_text())
    entry = receipt["items"][0]
    assert receipt["state"] == "needs_attention"
    assert entry["state"] in {"needs_attention", "cleanup_pending"}
    source = ops.Path(item["vodforge_output_path"])
    if fault in {"history_saved", "source_retired"}:
        target = ops.Path(result.records[0]["vodforge_output_path"])
        assert target.read_bytes() == b"fixture media"
        assert json.loads(history.read_text())["items"] == list(result.records)
        if fault == "source_retired":
            assert ops.Path(entry["retired"]).read_bytes() == b"fixture media"
        else:
            assert source.read_bytes() == b"fixture media"
    else:
        assert source.read_bytes() == b"fixture media"
        assert history.read_bytes() == before


def test_cancel_after_verified_copy_keeps_source_and_old_history(item, move_context):
    event = Event()
    before = move_context[1].read_bytes()

    def cancel(boundary):
        if boundary == "copies_verified":
            event.set()

    result = move(item, move_context, cancelled=event, boundary=cancel)
    assert result.outcomes[0][1] == "cancelled"
    assert move_context[1].read_bytes() == before
    assert ops.Path(item["vodforge_output_path"]).read_bytes() == b"fixture media"


def test_changed_source_after_copy_is_not_removed_or_published(item, move_context):
    before = move_context[1].read_bytes()

    def change(boundary):
        if boundary == "copies_verified":
            ops.Path(item["vodforge_output_path"]).write_bytes(b"another file")

    result = move(item, move_context, boundary=change)
    assert result.outcomes[0][1] == "needs_attention"
    assert move_context[1].read_bytes() == before
    assert ops.Path(item["vodforge_output_path"]).read_bytes() == b"another file"


def test_failed_copy_verification_keeps_source_and_history(
    item, move_context, monkeypatch
):
    before = move_context[1].read_bytes()
    monkeypatch.setattr(ops, "_hash_file", lambda *_: "wrong hash")
    result = move(item, move_context)
    assert result.outcomes[0][1] == "needs_attention"
    assert move_context[1].read_bytes() == before
    assert ops.Path(item["vodforge_output_path"]).read_bytes() == b"fixture media"


def test_cancel_after_history_publication_keeps_both_copies(item, move_context):
    event = Event()

    def cancel(boundary):
        if boundary == "history_saved":
            event.set()

    result = move(item, move_context, cancelled=event, boundary=cancel)
    assert result.outcomes[0][1] == "cleanup_pending"
    assert ops.Path(item["vodforge_output_path"]).read_bytes() == b"fixture media"
    assert (
        ops.Path(result.records[0]["vodforge_output_path"]).read_bytes()
        == b"fixture media"
    )


def test_history_save_failure_retains_source_and_recovery_receipt(
    item, move_context, monkeypatch
):
    from yt_downloader import history

    before = move_context[1].read_bytes()

    def failed(*_):
        raise history.HistoryError("fixture failure")

    monkeypatch.setattr(history, "save_history", failed)
    result = move(item, move_context)
    assert result.outcomes[0][1] == "needs_attention"
    assert move_context[1].read_bytes() == before
    assert ops.Path(item["vodforge_output_path"]).read_bytes() == b"fixture media"


def test_failure_after_actual_history_write_adopts_real_publication(
    item, move_context, monkeypatch
):
    original = ops._save_durable_history

    def uncertain(path, records):
        original(path, records)
        raise OSError("flush result unavailable")

    monkeypatch.setattr(ops, "_save_durable_history", uncertain)
    result = move(item, move_context)
    assert result.outcomes[0][1] == "history_uncertain"
    assert json.loads(move_context[1].read_text())["items"] == list(result.records)
    assert result.records[0]["vodforge_output_path"] != item["vodforge_output_path"]
    assert ops.Path(item["vodforge_output_path"]).read_bytes() == b"fixture media"


def test_destination_changed_before_cleanup_preserves_original(item, move_context):
    def change(boundary):
        if boundary == "before_source_cleanup":
            (move_context[0] / "item" / "video.mp4").write_bytes(b"changed destination")

    result = move(item, move_context, boundary=change)
    assert result.outcomes[0][1] == "cleanup_pending"
    assert ops.Path(item["vodforge_output_path"]).read_bytes() == b"fixture media"


@pytest.mark.parametrize("replacement", ["leaf", "ancestor"])
def test_replacement_after_retirement_boundary_is_preserved(
    item, move_context, replacement
):
    replacements = []

    def change(boundary):
        if boundary == "source_retired":
            cleanup = next(
                ops.Path(item["vodforge_output_dir"]).glob(".vodforge-move-*")
            )
            if replacement == "ancestor":
                displaced = cleanup.with_name(cleanup.name + "-preserved")
                cleanup.rename(displaced)
                cleanup.mkdir()
            else:
                (cleanup / "video.mp4").rename(cleanup / "original-retained")
            foreign = cleanup / "video.mp4"
            foreign.write_bytes(b"foreign replacement")
            replacements.append(foreign)

    result = move(item, move_context, boundary=change)
    assert result.outcomes[0][1] == "cleanup_pending"
    assert replacements[0].read_bytes() == b"foreign replacement"


@pytest.mark.parametrize("failed_state", ["history_saved", "cleanup_pending"])
def test_journal_failure_after_publication_requires_authority_reload(
    item, move_context, monkeypatch, failed_state
):
    original = ops.OperationJournal.update

    def update(self, index, state, **facts):
        if state in {failed_state, "cleanup_pending"}:
            raise OSError("receipt disk full")
        original(self, index, state, **facts)

    monkeypatch.setattr(ops.OperationJournal, "update", update)

    def fail(boundary):
        if failed_state == "cleanup_pending" and boundary == "history_saved":
            raise OSError("cleanup blocked")

    with pytest.raises(ops.FileOperationUncertain) as error:
        move(item, move_context, boundary=fail)
    actual = json.loads(move_context[1].read_text())["items"]
    assert actual[0]["vodforge_output_path"] != item["vodforge_output_path"]
    assert ops.Path(item["vodforge_output_path"]).read_bytes() == b"fixture media"
    assert error.value.journal.exists()


def test_cleanup_receipt_tracks_each_artifact_independently(item, move_context):
    folder = ops.Path(item["vodforge_output_dir"])
    (folder / "metadata.json").write_text(json.dumps({"id": item["id"]}))
    (folder / "thumbnail.jpg").write_bytes(b"picture")
    result = move(item, move_context)
    steps = json.loads(result.journal.read_text())["items"][0]["cleanup_steps"]
    assert len(steps) == 3
    assert all(step["state"] == "removed" and step["retired_stamp"] for step in steps)


@pytest.fixture
def fake_trash(tmp_path):
    folder = (tmp_path / "fixture-trash").resolve()
    folder.mkdir()

    def trash(path):
        target = folder / path.name
        if target.exists():
            raise OSError("fixture conflict")
        path.rename(target)
        return str(target)

    return folder, trash


def delete(item, context, **kwargs):
    return ops.delete_files(plan(item), [item], context[1], context[2], **kwargs)


def test_delete_uses_trash_and_removes_history_only_after_success(
    item, move_context, fake_trash
):
    folder, trash = fake_trash
    result = delete(item, move_context, trash=trash)
    assert result.outcomes[0][1] == "completed"
    assert result.records == ()
    assert json.loads(move_context[1].read_text())["items"] == []
    assert (folder / "video.mp4").read_bytes() == b"fixture media"
    receipt = json.loads(result.journal.read_text())["items"][0]
    assert receipt["delete_steps"][0]["state"] == "trashed"


def test_missing_file_removes_only_entry_never_calls_trash(item, move_context):
    ops.Path(item["vodforge_output_path"]).unlink()
    calls = []
    result = delete(item, move_context, trash=lambda path: calls.append(path))
    assert result.outcomes[0][1] == "entry_removed"
    assert result.records == () and calls == []


def test_trash_failure_never_falls_back_to_permanent_delete(item, move_context):
    before = move_context[1].read_bytes()

    def fail(_):
        raise OSError("Trash unavailable")

    result = delete(item, move_context, trash=fail)
    assert result.outcomes[0][1] == "needs_attention"
    assert ops.Path(item["vodforge_output_path"]).read_bytes() == b"fixture media"
    assert move_context[1].read_bytes() == before
    step = json.loads(result.journal.read_text())["items"][0]["delete_steps"][0]
    assert step["state"] == "trash_requested"


def test_explicit_permanent_mode_is_separate_from_trash(item, move_context):
    calls = []
    result = delete(
        item, move_context, permanent=True, trash=lambda path: calls.append(path)
    )
    assert result.outcomes[0][1] == "completed"
    assert not ops.Path(item["vodforge_output_path"]).exists()
    assert calls == [] and result.records == ()


def test_delete_history_failure_keeps_entry_and_trash_receipt(
    item, move_context, fake_trash, monkeypatch
):
    from yt_downloader import history

    before = move_context[1].read_bytes()

    def fail(*_):
        raise history.HistoryError("fixture failure")

    monkeypatch.setattr(history, "save_history", fail)
    result = delete(item, move_context, trash=fake_trash[1])
    assert result.outcomes[0][1] == "needs_attention"
    assert move_context[1].read_bytes() == before
    assert result.records == (item,)
    assert (fake_trash[0] / "video.mp4").read_bytes() == b"fixture media"
    receipt = json.loads(result.journal.read_text())["items"][0]
    assert receipt["delete_steps"][0]["state"] == "trashed"


def test_uncertain_trash_boundary_is_not_recorded_as_completed(
    item, move_context, fake_trash
):
    def fail(boundary):
        if boundary == "file_deleted":
            raise OSError("result receipt interrupted")

    result = delete(item, move_context, trash=fake_trash[1], boundary=fail)
    assert result.records == (item,)
    assert result.outcomes[0][1] == "needs_attention"
    assert (fake_trash[0] / "video.mp4").exists()
    step = json.loads(result.journal.read_text())["items"][0]["delete_steps"][0]
    assert step["state"] == "trash_requested"


def test_partial_companion_failure_keeps_history_and_each_outcome(
    item, move_context, fake_trash
):
    folder = ops.Path(item["vodforge_output_dir"])
    (folder / "metadata.json").write_text(json.dumps({"id": item["id"]}))

    def trash(path):
        if path.name == "metadata.json":
            raise OSError("metadata busy")
        return fake_trash[1](path)

    result = delete(item, move_context, trash=trash)
    assert result.records == (item,)
    assert (folder / "metadata.json").exists()
    steps = json.loads(result.journal.read_text())["items"][0]["delete_steps"]
    assert [step["state"] for step in steps] == ["trashed", "trash_requested"]


def test_delete_rechecks_after_confirmation(item, move_context, fake_trash):
    confirmed = plan(item)
    ops.Path(item["vodforge_output_path"]).write_bytes(b"replacement")
    with pytest.raises(ValueError, match="changed"):
        ops.delete_files(
            confirmed, [item], move_context[1], move_context[2], trash=fake_trash[1]
        )
    assert ops.Path(item["vodforge_output_path"]).read_bytes() == b"replacement"
    assert list(fake_trash[0].iterdir()) == []


def test_delete_mixed_existing_and_missing_preserves_partial_failure(
    item, move_context, fake_trash, tmp_path
):
    missing_folder = (tmp_path / "missing-item").resolve()
    missing_folder.mkdir()
    missing = dict(
        item,
        id="missing",
        vodforge_output_dir=str(missing_folder),
        vodforge_output_path=str(missing_folder / "missing.mp4"),
    )
    records = [item, missing]
    confirmed = ops.plan_file_operation(
        records, [history_archive_owner(row) for row in records]
    )
    assert confirmed.counts == {"ready": 1, "missing": 1}
    result = ops.delete_files(
        confirmed, records, move_context[1], move_context[2], trash=fake_trash[1]
    )
    assert [state for _, state in result.outcomes] == ["completed", "entry_removed"]
    assert result.records == ()


@pytest.mark.parametrize("initial", ["missing", "existing"])
def test_file_appearing_before_history_removal_is_preserved(
    item, move_context, fake_trash, initial
):
    source = ops.Path(item["vodforge_output_path"])
    if initial == "missing":
        source.unlink()

    def appear(boundary):
        if boundary == "before_history":
            source.write_bytes(b"new file")

    result = delete(item, move_context, trash=fake_trash[1], boundary=appear)
    assert result.outcomes[0][1] == "needs_attention"
    assert result.records == (item,)
    assert source.read_bytes() == b"new file"


def test_restart_receipt_blocks_repeating_an_uncertain_trash_call(
    item, move_context, fake_trash
):
    calls = []

    def trash(path):
        calls.append(str(path))
        fake_trash[1](path)
        raise OSError("receipt unknown")

    result = delete(item, move_context, trash=trash)
    pending = ops.pending_file_operations(move_context[2])
    assert len(pending) == 1 and pending[0].path == result.journal
    # After restart this exact path looks missing, but the prior intent must be
    # reconciled before a fresh operation can act on that state.
    with pytest.raises(ValueError, match="interrupted"):
        delete(item, move_context, trash=trash)
    assert len(calls) == 1
    assert json.loads(move_context[1].read_text())["items"] == [item]


def test_successful_operation_receipt_does_not_block_future_work(item, move_context):
    result = move(item, move_context)
    assert json.loads(result.journal.read_text())["state"] == "completed"
    assert ops.pending_file_operations(move_context[2]) == ()


def test_malformed_or_redirected_recovery_receipt_fails_closed(tmp_path):
    folder = (tmp_path / "file-operations").resolve()
    folder.mkdir()
    bad = folder / "bad.json"
    bad.write_text("not a receipt")
    with pytest.raises(ValueError):
        ops.pending_file_operations(folder)
    bad.unlink()
    foreign = tmp_path / "foreign.json"
    foreign.write_text("{}")
    bad.symlink_to(foreign)
    with pytest.raises(ValueError):
        ops.pending_file_operations(folder)


def test_move_preserves_local_progress_key_across_history_reload(item, move_context):
    from yt_downloader.history import load_history
    from yt_downloader.playback_progress import progress_key

    item.pop("id")
    before = progress_key(item)
    result = move(item, move_context)
    assert result.outcomes[0][1] == "completed"
    assert progress_key(result.records[0]) == before
    reloaded = load_history(move_context[1])
    assert progress_key(reloaded[0]) == before


def test_interrupted_publication_blocks_other_history_writers(item, move_context):
    from yt_downloader.history import HistoryError, load_history, save_history

    event = Event()

    def cancel(boundary):
        if boundary == "history_saved":
            event.set()

    result = move(item, move_context, cancelled=event, boundary=cancel)
    before = move_context[1].read_bytes()
    with pytest.raises(HistoryError, match="interrupted"):
        save_history(move_context[1], [item])
    assert move_context[1].read_bytes() == before
    assert (
        load_history(move_context[1])[0]["vodforge_output_path"]
        == result.records[0]["vodforge_output_path"]
    )


def test_fresh_process_reads_recovery_gate_and_actual_history(item, move_context):
    import subprocess
    import sys

    event = Event()

    def cancel(boundary):
        if boundary == "history_saved":
            event.set()

    result = move(item, move_context, cancelled=event, boundary=cancel)
    script = """
import json,sys
from pathlib import Path
from yt_downloader.history import load_history,save_history,HistoryError
path=Path(sys.argv[1])
records=load_history(path)
blocked=False
try:
    save_history(path,[])
except HistoryError:
    blocked=True
print(json.dumps({"blocked":blocked,"path":records[0]["vodforge_output_path"]}))
"""
    checked = subprocess.run(
        [sys.executable, "-c", script, str(move_context[1])],
        capture_output=True,
        text=True,
        check=True,
    )
    observed = json.loads(checked.stdout)
    assert observed == {
        "blocked": True,
        "path": result.records[0]["vodforge_output_path"],
    }
    assert ops.Path(item["vodforge_output_path"]).read_bytes() == b"fixture media"


@pytest.mark.parametrize(
    "boundary_name", ["history_saved", "source_retired", "cleanup_removed"]
)
def test_published_move_recovers_in_a_fresh_process(item, move_context, boundary_name):
    import subprocess
    import sys

    def interrupt(boundary):
        if boundary == boundary_name:
            raise OSError("fixture interruption")

    result = move(item, move_context, boundary=interrupt)
    script = """
import json,sys
from pathlib import Path
from yt_downloader.history import load_history
from yt_downloader.archive_file_operations import recover_move_cleanup
history=Path(sys.argv[1])
result=recover_move_cleanup(Path(sys.argv[2]),load_history(history),history)
print(json.dumps(list(result.outcomes)))
"""
    checked = subprocess.run(
        [sys.executable, "-c", script, str(move_context[1]), str(result.journal)],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert checked.returncode == 0, checked.stderr
    assert json.loads(checked.stdout)[0][1] == "completed"
    assert not ops.Path(item["vodforge_output_path"]).exists()
    assert (
        ops.Path(result.records[0]["vodforge_output_path"]).read_bytes()
        == b"fixture media"
    )
    assert ops.pending_file_operations(move_context[2]) == ()


def test_recovery_reestablishes_durability_before_cleanup(
    item, move_context, monkeypatch
):
    event = Event()

    def cancel(boundary):
        if boundary == "history_saved":
            event.set()

    result = move(item, move_context, cancelled=event, boundary=cancel)

    def fail(*_):
        raise OSError("history flush unavailable")

    monkeypatch.setattr(ops, "_save_durable_history", fail)
    with pytest.raises(OSError, match="flush"):
        ops.recover_move_cleanup(result.journal, result.records, move_context[1])
    assert ops.Path(item["vodforge_output_path"]).read_bytes() == b"fixture media"


def test_recovery_preserves_foreign_retired_replacement(item, move_context):
    def fail(boundary):
        if boundary == "source_retired":
            raise OSError("pause")

    result = move(item, move_context, boundary=fail)
    receipt = json.loads(result.journal.read_text())["items"][0]
    retired = ops.Path(receipt["retired"])
    retired.rename(retired.with_suffix(".retained"))
    retired.write_bytes(b"foreign")
    with pytest.raises(ValueError, match="identity"):
        ops.recover_move_cleanup(result.journal, result.records, move_context[1])
    assert retired.read_bytes() == b"foreign"


def test_recovery_does_not_delete_source_when_destination_was_changed(
    item, move_context
):
    event = Event()

    def cancel(boundary):
        if boundary == "history_saved":
            event.set()

    result = move(item, move_context, cancelled=event, boundary=cancel)
    ops.Path(result.records[0]["vodforge_output_path"]).write_bytes(b"changed")
    with pytest.raises(ValueError):
        ops.recover_move_cleanup(result.journal, result.records, move_context[1])
    assert ops.Path(item["vodforge_output_path"]).read_bytes() == b"fixture media"


def test_keep_current_state_unblocks_writers_without_repeating_file_effects(
    item, move_context, fake_trash
):
    from yt_downloader.history import load_history, save_history

    calls = []

    def uncertain(path):
        calls.append(str(path))
        fake_trash[1](path)
        raise OSError("unknown completion")

    result = delete(item, move_context, trash=uncertain)
    current = load_history(move_context[1])
    ops.keep_current_file_state(result.journal, current, move_context[1])
    assert len(calls) == 1 and ops.pending_file_operations(move_context[2]) == ()
    assert (fake_trash[0] / "video.mp4").read_bytes() == b"fixture media"
    assert json.loads(result.journal.read_text())["state"] == "kept_files"
    save_history(move_context[1], current)


def test_keep_current_state_requires_actual_history_not_old_memory(item, move_context):
    event = Event()

    def cancel(boundary):
        if boundary == "history_saved":
            event.set()

    result = move(item, move_context, cancelled=event, boundary=cancel)
    with pytest.raises(ValueError, match="changed"):
        ops.keep_current_file_state(result.journal, [item], move_context[1])
    assert ops.pending_file_operations(move_context[2])


def test_keep_current_state_cannot_clear_gate_after_failed_flush(
    item, move_context, monkeypatch
):
    from yt_downloader.history import load_history

    event = Event()

    def cancel(boundary):
        if boundary == "history_saved":
            event.set()

    result = move(item, move_context, cancelled=event, boundary=cancel)

    def fail(*_):
        raise OSError("flush failed")

    monkeypatch.setattr(ops, "_save_durable_history", fail)
    with pytest.raises(OSError):
        ops.keep_current_file_state(
            result.journal, load_history(move_context[1]), move_context[1]
        )
    assert ops.pending_file_operations(move_context[2])


def test_move_destination_claims_include_hidden_offline_history(item, move_context):
    target = move_context[0] / "item"
    peer = dict(
        item,
        id="offline-peer",
        vodforge_output_dir=str(target),
        vodforge_output_path=str(target / "old.mp4"),
    )
    proposal = ops.plan_move_operation(
        [item, peer], [history_archive_owner(item)], move_context[0]
    )
    assert proposal.counts == {"conflict": 1}
    assert not target.exists()


def test_bulk_move_duplicate_folder_names_are_visible_conflicts(
    item, move_context, tmp_path
):
    folder = (tmp_path / "elsewhere" / "item").resolve()
    folder.mkdir(parents=True)
    path = folder / "second.mp4"
    path.write_bytes(b"second")
    other = dict(
        item,
        id="other",
        vodforge_output_dir=str(folder),
        vodforge_output_path=str(path),
    )
    records = [item, other]
    proposal = ops.plan_move_operation(
        records, [history_archive_owner(row) for row in records], move_context[0]
    )
    assert proposal.counts == {"conflict": 2}
    assert list(move_context[0].iterdir()) == []


def test_move_rechecks_destination_after_review(item, move_context):
    proposal = ops.plan_move_operation(
        [item], [history_archive_owner(item)], move_context[0]
    )
    (move_context[0] / "item").mkdir()
    with pytest.raises(ValueError, match="destination changed"):
        ops.move_files(proposal, [item], *move_context)
    assert ops.Path(item["vodforge_output_path"]).exists()


def test_case_alias_durable_peer_cannot_gain_duplicate_file_authority(item):
    peer = dict(
        item,
        id="different-row",
        vodforge_output_dir=item["vodforge_output_dir"].upper(),
        vodforge_output_path=item["vodforge_output_path"].upper(),
    )
    assert plan(item, [item, peer]).counts == {"ambiguous": 1}


def test_finished_receipt_retention_is_bounded_without_touching_media(item, tmp_path):
    folder = (tmp_path / "file-operations").resolve()
    for _ in range(42):
        receipt = ops.OperationJournal(folder, "move", ops.FileOperationPlan((), ()))
        receipt.document["state"] = "completed"
        receipt.write()
    assert len(list(folder.glob("*.json"))) == 42
    ops._retire_finished_receipts(folder)
    assert len(list(folder.glob("*.json"))) == 32
    assert ops.Path(item["vodforge_output_path"]).read_bytes() == b"fixture media"


@pytest.mark.parametrize("action", ["move", "delete"])
def test_staged_same_run_record_does_not_restore_old_path_or_deleted_entry(
    item, move_context, fake_trash, action
):
    from yt_downloader.history import load_history, stage_history_mutation

    item["vodforge_run_id"] = "original-run"

    def stage(boundary):
        if boundary == "before_history":
            stage_history_mutation(
                move_context[1],
                {
                    "kind": "record",
                    "record": dict(item, vodforge_run_activity=["late activity"]),
                },
            )

    if action == "move":
        result = move(item, move_context, boundary=stage)
    else:
        result = delete(item, move_context, trash=fake_trash[1], boundary=stage)
    settled = load_history(move_context[1])
    if action == "move":
        assert len(settled) == 1
        assert (
            settled[0]["vodforge_output_path"]
            == result.records[0]["vodforge_output_path"]
        )
        assert settled[0]["vodforge_run_activity"] == ["late activity"]
    else:
        assert settled == []


def test_new_run_is_not_suppressed_by_a_prior_delete_receipt(
    item, move_context, fake_trash
):
    from yt_downloader.history import load_history, stage_history_mutation

    item["vodforge_run_id"] = "old-run"
    delete(item, move_context, trash=fake_trash[1])
    source = ops.Path(item["vodforge_output_path"])
    source.write_bytes(b"fresh new download")
    new = dict(
        item,
        vodforge_run_id="new-run",
        vodforge_recorded_at="2026-09-18T00:00:00+00:00",
    )
    stage_history_mutation(move_context[1], {"kind": "record", "record": new})
    settled = load_history(move_context[1])
    assert len(settled) == 1 and settled[0]["vodforge_run_id"] == "new-run"
    assert source.read_bytes() == b"fresh new download"


def test_history_write_lease_is_payload_scoped_and_cleared_after_exception(
    item, move_context
):
    from yt_downloader.history import (
        HistoryError,
        file_operation_history_write,
        load_history,
        save_history,
    )

    event = Event()

    def cancel(boundary):
        if boundary == "history_saved":
            event.set()

    result = move(item, move_context, cancelled=event, boundary=cancel)
    actual = load_history(move_context[1])
    with (
        pytest.raises(RuntimeError, match="fixture interruption"),
        file_operation_history_write(result.journal, actual),
    ):
        with pytest.raises(HistoryError):
            save_history(move_context[1], [])
        raise RuntimeError("fixture interruption")
    with pytest.raises(HistoryError):
        save_history(move_context[1], actual)
    assert load_history(move_context[1]) == actual


@pytest.mark.parametrize("replacement", ["source", "cleanup"])
def test_removed_cleanup_recovery_preserves_replacements(
    item, move_context, replacement, monkeypatch
):
    def interrupt(boundary):
        if boundary == "cleanup_removed":
            raise OSError("interrupted after directory removal")

    result = move(item, move_context, boundary=interrupt)
    entry = json.loads(result.journal.read_text())["items"][0]
    if replacement == "source":
        foreign = ops.Path(item["vodforge_output_path"])
    else:
        directory = ops.Path(entry["cleanup"])
        directory.mkdir()
        foreign = directory / "unrelated.txt"
        # A replacement folder may reuse the original inode on Linux. Force
        # that observation on every platform so the nonempty removal boundary
        # still preserves foreign contents.
        recorded = tuple(
            (ops.Path(path), int(device), int(inode))
            for path, device, inode in entry["cleanup_proof"]
        )
        actual_evidence = ops.directory_evidence
        monkeypatch.setattr(
            ops,
            "directory_evidence",
            lambda path: (
                recorded if ops.Path(path) == directory else actual_evidence(path)
            ),
        )
    foreign.write_bytes(b"foreign replacement")
    with pytest.raises(ValueError, match="changed"):
        ops.recover_move_cleanup(result.journal, result.records, move_context[1])
    assert foreign.read_bytes() == b"foreign replacement"
    assert ops.pending_file_operations(move_context[2])


@pytest.mark.parametrize("invalid", ["oversized", "schema", "redirect"])
def test_late_delta_reconciliation_rejects_unreadable_receipts(
    item, move_context, invalid
):
    result = move(item, move_context)
    if invalid == "oversized":
        with result.journal.open("wb") as stream:
            stream.truncate(16 * 1024 * 1024 + 1)
    elif invalid == "schema":
        result.journal.write_text('{"state":"completed","items":[null]}')
    else:
        original = result.journal.with_suffix(".saved")
        result.journal.rename(original)
        result.journal.symlink_to(original)
    with pytest.raises(ValueError):
        ops.reconcile_file_record_delta(item, result.records, move_context[2])


@pytest.mark.parametrize("last_action", ["move", "delete"])
def test_original_run_delta_follows_repeated_move_and_delete(
    item, move_context, fake_trash, tmp_path, last_action
):
    from yt_downloader.history import load_history, stage_history_mutation

    item["vodforge_run_id"] = "original-run"
    first = move(item, move_context)
    current = dict(first.records[0])
    if last_action == "move":
        destination = (tmp_path / "third-location").resolve()
        destination.mkdir()
        second = move(current, (destination, move_context[1], move_context[2]))
    else:
        second = delete(current, move_context, trash=fake_trash[1])
    stage_history_mutation(
        move_context[1],
        {"kind": "record", "record": dict(item, vodforge_run_activity=["late"])},
    )
    actual = load_history(move_context[1])
    if last_action == "delete":
        assert actual == []
    else:
        assert len(actual) == 1
        assert (
            actual[0]["vodforge_output_path"]
            == second.records[0]["vodforge_output_path"]
        )
        assert actual[0]["vodforge_run_activity"] == ["late"]


def test_same_session_delta_remains_protected_after_many_operations(
    item, move_context, fake_trash
):
    from yt_downloader.history import load_history, stage_history_mutation

    item["vodforge_run_id"] = "original-run"
    delete(item, move_context, trash=fake_trash[1])
    for _ in range(40):
        receipt = ops.OperationJournal(
            move_context[2], "move", ops.FileOperationPlan((), ())
        )
        receipt.document["state"] = "completed"
        receipt.write()
    stage_history_mutation(move_context[1], {"kind": "record", "record": item})
    assert load_history(move_context[1]) == []


@pytest.mark.parametrize("action", ["finish", "keep"])
@pytest.mark.parametrize("replacement", ["corrupt", "replace"])
def test_recovery_rejects_receipt_change_after_validation(
    item, move_context, monkeypatch, action, replacement
):
    event = Event()

    def stop(boundary):
        if boundary == "history_saved":
            event.set()

    result = move(item, move_context, cancelled=event, boundary=stop)
    original = ops._save_durable_history

    def change_after_save(path, records):
        original(path, records)
        if replacement == "replace":
            result.journal.unlink()
        result.journal.write_text('{"foreign":"leave untouched"}')

    monkeypatch.setattr(ops, "_save_durable_history", change_after_save)
    recover = (
        ops.recover_move_cleanup if action == "finish" else ops.keep_current_file_state
    )
    with pytest.raises(ValueError, match="receipt changed"):
        recover(result.journal, result.records, move_context[1])
    assert ops.Path(item["vodforge_output_path"]).read_bytes() == b"fixture media"
    assert result.journal.read_text() == '{"foreign":"leave untouched"}'


def test_stable_archive_owner_delta_keeps_latest_move_path(
    item, move_context, tmp_path
):
    item["vodforge_run_id"] = "same-run"
    first = move(item, move_context)
    previous = dict(first.records[0])
    destination = (tmp_path / "latest").resolve()
    destination.mkdir()
    second = move(previous, (destination, move_context[1], move_context[2]))
    assert history_archive_owner(previous) == history_archive_owner(second.records[0])
    merged = ops.reconcile_file_record_delta(previous, second.records, move_context[2])
    assert merged["vodforge_output_path"] == second.records[0]["vodforge_output_path"]


def test_startup_replays_pending_delta_before_retiring_prior_session_receipts(
    item, move_context, fake_trash
):
    from yt_downloader.history import load_history, stage_history_mutation

    item["vodforge_run_id"] = "prior-process"
    delete(item, move_context, trash=fake_trash[1])
    for _ in range(40):
        receipt = ops.OperationJournal(
            move_context[2], "move", ops.FileOperationPlan((), ())
        )
        receipt.document["state"] = "completed"
        receipt.write()
    stage_history_mutation(move_context[1], {"kind": "record", "record": item})
    assert load_history(move_context[1]) == []
    ops._retire_finished_receipts(move_context[2])
    assert len(list(move_context[2].glob("*.json"))) == 32
    assert load_history(move_context[1]) == []


def test_oversized_initial_receipt_fails_before_media_or_history_effect(
    item, move_context, monkeypatch
):
    from yt_downloader.history import file_operations_pending, load_history

    before = move_context[1].read_bytes()
    monkeypatch.setattr(ops, "MAX_RECEIPT_BYTES", 100)
    with pytest.raises(ValueError, match="selection is too large"):
        move(item, move_context)
    assert ops.Path(item["vodforge_output_path"]).read_bytes() == b"fixture media"
    assert list(move_context[0].iterdir()) == []
    assert move_context[1].read_bytes() == before
    assert not file_operations_pending(move_context[1])
    assert load_history(move_context[1])


def test_receipt_inventory_rejects_aggregate_before_parsing(
    item, move_context, monkeypatch
):
    result = move(item, move_context)
    monkeypatch.setattr(ops, "MAX_RECEIPT_TOTAL_BYTES", 100)
    monkeypatch.setattr(
        ops.json, "loads", lambda *_: pytest.fail("must reject before parsing")
    )
    with pytest.raises(ValueError, match="storage needs review"):
        ops.pending_file_operations(move_context[2])
    assert ops.Path(result.records[0]["vodforge_output_path"]).exists()


def test_unchanged_receipts_are_identity_checked_without_reparsing(
    item, move_context, monkeypatch
):
    move(item, move_context)
    ops.pending_file_operations(move_context[2])
    original = ops.json.loads
    reads = []
    monkeypatch.setattr(
        ops.json, "loads", lambda value: reads.append(len(value)) or original(value)
    )
    for _ in range(5):
        assert ops.pending_file_operations(move_context[2]) == ()
    assert reads == []


def test_journal_admission_reserves_recovery_growth_before_effect(
    item, move_context, monkeypatch
):
    receipt = ops.OperationJournal(
        move_context[2], "move", ops.FileOperationPlan((), ())
    )
    receipt.document["state"] = "completed"
    receipt.write()
    monkeypatch.setattr(ops, "MAX_RECEIPT_TOTAL_BYTES", ops.MAX_RECEIPT_BYTES)
    with pytest.raises(ValueError, match="storage is full"):
        move(item, move_context)
    assert ops.Path(item["vodforge_output_path"]).exists()
    assert list(move_context[0].iterdir()) == []
    assert ops.pending_file_operations(move_context[2]) == ()


@pytest.mark.parametrize("blocked", ["pending_operation", "replay_failed"])
def test_startup_never_retires_receipts_when_recovery_is_unsettled(
    item, move_context, monkeypatch, blocked
):
    from unittest.mock import Mock

    from tests.test_history_publication import state
    from yt_downloader import app as app_module
    from yt_downloader.archive_library_ui import ArchiveLibraryMixin
    from yt_downloader.history import HistoryError

    view = state(move_context[1].parent)
    view.after_idle = Mock()
    view._show_library_file_recovery = Mock()
    monkeypatch.setattr(ArchiveLibraryMixin, "_archive_history_observe", Mock())
    retirement = Mock()
    monkeypatch.setattr(ops, "_retire_finished_receipts", retirement)
    if blocked == "pending_operation":
        event = Event()

        def stop(boundary):
            if boundary == "history_saved":
                event.set()

        result = move(item, move_context, cancelled=event, boundary=stop)
        view.history_path = move_context[1]
        app_module.DownloaderApp._load_download_history(view)
        assert view._archive_file_recovery_blocked
        assert (
            view.download_history[0]["vodforge_output_path"]
            == result.records[0]["vodforge_output_path"]
        )
    else:
        monkeypatch.setattr(
            app_module, "load_history", Mock(side_effect=HistoryError("replay failed"))
        )
        app_module.DownloaderApp._load_download_history(view)
        assert view._history_recovery_blocked
    retirement.assert_not_called()


def test_kept_uncertain_delete_preserves_committed_absence_against_late_delta(
    item, move_context, fake_trash, monkeypatch
):
    from yt_downloader.history import load_history, stage_history_mutation

    item["vodforge_run_id"] = "original-run"
    original = ops.OperationJournal.update

    def fail_completion(journal, index, state, **facts):
        if state == "completed":
            raise OSError("receipt unavailable after history commit")
        return original(journal, index, state, **facts)

    monkeypatch.setattr(ops.OperationJournal, "update", fail_completion)
    result = delete(item, move_context, trash=fake_trash[1])
    assert result.outcomes[0][1] == "history_uncertain"
    actual = load_history(move_context[1])
    assert actual == []
    ops.keep_current_file_state(result.journal, actual, move_context[1])
    stage_history_mutation(move_context[1], {"kind": "record", "record": item})
    assert load_history(move_context[1]) == []
    receipt = json.loads(result.journal.read_text())
    assert receipt["state"] == "kept_files"
    assert receipt["items"][0]["state"] == "history_uncertain"


def test_reviewed_move_cannot_be_reopened_after_later_delete(
    item, move_context, fake_trash
):
    from yt_downloader.history import load_history

    item["vodforge_run_id"] = "original-run"
    event = Event()

    def stop(boundary):
        if boundary == "history_saved":
            event.set()

    first = move(item, move_context, cancelled=event, boundary=stop)
    with pytest.raises(ValueError, match="Review"):
        move(dict(first.records[0]), move_context)
    ops.keep_current_file_state(first.journal, first.records, move_context[1])
    second = delete(dict(first.records[0]), move_context, trash=fake_trash[1])
    original_mtime = first.journal.stat().st_mtime_ns
    for action in (ops.keep_current_file_state, ops.recover_move_cleanup):
        with pytest.raises(ValueError, match="Review"):
            action(first.journal, second.records, move_context[1])
    assert first.journal.stat().st_mtime_ns == original_mtime
    assert (
        ops.reconcile_file_record_delta(
            item, load_history(move_context[1]), move_context[2]
        )
        is None
    )


@pytest.mark.parametrize("records_present", [False, True])
def test_durable_history_flush_uses_write_capability_without_content_change(
    item, tmp_path, monkeypatch, records_present
):
    import stat

    from yt_downloader.history import load_history

    history_path = tmp_path / "durable-history.json"
    records = [item] if records_present else []
    real_fsync = os.fsync
    flushed = []

    def require_writable_flush(descriptor):
        observed = os.fstat(descriptor)
        if stat.S_ISREG(observed.st_mode):
            # Zero-byte write independently checks the OS descriptor capability,
            # without changing file bytes. Windows fsync requires that capability.
            os.write(descriptor, b"")
            flushed.append((observed.st_dev, observed.st_ino))
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", require_writable_flush)
    ops._save_durable_history(history_path, records)
    before = history_path.read_bytes()
    assert load_history(history_path) == records
    stamp = history_path.stat()
    assert (stamp.st_dev, stamp.st_ino) in flushed
    ops._save_durable_history(history_path, records)
    assert history_path.read_bytes() == before


def test_path_and_open_handle_share_mutation_stamp(tmp_path):
    path = tmp_path / "identity.bin"
    path.write_bytes(b"first")
    path.write_bytes(b"later")  # Creation and mutation times differ on Windows.
    evidence = ops._regular_evidence(path)
    with path.open("rb") as stream:
        assert ops._descriptor_stamp(stream.fileno()) == evidence.stamp
    assert ops._hash_file(path, evidence.stamp, None)


@pytest.mark.parametrize("effect", ["restored-mtime", "replacement"])
def test_file_authority_rejects_same_size_and_restored_mtime(tmp_path, effect):
    import time

    path = tmp_path / "identity.bin"
    path.write_bytes(b"first")
    before = path.stat()
    evidence = ops._regular_evidence(path)
    time.sleep(0.002)  # Cross a filesystem timestamp tick before an actual mutation.
    if effect == "replacement":
        replacement = tmp_path / "other.bin"
        replacement.write_bytes(b"other")
        os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
        os.replace(replacement, path)
    else:
        path.write_bytes(b"other")
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_size == before.st_size
    assert path.stat().st_mtime_ns == before.st_mtime_ns
    assert ops._regular_evidence(path).stamp != evidence.stamp
    with pytest.raises(ValueError, match="changed"):
        ops._hash_file(path, evidence.stamp, None)
