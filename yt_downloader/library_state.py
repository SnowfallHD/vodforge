from __future__ import annotations

import math
from collections.abc import Iterable
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Any

from .history import history_identity, history_output_dir, history_output_type
from .models import DownloadJob, OutputType

ACTIVE_METADATA_RUN_ID_KEY = "vodforge_active_run_id"
_ACTIVE_METADATA_STALE_KEYS = (
    "vodforge_preview_complete",
    "vodforge_preview_run_id",
    "vodforge_terminal_status",
    "vodforge_terminal_message",
    "vodforge_terminal_run_id",
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


def is_metadata_preview(info: dict[str, Any] | None) -> bool:
    """Return true only for a metadata-only item, never a terminal or saved run."""
    return bool(
        isinstance(info, dict)
        and info.get("vodforge_preview_complete") is True
        and history_output_dir(info) is None
        and not str(info.get("vodforge_terminal_status") or "").strip()
    )


def claim_active_metadata_row(
    row: dict[str, Any],
    incoming: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    """Give one ephemeral Library row to an exact active run authority."""
    row.update(incoming)
    for key in _ACTIVE_METADATA_STALE_KEYS:
        row.pop(key, None)
    row[ACTIVE_METADATA_RUN_ID_KEY] = str(run_id)
    return row


@dataclass(frozen=True)
class LibraryMetadataMerge:
    """One immutable transition receipt around intentionally mutable row objects."""

    items: list[dict[str, Any]]
    incoming_items: list[dict[str, Any]]


def merge_library_metadata_items(
    existing_items: list[dict[str, Any]],
    incoming_items: Iterable[dict[str, Any]],
    *,
    active_run_id: str | None = None,
    preview_complete: bool = False,
    preview_run_id: str = "",
) -> LibraryMetadataMerge:
    """Merge provider metadata while preserving Library row and list authority."""
    normalized_incoming = [dict(item) for item in incoming_items]
    new_items: list[dict[str, Any]] = []
    for source_item in normalized_incoming:
        incoming = source_item
        if active_run_id is not None:
            incoming = claim_active_metadata_row({}, incoming, active_run_id)
        elif preview_complete:
            incoming["vodforge_preview_complete"] = True
            if preview_run_id:
                incoming["vodforge_preview_run_id"] = preview_run_id
        else:
            incoming.pop("vodforge_preview_complete", None)
            incoming.pop("vodforge_preview_run_id", None)

        video_id = str(incoming.get("id") or "")
        output_type = metadata_output_type(incoming)
        matching = next(
            (
                item
                for item in [*new_items, *existing_items]
                if video_id
                and str(item.get("id") or "") == video_id
                and metadata_output_type(item) == output_type
                and not (
                    active_run_id is not None and history_output_dir(item) is not None
                )
            ),
            None,
        )
        if matching is None:
            new_items.append(incoming)
            continue
        if active_run_id is not None:
            claim_active_metadata_row(matching, incoming, active_run_id)
        else:
            matching.update(incoming)
        if not preview_complete and active_run_id is None:
            matching.pop("vodforge_preview_complete", None)
            matching.pop("vodforge_preview_run_id", None)

    merged_items = [*new_items, *existing_items] if new_items else existing_items
    return LibraryMetadataMerge(
        items=merged_items,
        incoming_items=normalized_incoming,
    )


def persisted_run_deck_records(
    metadata_items: list[dict[str, Any]],
    *,
    active_metadata_keys: AbstractSet[MetadataRunKey],
    terminal_metadata_keys: AbstractSet[MetadataRunKey],
    active_history_identities: AbstractSet[HistoryIdentity],
    completed_jobs: Iterable[DownloadJob],
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
        item_history_identity = history_identity(item) if saved is not None else None
        if (
            saved is None
            and item_key is not None
            and (item_key in active_metadata_keys or item_key in terminal_metadata_keys)
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
