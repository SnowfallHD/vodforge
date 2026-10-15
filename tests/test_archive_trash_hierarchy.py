"""Disposable real Trash transfers; never inspect or clean ordinary user media."""

import json
from pathlib import Path

import pytest

from yt_downloader import archive_file_operations as ops
from yt_downloader.history import history_archive_owner


def fixture(tmp_path, *, root_kind="retry"):
    root = tmp_path / "Library"
    folder = root / "Channel" / "Playlists" / "Playlist" / "Video"
    folder.mkdir(parents=True)
    media = folder / "video.mp4"
    media.write_bytes(b"fixture media")
    (folder / "metadata.json").write_text(json.dumps({"id": "fixture"}))
    (folder / "thumbnail.jpg").write_bytes(b"fixture thumbnail")
    record = {
        "id": "fixture",
        "channel": "Channel",
        "vodforge_run_id": "fixture-run",
        "vodforge_output_type": "MP4",
        "vodforge_output_path": str(media),
        "vodforge_output_dir": str(folder),
    }
    if root_kind == "retry":
        record["vodforge_retry_job"] = {"output_dir": str(root)}
    elif root_kind == "archive":
        record["vodforge_archive_root"] = str(root)
    return root, folder, record


def execute(tmp_path, record, *, boundary=lambda _: None, trash=None, peers=()):
    history = tmp_path / "profile" / "download-history.json"
    history.parent.mkdir()
    records = [record, *peers]
    ops._save_durable_history(history, records)
    proposal = ops.plan_file_operation(records, [history_archive_owner(record)])
    rubbish = tmp_path / "Trash"
    rubbish.mkdir()

    def move_to_trash(path):
        destination = rubbish / path.name
        path.rename(destination)
        return str(destination)

    result = ops.delete_files(
        proposal,
        records,
        history,
        history.parent / "file-operations",
        trash=trash or move_to_trash,
        boundary=boundary,
    )
    return result, rubbish


@pytest.mark.parametrize("root_kind", ["retry", "archive"])
def test_trash_sole_video_prunes_owned_hierarchy_but_keeps_root(tmp_path, root_kind):
    root, folder, record = fixture(tmp_path, root_kind=root_kind)
    result, rubbish = execute(tmp_path, record)
    assert result.outcomes == ((history_archive_owner(record), "completed"),)
    assert result.records == ()
    assert root.is_dir() and list(root.iterdir()) == []
    assert not folder.exists()
    assert (rubbish / "video.mp4").read_bytes() == b"fixture media"
    assert (rubbish / "thumbnail.jpg").read_bytes() == b"fixture thumbnail"
    assert json.loads((rubbish / "metadata.json").read_text()) == {"id": "fixture"}
    assert json.loads(result.journal.read_text())["state"] == "completed"


@pytest.mark.parametrize("location", ["Video", "Playlist", "Playlists", "Channel"])
def test_trash_stops_at_unknown_nonempty_parent(tmp_path, location):
    root, folder, record = fixture(tmp_path)
    parent = next(path for path in (folder, *folder.parents) if path.name == location)
    unrelated = parent / "personal.txt"
    unrelated.write_bytes(b"preserved unknown content")
    result, _ = execute(tmp_path, record)
    assert result.outcomes[0][1] == "completed"
    assert unrelated.read_bytes() == b"preserved unknown content"
    assert parent.is_dir() and root.is_dir()
    if parent != folder:
        assert not folder.exists()


def test_trash_legacy_sibling_keeps_playlist_and_other_video(tmp_path):
    root, folder, record = fixture(tmp_path)
    sibling = folder.parent / "Older video"
    sibling.mkdir()
    (sibling / "video.mp4").write_bytes(b"retained older media")
    result, _ = execute(tmp_path, record)
    assert result.outcomes[0][1] == "completed"
    assert not folder.exists()
    assert (sibling / "video.mp4").read_bytes() == b"retained older media"
    assert sibling.parent.is_dir() and root.is_dir()


