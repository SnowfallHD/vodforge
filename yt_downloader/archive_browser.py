from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal
from urllib.parse import urlsplit

from .archive_paths import ArchivePath
from .history import history_archive_owner
from .library_state import (
    PROJECTION_OWNER_KEY,
    PROJECTION_OWNER_KIND_KEY,
    TRANSIENT_LIBRARY_STATUSES,
)
from .run_identity import metadata_output_profile

PAGE_SIZE = 48
ISSUE_STATUSES = frozenset({"Failed", "Stopped", "Skipped"})


@dataclass(frozen=True, slots=True)
class ArchiveComponent:
    key: str
    kind: Literal["folder", "media", "activity", "missing", "file"]
    title: str
    detail: str
    indices: tuple[int, ...]
    path: ArchivePath | None = None


def archive_row_owner(record: Mapping[str, Any]) -> str:
    return str(record.get(PROJECTION_OWNER_KEY) or history_archive_owner(dict(record)))


def resolve_archive_subject(
    records: Sequence[Mapping[str, Any]], captured: Mapping[str, Any]
) -> tuple[int, Mapping[str, Any]] | None:
    """Resolve a menu's original owner against the latest projection."""
    owner = archive_row_owner(captured)
    return next(
        (
            (index, record)
            for index, record in enumerate(records)
            if archive_row_owner(record) == owner
        ),
        None,
    )


def archive_directory(record: Mapping[str, Any]) -> ArchivePath | None:
    try:
        return ArchivePath.parse(str(record.get("vodforge_output_dir") or ""))
    except ValueError:
        return None


