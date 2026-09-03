from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from yt_downloader.library_annotations import (
    LibraryAnnotation,
    LibraryAnnotationsError,
    LibraryAnnotationsOwner,
    library_annotations_file_path,
    load_library_annotations,
    sanitize_library_annotation,
    save_library_annotations,
)


def test_annotation_round_trip_is_private_atomic_and_bounded(tmp_path: Path) -> None:
    path = tmp_path / "state" / "library-annotations.json"
    save_library_annotations(
        path,
        {
            "run:one": LibraryAnnotation(
                note="Worth revisiting", tags=("Focus", "music"), category="Work"
            )
        },
    )

    assert load_library_annotations(path) == {
        "run:one": LibraryAnnotation(
            note="Worth revisiting", tags=("Focus", "music"), category="Work"
        )
    }
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert list(path.parent.glob("*.tmp")) == []


def test_annotation_path_uses_private_application_data_location(tmp_path: Path) -> None:
    assert library_annotations_file_path(platform_name="darwin", home=tmp_path) == (
        tmp_path
        / "Library"
        / "Application Support"
        / "VODForge"
        / "library-annotations.json"
    )


def test_annotation_sanitization_deduplicates_tags_without_provider_mutation() -> None:
    annotation = sanitize_library_annotation(
        {
            "note": "  private note  ",
            "tags": ["Focus", "focus", "  Music  ", ""],
            "category": "  Work  ",
        }
    )

    assert annotation == LibraryAnnotation(
        note="private note", tags=("Focus", "Music"), category="Work"
    )


def test_owner_commits_replacement_or_removal_atomically(tmp_path: Path) -> None:
    owner = LibraryAnnotationsOwner(tmp_path / "annotations.json")
    assert owner.load() == {}

    owner.replace("run:one", LibraryAnnotation(note="First"))
    owner.replace("run:one", LibraryAnnotation(note="Second", tags=("Keep",)))
    assert owner.annotation_for("run:one") == LibraryAnnotation(
        note="Second", tags=("Keep",)
    )

    owner.remove("run:one")
    assert owner.annotation_for("run:one").empty
    assert load_library_annotations(owner.path) == {}


def test_owner_snapshot_is_immutable_and_detached(tmp_path: Path) -> None:
    owner = LibraryAnnotationsOwner(tmp_path / "annotations.json")
    owner.replace("run:one", LibraryAnnotation(note="Keep"))

    snapshot = owner.snapshot

    with pytest.raises(TypeError):
        snapshot["run:two"] = LibraryAnnotation(note="No")  # type: ignore[index]
    assert owner.annotation_for("run:two").empty


def test_owner_transfers_annotations_across_canonical_run_replacement(
    tmp_path: Path,
) -> None:
    owner = LibraryAnnotationsOwner(tmp_path / "annotations.json")
    annotation = LibraryAnnotation(note="Keep this context", category="Research")
    owner.replace("run:old", annotation)

    owner.transfer("run:old", "run:new")

    assert owner.annotation_for("run:old").empty
    assert owner.annotation_for("run:new") == annotation
    assert load_library_annotations(owner.path) == {"run:new": annotation}


def test_malformed_annotation_ledger_fails_closed_without_rewriting(
    tmp_path: Path,
) -> None:
    path = tmp_path / "annotations.json"
    original = json.dumps({"schema_version": 99, "items": {}}).encode()
    path.write_bytes(original)

    with pytest.raises(LibraryAnnotationsError):
        load_library_annotations(path)

    assert path.read_bytes() == original
