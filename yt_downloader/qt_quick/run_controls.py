"""Pure presentation of existing run controls; never changes worker behavior."""

from __future__ import annotations

from queue import Queue
from typing import Any
from urllib.parse import parse_qs, urlsplit


class RunControlEvents(Queue):
    """Retain source-bearing events when the runtime consumes their envelopes.

    The existing runtime flattens job_log to text for display. Preserve its job
    identity for presentation without inspecting that text or changing delivery.
    Only the UI consumer writes/drains this side buffer.
    """

    def __init__(self) -> None:
        super().__init__()
        self.context_events: list[tuple[str, Any]] = []

    def get_nowait(self) -> Any:
        event = super().get_nowait()
        # Direct tuples are trusted consumer/test injections. Worker envelopes
        # remain opaque here until the runtime validates their execution owner.
        self.retain_context_event(event)
        return event

    def retain_context_event(self, event: tuple[str, Any]) -> None:
        """Retain raw context, or worker context admitted by the runtime."""
        if event[0] in {"job_log", "job_metadata"}:
            self.context_events.append(event)

    def take_context_events(self) -> list[tuple[str, Any]]:
        events, self.context_events = self.context_events, []
        return events


def _playlist(source: Any, info: dict[str, Any]) -> bool:
    if source.single_video_only:
        return False
    url = urlsplit(source.url)
    return bool(
        parse_qs(url.query).get("list")
        or url.path.rstrip("/").endswith(("/videos", "/streams", "/shorts"))
        or url.path.startswith(("/@", "/channel/", "/c/", "/user/"))
        or info.get("entries") is not None
        or info.get("playlist_id")
        or info.get("playlist_title")
    )


def _action(label: str, operation: str, description: str) -> dict[str, str]:
    return {"label": label, "operation": operation, "description": description}


class RunControlPresentation:
    """Track source evidence from existing job events under one execution owner.

    Batch child jobs are immutable replacements carrying the parent's run ID.
    Their source settings, rather than mutable composer inputs, determine scope.
    Parent batch logs retire prior child evidence between sources. No status text
    or progress percentage is interpreted as control authority.
    """

    def __init__(self) -> None:
        self.owner: Any = None
        self.source: Any = None
        self.info: dict[str, Any] = {}

    def observe(self, active: Any, kind: str, payload: Any) -> None:
        self._sync(active)
        if active is None or not isinstance(payload, dict):
            return
        source = payload.get("job")
        if source is None or source.run_id != active.run_id:
            return
        if kind == "job_log" and active.batch_mode and source is active:
            self.source = None
            self.info = {}
        elif kind in {"job_log", "job_metadata"}:
            if self.source is None or self.source.url != source.url:
                self.info = {}
            self.source = source
            if kind == "job_metadata" and isinstance(payload.get("info"), dict):
                self.info = dict(payload["info"])

    def _sync(self, active: Any) -> None:
        if self.owner is not active:
            self.owner = active
            self.source = None
            self.info = {}

    def actions(self, active: Any) -> list[dict[str, str]]:
        self._sync(active)
        if active is None:
            return []
        source = self.source or (None if active.batch_mode else active)
        playlist = source is not None and _playlist(
            source, self.info or source.preview_info or {}
        )
        retained = "Completed files and queued independent runs are kept."
        if active.batch_mode:
            stop = _action("Stop batch", "cancel", "Stop this batch. " + retained)
            if playlist:
                return [
                    _action(
                        "Skip this video",
                        "skip_item",
                        "Skip this video and continue the playlist. Completed files are kept.",
                    ),
                    _action(
                        "Skip playlist",
                        "skip_source",
                        "Skip the rest of this playlist and continue the batch. Completed files are kept.",
                    ),
                    stop,
                ]
            return [
                _action(
                    "Skip this link",
                    "skip_source",
                    "Skip this source link and continue the batch. Completed files are kept.",
                ),
                stop,
            ]
        if playlist:
            return [
                _action(
                    "Skip this video",
                    "skip_item",
                    "Skip this video and continue the playlist. Completed files are kept.",
                ),
                _action("Stop playlist", "cancel", "Stop this playlist. " + retained),
            ]
        return [_action("Cancel download", "cancel", "Stop this download. " + retained)]