def _is_issue_without_export(
    record: Mapping[str, Any], directory: ArchivePath | None
) -> bool:
    status = str(
        record.get("vodforge_terminal_status")
        or record.get("vodforge_run_status")
        or ""
    )
    return directory is None and (
        status in ISSUE_STATUSES
        or (
            record.get("vodforge_issue_retry") is True
            and status in TRANSIENT_LIBRARY_STATUSES
        )
    )


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
        self.mode: Literal["folders", "all", "activity", "issues"] = "folders"
        self.page = 0
        self.selected_owner = ""
        self._directories: dict[int, ArchivePath] = {}
        self._all_directories: dict[int, ArchivePath | None] = {}
        self.mode_eligible_count = 0
        self.locations: tuple[ArchiveComponent, ...] = ()
        self.components: tuple[ArchiveComponent, ...] = ()
        self.missing_owners: frozenset[str] = frozenset()
        self.folder_entries: tuple[ArchiveComponent, ...] = ()
        self.folder_entries_path: ArchivePath | None = None

    def set_folder_entries(
        self, path: ArchivePath, entries: Sequence[ArchiveComponent]
    ) -> None:
        if self.mode != "folders" or self.path != path:
            return
        self.folder_entries_path = path
        self.folder_entries = tuple(entries)
        self.reconcile()

    def replace(
        self,
        records: Sequence[Mapping[str, Any]],
        visible: Sequence[int],
        *,
        missing_owners: frozenset[str] = frozenset(),
    ) -> None:
        incoming = tuple(records)
        if incoming != self.records:
            self._all_directories = {
                index: archive_directory(record)
                for index, record in enumerate(incoming)
            }
        self.records = incoming
        self.visible = tuple(visible)
        self.missing_owners = missing_owners
        self._directories = {
            index: directory
            for index in self.visible
            if (directory := self._all_directories.get(index)) is not None
        }
        self.locations = self._locations()
        if self.mode == "folders" and self.path is None and len(self.locations) == 1:
            self.path = self.locations[0].path
        self.reconcile()

    @property
    def parent_path(self) -> ArchivePath | None:
        if self.mode != "folders" or self.path is None:
            return None
        location = next(
            (
                item.path
                for item in self.locations
                if item.path is not None
                and self.path.relative_to(item.path) is not None
            ),
            None,
        )
        return (
            self.path.parent if location is not None and self.path != location else None
        )

    @property
    def breadcrumbs(self) -> tuple[ArchivePath, ...]:
        if self.mode != "folders" or self.path is None:
            return ()
        location = next(
            (
                item.path
                for item in self.locations
                if item.path is not None
                and self.path.relative_to(item.path) is not None
            ),
            None,
        )
        if location is None:
            return ()
        relative = self.path.relative_to(location) or ()
        return (
            location,
            *(location.join(relative[:index]) for index in range(1, len(relative) + 1)),
        )

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
        mode: Literal["folders", "all", "activity", "issues"] = "folders",
    ) -> None:
        self.path = (
            self.locations[0].path
            if mode == "folders" and path is None and len(self.locations) == 1
            else path
        )
        if self.path != self.folder_entries_path or mode != "folders":
            self.folder_entries = ()
            self.folder_entries_path = None
        self.mode, self.page = mode, 0
        self.reconcile()

    def folder_relink_indices(self) -> tuple[int, ...]:
        """All saved files whose recorded directory is under the current folder."""
        if self.mode != "folders" or self.path is None:
            return ()
        return tuple(
            index
            for index in self.visible
            if (directory := self._directories.get(index)) is not None
            and directory.relative_to(self.path) is not None
        )

    def reconcile(self) -> None:
        # All canonical records in this mode/scope, before search/category/type
        # filters. These are metadata-only paths; no filesystem work is added.
        self.mode_eligible_count = (
            sum(path is not None for path in self._all_directories.values())
            if self.mode == "all"
            else sum(
                _is_issue_without_export(record, self._all_directories[index])
                or (
                    self._all_directories[index] is not None
                    and history_archive_owner(dict(record)) in self.missing_owners
                )
                for index, record in enumerate(self.records)
            )
            if self.mode == "issues"
            else sum(path is None for path in self._all_directories.values())
            if self.mode == "activity"
            else sum(
                directory is not None
                and (
                    self.path is None
                    or _media_folder(self.records[index], directory).relative_to(
                        self.path
                    )
                    is not None
                )
                for index, directory in self._all_directories.items()
            )
        )
        if self.mode == "folders" and self.path is None:
            self.components = self.locations
        else:
            folders: dict[tuple[str, ...], tuple[ArchivePath, list[int]]] = {}
            media: dict[tuple[Any, ...], list[int]] = {}
            for index in self.visible:
                record = self.records[index]
                directory = self._directories.get(index)
                missing = (
                    directory is not None
                    and history_archive_owner(dict(record)) in self.missing_owners
                )
                if self.mode == "issues" and not (
                    _is_issue_without_export(record, directory) or missing
                ):
                    continue
                if self.mode == "activity" and directory is not None:
                    continue
                if self.mode == "all" and directory is None:
                    continue
                if self.mode == "folders":
                    if directory is None or self.path is None:
                        continue
                    relative = directory.relative_to(self.path)
                    if relative is None:
                        continue
                    if relative:
                        child = self.path.join(relative[:1])
                        folders.setdefault(child.key, (child, []))[1].append(index)
                        continue
                key = (
                    ("missing", history_archive_owner(dict(record)))
                    if self.mode == "issues" and missing
                    else (
                        *_source_key(record, index),
                        self._directories[index].storage[1].key if directory else (),
                        str(_media_folder(record, directory))
                        if directory
                        else archive_row_owner(record),
                    )
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
                first_missing = (
                    self._directories.get(indices[0]) is not None
                    and history_archive_owner(dict(first)) in self.missing_owners
                )
                kind: Literal["media", "activity", "missing"] = (
                    "missing"
                    if self.mode == "issues" and first_missing
                    else "media"
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
                    else "Saved file missing"
                    if kind == "missing"
                    else status
                )
                result.append(
                    ArchiveComponent(
                        history_archive_owner(dict(first))
                        if kind == "missing"
                        else archive_row_owner(first),
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
            ordered = tuple(
                sorted(
                    result,
                    key=lambda item: (
                        0
                        if item.kind in {"activity", "missing"}
                        else 1
                        if item.kind == "folder"
                        else 2,
                        positions[item.indices[0]]
                        if item.kind in {"activity", "missing"}
                        else item.title.casefold(),
                        item.key,
                    ),
                )
            )
            if self.mode == "folders" and self.folder_entries_path == self.path:
                present = {
                    item.path.key
                    for item in self.folder_entries
                    if item.path is not None
                }
                physical = []
                for item in ordered:
                    if item.kind == "folder":
                        if item.path is not None and item.path.key in present:
                            physical.append(item)
                    elif item.kind == "media":
                        indices = []
                        for index in item.indices:
                            try:
                                output = ArchivePath.parse(
                                    str(
                                        self.records[index].get("vodforge_output_path")
                                        or ""
                                    )
                                )
                            except ValueError:
                                continue
                            if output.key in present:
                                indices.append(index)
                        if indices:
                            physical.append(replace(item, indices=tuple(indices)))
                ordered = tuple(physical)
                folder_paths = {
                    item.path.key
                    for item in ordered
                    if item.kind == "folder" and item.path is not None
                }
                media_paths = set()
                for item in ordered:
                    if item.kind != "media":
                        continue
                    for index in item.indices:
                        try:
                            media_paths.add(
                                ArchivePath.parse(
                                    str(
                                        self.records[index].get("vodforge_output_path")
                                        or ""
                                    )
                                ).key
                            )
                        except ValueError:
                            pass
                # Above a saved media folder, My Files is a route through known
                # locations, not a browser for the user's entire home directory.
                # Once there, include real sidecars and child folders as well.
                in_media_folder = any(
                    (directory := self._directories.get(index)) is not None
                    and self.path.relative_to(
                        _media_folder(self.records[index], directory)
                    )
                    is not None
                    for index in self.visible
                )
                if in_media_folder:
                    ordered += tuple(
                        item
                        for item in self.folder_entries
                        if item.path is not None
                        and item.path.key
                        not in (folder_paths if item.kind == "folder" else media_paths)
                    )
            self.components = ordered
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
