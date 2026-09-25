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


def native_surface_contract(repo_root, output_dir, *, profile="normal", ui="tk"):
    if ui not in {"tk", "qt"}:
        raise ValueError(f"Unsupported native UI renderer: {ui}")
    output_dir.mkdir(parents=True, exist_ok=True)
    report = output_dir / "native.xml"
    report.unlink(missing_ok=True)
    qt_component_tests = [
        "tests/test_qt_artwork_image.py",
        "tests/test_qt_metadata_preview.py",
        "tests/test_qt_previews.py",
        "tests/test_qt_terminal_item_events.py",
        "tests/test_qt_relink.py",
        "tests/test_qt_presentation_diagnostics.py",
    ]
    tk_tests = [
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
        "tests/test_matte_projection_resize_native.py",
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
                "tests/test_macos_resize_pointer_native.py",
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
            [
                "tests/test_windows_surface_capture_native.py",
                "tests/test_windows_resize_inflight_native.py",
                "tests/test_windows_resize_pointer_native.py",
            ]
            if sys.platform == "win32"
            else []
        ),
        "tests/test_native_ui_polish.py",
        "tests/test_support_native.py",
        "tests/test_forge_activity_ui.py",
        "tests/test_analytics_consent_ui.py",
    ]
    native_env = {
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
        "VODFORGE_UI": ui,
        **({"QT_QPA_PLATFORM": "offscreen"} if ui == "qt" else {}),
        "VODFORGE_NATIVE_FILE_QA": "1",
        "VODFORGE_ACTUAL_PLAYBACK_TESTS": "1",
        "VODFORGE_DISABLE_TELEMETRY": "1",
    }
    if ui == "qt":
        # QGuiApplication and native worker state are process-wide. Keep every
        # required Qt test, but give the scene and component groups separate
        # processes and evidence directories.
        groups = (
            ("scene", ["tests/test_qt_scene_port.py"]),
            ("components", qt_component_tests),
        )
        group_results = []
        for name, tests in groups:
            group_dir = output_dir / name
            group_dir.mkdir(parents=True, exist_ok=True)
            group_report = group_dir / "native.xml"
            group_report.unlink(missing_ok=True)
            result = run_command(
                native_pytest_command(
                    [
                        "-p",
                        "quality_harness.native_reports",
                        *tests,
                        "-q",
                        f"--junitxml={group_report}",
                    ]
                ),
                cwd=repo_root,
                timeout=1800,
                env={**native_env, "VODFORGE_NATIVE_EVIDENCE_DIR": str(group_dir)},
            )
            (group_dir / "native-command.json").write_text(
                json.dumps(asdict(result), indent=2) + "\n"
            )
            group_results.append((name, group_dir, group_report, result))
        passed = all(
            result.returncode == 0 and complete_native_report(group_report)
            for _name, _group_dir, group_report, result in group_results
        )
        return (
            {
                "id": "unit_static.native_surface_contract",
                "evidence_tier": "unit_static",
                "category": "reliability",
                "status": "passed" if passed else "failed",
                "duration_seconds": sum(
                    result.duration_seconds
                    for _name, _group_dir, _group_report, result in group_results
                ),
                "metrics": {
                    "ui": ui,
                    "timed_out": any(
                        result.timed_out
                        for _name, _group_dir, _group_report, result in group_results
                    ),
                    "unavailable": any(
                        result.unavailable
                        for _name, _group_dir, _group_report, result in group_results
                    ),
                },
                "evidence": [
                    item
                    for name, _group_dir, _group_report, result in group_results
                    for item in (
                        f"{name} native pytest exit code: {result.returncode}",
                        result.stdout,
                        result.stderr,
                    )
                ]
                + ["source-native; not packaged or cross-platform proof"],
                "artifacts": [
                    str(group_dir / artifact)
                    for _name, group_dir, _group_report, _result in group_results
                    for artifact in (
                        "native.xml",
                        "native-command.json",
                        "native-results.jsonl",
                        "native-evidence.json",
                        "native-imports.json",
                    )
                ],
                "error": (
                    "Native suite exceeded 1800 seconds"
                    if any(
                        result.timed_out
                        for _name, _group_dir, _group_report, result in group_results
                    )
                    else None
                ),
            },
            [],
        )
    result = run_command(
        native_pytest_command(
            [
                "-p",
                "quality_harness.native_reports",
                *tk_tests,
                "-q",
                f"--junitxml={report}",
            ]
        ),
        cwd=repo_root,
        timeout=1800,  # Whole-suite envelope; interaction/readiness/release deadlines are unchanged.
        env={**native_env, "VODFORGE_NATIVE_EVIDENCE_DIR": str(output_dir)},
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
                "ui": ui,
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
