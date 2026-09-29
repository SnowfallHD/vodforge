"""Run-owned friendly activity projection shared by the desktop front ends."""

from __future__ import annotations

import re
from collections.abc import Sequence

from .library_state import library_phase_from_status


def friendly_phase(status: str) -> str | None:
    """Use worker status, never arbitrary technical log prose, for phase labels."""
    terminal = {
        "Completed": "[success] Download complete",
        "Failed": "ERROR: Download failed. Open Technical details for the cause.",
        "Partial": "WARNING: Some items could not finish. See Technical details.",
        "Stopped": "Download stopped",
        "Skipped": "Download skipped",
    }
    if status in terminal:
        return terminal[status]
    if status == "Download finished; finalizing output…":
        return None
    phase = library_phase_from_status(status)
    label = {
        "Preparing": "Getting video information",
        "Downloading": "Downloading media",
        "Transcoding": "Converting media",
        "Validating": "Checking the output",
        "Finalizing": "Finishing the download",
    }.get(phase or "")
    if label is None:
        return None
    item = re.match(r"(?:Video|Batch URL) \d+ of (\d+)", status)
    return f"{item[0]} · {label}" if item and int(item[1]) > 1 else label


def friendly_saved_activity(status: str, lines: Sequence[str]) -> str:
    """Reconstruct the steps evidenced by a saved run's bounded activity log."""
    stages: set[str] = set()
    warning = False
    error = False
    for line in lines:
        detail = str(line).strip().lower()
        if detail.startswith("warning:"):
            warning = True
            continue
        if detail.startswith("error:"):
            error = True
            continue
        if (
            "selected format" in detail
            or "single video detected" in detail
            or "playlist detected" in detail
        ):
            stages.add("Preparing")
        if re.search(r": downloading(?:\s|$)", detail):
            stages.add("Downloading")
        if "ffmpeg command started" in detail or "transcoded staged" in detail:
            stages.add("Transcoding")
        if re.search(r": validated\s", detail):
            stages.add("Validating")
        if "packaged media file" in detail or "atomic commit" in detail:
            stages.add("Finalizing")
    rows = [
        label
        for phase, label in (
            ("Preparing", "Getting video information"),
            ("Downloading", "Downloading media"),
            ("Transcoding", "Converting media"),
            ("Validating", "Checking the output"),
            ("Finalizing", "Finishing the download"),
        )
        if phase in stages
    ]
    terminal = friendly_phase(status)
    if terminal:
        rows.append(terminal)
    if warning:
        rows.append("WARNING: A warning was reported. See Technical details.")
    if error:
        rows.append("ERROR: An error was reported. See Technical details.")
    return "\n".join(row for row in rows if row) or status or "No run selected."


class ForgeActivityProjection:
    """Bounded session view; durable technical activity stays with the run."""

    def __init__(self) -> None:
        self._runs: dict[str, list[str]] = {}

    def observe(self, run_id: str, status: str, message: str = "") -> bool:
        label = friendly_phase(status)
        if not run_id or label is None:
            return False
        if status in {"Failed", "Partial"} and message:
            label = ("ERROR: " if status == "Failed" else "WARNING: ") + message
        rows = self._runs.setdefault(run_id, [])
        if label in rows or (rows and rows[-1].endswith(" · " + label)):
            return False
        rows.append(label)
        del rows[:-64]
        if len(self._runs) > 128:
            del self._runs[next(iter(self._runs))]
        return True

    def friendly(self, run_id: str, raw: str) -> str:
        rows = list(self._runs.get(run_id, ()))
        if not rows:
            rows = [
                "Open Technical details for this run’s saved activity."
                if run_id
                else "Your next run’s progress will appear here."
            ]
        if re.search(r"(?im)^(?:\d{2}:\d{2}:\d{2}\s+)?(?:WARNING:|\[warning\])", raw):
            rows.append("WARNING: A warning was reported. See Technical details.")
        if re.search(r"(?im)^(?:\d{2}:\d{2}:\d{2}\s+)?(?:ERROR:|\[error\])", raw):
            rows.append("ERROR: An error was reported. See Technical details.")
        return "\n".join(rows)
