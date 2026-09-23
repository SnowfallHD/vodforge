"""Required source-native interaction evidence, never packaged-app evidence."""

from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict

from .native_process import native_pytest_command
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


def native_surface_contract(repo_root, output_dir, *, profile="normal"):
    output_dir.mkdir(parents=True, exist_ok=True)
    report = output_dir / "native.xml"
    report.unlink(missing_ok=True)
    result = run_command(
        native_pytest_command(
            [
                "-p",
                "quality_harness.native_reports",
                "tests/test_choice_popover_lifecycle.py",
                "tests/test_native_interaction_readiness.py",
                "tests/test_native_thumbnail_rendering.py",
                "tests/test_archive_native.py",
                "tests/test_player_action_retirement_native.py",
                "tests/test_archive_presentation_native.py",
                "tests/test_archive_composed_native.py",
                "tests/test_presentation_native.py",
                "tests/test_archive_actual_playback.py",
                "tests/test_watch_queue_native.py",
                "tests/test_foundation_acceptance_native.py",
                "tests/test_library_file_actions_native.py",
                "tests/test_relink_consent_native.py",
                "tests/test_relink_navigation_native.py",
                "tests/test_relink_admission_native.py",
                "tests/test_relink_layout_native.py",
                "tests/test_widget_reveal_native.py",
                "tests/test_button_parity_native.py",
                "tests/test_shared_header_action_native.py",
                "tests/test_inline_description_native.py",
                "tests/test_player_layout_native.py",
                "tests/test_startup_update_native.py",
                *(
                    [
                        "tests/test_library_restraint_native.py",
                        "tests/test_archive_overlay_reveal_native.py",
                        "tests/test_platform_trash_native.py",
                        "tests/test_shared_controls_native.py",
                        "tests/test_catalog_scale_native.py",
                        "tests/test_description_readability_native.py",
                        "tests/test_window_chrome_native.py",
                        "tests/test_brand_native.py",
                        "tests/test_matte_native.py",
                        "tests/test_matte_projection_native.py",
                        "tests/test_scene_inflight_native.py",
                        "tests/test_scroll_inflight_native.py",
                        "tests/test_scroll_idle_native.py",
                        "tests/test_surface_raster_native.py",
                        "tests/test_field_density_native.py",
                        "tests/test_window_logical_metrics_native.py",
                        "tests/test_surface_memory_native.py",
                        "tests/test_view_transition_native.py",
                    ]
                    if sys.platform == "darwin"
                    else []
                ),
                *(
                    ["tests/test_windows_surface_capture_native.py"]
                    if sys.platform == "win32"
                    else []
                ),
                "tests/test_native_ui_polish.py",
                "tests/test_support_native.py",
                "tests/test_forge_activity_ui.py",
                "tests/test_analytics_consent_ui.py",
                "-q",
                f"--junitxml={report}",
            ]
        ),
        cwd=repo_root,
        timeout=1800,  # Whole-suite envelope; interaction/readiness/release deadlines are unchanged.
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                filter(
                    None,
                    (
                        str(repo_root.resolve()),
                        str((repo_root / "engineering-quality").resolve()),
                        os.environ.get("PYTHONPATH", ""),
                    ),
                )
            ),
            "VODFORGE_NATIVE_SOURCE_ROOT": str(repo_root.resolve()),
            "VODFORGE_NATIVE_HARNESS_ROOT": str(
                (repo_root / "engineering-quality").resolve()
            ),
            "VODFORGE_NATIVE_UI_TESTS": "1",
            "VODFORGE_NATIVE_PROFILE": profile,
            "VODFORGE_NATIVE_FILE_QA": "1",
            "VODFORGE_ACTUAL_PLAYBACK_TESTS": "1",
            "VODFORGE_NATIVE_EVIDENCE_DIR": str(output_dir),
            "VODFORGE_DISABLE_TELEMETRY": "1",
        },
    )
    command_report = output_dir / "native-command.json"
    command_report.write_text(json.dumps(asdict(result), indent=2) + "\n")
    return (
        {
            "id": "unit_static.native_surface_contract",
            "evidence_tier": "unit_static",
            "category": "reliability",
            "status": "passed"
            if result.returncode == 0 and complete_native_report(report)
            else "failed",
            "duration_seconds": result.duration_seconds,
            "metrics": {
                "timed_out": result.timed_out,
                "unavailable": result.unavailable,
            },
            "evidence": [
                f"Native pytest exit code: {result.returncode}",
                result.stdout,
                result.stderr,
                "source-native; not packaged or cross-platform proof",
            ],
            "artifacts": [
                str(report),
                str(command_report),
                str(output_dir / "native-results.jsonl"),
                str(output_dir / "native-evidence.json"),
                str(output_dir / "native-imports.json"),
            ],
            "error": "Native suite exceeded 1800 seconds" if result.timed_out else None,
        },
        [],
    )
