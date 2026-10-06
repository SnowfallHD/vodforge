"""Missing indexed media transfers only verified hierarchy and companions."""

import json
from pathlib import Path
from threading import Event

import pytest

from tests.test_archive_file_operations import item, move_context
from yt_downloader import archive_file_operations as ops
from yt_downloader.history import history_archive_owner, load_history

__all__ = ["item", "move_context"]


def planned(item, context):
    return ops.plan_move_operation([item], [history_archive_owner(item)], context[0])


@pytest.mark.parametrize("parent_exists", [True, False])
def test_preserves_channel_playlist_video_paths_and_missing_index(
    item, move_context, parent_exists
):
    root = Path(item["vodforge_retry_job"]["output_dir"])
    folder = root / "Creator" / "playlists" / "Playlist" / "Video [fixture-id]"
    folder.mkdir(parents=True)
    source = folder / "video.mp4"
    if not parent_exists:
        folder.rmdir()
    item.update(vodforge_output_path=str(source), vodforge_output_dir=str(folder))
    ops._save_durable_history(move_context[1], [item])
    plan = planned(item, move_context)
    assert plan.items[0].missing_media and plan.counts == {"ready": 1}
    result = ops.move_files(plan, [item], *move_context)
    target = move_context[0] / folder.relative_to(root) / source.name
    assert target.parent.is_dir() and not target.exists()
    assert result.records == tuple(load_history(move_context[1]))
    assert result.records[0]["vodforge_output_path"] == str(target)
    assert result.records[0]["vodforge_retry_job"]["output_dir"] == str(move_context[0])
    assert not (root / "Creator").exists()


def test_nested_empty_folders_and_unrelated_files_are_preserved(item, move_context):
    source = Path(item["vodforge_output_path"])
    source.unlink()
    nested = source.parent / "empty" / "nested"
    nested.mkdir(parents=True)
    foreign = source.parent / "private.txt"
    foreign.write_text("unrelated")
    result = ops.move_files(planned(item, move_context), [item], *move_context)
    target = move_context[0] / source.parent.name
    assert (target / "empty" / "nested").is_dir()
    assert not (target / "private.txt").exists()
    assert foreign.read_text() == "unrelated"
    assert not nested.exists()
    assert result.outcomes[0][1] == "completed"


def test_missing_media_copies_and_hash_verifies_owned_companions(item, move_context):
    source = Path(item["vodforge_output_path"])
    source.unlink()
    metadata = source.parent / "metadata.json"
    metadata.write_text(json.dumps({"id": item["id"]}))
    thumbnail = source.parent / "thumbnail.jpg"
    thumbnail.write_bytes(b"owned picture")
    result = ops.move_files(planned(item, move_context), [item], *move_context)
    receipt = json.loads(result.journal.read_text())["items"][0]
    assert len(receipt["copies"]) == 2
    for copy in receipt["copies"]:
        target = Path(copy["destination"])
        assert ops._hash_file(target, tuple(copy["stamp"]), None) == copy["sha256"]
    assert not source.parent.exists()
    assert not Path(result.records[0]["vodforge_output_path"]).exists()


@pytest.mark.parametrize(
    "mutation",
    ["source_media", "nested_redirect", "destination_conflict", "missing_root"],
)
def test_missing_structure_refuses_changed_or_unavailable_locations(
    item, move_context, mutation
):
    source = Path(item["vodforge_output_path"])
    source.unlink()
    plan = planned(item, move_context)
    if mutation == "source_media":
        source.write_bytes(b"new unreviewed media")
    elif mutation == "nested_redirect":
        (source.parent / "redirect").symlink_to(
            move_context[0], target_is_directory=True
        )
    elif mutation == "destination_conflict":
        (move_context[0] / source.parent.name).mkdir()
    else:
        item["vodforge_retry_job"]["output_dir"] = str(source.parent / "absent-root")
    with pytest.raises(ValueError, match="changed"):
        ops.move_files(plan, [item], *move_context)
    assert not (move_context[2]).exists()


@pytest.mark.parametrize(
    "fault",
    [
        "destination_claimed",
        "copies_verified",
        "before_history",
        "history_saved",
        "structure_removed",
    ],
)
def test_missing_structure_faults_keep_consistent_history_and_recovery(
    item, move_context, fault
):
    source = Path(item["vodforge_output_path"])
    source.unlink()
    (source.parent / "nested").mkdir()
    before = move_context[1].read_bytes()

    def fail(boundary):
        if boundary == fault:
            raise OSError("fixture interruption")

    result = ops.move_files(
        planned(item, move_context), [item], *move_context, boundary=fail
    )
    if fault in {"history_saved", "structure_removed"}:
        assert result.records == tuple(load_history(move_context[1]))
        assert result.outcomes[0][1] == "cleanup_pending"
        recovered = ops.recover_move_cleanup(
            result.journal, result.records, move_context[1]
        )
        assert recovered.outcomes[0][1] == "completed"
        assert not source.parent.exists()
        assert Path(recovered.records[0]["vodforge_output_path"]).parent.is_dir()
    else:
        assert move_context[1].read_bytes() == before
        assert source.parent.is_dir()
        assert result.outcomes[0][1] == "needs_attention"
        assert ops.pending_file_operations(move_context[2])


