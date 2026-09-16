from __future__ import annotations

import copy
import json
from pathlib import Path
from threading import Event

import pytest

from yt_downloader.archive_paths import ArchivePath, RootMapping, map_archive_path
from yt_downloader.archive_relink import (
    FileObservation,
    RelinkConflict,
    observe_destination,
    preview_relink,
    relocated_records,
    verify_relink,
)
from yt_downloader.history import (
    history_annotation_owner,
    history_archive_owner,
    load_history,
    save_history,
)
from yt_downloader.library_annotations import LibraryAnnotation
from yt_downloader.library_state import LibraryProjectionOwner


def mapping(source, destination):
    return RootMapping(
        ArchivePath.parse(str(source)), ArchivePath.parse(str(destination))
    )


def record(path, *, identity="video", run=""):
    parsed = ArchivePath.parse(str(path))
    return {
        "id": identity,
        "title": "Private fixture",
        "vodforge_output_type": "MP4",
        "vodforge_output_dir": str(parsed.parent),
        "vodforge_output_path": str(parsed),
        "vodforge_output_variant": "MP4 Everyday [1234567890abcdef]",
        "vodforge_output_profile": "MP4 1080p Everyday",
        "vodforge_run_id": run,
        "vodforge_encoding_summary": {
            "source": {"Video codec": "h264", "Source private label": "unchanged"},
            "output": {"Output file path": str(parsed), "Video codec": "h264"},
        },
        "vodforge_retry_job": {
            "output_dir": str(parsed.parent),
            "settings": "untouched",
        },
    }


@pytest.mark.parametrize(
    ("source", "root", "relative"),
    [
        (r"C:\Downloads\Series\clip.mp4", r"c:\downloads", ("Series", "clip.mp4")),
        (r"C:\Downloads-old\clip.mp4", r"C:\Downloads", None),
        (r"\\NAS\Vault\Series\clip.mp4", r"\\nas\vault", ("Series", "clip.mp4")),
        (r"\\NAS\Vault2\clip.mp4", r"\\NAS\Vault", None),
        ("/Volumes/Archive/A/clip.mp4", "/Volumes/Archive", ("A", "clip.mp4")),
        ("/Volumes/archive/clip.mp4", "/Volumes/Archive", None),
        ("/archive-long/a.mp4", "/archive", None),
    ],
)
def test_component_mapping_does_not_cross_siblings_or_storage(source, root, relative):
    assert ArchivePath.parse(source).relative_to(ArchivePath.parse(root)) == relative


@pytest.mark.parametrize(
    "path",
    [
        r"C:relative\clip.mp4",
        r"\rooted\clip.mp4",
        "relative/file",
        "/old/../other/file",
        r"C:\old\..\other\file",
        r"\\?\C:\file",
        r"C:\test\CON.mp4",
        r"C:\test\name.",
        "/bad\0name",
    ],
)
def test_ambiguous_or_unsafe_paths_remain_unresolved(path):
    with pytest.raises(ValueError):
        ArchivePath.parse(path)


def test_nested_mapping_is_specific_and_equal_root_conflict_is_ambiguous():
    path = ArchivePath.parse(r"C:\Archive\Series\season\clip.mp4")
    broad = mapping(r"C:\Archive", r"\\NAS\Vault")
    nested = mapping(r"C:\Archive\Series", "/Volumes/SSD/Series")
    target, chosen, state = map_archive_path(path, (broad, nested))
    assert str(target) == "/Volumes/SSD/Series/season/clip.mp4"
    assert chosen == nested and state == "mapped"
    assert (
        map_archive_path(path, (nested, mapping(r"c:\archive\series", "/different")))[2]
        == "ambiguous_mapping"
    )


