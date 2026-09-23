"""Qt event handoff for the existing exact-file Library transaction owner."""

from __future__ import annotations

import copy
import queue
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from yt_downloader.archive_file_operations import (
    FileOperationPlan,
    PendingFileOperation,
    delete_files,
    keep_current_file_state,
    move_files,
    pending_file_operations,
    plan_file_operation,
    plan_move_operation,
    recover_move_cleanup,
)
from yt_downloader.archive_relink import record_fingerprint
from yt_downloader.history import load_history
from yt_downloader.platform_services import system_trash_available


class QtLibraryFiles:
    """Holds only the current UI decision; file and history authority stays shared."""

    def __init__(self, history_path: Path) -> None:
        self.history_path = history_path
        self.journal_directory = history_path.parent / "file-operations"
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancelled = threading.Event()
        self.phase = "idle"
        self.status = ""
        self.action = ""
        self.destination: Path | None = None
        self.records: list[dict[str, Any]] = []
        self.plan: FileOperationPlan | None = None
        self.pending: tuple[PendingFileOperation, ...] = ()
        self.latest_history: list[dict[str, Any]] | None = None
        self.uncertain = False

    @property
    def busy(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    @property
    def eligible(self) -> bool:
        if self.plan is None:
            return False
        counts = self.plan.counts
        return bool(
            counts.get("ready", 0)
            or (self.action == "delete" and counts.get("missing", 0))
        )

    @property
    def can_finish(self) -> bool:
        return len(self.pending) == 1 and self.pending[0].can_finish

    def _start(self, target: Any, name: str) -> bool:
        if self.busy:
            return False
        self.cancelled = threading.Event()
        self.worker = threading.Thread(target=target, name=name, daemon=False)
        self.worker.start()
        return True

    def begin(
        self,
        action: str,
        owner: str,
        records: Sequence[dict[str, Any]],
        *,
        destination: Path | None = None,
    ) -> bool:
        if (
            action not in {"move", "delete"}
            or not owner
            or self.busy
            or self.phase in {"checking", "working"}
        ):
            return False
        if action == "move" and destination is None:
            return False
        if action == "delete" and not system_trash_available():
            self.phase = "error"
            self.status = "Trash is unavailable. The media and Library card were kept."
            return False
        self.action, self.destination = action, destination
        self.records = copy.deepcopy(list(records))
        self.plan = None
        self.phase = "checking"
        self.status = "Checking the exact saved files…"

        def work() -> None:
            try:
                pending = pending_file_operations(self.journal_directory)
                if pending:
                    self.events.put(("pending", pending))
                    return
                if action == "move":
                    assert destination is not None
                    plan = plan_move_operation(
                        self.records, [owner], destination, cancelled=self.cancelled
                    )
                else:
                    plan = plan_file_operation(
                        self.records, [owner], cancelled=self.cancelled
                    )
                self.events.put(("plan", plan))
            except Exception:  # noqa: BLE001 - worker reports a bounded UI outcome
                self.events.put(("error", "The files could not be checked safely."))

        return self._start(work, "vodforge-qt-library-plan")

    def confirm(self, current: Sequence[dict[str, Any]]) -> bool:
        plan = self.plan
        if self.phase != "preview" or plan is None or not self.eligible or self.busy:
            return False
        if tuple(map(record_fingerprint, current)) != plan.snapshot:
            self.phase = "error"
            self.status = "Library changed. Review the selected files again."
            return False
        self.phase = "working"
        self.uncertain = True
        self.status = "Updating your Library and media…"

        def work() -> None:
            result = None
            error = False
            try:
                if pending_file_operations(self.journal_directory):
                    raise ValueError("An earlier file change needs recovery")
                actual = load_history(self.history_path)
                if tuple(map(record_fingerprint, actual)) != plan.snapshot:
                    raise ValueError("Durable Library changed")
                if self.action == "move":
                    assert self.destination is not None
                    result = move_files(
                        plan,
                        actual,
                        self.destination,
                        self.history_path,
                        self.journal_directory,
                        cancelled=self.cancelled,
                    )
                else:
                    result = delete_files(
                        plan,
                        actual,
                        self.history_path,
                        self.journal_directory,
                        permanent=False,
                        cancelled=self.cancelled,
                    )
            except Exception:  # noqa: BLE001 - preserve recovery after any worker failure
                error = True
            try:
                actual = load_history(self.history_path)
                pending = pending_file_operations(self.journal_directory)
            except Exception:  # noqa: BLE001 - keep an uncertain receipt for review
                self.events.put(("error", "Library recovery needs attention."))
                return
            self.events.put(("finished", (result, actual, pending, error)))

        return self._start(work, "vodforge-qt-library-commit")

    def refresh_recovery(self) -> bool:
        if self.busy or self.phase in {"checking", "working"}:
            return False
        try:
            self.pending = pending_file_operations(self.journal_directory)
        except Exception:  # noqa: BLE001 - malformed private receipts block new work
            self.phase = "error"
            self.uncertain = True
            self.status = "Library file recovery needs attention."
            return False
        self.phase = "recovery" if self.pending else "idle"
        self.uncertain = bool(self.pending)
        self.status = (
            "Review the interrupted file change before starting new work."
            if self.pending
            else ""
        )
        return bool(self.pending)

    def recover(self, *, finish: bool) -> bool:
        if self.busy or len(self.pending) != 1 or (finish and not self.can_finish):
            return False
        receipt = self.pending[0].path
        self.phase = "working"
        self.uncertain = True
        self.status = "Verifying the saved file change…"

        def work() -> None:
            error = False
            try:
                actual = load_history(self.history_path)
                if finish:
                    recover_move_cleanup(
                        receipt, actual, self.history_path, cancelled=self.cancelled
                    )
                else:
                    keep_current_file_state(receipt, actual, self.history_path)
            except Exception:  # noqa: BLE001 - never infer file success from an error
                error = True
            try:
                actual = load_history(self.history_path)
                pending = pending_file_operations(self.journal_directory)
            except Exception:  # noqa: BLE001 - keep an uncertain receipt for review
                self.events.put(("error", "Library recovery needs attention."))
                return
            self.events.put(("recovered", (actual, pending, error)))

        return self._start(work, "vodforge-qt-library-recovery")

    def poll(self) -> bool:
        changed = False
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            changed = True
            if kind == "plan" and isinstance(payload, FileOperationPlan):
                self.plan = payload
                self.phase = "preview"
                counts = payload.counts
                ready, missing = counts.get("ready", 0), counts.get("missing", 0)
                if self.action == "move":
                    self.status = (
                        f"Move {ready} verified item(s) to {self.destination}?"
                    )
                else:
                    self.status = (
                        f"Move {ready} file(s) to Trash and remove {missing} "
                        "already-missing Library entry(s)?"
                    )
                if not self.eligible:
                    self.status = (
                        "No selected files could be verified. Nothing will change."
                    )
            elif kind == "pending":
                self.pending = payload
                self.plan = None
                self.phase = "recovery"
                self.status = "Review the interrupted file change first."
            elif kind == "finished":
                result, actual, pending, error = payload
                self.latest_history = actual
                self.pending = pending
                self.uncertain = bool(pending)
                self.plan = None
                self.phase = "recovery" if pending else "error" if error else "done"
                completed = (
                    sum(
                        state in {"completed", "entry_removed"}
                        for _, state in result.outcomes
                    )
                    if result is not None
                    else 0
                )
                self.status = (
                    "An interrupted file change needs review."
                    if pending
                    else "The file change could not be confirmed. Review Library."
                    if error or result is None
                    else "Library and media updated."
                    if completed
                    else "No files changed. Review the selected item."
                )
            elif kind == "recovered":
                actual, pending, error = payload
                self.latest_history = actual
                self.pending = pending
                self.uncertain = bool(pending)
                self.phase = "recovery" if pending else "error" if error else "done"
                self.status = (
                    "The file change still needs review."
                    if pending
                    else "The recovery could not be confirmed."
                    if error
                    else "Library file state confirmed."
                )
            else:
                self.phase = "error"
                self.status = str(payload)
        return changed

    def close(self) -> None:
        self.cancelled.set()
        if self.worker is not None and self.worker.is_alive():
            self.worker.join(timeout=10)
