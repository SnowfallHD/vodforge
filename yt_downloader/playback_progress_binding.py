"""Connect observed player state to durable Watch progress and one resume attempt."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping
from typing import Any

from .playback_backend import MediaPlayerError, PlaybackSnapshot
from .playback_progress import PlaybackProgressOwner


class PlaybackProgressBinding:
    """A player lifetime, fenced by both the ledger session and loaded media path.

    Startup snapshots never overwrite a saved resume point. A successful command
    is not proof of a seek: a later provider snapshot must reach the saved point.
    """

    def __init__(
        self,
        owner: PlaybackProgressOwner,
        record: Mapping[str, Any],
        *,
        snapshot: PlaybackSnapshot,
        seek: Callable[[float], PlaybackSnapshot],
        observe: Callable[..., None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._owner, self._record = owner, dict(record)
        self._path, self._seek = snapshot.path, seek
        self._observe = observe or (lambda *_args, **_kwargs: None)
        self._clock = clock
        self._session = owner.begin(record, resume=True)
        self._target = owner.resume_position(record)
        self._state = "waiting" if self._target else "recording"
        self._requested_at = 0.0
        self._recorded = False
        self._closed = False

    @property
    def notice(self) -> str:
        if self._state == "failed":
            return "Could not resume. Your saved place is still available."
        return ""

    def _emit(self, action: str, reason: str | None = None) -> None:
        try:
            self._observe(
                action, dimensions={"resume_reason": reason} if reason else {}
            )
        except Exception:  # noqa: BLE001, S110  # nosec B110 - optional telemetry cannot break playback
            pass

    def _finish_resume(self, action: str, reason: str | None = None) -> None:
        self._state = "recording" if action == "resume_completed" else "failed"
        self._emit(action, reason)

    def present(self, snapshot: PlaybackSnapshot) -> None:
        if self._closed or not self._owner.is_active(self._session):
            return
        if self._path is None or snapshot.path != self._path:
            return
        if snapshot.status == "Failed":
            if self._state in {"waiting", "seeking"}:
                self._finish_resume("resume_failed", "provider_failed")
            return
        valid = (
            snapshot.status in {"Playing", "Paused", "Ended"}
            and math.isfinite(snapshot.position)
            and math.isfinite(snapshot.duration)
            and snapshot.position >= 0
            and snapshot.duration > 0
        )
        if not valid:
            return
        if self._state == "waiting":
            if snapshot.status not in {"Playing", "Paused"}:
                return
            target = self._owner.resume_position(self._record, snapshot.duration)
            if not target:
                self._owner.accept_manual_position(self._session)
                self._state = "recording"
                self._emit("resume_cancelled", "media_changed")
            else:
                self._target = target
                self._state = "seeking"
                self._requested_at = self._clock()
                self._emit("resume_requested")
                try:
                    result = self._seek(target)
                except MediaPlayerError:
                    self._finish_resume("resume_failed", "seek_rejected")
                else:
                    if result.status == "Failed":
                        self._finish_resume("resume_failed", "seek_rejected")
                # The pre-seek frame cannot authorize the new saved position.
                return
        if self._state == "seeking":
            if abs(snapshot.position - self._target) <= 2:
                self._finish_resume("resume_completed")
            elif self._clock() - self._requested_at >= 5:
                self._finish_resume("resume_failed", "seek_timeout")
            else:
                return
        if self._state != "recording":
            return
        self._recorded = self._owner.observe(self._session, snapshot) or self._recorded

    def manual_seek(self, command_result: PlaybackSnapshot) -> None:
        if (
            self._closed
            or not self._owner.is_active(self._session)
            or command_result.status == "Failed"
        ):
            return
        if self._state in {"waiting", "seeking"}:
            self._emit("resume_cancelled", "manual_seek")
        self._state = "recording"
        self._owner.accept_manual_position(self._session)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if not self._owner.is_active(self._session):
            return
        if self._state in {"waiting", "seeking"}:
            self._emit("resume_cancelled", "closed")
        saved = self._owner.retire(self._session)
        if self._recorded:
            self._emit("progress_saved" if saved else "progress_save_failed")