@pytest.mark.parametrize("root_kind", ["unknown", "outside", "traversal", "import"])
def test_trash_uncertain_hierarchy_never_prunes(tmp_path, root_kind):
    root, folder, record = fixture(tmp_path, root_kind="unknown")
    if root_kind == "outside":
        record["vodforge_archive_root"] = str(tmp_path / "Different library")
    elif root_kind == "traversal":
        record["vodforge_retry_job"] = {"output_dir": str(root / "..")}
    elif root_kind == "import":
        record["vodforge_archive_root"] = str(root)
        record["id"] = "local-fixture"
        record["vodforge_run_id"] = "import-fixture"
        (folder / "metadata.json").write_text(json.dumps({"id": record["id"]}))
    result, _ = execute(tmp_path, record)
    assert result.outcomes[0][1] == "completed"
    assert folder.is_dir() and list(folder.iterdir()) == []
    assert root.is_dir()


@pytest.mark.parametrize(
    "mutation",
    ["root_redirect", "parent_redirect", "parent_replaced", "permission_error"],
)
def test_trash_cleanup_stops_on_changed_or_unreadable_ancestors(
    tmp_path, monkeypatch, mutation
):
    root, folder, record = fixture(tmp_path)
    original_write = ops.OperationJournal.write
    changed = False
    retained = tmp_path / "retained"

    def write(journal):
        nonlocal changed
        original_write(journal)
        if journal.document["state"] != "completed" or changed:
            return
        changed = True
        if mutation == "permission_error":
            original_rmdir = Path.rmdir

            def deny(path):
                if path == folder:
                    raise PermissionError("fixture denial")
                return original_rmdir(path)

            monkeypatch.setattr(Path, "rmdir", deny)
        else:
            target = root if mutation == "root_redirect" else folder.parent
            target.rename(retained)
            if mutation == "parent_replaced":
                target.mkdir()
                # A new empty child cannot acquire the retired directory's proof.
                (target / "Video").mkdir()
            else:
                try:
                    target.symlink_to(retained, target_is_directory=True)
                except OSError:
                    pytest.skip("fixture symlinks unavailable")

    monkeypatch.setattr(ops.OperationJournal, "write", write)
    result, _ = execute(tmp_path, record)
    assert result.outcomes[0][1] == "completed"
    assert folder.is_dir()  # Neither redirected target nor replacement was removed.
    assert list(folder.iterdir()) == []
    assert root.is_dir()


@pytest.mark.parametrize("failure", ["trash", "history", "receipt"])
def test_trash_partial_or_uncommitted_operation_keeps_owned_directories(
    tmp_path, monkeypatch, failure
):
    root, folder, record = fixture(tmp_path)
    if failure == "history":

        def fail_history(*_):
            raise OSError("fixture durable save failure")

        # Seed first; fail only operation's actual durable publication.
        original = ops._save_durable_history
        calls = 0

        def save(*args):
            nonlocal calls
            calls += 1
            if calls > 1:
                fail_history()
            return original(*args)

        monkeypatch.setattr(ops, "_save_durable_history", save)
    elif failure == "receipt":
        original = ops.OperationJournal.write

        def write(journal):
            if journal.document["state"] == "completed":
                raise OSError("fixture final receipt failure")
            return original(journal)

        monkeypatch.setattr(ops.OperationJournal, "write", write)

    def fail_trash(_):
        raise OSError("fixture Trash failure")

    if failure == "receipt":
        with pytest.raises(ops.FileOperationUncertain):
            execute(tmp_path, record)
    else:
        result, _ = execute(
            tmp_path, record, trash=fail_trash if failure == "trash" else None
        )
        assert result.outcomes[0][1] != "completed"
    assert folder.is_dir() and root.is_dir()


@pytest.mark.parametrize(
    "name", ["orphan.mp4", "orphan.flac", "metadata.json", "thumbnail.jpg"]
)
@pytest.mark.parametrize("other_playlist", [False, True])
def test_any_other_channel_artifact_retains_all_higher_folders(
    tmp_path, name, other_playlist
):
    root, folder, record = fixture(tmp_path)
    sibling = (
        (folder.parent.parent / "Other playlist" / "Other video")
        if other_playlist
        else (folder.parent / "Other video")
    )
    sibling.mkdir(parents=True)
    artifact = sibling / name
    artifact.write_bytes(b"preserved other artifact")
    result, _ = execute(tmp_path, record)
    assert result.outcomes[0][1] == "completed"
    assert not folder.exists()
    assert folder.parent.is_dir()  # Even the now-empty selected playlist remains.
    assert folder.parent.parent.is_dir() and folder.parent.parent.parent.is_dir()
    assert root.is_dir() and artifact.read_bytes() == b"preserved other artifact"


