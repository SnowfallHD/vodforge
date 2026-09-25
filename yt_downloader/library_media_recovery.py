from __future__ import annotations

import os
import re
import urllib.parse
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

from .archive_paths import ArchivePath
from .history import (
    HISTORY_MEDIA_MISSING,
    HISTORY_MEDIA_PRESENT,
    HISTORY_MEDIA_UNAVAILABLE,
    RETRY_JOB_METADATA_KEY,
    history_annotation_owner,
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
from .models import DownloadJob, ExportMode, OutputType
from .run_identity import (
    OUTPUT_PROFILE_KEY,
    annotate_job_metadata,
    job_attempt_signature,
    job_output_profile,
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
    previous_annotation_owner: str = ""
    requires_destination_choice: bool = False
    preset_migrated: bool = False

    @property
    def can_redownload(self) -> bool:
        return self.kind == "missing" and self.job is not None


def _selected_item_url(info: Mapping[str, Any], saved_job: DownloadJob) -> str | None:
    """Recover the captured video only; playlist identity remains organization."""
    video_id = str(info.get("id") or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", video_id) is None:
        return None
    # A single-item source may not have a provider watch URL at all. Reuse its
    # validated saved input only when the committed row and preview both bind
    # that input to this exact item. Playlist and batch recovery still targets
    # the selected video below.
    if (
        saved_job.single_video_only
        and not saved_job.batch_mode
        and len(saved_job.urls or [saved_job.url]) == 1
        and saved_job.url
        == str(info.get("original_url") or info.get("webpage_url") or "").strip()
        and str((saved_job.preview_info or {}).get("id") or "").strip() == video_id
    ):
        return saved_job.url
    query = {"v": video_id}
    playlist_id = str(info.get("playlist_id") or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", playlist_id):
        query["list"] = playlist_id
    return "https://www.youtube.com/watch?" + urllib.parse.urlencode(query)


def _redownload_export_mode(job: DownloadJob, info: Mapping[str, Any]) -> ExportMode:
    """Retire old MP4 presets without changing current CTV or custom intent."""
    if job.output_type is not OutputType.MP4:
        return job.export_mode
    if job.export_mode is ExportMode.STRICT_COMPLIANCE:
        return ExportMode.EVERYDAY
    # AUTO_CBR is also the current CTV engine value. Only its exact saved
    # current profile proves that choice; ambiguous old records use Everyday.
    if job.export_mode is ExportMode.AUTO_CBR and info.get(
        OUTPUT_PROFILE_KEY
    ) != job_output_profile(job):
        return ExportMode.EVERYDAY
    return job.export_mode


def _legacy_preset_needs_everyday(info: Mapping[str, Any]) -> bool:
    """Recognize retired MP4 labels without inventing an incomplete saved job."""
    parts = [
        part.strip() for part in str(info.get(OUTPUT_PROFILE_KEY) or "").split("•")
    ]
    return (
        len(parts) == 3
        and parts[0] == "MP4"
        and parts[-1]
        in {
            "Auto CBR",
            "Auto CBR (Recommended)",
            "Strict Compliance",
            "CTV (legacy fixed bitrate)",
        }
    )


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
        "vodforge_archive_id",
        "vodforge_archive_annotation_owner",
        "vodforge_relinked",
    ):
        preview.pop(key, None)
    return preview


class LibraryMediaRecoveryOwner:
    """Reconstruct exact redownload work without making a Library row authoritative."""

    def __init__(
        self,
        *,
        run_id_factory: Callable[[], str] | None = None,
        artifact_directory: Callable[[Path, dict[str, Any]], Path] | None = None,
    ) -> None:
        self._run_id_factory = run_id_factory or (lambda: uuid.uuid4().hex)
        self._artifact_directory = artifact_directory
        self._draft_destination: tuple[str, Path] | None = None
        self._draft_export_mode: ExportMode | None = None

    def prepare_destination(
        self,
        source_url: str,
        destination: Path,
        *,
        export_mode: ExportMode | None = None,
    ) -> None:
        """Session-only recovery draft; durable settings and history are untouched."""
        self._draft_destination = (source_url.strip(), destination)
        self._draft_export_mode = export_mode

    def clear_destination(self) -> None:
        self._draft_destination = None
        self._draft_export_mode = None

    def is_draft_for(self, source_url: str) -> bool:
        draft = self._draft_destination
        return draft is not None and draft[0] == source_url.strip()

    def export_mode_for(self, source_url: str) -> ExportMode | None:
        return self._draft_export_mode if self.is_draft_for(source_url) else None

    def update_export_mode(self, source_url: str, mode: ExportMode) -> bool:
        if not self.is_draft_for(source_url) or self._draft_export_mode is None:
            return False
        self._draft_export_mode = mode
        return True

    def destination_for(self, source_url: str, default: str) -> str:
        draft = self._draft_destination
        if draft is not None and draft[0] == source_url.strip():
            return str(draft[1])
        self.clear_destination()
        return default

    def _legacy_root(self, directory: Path, row: dict[str, Any]) -> Path | None:
        # Reverse only an exact production-generated suffix, never a channel-name
        # substring or a fixed count of parents. Repeated suffixes are ambiguous.
        if self._artifact_directory is None or not row.get("id"):
            return None
        legacy_row = dict(row)
        legacy_row.pop("vodforge_output_variant", None)
        for parent in directory.parents:
            if any(
                self._artifact_directory(parent, candidate) == directory
                for candidate in (row, legacy_row)
            ):
                return parent
        return None

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
            root = self._legacy_root(destination, row)
            if root is not None and self._legacy_root(root, row) is not None:
                root = None
            return LibraryMediaRecoveryPlan(
                "legacy",
                root,
                requires_destination_choice=root is None,
                preset_migrated=_legacy_preset_needs_everyday(row),
            )
        # History's location is the committed artifact parent and may include
        # VODForge's channel/playlist/video hierarchy. The durable job owns the
        # user-selected base destination used to reconstruct that hierarchy.
        # A reviewed relink changes artifact location, not the original signed
        # export intent. Preserve that intent, but require an explicit new base.
        # The innermost media folder must never become an inferred download root.
        relocated = row.get("vodforge_relinked") is True
        if not relocated and not _path_is_within(destination, saved_job.output_dir):
            return LibraryMediaRecoveryPlan("invalid", destination)
        stored_signature = metadata_attempt_signature(row)
        if stored_signature and job_attempt_signature(saved_job) != stored_signature:
            return LibraryMediaRecoveryPlan("invalid", destination)

        if not relocated and self._legacy_root(saved_job.output_dir, row) is not None:
            # A previous legacy recovery may already have saved a nested base.
            # Do not silently reinterpret a durable job or alter its signature.
            return LibraryMediaRecoveryPlan(
                "legacy",
                None,
                requires_destination_choice=True,
                preset_migrated=_redownload_export_mode(saved_job, row)
                != saved_job.export_mode,
            )

        source_url = _selected_item_url(row, saved_job)
        if source_url is None:
            return LibraryMediaRecoveryPlan("invalid", destination)
        export_mode = _redownload_export_mode(saved_job, row)
        previous_run_id = str(row.get("vodforge_run_id") or saved_job.run_id).strip()
        preview = _clean_preview(row)
        job = replace(
            saved_job,
            url=source_url,
            urls=[source_url],
            single_video_only=True,
            batch_mode=False,
            export_mode=export_mode,
            run_id=self._run_id_factory(),
            origin_run_id=previous_run_id or saved_job.run_id,
            execution_run_id=None,
            retry_of_run_id=previous_run_id or saved_job.run_id,
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
            row.get(ANNOTATION_OWNER_KEY) or history_annotation_owner(row)
        ).strip()
        return LibraryMediaRecoveryPlan(
            "missing",
            None if relocated else saved_job.output_dir,
            job=job,
            requires_destination_choice=relocated,
            preset_migrated=export_mode != saved_job.export_mode,
            previous_annotation_owner=previous_annotation_owner,
        )

    @staticmethod
    def with_destination(
        plan: LibraryMediaRecoveryPlan, destination: Path
    ) -> LibraryMediaRecoveryPlan:
        """Apply an explicit recovery-only base without editing saved settings."""
        if (
            not plan.can_redownload
            or plan.job is None
            or not plan.requires_destination_choice
        ):
            raise ValueError("This recovery does not require a destination")
        parsed = ArchivePath.parse(str(destination))
        if (parsed.style == "windows") != (os.name == "nt"):
            raise ValueError("Choose a location available on this computer")
        job = replace(plan.job, output_dir=destination)
        job.preview_info = annotate_job_metadata(job, dict(job.preview_info or {}))
        return replace(
            plan, destination=destination, job=job, requires_destination_choice=False
        )
