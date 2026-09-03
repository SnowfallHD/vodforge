from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Any, TypeGuard

from .history import history_identity, history_output_dir, history_output_type
from .library_annotations import LibraryAnnotation
from .models import DownloadJob, OutputType
from .run_identity import annotate_job_metadata

ACTIVE_METADATA_RUN_ID_KEY = "vodforge_active_run_id"
QUEUED_METADATA_RUN_ID_KEY = "vodforge_queued_run_id"
RUN_STATUS_KEY = "vodforge_run_status"
PROJECTION_OWNER_KEY = "vodforge_projection_owner"
PROJECTION_OWNER_KIND_KEY = "vodforge_projection_owner_kind"
ANNOTATION_OWNER_KEY = "vodforge_annotation_owner"
TRANSIENT_LIBRARY_STATUSES = frozenset(
    {"Queued", "Preparing", "Downloading", "Transcoding", "Validating", "Finalizing"}
)
TERMINAL_LIBRARY_STATUSES = frozenset({"Completed", "Failed", "Stopped", "Skipped"})
_ACTIVE_METADATA_STALE_KEYS = (
    "vodforge_preview_complete",
    "vodforge_preview_run_id",
    "vodforge_terminal_status",
    "vodforge_terminal_message",
    "vodforge_terminal_run_id",
    QUEUED_METADATA_RUN_ID_KEY,
    RUN_STATUS_KEY,
)
_PROJECTION_DECORATION_KEYS = (
    PROJECTION_OWNER_KEY,
    PROJECTION_OWNER_KIND_KEY,
    ANNOTATION_OWNER_KEY,
    "vodforge_user_note",
    "vodforge_user_tags",
    "vodforge_user_category",
)

MetadataRunKey = tuple[str, str]
HistoryIdentity = tuple[str, str, str]


def metadata_output_type(info: dict[str, Any]) -> OutputType:
    """Return the canonical MP3/MP4 identity for one Library row."""
    return OutputType(history_output_type(info))


def format_duration(seconds: Any) -> str:
    """Render a finite nonnegative duration using the Library's compact form."""
    try:
        number = float(seconds)
    except (TypeError, ValueError, OverflowError):
        return "—"
    if not math.isfinite(number) or number < 0:
        return "—"
    total = int(number)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def metadata_run_key(info: dict[str, Any]) -> MetadataRunKey | None:
    """Identify one provider item and output type independently of run state."""
    video_id = str(info.get("id") or "").strip()
    if not video_id:
        return None
    return video_id, metadata_output_type(info).value


def is_metadata_preview(info: object) -> TypeGuard[dict[str, Any]]:
    """Return true only for a metadata-only item, never a terminal or saved run."""
    return bool(
        isinstance(info, dict)
        and info.get("vodforge_preview_complete") is True
        and history_output_dir(info) is None
        and not str(info.get("vodforge_terminal_status") or "").strip()
    )


def library_status_or_location(info: dict[str, Any]) -> str:
    """Render terminal state or the complete saved location for one Library row."""
    terminal_status = str(info.get("vodforge_terminal_status") or "").strip()
    if terminal_status:
        return terminal_status
    run_status = str(info.get(RUN_STATUS_KEY) or "").strip()
    if run_status:
        return run_status
    output_dir = history_output_dir(info)
    if output_dir is not None:
        return str(output_dir)
    return "Preview complete" if is_metadata_preview(info) else "Metadata only"


def library_phase_from_status(status_text: str) -> str | None:
    """Normalize worker prose into the bounded Library phase vocabulary."""

    normalized = status_text.casefold()
    return (
        "Transcoding"
        if "transcod" in normalized or "encoded" in normalized
        else "Downloading"
        if "downloading" in normalized
        else "Validating"
        if "validating" in normalized
        else "Finalizing"
        if "finalizing" in normalized
        else "Preparing"
        if any(
            marker in normalized
            for marker in ("starting", "reading playlist", "analyzing source")
        )
        else None
    )