def test_known_empty_sibling_branches_do_not_count_as_other_artifacts(tmp_path):
    root, folder, record = fixture(tmp_path)
    sibling = folder.parent.parent / "Other playlist" / "Older video"
    sibling.mkdir(parents=True)
    peer = dict(
        record,
        id="older",
        vodforge_run_id="older-run",
        vodforge_output_path=str(sibling / "video.mp4"),
        vodforge_output_dir=str(sibling),
    )
    result, _ = execute(tmp_path, record, peers=[peer])
    assert result.outcomes[0][1] == "completed"
    assert root.is_dir() and list(root.iterdir()) == []
    assert not sibling.exists() and not folder.exists()
    assert result.records == (peer,)  # Missing peer history remains recoverable.


def test_unknown_empty_sibling_branch_is_preserved(tmp_path):
    root, folder, record = fixture(tmp_path)
    unknown = folder.parent.parent / "Unindexed personal folder"
    unknown.mkdir()
    result, _ = execute(tmp_path, record)
    assert result.outcomes[0][1] == "completed"
    assert not folder.exists()
    assert unknown.is_dir() and root.is_dir()


def canonical_legacy_fixture(tmp_path, *, playlist=True, root_record=False):
    from yt_downloader.download_service import video_output_dir

    root = tmp_path / "Library"
    record = {
        "id": "fixture",
        "title": "Selected video",
        "channel": "Channel",
        "vodforge_run_id": "legacy-fixture-run",
        "vodforge_output_type": "MP4",
    }
    if playlist:
        record.update(playlist_id="playlist", playlist_title="Playlist")
    folder = video_output_dir(root, record)
    folder.mkdir(parents=True)
    media = folder / "video.mp4"
    media.write_bytes(b"fixture media")
    (folder / "metadata.json").write_text(json.dumps({"id": "fixture"}))
    (folder / "thumbnail.jpg").write_bytes(b"fixture thumbnail")
    record.update(vodforge_output_path=str(media), vodforge_output_dir=str(folder))
    if root_record:
        record["vodforge_retry_job"] = {"output_dir": str(root)}
    return root, folder, record


@pytest.mark.parametrize("playlist", [False, True])
def test_legacy_durable_canonical_path_prunes_to_retained_root(tmp_path, playlist):
    root, folder, record = canonical_legacy_fixture(tmp_path, playlist=playlist)
    result, _ = execute(tmp_path, record)
    assert result.outcomes[0][1] == "completed"
    assert root.is_dir() and list(root.iterdir()) == []
    assert not folder.exists()


@pytest.mark.parametrize("remaining", ["metadata.json", "thumbnail.jpg", "none"])
@pytest.mark.parametrize("root_record", [False, True])
def test_partial_missing_selected_media_cleans_verified_empty_hierarchy(
    tmp_path, remaining, root_record
):
    root, folder, record = canonical_legacy_fixture(tmp_path, root_record=root_record)
    for child in folder.iterdir():
        if child.name != remaining:
            child.unlink()
    result, _ = execute(tmp_path, record)
    assert result.outcomes[0][1] == "entry_removed"
    if remaining == "thumbnail.jpg":
        # A generic thumbnail without its ownership metadata is not ours to trash.
        assert (folder / remaining).read_bytes() == b"fixture thumbnail"
        assert root.is_dir()
    else:
        assert root.is_dir() and list(root.iterdir()) == []


def test_unindexed_empty_canonical_video_branches_are_cleaned(tmp_path):
    from yt_downloader.download_service import video_output_dir

    root, _folder, record = canonical_legacy_fixture(tmp_path, root_record=True)
    peer = dict(record, id="older", title="Older video", playlist_title="Other list")
    video_output_dir(root, peer).mkdir(parents=True)
    result, _ = execute(tmp_path, record)
    assert result.outcomes[0][1] == "completed"
    assert root.is_dir() and list(root.iterdir()) == []


