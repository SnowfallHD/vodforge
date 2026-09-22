"""Read selected local media without copying, transcoding or modifying it."""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess  # nosec B404 - fixed ffprobe arguments
import threading
from pathlib import Path
from typing import Any

from .platform_services import find_runtime_executable, hidden_window_subprocess_kwargs

SUPPORTED_IMPORTS = frozenset(
    {".mp4", ".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus"}
)


def inspect_local_media(path: Path, cancelled: threading.Event) -> dict[str, Any]:
    if cancelled.is_set():
        raise InterruptedError("Import cancelled.")
    path = path.expanduser().resolve(strict=True)
    if path.suffix.casefold() not in SUPPORTED_IMPORTS or not path.is_file():
        raise ValueError("Choose an MP4 video or supported audio file.")
    before = path.stat()
    executable = find_runtime_executable("ffprobe")
    if not executable:
        raise RuntimeError("Media inspection is unavailable.")
    result = subprocess.run(  # nosec B603 - runtime tool and selected path are separate argv
        [
            executable,
            "-v",
            "error",
            "-show_entries",
            "format=duration,format_name,size:stream=index,codec_type,codec_name,width,height,sample_rate,channels:stream_disposition=attached_pic",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        timeout=15,
        check=False,
        **hidden_window_subprocess_kwargs(),
    )
    if result.returncode or len(result.stdout) > 1024 * 1024:
        raise ValueError("This file could not be read as media.")
    data = json.loads(result.stdout)
    streams = [s for s in data.get("streams", [])[:128] if isinstance(s, dict)]
    # Album covers are artwork carried in an audio container, not motion video.
    video = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "video"
            and str((s.get("disposition") or {}).get("attached_pic", 0)) != "1"
        ),
        None,
    )
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video and path.suffix.casefold() != ".mp4":
        raise ValueError("Choose an MP4 file for motion video.")
    if not video and not audio:
        raise ValueError("No playable video or audio was found.")
    duration = float((data.get("format") or {}).get("duration") or 0)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("The media duration is unavailable.")
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("The file changed while it was being inspected. Try again.")
    if cancelled.is_set():
        raise InterruptedError("Import cancelled.")
    identity = hashlib.sha256(os.path.normcase(str(path)).encode()).hexdigest()
    output_type = (
        "MP4"
        if video
        else "MP3"
        if path.suffix.casefold() == ".mp3"
        else "Original audio"
    )
    output = {
        "Output file path": str(path),
        "Output container": path.suffix[1:],
        "File size": str(after.st_size) + " bytes",
        "Duration": f"{duration:g} seconds",
    }
    if video:
        output.update(
            {
                "Output resolution": f"{video.get('width', 0)}x{video.get('height', 0)}",
                "Output video codec": str(video.get("codec_name") or "Unknown"),
            }
        )
    if audio:
        output.update(
            {
                "Output audio codec": str(audio.get("codec_name") or "Unknown"),
                "Audio sample rate": str(audio.get("sample_rate") or "Unknown"),
                "Audio channels": str(audio.get("channels") or "Unknown"),
            }
        )
    return {
        "id": "local-" + identity,
        "title": path.stem,
        "channel": "Local media",
        "duration": duration,
        "vodforge_run_id": "import-" + identity[:32],
        "vodforge_output_type": output_type,
        "vodforge_output_path": str(path),
        "vodforge_encoding_summary": {
            "source": {"Source": "Imported from this computer"},
            "output": output,
            "warnings": [],
        },
    }


def commit_imports(history, records, path, *, save=None):
    """Publish a prospective history only after the complete batch is durable."""
    from .history import save_history, upsert_history

    prospective = list(history)
    for record in records:
        prospective = upsert_history(
            prospective,
            record,
            Path(record["vodforge_output_path"]).parent,
            replace_missing_media=True,
        )
    (save or save_history)(path, prospective)
    return prospective
