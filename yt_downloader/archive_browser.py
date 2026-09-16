from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

from .archive_paths import ArchivePath
from .history import history_archive_owner
from .library_state import PROJECTION_OWNER_KEY, PROJECTION_OWNER_KIND_KEY
from .run_identity import metadata_output_profile

PAGE_SIZE = 48


@dataclass(frozen=True, slots=True)
class ArchiveComponent:
    key: str
    kind: Literal["folder", "media", "activity"]
    title: str
    detail: str
    indices: tuple[int, ...]
    path: ArchivePath | None = None


def archive_row_owner(record: Mapping[str, Any]) -> str:
    return str(record.get(PROJECTION_OWNER_KEY) or history_archive_owner(dict(record)))


def archive_directory(record: Mapping[str, Any]) -> ArchivePath | None:
    try:
        return ArchivePath.parse(str(record.get("vodforge_output_dir") or ""))
    except ValueError:
        return None


def _media_folder(record: Mapping[str, Any], directory: ArchivePath) -> ArchivePath:
    variant = str(record.get("vodforge_output_variant") or "")
    return directory.parent if variant and directory.name == variant else directory


def media_source_identity(record: Mapping[str, Any]) -> tuple[str, str]:
    """Group versions within a provider; never equate cross-provider IDs."""
    url = str(record.get("webpage_url") or record.get("original_url") or "")
    try:
        provider = (urlsplit(url).hostname or "").casefold()
    except ValueError:
        provider = ""
    if provider in {
        "youtu.be",
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
    }:
        provider = "youtube"
    source = str(record.get("id") or url or archive_row_owner(record))
    return provider, source


def _source_key(record: Mapping[str, Any], index: int) -> tuple[str, str, str]:
    return (*media_source_identity(record), str(record.get("playlist_id") or ""))


