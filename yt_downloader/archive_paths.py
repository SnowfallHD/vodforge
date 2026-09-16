from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal

PathStyle = Literal["windows", "posix"]
StorageKind = Literal["local", "drive", "network", "external"]


@dataclass(frozen=True, slots=True)
class ArchivePath:
    """A lexical absolute path. Parsing never touches a drive or network share.

    Windows paths compare without case; POSIX paths compare exactly. Actual
    filesystem aliases/case behavior are resolved only by the verification worker.
    Drive letters never imply a mapped UNC share on another computer.
    """

    style: PathStyle
    parts: tuple[str, ...]

    @classmethod
    def parse(cls, value: str) -> ArchivePath:
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 8192
            or any(ord(char) < 32 for char in value)
        ):
            raise ValueError("Invalid archive path")
        windows = bool(re.match(r"^[A-Za-z]:", value)) or value.startswith(
            ("\\\\", "//")
        )
        if windows:
            if value.startswith(("\\\\?\\", "\\\\.\\")):
                raise ValueError(
                    "Device namespace paths require a normal drive or share"
                )
            path = PureWindowsPath(value)
            if not path.is_absolute():
                raise ValueError("Choose an absolute drive or UNC share path")
            for component in path.parts[1:]:
                if (
                    component in {".", ".."}
                    or component.endswith((" ", "."))
                    or re.search(r'[<>:"|?*]', component)
                    or re.fullmatch(
                        r"(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?",
                        component,
                        re.IGNORECASE,
                    )
                ):
                    raise ValueError("Unsupported Windows path component")
            return cls("windows", path.parts)
        posix_path = PurePosixPath(value)
        if not posix_path.is_absolute() or ".." in posix_path.parts:
            raise ValueError("Choose an absolute path without parent traversal")
        return cls("posix", posix_path.parts)

    @property
    def key(self) -> tuple[str, ...]:
        parts = (
            tuple(part.casefold() for part in self.parts)
            if self.style == "windows"
            else self.parts
        )
        return (self.style, *parts)

    def __str__(self) -> str:
        path_class = PureWindowsPath if self.style == "windows" else PurePosixPath
        return str(path_class(*self.parts))

    @property
    def name(self) -> str:
        return self.parts[-1]

    @property
    def parent(self) -> ArchivePath:
        return ArchivePath(self.style, self.parts[:-1] or self.parts)

    def relative_to(self, root: ArchivePath) -> tuple[str, ...] | None:
        if self.style != root.style or self.key[: len(root.key)] != root.key:
            return None
        return self.parts[len(root.parts) :]

    def join(self, parts: tuple[str, ...]) -> ArchivePath:
        if any(
            part in {"", ".", ".."}
            or "/" in part
            or (self.style == "windows" and "\\" in part)
            for part in parts
        ):
            raise ValueError("Invalid relative archive path")
        path_class = PureWindowsPath if self.style == "windows" else PurePosixPath
        return ArchivePath.parse(str(path_class(*self.parts, *parts)))

    @property
    def ancestry(self) -> tuple[ArchivePath, ...]:
        return tuple(
            ArchivePath(self.style, self.parts[:index])
            for index in range(1, len(self.parts) + 1)
        )

    @property
    def storage(self) -> tuple[StorageKind, ArchivePath]:
        anchor = self.parts[0]
        if self.style == "windows":
            kind: StorageKind = "network" if anchor.startswith("\\\\") else "drive"
            return kind, ArchivePath(self.style, (anchor,))
        if len(self.parts) >= 3 and self.parts[1] in {"Volumes", "mnt", "media"}:
            return "external", ArchivePath(self.style, self.parts[:3])
        if len(self.parts) >= 4 and self.parts[1:3] == ("run", "media"):
            return "external", ArchivePath(self.style, self.parts[:4])
        return "local", ArchivePath(self.style, (anchor,))


@dataclass(frozen=True, slots=True)
class RootMapping:
    source: ArchivePath
    destination: ArchivePath

    def map(self, path: ArchivePath) -> ArchivePath | None:
        relative = path.relative_to(self.source)
        return None if relative is None else self.destination.join(relative)


def map_archive_path(
    path: ArchivePath, mappings: tuple[RootMapping, ...]
) -> tuple[ArchivePath | None, RootMapping | None, str]:
    """Most specific component mapping wins; conflicting equal roots are unresolved."""
    matches = [
        mapping for mapping in mappings if path.relative_to(mapping.source) is not None
    ]
    if not matches:
        return None, None, "outside_mapping"
    depth = max(len(mapping.source.parts) for mapping in matches)
    matches = [mapping for mapping in matches if len(mapping.source.parts) == depth]
    try:
        destinations = {str(mapping.map(path)): mapping for mapping in matches}
    except ValueError:
        return None, None, "invalid_destination"
    if len({ArchivePath.parse(value).key for value in destinations}) != 1:
        return None, None, "ambiguous_mapping"
    value, mapping = next(iter(destinations.items()))
    return ArchivePath.parse(value), mapping, "mapped"
