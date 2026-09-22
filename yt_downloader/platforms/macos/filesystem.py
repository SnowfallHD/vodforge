from __future__ import annotations

from pathlib import Path


def system_trash_available() -> bool:
    from Foundation import NSFileManager

    return hasattr(
        NSFileManager.defaultManager(), "trashItemAtURL_resultingItemURL_error_"
    )


def trash_file(path: Path) -> str | None:
    from Foundation import NSURL, NSFileManager

    succeeded, resulting_url, _error = (
        NSFileManager.defaultManager().trashItemAtURL_resultingItemURL_error_(
            NSURL.fileURLWithPath_(str(path)), None, None
        )
    )
    if not succeeded:
        raise OSError("The system could not move this file to Trash.")
    return str(resulting_url.path()) if resulting_url is not None else None
