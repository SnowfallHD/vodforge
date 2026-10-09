"""Legacy multiselect moves keep hierarchy without adopting destination parents."""

import json
from pathlib import Path

from yt_downloader.history import history_archive_owner, load_history
from yt_downloader.qt_quick.library_files import QtLibraryFiles


def test_legacy_multiselect_repeated_moves_preserve_scope(tmp_path):
    source = tmp_path / "source"
    rows = []
    for i, relative in enumerate(
        ("One", "Two", "Channel/playlists/List/Three", "Channel/playlists/List/Four")
    ):
        folder = source / relative
        folder.mkdir(parents=True)
        (folder / "video.mp4").write_bytes(f"media-{i}".encode())
        (folder / "metadata.json").write_text(json.dumps({"id": str(i)}))
        (folder / "personal.txt").write_text("leave here")
        rows.append(
            {
                "id": str(i),
                "vodforge_output_type": "MP4",
                "vodforge_output_dir": str(folder),
                "vodforge_output_path": str(folder / "video.mp4"),
                "vodforge_retry_job": {"output_dir": str(source)},
            }
        )
    history = tmp_path / "download-history.json"
    history.write_text(json.dumps({"schema_version": 1, "items": rows}))
    assert load_history(history) == load_history(history)
    previous = source
    for destination in (
        tmp_path / "first",
        tmp_path / "personal/projects/nested",
        tmp_path / "final",
    ):
        destination.mkdir(parents=True)
        (destination / "keep.txt").write_text("destination file")
        records = load_history(history)
        controller = QtLibraryFiles(history)
        assert controller.begin(
            "move",
            [history_archive_owner(r) for r in records],
            records,
            destination=destination,
        )
        controller.worker.join(5)
        controller.poll()
        assert controller.eligible
        assert controller.confirm(records)
        controller.worker.join(5)
        controller.poll()
        assert controller.phase == "done", controller.status
        updated = load_history(history)
        for old, row in zip(rows, updated):
            relative = Path(old["vodforge_output_path"]).relative_to(source)
            target = destination / relative
            assert Path(row["vodforge_output_path"]) == target
            assert target.read_bytes() == f"media-{row['id']}".encode()
            assert (
                json.loads((target.parent / "metadata.json").read_text())["id"]
                == row["id"]
            )
            assert not (previous / relative).exists()
            assert row["vodforge_archive_root"] == str(destination)
            assert (
                Path(old["vodforge_output_dir"]) / "personal.txt"
            ).read_text() == "leave here"
        assert not (destination / "personal").exists()
        assert (destination / "keep.txt").read_text() == "destination file"
        previous = destination
    assert (
        tmp_path / "personal/projects/nested/keep.txt"
    ).read_text() == "destination file"
