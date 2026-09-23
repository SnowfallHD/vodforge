"""A new Tk presentation owner must enter the Qt port review ledger."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "engineering-quality" / "qt-port-owner-review.md"
PRESENTATION_MARKERS = re.compile(
    r"\bImageTk\b|\btk\.|\bttk\.|\.canvas\.|"
    r"ScenePainter|ProductButton|Toplevel\("
)


def test_every_tk_presentation_code_file_has_a_reviewed_qt_owner() -> None:
    review = REVIEW.read_text(encoding="utf-8")
    candidates = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "yt_downloader").rglob("*.py")
        if "qt_quick" not in path.parts
        and PRESENTATION_MARKERS.search(path.read_text(encoding="utf-8"))
    }
    reviewed = set(
        re.findall(r"^\| `(yt_downloader/[^`]+\.py)` \|", review, re.MULTILINE)
    )
    assert candidates <= reviewed, sorted(candidates - reviewed)
    assert all((ROOT / path).is_file() for path in reviewed)
