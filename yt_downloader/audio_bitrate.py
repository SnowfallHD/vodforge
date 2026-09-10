"""Measured compressed-audio averages; never substitute container or target rates."""

from __future__ import annotations

import math
import subprocess  # nosec B404 - exception type only; the existing runner owns execution.
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any


def needs_packet_average(data: dict[str, Any]) -> bool:
    audio = next(
        (
            s
            for s in data.get("streams", [])
            if isinstance(s, dict) and s.get("codec_type") == "audio"
        ),
        None,
    )
    if audio is None:
        return False
    try:
        rate = float(audio.get("bit_rate", 0))
        return not math.isfinite(rate) or rate <= 0
    except (ValueError, TypeError):
        return True


def packet_average_bps(data: dict[str, Any]) -> float | None:
    """Require complete packet size/duration evidence, excluding container bytes."""
    packets = data.get("packets")
    if not isinstance(packets, list) or not packets:
        return None
    return _average(packets)


def _average(packets: Iterable[dict[str, Any]]) -> float | None:
    size = 0
    duration = 0.0
    for packet in packets:
        try:
            packet_size = int(packet["size"])
            packet_duration = float(packet["duration_time"])
        except (KeyError, TypeError, ValueError, OverflowError):
            return None
        if (
            packet_size < 0
            or not math.isfinite(packet_duration)
            or packet_duration <= 0
        ):
            return None
        size += packet_size
        duration += packet_duration
    return size * 8 / duration if size and math.isfinite(duration) else None


def measure_packet_average(
    ffprobe: str, path: Path, run: Callable[[list[str]], Any]
) -> float | None:
    # Spool long recordings to disk; the existing runner owns cancellation.
    with tempfile.TemporaryDirectory(prefix="vodforge-audio-probe-") as temporary:
        output = Path(temporary) / "packets.txt"
        try:
            run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_entries",
                    "packet=size,duration_time",
                    "-of",
                    "compact",
                    "-o",
                    str(output),
                    str(path),
                ]
            )
            with output.open(encoding="utf-8") as source:
                return _average(
                    dict(
                        part.split("=", 1)
                        for part in line.strip().split("|")[1:]
                        if "=" in part
                    )
                    for line in source
                    if line.startswith("packet|")
                )
        except (OSError, subprocess.SubprocessError):
            return None
