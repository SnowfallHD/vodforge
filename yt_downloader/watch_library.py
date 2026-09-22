from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .archive_browser import media_source_identity


@dataclass(frozen=True, slots=True)
class WatchVideo:
    key: str
    title: str
    indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class WatchRail:
    key: str
    title: str
    channel: str
    videos: tuple[WatchVideo, ...]
    channel_key: str = ""

    @property
    def downloaded_count(self) -> int:
        return len(self.videos)


def watch_variant_indices(
    records: Sequence[Mapping[str, Any]], indices: Sequence[int]
) -> tuple[int, ...]:
    """Retain every saved variant, with the same explicit playback preference."""
    priority = {"mp4": 0, "original audio": 1, "mp3": 2}
    return tuple(
        sorted(
            set(indices),
            key=lambda index: (
                priority.get(
                    str(records[index].get("vodforge_output_type") or "").casefold(), 3
                ),
                index,
            ),
        )
    )


def unique_watch_videos(
    records: Sequence[Mapping[str, Any]], videos: Sequence[WatchVideo]
) -> tuple[WatchVideo, ...]:
    merged: dict[str, WatchVideo] = {}
    for video in videos:
        previous = merged.get(video.key)
        merged[video.key] = WatchVideo(
            video.key,
            previous.title if previous else video.title,
            watch_variant_indices(
                records, (previous.indices if previous else ()) + video.indices
            ),
        )
    return tuple(merged.values())


def watch_media_kind(record: Mapping[str, Any]) -> str:
    return (
        "audio"
        if str(record.get("vodforge_output_type") or "").casefold()
        in {
            "mp3",
            "m4a",
            "original audio",
        }
        else "video"
    )


@dataclass(frozen=True, slots=True)
class WatchMediaSummary:
    count: int
    kind: str

    @property
    def label(self) -> str:
        noun = (
            "track"
            if self.kind == "audio"
            else "video"
            if self.kind == "video"
            else "item"
        )
        return f"{self.count} {noun}" + ("s" if self.count != 1 else "")

    @property
    def heading(self) -> str:
        return (
            "All Audio"
            if self.kind == "audio"
            else "All Videos"
            if self.kind == "video"
            else "All Media"
        )

    @property
    def fallback_description(self) -> str:
        return (
            "Your saved audio, ready to play."
            if self.kind == "audio"
            else "Your saved video, ready to watch."
            if self.kind == "video"
            else "Your saved media, ready to play."
        )


def watch_media_summary(
    records: Sequence[Mapping[str, Any]], videos: Sequence[WatchVideo]
) -> WatchMediaSummary:
    """Count unique source items and all saved kinds, including source variants."""
    unique: dict[str, set[int]] = {}
    for video in videos:
        unique.setdefault(video.key, set()).update(video.indices)
    kinds = {
        watch_media_kind(records[index])
        for indices in unique.values()
        for index in indices
    }
    return WatchMediaSummary(
        len(unique), next(iter(kinds)) if len(kinds) == 1 else "mixed"
    )


def channel_identity(record: Mapping[str, Any]) -> str:
    """Provider-scoped identity; display names never override a known channel ID."""
    provider = media_source_identity(record)[0]
    source_id = str(record.get("channel_id") or record.get("uploader_id") or "").strip()
    if source_id:
        return f"{provider}\\0id\\0{source_id}"
    raw_url = str(record.get("channel_url") or record.get("uploader_url") or "").strip()
    if raw_url:
        try:
            parts = urlsplit(raw_url)
            if parts.scheme in {"http", "https"} and parts.hostname:
                host = parts.hostname.casefold()
                if host in {"www.youtube.com", "m.youtube.com", "youtube.com"}:
                    host = "youtube.com"
                canonical = urlunsplit(("https", host, parts.path.rstrip("/"), "", ""))
                return f"{provider}\\0url\\0{canonical}"
        except ValueError:
            pass
    name = str(
        record.get("channel") or record.get("uploader") or "Unknown channel"
    ).strip()
    return f"{provider}\\0name\\0{name.casefold()}"


