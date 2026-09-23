"""Windows native frame edge must stay with the held pointer during resize."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(
    sys.platform != "win32" or os.environ.get("VODFORGE_NATIVE_UI_TESTS") != "1",
    reason="Interactive Windows native display required",
)
def test_forge_frame_tracks_pointer_during_live_resize(tmp_path):
    checkout = Path(os.environ["VODFORGE_NATIVE_SOURCE_ROOT"])
    output = tmp_path / "resize-pointer"
    completed = subprocess.run(
        [
            sys.executable,
            str(checkout / "engineering-quality/runners/native-resize-probe.py"),
            "--source",
            str(checkout),
            "--output",
            str(output),
            "--rows",
            "25",
            "--view",
            "forge",
            "--drag-count",
            "2",
            "--edge",
            "right",
            "--assert-pointer-tracking",
            "--auto-continue",
        ],
        cwd=checkout,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    report = output / "pointer-assessment.json"
    evidence = json.loads(report.read_text()) if report.exists() else None
    assert completed.returncode == 0, {
        "assessment": evidence,
        "stdout": completed.stdout[-2000:],
        "stderr": completed.stderr[-2000:],
    }
    assert evidence is not None and evidence["passed"]
