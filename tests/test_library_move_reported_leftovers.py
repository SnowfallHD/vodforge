"""Disposable reproduction of the reported move, without touching personal data."""

from tests.test_archive_file_operations import item, move, move_context
from yt_downloader import archive_file_operations as ops
from yt_downloader.history import history_archive_owner

__all__ = ["item", "move_context"]


def test_move_retires_media_but_retains_finder_metadata_ancestor(item, move_context):
    folder = ops.Path(item["vodforge_output_dir"])
    (folder / ".DS_Store").write_bytes(b"finder fixture")
    result = move(item, move_context)
    destination = move_context[0] / folder.name / "video.mp4"
    assert result.outcomes == ((history_archive_owner(item), "completed"),)
    assert destination.read_bytes() == b"fixture media"
    assert not ops.Path(item["vodforge_output_path"]).exists()
    assert sorted(p.name for p in folder.iterdir()) == [".DS_Store"]


def test_current_move_skips_missing_media_even_when_directory_remains(
    item, move_context
):
    source = ops.Path(item["vodforge_output_path"])
    source.unlink()
    plan = ops.plan_move_operation(
        [item], [history_archive_owner(item)], move_context[0]
    )
    assert plan.counts == {"missing": 1}
    result = ops.move_files(plan, [item], *move_context)
    assert result.records[0]["vodforge_output_path"] == str(source)
    assert source.parent.is_dir()
    assert not (move_context[0] / source.parent.name).exists()
