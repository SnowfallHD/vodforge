"""Required source-native interaction evidence, never packaged-app evidence."""

from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict

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


QT_COMPONENT_TESTS = [
    "tests/test_qt_artwork_image.py",
    "tests/test_qt_metadata_preview.py",
    "tests/test_qt_previews.py",
    "tests/test_qt_interaction_invariants.py",
    "tests/test_qt_terminal_item_events.py",
    "tests/test_qt_relink.py",
    "tests/test_qt_output_config.py",
    "tests/test_qt_settings_theme.py",
    "tests/test_qt_presentation_diagnostics.py",
]
# Keep recent user-reported Qt regressions in a separate process. They
# exercise component/event ownership; offscreen execution is not native
# pointer timing, displayed pixels or packaged application acceptance.
QT_REPORTED_REGRESSIONS = [
    "tests/test_qt_inspector_description_geometry.py",
    "tests/test_qt_folder_columns_responsive.py",
    "tests/test_qt_composer_custom_options.py",
    "tests/test_qt_composer_feedback.py",
    "tests/test_qt_all_runs_hover_seam.py",
    "tests/test_qt_output_path_layout.py",
    "tests/test_qt_run_deck_responsive_labels.py",
    "tests/test_qt_recovery_draft_retirement.py",
    "tests/test_qt_retry_recovery_membership.py",
    "tests/test_qt_move_dialog_content_fit.py",
    "tests/test_qt_move_root_notice.py",
    "tests/test_qt_inspector_recovery_details.py",
    "tests/test_qt_worker_control_context.py",
    "tests/test_qt_scroll_lifecycle.py",
    "tests/test_qt_vertical_scroll_chain.py",
    "tests/test_qt_artwork_continuity.py",
    "tests/test_qt_player_resize_continuity.py",
]
QT_SELECTOR_GROUPS = {
    "scene": ["tests/test_qt_scene_port.py"],
    "components": QT_COMPONENT_TESTS,
    "reported-regressions": QT_REPORTED_REGRESSIONS,
}


def native_surface_contract(repo_root, output_dir, *, profile="normal", ui="qt"):
    if ui != "qt":
        raise ValueError(f"Unsupported native UI renderer: {ui}")
    output_dir.mkdir(parents=True, exist_ok=True)
    report = output_dir / "native.xml"
    report.unlink(missing_ok=True)
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
        **(
            {"QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"}
            if ui == "qt"
            else {}
        ),
        "VODFORGE_NATIVE_FILE_QA": "1",
        "VODFORGE_ACTUAL_PLAYBACK_TESTS": "1",
        "VODFORGE_DISABLE_TELEMETRY": "1",
    }
    if ui == "qt":
        from .aggregate_observation import AggregateObservation, ref

        observation = AggregateObservation(
            "unit_static.native_surface_contract", output_dir, repo_root
        )
        # QGuiApplication and native worker state are process-wide. Keep every
        # required Qt test, but give the scene and component groups separate
        # processes and evidence directories.
        groups = (
            ("scene", ["tests/test_qt_scene_port.py"]),
            ("components", QT_COMPONENT_TESTS),
            ("reported-regressions", QT_REPORTED_REGRESSIONS),
        )
        group_results = []
        for name, tests in groups:
            group_dir = output_dir / name
            group_dir.mkdir(parents=True, exist_ok=True)
            group_report = group_dir / "native.xml"
            group_report.unlink(missing_ok=True)
            # Qt uses an offscreen QGuiApplication. The AppKit startup shim
            # used by Tk changes process startup and can destabilize repeated
            # Qt scene creation; match the direct package-build invocation.
            result = run_command(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-p",
                    "quality_harness.native_reports",
                    *tests,
                    "-q",
                    f"--junitxml={group_report}",
                ],
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
        outcome = (
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
                    "render_surface": "offscreen_qml_components",
                    "native_window_observed": False,
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
                + [
                    (
                        "Offscreen Qt component/event contracts; not native input, "
                        "displayed-window pixels, packaged or cross-platform proof"
                    )
                ],
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
        groups = {
            name: {
                key: ref(directory / filename)
                for key, filename in {
                    "command": "native-command.json",
                    "junit": "native.xml",
                    "collection": "native-collection.json",
                    "source_before": "native-source-before.json",
                    "source_after": "native-source-after.json",
                    "imports": "native-imports.json",
                }.items()
                if (directory / filename).is_file()
            }
            for name, directory, _report, _result in group_results
        }
        observation.finish(
            outcome[0], renderer="qt", native_window_observed=False, groups=groups
        )
        return outcome
    raise AssertionError("Qt native contract did not return its required report")
