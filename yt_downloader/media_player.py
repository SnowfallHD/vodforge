from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .archive_paths import ArchivePath
from .history import history_output_dir, history_output_path, history_output_type


def resolve_library_media_path(record: dict[str, Any]) -> Path | None:
    """Resolve one committed Library artifact without treating its row as authority."""

    try:
        saved = ArchivePath.parse(str(record.get("vodforge_output_dir") or ""))
    except ValueError:
        return None
    if (saved.style == "windows") != (os.name == "nt"):
        return None
    exact = history_output_path(record)
    if exact is not None:
        try:
            if exact.is_file() and exact.stat().st_size > 0:
                return exact
        except OSError:
            pass
        # A canonical exact path must never fall through to an unrelated file
        # that merely shares the same extension in the saved directory.
        return None
    output_dir = history_output_dir(record)
    if output_dir is None:
        return None
    if history_output_type(record) == "Original audio":
        return None  # Never substitute a nearby MP4 for an incomplete audio record.
    extension = ".mp3" if history_output_type(record) == "MP3" else ".mp4"
    try:
        candidates: list[Path] = []
        for index, child in enumerate(output_dir.iterdir()):
            if index >= 128:
                return None  # Legacy folders require explicit selection beyond the cap.
            if (
                child.suffix.casefold() == extension
                and child.is_file()
                and child.stat().st_size > 0
            ):
                candidates.append(child)
                if len(candidates) > 1:
                    return None
    except OSError:
        return None
    return candidates[0] if len(candidates) == 1 else None
