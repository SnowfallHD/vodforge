"""Qt data adapter for the current Tk Library and Watch scene owners.

Grouping and identity stay with watch_library and history. This module only
serializes those existing projections for QML.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from yt_downloader.history import history_archive_owner
from yt_downloader.watch_library import unique_watch_videos, watch_channels, watch_rails

Artwork = Callable[[dict[str, Any]], str]


def _media(record: dict[str, Any], index: int, artwork: Artwork) -> dict[str, Any]:
    return {
        "index": index,
        "owner": history_archive_owner(record),
        "title": str(record.get("title") or "Saved media"),
        "creator": str(
            record.get("channel") or record.get("uploader") or "Local media"
        ),
        "type": str(record.get("vodforge_output_type") or "MP4"),
        "artwork": artwork(record),
        "category": str(record.get("vodforge_user_category") or ""),
    }


def _group(
    record: dict[str, Any],
    key: str,
    title: str,
    count: int,
    kind: str,
    artwork: Artwork,
) -> dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "count": count,
        "kind": kind,
        "artwork": artwork(record),
    }


def library_scene(
    records: Sequence[dict[str, Any]],
    route: str,
    group_key: str = "",
    group_kind: str = "",
    artwork: Artwork = lambda _record: "",
    query: str = "",
    category: str = "",
    sort: str = "recent",
) -> dict[str, Any]:
    """Use the Tk scene's saved-item, channel, playlist and collection definitions."""
    saved = [
        (index, record)
        for index, record in enumerate(records)
        if record.get("vodforge_output_dir")
    ]
    audio = [
        (index, record)
        for index, record in saved
        if str(record.get("vodforge_output_type") or "").casefold()
        in {"mp3", "m4a", "original audio"}
    ]
    audio_indices = {index for index, _ in audio}
    channels = watch_channels(records, query=query)
    playlists = watch_rails(records, query=query)
    collections = watch_rails(records, collection_mode=True, query=query)
    counts = {
        "all": len(saved),
        "channels": len(channels),
        "playlists": len(playlists),
        "videos": len(saved) - len(audio),
        "audio": len(audio),
    }
    groups: list[dict[str, Any]] = []
    if route == "channels":
        groups = [
            _group(
                records[channel.videos[0].indices[0]],
                channel.key,
                channel.name,
                len(channel.videos),
                "channel",
                artwork,
            )
            for channel in channels
            if channel.videos
        ]
    elif route in {"playlists", "collections", "home"}:
        chosen = collections if route == "collections" else playlists
        if route == "home":
            chosen = collections or playlists
        groups = [
            _group(
                records[rail.videos[0].indices[0]],
                rail.key,
                rail.title,
                len(rail.videos),
                "collection" if chosen is collections else "playlist",
                artwork,
            )
            for rail in chosen
            if rail.videos
        ]
    group_title = ""
    if route == "audio":
        media = audio
    elif route == "videos":
        media = [
            (index, record) for index, record in saved if index not in audio_indices
        ]
    elif route == "group":
        candidates = (
            channels
            if group_kind == "channel"
            else collections
            if group_kind == "collection"
            else playlists
        )
        selected = next((group for group in candidates if group.key == group_key), None)
        group_title = (
            (selected.name if group_kind == "channel" else selected.title)
            if selected is not None
            else ""
        )
        indices = (
            {index for video in selected.videos for index in video.indices}
            if selected is not None
            else set()
        )
        media = [(index, record) for index, record in saved if index in indices]
    elif route in {"channels", "playlists", "collections"}:
        media = []
    else:
        media = saved
    if query:
        terms = query.casefold().split()
        media = [
            (index, record)
            for index, record in media
            if all(
                term
                in " ".join(
                    str(record.get(field) or "")
                    for field in (
                        "title",
                        "channel",
                        "uploader",
                        "description",
                        "vodforge_user_note",
                        "vodforge_user_tags",
                        "vodforge_user_category",
                    )
                ).casefold()
                for term in terms
            )
        ]
    if category:
        media = [
            (index, record)
            for index, record in media
            if str(record.get("vodforge_user_category") or "") == category
        ]
    if sort == "title":
        media.sort(key=lambda pair: str(pair[1].get("title") or "").casefold())
    return {
        "route": route,
        "counts": counts,
        "groups": groups,
        "media": [_media(record, index, artwork) for index, record in media],
        "groupTitle": group_title,
    }


def watch_scene(
    records: Sequence[dict[str, Any]],
    route: str,
    artwork: Artwork = lambda _record: "",
    group_key: str = "",
    group_kind: str = "",
    query: str = "",
) -> dict[str, Any]:
    query = query.strip()
    effective_route = "videos" if query else route
    channels = watch_channels(records, query=query)
    playlists = watch_rails(records, query=query)
    collections = watch_rails(records, collection_mode=True, query=query)
    selected = None
    if effective_route == "group":
        candidates = (
            channels
            if group_kind == "channel"
            else collections
            if group_kind == "collection"
            else playlists
        )
        selected = next((group for group in candidates if group.key == group_key), None)
    source_videos = (
        selected.videos
        if selected is not None
        else ()
        if effective_route == "group"
        else tuple(video for rail in playlists for video in rail.videos)
    )
    videos = unique_watch_videos(records, source_videos)
    media = [
        {
            **_media(records[video.indices[0]], video.indices[0], artwork),
            "queueKey": video.key,
        }
        for video in videos
        if video.indices
    ]
    return {
        "route": effective_route,
        "query": query,
        "groupTitle": (selected.name if group_kind == "channel" else selected.title)
        if selected is not None
        else "",
        "hero": media[0] if media else {},
        "channels": [
            _group(
                records[channel.videos[0].indices[0]],
                channel.key,
                channel.name,
                len(channel.videos),
                "channel",
                artwork,
            )
            for channel in channels
            if channel.videos
        ],
        "playlists": [
            _group(
                records[rail.videos[0].indices[0]],
                rail.key,
                rail.title,
                len(rail.videos),
                "playlist",
                artwork,
            )
            for rail in playlists
            if rail.videos
        ],
        "collections": [
            _group(
                records[rail.videos[0].indices[0]],
                rail.key,
                rail.title,
                len(rail.videos),
                "collection",
                artwork,
            )
            for rail in collections
            if rail.videos
        ],
        "videos": media,
        "queueKeys": [video.key for video in videos],
        "queueKind": "channel" if group_kind == "channel" else "playlist",
    }