def test_ancestry_keeps_every_parent_and_innermost_export_folder():
    path = ArchivePath.parse(r"\\NAS\Vault\Show\Season 01\Export")
    assert [str(parent) for parent in path.ancestry] == [
        "\\\\NAS\\Vault\\",
        "\\\\NAS\\Vault\\Show",
        "\\\\NAS\\Vault\\Show\\Season 01",
        "\\\\NAS\\Vault\\Show\\Season 01\\Export",
    ]
    assert path.storage == ("network", path.ancestry[0])


def test_mapping_preview_has_no_filesystem_effects_and_preserves_variant_names(
    monkeypatch,
):
    def forbidden(*args, **kwargs):
        pytest.fail("Preview touched the filesystem")

    monkeypatch.setattr(Path, "stat", forbidden)
    rows = [record(r"C:\Archive\Show\MP4 Everyday [1234567890abcdef]\clip.mp4")]
    before = copy.deepcopy(rows)
    proposal = preview_relink(rows, [mapping(r"C:\Archive", r"\\NAS\Vault")])
    assert (
        str(proposal.entries[0].destination)
        == r"\\NAS\Vault\Show\MP4 Everyday [1234567890abcdef]\clip.mp4"
    )
    assert rows == before and proposal.counts == {"pending": 1}


def test_collisions_with_selected_or_unselected_history_never_displace_items():
    rows = [record("/old/a.mp4"), record("/dest/a.mp4", identity="other")]
    result = preview_relink(rows, [mapping("/old", "/dest")], selected=[0])
    assert result.counts == {"collision": 1}
    rows = [record("/one/a.mp4"), record("/two/a.mp4", identity="other")]
    result = preview_relink(rows, [mapping("/one", "/dest"), mapping("/two", "/dest")])
    assert result.counts == {"collision": 2}


def test_actual_destination_verification_detects_missing_empty_and_wrong_sidecar(
    tmp_path,
):
    old, new = tmp_path / "old", tmp_path / "new"
    new.mkdir()
    rows = [record(old / "clip.mp4")]
    preview = preview_relink(rows, [mapping(old, new)])
    assert verify_relink(preview, rows).counts == {"missing": 1}
    (new / "clip.mp4").write_bytes(b"")
    assert verify_relink(preview, rows).counts == {"missing": 1}
    (new / "clip.mp4").write_bytes(b"synthetic-media")
    (new / "metadata.json").write_text(json.dumps({"id": "wrong"}))
    assert verify_relink(preview, rows).counts == {"identity_mismatch": 1}
    (new / "metadata.json").write_text(json.dumps({"id": "video"}))
    (new / "thumbnail.jpg").write_bytes(b"synthetic-thumbnail")
    verified = verify_relink(preview, rows)
    assert verified.counts == {"ready": 1}
    assert verified.entries[0].companions == ("metadata.json", "thumbnail.jpg")


def test_foreign_platform_path_is_unavailable_without_trying_local_relative_path(
    tmp_path,
):
    import os

    destination = ArchivePath.parse(
        "/Volumes/Fake/clip.mp4" if os.name == "nt" else r"G:\Vault\clip.mp4"
    )
    assert observe_destination(destination, {}).state == "foreign_platform"


def test_actual_alias_collision_is_not_treated_as_two_exports(tmp_path):
    new = tmp_path / "new"
    new.mkdir()
    (new / "a.mp4").write_bytes(b"synthetic")
    (new / "b.mp4").hardlink_to(new / "a.mp4")
    rows = [
        record(tmp_path / "old" / name, identity=name) for name in ("a.mp4", "b.mp4")
    ]
    preview = preview_relink(rows, [mapping(tmp_path / "old", new)])
    assert verify_relink(preview, rows).counts == {"collision": 2}


