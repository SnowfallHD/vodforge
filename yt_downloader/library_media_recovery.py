from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

from .history import (
    HISTORY_MEDIA_MISSING,
    HISTORY_MEDIA_PRESENT,
    HISTORY_MEDIA_UNAVAILABLE,
    RETRY_JOB_METADATA_KEY,
    history_identity,
    history_media_file_state,
    history_output_dir,
)
from .library_state import (
    ACTIVE_METADATA_RUN_ID_KEY,
    ANNOTATION_OWNER_KEY,
    PROJECTION_OWNER_KEY,
    QUEUED_METADATA_RUN_ID_KEY,
    RUN_STATUS_KEY,
)
from .models import DownloadJob
from .run_identity import (
    annotate_job_metadata,
    job_attempt_signature,
    metadata_attempt_signature,
)
from .run_state import RunStateError, deserialize_download_job

MediaRecoveryKind = Literal[
    "available", "missing", "unavailable", "ambiguous", "legacy", "invalid"
]


@dataclass(frozen=True, slots=True)
class LibraryMediaRecoveryPlan:
    """One immutable decision for a missing committed Library artifact."""

    kind: MediaRecoveryKind
    destination: Path | None
    job: DownloadJob | None = None
    replaced_history_identity: tuple[str, str, str] | None = None
    previous_annotation_owner: str = ""

    @property
    def can_redownload(self) -> bool:
        return self.kind == "missing" and self.job is not None


def _normalized_path(path: Path) -> str:
    try:
        resolved = path.expanduser().resolve(strict=False)
    except OSError:
        resolved = Path(os.path.abspath(str(path.expanduser())))
    return os.path.normcase(str(resolved))


def _path_is_within(path: Path, root: Path) -> bool:
    """Return whether a committed artifact directory belongs to a saved base."""

    normalized_path = Path(_normalized_path(path))
    normalized_root = Path(_normalized_path(root))
    try:
        normalized_path.relative_to(normalized_root)
    except ValueError:
        return False
    return True


def _clean_preview(info: Mapping[str, Any]) -> dict[str, Any]:
    preview = dict(info)
    for key in (
        ACTIVE_METADATA_RUN_ID_KEY,
        QUEUED_METADATA_RUN_ID_KEY,
        RUN_STATUS_KEY,
        PROJECTION_OWNER_KEY,
        ANNOTATION_OWNER_KEY,
        "vodforge_projection_owner_kind",
        "vodforge_terminal_status",
        "vodforge_terminal_message",
        "vodforge_terminal_run_id",
        "vodforge_preview_complete",
        "vodforge_preview_run_id",
        RETRY_JOB_METADATA_KEY,
    ):
        preview.pop(key, None)
    return preview


class LibraryMediaRecoveryOwner:
    """Reconstruct exact redownload work without making a Library row authoritative."""

    def __init__(self, *, run_id_factory: Callable[[], str] | None = None) -> None:
        self._run_id_factory = run_id_factory or (lambda: uuid.uuid4().hex)

    def plan(
        self,
        info: Mapping[str, Any],
        *,
        completed_jobs: Sequence[DownloadJob] = (),
    ) -> LibraryMediaRecoveryPlan:
        row = dict(info)
        destination = history_output_dir(row)
        media_state = history_media_file_state(row)
        if media_state == HISTORY_MEDIA_UNAVAILABLE:
            return LibraryMediaRecoveryPlan("unavailable", destination)
        if media_state == HISTORY_MEDIA_PRESENT:
            return LibraryMediaRecoveryPlan("ambiguous", destination)
        if media_state != HISTORY_MEDIA_MISSING or destination is None:
            return LibraryMediaRecoveryPlan("invalid", destination)

        saved_job: DownloadJob | None = None
        payload = row.get(RETRY_JOB_METADATA_KEY)
        if isinstance(payload, Mapping):
            try:
                saved_job = deserialize_download_job(payload)
            except RunStateError:
                return LibraryMediaRecoveryPlan("invalid", destination)
        if saved_job is None:
            recorded_run_id = str(row.get("vodforge_run_id") or "").strip()
            stored_signature = metadata_attempt_signature(row)
            saved_job = next(
                (
                    job
                    for job in completed_jobs
                    if job.run_id == recorded_run_id
                    and (
                        not stored_signature
                        or job_attempt_signature(job) == stored_signature
                    )
                ),
                None,
            )
        if saved_job is None:
            return LibraryMediaRecoveryPlan("legacy", destination)
        # History's location is the committed artifact parent and may include
        # VODForge's channel/playlist/video hierarchy. The durable job owns the
        # user-selected base destination used to reconstruct that hierarchy.
        if not _path_is_within(destination, saved_job.output_dir):
            return LibraryMediaRecoveryPlan("invalid", destination)
        stored_signature = metadata_attempt_signature(row)
        if stored_signature and job_attempt_signature(saved_job) != stored_signature:
            return LibraryMediaRecoveryPlan("invalid", destination)

        previous_run_id = str(row.get("vodforge_run_id") or saved_job.run_id).strip()
        preview = _clean_preview(row)
        job = replace(
            saved_job,
            run_id=self._run_id_factory(),
            origin_run_id=previous_run_id or saved_job.run_id,
            preview_info=dict(preview),
            metadata_keys=set(),
            history_identities=set(),
            activity_lines=[],
            terminal_status=None,
            terminal_message="",
            item_terminal_emitted=False,
        )
        job.preview_info = annotate_job_metadata(job, dict(preview))
        previous_annotation_owner = str(
            row.get(ANNOTATION_OWNER_KEY)
            or (f"run:{previous_run_id}" if previous_run_id else "")
        ).strip()
        return LibraryMediaRecoveryPlan(
            "missing",
            saved_job.output_dir,
            job=job,
            replaced_history_identity=history_identity(row),
            previous_annotation_owner=previous_annotation_owner,
        )

    @staticmethod
    def history_after_acceptance(
        history_items: Sequence[dict[str, Any]],
        plan: LibraryMediaRecoveryPlan,
    ) -> list[dict[str, Any]]:
        """Retire only the exact stale artifact after replacement is durable."""

        replaced = plan.replaced_history_identity
        if replaced is None:
            return [dict(item) for item in history_items]
        return [
            dict(item)
            for item in history_items
            if history_identity(dict(item)) != replaced
        ]
