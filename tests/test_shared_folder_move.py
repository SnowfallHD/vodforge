"""Move all distinct indexed exports together without overwriting other files."""

import json
from pathlib import Path

import pytest

from yt_downloader import archive_file_operations as ops
from yt_downloader.history import history_archive_owner

pytest_plugins = ["tests.test_archive_file_operations"]


def peers(item):
    first = Path(item["vodforge_output_path"])
    second = first.with_name("video (1).mp4")
    second.write_bytes(b"distinct second export")
    row = dict(
        item,
        vodforge_output_path=str(second),
        vodforge_recorded_at="2026-09-18T00:00:00+00:00",
    )
    (first.parent / "metadata.json").write_text(json.dumps({"id": item["id"]}))
    (first.parent / "thumbnail.jpg").write_bytes(b"owned thumbnail")
    return [item, row]


def execute(rows, context, **kwargs):
    ops._save_durable_history(context[1], rows)
    plan = ops.plan_move_operation(
        rows, [history_archive_owner(row) for row in rows], context[0]
    )
    return plan, ops.move_files(plan, rows, *context, **kwargs)


def test_all_distinct_shared_exports_move_and_companions_transfer_once(
    item, move_context
):
    rows = peers(item)
    originals = [Path(row["vodforge_output_path"]) for row in rows]
    expected = [p.read_bytes() for p in originals]
    plan, result = execute(rows, move_context)
    assert plan.counts == {"ready": 2}
    assert [len(i.artifacts) for i in plan.items] == [3, 1]
    assert [state for _, state in result.outcomes] == ["completed", "completed"]
    assert [
        Path(row["vodforge_output_path"]).read_bytes() for row in result.records
    ] == expected
    assert all(not p.exists() for p in originals)
    target = Path(result.records[0]["vodforge_output_dir"])
    assert {p.name for p in target.iterdir()} == {
        "video.mp4",
        "video (1).mp4",
        "metadata.json",
        "thumbnail.jpg",
    }
    assert ops.pending_file_operations(move_context[2]) == ()


@pytest.mark.parametrize(
    "hazard", ["subset", "same_path", "legacy", "alias_legacy", "metadata", "hardlink"]
)
def test_shared_source_requires_all_exclusively_owned_matching_peers(
    item, move_context, hazard
):
    rows = peers(item)
    owners = [history_archive_owner(row) for row in rows]
    if hazard == "subset":
        owners = owners[:1]
    elif hazard == "same_path":
        rows[1]["vodforge_output_path"] = rows[0]["vodforge_output_path"]
    elif hazard in {"legacy", "alias_legacy"}:
        rows.append(
            dict(rows[0], id="legacy", vodforge_recorded_at="2026-09-19T00:00:00+00:00")
        )
        rows[-1].pop("vodforge_output_path")
        if hazard == "alias_legacy":
            rows[-1]["vodforge_output_dir"] = str(
                Path(item["vodforge_output_dir"])
            ).upper()
    elif hazard == "metadata":
        (Path(item["vodforge_output_dir"]) / "metadata.json").write_text(
            json.dumps({"id": "someone-else"})
        )
    else:
        p = Path(rows[1]["vodforge_output_path"])
        p.unlink()
        p.hardlink_to(Path(rows[0]["vodforge_output_path"]))
    plan = ops.plan_move_operation(rows, owners, move_context[0])
    assert all(i.state != "ready" for i in plan.items)
    assert Path(item["vodforge_output_path"]).exists()


def test_empty_destination_is_reviewed_and_reused(item, move_context):
    target = move_context[0] / Path(item["vodforge_output_dir"]).name
    target.mkdir()
    inode = target.stat().st_ino
    plan, result = execute([item], move_context)
    assert plan.items[0].destination_existing
    assert result.outcomes[0][1] == "completed"
    assert target.stat().st_ino == inode
    assert (target / "video.mp4").read_bytes() == b"fixture media"


@pytest.mark.parametrize("hazard", ["foreign", "redirect", "changed_after_preview"])
def test_nonempty_or_redirected_destination_is_preserved(item, move_context, hazard):
    target = move_context[0] / Path(item["vodforge_output_dir"]).name
    if hazard == "redirect":
        target.symlink_to(Path(item["vodforge_output_dir"]), target_is_directory=True)
    else:
        target.mkdir()
    owners = [history_archive_owner(item)]
    plan = ops.plan_move_operation([item], owners, move_context[0])
    if hazard == "changed_after_preview":
        (target / "personal.txt").write_text("keep")
        with pytest.raises(ValueError, match="changed"):
            ops.move_files(plan, [item], *move_context)
    else:
        if hazard == "foreign":
            (target / "personal.txt").write_text("keep")
            plan = ops.plan_move_operation([item], owners, move_context[0])
        assert plan.counts == {"conflict": 1}
    assert Path(item["vodforge_output_path"]).read_bytes() == b"fixture media"


