"""Library ledger recovery and deferred publication without a GUI host."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .archive_observations import history_operation
from .history import (
    HistoryError,
    load_history,
    save_history,
    stage_history_mutation,
    upsert_history,
)


class LibraryHistory:
    def __init__(self, path: Path, telemetry: Any = None) -> None:
        self.history_path = path
        self.product_telemetry = telemetry
        self.download_history: list[dict[str, Any]] = []
        self.blocked = False
        self.notice = ""
        self._deferred: dict[Any, Callable[[], None]] = {}

    def _observe(
        self, action: str, operation: str, boundary: str, **kwargs: Any
    ) -> None:
        history_operation(self.product_telemetry, action, operation, boundary, **kwargs)

    def load(self) -> bool:
        operation = str(uuid.uuid4())
        self._observe("started", operation, "startup")
        try:
            self.download_history = load_history(
                self.history_path,
                on_recovered=lambda count: self._observe(
                    "recovered", operation, "startup", item_count=count
                ),
            )
        except (HistoryError, OSError, ValueError) as error:
            self.blocked = True
            self.download_history = []
            self.notice = "Library data needs attention before new work. The existing files were left untouched."
            self._observe(
                "failed",
                operation,
                "startup",
                error=error
                if isinstance(error, HistoryError)
                else HistoryError("Library recovery needs attention."),
            )
            return False
        self.blocked = False
        self.notice = ""
        self._observe("completed", operation, "startup")
        return True

    def defer(
        self, key: Any, callback: Callable[[], None], *, mutation: dict[str, Any]
    ) -> None:
        operation = str(uuid.uuid4())
        self._observe("started", operation, "defer")
        try:
            stage_history_mutation(self.history_path, mutation)
        except HistoryError as error:
            self._observe("failed", operation, "defer", error=error)
            raise
        self._deferred[key] = callback
        self._observe("deferred", operation, "defer")

    def publish(self, records: list[dict[str, Any]]) -> None:
        if self.blocked:
            raise HistoryError("History recovery must finish before new work.")
        save_history(self.history_path, records)
        self.download_history = records

    def record(self, info: dict[str, Any], output_dir: Path) -> None:
        self.publish(
            upsert_history(
                self.download_history, info, output_dir, replace_missing_media=True
            )
        )

    def flush(self) -> bool:
        callbacks, self._deferred = self._deferred, {}
        operation = str(uuid.uuid4())
        self._observe("started", operation, "settlement")
        try:
            self.download_history = load_history(
                self.history_path,
                on_recovered=lambda count: self._observe(
                    "recovered", operation, "settlement", item_count=count
                ),
            )
            for callback in callbacks.values():
                callback()
            self.download_history = load_history(self.history_path)
        except HistoryError as error:
            self.blocked = True
            self.notice = "History recovery needs attention. Pending updates were retained for the next launch."
            self._observe("failed", operation, "settlement", error=error)
            return False
        self._observe("completed", operation, "settlement")
        return True
