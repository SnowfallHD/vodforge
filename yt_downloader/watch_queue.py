"""One ephemeral playback queue; source identities outlive row positions.

The queue owns order and continuation intent. The application resolves/open files,
and the current player alone owns media, audio and the provider's Ended signal.
"""

from __future__ import annotations

import logging
import random
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Protocol

from .archive_browser import media_source_identity
from .failure_diagnostics import FailureDiagnostic
from .watch_library import watch_variant_indices


def queue_media_key(record: Mapping[str, Any]) -> str:
    return "\\0".join(media_source_identity(record))


@dataclass(frozen=True, slots=True)
class QueueToken:
    generation: int
    position: int
    key: str


@dataclass(frozen=True, slots=True)
class QueueContinuity:
    volume: int
    unmuted_volume: int
    presentation: str


def queue_count_bucket(count: int) -> str:
    return (
        "0"
        if count == 0
        else "1"
        if count == 1
        else "2_5"
        if count <= 5
        else "6_20"
        if count <= 20
        else "21_100"
        if count <= 100
        else "101_plus"
    )


class QueueObserver(Protocol):
    def __call__(
        self,
        action: str,
        operation: str,
        dimensions: dict[str, str],
        *,
        failure_detail: FailureDiagnostic | None = None,
    ) -> None: ...