@dataclass(frozen=True)
class LibraryRemovalPlan:
    """Immutable ownership resolved before a Library removal mutates app state."""

    history_identity: HistoryIdentity | None
    active_run_id: str | None
    queued_run_ids: frozenset[str]

    @property
    def execution_run_ids(self) -> frozenset[str]:
        if self.active_run_id is None:
            return self.queued_run_ids
        return self.queued_run_ids | {self.active_run_id}

    @property
    def execution_notice(self) -> str:
        if self.active_run_id is not None:
            return (
                " Its active run will be stopped and will not return to Forge recents."
            )
        if self.queued_run_ids:
            return " Its queued run will be removed before it starts."
        return ""


@dataclass(frozen=True)
class LibraryInvariantViolation:
    """Privacy-bounded evidence that canonical Library ownership was ambiguous."""

    code: str
    run_ids: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ()


@dataclass(frozen=True)
class LibraryProjection:
    """One deterministic, render-ready snapshot and its invariant receipt."""

    rows: tuple[dict[str, Any], ...]
    violations: tuple[LibraryInvariantViolation, ...]
    receipt: LibraryInvariantReceipt


@dataclass(frozen=True)
class LibraryInvariantReceipt:
    """Sensitive-content-free readback for runtime and packaged harness checks."""

    row_count: int
    canonical_run_ids: tuple[str, ...]
    projected_run_ids: tuple[str, ...]
    statuses: tuple[str, ...]
    violation_codes: tuple[str, ...]