@pytest.mark.parametrize("interruption", ["cancel", "deadline"])
def test_interruption_invalidates_earlier_success_in_same_batch(interruption):
    rows = [record(f"/old/{index}.mp4") for index in range(3)]
    preview = preview_relink(rows, [mapping("/old", "/new")])
    cancelled = Event()
    now = [0.0]
    calls = []

    def observe(*args, **kwargs):
        calls.append(1)
        if interruption == "cancel":
            cancelled.set()
        else:
            now[0] = 100.0
        return FileObservation("ready", (1, 2, 8, 123))

    result = verify_relink(
        preview, rows, cancelled=cancelled, observe=observe, clock=lambda: now[0]
    )
    assert len(calls) == 1
    assert result.counts == {
        ("cancelled" if interruption == "cancel" else "timed_out"): 3
    }
    with pytest.raises(RelinkConflict):
        relocated_records(result, rows, accepted=[0])


def test_stale_history_and_changed_metadata_do_not_apply_even_if_paths_match():
    rows = [record("/old/a.mp4")]
    preview = preview_relink(rows, [mapping("/old", "/new")])
    current = copy.deepcopy(rows)
    current[0]["title"] = "New title"
    result = verify_relink(
        preview, current, observe=lambda *a, **kw: pytest.fail("stale probe")
    )
    assert result.counts == {"stale": 1}
    with pytest.raises(RelinkConflict):
        relocated_records(result, current, accepted=[0])


@pytest.mark.parametrize("run", ["", "original-run"])
def test_relink_restart_preserves_identity_annotations_settings_and_companion_bytes(
    tmp_path, run
):
    old = tmp_path / "old"
    new = tmp_path / "new"
    new.mkdir()
    media = new / "clip.mp4"
    media.write_bytes(b"synthetic media bytes")
    thumbnail = new / "thumbnail.jpg"
    thumbnail.write_bytes(b"synthetic image bytes")
    rows = [record(old / "clip.mp4", run=run)]
    before = copy.deepcopy(rows)
    previous_owner = history_annotation_owner(rows[0])
    annotations = {
        previous_owner: LibraryAnnotation(
            note="Keep note", tags=("tag",), category="Collection"
        )
    }
    verified = verify_relink(preview_relink(rows, [mapping(old, new)]), rows)
    updated = relocated_records(verified, rows, accepted=[0])
    assert rows == before
    assert updated[0]["vodforge_retry_job"] == before[0]["vodforge_retry_job"]
    assert updated[0]["vodforge_output_variant"] == before[0]["vodforge_output_variant"]
    assert (
        updated[0]["vodforge_encoding_summary"]["source"]
        == before[0]["vodforge_encoding_summary"]["source"]
    )
    ledger = tmp_path / "history.json"
    save_history(ledger, updated)
    reloaded = load_history(ledger)
    assert history_archive_owner(reloaded[0]) == history_archive_owner(updated[0])
    assert history_annotation_owner(reloaded[0]) == previous_owner
    projected = LibraryProjectionOwner().reconcile(
        history_items=reloaded,
        active_job=None,
        queued_jobs=(),
        terminal_jobs=(),
        annotations=annotations,
    )
    assert projected.rows[0]["vodforge_user_note"] == "Keep note"
    assert projected.rows[0]["vodforge_user_category"] == "Collection"
    assert media.read_bytes() == b"synthetic media bytes"
    assert thumbnail.read_bytes() == b"synthetic image bytes"
    assert not old.exists()


def test_partial_verification_applies_only_explicitly_accepted_ready_items():
    rows = [record(f"/old/{index}.mp4") for index in range(3)]
    proposal = preview_relink(rows, [mapping("/old", "/new")])
    responses = iter(
        [
            FileObservation("ready", (1, 2, 3, 4)),
            FileObservation("unavailable"),
            FileObservation("missing"),
        ]
    )
    verified = verify_relink(proposal, rows, observe=lambda *a, **kw: next(responses))
    updated = relocated_records(verified, rows, accepted=[0])
    assert len(updated) == 3 and updated[1:] == rows[1:]
    assert rows[0]["vodforge_output_path"] == "/old/0.mp4"