class WatchQueueOwner:
    def __init__(
        self,
        *,
        records: Callable[[], Sequence[Mapping[str, Any]]],
        open_record: Callable[[dict[str, Any], QueueToken], None],
        schedule: Callable[[Callable[[], None]], Any],
        observe: QueueObserver,
        unavailable: Callable[[], None],
        shuffle: Callable[[list[str]], None] = random.shuffle,
    ) -> None:
        self._records = records
        self._open = open_record
        self._schedule = schedule
        self._observe = observe
        self._unavailable = unavailable
        self._shuffle = shuffle
        self._generation = 0
        self._keys: tuple[str, ...] = ()
        self._position = 0
        self._completed_count = 0
        self._player: Any = None
        self._ended = False
        self._played = False
        self._started = self._advanced = False
        self._retiring = 0
        self._observer_failures = 0
        self._operation = ""
        self._kind = "playlist"
        self._order = "ordered"
        self.continuity: QueueContinuity | None = None

    @property
    def token(self) -> QueueToken | None:
        if not self._keys:
            return None
        return QueueToken(self._generation, self._position, self._keys[self._position])

    @property
    def remaining_keys(self) -> tuple[str, ...] | None:
        return self._keys[self._position + 1 :] if self._keys else None

    def owns(self, token: QueueToken | None) -> bool:
        return token is not None and token == self.token

    def start(self, keys: Sequence[str], *, kind: str, shuffled: bool = False) -> None:
        self.cancel("cancelled")
        distinct = list(dict.fromkeys(keys))
        if not distinct:
            return
        if shuffled:
            self._shuffle(distinct)
        self._generation += 1
        self._keys, self._position = tuple(distinct), 0
        self._kind = "channel" if kind == "channel" else "playlist"
        self._order = "shuffle" if shuffled else "ordered"
        self._operation = str(uuid.uuid4())
        self._ended, self._played, self._player, self.continuity = (
            False,
            False,
            None,
            None,
        )
        self._started = self._advanced = False
        self._completed_count = 0
        self._emit("requested")
        self._open_current()

    def _resolve(self, key: str) -> tuple[dict[str, Any] | None, str]:
        records = self._records()
        matching = [
            index
            for index, record in enumerate(records)
            if queue_media_key(record) == key
        ]
        if not matching:
            return None, "source_removed"
        indices = [
            index for index in matching if records[index].get("vodforge_output_dir")
        ]
        ordered = watch_variant_indices(records, indices)
        return (
            (dict(records[ordered[0]]), "")
            if ordered
            else (None, "saved_output_missing")
        )

    def _open_current(self) -> None:
        token = self.token
        if token is None:
            return
        record, reason = self._resolve(token.key)
        if record is None:
            self.cancel("failed", failure_boundary="metadata", failure_reason=reason)
            self._unavailable()
            return
        self._open(record, token)

    def attach(
        self, player: Any, record: Mapping[str, Any], token: QueueToken | None
    ) -> None:
        if (
            self.owns(token)
            and token is not None
            and token.key == queue_media_key(record)
        ):
            self._player = player
            self._ended = False
            self._played = False

    def present(
        self,
        player: Any,
        status: str,
        *,
        continuity: QueueContinuity | None = None,
        failure_detail: FailureDiagnostic | None = None,
        failure_boundary: str = "provider",
    ) -> None:
        if player is not self._player or self.token is None or self._ended:
            return
        if status == "Playing":
            if not self._played:
                self._played = True
                if not self._started:
                    self._started = True
                    self._emit("started")
            return
        if status == "Failed":
            self.cancel(
                "failed",
                failure_boundary=failure_boundary,
                failure_reason=failure_detail.reason
                if failure_detail
                else "provider_failed",
                failure_detail=failure_detail,
            )
            return
        if status != "Ended":
            return
        if not self._played:
            self.cancel(
                "failed",
                failure_boundary="unexpected_end",
                failure_reason="ended_before_playing",
            )
            return
        self._ended = True
        # Completion is a provider fact; canceling the deferred opening cannot erase it.
        self._completed_count += 1
        token = self.token
        self.continuity = continuity
        self._schedule(lambda: self._advance(token))

    def _advance(self, token: QueueToken | None) -> None:
        if not self.owns(token) or not self._ended:
            return
        if self._position + 1 == len(self._keys):
            self.cancel("completed")
            return
        self._position += 1
        self._ended, self._played, self._player = False, False, None
        self._observe_advance()
        self._open_current()

    def jump(self, key: str, *, continuity: QueueContinuity | None = None) -> bool:
        if not self._keys or key not in self._keys[self._position + 1 :]:
            return False
        self.continuity = continuity
        self._position = self._keys.index(key)
        self._ended, self._played, self._player = False, False, None
        self._observe_advance()
        self._open_current()
        return True

    def _observe_advance(self) -> None:
        # One first-transition event per queue, keeping even huge queues within
        # the operation event budget and retaining their terminal observation.
        if not self._advanced:
            self._advanced = True
            self._emit("advanced")

    @contextmanager
    def retiring_player(self) -> Iterator[None]:
        """Only the synchronous old-player shutdown is a queue handoff."""
        self._retiring += 1
        try:
            yield
        finally:
            self._retiring -= 1

    def player_closed(self) -> None:
        if not self._retiring:
            self.cancel("cancelled")

    def cancel(
        self,
        action: str = "cancelled",
        *,
        failure_boundary: str = "unknown",
        failure_reason: str = "unknown",
        failure_detail: FailureDiagnostic | None = None,
    ) -> None:
        if self._keys:
            self._emit(
                action,
                failure_boundary=failure_boundary,
                failure_reason=failure_reason,
                failure_detail=failure_detail,
            )
        self._generation += 1
        self._keys = ()
        self._player = None
        self._ended = self._played = False
        self.continuity = None

    def _emit(
        self,
        action: str,
        *,
        failure_boundary: str = "unknown",
        failure_reason: str = "unknown",
        failure_detail: FailureDiagnostic | None = None,
    ) -> None:
        dimensions = {
            "queue_kind": self._kind,
            "queue_order": self._order,
            "item_count_bucket": queue_count_bucket(len(self._keys)),
            "queue_position_bucket": queue_count_bucket(self._position + 1),
            "queue_completed_bucket": queue_count_bucket(self._completed_count),
        }
        if action == "failed":
            dimensions.update(
                queue_failure_boundary=failure_boundary,
                queue_failure_reason=failure_reason,
            )
        try:
            if failure_detail is None:
                self._observe(action, self._operation, dimensions)
            else:
                self._observe(
                    action, self._operation, dimensions, failure_detail=failure_detail
                )
        except Exception:  # noqa: BLE001 - optional telemetry cannot interrupt playback
            if self._observer_failures < 3:
                logging.getLogger(__name__).warning("Playback queue observation failed")
            self._observer_failures += 1
