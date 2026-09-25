"""Exact-file operation planning, independent of Tk and Library projections.

Plans are private, short-lived evidence. The completed-output history remains the
only record authority. Every commit must repeat this preflight against that
authority; display presence and guessed legacy filenames are never destructive
evidence.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
import unicodedata
import uuid
from collections import Counter, OrderedDict
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event, Lock
from typing import Any, Literal

from .archive_paths import ArchivePath
from .archive_relink import (
    COMPANION_NAMES,
    RelinkEntry,
    RelinkPreview,
    record_fingerprint,
    recorded_artifact,
    relocated_records,
)
from .history import MAX_HISTORY_ITEMS, HistoryError, history_archive_owner
from .platform_services import file_change_time_ns
from .safe_output import (
    cleanup_private_staging_directory,
    commit_file_beneath,
    create_private_staging_directory,
)
from .safe_output import (
    is_symlink_or_reparse as _redirect,
)

FileState = Literal[
    "ready", "missing", "unavailable", "ambiguous", "changed", "cancelled", "conflict"
]
Stamp = tuple[int, int, int, int, int]

MAX_RECEIPT_BYTES = 4 * 1024 * 1024
MAX_RECEIPT_TOTAL_BYTES = 16 * 1024 * 1024
_RECEIPT_CACHE: OrderedDict[Path, tuple[Stamp, dict[str, Any]]] = OrderedDict()
_RECEIPT_CACHE_LOCK = Lock()


class FileOperationCapacityError(ValueError):
    """No additional receipt capacity; UI offers smaller selection or restart."""


def _receipt_inventory(directory: Path) -> list[ArtifactEvidence]:
    try:
        directory.lstat()
    except FileNotFoundError:
        return []
    directory_evidence(directory)
    paths = tuple(directory.glob("*.json"))
    if len(paths) > MAX_HISTORY_ITEMS:
        raise ValueError("File-operation receipt storage needs review")
    evidence = [_regular_evidence(path) for path in paths]
    if any(item.stamp[2] > MAX_RECEIPT_BYTES for item in evidence):
        raise ValueError("File-operation receipt is oversized")
    if sum(item.stamp[2] for item in evidence) > MAX_RECEIPT_TOTAL_BYTES:
        raise ValueError("File-operation receipt storage needs review")
    return evidence


@dataclass(frozen=True, slots=True)
class ArtifactEvidence:
    path: Path
    stamp: Stamp


@dataclass(frozen=True, slots=True)
class FileOperationItem:
    owner: str
    fingerprint: str
    source: Path | None
    state: FileState
    artifacts: tuple[ArtifactEvidence, ...] = ()
    # Root-to-parent identity proofs detect a redirected ancestor on recheck.
    ancestors: tuple[tuple[Path, int, int], ...] = ()


@dataclass(frozen=True, slots=True)
class FileOperationPlan:
    snapshot: tuple[str, ...]
    items: tuple[FileOperationItem, ...]

    @property
    def counts(self) -> dict[str, int]:
        return dict(Counter(item.state for item in self.items))


def file_stamp(value: os.stat_result) -> Stamp:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _descriptor_stamp(descriptor: int) -> Stamp:
    observed = os.fstat(descriptor)
    return (*file_stamp(observed)[:4], file_change_time_ns(descriptor, observed))


def directory_evidence(path: Path) -> tuple[tuple[Path, int, int], ...]:
    """Refuse symlinks/reparse points throughout an absolute directory path."""
    if not path.is_absolute():
        raise ValueError("An absolute folder is required")
    result = []
    for directory in (*reversed(path.parents), path):
        value = directory.lstat()
        if _redirect(value) or not stat.S_ISDIR(value.st_mode):
            raise ValueError("A folder was redirected")
        result.append((directory, value.st_dev, value.st_ino))
    # Stat alone can succeed on a directory whose contents are inaccessible.
    with os.scandir(path) as entries:
        next(entries, None)
    return tuple(result)


def _regular_evidence(path: Path) -> ArtifactEvidence:
    value = path.lstat()
    if _redirect(value) or not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
        raise ValueError("The artifact is not an exclusively owned regular file")
    if os.name == "nt":
        # Python's Windows path stat and fstat can expose different ctime epochs.
        # Read mutation time from a real handle, then recheck path identity. Keep
        # the reparse/hardlink and replacement guards; birth time is not mutation time.
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or file_stamp(opened)[:4] != file_stamp(value)[:4]
            ):
                raise ValueError("The artifact changed while opening")
            stamp = _descriptor_stamp(descriptor)
            current = path.lstat()
            if _redirect(current) or file_stamp(current) != file_stamp(value):
                raise ValueError("The artifact changed while observing")
        finally:
            os.close(descriptor)
        return ArtifactEvidence(path, stamp)
    return ArtifactEvidence(path, file_stamp(value))


def _observe(record: Mapping[str, Any], source: ArchivePath) -> FileOperationItem:
    owner, fingerprint = history_archive_owner(dict(record)), record_fingerprint(record)
    path = Path(str(source))
    if (source.style == "windows") != (os.name == "nt"):
        return FileOperationItem(owner, fingerprint, None, "unavailable")
    try:
        # A disconnected mount must never become a local empty directory.
        kind, anchor = source.storage
        if kind == "external" and not os.path.ismount(str(anchor)):
            return FileOperationItem(owner, fingerprint, path, "unavailable")
        ancestors = directory_evidence(path.parent)
        try:
            media = _regular_evidence(path)
        except FileNotFoundError:
            # Only ENOENT at the exact leaf, with an accessible parent and
            # available storage, supports Library-entry-only removal.
            return FileOperationItem(
                owner, fingerprint, path, "missing", ancestors=ancestors
            )
        artifacts = [media]
        metadata = path.parent / "metadata.json"
        try:
            metadata_evidence = _regular_evidence(metadata)
        except FileNotFoundError:
            metadata_evidence = None
        if metadata_evidence is not None:
            if metadata_evidence.stamp[2] > 1024 * 1024:
                raise ValueError("Companion metadata exceeds the inspection limit")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            with os.fdopen(os.open(metadata, flags), "rb") as stream:
                if _descriptor_stamp(stream.fileno()) != metadata_evidence.stamp:
                    raise ValueError("Companion metadata changed")
                data = json.loads(stream.read(1024 * 1024 + 1))
            # A generic sibling thumbnail is owned only with matching provider
            # identity in the item's metadata; unrelated files remain untouched.
            if (
                not isinstance(data, dict)
                or not record.get("id")
                or str(data.get("id")) != str(record["id"])
            ):
                raise ValueError("Companion ownership is ambiguous")
            for key in ("extractor_key", "vodforge_output_type"):
                if record.get(key) and data.get(key) and record[key] != data[key]:
                    raise ValueError("Companion identity differs")
            artifacts.append(metadata_evidence)
            for name in COMPANION_NAMES:
                if name == "metadata.json":
                    continue
                try:
                    artifacts.append(_regular_evidence(path.parent / name))
                except FileNotFoundError:
                    pass
        if directory_evidence(path.parent) != ancestors:
            raise ValueError("Source folder changed")
        if any(_regular_evidence(item.path) != item for item in artifacts):
            raise ValueError("Source changed during inspection")
        return FileOperationItem(
            owner, fingerprint, path, "ready", tuple(artifacts), ancestors
        )
    except (PermissionError, OSError):
        return FileOperationItem(owner, fingerprint, path, "unavailable")
    except (ValueError, TypeError, UnicodeError):
        return FileOperationItem(owner, fingerprint, path, "ambiguous")


def _ownership_key(path: ArchivePath) -> tuple[str, ...]:
    # Conservative alias protection also covers case/Unicode-insensitive volumes.
    # Two durable spellings must never silently acquire the same physical file.
    return (
        path.style,
        *(unicodedata.normalize("NFC", part).casefold() for part in path.parts),
    )


def plan_file_operation(
    records: Sequence[Mapping[str, Any]],
    owners: Sequence[str],
    *,
    cancelled: Event | None = None,
) -> FileOperationPlan:
    """Worker-only exact checks against ALL durable rows, never visible rows.

    A duplicate owner/path, sibling output, hard link, redirected component,
    unknown exact filename, inaccessible storage, or unowned metadata cannot
    acquire destructive authority by being selected in the UI.
    """
    if len(records) > MAX_HISTORY_ITEMS or len(owners) > MAX_HISTORY_ITEMS:
        raise ValueError("Selection exceeds the supported Library limit")
    snapshot = tuple(record_fingerprint(record) for record in records)
    owner_rows: dict[str, list[int]] = {}
    paths: dict[int, ArchivePath] = {}
    folders: Counter[tuple[str, ...]] = Counter()
    path_counts: Counter[tuple[str, ...]] = Counter()
    for index, record in enumerate(records):
        owner_rows.setdefault(history_archive_owner(dict(record)), []).append(index)
        try:
            source = recorded_artifact(record)
            if source is not None:
                paths[index] = source
                path_counts[_ownership_key(source)] += 1
                folders[_ownership_key(source.parent)] += 1
            else:
                # A legacy durable row still claims its folder, even if its
                # exact leaf is unknown. Do not appropriate its sidecars.
                folders[
                    _ownership_key(
                        ArchivePath.parse(str(record.get("vodforge_output_dir") or ""))
                    )
                ] += 1
        except (ValueError, TypeError):
            try:
                folders[
                    _ownership_key(
                        ArchivePath.parse(str(record.get("vodforge_output_dir") or ""))
                    )
                ] += 1
            except (ValueError, TypeError):
                pass
    items = []
    for owner in dict.fromkeys(owners):
        indices = owner_rows.get(owner, [])
        if cancelled is not None and cancelled.is_set():
            items.append(FileOperationItem(owner, "", None, "cancelled"))
            continue
        if len(indices) != 1:
            items.append(
                FileOperationItem(
                    owner, "", None, "changed" if not indices else "ambiguous"
                )
            )
            continue
        index = indices[0]
        source = paths.get(index)
        if (
            source is None
            or path_counts[_ownership_key(source)] != 1
            or folders[_ownership_key(source.parent)] != 1
        ):
            items.append(FileOperationItem(owner, snapshot[index], None, "ambiguous"))
            continue
        items.append(_observe(records[index], source))
    return FileOperationPlan(snapshot, tuple(items))


def plan_move_operation(
    records: Sequence[Mapping[str, Any]],
    owners: Sequence[str],
    destination: Path,
    *,
    cancelled: Event | None = None,
) -> FileOperationPlan:
    """Include visible destination conflicts before the user confirms Move."""
    plan = plan_file_operation(records, owners, cancelled=cancelled)
    directory_evidence(destination)
    folders = Counter(
        item.source.parent.name.casefold()
        for item in plan.items
        if item.state == "ready" and item.source is not None
    )
    claims = []
    for row in records:
        try:
            claims.append(ArchivePath.parse(str(row.get("vodforge_output_dir") or "")))
        except ValueError:
            pass
    items = []
    for item in plan.items:
        if item.state != "ready" or item.source is None:
            items.append(item)
            continue
        target = destination / item.source.parent.name
        proposed = ArchivePath.parse(str(target))
        reserved = any(
            _ownership_key(claim)[: len(proposed.key)] == _ownership_key(proposed)
            for claim in claims
        )
        try:
            target.lstat()
            existing = True
        except FileNotFoundError:
            existing = False
        except OSError:
            items.append(replace(item, state="unavailable"))
            continue
        conflict = (
            reserved
            or existing
            or folders[item.source.parent.name.casefold()] > 1
            or item.source.parent in target.parents
        )
        items.append(replace(item, state="conflict") if conflict else item)
    return replace(plan, items=tuple(items))


def recheck_file_operation(
    plan: FileOperationPlan,
    records: Sequence[Mapping[str, Any]],
    *,
    cancelled: Event | None = None,
) -> FileOperationPlan:
    """A confirmation is valid only for the same records and filesystem evidence."""
    fresh = plan_file_operation(
        records, [item.owner for item in plan.items], cancelled=cancelled
    )
    if fresh != plan:
        raise ValueError("The selected files changed. Review the selection again.")
    return fresh


class FileOperationCancelled(Exception):
    pass


class FileOperationUncertain(RuntimeError):
    """No further history writer may run until authoritative state is reloaded."""

    def __init__(self, journal: Path):
        super().__init__("File work needs recovery before another change.")
        self.journal = journal


@dataclass(frozen=True, slots=True)
class FileOperationResult:
    records: tuple[dict[str, Any], ...]
    outcomes: tuple[tuple[str, str], ...]
    journal: Path


def _sync_directory(path: Path) -> None:
    # Windows rename durability is managed by its filesystem; opening a directory
    # for fsync is POSIX-only. File contents are explicitly flushed on both.
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


@dataclass(frozen=True, slots=True)
class PendingFileOperation:
    path: Path
    action: str
    states: tuple[str, ...]
    locations: tuple[tuple[str, Path], ...] = ()
    can_finish: bool = False


def _read_operation_receipts(
    directory: Path,
) -> list[tuple[Path, Stamp, dict[str, Any]]]:
    """Bound private receipt reads and reject replacement during the read."""
    evidence_list = _receipt_inventory(directory)
    receipts = []
    for evidence in evidence_list:
        path = evidence.path
        with _RECEIPT_CACHE_LOCK:
            cached = _RECEIPT_CACHE.get(path)
            if cached is not None and cached[0] == evidence.stamp:
                _RECEIPT_CACHE.move_to_end(path)
                receipts.append((path, evidence.stamp, cached[1]))
                continue
        with path.open("rb") as stream:
            if _descriptor_stamp(stream.fileno()) != evidence.stamp:
                raise ValueError("File-operation receipt changed")
            content = stream.read(MAX_RECEIPT_BYTES + 1)
            if (
                len(content) > MAX_RECEIPT_BYTES
                or _descriptor_stamp(stream.fileno()) != evidence.stamp
            ):
                raise ValueError("File-operation receipt changed")
        if _regular_evidence(path).stamp != evidence.stamp:
            raise ValueError("File-operation receipt changed")
        document = json.loads(content)
        if (
            not isinstance(document, dict)
            or document.get("schema_version") != 1
            or document.get("action") not in {"move", "delete", "delete_permanent"}
            or not isinstance(document.get("items"), list)
            or any(not isinstance(item, dict) for item in document["items"])
        ):
            raise ValueError("A file-operation receipt could not be read")
        with _RECEIPT_CACHE_LOCK:
            _RECEIPT_CACHE[path] = (evidence.stamp, document)
            _RECEIPT_CACHE.move_to_end(path)
            while (
                len(_RECEIPT_CACHE) > MAX_HISTORY_ITEMS
                or sum(value[0][2] for value in _RECEIPT_CACHE.values())
                > MAX_RECEIPT_TOTAL_BYTES
            ):
                _RECEIPT_CACHE.popitem(last=False)
        receipts.append((path, evidence.stamp, document))
    return receipts


def pending_file_operations(directory: Path) -> tuple[PendingFileOperation, ...]:
    """Read-only restart gate. Uncertain receipts never authorize a repeated effect."""
    pending = []
    for path, _stamp, document in sorted(_read_operation_receipts(directory)):
        if document.get("state") not in {"completed", "kept_files"}:
            entries = [item for item in document["items"] if isinstance(item, dict)]
            locations: list[tuple[str, Path]] = []
            for entry in entries:
                for label, value in (
                    ("Source folder", entry.get("source")),
                    ("Destination folder", entry.get("destination")),
                ):
                    if isinstance(value, str) and Path(value).is_absolute():
                        location = (
                            Path(value).parent
                            if label == "Source folder"
                            else Path(value)
                        )
                        pair = (label, location)
                        if pair not in locations:
                            locations.append(pair)
            pending.append(
                PendingFileOperation(
                    path,
                    document["action"],
                    tuple(str(item.get("state", "unknown")) for item in entries),
                    tuple(locations[:4]),
                    document["action"] == "move"
                    and all(
                        entry.get("state") in {"completed", "skipped"}
                        or bool(entry.get("updated_fingerprint"))
                        for entry in entries
                    ),
                )
            )
    return tuple(pending)


def _retire_finished_receipts(directory: Path) -> None:
    """Startup-only retirement after prior producers died and pending deltas merged.

    Never call during a live producer session: even completed receipts can still
    protect an event already queued by a finished download.
    """
    finished = []
    for path, stamp, document in _read_operation_receipts(directory):
        try:
            if len(path.stem) != 32 or uuid.UUID(path.stem).version != 4:
                continue
        except ValueError:
            continue
        if document.get("state") in {"completed", "kept_files"}:
            finished.append(ArtifactEvidence(path, stamp))
    finished.sort(key=lambda item: item.stamp[3], reverse=True)
    for evidence in finished[32:]:
        proof = directory_evidence(directory)
        _unlink_retired(evidence.path, evidence.stamp, proof)
    if len(finished) > 32:
        _sync_directory(directory)


class OperationJournal:
    """One bounded recovery receipt, never a second completed-output ledger.

    Each item records intent before a filesystem effect, and the observed outcome
    after it. An uncertain effect is retained for reconciliation, never blindly
    repeated. Completed receipts may be removed only by the lifecycle owner.
    """

    def __init__(
        self,
        directory: Path,
        action: str,
        plan: FileOperationPlan,
        records: Sequence[Mapping[str, Any]] = (),
    ):
        directory_evidence(directory.parent)
        directory.mkdir(mode=0o700, exist_ok=True)
        directory_evidence(directory)
        if pending_file_operations(directory):
            raise ValueError(
                "Review the interrupted file operation before another change."
            )
        self.path = directory / (uuid.uuid4().hex + ".json")
        self._stamp: Stamp | None = None
        self.document: dict[str, Any] = {
            "schema_version": 1,
            "action": action,
            "state": "active",
            "items": [
                {
                    "owner": item.owner,
                    "fingerprint": item.fingerprint,
                    "source": str(item.source) if item.source else None,
                    "record_run_id": next(
                        (
                            str(row.get("vodforge_run_id") or "")
                            for row in records
                            if history_archive_owner(dict(row)) == item.owner
                        ),
                        "",
                    ),
                    "state": "pending",
                    "ancestors": [
                        [str(path), device, inode]
                        for path, device, inode in item.ancestors
                    ],
                    "artifacts": [
                        {"source": str(a.path), "stamp": list(a.stamp)}
                        for a in item.artifacts
                    ],
                }
                for item in plan.items
            ],
        }
        self.write()

    def assert_current(self) -> None:
        expected = getattr(self, "_stamp", None)
        if expected is not None:
            if _regular_evidence(self.path).stamp != expected:
                raise ValueError("File-operation receipt changed")
        else:
            try:
                self.path.lstat()
            except FileNotFoundError:
                return
            raise ValueError("File-operation receipt already exists")

    def write(self) -> None:
        directory_evidence(self.path.parent)
        self.assert_current()
        content = (json.dumps(self.document, ensure_ascii=False) + "\n").encode()
        if len(content) > MAX_RECEIPT_BYTES:
            raise FileOperationCapacityError(
                "This selection is too large. Try fewer items at once."
            )
        inventory = _receipt_inventory(self.path.parent)
        if (
            sum(item.stamp[2] for item in inventory if item.path != self.path)
            + len(content)
            > MAX_RECEIPT_TOTAL_BYTES
        ):
            raise FileOperationCapacityError(
                "File-operation storage is full. Finish any pending change and restart VODForge."
            )
        if self._stamp is None and (
            len(inventory) >= MAX_HISTORY_ITEMS
            or sum(item.stamp[2] for item in inventory) + MAX_RECEIPT_BYTES
            > MAX_RECEIPT_TOTAL_BYTES
        ):
            # Reserve the full per-operation allowance before any media effect.
            # Recovery can always grow this receipt within its admitted budget.
            raise FileOperationCapacityError(
                "File-operation storage is full. Restart VODForge before another change."
            )
        temporary = self.path.with_name("." + self.path.name + "." + uuid.uuid4().hex)
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            with os.fdopen(os.open(temporary, flags, 0o600), "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            self.assert_current()
            os.replace(temporary, self.path)
            self._stamp = _regular_evidence(self.path).stamp
            _sync_directory(self.path.parent)
        finally:
            temporary.unlink(missing_ok=True)

    def update(self, index: int, state: str, **facts: Any) -> None:
        self.document["items"][index].update(state=state, **facts)
        self.write()


def _cancel(event: Event | None) -> None:
    if event is not None and event.is_set():
        raise FileOperationCancelled()


def _hash_file(path: Path, expected: Stamp, cancelled: Event | None) -> str:
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        if _descriptor_stamp(stream.fileno()) != expected:
            raise ValueError("An artifact changed")
        while chunk := stream.read(1024 * 1024):
            _cancel(cancelled)
            digest.update(chunk)
        if _descriptor_stamp(stream.fileno()) != expected:
            raise ValueError("An artifact changed while reading")
    return digest.hexdigest()


def _copy_verified(
    artifact: ArtifactEvidence, target: Path, cancelled: Event | None
) -> dict[str, Any]:
    digest = hashlib.sha256()
    read_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    write_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    staging = create_private_staging_directory(target.parent)
    try:
        staged = staging / "media"
        with os.fdopen(os.open(artifact.path, read_flags), "rb") as source:
            if _descriptor_stamp(source.fileno()) != artifact.stamp:
                raise ValueError("The source changed")
            with os.fdopen(os.open(staged, write_flags, 0o600), "wb") as destination:
                while chunk := source.read(1024 * 1024):
                    _cancel(cancelled)
                    destination.write(chunk)
                    digest.update(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            if _descriptor_stamp(source.fileno()) != artifact.stamp:
                raise ValueError("The source changed while copying")
        staged_evidence = _regular_evidence(staged)
        if _hash_file(staged, staged_evidence.stamp, cancelled) != digest.hexdigest():
            raise ValueError("The staged copy did not verify")
        commit_file_beneath(
            staged,
            target.parent,
            target,
            control_check=lambda: _cancel(cancelled),
            replace_existing=False,
        )
        evidence = _regular_evidence(target)
        if _hash_file(target, evidence.stamp, cancelled) != digest.hexdigest():
            raise ValueError("The copy did not verify")
        return {
            "destination": str(target),
            "stamp": list(evidence.stamp),
            "sha256": digest.hexdigest(),
        }
    finally:
        cleanup_private_staging_directory(staging)


def _save_durable_history(path: Path, records: list[dict[str, Any]]) -> None:
    from .history import save_history

    save_history(path, records)
    # A successful relink publication must reach the actual file writer before
    # the source can be retired. The UI's deferred incoming-history buffer cannot
    # stand in for this boundary.
    # Windows FlushFileBuffers (used by fsync) needs a write-capable handle.
    # Reopen without truncation; the existing history writer remains authority.
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())
    _sync_directory(path.parent)


def _relocate_one(
    records: Sequence[Mapping[str, Any]], owner: str, destination: Path
) -> list[dict[str, Any]]:
    index = next(
        i for i, row in enumerate(records) if history_archive_owner(dict(row)) == owner
    )
    source = recorded_artifact(records[index])
    observed = destination.stat()
    entry = RelinkEntry(
        index,
        record_fingerprint(records[index]),
        source,
        ArchivePath.parse(str(destination)),
        None,
        "ready",
        stamp=(
            observed.st_dev,
            observed.st_ino,
            observed.st_size,
            observed.st_mtime_ns,
        ),
    )
    preview = RelinkPreview((entry,), tuple(record_fingerprint(r) for r in records))
    return relocated_records(preview, records, accepted=(index,))


def _unlink_retired(
    path: Path, expected: Stamp, proof: tuple[tuple[Path, int, int], ...]
) -> None:
    """Recheck after receipt/fault boundaries; anchor POSIX deletion to its directory."""
    if directory_evidence(path.parent) != proof:
        raise ValueError("Cleanup folder changed; retained for recovery")
    if os.unlink in os.supports_dir_fd:
        descriptor = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            parent = os.fstat(descriptor)
            if (parent.st_dev, parent.st_ino) != proof[-1][1:]:
                raise ValueError("Cleanup directory identity changed")
            observed = os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
            if _redirect(observed) or file_stamp(observed) != expected:
                raise ValueError("Retired file changed; retained for recovery")
            os.unlink(path.name, dir_fd=descriptor)
        finally:
            os.close(descriptor)
    else:
        # Windows does not expose dir_fd through Python. The platform path and
        # leaf are rechecked immediately; redirected/reparse paths are refused.
        if _regular_evidence(path).stamp != expected:
            raise ValueError("Retired file changed; retained for recovery")
        path.unlink()


def _finish_move_cleanup(
    journal: OperationJournal,
    index: int,
    item: FileOperationItem,
    copies: list[dict[str, Any]],
    target_proof: tuple[tuple[Path, int, int], ...],
    *,
    cancelled: Event | None = None,
    boundary: Callable[[str], None] = lambda _: None,
) -> None:
    if item.source is None:
        raise ValueError("The exact source is unavailable")
    entry = journal.document["items"][index]
    if entry.get("cleanup_proof"):
        cleanup = Path(entry["cleanup"])
        cleanup_proof = tuple(
            (Path(p), int(d), int(i)) for p, d, i in entry["cleanup_proof"]
        )
        if cleanup.parent != item.source.parent:
            raise ValueError("Cleanup location changed")
        try:
            cleanup.lstat()
        except FileNotFoundError:
            # The empty directory can be removed before its final receipt lands.
            # Reconcile that observation without repeating any filesystem effect.
            steps = entry.get("cleanup_steps") or []
            if (
                len(steps) != len(item.artifacts)
                or directory_evidence(item.source.parent) != item.ancestors
                or directory_evidence(target_proof[-1][0]) != target_proof
            ):
                raise ValueError("Cleanup evidence is incomplete")
            for artifact, step in zip(item.artifacts, steps, strict=True):
                if (
                    step.get("state") != "removed"
                    or step.get("source") != str(artifact.path)
                    or step.get("retired") != str(cleanup / artifact.path.name)
                ):
                    raise ValueError("Cleanup evidence is incomplete")
                try:
                    artifact.path.lstat()
                except FileNotFoundError:
                    pass
                else:
                    raise ValueError("Source changed; retained for recovery")
            for copy in copies:
                if (
                    _hash_file(
                        Path(copy["destination"]), tuple(copy["stamp"]), cancelled
                    )
                    != copy["sha256"]
                ):
                    raise ValueError("Destination changed before source cleanup")
            _sync_directory(item.source.parent)
            return
        if directory_evidence(cleanup) != cleanup_proof:
            raise ValueError("Cleanup location changed")
    else:
        cleanup = item.source.parent / (".vodforge-move-" + uuid.uuid4().hex)
        journal.update(index, "cleanup_claim_requested", cleanup=str(cleanup))
        cleanup.mkdir(mode=0o700)
        cleanup_proof = directory_evidence(cleanup)
        journal.update(
            index,
            "cleanup",
            cleanup_proof=[
                [str(path), device, inode] for path, device, inode in cleanup_proof
            ],
        )
    steps = entry.get("cleanup_steps") or [
        {
            "source": str(artifact.path),
            "source_stamp": list(artifact.stamp),
            "retired": str(cleanup / artifact.path.name),
            "state": "pending",
        }
        for artifact in item.artifacts
    ]
    if len(steps) != len(item.artifacts):
        raise ValueError("Cleanup evidence is incomplete")
    journal.update(index, "cleanup", cleanup_steps=steps)
    for artifact_index, artifact in enumerate(item.artifacts):
        _cancel(cancelled)
        boundary("before_source_cleanup")
        if directory_evidence(target_proof[-1][0]) != target_proof:
            raise ValueError("Destination changed before source cleanup")
        for copy in copies:
            if (
                _hash_file(Path(copy["destination"]), tuple(copy["stamp"]), cancelled)
                != copy["sha256"]
            ):
                raise ValueError("Destination changed before source cleanup")
        if directory_evidence(item.source.parent) != item.ancestors:
            raise ValueError("Source location changed")
        if directory_evidence(cleanup) != cleanup_proof:
            raise ValueError("Cleanup location changed")
        step = steps[artifact_index]
        retired = cleanup / artifact.path.name
        if step["source"] != str(artifact.path) or step["retired"] != str(retired):
            raise ValueError("Cleanup artifact differs")
        try:
            source_stat = artifact.path.lstat()
        except FileNotFoundError:
            source_stat = None
        try:
            retired_stat = retired.lstat()
        except FileNotFoundError:
            retired_stat = None
        if source_stat is not None:
            if (
                _regular_evidence(artifact.path).stamp != artifact.stamp
                or _redirect(source_stat)
                or retired_stat is not None
            ):
                raise ValueError("Source changed; retained for recovery")
            step["state"] = "retire_requested"
            journal.update(
                index,
                "retire_requested",
                retiring=str(artifact.path),
                retired=str(retired),
                cleanup_steps=steps,
            )
            artifact.path.rename(retired)
            retired_stat = retired.lstat()
        elif retired_stat is None:
            # Reconcile the unlink-before-receipt crash without repeating unlink.
            if step["state"] not in {"retired", "removed"}:
                raise ValueError("Source outcome is unknown")
            step["state"] = "removed"
            journal.update(index, "cleanup", cleanup_steps=steps)
            continue
        if (
            retired_stat.st_dev,
            retired_stat.st_ino,
            retired_stat.st_size,
            retired_stat.st_mtime_ns,
        ) != artifact.stamp[:4] or _redirect(retired_stat):
            raise ValueError("Retired identity changed; retained for recovery")
        expected = _regular_evidence(retired).stamp
        copy = next(
            c for c in copies if Path(c["destination"]).name == artifact.path.name
        )
        if _hash_file(retired, expected, cancelled) != copy["sha256"]:
            raise ValueError("Retired contents changed; retained for recovery")
        step.update(state="retired", retired_stamp=list(expected))
        journal.update(
            index,
            "retired",
            retired=str(retired),
            retired_stamp=list(expected),
            cleanup_steps=steps,
        )
        boundary("source_retired")
        _unlink_retired(retired, expected, cleanup_proof)
        _sync_directory(cleanup)
        step["state"] = "removed"
        journal.update(index, "cleanup", cleanup_steps=steps)
    if directory_evidence(cleanup) != cleanup_proof:
        raise ValueError("Cleanup location changed")
    try:
        cleanup.rmdir()
    except OSError as exc:
        if exc.errno not in {errno.ENOTEMPTY, errno.EEXIST}:
            raise
        # A foreign entry may arrive after the preceding identity check, or
        # a replacement directory may reuse the retired inode. Preserve it.
        raise ValueError("Cleanup location changed; retained for recovery") from exc
    _sync_directory(item.source.parent)
    boundary("cleanup_removed")


def move_files(
    plan: FileOperationPlan,
    records: Sequence[Mapping[str, Any]],
    destination: Path,
    history_path: Path,
    journal_directory: Path,
    *,
    cancelled: Event | None = None,
    boundary: Callable[[str], None] = lambda _: None,
) -> FileOperationResult:
    """Copy and verify all owned artifacts, publish history, then retire sources.

    The caller serializes canonical history writers. A newly claimed item folder
    prevents overwriting any existing destination. Failures retain their receipt
    and any copies for recovery; the next operation never retries uncertain work.
    """
    if journal_directory != history_path.parent / "file-operations":
        raise ValueError("Use the Library file-operation recovery directory")
    fresh_plan = plan_move_operation(
        records, [item.owner for item in plan.items], destination, cancelled=cancelled
    )
    if fresh_plan != plan:
        raise ValueError("Files or destination changed. Review the move again.")
    destination_proof = directory_evidence(destination)
    journal = OperationJournal(journal_directory, "move", plan, records)
    current = [dict(record) for record in records]
    outcomes: list[tuple[str, str]] = []
    for index, item in enumerate(plan.items):
        if item.state != "ready" or item.source is None:
            journal.update(index, "skipped", reason=item.state)
            outcomes.append((item.owner, item.state))
            continue
        published = False
        durability_confirmed = False
        prospective: list[dict[str, Any]] | None = None
        try:
            _cancel(cancelled)
            fresh = plan_file_operation(current, [item.owner], cancelled=cancelled)
            if fresh.items != (item,):
                raise ValueError("Selected files changed")
            if directory_evidence(destination) != destination_proof:
                raise ValueError("The destination changed")
            target_folder = destination / item.source.parent.name
            # Refuse a destination inside the source folder, including the same
            # folder. The directory proofs above have already excluded aliases.
            if (
                target_folder == item.source.parent
                or item.source.parent in target_folder.parents
            ):
                raise ValueError("Choose another destination")
            journal.update(index, "claim_requested", destination=str(target_folder))
            target_folder.mkdir(mode=0o700)
            target_proof = directory_evidence(target_folder)
            journal.update(
                index,
                "copying",
                destination_proof=[
                    [str(path), device, inode] for path, device, inode in target_proof
                ],
            )
            boundary("destination_claimed")
            copied = []
            for artifact in item.artifacts:
                if directory_evidence(target_folder) != target_proof:
                    raise ValueError("Destination folder changed")
                copied.append(
                    _copy_verified(
                        artifact, target_folder / artifact.path.name, cancelled
                    )
                )
                journal.update(index, "copying", copies=copied)
                boundary("artifact_copied")
            _sync_directory(target_folder)
            _sync_directory(destination)
            journal.update(index, "verified", copies=copied)
            boundary("copies_verified")
            _cancel(cancelled)
            if plan_file_operation(current, [item.owner]).items != (item,):
                raise ValueError("Source changed before publication")
            if directory_evidence(target_folder) != target_proof:
                raise ValueError("Destination changed before publication")
            for copy in copied:
                path = Path(copy["destination"])
                if _hash_file(path, tuple(copy["stamp"]), cancelled) != copy["sha256"]:
                    raise ValueError("Destination changed before publication")
            prospective = _relocate_one(
                current, item.owner, target_folder / item.source.name
            )
            new_index = next(
                i
                for i, row in enumerate(current)
                if history_archive_owner(dict(row)) == item.owner
            )
            journal.update(
                index,
                "history_requested",
                updated_fingerprint=record_fingerprint(prospective[new_index]),
                updated_owner=history_archive_owner(prospective[new_index]),
            )
            _cancel(cancelled)
            boundary("before_history")
            from .history import file_operation_history_write

            with file_operation_history_write(journal.path, prospective):
                _save_durable_history(history_path, prospective)
            current = prospective
            published = True
            durability_confirmed = True
            journal.update(index, "history_saved")
            boundary("history_saved")
            # Cancellation after publication leaves the durable destination and
            # source duplicates intact. Recovery must not pretend this was undone.
            _cancel(cancelled)
            _finish_move_cleanup(
                journal,
                index,
                item,
                copied,
                target_proof,
                cancelled=cancelled,
                boundary=boundary,
            )
            journal.update(index, "completed")
            outcomes.append((item.owner, "completed"))
        except (OSError, ValueError, HistoryError, FileOperationCancelled) as exc:
            # Atomic replace may have succeeded before a flush or receipt write
            # failed. Reconcile the actual history bytes; never return stale
            # in-memory records as though publication had been undone.
            if prospective is not None and not published:
                try:
                    actual = json.loads(history_path.read_text(encoding="utf-8"))
                    if isinstance(actual, dict) and actual.get("items") == prospective:
                        current, published = prospective, True
                except (OSError, ValueError):
                    pass
            state = (
                ("cleanup_pending" if durability_confirmed else "history_uncertain")
                if published
                else (
                    "cancelled"
                    if isinstance(exc, FileOperationCancelled)
                    else "needs_attention"
                )
            )
            try:
                journal.update(index, state, failure=type(exc).__name__)
            except (OSError, ValueError) as journal_error:
                raise FileOperationUncertain(journal.path) from journal_error
            outcomes.append((item.owner, state))
    journal.document["state"] = (
        "completed"
        if all(
            entry["state"] in {"completed", "skipped"}
            for entry in journal.document["items"]
        )
        else "needs_attention"
    )
    try:
        journal.write()
    except (OSError, ValueError) as journal_error:
        raise FileOperationUncertain(journal.path) from journal_error
    return FileOperationResult(tuple(current), tuple(outcomes), journal.path)


def delete_files(
    plan: FileOperationPlan,
    records: Sequence[Mapping[str, Any]],
    history_path: Path,
    journal_directory: Path,
    *,
    permanent: bool = False,
    cancelled: Event | None = None,
    trash: Callable[[Path], str | None] | None = None,
    boundary: Callable[[str], None] = lambda _: None,
) -> FileOperationResult:
    """Delete exactly the confirmed items; missing entries never guess a file.

    Permanent deletion is a separate explicit confirmation mode. A Trash failure
    never switches modes. Partial files remain represented in history with a
    recovery receipt; successful individual items are durably removed.
    """
    from .platform_services import trash_file

    trash = trash or trash_file
    if journal_directory != history_path.parent / "file-operations":
        raise ValueError("Use the Library file-operation recovery directory")
    recheck_file_operation(plan, records, cancelled=cancelled)
    journal = OperationJournal(
        journal_directory, "delete_permanent" if permanent else "delete", plan, records
    )
    current = [dict(record) for record in records]
    outcomes: list[tuple[str, str]] = []
    for index, item in enumerate(plan.items):
        if item.state not in {"ready", "missing"}:
            journal.update(index, "skipped", reason=item.state)
            outcomes.append((item.owner, item.state))
            continue
        prospective = None
        published = False
        try:
            _cancel(cancelled)
            if plan_file_operation(
                current, [item.owner], cancelled=cancelled
            ).items != (item,):
                raise ValueError("Selected files changed")
            steps: list[dict[str, Any]] = [
                {
                    "source": str(artifact.path),
                    "stamp": list(artifact.stamp),
                    "state": "pending",
                }
                for artifact in item.artifacts
            ]
            journal.update(
                index, "deleting", delete_steps=steps, missing=item.state == "missing"
            )
            for artifact_index, artifact in enumerate(item.artifacts):
                _cancel(cancelled)
                boundary("before_delete")
                if (
                    directory_evidence(artifact.path.parent) != item.ancestors
                    or _regular_evidence(artifact.path) != artifact
                ):
                    raise ValueError("Source changed before deletion")
                steps[artifact_index]["state"] = (
                    "delete_requested" if permanent else "trash_requested"
                )
                journal.update(index, "deleting", delete_steps=steps)
                if permanent:
                    # The same anchored, immediate identity check used for Move
                    # cleanup applies to explicitly confirmed permanent deletion.
                    _unlink_retired(artifact.path, artifact.stamp, item.ancestors)
                    _sync_directory(artifact.path.parent)
                    result_path = None
                else:
                    # The API owns the final transfer into system Trash; there
                    # is no second shell fallback and no unlink on API failure.
                    if (
                        directory_evidence(artifact.path.parent) != item.ancestors
                        or _regular_evidence(artifact.path) != artifact
                    ):
                        raise ValueError("Source changed before Trash")
                    result_path = trash(artifact.path)
                boundary("file_deleted")
                steps[artifact_index].update(
                    state="deleted" if permanent else "trashed", trash_path=result_path
                )
                journal.update(index, "deleting", delete_steps=steps)
            _cancel(cancelled)
            prospective = [
                dict(row)
                for row in current
                if history_archive_owner(dict(row)) != item.owner
            ]
            journal.update(index, "history_requested")
            boundary("before_history")
            # A missing entry must still be missing at the actual history
            # boundary. A new file at a trashed path also stops entry removal.
            if item.source is not None:
                if directory_evidence(item.source.parent) != item.ancestors:
                    raise ValueError("Source location changed before history removal")
                try:
                    item.source.lstat()
                except FileNotFoundError:
                    pass
                else:
                    raise ValueError("A file appeared before history removal")
            from .history import file_operation_history_write

            with file_operation_history_write(journal.path, prospective):
                _save_durable_history(history_path, prospective)
            current, published = prospective, True
            journal.update(index, "completed")
            outcomes.append(
                (
                    item.owner,
                    "entry_removed" if item.state == "missing" else "completed",
                )
            )
        except (OSError, ValueError, HistoryError, FileOperationCancelled) as exc:
            if prospective is not None and not published:
                try:
                    actual = json.loads(history_path.read_text(encoding="utf-8"))
                    if isinstance(actual, dict) and actual.get("items") == prospective:
                        current, published = prospective, True
                except (OSError, ValueError):
                    pass
            state = (
                "history_uncertain"
                if published
                else (
                    "cancelled"
                    if isinstance(exc, FileOperationCancelled)
                    else "needs_attention"
                )
            )
            try:
                journal.update(index, state, failure=type(exc).__name__)
            except (OSError, ValueError) as journal_error:
                raise FileOperationUncertain(journal.path) from journal_error
            outcomes.append((item.owner, state))
    journal.document["state"] = (
        "completed"
        if all(
            entry["state"] in {"completed", "skipped"}
            for entry in journal.document["items"]
        )
        else "needs_attention"
    )
    try:
        journal.write()
    except (OSError, ValueError) as journal_error:
        raise FileOperationUncertain(journal.path) from journal_error
    return FileOperationResult(tuple(current), tuple(outcomes), journal.path)


def _recovery_journal(receipt: Path, history_path: Path) -> OperationJournal:
    if receipt.parent != history_path.parent / "file-operations":
        raise ValueError("Recovery receipt is outside the Library profile")
    pending = [
        (path, stamp, document)
        for path, stamp, document in _read_operation_receipts(receipt.parent)
        if document.get("state") not in {"completed", "kept_files"}
    ]
    if len(pending) != 1 or pending[0][0] != receipt:
        raise ValueError("Review each interrupted operation separately")
    journal = object.__new__(OperationJournal)
    journal.path, journal._stamp, document = pending[0]
    journal.document = deepcopy(document)
    journal.assert_current()
    return journal


def recover_move_cleanup(
    receipt: Path,
    records: Sequence[Mapping[str, Any]],
    history_path: Path,
    *,
    cancelled: Event | None = None,
) -> FileOperationResult:
    """Explicitly resume only a verified, already-published Move.

    Unpublished copies and ambiguous source changes require review, not a guessed
    retry. Current history and every destination are re-established before any
    original/quarantined source is retired.
    """
    journal = _recovery_journal(receipt, history_path)
    document = journal.document
    if document["action"] != "move":
        raise ValueError("This operation needs individual review")
    current = [dict(record) for record in records]
    outcomes = []
    for index, entry in enumerate(document["items"]):
        if entry["state"] in {"completed", "skipped"}:
            outcomes.append((entry["owner"], entry["state"]))
            continue
        candidates = [
            record
            for record in current
            if history_archive_owner(record) == entry.get("updated_owner")
            and record_fingerprint(record) == entry.get("updated_fingerprint")
        ]
        if (
            len(candidates) != 1
            or not entry.get("copies")
            or not entry.get("destination_proof")
        ):
            raise ValueError(
                "This move has not been confirmed in Library; keep its files for review"
            )
        source = Path(entry["source"])
        target = Path(entry["destination"])
        if str(recorded_artifact(candidates[0])) != str(target / source.name):
            raise ValueError("Saved destination differs")
        proof = tuple(
            (Path(p), int(d), int(i)) for p, d, i in entry["destination_proof"]
        )
        if directory_evidence(target) != proof:
            raise ValueError("Destination identity changed")
        artifacts = tuple(
            ArtifactEvidence(Path(a["source"]), tuple(a["stamp"]))
            for a in entry["artifacts"]
        )
        copies = entry["copies"]
        if len(copies) != len(artifacts) or any(
            a.path.parent != source.parent
            or Path(c["destination"]) != target / a.path.name
            for a, c in zip(artifacts, copies, strict=True)
        ):
            raise ValueError("Copied artifact scope differs")
        for copy in copies:
            if (
                _hash_file(Path(copy["destination"]), tuple(copy["stamp"]), cancelled)
                != copy["sha256"]
            ):
                raise ValueError("Destination no longer verifies")
        from .history import file_operation_history_write

        # Bytes matching a previous receipt do not establish durability. Flush
        # the actual current ledger again, and stop on failure before cleanup.
        journal.assert_current()
        with file_operation_history_write(receipt, current):
            _save_durable_history(history_path, current)
        journal.assert_current()
        item = FileOperationItem(
            entry["owner"],
            entry["fingerprint"],
            source,
            "ready",
            artifacts,
            tuple((Path(p), int(d), int(i)) for p, d, i in entry["ancestors"]),
        )
        _finish_move_cleanup(journal, index, item, copies, proof, cancelled=cancelled)
        journal.update(index, "completed")
        outcomes.append((entry["owner"], "completed"))
    journal.document["state"] = "completed"
    journal.write()
    return FileOperationResult(tuple(current), tuple(outcomes), receipt)


def keep_current_file_state(
    receipt: Path,
    records: Sequence[Mapping[str, Any]],
    history_path: Path,
) -> None:
    """User-reviewed recovery exit: preserve every media path, adopt actual history.

    This acknowledges an incomplete outcome, not a successful move or deletion.
    No uncertain filesystem effect is retried. The private receipt is retained.
    """
    journal = _recovery_journal(receipt, history_path)
    from .history import file_operation_history_write, load_history

    actual = load_history(history_path)
    if tuple(map(record_fingerprint, actual)) != tuple(
        map(record_fingerprint, records)
    ):
        raise ValueError("Library changed; review the current files again")
    with file_operation_history_write(receipt, actual):
        _save_durable_history(history_path, actual)
    journal.assert_current()
    if journal.document["action"] in {"delete", "delete_permanent"}:
        actual_owners = {history_archive_owner(row) for row in actual}
        for entry in journal.document["items"]:
            if entry.get("owner") not in actual_owners:
                # This records only the re-flushed Library disposition. It does
                # not convert an uncertain physical Trash/delete effect to success.
                entry["history_disposition"] = "removed"
    journal.document["state"] = "kept_files"
    journal.write()


def reconcile_file_record_delta(
    incoming: dict[str, Any],
    current: Sequence[Mapping[str, Any]],
    directory: Path,
) -> dict[str, Any] | None:
    """Merge a late run delta without restoring a retired path or deleted entry.

    Only the same recorded run (or byte-equivalent original record) can follow a
    receipt. A new run writing a fresh output is never mistaken for an old delta.
    """
    receipts = sorted(_read_operation_receipts(directory), key=lambda row: row[1][3])
    owner = history_archive_owner(incoming)
    original_owner = owner
    moved = False
    run = str(incoming.get("vodforge_run_id") or "")
    for _receipt, _stamp, document in receipts:
        if document.get("state") not in {"completed", "kept_files"}:
            continue
        for entry in document["items"]:
            if owner != entry.get("owner"):
                continue
            if not (
                (run and run == entry.get("record_run_id"))
                or record_fingerprint(incoming) == entry.get("fingerprint")
                or owner != original_owner
            ):
                continue
            if document["action"] in {"delete", "delete_permanent"}:
                if (
                    entry.get("state") == "completed"
                    or entry.get("history_disposition") == "removed"
                ):
                    return None
            elif document["action"] == "move" and entry.get("updated_owner"):
                owner = entry["updated_owner"]
                moved = True
    target = next(
        (row for row in current if history_archive_owner(dict(row)) == owner), None
    )
    if target is None or not moved:
        return incoming
    if run and target.get("vodforge_run_id") and target["vodforge_run_id"] != run:
        return None
    merged = {**dict(target), **incoming}
    for key in (
        "vodforge_output_dir",
        "vodforge_output_path",
        "vodforge_archive_id",
        "vodforge_archive_annotation_owner",
        "vodforge_progress_key",
        "vodforge_relinked",
    ):
        if key in target:
            merged[key] = target[key]
    summary = merged.get("vodforge_encoding_summary")
    if isinstance(summary, dict) and isinstance(summary.get("output"), dict):
        merged["vodforge_encoding_summary"] = {
            **summary,
            "output": {
                **summary["output"],
                "Output file path": target["vodforge_output_path"],
            },
        }
    return merged
