from __future__ import annotations

import json
import subprocess  # nosec B404 - fixed argv to trusted local media tools
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .history import history_output_dir, history_output_path, history_output_type
from .platform_services import hidden_window_subprocess_kwargs
from .playback_backend import MediaPlayerError


def resolve_library_media_path(record: dict[str, Any]) -> Path | None:
    """Resolve one committed Library artifact without treating its row as authority."""

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
    extension = ".mp3" if history_output_type(record) == "MP3" else ".mp4"
    try:
        candidates = sorted(
            (
                child
                for child in output_dir.iterdir()
                if child.suffix.casefold() == extension
                and child.is_file()
                and child.stat().st_size > 0
            ),
            key=lambda path: path.name.casefold(),
        )
    except OSError:
        return None
    return candidates[0] if len(candidates) == 1 else None


def probe_media_duration(
    ffprobe: str,
    path: Path,
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> float:
    """Read duration through a fixed ffprobe query and reject malformed output."""

    try:
        result = runner(  # nosec B603 - executable is resolved by platform service
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            **hidden_window_subprocess_kwargs(),
        )
        value = float(json.loads(result.stdout)["format"]["duration"])
    except (
        OSError,
        subprocess.SubprocessError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        raise MediaPlayerError("VODForge could not read this media duration.") from exc
    if not 0 < value < 60 * 60 * 48:
        raise MediaPlayerError("This media item reports an invalid duration.")
    return value