def test_already_target_is_a_noop_not_conflict(item, move_context):
    destination = Path(item["vodforge_retry_job"]["output_dir"])
    plan = ops.plan_move_operation([item], [history_archive_owner(item)], destination)
    assert plan.counts == {"already_in_target": 1}
    result = ops.move_files(plan, [item], destination, move_context[1], move_context[2])
    assert result.outcomes == ((history_archive_owner(item), "already_in_target"),)
    assert result.records == (item,)


def test_another_source_group_cannot_share_a_target_claim(item, move_context):
    rows = peers(item)
    other_root = Path(item["vodforge_retry_job"]["output_dir"]) / "other-root"
    other_folder = other_root / Path(item["vodforge_output_dir"]).name
    other_folder.mkdir(parents=True)
    media = other_folder / "other.mp4"
    media.write_bytes(b"unrelated source")
    rows.append(
        dict(
            item,
            id="other",
            vodforge_output_path=str(media),
            vodforge_output_dir=str(other_folder),
            vodforge_retry_job={"output_dir": str(other_root)},
        )
    )
    plan = ops.plan_move_operation(
        rows, [history_archive_owner(row) for row in rows], move_context[0]
    )
    assert plan.counts == {"conflict": 3}


def test_cancelled_shared_preflight_does_not_regain_file_authority(item, move_context):
    from threading import Event

    rows = peers(item)
    cancelled = Event()
    cancelled.set()
    plan = ops.plan_move_operation(
        rows,
        [history_archive_owner(row) for row in rows],
        move_context[0],
        cancelled=cancelled,
    )
    assert plan.counts == {"cancelled": 2}


def test_full_27_selection_preview_and_result_account_for_every_entry(
    item, move_context
):
    from yt_downloader.qt_quick.library_files import QtLibraryFiles

    rows = peers(item)
    root = Path(item["vodforge_retry_job"]["output_dir"])
    motivational = root / "Motivational"
    motivational.mkdir()
    (motivational / "clip.mp4").write_bytes(b"motivation")
    (move_context[0] / "Motivational").mkdir()
    rows.append(
        dict(
            item,
            id="motivation",
            vodforge_output_path=str(motivational / "clip.mp4"),
            vodforge_output_dir=str(motivational),
        )
    )
    for n in range(22):
        folder = root / f"Missing-{n}"
        rows.append(
            dict(
                item,
                id=f"missing-{n}",
                vodforge_output_path=str(folder / "clip.mp4"),
                vodforge_output_dir=str(folder),
            )
        )
    for n in range(2):
        folder = move_context[0] / f"Already-{n}"
        folder.mkdir()
        (folder / "clip.mp4").write_bytes(b"already")
        rows.append(
            dict(
                item,
                id=f"already-{n}",
                vodforge_output_path=str(folder / "clip.mp4"),
                vodforge_output_dir=str(folder),
                vodforge_retry_job={"output_dir": str(move_context[0])},
            )
        )
    ops._save_durable_history(move_context[1], rows)
    owner = QtLibraryFiles(move_context[1])
    try:
        assert owner.begin(
            "move",
            [history_archive_owner(row) for row in rows],
            rows,
            destination=move_context[0],
        )
        owner.worker.join(30)
        assert not owner.worker.is_alive(), "Library worker did not finish"
        owner.poll()
        assert "27 selected:" in owner.status
        assert "3 media ready to move" in owner.status
        assert "22 missing-media folder structures ready to move" in owner.status
        assert "2 already in destination" in owner.status
        assert owner.confirm(rows)
        owner.worker.join(30)
        assert not owner.worker.is_alive(), "Library worker did not finish"
        owner.poll()
        assert owner.phase == "done"
        assert "27 selected:" in owner.status
        assert "3 media moved" in owner.status
        assert "22 missing-media folder structures moved" in owner.status
        assert "2 already in destination" in owner.status
        assert "remain missing" in owner.status
        assert len(owner.latest_history) == 27
    finally:
        owner.close()


