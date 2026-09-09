"""Required source-native interaction evidence, never packaged-app evidence."""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET

from .util import run_command


def complete_native_report(path):
    """A successful pytest process with only skips is not native UI proof."""
    try:
        cases = ET.parse(path).getroot().findall(".//testcase")
    except (OSError, ET.ParseError):
        return False
    return bool(cases) and all(
        not any(case.find(tag) is not None for tag in ("skipped", "failure", "error"))
        for case in cases
    )


def native_surface_contract(repo_root, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    report = output_dir / "native.xml"
    report.unlink(missing_ok=True)
    result = run_command(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_choice_popover_lifecycle.py",
            "tests/test_native_ui_polish.py",
            "tests/test_support_native.py",
            "-q",
            f"--junitxml={report}",
        ],
        cwd=repo_root,
        env={
            **os.environ,
            "VODFORGE_NATIVE_UI_TESTS": "1",
            "VODFORGE_DISABLE_TELEMETRY": "1",
        },
    )
    return (
        {
            "id": "unit_static.native_surface_contract",
            "evidence_tier": "unit_static",
            "category": "reliability",
            "status": "passed"
            if result.returncode == 0 and complete_native_report(report)
            else "failed",
            "duration_seconds": 0,
            "metrics": {},
            "evidence": {
                "native_process": result.as_dict(),
                "scope": "source-native; not packaged or cross-platform proof",
            },
            "artifacts": [str(report)],
            "error": None,
        },
        [],
    )