def channel_label(record: Mapping[str, Any]) -> str:
    return str(
        record.get("channel") or record.get("uploader") or "Unknown channel"
    ).strip()


def watch_rails(
    records: Sequence[Mapping[str, Any]],
    *,
    channel: str = "",
    collection_mode: bool = False,
    query: str = "",
) -> tuple[WatchRail, ...]:
    """Only canonical saved exports; playlists contain their own downloaded videos.

    Channel navigation is metadata organization, independent of storage paths.
    Personal categories remain single-membership logical collections.
    """
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    labels: dict[tuple[str, str], str] = {}
    creators: dict[str, str] = {}
    terms = query.casefold().split()
    for index, record in enumerate(records):
        if not record.get("vodforge_output_dir"):
            continue
        creator = channel_label(record)
        creator_key = channel_identity(record)
        creators.setdefault(creator_key, creator)
        if channel and channel not in {creator_key, creator}:
            continue
        text = " ".join(
            str(record.get(field) or "")
            for field in (
                "title",
                "channel",
                "uploader",
                "playlist_title",
                "vodforge_user_category",
                "vodforge_user_tags",
            )
        ).casefold()
        if any(term not in text for term in terms):
            continue
        if collection_mode:
            category = str(record.get("vodforge_user_category") or "").strip()
            if not category:
                continue
            key = ("collection", category.casefold())
            label = category
        else:
            playlist = str(
                record.get("playlist_id") or record.get("playlist_title") or ""
            )
            key = (creator_key, playlist)
            label = str(record.get("playlist_title") or playlist or "Saved videos")
        groups[key].append(index)
        labels[key] = label
    rails: list[WatchRail] = []
    for group, indices in groups.items():
        videos: dict[str, list[int]] = defaultdict(list)
        for index in indices:
            record = records[index]
            identity = "\\0".join(media_source_identity(record))
            videos[identity].append(index)

        def playlist_order(item: tuple[str, list[int]]) -> tuple[float, str]:
            record = records[item[1][0]]
            try:
                order = float(record.get("playlist_index") or 0)
            except (TypeError, ValueError):
                order = 0
            return order, str(record.get("title") or "").casefold()

        components = tuple(
            WatchVideo(
                identity,
                str(records[variants[0]].get("title") or "Saved media"),
                watch_variant_indices(records, variants),
            )
            for identity, variants in sorted(videos.items(), key=playlist_order)
        )
        rails.append(
            WatchRail(
                "\0".join(group),
                labels[group],
                "" if collection_mode else creators[group[0]],
                components,
                "" if collection_mode else group[0],
            )
        )
    return tuple(
        sorted(rails, key=lambda rail: (rail.channel.casefold(), rail.title.casefold()))
    )


@dataclass(frozen=True, slots=True)
class WatchChannel:
    name: str
    videos: tuple[WatchVideo, ...]
    key: str = ""


def watch_channels(
    records: Sequence[Mapping[str, Any]], *, query: str = ""
) -> tuple[WatchChannel, ...]:
    """A creator destination counts unique saved videos across its playlists."""
    channels: dict[str, dict[str, WatchVideo]] = {}
    labels: dict[str, str] = {}
    for rail in watch_rails(records, query=query):
        videos = channels.setdefault(rail.channel_key, {})
        labels.setdefault(rail.channel_key, rail.channel)
        for video in rail.videos:
            previous = videos.get(video.key)
            videos[video.key] = unique_watch_videos(
                records, (previous, video) if previous else (video,)
            )[0]
    return tuple(
        WatchChannel(labels[key], tuple(videos.values()), key)
        for key, videos in sorted(
            channels.items(), key=lambda item: (labels[item[0]].casefold(), item[0])
        )
    )
