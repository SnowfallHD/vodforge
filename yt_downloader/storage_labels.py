"""Storage display facts; canonical archive paths remain the action identity."""

from __future__ import annotations

from dataclasses import dataclass

from .archive_paths import ArchivePath
from .volume_storage import StorageVolume


@dataclass(frozen=True, slots=True)
class LocationLabel:
    path: ArchivePath
    title: str
    subtitle: str

    @property
    def tooltip(self) -> str:
        return f"{self.title}\n{self.subtitle}\n{self.path}"


def location_labels(
    paths: tuple[ArchivePath, ...],
    volumes: tuple[StorageVolume, ...],
) -> tuple[LocationLabel, ...]:
    labels = []
    for path in paths:
        lexical_kind, anchor = path.storage
        candidates = []
        for candidate in volumes:
            try:
                mount = ArchivePath.parse(candidate.path)
            except ValueError:
                continue
            # An offline /Volumes/name is never the root disk merely because
            # its lexical path starts with /. Discovered more-specific mounts win.
            if path.relative_to(mount) is not None and (
                lexical_kind != "external" or len(mount.parts) >= len(anchor.parts)
            ):
                candidates.append((len(mount.parts), candidate))
        volume = max(candidates, key=lambda item: item[0])[1] if candidates else None
        if volume:
            title = volume.label
            kind = volume.kind
        elif lexical_kind == "network":
            # UNC syntax explicitly names a share; a drive letter does not.
            title = str(anchor).rstrip(chr(92) + "/").rsplit(chr(92), 1)[-1]
            kind = "network"
        else:
            title = anchor.name if anchor.name not in {"/", "\\\\"} else path.name
            title = title if title not in {"/", "\\\\"} else "Saved location"
            kind = "unknown"
        subtitle = {"local": "Local", "external": "External", "network": "Network"}.get(
            kind, "Type unknown"
        )
        labels.append(LocationLabel(path, title, subtitle))
    # Put the distinguishing suffix first, rather than clipping identical
    # /Volumes/ prefixes in the narrow sidebar. Tooltips retain the full path.
    groups: dict[str, list[LocationLabel]] = {}
    for item in labels:
        groups.setdefault(item.title.casefold(), []).append(item)
    result = []
    for item in labels:
        peers = groups[item.title.casefold()]
        suffix = ""
        if len(peers) > 1:
            for length in range(1, len(item.path.parts) + 1):
                if all(
                    other.path.key[-length:] != item.path.key[-length:]
                    for other in peers
                    if other is not item
                ):
                    suffix = "/".join(item.path.parts[-length:])
                    break
        result.append(
            LocationLabel(
                item.path,
                item.title,
                f"{item.subtitle} · {suffix}" if suffix else item.subtitle,
            )
        )
    return tuple(result)
