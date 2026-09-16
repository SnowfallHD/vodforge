from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ArchiveWorkResult:
    generation: int
    kind: str
    value: Any = None
    error: str = ""
    elapsed_ms: int = 0


class ArchiveWorkOwner:
    """One bounded filesystem lane. Never calls Tk and never waits on UI shutdown.

    A blocked OS call keeps this sole worker occupied. Cancellation retires its
    result; repeated requests cannot create additional blocked threads.
    """

    def __init__(self) -> None:
        self._requests: queue.Queue[Any] = queue.Queue(maxsize=1)
        self._results: queue.Queue[ArchiveWorkResult] = queue.Queue(maxsize=2)
        self._generation = 0
        self._current: tuple[int, str, threading.Event] | None = None
        self._closed = False
        self._busy = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="VODForgeArchive", daemon=True
        )
        self._thread.start()

    @property
    def busy(self) -> bool:
        return (
            self._current is not None
            or self._busy.is_set()
            or not self._requests.empty()
        )

    def submit(self, kind: str, work: Callable[[threading.Event], Any]) -> int | None:
        if self._closed or self.busy:
            return None
        self._generation += 1
        cancelled = threading.Event()
        generation = self._generation
        self._current = (generation, kind, cancelled)
        self._requests.put_nowait((generation, kind, cancelled, work))
        return generation

    def cancel(self, *, retire_result: bool = True) -> None:
        if self._current:
            self._current[2].set()
        if retire_result:
            self._generation += 1
            self._current = None

    def poll(self) -> ArchiveWorkResult | None:
        while True:
            try:
                result = self._results.get_nowait()
            except queue.Empty:
                return None
            if (
                not self._closed
                and self._current
                and result.generation == self._current[0] == self._generation
            ):
                self._current = None
                return result

    def close(self) -> None:
        self.cancel()
        self._closed = True
        try:
            self._requests.put_nowait(None)
        except queue.Full:
            pass

    def _run(self) -> None:
        while not self._closed:
            request = self._requests.get()
            if request is None:
                return
            generation, kind, cancelled, work = request
            self._busy.set()
            started = time.monotonic()
            try:
                value = work(cancelled) if not cancelled.is_set() else None
                result = ArchiveWorkResult(
                    generation,
                    kind,
                    value=value,
                    elapsed_ms=round((time.monotonic() - started) * 1000),
                )
            except Exception as exc:  # noqa: BLE001 - closed diagnostic category, no raw path/error
                result = ArchiveWorkResult(
                    generation,
                    kind,
                    error=type(exc).__name__,
                    elapsed_ms=round((time.monotonic() - started) * 1000),
                )
            finally:
                self._busy.clear()
            if self._closed:
                return
            # Only one active request exists; retired unread results stay bounded.
            try:
                self._results.put_nowait(result)
            except queue.Full:
                try:
                    self._results.get_nowait()
                except queue.Empty:
                    pass
                self._results.put_nowait(result)
