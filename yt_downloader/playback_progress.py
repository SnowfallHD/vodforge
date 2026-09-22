"""Durable watched progress; only observed playback updates this private ledger."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .archive_browser import media_source_identity
from .playback_backend import PlaybackSnapshot
from .private_files import write_private_bytes

MAX_PROGRESS_ITEMS = 5000
MAX_PROGRESS_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class WatchedProgress:
    position: float
    duration: float
    updated_at: float
    completed: bool = False

    @property
    def fraction(self) -> float:
        return min(1.0, self.position / self.duration) if self.duration > 0 else 0.0


def progress_key(record: Mapping[str, Any]) -> str:
    preserved = record.get("vodforge_progress_key")
    if (
        isinstance(preserved, str)
        and len(preserved) == 64
        and all(character in "0123456789abcdef" for character in preserved)
    ):
        return preserved
    identity = media_source_identity(record)
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest()


def _progress(value: Any) -> WatchedProgress | None:
    if not isinstance(value, Mapping):
        return None
    try:
        position, duration, updated = (
            float(value[key]) for key in ("position", "duration", "updated_at")
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(number) for number in (position, duration, updated)):
        return None
    if duration <= 0 or position < 0 or updated < 0:
        return None
    return WatchedProgress(
        min(position, duration), duration, updated, value.get("completed") is True
    )


class PlaybackProgressOwner:
    """One active session token prevents late snapshots from another item's player."""

    def __init__(
        self,
        path: Path,
        *,
        clock: Callable[[], float] = time.time,
        diagnostic: Callable[[str], None] | None = None,
    ) -> None:
        self.path, self._clock = path, clock
        self._diagnostic = diagnostic or (lambda _: None)
        self._items: dict[str, WatchedProgress] = {}
        self._generation = 0
        self._session: tuple[int, str] | None = None
        self._resume_pending = 0.0
        self._dirty = False
        self._last_save = 0.0
        self._writable = True

    def load(self) -> None:
        try:
            if not self.path.exists():
                return
            if self.path.stat().st_size > MAX_PROGRESS_BYTES:
                raise ValueError("Oversized progress ledger")
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("schema_version") != 1:
                raise ValueError("Unsupported progress ledger")
            items = payload.get("items")
            if not isinstance(items, dict):
                raise TypeError("Missing progress map")
            self._items = {
                key: item
                for key, value in list(items.items())[:MAX_PROGRESS_ITEMS]
                if isinstance(key, str)
                and len(key) == 64
                and (item := _progress(value)) is not None
            }
        except (OSError, UnicodeError, ValueError, TypeError):
            self._writable = False
            self._diagnostic(
                "Saved watching progress could not be read; existing data was preserved."
            )

    def for_record(self, record: Mapping[str, Any]) -> WatchedProgress | None:
        return self._items.get(progress_key(record))

    def resume_position(self, record: Mapping[str, Any], duration: float = 0) -> float:
        item = self.for_record(record)
        if item is None or item.completed or item.position < 1:
            return 0.0
        if duration > 0 and abs(duration - item.duration) > max(5, duration * 0.02):
            return 0.0
        return min(item.position, duration if duration > 0 else item.duration)

    def begin(self, record: Mapping[str, Any], *, resume: bool = False) -> int:
        self.flush()
        self._generation += 1
        self._session = (self._generation, progress_key(record))
        self._resume_pending = self.resume_position(record) if resume else 0.0
        return self._generation

    def observe(self, session: int, snapshot: PlaybackSnapshot) -> bool:
        if self._session is None or session != self._session[0]:
            return False
        if snapshot.status not in {"Playing", "Paused", "Ended"}:
            return False
        item = _progress(
            {
                "position": snapshot.position,
                "duration": snapshot.duration,
                "updated_at": self._clock(),
                "completed": snapshot.status == "Ended",
            }
        )
        if item is None:
            return False
        # Invalid snapshots cannot mutate the resume gate. A provider duration
        # identifying a different edit deliberately starts a fresh progress record.
        if self._resume_pending:
            saved = self._items.get(self._session[1])
            if saved and abs(item.duration - saved.duration) > max(
                5, item.duration * 0.02
            ):
                self._resume_pending = 0.0
            elif abs(item.position - self._resume_pending) > 2:
                return False
            else:
                self._resume_pending = 0.0
        previous = self._items.get(self._session[1])
        if previous is not None and (
            previous.position,
            previous.duration,
            previous.completed,
        ) == (item.position, item.duration, item.completed):
            return True
        self._items[self._session[1]] = item
        self._dirty = True
        if len(self._items) > MAX_PROGRESS_ITEMS:
            oldest = min(self._items, key=lambda key: self._items[key].updated_at)
            self._items.pop(oldest)
        if self._clock() - self._last_save >= 5 or item.completed:
            self.flush()
        return True

    def accept_manual_position(self, session: int) -> None:
        """A deliberate seek/restart supersedes an outstanding resume target."""
        if self._session is not None and session == self._session[0]:
            self._resume_pending = 0.0

    def is_active(self, session: int) -> bool:
        return self._session is not None and session == self._session[0]

    def retire(self, session: int) -> bool:
        if not self.is_active(session):
            return False
        saved = self.flush()
        self._session = None
        return saved

    def flush(self) -> bool:
        if not self._writable:
            return False
        if not self._dirty:
            return True
        payload = {
            "schema_version": 1,
            "items": {key: asdict(value) for key, value in self._items.items()},
        }
        self._last_save = self._clock()
        try:
            encoded = json.dumps(
                payload, separators=(",", ":"), allow_nan=False
            ).encode()
            if len(encoded) > MAX_PROGRESS_BYTES:
                raise ValueError("Progress ledger exceeded its bound")
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            write_private_bytes(self.path, encoded)
        except (OSError, ValueError):
            self._diagnostic("Watching progress could not be saved.")
            return False
        self._dirty = False
        self._last_save = self._clock()
        return True
