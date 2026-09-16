from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

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

    @property
    def downloaded_count(self) -> int:
        return len(self.videos)


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
    terms = query.casefold().split()
    for index, record in enumerate(records):
        if not record.get("vodforge_output_dir"):
            continue
        creator = str(
            record.get("channel") or record.get("uploader") or "Unknown channel"
        )
        if channel and creator != channel:
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
            key = (creator, playlist)
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
                tuple(
                    sorted(
                        variants,
                        key=lambda index: {"MP4": 0, "Original audio": 1, "MP3": 2}.get(
                            str(records[index].get("vodforge_output_type")), 3
                        ),
                    )
                ),
            )
            for identity, variants in sorted(videos.items(), key=playlist_order)
        )
        rails.append(
            WatchRail(
                "\0".join(group),
                labels[group],
                "" if collection_mode else group[0],
                components,
            )
        )
    return tuple(
        sorted(rails, key=lambda rail: (rail.channel.casefold(), rail.title.casefold()))
    )