class ArchiveBrowserModel:
    """A metadata-only index; all UI component work is bounded by PAGE_SIZE."""

    def __init__(self) -> None:
        self.records: tuple[Mapping[str, Any], ...] = ()
        self.visible: tuple[int, ...] = ()
        self.path: ArchivePath | None = None
        self.mode: Literal["folders", "all", "activity"] = "folders"
        self.page = 0
        self.selected_owner = ""
        self._directories: dict[int, ArchivePath] = {}
        self.locations: tuple[ArchiveComponent, ...] = ()
        self.components: tuple[ArchiveComponent, ...] = ()

    def replace(
        self, records: Sequence[Mapping[str, Any]], visible: Sequence[int]
    ) -> None:
        self.records = tuple(records)
        self.visible = tuple(visible)
        self._directories = {
            index: directory
            for index in self.visible
            if (directory := archive_directory(self.records[index])) is not None
        }
        self.locations = self._locations()
        self.reconcile()

    def _locations(self) -> tuple[ArchiveComponent, ...]:
        groups: dict[tuple[str, ...], list[int]] = {}
        for index, directory in self._directories.items():
            groups.setdefault(directory.storage[1].key, []).append(index)
        result = []
        for indices in groups.values():
            paths = [self._directories[index] for index in indices]
            shared = paths[0]
            while any(path.relative_to(shared) is None for path in paths):
                shared = shared.parent
            # Prefer a recorded download root when the entire storage group belongs
            # to it. This avoids making a single-item export folder the navigation root.
            retry = self.records[indices[0]].get("vodforge_retry_job")
            root = None
            if isinstance(retry, Mapping):
                try:
                    root = ArchivePath.parse(str(retry.get("output_dir") or ""))
                except ValueError:
                    pass
            if root is not None and all(
                path.relative_to(root) is not None for path in paths
            ):
                shared = root
            elif len(indices) == 1:
                shared = shared.parent
            kind, storage = shared.storage
            label = (
                shared.name
                if shared != storage
                else str(storage).rstrip("\\/") or "This computer"
            )
            detail = {
                "local": "Local storage",
                "drive": "Drive",
                "network": "Network share",
                "external": "Mounted storage",
            }[kind]
            result.append(
                ArchiveComponent(
                    str(shared),
                    "folder",
                    label,
                    f"{detail} · {len(indices)} exports · availability not checked",
                    tuple(indices),
                    shared,
                )
            )
        return tuple(sorted(result, key=lambda item: item.title.casefold()))

    def navigate(
        self,
        path: ArchivePath | None,
        *,
        mode: Literal["folders", "all", "activity"] = "folders",
    ) -> None:
        self.path, self.mode, self.page = path, mode, 0
        self.reconcile()

    def reconcile(self) -> None:
        if self.mode == "folders" and self.path is None:
            self.components = self.locations
        else:
            folders: dict[tuple[str, ...], tuple[ArchivePath, list[int]]] = {}
            media: dict[tuple[Any, ...], list[int]] = {}
            for index in self.visible:
                record = self.records[index]
                directory = self._directories.get(index)
                if self.mode == "activity" and directory is not None:
                    continue
                if self.mode == "folders":
                    if directory is None or self.path is None:
                        continue
                    media_folder = _media_folder(record, directory)
                    relative = media_folder.relative_to(self.path)
                    if relative is None:
                        continue
                    if relative:
                        child = self.path.join(relative[:1])
                        folders.setdefault(child.key, (child, []))[1].append(index)
                        continue
                key = (
                    *_source_key(record, index),
                    self._directories[index].storage[1].key if directory else (),
                    str(_media_folder(record, directory))
                    if directory
                    else archive_row_owner(record),
                )
                media.setdefault(key, []).append(index)
            result = [
                ArchiveComponent(
                    str(path),
                    "folder",
                    path.name,
                    f"{len(indices)} exports",
                    tuple(indices),
                    path,
                )
                for path, indices in folders.values()
            ]
            for indices in media.values():
                first = self.records[indices[0]]
                kind: Literal["media", "activity"] = (
                    "media"
                    if self._directories.get(indices[0]) is not None
                    else "activity"
                )
                status = str(
                    first.get("vodforge_terminal_status")
                    or first.get("vodforge_run_status")
                    or (
                        "Metadata preview"
                        if first.get(PROJECTION_OWNER_KIND_KEY) == "preview"
                        else "Metadata"
                    )
                )
                detail = (
                    (
                        metadata_output_profile(dict(first))
                        if len(indices) == 1
                        else f"{len(indices)} export versions · "
                        + " / ".join(
                            dict.fromkeys(
                                str(
                                    self.records[index].get("vodforge_output_type")
                                    or "Media"
                                )
                                for index in indices
                            )
                        )
                    )
                    if kind == "media"
                    else status
                )
                result.append(
                    ArchiveComponent(
                        archive_row_owner(first),
                        kind,
                        str(first.get("title") or first.get("id") or "Untitled media"),
                        detail,
                        tuple(indices),
                        self._directories.get(indices[0]),
                    )
                )
            # Run ordering belongs to the shared projection (active, queued,
            # terminal, preview). Folder/media labels may be alphabetized.
            positions = {index: order for order, index in enumerate(self.visible)}
            self.components = tuple(
                sorted(
                    result,
                    key=lambda item: (
                        0
                        if item.kind == "activity"
                        else 1
                        if item.kind == "folder"
                        else 2,
                        positions[item.indices[0]]
                        if item.kind == "activity"
                        else item.title.casefold(),
                        item.key,
                    ),
                )
            )
        self.page = min(
            max(0, self.page), max(0, (len(self.components) - 1) // PAGE_SIZE)
        )

    @property
    def page_components(self) -> tuple[ArchiveComponent, ...]:
        start = self.page * PAGE_SIZE
        return self.components[start : start + PAGE_SIZE]

    def selected_index(self) -> int | None:
        return next(
            (
                index
                for index in self.visible
                if archive_row_owner(self.records[index]) == self.selected_owner
            ),
            None,
        )

    def select(self, index: int) -> None:
        if index in self.visible:
            self.selected_owner = archive_row_owner(self.records[index])

    def reveal(self, index: int) -> None:
        if index not in self.visible:
            return
        directory = self._directories.get(index)
        self.navigate(
            _media_folder(self.records[index], directory), mode="folders"
        ) if directory else self.navigate(None, mode="activity")
        self.select(index)
        for position, component in enumerate(self.components):
            if index in component.indices:
                self.page = position // PAGE_SIZE
                break
