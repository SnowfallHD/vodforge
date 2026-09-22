from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePath
from threading import Event
from typing import Any, Literal

from .archive_paths import ArchivePath, RootMapping, map_archive_path

RelinkState = Literal[
    "pending",
    "ready",
    "unchanged",
    "outside_mapping",
    "ambiguous_mapping",
    "invalid_destination",
    "invalid_record",
    "choose_file",
    "collision",
    "missing",
    "unavailable",
    "foreign_platform",
    "identity_mismatch",
    "cancelled",
    "timed_out",
    "stale",
]
MAX_RELINK_ITEMS = 5000
MAX_ROOT_MAPPINGS = 64
COMPANION_NAMES = (
    "metadata.json",
    "thumbnail.jpg",
    "thumbnail.jpeg",
    "thumbnail.png",
    "thumbnail.webp",
)


def record_fingerprint(record: Mapping[str, Any]) -> str:
    """Private optimistic-concurrency token; never emit to diagnostics."""
    return hashlib.sha256(
        json.dumps(
            dict(record),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def recorded_artifact(record: Mapping[str, Any]) -> ArchivePath | None:
    value = record.get("vodforge_output_path")
    if not value:
        summary = record.get("vodforge_encoding_summary")
        output = summary.get("output") if isinstance(summary, Mapping) else None
        value = output.get("Output file path") if isinstance(output, Mapping) else None
    if not isinstance(value, str) or not value:
        return None
    path = ArchivePath.parse(value)
    directory = ArchivePath.parse(str(record.get("vodforge_output_dir") or ""))
    if path.parent.key != directory.key or path.parent == path:
        raise ValueError("Saved artifact is outside its recorded export folder")
    return path


@dataclass(frozen=True, slots=True)
class RelinkEntry:
    index: int
    fingerprint: str
    source: ArchivePath | None
    destination: ArchivePath | None
    mapping: RootMapping | None
    state: RelinkState
    explicit_file: bool = False
    # Private, ephemeral OS evidence. Never serialized as product diagnostics.
    stamp: tuple[int, int, int, int] | None = None
    companions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RelinkPreview:
    entries: tuple[RelinkEntry, ...]
    snapshot: tuple[str, ...]
    elapsed_ms: int = 0

    @property
    def counts(self) -> dict[str, int]:
        return dict(Counter(entry.state for entry in self.entries))

    def diagnostic(self, phase: str) -> dict[str, Any]:
        if phase not in {"preview", "verify", "apply", "cancel"}:
            raise ValueError("Unknown relink phase")
        return {
            "phase": phase,
            "items": len(self.entries),
            "states": self.counts,
            "elapsed_ms": self.elapsed_ms,
        }


def preview_relink(
    records: Sequence[Mapping[str, Any]],
    mappings: Sequence[RootMapping] = (),
    *,
    selected: Sequence[int] | None = None,
    exact_files: Mapping[int, str] | None = None,
) -> RelinkPreview:
    """Build a metadata-only proposal. No filesystem calls and no side effects."""
    if len(records) > MAX_RELINK_ITEMS or len(mappings) > MAX_ROOT_MAPPINGS:
        raise ValueError("Relink scope exceeds the supported archive limit")
    indices = (
        list(range(len(records))) if selected is None else list(dict.fromkeys(selected))
    )
    if any(
        isinstance(index, bool) or index < 0 or index >= len(records)
        for index in indices
    ):
        raise ValueError("Relink selection is stale")
    exact_files = exact_files or {}
    if any(index not in indices for index in exact_files):
        raise ValueError("An exact destination is outside the selected scope")
    fingerprints = tuple(record_fingerprint(record) for record in records)
    entries: list[RelinkEntry] = []
    for index in indices:
        record = records[index]
        source = destination = mapping = None
        state: RelinkState = "invalid_record"
        try:
            source = recorded_artifact(record)
            if index in exact_files:
                destination = ArchivePath.parse(exact_files[index])
                state = "pending"
            elif source is None:
                state = "choose_file"
            else:
                destination, mapping, mapped = map_archive_path(source, tuple(mappings))
                state = "pending" if mapped == "mapped" else mapped  # type: ignore[assignment]
            if (
                destination is not None
                and source is not None
                and destination.key == source.key
            ):
                state = "unchanged"
        except (ValueError, TypeError):
            state = "invalid_record" if destination is None else "invalid_destination"
        entries.append(
            RelinkEntry(
                index,
                fingerprints[index],
                source,
                destination,
                mapping,
                state,
                explicit_file=index in exact_files,
            )
        )
    # Include unselected and unresolved records: a proposed destination must never
    # silently displace any existing history item, even when that file is offline.
    proposed = {entry.index: entry for entry in entries}
    destinations: dict[tuple[str, ...], list[int]] = {}
    for index, record in enumerate(records):
        entry = proposed.get(index)
        try:
            # Selected entries already validated this source in the same
            # metadata-only snapshot. Reuse it for collision detection; never
            # cache across proposals or skip unselected/worker validation.
            path = (
                (entry.destination if entry.state == "pending" else entry.source)
                if entry is not None
                else recorded_artifact(record)
            )
        except (ValueError, TypeError):
            path = None
        if path is not None:
            destinations.setdefault(path.key, []).append(index)
    colliding = {
        index
        for indices in destinations.values()
        if len(indices) > 1
        for index in indices
    }
    entries = [
        replace(entry, state="collision")
        if entry.index in colliding and entry.state == "pending"
        else entry
        for entry in entries
    ]
    return RelinkPreview(tuple(entries), fingerprints)


@dataclass(frozen=True, slots=True)
class FileObservation:
    state: RelinkState
    stamp: tuple[int, int, int, int] | None = None
    companions: tuple[str, ...] = ()


def observe_destination(
    path: ArchivePath,
    record: Mapping[str, Any],
    *,
    explicit_file: bool = False,
) -> FileObservation:
    """Worker-only exact-path checks. No recursion, directory listing or hashing."""
    if (path.style == "windows") != (os.name == "nt"):
        return FileObservation("foreign_platform")
    native = Path(str(path))
    try:
        observed = native.stat()
        if not stat.S_ISREG(observed.st_mode) or observed.st_size <= 0:
            return FileObservation("missing")
        source = recorded_artifact(record)
        # A relink cannot silently turn a saved MP3 into a different media format.
        expected_suffix = PurePath(source.name).suffix.casefold() if source else ""
        if not expected_suffix:
            # Legacy rows may retain the output format without an exact filename.
            # Use only recorded evidence: history_output_type defaults unknown
            # records to MP4, which would invent a format for this identity check.
            output_type = (
                str(record.get("vodforge_output_type") or "").strip().casefold()
            )
            expected_suffix = {"mp4": ".mp4", "mp3": ".mp3"}.get(output_type, "")
        # Original audio and unknown formats have no single inferred extension.
        # Without a canonical suffix, explicit selection supplies the file;
        # optional companion checks below still apply, with no decoding claim.
        actual_suffix = native.suffix.casefold()
        if expected_suffix and expected_suffix != actual_suffix:
            return FileObservation("identity_mismatch")
        companion_names: list[str] = []
        for name in COMPANION_NAMES:
            companion = native.parent / name
            try:
                companion_stat = companion.stat()
            except FileNotFoundError:
                continue
            if stat.S_ISREG(companion_stat.st_mode) and companion_stat.st_size > 0:
                companion_names.append(name)
                if name == "metadata.json":
                    if companion_stat.st_size > 1024 * 1024:
                        return FileObservation("identity_mismatch")
                    # Bounded read even if the file grows after stat.
                    with companion.open("rb") as stream:
                        raw = stream.read(1024 * 1024 + 1)
                    metadata = json.loads(raw)
                    if not isinstance(metadata, dict):
                        return FileObservation("identity_mismatch")
                    for key in ("id", "vodforge_output_type"):
                        if (
                            record.get(key)
                            and metadata.get(key)
                            and record[key] != metadata[key]
                        ):
                            return FileObservation("identity_mismatch")
        # Existence is evidence of the exact proposed file, not a content/hash
        # identity claim. The UI must show the mapping before user acceptance.
        return FileObservation(
            "ready",
            (observed.st_dev, observed.st_ino, observed.st_size, observed.st_mtime_ns),
            tuple(companion_names),
        )
    except FileNotFoundError:
        kind, root = path.storage
        if kind != "local":
            try:
                if not Path(str(root)).is_dir():
                    return FileObservation("unavailable")
            except OSError:
                return FileObservation("unavailable")
        return FileObservation("missing")
    except (OSError, ValueError, UnicodeError):
        return FileObservation("unavailable")


def _existing_identity(path: ArchivePath) -> tuple[int, int] | None:
    """Compare only recorded exact peer files, without enumerating directories."""
    if (path.style == "windows") != (os.name == "nt"):
        return None
    try:
        observed = Path(str(path)).stat()
    except OSError:
        return None
    if stat.S_ISREG(observed.st_mode) and observed.st_ino:
        return observed.st_dev, observed.st_ino
    return None


def verify_relink(
    preview: RelinkPreview,
    records: Sequence[Mapping[str, Any]],
    *,
    cancelled: Event | None = None,
    budget_seconds: float = 15.0,
    observe: Callable[..., FileObservation] = observe_destination,
    clock: Callable[[], float] = time.monotonic,
    peer_identity: Callable[[ArchivePath], tuple[int, int] | None] = _existing_identity,
) -> RelinkPreview:
    """Run off the UI thread. Bounds exact checks and rejects stale/cancelled work.

    OS filesystem calls can block beyond the budget. The UI owner must keep only
    one worker and retire its generation on timeout; it must never wait for it.
    """
    started = clock()
    if tuple(record_fingerprint(record) for record in records) != preview.snapshot:
        return replace(
            preview,
            entries=tuple(
                replace(entry, state="stale", stamp=None) for entry in preview.entries
            ),
        )
    result: list[RelinkEntry] = []
    interrupted: RelinkState | None = None
    for entry in preview.entries:
        if cancelled is not None and cancelled.is_set():
            interrupted = "cancelled"
        elif clock() - started >= budget_seconds:
            interrupted = "timed_out"
        if interrupted is not None:
            result.append(replace(entry, state=interrupted, stamp=None))
        elif entry.state != "pending" or entry.destination is None:
            result.append(entry)
        else:
            observation = observe(
                entry.destination,
                records[entry.index],
                explicit_file=entry.explicit_file,
            )
            result.append(
                replace(
                    entry,
                    state=observation.state,
                    stamp=observation.stamp,
                    companions=observation.companions,
                )
            )
    if cancelled is not None and cancelled.is_set():
        interrupted = "cancelled"
    elif clock() - started >= budget_seconds:
        interrupted = "timed_out"
    if interrupted:
        result = [replace(entry, state=interrupted, stamp=None) for entry in result]
    aliases: dict[tuple[int, int], list[int]] = {}
    for entry in result:
        if entry.state == "ready" and entry.stamp and entry.stamp[1]:
            aliases.setdefault(entry.stamp[:2], []).append(entry.index)
    # Retained peers include unselected and unresolved rows. Different spellings
    # (symlinks, hardlinks, case aliases) must not silently merge their identities.
    ready_indices = {entry.index for entry in result if entry.state == "ready"}
    if aliases:
        for index, record in enumerate(records):
            if index in ready_indices:
                continue
            if cancelled is not None and cancelled.is_set():
                interrupted = "cancelled"
                break
            if clock() - started >= budget_seconds:
                interrupted = "timed_out"
                break
            try:
                path = recorded_artifact(record)
            except (ValueError, TypeError):
                continue
            identity = peer_identity(path) if path is not None else None
            if identity in aliases:
                aliases[identity].append(index)
    if cancelled is not None and cancelled.is_set():
        interrupted = "cancelled"
    elif clock() - started >= budget_seconds:
        interrupted = "timed_out"
    if interrupted:
        result = [replace(entry, state=interrupted, stamp=None) for entry in result]
    colliding = {
        index for indices in aliases.values() if len(indices) > 1 for index in indices
    }
    result = [
        replace(entry, state="collision", stamp=None)
        if entry.state == "ready" and entry.index in colliding
        else entry
        for entry in result
    ]
    return replace(
        preview,
        entries=tuple(result),
        elapsed_ms=max(0, round((clock() - started) * 1000)),
    )


class RelinkConflict(ValueError):
    """The current archive no longer matches an accepted preview."""


class RelinkCancelled(RelinkConflict):
    """Cancellation was acknowledged before the durable history write."""


def relocated_records(
    preview: RelinkPreview,
    current: Sequence[Mapping[str, Any]],
    *,
    accepted: Sequence[int],
) -> list[dict[str, Any]]:
    """Pure final proposal; caller revalidates stamps and atomically saves it.

    Never removes records or writes, moves, repairs or renames media/companions.
    Original export intent remains historical; location has a separate field.
    """
    if tuple(record_fingerprint(record) for record in current) != preview.snapshot:
        raise RelinkConflict("Archive changed; review the locations again")
    requested = set(accepted)
    ready = {entry.index: entry for entry in preview.entries if entry.state == "ready"}
    if not requested or requested - ready.keys():
        raise RelinkConflict("Only verified locations can be accepted")
    prospective = copy.deepcopy([dict(record) for record in current])
    for index in requested:
        entry = ready[index]
        if entry.destination is None or entry.stamp is None:
            raise RelinkConflict("Destination verification is incomplete")
        record = prospective[index]
        from .history import history_annotation_owner, history_archive_owner
        from .playback_progress import progress_key

        previous_annotation_owner = history_annotation_owner(record)
        record.setdefault("vodforge_progress_key", progress_key(record))
        record.setdefault(
            "vodforge_archive_id",
            hashlib.sha256(history_archive_owner(record).encode("utf-8")).hexdigest(),
        )
        record.setdefault(
            "vodforge_archive_annotation_owner", previous_annotation_owner
        )
        record["vodforge_output_dir"] = str(entry.destination.parent)
        record["vodforge_output_path"] = str(entry.destination)
        summary = record.get("vodforge_encoding_summary")
        if isinstance(summary, dict) and isinstance(summary.get("output"), dict):
            summary["output"]["Output file path"] = str(entry.destination)
        # A bounded latest location receipt, not an unbounded path history.
        record["vodforge_relinked"] = True
    return prospective


def commit_relink(
    preview: RelinkPreview,
    current: Sequence[Mapping[str, Any]],
    history_path: Path,
    *,
    accepted: Sequence[int],
    cancelled: Event | None = None,
) -> list[dict[str, Any]]:
    """Recheck accepted destinations, then persist through the history authority.

    The UI serializes its canonical history writers around this worker operation.
    Only a successful atomic save returns a new in-memory projection.
    """
    from .history import save_history

    # Validate ownership before any filesystem effects or verification.
    relocated_records(preview, current, accepted=accepted)
    accepted_indices = set(accepted)
    pending = replace(
        preview,
        entries=tuple(
            replace(entry, state="pending", stamp=None)
            if entry.index in accepted_indices
            else entry
            for entry in preview.entries
        ),
    )
    fresh = verify_relink(pending, current, cancelled=cancelled)
    if cancelled is not None and cancelled.is_set():
        raise RelinkCancelled("Relink cancelled")
    old = {entry.index: entry for entry in preview.entries}
    for entry in fresh.entries:
        if entry.index in accepted_indices and (
            entry.state != "ready" or entry.stamp != old[entry.index].stamp
        ):
            raise RelinkConflict("Destination changed after review")
    if cancelled is not None and cancelled.is_set():
        raise RelinkCancelled("Relink cancelled")
    prospective = relocated_records(fresh, current, accepted=accepted)
    save_history(history_path, prospective)
    return prospective
