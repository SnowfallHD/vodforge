from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from yt_downloader.run_deck_renderer import (
    RunDeckRenderOwner,
    RunDeckRenderResult,
    RunDeckSnapshot,
    RunDeckTileSnapshot,
)


def _snapshot(*, status: str = "Queued", title: str = "One") -> RunDeckSnapshot:
    return RunDeckSnapshot(
        layout="wide",
        capacity=4,
        tiles=(
            RunDeckTileSnapshot(
                structure=("queued", "run-1", title),
                status=status,
                progress=0.0,
            ),
        ),
        summary_text="1 run  •  1 queued",
        overflow_text="All 1 runs",
        overflow_visible=True,
    )


def test_run_deck_owner_noops_patches_and_rebuilds_from_snapshots():
    owner = RunDeckRenderOwner()
    operations: list[str] = []

    assert (
        owner.render(
            _snapshot(),
            patch_values=lambda *_args: operations.append("patch"),
            rebuild=lambda _snapshot: operations.append("rebuild"),
        )
        is RunDeckRenderResult.REBUILT
    )
    assert (
        owner.render(
            _snapshot(),
            patch_values=lambda *_args: operations.append("patch"),
            rebuild=lambda _snapshot: operations.append("rebuild"),
        )
        is RunDeckRenderResult.NOOP
    )
    assert (
        owner.render(
            _snapshot(status="Downloading"),
            patch_values=lambda *_args: operations.append("patch"),
            rebuild=lambda _snapshot: operations.append("rebuild"),
        )
        is RunDeckRenderResult.PATCHED
    )
    assert (
        owner.render(
            _snapshot(title="Two"),
            patch_values=lambda *_args: operations.append("patch"),
            rebuild=lambda _snapshot: operations.append("rebuild"),
        )
        is RunDeckRenderResult.REBUILT
    )

    assert operations == ["rebuild", "patch", "rebuild"]


def test_run_deck_snapshots_are_immutable_values():
    snapshot = _snapshot()

    with pytest.raises(FrozenInstanceError):
        snapshot.summary_text = "changed"  # type: ignore[misc]
