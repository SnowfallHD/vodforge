"""Qt event handoff for the existing verified Archive relink transaction."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from yt_downloader.archive_paths import ArchivePath, RootMapping
from yt_downloader.archive_relink import (
    RelinkPreview,
    commit_relink,
    preview_relink,
    record_fingerprint,
    verify_relink,
)
from yt_downloader.archive_work import ArchiveWorkOwner
from yt_downloader.history import history_archive_owner, load_history


def _content_fingerprints(rows: list[dict[str, Any]]) -> tuple[str, ...]:
    # Legacy history can synthesize recorded_at on each load until the next
    # durable save. Bind the raw document separately to detect every disk edit.
    return tuple(
        record_fingerprint(
            {key: value for key, value in row.items() if key != "vodforge_recorded_at"}
        )
        for row in rows
    )


class QtRelinkSession:
    """Keep one reviewed file decision separate from canonical history ownership."""

    def __init__(self, history_path: Path) -> None:
        self.history_path = history_path
        self.work = ArchiveWorkOwner()
        self.phase = "idle"
        self.status = ""
        self.owner = ""
        self.destination = ""
        self.index = -1
        self.mode = "file"
        self.selected: tuple[int, ...] = ()
        self.preview: RelinkPreview | None = None
        self.records: list[dict[str, Any]] = []
        self.updated_history: list[dict[str, Any]] | None = None
        self._document_hash: bytes | None = None
        self._cancel_requested = False
        self._started = 0.0

    @property
    def active(self) -> bool:
        return self.phase in {"checking", "preview", "working"} or self.work.busy

    @property
    def eligible(self) -> bool:
        return (
            self.phase == "preview"
            and self.preview is not None
            and bool(self.ready_indices)
        )

    @property
    def ready_indices(self) -> tuple[int, ...]:
        return (
            tuple(
                entry.index for entry in self.preview.entries if entry.state == "ready"
            )
            if self.preview is not None
            else ()
        )

    def begin(
        self, owner: str, destination: Path, records: list[dict[str, Any]]
    ) -> bool:
        if self.active or not destination.is_absolute():
            return False
        indices = [
            index
            for index, row in enumerate(records)
            if history_archive_owner(row) == owner
        ]
        if len(indices) != 1:
            return False
        index = indices[0]
        snapshot = [dict(row) for row in records]
        proposal = preview_relink(
            snapshot, selected=[index], exact_files={index: str(destination)}
        )

        return self._begin_proposal(
            owner, str(destination), (index,), snapshot, proposal
        )

    def begin_folder(
        self,
        source: ArchivePath,
        destination: ArchivePath,
        owners: tuple[str, ...],
        records: list[dict[str, Any]],
    ) -> bool:
        if self.active or not owners:
            return False
        by_owner: dict[str, list[int]] = {}
        for index, row in enumerate(records):
            by_owner.setdefault(history_archive_owner(row), []).append(index)
        if len(set(owners)) != len(owners) or any(
            len(by_owner.get(owner, ())) != 1 for owner in owners
        ):
            return False
        selected = tuple(by_owner[owner][0] for owner in owners)
        snapshot = [dict(row) for row in records]
        proposal = preview_relink(
            snapshot,
            (RootMapping(source, destination),),
            selected=selected,
        )
        return self._begin_proposal("", str(destination), selected, snapshot, proposal)

    def _begin_proposal(
        self,
        owner: str,
        destination: str,
        selected: tuple[int, ...],
        snapshot: list[dict[str, Any]],
        proposal: RelinkPreview,
    ) -> bool:

        def verify(cancelled: Any) -> tuple[RelinkPreview, bytes]:
            on_disk = load_history(self.history_path)
            if _content_fingerprints(on_disk) != _content_fingerprints(snapshot):
                raise ValueError("Library changed before file verification")
            document_hash = hashlib.sha256(self.history_path.read_bytes()).digest()
            return verify_relink(proposal, snapshot, cancelled=cancelled), document_hash

        generation = self.work.submit("verify", verify)
        if generation is None:
            return False
        self.owner = owner
        self.destination = destination
        self.index = selected[0] if owner else -1
        self.mode = "file" if owner else "folder"
        self.selected = selected
        self.records = snapshot
        self.preview = None
        self.updated_history = None
        self._document_hash = None
        self._cancel_requested = False
        self.phase = "checking"
        self.status = "Checking the selected files and saved details…"
        self._started = time.monotonic()
        return True

    def accept(self, current: list[dict[str, Any]]) -> bool:
        if not self.eligible or self.preview is None:
            return False
        if tuple(record_fingerprint(row) for row in current) != self.preview.snapshot:
            self.phase = "stale"
            self.status = "Library changed. Choose and verify the file again."
            return False
        preview = self.preview
        snapshot = self.records
        selected = self.ready_indices

        def commit(cancelled: Any) -> list[dict[str, Any]]:
            if (
                self._document_hash is None
                or hashlib.sha256(self.history_path.read_bytes()).digest()
                != self._document_hash
            ):
                raise ValueError("Library changed before the saved-location update")
            on_disk = load_history(self.history_path)
            if _content_fingerprints(on_disk) != _content_fingerprints(snapshot):
                raise ValueError("Library changed before the saved-location update")
            return commit_relink(
                preview,
                snapshot,
                self.history_path,
                accepted=selected,
                cancelled=cancelled,
            )

        if self.work.submit("commit", commit) is None:
            return False
        self.phase = "working"
        self.status = "Saving the verified file location…"
        self._started = time.monotonic()
        return True

    def poll(self) -> bool:
        if self.phase == "checking" and time.monotonic() - self._started >= 20:
            self.work.cancel()
            self.phase = "timed_out"
            self.status = "Checking this file took too long. Try again later."
            return True
        result = self.work.poll()
        if result is None:
            return False
        if result.kind == "verify" and self.phase == "checking":
            if (
                result.error
                or not isinstance(result.value, tuple)
                or not isinstance(result.value[0], RelinkPreview)
            ):
                self.phase = "error"
                self.status = "The selected file could not be checked."
                return True
            self.preview, self._document_hash = result.value
            if self.ready_indices:
                self.phase = "preview"
                self.status = (
                    f"Review {len(self.ready_indices)} verified location(s) before updating Library. "
                    "Other files will stay unchanged. Identical content is not confirmed."
                )
            else:
                self.phase = "error"
                state = (
                    self.preview.entries[0].state
                    if self.preview.entries
                    else "unavailable"
                )
                self.status = f"This file cannot be linked ({state})."
            return True
        if result.kind == "commit" and self.phase == "working":
            if result.error or not isinstance(result.value, list):
                self.phase = "cancelled" if self._cancel_requested else "error"
                self.status = (
                    "Update cancelled. Your saved location was not changed."
                    if self._cancel_requested
                    else "The location was not confirmed. Review Library and try again."
                )
            else:
                self.updated_history = result.value
                self.phase = "done"
                self.status = "Saved file location updated."
            return True
        return False

    def cancel(self) -> None:
        if self.phase == "working":
            self._cancel_requested = True
            self.work.cancel(retire_result=False)
            self.status = "Stopping the saved-location update…"
            return
        self.work.cancel()
        self.phase = "idle"
        self.status = ""
        self.preview = None

    def close(self) -> None:
        self.work.close()