def test_cancel_before_publication_keeps_missing_source_hierarchy(item, move_context):
    source = Path(item["vodforge_output_path"])
    source.unlink()
    event = Event()
    before = move_context[1].read_bytes()

    def cancel(boundary):
        if boundary == "copies_verified":
            event.set()

    result = ops.move_files(
        planned(item, move_context),
        [item],
        *move_context,
        cancelled=event,
        boundary=cancel,
    )
    assert result.outcomes[0][1] == "cancelled"
    assert source.parent.is_dir() and move_context[1].read_bytes() == before


def test_mixed_selection_partial_failure_updates_only_completed_index(
    item, move_context
):
    source = Path(item["vodforge_output_path"])
    source.unlink()
    folder = source.parent.parent / "second"
    folder.mkdir()
    media = folder / "second.mp4"
    media.write_bytes(b"second fixture")
    second = dict(
        item,
        id="second",
        vodforge_output_path=str(media),
        vodforge_output_dir=str(folder),
    )
    records = [item, second]
    ops._save_durable_history(move_context[1], records)
    plan = ops.plan_move_operation(
        records, [history_archive_owner(r) for r in records], move_context[0]
    )
    calls = 0

    def fail_second(boundary):
        nonlocal calls
        if boundary == "before_history":
            calls += 1
            if calls == 2:
                raise OSError("second publication blocked")

    result = ops.move_files(plan, records, *move_context, boundary=fail_second)
    assert [outcome for _, outcome in result.outcomes] == [
        "completed",
        "needs_attention",
    ]
    assert result.records == tuple(load_history(move_context[1]))
    assert Path(result.records[0]["vodforge_output_path"]).parent.is_dir()
    assert result.records[1]["vodforge_output_path"] == str(media)
    assert media.read_bytes() == b"second fixture"


def test_missing_companions_use_verified_copy_and_only_local_cleanup_rename(
    item, move_context, monkeypatch
):
    source = Path(item["vodforge_output_path"])
    source.unlink()
    (source.parent / "metadata.json").write_text(json.dumps({"id": item["id"]}))
    copied = []
    original_copy, original_rename = ops._copy_verified, Path.rename

    def record_copy(artifact, target, cancelled):
        copied.append((artifact.path, target))
        return original_copy(artifact, target, cancelled)

    def local_rename(path, target):
        target = Path(target)
        assert target.parent.parent == path.parent
        return original_rename(path, target)

    monkeypatch.setattr(ops, "_copy_verified", record_copy)
    monkeypatch.setattr(Path, "rename", local_rename)
    result = ops.move_files(planned(item, move_context), [item], *move_context)
    assert result.outcomes[0][1] == "completed"
    assert len(copied) == 1 and copied[0][0].parent != copied[0][1].parent


def test_source_appearing_after_publication_prevents_folder_cleanup(item, move_context):
    source = Path(item["vodforge_output_path"])
    source.unlink()

    def appear(boundary):
        if boundary == "history_saved":
            source.write_bytes(b"new unrelated media")

    result = ops.move_files(
        planned(item, move_context), [item], *move_context, boundary=appear
    )
    assert result.outcomes[0][1] == "cleanup_pending"
    assert source.read_bytes() == b"new unrelated media"
    with pytest.raises(ValueError, match="appeared"):
        ops.recover_move_cleanup(result.journal, result.records, move_context[1])
    assert source.exists()


def test_recovery_refuses_replaced_destination_structure(item, move_context):
    source = Path(item["vodforge_output_path"])
    source.unlink()

    def stop(boundary):
        if boundary == "history_saved":
            raise OSError("stop after durable publication")

    result = ops.move_files(
        planned(item, move_context), [item], *move_context, boundary=stop
    )
    target = Path(result.records[0]["vodforge_output_path"]).parent
    target.rename(target.with_name("retained-original"))
    target.mkdir()
    with pytest.raises(ValueError, match="identity changed"):
        ops.recover_move_cleanup(result.journal, result.records, move_context[1])
    assert source.parent.is_dir()


def test_qt_preview_discloses_missing_structure_and_commits_consistent_index(
    item, move_context
):
    from yt_downloader.qt_quick.library_files import QtLibraryFiles

    source = Path(item["vodforge_output_path"])
    source.unlink()
    owner = QtLibraryFiles(move_context[1])
    try:
        assert owner.begin(
            "move", [history_archive_owner(item)], [item], destination=move_context[0]
        )
        owner.worker.join(3)
        assert not owner.busy
        owner.poll()
        assert owner.phase == "preview" and owner.eligible
        assert "missing-media folder structure" in owner.status
        assert "remain missing" in owner.status
        assert owner.confirm([item])
        owner.worker.join(3)
        assert not owner.busy
        owner.poll()
        assert owner.latest_history == load_history(move_context[1])
        assert Path(owner.latest_history[0]["vodforge_output_path"]).parent.is_dir()
        assert not Path(owner.latest_history[0]["vodforge_output_path"]).exists()
    finally:
        owner.close()


def test_qt_missing_structure_confirmation_rejects_stale_index(
    item, move_context, monkeypatch
):
    from yt_downloader.qt_quick.library_files import QtLibraryFiles

    source = Path(item["vodforge_output_path"])
    source.unlink()
    owner = QtLibraryFiles(move_context[1])
    owner.action, owner.destination = "move", move_context[0]
    owner.phase, owner.plan = "preview", planned(item, move_context)
    monkeypatch.setattr(
        owner, "_start", lambda *_: pytest.fail("must not start stale commit")
    )
    changed = dict(item, title="new title")
    assert not owner.confirm([changed])
    assert owner.phase == "error"
    assert source.parent.is_dir()