class _ImmutableDict(dict[Any, Any]):
    """A deeply immutable dict that remains compatible with dict-based renderers."""

    @staticmethod
    def _immutable(*_args: Any, **_kwargs: Any) -> None:
        raise TypeError("Library projection values are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable  # type: ignore[assignment]
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable  # type: ignore[assignment]


class _ImmutableList(list[Any]):
    """A deeply immutable list that remains compatible with list-based renderers."""

    @staticmethod
    def _immutable(*_args: Any, **_kwargs: Any) -> None:
        raise TypeError("Library projection values are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    append = _immutable
    clear = _immutable
    extend = _immutable
    insert = _immutable
    pop = _immutable
    remove = _immutable
    reverse = _immutable
    sort = _immutable
    __iadd__ = _immutable  # type: ignore[assignment]
    __imul__ = _immutable  # type: ignore[assignment]


def _freeze_projection_value(value: Any) -> Any:
    """Recursively freeze one projected value without changing renderer type tests."""

    if isinstance(value, dict):
        frozen = _ImmutableDict()
        dict.update(
            frozen,
            {key: _freeze_projection_value(item) for key, item in value.items()},
        )
        return frozen
    if isinstance(value, list):
        frozen_list = _ImmutableList()
        list.extend(frozen_list, (_freeze_projection_value(item) for item in value))
        return frozen_list
    if isinstance(value, tuple):
        return tuple(_freeze_projection_value(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze_projection_value(item) for item in value)
    return value


def _legacy_history_owner(info: dict[str, Any]) -> str:
    """Return a stable compatibility owner for history written before run IDs."""

    identity = history_identity(info)
    digest = hashlib.sha256("\0".join(identity).encode("utf-8")).hexdigest()[:24]
    return f"history:{digest}"


def _clean_projection_row(info: dict[str, Any]) -> dict[str, Any]:
    row = dict(info)
    row.pop(ACTIVE_METADATA_RUN_ID_KEY, None)
    row.pop(QUEUED_METADATA_RUN_ID_KEY, None)
    row.pop(RUN_STATUS_KEY, None)
    for key in _PROJECTION_DECORATION_KEYS:
        row.pop(key, None)
    return row


class LibraryProjectionOwner:
    """Derive Library rows from canonical run, history, and preview owners.

    This owner never accepts a rendered row as authority.  Every reconciliation
    starts from the supplied canonical sources and is therefore idempotent.
    """

    def __init__(self, *, diagnostic: Any = None) -> None:
        self._diagnostic = diagnostic or (lambda _message: None)
        self._preview_items: dict[str, list[dict[str, Any]]] = {}
        self._run_phases: dict[str, str] = {}
        self._snapshot = LibraryProjection(
            rows=(),
            violations=(),
            receipt=LibraryInvariantReceipt(0, (), (), (), ()),
        )

    @property
    def snapshot(self) -> LibraryProjection:
        """Return the current immutable snapshot; callers cannot mutate owner state."""

        return self._snapshot

    def record_preview(
        self, preview_run_id: str, items: Iterable[dict[str, Any]]
    ) -> None:
        owner = str(preview_run_id).strip()
        if not owner:
            return
        self._preview_items[owner] = [dict(item) for item in items]

    def remove_preview(self, preview_run_id: str) -> None:
        self._preview_items.pop(str(preview_run_id).strip(), None)

    def claim_preview(self, preview_run_id: str) -> list[dict[str, Any]]:
        return self._preview_items.pop(str(preview_run_id).strip(), [])

    def observe_phase(self, run_id: str, status: str) -> bool:
        """Record one transient run phase and report whether it changed."""

        owner = str(run_id).strip()
        phase = str(status).strip()
        if not owner or phase not in TRANSIENT_LIBRARY_STATUSES:
            return False
        if self._run_phases.get(owner) == phase:
            return False
        self._run_phases[owner] = phase
        return True

    def forget_run(self, run_id: str) -> None:
        self._run_phases.pop(str(run_id).strip(), None)

    def reconcile(
        self,
        *,
        history_items: Sequence[dict[str, Any]],
        active_job: DownloadJob | None,
        queued_jobs: Sequence[DownloadJob],
        terminal_jobs: Sequence[DownloadJob],
        suppressed_run_ids: AbstractSet[str] = frozenset(),
        annotations: Mapping[str, LibraryAnnotation] | None = None,
    ) -> LibraryProjection:
        """Return one row per canonical owner using deterministic precedence."""

        violations: list[LibraryInvariantViolation] = []
        suppressed = {str(value) for value in suppressed_run_ids if str(value)}
        run_sources: dict[str, tuple[str, DownloadJob]] = {}

        def add_run_source(kind: str, job: DownloadJob) -> None:
            run_id = str(job.run_id).strip()
            if not run_id or run_id in suppressed:
                return
            existing = run_sources.get(run_id)
            if existing is not None:
                statuses = (existing[0], kind)
                violations.append(
                    LibraryInvariantViolation(
                        code="duplicate_canonical_run_owner",
                        run_ids=(run_id,),
                        statuses=statuses,
                    )
                )
                # Terminal is the safest visible state; active outranks queued.
                rank = {"queued": 1, "active": 2, "terminal": 3}
                if rank[kind] <= rank[existing[0]]:
                    return
            run_sources[run_id] = (kind, job)

        for job in queued_jobs:
            add_run_source("queued", job)
        if active_job is not None and not str(active_job.terminal_status or "").strip():
            add_run_source("active", active_job)
        for job in terminal_jobs:
            add_run_source("terminal", job)

        history_rows: list[dict[str, Any]] = []
        committed_run_ids: set[str] = set()
        seen_history_owners: set[str] = set()
        for source in history_items:
            row = _clean_projection_row(source)
            run_id = str(row.get("vodforge_run_id") or "").strip()
            owner = _legacy_history_owner(row)
            output_path = str(row.get("vodforge_output_path") or "").strip()
            if output_path:
                owner = f"history-path:{output_path}"
            if owner in seen_history_owners:
                violations.append(
                    LibraryInvariantViolation(code="duplicate_history_owner")
                )
                continue
            seen_history_owners.add(owner)
            if run_id:
                committed_run_ids.add(run_id)
            row[PROJECTION_OWNER_KEY] = owner
            row[PROJECTION_OWNER_KIND_KEY] = "history"
            history_rows.append(row)

        live_rows: list[dict[str, Any]] = []
        terminal_rows: list[dict[str, Any]] = []
        ordered_sources: list[tuple[str, DownloadJob]] = []
        if active_job is not None and active_job.run_id in run_sources:
            ordered_sources.append(run_sources[active_job.run_id])
        ordered_sources.extend(
            run_sources[job.run_id]
            for job in queued_jobs
            if job.run_id in run_sources
            and run_sources[job.run_id] not in ordered_sources
        )
        ordered_sources.extend(
            run_sources[job.run_id]
            for job in terminal_jobs
            if job.run_id in run_sources
            and run_sources[job.run_id] not in ordered_sources
        )
        for kind, job in ordered_sources:
            run_id = str(job.run_id)
            if run_id in committed_run_ids:
                continue
            row = _clean_projection_row(job.preview_info or {})
            row.setdefault("webpage_url", job.url)
            row.setdefault("original_url", job.url)
            row["vodforge_output_type"] = job.output_type.value
            row = annotate_job_metadata(job, row)
            row[PROJECTION_OWNER_KEY] = f"run:{run_id}"
            row[PROJECTION_OWNER_KIND_KEY] = kind
            if kind == "terminal":
                status = str(
                    job.terminal_status
                    or row.get("vodforge_terminal_status")
                    or "Failed"
                )
                message = str(
                    job.terminal_message or row.get("vodforge_terminal_message") or ""
                )
                row.setdefault(
                    "title",
                    "Interrupted VODForge run"
                    if status == "Failed"
                    else "Preparing video run",
                )
                row["vodforge_terminal_status"] = status
                row["vodforge_terminal_message"] = message
                row["vodforge_terminal_run_id"] = run_id
                row.pop("vodforge_preview_complete", None)
                row.pop("vodforge_preview_run_id", None)
                terminal_rows.append(row)
                self._run_phases.pop(run_id, None)
            else:
                status = (
                    "Queued"
                    if kind == "queued"
                    else self._run_phases.get(run_id, "Preparing")
                )
                row.setdefault("title", f"{status} video run")
                row[
                    QUEUED_METADATA_RUN_ID_KEY
                    if kind == "queued"
                    else ACTIVE_METADATA_RUN_ID_KEY
                ] = run_id
                row[RUN_STATUS_KEY] = status
                live_rows.append(row)

        preview_rows: list[dict[str, Any]] = []
        for preview_run_id, items in self._preview_items.items():
            for item_index, source in enumerate(items):
                row = _clean_projection_row(source)
                row["vodforge_preview_complete"] = True
                row["vodforge_preview_run_id"] = preview_run_id
                row[PROJECTION_OWNER_KEY] = f"preview:{preview_run_id}:{item_index}"
                row[PROJECTION_OWNER_KIND_KEY] = "preview"
                preview_rows.append(row)

        mutable_rows = [*live_rows, *terminal_rows, *preview_rows, *history_rows]
        annotation_snapshot = annotations or {}
        for row in mutable_rows:
            run_id = str(
                row.get("vodforge_run_id")
                or row.get("vodforge_terminal_run_id")
                or row.get(ACTIVE_METADATA_RUN_ID_KEY)
                or row.get(QUEUED_METADATA_RUN_ID_KEY)
                or ""
            ).strip()
            annotation_owner = (
                f"run:{run_id}" if run_id else str(row.get(PROJECTION_OWNER_KEY) or "")
            )
            row[ANNOTATION_OWNER_KEY] = annotation_owner
            annotation = annotation_snapshot.get(annotation_owner)
            if annotation is None:
                continue
            row["vodforge_user_note"] = annotation.note
            row["vodforge_user_tags"] = list(annotation.tags)
            row["vodforge_user_category"] = annotation.category
        rows = tuple(_freeze_projection_value(row) for row in mutable_rows)
        owner_keys = [str(row.get(PROJECTION_OWNER_KEY) or "") for row in rows]
        if len(owner_keys) != len(set(owner_keys)):
            violations.append(
                LibraryInvariantViolation(code="duplicate_projection_owner")
            )

        visible_run_ids = [
            str(
                row.get("vodforge_terminal_run_id")
                or row.get(ACTIVE_METADATA_RUN_ID_KEY)
                or row.get(QUEUED_METADATA_RUN_ID_KEY)
                or ""
            )
            for row in rows
            if row.get(PROJECTION_OWNER_KIND_KEY) in {"active", "queued", "terminal"}
        ]
        if len(visible_run_ids) != len(set(visible_run_ids)):
            violations.append(
                LibraryInvariantViolation(
                    code="duplicate_projected_run_id",
                    run_ids=tuple(value for value in visible_run_ids if value),
                )
            )

        projected_run_ids = {
            str(
                row.get("vodforge_run_id")
                or row.get("vodforge_terminal_run_id")
                or row.get(ACTIVE_METADATA_RUN_ID_KEY)
                or row.get(QUEUED_METADATA_RUN_ID_KEY)
                or ""
            )
            for row in rows
            if str(
                row.get("vodforge_run_id")
                or row.get("vodforge_terminal_run_id")
                or row.get(ACTIVE_METADATA_RUN_ID_KEY)
                or row.get(QUEUED_METADATA_RUN_ID_KEY)
                or ""
            )
        }
        expected_run_ids = set(run_sources) | committed_run_ids
        missing_run_ids = sorted(expected_run_ids - projected_run_ids - suppressed)
        if missing_run_ids:
            violations.append(
                LibraryInvariantViolation(
                    code="canonical_visible_run_missing",
                    run_ids=tuple(missing_run_ids),
                )
            )

        canonical_transient_ids = {
            run_id for run_id, (kind, _job) in run_sources.items() if kind != "terminal"
        }
        canonical_terminal_ids = {
            run_id for run_id, (kind, _job) in run_sources.items() if kind == "terminal"
        }
        for row in rows:
            status = str(
                row.get(RUN_STATUS_KEY)
                or row.get("vodforge_terminal_status")
                or "Completed"
                if row.get(PROJECTION_OWNER_KIND_KEY) == "history"
                else row.get(RUN_STATUS_KEY)
                or row.get("vodforge_terminal_status")
                or "Preview complete"
            )
            run_id = str(
                row.get("vodforge_terminal_run_id")
                or row.get(ACTIVE_METADATA_RUN_ID_KEY)
                or row.get(QUEUED_METADATA_RUN_ID_KEY)
                or ""
            )
            if (
                status in TRANSIENT_LIBRARY_STATUSES
                and run_id not in canonical_transient_ids
            ):
                violations.append(
                    LibraryInvariantViolation(
                        code="transient_projection_without_owner",
                        run_ids=(run_id,) if run_id else (),
                        statuses=(status,),
                    )
                )
            if (
                status in TERMINAL_LIBRARY_STATUSES
                and row.get(PROJECTION_OWNER_KIND_KEY) == "terminal"
                and run_id not in canonical_terminal_ids
            ):
                violations.append(
                    LibraryInvariantViolation(
                        code="terminal_projection_without_durable_backing",
                        run_ids=(run_id,) if run_id else (),
                        statuses=(status,),
                    )
                )

        for violation in violations:
            self._diagnostic(
                "library_invariant_violation "
                f"code={violation.code} run_ids={','.join(violation.run_ids)} "
                f"statuses={','.join(violation.statuses)}"
            )
        receipt = LibraryInvariantReceipt(
            row_count=len(rows),
            canonical_run_ids=tuple(sorted(expected_run_ids)),
            projected_run_ids=tuple(sorted(projected_run_ids)),
            statuses=tuple(
                str(
                    row.get(RUN_STATUS_KEY)
                    or row.get("vodforge_terminal_status")
                    or (
                        "Completed"
                        if row.get(PROJECTION_OWNER_KIND_KEY) == "history"
                        else "Preview complete"
                    )
                )
                for row in rows
            ),
            violation_codes=tuple(violation.code for violation in violations),
        )
        self._snapshot = LibraryProjection(
            rows=rows,
            violations=tuple(violations),
            receipt=receipt,
        )
        return self._snapshot


def _library_execution_owner_run_id(info: dict[str, Any]) -> str | None:
    """Return an exact execution owner, never a same-media historical lookalike."""
    persisted_run_id = str(info.get("vodforge_run_id") or "").strip()
    if persisted_run_id:
        return persisted_run_id
    if history_output_dir(info) is not None:
        return None
    active_run_id = str(info.get(ACTIVE_METADATA_RUN_ID_KEY) or "").strip()
    queued_run_id = str(info.get(QUEUED_METADATA_RUN_ID_KEY) or "").strip()
    return active_run_id or queued_run_id or None


def resolve_library_removal_plan(
    info: dict[str, Any],
    *,
    active_job: DownloadJob | None,
    pending_jobs: Iterable[DownloadJob],
) -> LibraryRemovalPlan:
    """Resolve durable and live owners without changing Library or Forge state."""
    saved = history_output_dir(info)
    item_history_identity = history_identity(info) if saved is not None else None
    owner_run_id = _library_execution_owner_run_id(info)
    active_run_id = (
        active_job.run_id
        if active_job is not None and active_job.run_id == owner_run_id
        else None
    )
    queued_run_ids = frozenset(
        job.run_id for job in pending_jobs if job.run_id == owner_run_id
    )
    return LibraryRemovalPlan(
        history_identity=item_history_identity,
        active_run_id=active_run_id,
        queued_run_ids=queued_run_ids,
    )


def persisted_run_deck_records(
    metadata_items: Sequence[dict[str, Any]],
    *,
    active_metadata_keys: AbstractSet[MetadataRunKey],
    terminal_metadata_keys: AbstractSet[MetadataRunKey],
    active_history_identities: AbstractSet[HistoryIdentity],
    completed_jobs: Iterable[DownloadJob],
    active_run_ids: AbstractSet[str] = frozenset(),
    terminal_run_ids: AbstractSet[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Project saved and preview Library rows into run-deck records."""
    completed_jobs_by_identity: dict[HistoryIdentity, DownloadJob] = {}
    for owner_job in completed_jobs:
        for identity in owner_job.history_identities:
            # Callers keep completed jobs newest-first. An older repeated run
            # must not replace the first canonical owner.
            completed_jobs_by_identity.setdefault(identity, owner_job)

    records: list[dict[str, Any]] = []
    for index, item in enumerate(metadata_items):
        item_key = metadata_run_key(item)
        saved = history_output_dir(item)
        item_run_id = str(
            item.get(ACTIVE_METADATA_RUN_ID_KEY)
            or item.get("vodforge_terminal_run_id")
            or ""
        )
        item_history_identity = history_identity(item) if saved is not None else None
        if saved is None and (
            item_run_id in active_run_ids | terminal_run_ids
            or (
                not item_run_id
                and item_key is not None
                and (
                    item_key in active_metadata_keys
                    or item_key in terminal_metadata_keys
                )
            )
        ):
            continue
        if (
            item_history_identity is not None
            and item_history_identity in active_history_identities
        ):
            continue
        if saved is None and not is_metadata_preview(item):
            continue

        output_type = metadata_output_type(item)
        completed_owner = (
            completed_jobs_by_identity.get(item_history_identity)
            if item_history_identity is not None
            else None
        )
        records.append(
            {
                "title": str(item.get("title") or item.get("id") or "Untitled media"),
                "detail": str(
                    item.get("uploader")
                    or item.get("channel")
                    or format_duration(item.get("duration"))
                ),
                "status": (
                    f"{'Completed' if saved is not None else 'Preview complete'}"
                    f"  •  {output_type.value}"
                ),
                "progress": 100,
                "kind": "completed" if saved is not None else "preview",
                "metadata_index": index,
                "output_type": output_type.value,
                "run_id": (
                    completed_owner.run_id
                    if completed_owner is not None
                    else str(item.get("vodforge_preview_run_id") or f"history:{index}")
                ),
                "job": completed_owner,
                "preview_thumbnail_image": (
                    completed_owner.preview_thumbnail_image
                    if completed_owner is not None
                    else None
                ),
            }
        )
    return records
