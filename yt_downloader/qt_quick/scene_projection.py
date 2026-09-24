"""Qt data adapter for the current Tk Library and Watch scene owners.

Grouping and identity stay with watch_library and history. This module only
serializes those existing projections for QML.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from yt_downloader.history import history_archive_owner
from yt_downloader.library_state import format_duration
from yt_downloader.watch_library import (
    unique_watch_videos,
    watch_channels,
    watch_media_kind,
    watch_media_summary,
    watch_rails,
)

Artwork = Callable[[dict[str, Any], tuple[int, int], str], str]


def _defer_artwork(_record: dict[str, Any], _size: tuple[int, int], _role: str) -> str:
    return ""


def _media(record: dict[str, Any], index: int, artwork: Artwork) -> dict[str, Any]:
    return {
        "index": index,
        "owner": history_archive_owner(record),
        "title": str(record.get("title") or "Saved media"),
        "creator": str(
            record.get("channel") or record.get("uploader") or "Local media"
        ),
        "type": str(record.get("vodforge_output_type") or "MP4"),
        "artwork": artwork(record, (320, 180), "media"),
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
        "owner": history_archive_owner(record),
        "title": title,
        "count": count,
        "kind": kind,
        "artwork": artwork(
            record,
            (160, 160) if kind == "channel" else (480, 200),
            "avatar" if kind == "channel" else "playlist",
        ),
    }


def _library_group(
    group: Any, kind: str, records: Sequence[dict[str, Any]], artwork: Artwork
) -> dict[str, Any]:
    indices = tuple(index for video in group.videos for index in video.indices)
    first = records[indices[0]]
    audio = sum(watch_media_kind(records[index]) == "audio" for index in indices)
    result = _group(
        first,
        group.key,
        group.name if kind == "channel" else group.title,
        len(indices),
        kind,
        artwork,
    )
    result["videoCount"] = len(indices) - audio
    result["audioCount"] = audio
    result["owners"] = [history_archive_owner(records[index]) for index in indices]
    parts = [f"{len(indices)} item" + ("s" if len(indices) != 1 else "")]
    if len(indices) - audio:
        videos = len(indices) - audio
        parts.append(f"{videos} video" + ("s" if videos != 1 else ""))
    if audio:
        parts.append(f"{audio} audio")
    result["summary"] = " · ".join(parts)
    return result


def library_scene(
    records: Sequence[dict[str, Any]],
    route: str,
    group_key: str = "",
    group_kind: str = "",
    artwork: Artwork = lambda _record, _size, _role: "",
    query: str = "",
    category: str = "",
    sort: str = "recent",
    *,
    defer_media_artwork: bool = False,
    defer_group_artwork: bool = False,
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
    group_image = _defer_artwork if defer_group_artwork else artwork
    if route == "channels":
        groups = [
            _library_group(channel, "channel", records, group_image)
            for channel in channels
            if channel.videos
        ]
    elif route in {"playlists", "collections", "home"}:
        chosen = collections if route == "collections" else playlists
        if route == "home":
            chosen = collections or playlists
        groups = [
            _library_group(
                rail,
                "collection" if chosen is collections else "playlist",
                records,
                group_image,
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
    if route == "home":
        # The home scene is one recent row; avoid acquiring artwork for rows
        # that cannot appear there. QML applies the current column count.
        media = media[:5]
    media_image = _defer_artwork if defer_media_artwork else artwork
    return {
        "route": route,
        "counts": counts,
        "groups": groups,
        "media": [_media(record, index, media_image) for index, record in media],
        "groupTitle": group_title,
    }


def watch_scene(
    records: Sequence[dict[str, Any]],
    route: str,
    artwork: Artwork = lambda _record, _size, _role: "",
    group_key: str = "",
    group_kind: str = "",
    query: str = "",
    progress_for: Callable[[dict[str, Any]], Any] | None = None,
    *,
    defer_media_artwork: bool = False,
    defer_group_artwork: bool = False,
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
    media_image = _defer_artwork if defer_media_artwork else artwork
    group_image = _defer_artwork if defer_group_artwork else artwork
    media = [
        {
            **_media(records[video.indices[0]], video.indices[0], media_image),
            "queueKey": video.key,
        }
        for video in videos
        if video.indices
    ]
    featured = next(
        (
            video
            for video in videos
            if progress_for is not None
            and (progress := progress_for(records[video.indices[0]])) is not None
            and not progress.completed
            and progress.position >= 1
        ),
        videos[0] if videos else None,
    )
    hero_record = records[featured.indices[0]] if featured is not None else None
    hero_progress = (
        progress_for(hero_record)
        if hero_record is not None and progress_for is not None
        else None
    )
    hero_resume = bool(
        hero_progress is not None
        and not hero_progress.completed
        and hero_progress.position >= 1
    )
    hero = (
        {
            **_media(hero_record, featured.indices[0], artwork),
            "description": str(hero_record.get("description") or ""),
            "duration": format_duration(hero_record.get("duration")),
            "kind": watch_media_kind(hero_record),
            "playlist": next(
                (rail.title for rail in playlists if featured in rail.videos), ""
            ),
            "resume": hero_resume,
            "progress": hero_progress.fraction if hero_resume else 0.0,
            "progressLabel": (
                format_duration(hero_progress.position)
                + " / "
                + format_duration(hero_progress.duration)
                if hero_resume
                else ""
            ),
            "backdrop": artwork(hero_record, (1100, 400), "media"),
        }
        if hero_record is not None and featured is not None
        else {}
    )
    group_record = (
        records[selected.videos[0].indices[0]]
        if selected is not None and selected.videos
        else None
    )
    group_playlist_count = (
        len(watch_rails(records, channel=selected.key))
        if selected is not None and group_kind == "channel"
        else 0
    )
    group_summary = (
        watch_media_summary(records, selected.videos).label
        if selected is not None
        else ""
    )
    group_creators = (
        {
            str(
                records[video.indices[0]].get("channel")
                or records[video.indices[0]].get("uploader")
                or ""
            )
            for video in selected.videos
            if video.indices
        }
        - {""}
        if selected is not None and group_kind != "channel"
        else set()
    )
    return {
        "route": effective_route,
        "query": query,
        "groupKind": group_kind,
        "groupTitle": (selected.name if group_kind == "channel" else selected.title)
        if selected is not None
        else "",
        "groupDescription": (
            str(group_record.get("channel_description") or "")
            if group_record is not None and group_kind == "channel"
            else ""
        ),
        "groupCount": len(videos),
        "groupPlaylistCount": group_playlist_count,
        "groupSubtitle": (
            (next(iter(group_creators)) + "  ·  " if len(group_creators) == 1 else "")
            + group_summary
            + " saved"
            if selected is not None and group_kind != "channel"
            else ""
        ),
        "groupCountLabel": (
            group_summary
            + "  ·  "
            + f"{group_playlist_count} playlist"
            + ("s" if group_playlist_count != 1 else "")
            if selected is not None and group_kind == "channel"
            else ""
        ),
        "groupAvatar": artwork(group_record, (150, 150), "avatar")
        if group_record is not None and group_kind == "channel"
        else "",
        "groupBanner": artwork(group_record, (1100, 350), "banner")
        if group_record is not None and group_kind == "channel"
        else "",
        "groupFirstOwner": history_archive_owner(group_record)
        if group_record is not None
        else "",
        "hero": hero,
        "channels": [
            _group(
                records[channel.videos[0].indices[0]],
                channel.key,
                channel.name,
                len(channel.videos),
                "channel",
                group_image,
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
                group_image,
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
                group_image,
            )
            for rail in collections
            if rail.videos
        ],
        "videos": media,
        "queueKeys": [video.key for video in videos],
        "queueKind": "channel" if group_kind == "channel" else "playlist",
    }