def test_all_noop_preview_explains_already_target_without_find_file_advice(
    item, move_context
):
    from yt_downloader.qt_quick.library_files import QtLibraryFiles

    owner = QtLibraryFiles(move_context[1])
    try:
        assert owner.begin(
            "move",
            [history_archive_owner(item)],
            [item],
            destination=Path(item["vodforge_retry_job"]["output_dir"]),
        )
        owner.worker.join(3)
        owner.poll()
        assert not owner.eligible
        assert "1 already in destination" in owner.status
        assert "Find the saved file" not in owner.status
    finally:
        owner.close()


@pytest.mark.parametrize("interrupted", [False, True])
def test_legacy_preview_and_terminal_report_all_selection_outcomes(
    item, move_context, monkeypatch, interrupted
):
    from threading import Event
    from types import SimpleNamespace
    from unittest.mock import Mock

    from tests.test_library_file_actions import dialog
    from yt_downloader import library_file_actions_ui as ui
    from yt_downloader.archive_work import ArchiveWorkResult

    rows = peers(item)
    already = move_context[0] / "Already"
    already.mkdir()
    (already / "clip.mp4").write_bytes(b"already")
    rows.append(
        dict(
            item,
            id="already",
            vodforge_output_path=str(already / "clip.mp4"),
            vodforge_output_dir=str(already),
            vodforge_retry_job={"output_dir": str(move_context[0])},
        )
    )
    ops._save_durable_history(move_context[1], rows)
    popup = dialog()
    popup.offer = Mock()
    host = SimpleNamespace(
        download_history=rows,
        history_path=move_context[1],
        _archive_worker=SimpleNamespace(busy=False),
        _archive_observe=Mock(),
        _archive_flush_history=Mock(),
        _reconcile_library_projection=Mock(),
        _show_file_recovery=Mock(),
    )
    callbacks = []
    host._archive_submit = lambda kind, work, done, **_kwargs: (
        callbacks.append((work, done)) or True
    )
    monkeypatch.setattr(
        ui.filedialog, "askdirectory", lambda **_kwargs: str(move_context[0])
    )
    monkeypatch.setattr(ui, "FileActionDialog", lambda *_args: popup)
    ui.LibraryFileActionsMixin._begin_library_file_action(
        host, "move", tuple(history_archive_owner(row) for row in rows)
    )
    work, done = callbacks.pop()
    plan = work(Event())
    done(ArchiveWorkResult(1, "file_plan", value=plan))
    preview = popup.note.set.call_args.args[0]
    assert (
        "3 selected:" in preview
        and "2 media ready to move" in preview
        and "1 already in destination" in preview
    )
    hit = False

    def fail(name):
        nonlocal hit
        if interrupted and name == "history_saved" and not hit:
            hit = True
            raise OSError("synthetic interruption")

    result = ops.move_files(plan, rows, *move_context, boundary=fail)
    ui.LibraryFileActionsMixin._run_library_file_commit(
        host, popup, "move", None, Mock()
    )
    _, done = callbacks.pop()
    done(ArchiveWorkResult(2, "file_commit", value=result))
    terminal = popup.message.set.call_args.args[0]
    assert (
        "3 selected:" in terminal
        and ("1 media moved" if interrupted else "2 media moved") in terminal
        and "1 already in destination" in terminal
    )
    if interrupted:
        assert "1 need review" in terminal


@pytest.mark.parametrize("boundary_name", ["copies_verified", "history_saved"])
def test_partial_shared_move_keeps_recoverable_sources(
    item, move_context, boundary_name
):
    rows = peers(item)
    hit = False

    def fail(name):
        nonlocal hit
        if name == boundary_name and not hit:
            hit = True
            raise OSError("synthetic interruption")

    _, result = execute(rows, move_context, boundary=fail)
    assert ops.pending_file_operations(move_context[2])
    assert Path(rows[0]["vodforge_output_path"]).exists()
    if boundary_name == "copies_verified":
        assert [s for _, s in result.outcomes] == ["needs_attention", "needs_attention"]
        assert Path(rows[1]["vodforge_output_path"]).exists()
    else:
        assert [s for _, s in result.outcomes] == ["cleanup_pending", "completed"]
        assert not Path(rows[1]["vodforge_output_path"]).exists()
        recovered = ops.recover_move_cleanup(
            result.journal, result.records, move_context[1]
        )
        assert all(state == "completed" for _, state in recovered.outcomes)
        assert not Path(rows[0]["vodforge_output_path"]).exists()
        assert not ops.pending_file_operations(move_context[2])
