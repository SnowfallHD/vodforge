"""Private second-pass desired regression postconditions from independent audit."""

from dataclasses import replace

import pytest

from tests.test_run_identity import make_job
from yt_downloader.history import upsert_history
from yt_downloader.library_annotations import LibraryAnnotation
from yt_downloader.library_state import LibraryProjectionOwner
from yt_downloader.qt_quick.runtime import DownloadRuntime


def test_recovery_success_orphans_inherited_annotations(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    runtime = DownloadRuntime()
    job = replace(
        make_job(tmp_path / "out"),
        run_id="replacement",
        annotation_source_owner="run:original",
    )
    info = {
        "id": "abc123",
        "title": "Saved video",
        "vodforge_output_type": "MP4",
        "vodforge_output_path": str(job.output_dir / "video.mp4"),
    }
    old = {**info, "vodforge_run_id": "original"}
    runtime.history = upsert_history([], old, job.output_dir)
    runtime._history_store.publish(runtime.history)
    job.preview_info = dict(info)
    runtime.active_job = job
    notes = {
        "run:original": LibraryAnnotation(note="Keep this note", category="Research")
    }

    def projection(active):
        return LibraryProjectionOwner().reconcile(
            history_items=runtime.history,
            active_job=active,
            queued_jobs=[],
            terminal_jobs=[],
            annotations=notes,
        )

    before = projection(job)
    assert any(r.get("vodforge_user_note") == "Keep this note" for r in before.rows)
    runtime._record_history(
        {"job": job, "info": info, "output_dir": str(job.output_dir)}
    )
    after = projection(None)
    assert len(after.rows) == 1
    assert after.rows[0]["vodforge_annotation_owner"] == "run:original"
    assert after.rows[0]["vodforge_user_note"] == "Keep this note"
    cold = DownloadRuntime()
    assert (
        LibraryProjectionOwner()
        .reconcile(
            history_items=cold.history,
            active_job=None,
            queued_jobs=[],
            terminal_jobs=[],
            annotations=notes,
        )
        .rows[0]["vodforge_user_note"]
        == "Keep this note"
    )
    assert notes["run:original"].note == "Keep this note"


@pytest.mark.parametrize("shared", [True, False])
def test_card_removal_retains_shared_annotation_and_cleans_unreferenced_owner(
    tmp_path, monkeypatch, shared
):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from yt_downloader.archive_relink import record_fingerprint
    from yt_downloader.history import (
        history_annotation_owner,
        history_archive_owner,
        load_history,
        save_history,
    )
    from yt_downloader.library_annotations import LibraryAnnotationsOwner
    from yt_downloader.qt_quick.main import Bridge

    monkeypatch.setenv("HOME", str(tmp_path))
    rows = []
    for index in (1, 2):
        rows = upsert_history(
            rows,
            {
                "id": f"item{index}",
                "title": f"Item {index}",
                "vodforge_run_id": "one-playlist-run" if shared else f"run-{index}",
                "vodforge_output_type": "MP4",
                "vodforge_output_path": str(tmp_path / f"item{index}.mp4"),
            },
            tmp_path,
        )
    path = tmp_path / "history.json"
    save_history(path, rows)
    annotations = LibraryAnnotationsOwner(tmp_path / "annotations.json")
    annotation_owner = history_annotation_owner(rows[0])
    assert (annotation_owner == history_annotation_owner(rows[1])) is shared
    annotations.replace(
        annotation_owner,
        LibraryAnnotation(note="User-authored note", category="Research"),
    )
    item = rows[0]
    bridge = SimpleNamespace(
        _relink=SimpleNamespace(active=False),
        _pending_library_removal=(
            history_archive_owner(item),
            record_fingerprint(item),
        ),
        _file_action_busy=False,
        _files=SimpleNamespace(pending=False),
        _saved_item_for_owner=lambda _: item,
        _runtime=SimpleNamespace(
            history=rows, history_path=path, active_job=None, queued=[]
        ),
        _annotations=annotations,
        _library_category="All",
        libraryCategories=["All"],
        statusChanged=Mock(),
        historyChanged=Mock(),
        libraryCategoryChanged=Mock(),
        _record_update_feature=Mock(),
    )
    assert Bridge.confirmLibraryRemoval(bridge)
    retained = load_history(path)
    assert len(retained) == 1
    assert (history_annotation_owner(retained[0]) == annotation_owner) is shared
    assert (annotation_owner in annotations.snapshot) is shared
    reopened = LibraryAnnotationsOwner(annotations.path)
    reopened.load()
    assert (annotation_owner in reopened.snapshot) is shared
    if shared:
        assert reopened.snapshot[annotation_owner].note == "User-authored note"


def test_partial_annotation_write_destroys_previously_saved_notes(
    tmp_path, monkeypatch
):
    import errno
    from contextlib import contextmanager

    import pytest

    from yt_downloader import private_files
    from yt_downloader.library_annotations import (
        LibraryAnnotationsError,
        LibraryAnnotationsOwner,
    )

    path = tmp_path / "annotations.json"
    owner = LibraryAnnotationsOwner(path)
    owner.replace("first", LibraryAnnotation(note="Previously durable note"))
    before = path.read_bytes()
    original_open = private_files.open_private_binary_file

    @contextmanager
    def partial_write(target, **kwargs):
        with original_open(target, **kwargs) as stream:

            class Fault:
                def fileno(self):
                    return stream.fileno()

                def write(self, data):
                    stream.write(data[:12])
                    stream.flush()
                    raise OSError(errno.ENOSPC, "fixture disk full")

            yield Fault()

    with monkeypatch.context() as patch:
        patch.setattr(private_files, "open_private_binary_file", partial_write)
        with pytest.raises(LibraryAnnotationsError):
            owner.replace("second", LibraryAnnotation(note="New note"))
    assert path.read_bytes() == before
    assert owner.annotation_for("first").note == "Previously durable note"
    reopened = LibraryAnnotationsOwner(path)
    assert reopened.load()["first"].note == "Previously durable note"


def test_partial_journal_write_loses_previously_durable_queue(tmp_path, monkeypatch):
    import errno
    from contextlib import contextmanager

    import pytest

    from yt_downloader import private_files
    from yt_downloader.run_state import ActiveRunStore, RunStateError

    store = ActiveRunStore(tmp_path / "active-run.json")
    first = make_job(tmp_path / "out")
    queued = replace(first, run_id="previously-queued", output_dir=tmp_path / "other")
    store.begin(first, [queued])
    before = store.path.read_bytes()
    original_open = private_files.open_private_binary_file

    @contextmanager
    def partial_write(target, **kwargs):
        with original_open(target, **kwargs) as stream:

            class Fault:
                def fileno(self):
                    return stream.fileno()

                def write(self, data):
                    stream.write(data[:12])
                    stream.flush()
                    raise OSError(errno.ENOSPC, "fixture disk full")

            yield Fault()

    with monkeypatch.context() as patch:
        patch.setattr(private_files, "open_private_binary_file", partial_write)
        with pytest.raises(RunStateError):
            store.replace_queue([queued, replace(queued, run_id="new-queued")])
    assert store.path.read_bytes() == before
    assert [j.run_id for j in ActiveRunStore(store.path).load_queued_jobs()] == [
        "previously-queued"
    ]


def test_new_explicit_annotation_wins_over_inherited_lineage(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    runtime = DownloadRuntime()
    job = replace(
        make_job(tmp_path / "out"),
        run_id="replacement",
        annotation_source_owner="run:original",
    )
    notes = {
        "run:original": LibraryAnnotation(note="Shared original"),
        "run:replacement": LibraryAnnotation(note="Explicit replacement"),
    }
    runtime.annotation_snapshot = lambda: notes
    runtime.active_job = job
    info = {
        "id": "fixture",
        "title": "Saved video",
        "vodforge_output_type": "MP4",
        "vodforge_output_path": str(job.output_dir / "video.mp4"),
    }
    runtime._record_history(
        {"job": job, "info": info, "output_dir": str(job.output_dir)}
    )
    rows = (
        LibraryProjectionOwner()
        .reconcile(
            history_items=runtime.history,
            active_job=None,
            queued_jobs=[],
            terminal_jobs=[],
            annotations=notes,
        )
        .rows
    )
    assert rows[0]["vodforge_annotation_owner"] == "run:replacement"
    assert rows[0]["vodforge_user_note"] == "Explicit replacement"
    assert notes["run:original"].note == "Shared original"


def test_reference_set_retains_saved_live_queued_and_recovery_owners(tmp_path):
    from yt_downloader.library_annotations import referenced_annotation_owners

    first = replace(make_job(tmp_path), annotation_source_owner="run:source")
    queued = replace(first, run_id="queued", annotation_source_owner="run:other")
    owners = referenced_annotation_owners(
        [{"vodforge_run_id": "saved"}], [first, queued, None]
    )
    assert owners == {
        "run:saved",
        f"run:{first.run_id}",
        "run:source",
        "run:queued",
        "run:other",
    }
