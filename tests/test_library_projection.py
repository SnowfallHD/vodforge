from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from yt_downloader.library_state import (
    ACTIVE_METADATA_RUN_ID_KEY,
    PROJECTION_OWNER_KIND_KEY,
    QUEUED_METADATA_RUN_ID_KEY,
    RUN_STATUS_KEY,
    LibraryProjectionOwner,
)
from yt_downloader.models import (
    DownloadJob,
    ExportMode,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)


def _job(tmp_path: Path, suffix: str, *, metadata: bool) -> DownloadJob:
    job = DownloadJob(
        url=f"https://www.youtube.com/watch?v={suffix}",
        output_dir=tmp_path,
        output_type=OutputType.MP4,
        quality_label="1080p Full HD",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=True,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=False,
        tags=[],
    )
    if metadata:
        job.preview_info = {"id": suffix, "title": f"Video {suffix}"}
    return job


def _reconcile(
    owner: LibraryProjectionOwner,
    *,
    history: list[dict[str, Any]] | None = None,
    active: DownloadJob | None = None,
    queued: list[DownloadJob] | None = None,
    terminal: list[DownloadJob] | None = None,
):
    return owner.reconcile(
        history_items=history or [],
        active_job=active,
        queued_jobs=queued or [],
        terminal_jobs=terminal or [],
    )


def _assert_exact_run_projection(projection, expected: dict[str, str]) -> None:
    projected: dict[str, str] = {}
    for row in projection.rows:
        run_id = str(
            row.get(ACTIVE_METADATA_RUN_ID_KEY)
            or row.get(QUEUED_METADATA_RUN_ID_KEY)
            or row.get("vodforge_terminal_run_id")
            or ""
        )
        if not run_id:
            continue
        status = str(
            row.get(RUN_STATUS_KEY) or row.get("vodforge_terminal_status") or ""
        )
        assert run_id not in projected
        projected[run_id] = status
    assert projected == expected
    assert projection.receipt.violation_codes == ()


@pytest.mark.parametrize(
    "metadata", [False, True], ids=["without-metadata", "with-metadata"]
)
@pytest.mark.parametrize(
    ("phases", "terminal_status"),
    [
        ((), "Stopped"),
        (("Preparing",), "Stopped"),
        (("Preparing", "Downloading"), "Stopped"),
        (("Preparing", "Downloading", "Transcoding"), "Stopped"),
        (("Preparing", "Downloading"), "Failed"),
        (("Preparing", "Downloading", "Transcoding"), "Failed"),
        (("Preparing", "Downloading", "Transcoding"), "Completed"),
    ],
)
def test_transition_matrix_replaces_one_projection_by_run_id(
    tmp_path: Path,
    metadata: bool,
    phases: tuple[str, ...],
    terminal_status: str,
) -> None:
    owner = LibraryProjectionOwner()
    job = _job(tmp_path, "matrix", metadata=metadata)
    _assert_exact_run_projection(
        _reconcile(owner, queued=[job]), {job.run_id: "Queued"}
    )

    for phase in phases:
        owner.observe_phase(job.run_id, phase)
        _assert_exact_run_projection(_reconcile(owner, active=job), {job.run_id: phase})

    job.terminal_status = terminal_status
    terminal = _reconcile(owner, active=job, terminal=[job])
    _assert_exact_run_projection(terminal, {job.run_id: terminal_status})
    assert terminal == _reconcile(owner, active=job, terminal=[job])


@pytest.mark.parametrize("phase", ["Preparing", "Downloading", "Transcoding"])
def test_restart_recovery_replaces_interrupted_transient_with_failed(
    tmp_path: Path, phase: str
) -> None:
    owner = LibraryProjectionOwner()
    job = _job(tmp_path, f"restart-{phase}", metadata=False)
    owner.observe_phase(job.run_id, phase)
    _assert_exact_run_projection(_reconcile(owner, active=job), {job.run_id: phase})

    recovered = replace(job, terminal_status="Failed", terminal_message="Recovered")
    projection = _reconcile(owner, terminal=[recovered])
    _assert_exact_run_projection(projection, {job.run_id: "Failed"})
    assert all(row.get(RUN_STATUS_KEY) != phase for row in projection.rows)


def test_retry_replaces_terminal_owner_without_merging_other_same_video(
    tmp_path: Path,
) -> None:
    owner = LibraryProjectionOwner()
    stopped = _job(tmp_path, "same", metadata=True)
    stopped.terminal_status = "Stopped"
    other = _job(tmp_path / "other", "same", metadata=True)
    other.terminal_status = "Failed"
    _assert_exact_run_projection(
        _reconcile(owner, terminal=[stopped, other]),
        {stopped.run_id: "Stopped", other.run_id: "Failed"},
    )

    retry = _job(tmp_path, "same", metadata=True)
    retry.origin_run_id = stopped.run_id
    owner.observe_phase(retry.run_id, "Preparing")
    _assert_exact_run_projection(
        _reconcile(owner, active=retry, terminal=[other]),
        {retry.run_id: "Preparing", other.run_id: "Failed"},
    )


def test_late_and_duplicate_events_fail_closed_deterministically(
    tmp_path: Path,
) -> None:
    diagnostics: list[str] = []
    owner = LibraryProjectionOwner(diagnostic=diagnostics.append)
    job = _job(tmp_path, "duplicates", metadata=False)
    terminal = replace(job, terminal_status="Stopped")

    projection = _reconcile(owner, queued=[job], terminal=[terminal, terminal])
    assert len(projection.rows) == 1
    assert projection.rows[0]["vodforge_terminal_status"] == "Stopped"
    assert "duplicate_canonical_run_owner" in projection.receipt.violation_codes
    assert diagnostics
    assert all("duplicates" not in line for line in diagnostics)

    owner.observe_phase(job.run_id, "Downloading")
    after_late_progress = _reconcile(owner, terminal=[terminal])
    assert len(after_late_progress.rows) == 1
    assert after_late_progress.rows[0]["vodforge_terminal_status"] == "Stopped"
    assert RUN_STATUS_KEY not in after_late_progress.rows[0]


def test_completed_history_removal_and_physical_identity_merge(tmp_path: Path) -> None:
    owner = LibraryProjectionOwner()
    output = tmp_path / "same.mp4"
    first = {
        "id": "same",
        "title": "First",
        "vodforge_output_type": "MP4",
        "vodforge_output_path": str(output),
        "vodforge_run_id": "run-one",
        "vodforge_output_dir": str(tmp_path),
    }
    duplicate = {**first, "title": "Duplicate", "vodforge_run_id": "run-two"}

    projection = _reconcile(owner, history=[first, duplicate])
    assert len(projection.rows) == 1
    assert projection.rows[0][PROJECTION_OWNER_KIND_KEY] == "history"
    assert "duplicate_history_owner" in projection.receipt.violation_codes
    assert _reconcile(owner, history=[]).rows == ()


def test_no_projection_exists_without_a_canonical_owner() -> None:
    owner = LibraryProjectionOwner()
    assert _reconcile(owner).rows == ()
    owner.observe_phase("ghost", "Preparing")
    assert _reconcile(owner).rows == ()
