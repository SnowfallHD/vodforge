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