@pytest.mark.parametrize("root_record", [False, True])
@pytest.mark.parametrize(
    "bucket", ["playlists", "videos - no playlist", "path-safe videos"]
)
def test_empty_reserved_channel_bucket_does_not_strand_sole_video_channel(
    tmp_path, root_record, bucket
):
    root, folder, record = canonical_legacy_fixture(
        tmp_path, root_record=root_record, playlist=bucket != "playlists"
    )
    channel = folder.parents[2] if record.get("playlist_id") else folder.parents[1]
    empty_bucket = channel / bucket
    empty_bucket.mkdir()
    result, _ = execute(tmp_path, record)
    assert result.outcomes[0][1] == "completed"
    assert root.is_dir() and list(root.iterdir()) == []


@pytest.mark.parametrize("remaining", ["other.mp4", "metadata.json", "thumbnail.jpg"])
def test_legacy_partial_other_video_preserves_shared_channel(tmp_path, remaining):
    from yt_downloader.download_service import video_output_dir

    root, folder, record = canonical_legacy_fixture(tmp_path)
    peer = dict(record, id="other", title="Other video", playlist_title="Other list")
    other = video_output_dir(root, peer)
    other.mkdir(parents=True)
    (other / remaining).write_bytes(b"must remain")
    result, _ = execute(tmp_path, record)
    assert result.outcomes[0][1] == "completed"
    assert not folder.exists() and folder.parent.is_dir()
    assert (other / remaining).read_bytes() == b"must remain"


def test_legacy_root_reconstruction_requires_exact_durable_metadata(tmp_path):
    root, folder, record = canonical_legacy_fixture(tmp_path)
    record["channel"] = "Different channel"
    result, _ = execute(tmp_path, record)
    assert result.outcomes[0][1] == "completed"
    assert folder.is_dir() and list(folder.iterdir()) == []
    assert root.is_dir()


def test_unreadable_channel_scan_only_prunes_selected_empty_leaf(tmp_path, monkeypatch):
    root, folder, record = fixture(tmp_path)
    original = ops.os.scandir

    def scan(path):
        if Path(path) == root / "Channel":
            raise PermissionError("fixture channel scan refusal")
        return original(path)

    monkeypatch.setattr(ops.os, "scandir", scan)
    result, _ = execute(tmp_path, record)
    assert result.outcomes[0][1] == "completed"
    assert not folder.exists() and folder.parent.is_dir() and root.is_dir()


def test_channel_metadata_mismatch_retains_higher_hierarchy(tmp_path):
    root, folder, record = fixture(tmp_path)
    record["channel"] = "Different channel"
    result, _ = execute(tmp_path, record)
    assert result.outcomes[0][1] == "completed"
    assert not folder.exists() and folder.parent.is_dir() and root.is_dir()


@pytest.mark.parametrize(
    "root,source,expected",
    [
        (
            r"C:\Media",
            r"c:\media\CHANNEL\playlists\P\Video\video.mp4",
            r"C:\Media\Channel",
        ),
        (
            r"D:\Media",
            r"D:\Media\Channel\videos - no playlist\Video\video.mp4",
            r"D:\Media\Channel",
        ),
        (
            r"\\server\share\Media",
            r"\\SERVER\SHARE\media\Channel\playlists\P\Video\video.mp4",
            r"\\server\share\Media\Channel",
        ),
        (r"C:\Media", r"E:\Media\Channel\Video\video.mp4", None),
        (r"C:\Media", r"C:\Media-other\Channel\Video\video.mp4", None),
        (r"C:\Media", r"C:\Media\Channelish\Video\video.mp4", None),
        (r"C:\Media\..", r"C:\Media\Channel\Video\video.mp4", None),
    ],
)
def test_windows_channel_boundary_preserves_case_and_containment(
    tmp_path, monkeypatch, root, source, expected
):
    from pathlib import PureWindowsPath
    from types import SimpleNamespace

    monkeypatch.setattr(ops, "Path", PureWindowsPath)
    monkeypatch.setattr(ops, "os", SimpleNamespace(name="nt"))
    record = {"channel": "Channel", "vodforge_archive_root": root}
    result = ops._trash_channel_root(record, PureWindowsPath(source))
    assert result == (PureWindowsPath(expected) if expected else None)
