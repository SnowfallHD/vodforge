from pathlib import Path

from yt_downloader import archive_file_operations as ops
from yt_downloader.history import history_archive_owner


def fixture(root, relative, identity):
    folder = root / relative
    folder.mkdir(parents=True)
    media = folder / "video.mp4"
    media.write_bytes(identity.encode())
    return {
        "id": identity,
        "vodforge_output_type": "MP4",
        "vodforge_output_path": str(media),
        "vodforge_output_dir": str(folder),
        "vodforge_retry_job": {"output_dir": str(root)},
    }


def execute(tmp_path, records):
    destination = tmp_path / "new"
    destination.mkdir()
    history = tmp_path / "history.json"
    ops._save_durable_history(history, records)
    plan = ops.plan_move_operation(
        records, [history_archive_owner(r) for r in records], destination
    )
    result = ops.move_files(
        plan, records, destination, history, tmp_path / "file-operations"
    )
    return destination, result


def test_multiple_playlist_and_nonplaylist_hierarchy_and_empty_pruning(tmp_path):
    root = tmp_path / "old"
    records = [
        fixture(root, "channel/playlist/video-a", "a"),
        fixture(root, "channel/playlist/video-b", "b"),
        fixture(root, "channel/videos-noplaylist/video-c", "c"),
    ]
    destination, result = execute(tmp_path, records)
    assert all(state == "completed" for _, state in result.outcomes)
    for old, updated in zip(records, result.records, strict=True):
        relative = Path(old["vodforge_output_path"]).relative_to(root)
        assert Path(updated["vodforge_output_path"]) == destination / relative
        assert (destination / relative).read_bytes() == old["id"].encode()
    assert root.is_dir()
    assert not (root / "channel").exists()


def test_unrelated_sibling_prevents_parent_pruning(tmp_path):
    root = tmp_path / "old"
    record = fixture(root, "channel/playlist/video", "a")
    sibling = root / "channel/playlist/personal.txt"
    sibling.write_bytes(b"private fixture")
    _, result = execute(tmp_path, [record])
    assert result.outcomes[0][1] == "completed"
    assert sibling.read_bytes() == b"private fixture"
    assert not (root / "channel/playlist/video").exists()


def test_missing_root_is_explicitly_blocked(tmp_path):
    record = fixture(tmp_path / "old", "channel/video", "a")
    record.pop("vodforge_retry_job")
    destination = tmp_path / "new"
    destination.mkdir()
    plan = ops.plan_move_operation(
        [record], [history_archive_owner(record)], destination
    )
    assert plan.items[0].state == "unavailable"
    assert plan.items[0].reason == "hierarchy_root_unknown"


def test_existing_nested_destination_never_overwritten(tmp_path):
    record = fixture(tmp_path / "old", "channel/playlist/video", "a")
    destination = tmp_path / "new"
    target = destination / "channel/playlist/video"
    target.mkdir(parents=True)
    plan = ops.plan_move_operation(
        [record], [history_archive_owner(record)], destination
    )
    assert plan.counts == {"conflict": 1}


def test_repeated_move_after_restart_preserves_retry_configuration(tmp_path):
    from yt_downloader.history import load_history

    root = tmp_path / "old"
    record = fixture(root, "channel/playlist/video", "a")
    record["vodforge_retry_job"].update(
        {
            "use_nvenc": False,
            "manual_settings": {"video_crf": 20},
            "write_info_json": True,
        }
    )
    execute(tmp_path, [record])
    history = tmp_path / "history.json"
    restarted = load_history(history)
    assert restarted[0]["vodforge_archive_root"] == str(tmp_path / "new")
    assert restarted[0]["vodforge_retry_job"] == {
        **record["vodforge_retry_job"],
        "output_dir": str(tmp_path / "new"),
    }
    destination = tmp_path / "third"
    destination.mkdir()
    proposal = ops.plan_move_operation(
        restarted, [history_archive_owner(restarted[0])], destination
    )
    assert proposal.counts == {"ready": 1}
    second = ops.move_files(
        proposal, restarted, destination, history, tmp_path / "file-operations"
    )
    assert second.outcomes[0][1] == "completed"
    assert (destination / "channel/playlist/video/video.mp4").read_bytes() == b"a"
    assert not (tmp_path / "new/channel").exists()
    assert load_history(history)[0]["vodforge_archive_root"] == str(destination)
    assert second.records[0]["vodforge_retry_job"] == {
        **record["vodforge_retry_job"],
        "output_dir": str(destination),
    }
    assert record["vodforge_retry_job"]["output_dir"] == str(root)


def test_recovery_prunes_only_new_proven_root_after_verified_cleanup(tmp_path):
    root = tmp_path / "old"
    record = fixture(root, "channel/playlist/video", "a")
    destination = tmp_path / "new"
    destination.mkdir()
    history = tmp_path / "history.json"
    ops._save_durable_history(history, [record])
    proposal = ops.plan_move_operation(
        [record], [history_archive_owner(record)], destination
    )

    def interrupt(stage):
        if stage == "history_saved":
            raise OSError("fixture interrupted")

    result = ops.move_files(
        proposal,
        [record],
        destination,
        history,
        tmp_path / "file-operations",
        boundary=interrupt,
    )
    assert result.outcomes[0][1] == "cleanup_pending"
    recovered = ops.recover_move_cleanup(result.journal, result.records, history)
    assert recovered.outcomes[0][1] == "completed"
    assert not (root / "channel").exists()
    assert (destination / "channel/playlist/video/video.mp4").read_bytes() == b"a"


def test_failed_move_keeps_original_retry_root_and_options(tmp_path):
    from copy import deepcopy

    from yt_downloader.history import load_history

    root = tmp_path / "old"
    record = fixture(root, "channel/video", "a")
    record["vodforge_retry_job"].update(
        {
            "use_nvenc": False,
            "manual_settings": {"video_crf": 20},
            "write_info_json": True,
        }
    )
    original = deepcopy(record)
    destination = tmp_path / "new"
    destination.mkdir()
    history = tmp_path / "history.json"
    ops._save_durable_history(history, [record])
    proposal = ops.plan_move_operation(
        [record], [history_archive_owner(record)], destination
    )

    def interrupt(stage):
        if stage == "before_history":
            raise OSError("fixture publication prevented")

    result = ops.move_files(
        proposal,
        [record],
        destination,
        history,
        tmp_path / "file-operations",
        boundary=interrupt,
    )
    assert result.outcomes[0][1] == "needs_attention"
    assert result.records[0]["vodforge_retry_job"] == original["vodforge_retry_job"]
    assert (
        load_history(history)[0]["vodforge_retry_job"] == original["vodforge_retry_job"]
    )
    assert record == original
    assert Path(record["vodforge_output_path"]).read_bytes() == b"a"