def test_diagnostics_do_not_expose_paths_titles_identifiers_or_tokens():
    rows = [record("/PRIVATE_USERNAME/SECRET_TITLE/clip.mp4", identity="PRIVATE_ID")]
    result = preview_relink(rows, [mapping("/PRIVATE_USERNAME", "/PRIVATE_NAS")])
    encoded = json.dumps(result.diagnostic("preview"))
    for private in ("PRIVATE", "SECRET", ".mp4", result.snapshot[0]):
        assert private not in encoded


def test_large_archive_preview_is_bounded_without_scanning():
    rows = [
        record(f"/old/group-{index // 100}/clip-{index}.mp4", identity=str(index))
        for index in range(5000)
    ]
    result = preview_relink(rows, [mapping("/old", "/new")])
    assert len(result.entries) == 5000 and result.counts == {"pending": 5000}
    with pytest.raises(ValueError):
        preview_relink(rows + rows[:1], [mapping("/old", "/new")])


def test_unselected_hardlink_peer_prevents_identity_merger(tmp_path):
    new = tmp_path / "new"
    peer = tmp_path / "peer"
    new.mkdir()
    peer.mkdir()
    target = new / "clip.mp4"
    target.write_bytes(b"synthetic")
    (peer / "existing.mp4").hardlink_to(target)
    rows = [
        record(tmp_path / "old" / "clip.mp4"),
        record(peer / "existing.mp4", identity="other"),
    ]
    proposal = preview_relink(rows, [mapping(tmp_path / "old", new)], selected=[0])
    assert verify_relink(proposal, rows).counts == {"collision": 1}


@pytest.mark.parametrize(
    "fault", ["cancel", "metadata_change", "file_change", "write_failure"]
)
def test_commit_rechecks_and_failed_commit_preserves_durable_history(
    tmp_path, monkeypatch, fault
):
    from yt_downloader.archive_relink import commit_relink
    from yt_downloader.history import HistoryError

    new = tmp_path / "new"
    new.mkdir()
    target = new / "clip.mp4"
    target.write_bytes(b"synthetic media")
    rows = [record(tmp_path / "old" / "clip.mp4")]
    ledger = tmp_path / "history.json"
    save_history(ledger, rows)
    before = ledger.read_bytes()
    preview = verify_relink(
        preview_relink(rows, [mapping(tmp_path / "old", new)]), rows
    )
    cancelled = Event()
    if fault == "cancel":
        cancelled.set()
    elif fault == "metadata_change":
        rows[0]["title"] = "new metadata after review"
    elif fault == "file_change":
        target.write_bytes(b"replaced media changed its size")
    else:
        original_replace = Path.replace

        def fail_replace(self, destination):
            if Path(destination) == ledger:
                raise PermissionError("private history destination")
            return original_replace(self, destination)

        monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises((RelinkConflict, HistoryError)):
        commit_relink(preview, rows, ledger, accepted=[0], cancelled=cancelled)
    assert ledger.read_bytes() == before
    assert not ledger.with_name(".history.json.tmp").exists()
    assert len(load_history(ledger)) == 1
    assert not (tmp_path / "old").exists()


@pytest.mark.parametrize("interruption", ["cancel", "deadline"])
def test_peer_alias_discovery_cannot_overwrite_terminal_interruption(interruption):
    rows = [record("/old/a.mp4"), record("/peer/a.mp4", identity="peer")]
    proposal = preview_relink(rows, [mapping("/old", "/new")], selected=[0])
    cancelled = Event()
    now = [0.0]

    def peer_identity(_path):
        if interruption == "cancel":
            cancelled.set()
        else:
            now[0] = 100.0
        return (1, 2)

    result = verify_relink(
        proposal,
        rows,
        cancelled=cancelled,
        clock=lambda: now[0],
        observe=lambda *a, **kw: FileObservation("ready", (1, 2, 3, 4)),
        peer_identity=peer_identity,
    )
    assert result.counts == {
        ("cancelled" if interruption == "cancel" else "timed_out"): 1
    }
    with pytest.raises(RelinkConflict):
        relocated_records(result, rows, accepted=[0])
