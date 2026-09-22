"""Saved-media recommendations retain canonical source and variant ownership."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .archive_browser import archive_row_owner, media_source_identity
from .watch_library import WatchVideo, unique_watch_videos, watch_rails


@dataclass(frozen=True, slots=True)
class PlayerRelatedPlan:
    up_next: tuple[WatchVideo, ...]
    recent: tuple[WatchVideo, ...]


def player_related_plan(
    records: Sequence[Mapping[str, Any]],
    current: Mapping[str, Any],
    queue_keys: Sequence[str] | None = None,
) -> PlayerRelatedPlan:
    rails = watch_rails(records)
    all_videos = unique_watch_videos(
        records, tuple(video for rail in rails for video in rail.videos)
    )
    if queue_keys is not None:
        by_key = {video.key: video for video in all_videos}
        return PlayerRelatedPlan(
            tuple(by_key[key] for key in queue_keys if key in by_key),
            tuple(sorted(all_videos, key=lambda video: min(video.indices))),
        )
    identity = media_source_identity(current)
    other = tuple(
        video
        for video in all_videos
        if media_source_identity(records[video.indices[0]]) != identity
    )
    # A lone saved item already occupies the player; do not manufacture rails.
    if not other:
        return PlayerRelatedPlan((), ())
    current_owner = archive_row_owner(current)
    selected = next(
        (
            (rail, offset)
            for rail in rails
            for offset, video in enumerate(rail.videos)
            if any(
                archive_row_owner(records[index]) == current_owner
                for index in video.indices
            )
        ),
        None,
    )
    remaining = selected[0].videos[selected[1] + 1 :] if selected else ()
    # These are user-selectable suggestions; this projection does not autoplay.
    suggestions = unique_watch_videos(records, (*remaining, *other))
    return PlayerRelatedPlan(
        suggestions,
        tuple(sorted(all_videos, key=lambda video: min(video.indices))),
    )
