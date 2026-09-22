"""Required regression classes for Library recovery and Forge state authority.

Runs maintained behavioral probes against explicitly bound production sources.
Tcl traces and controlled projection/provider seams do not constitute native
window, network transfer, or packaged application evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from .util import run_command

_BASE = "tests/test_library_media_recovery.py::"
_NEW = "tests/test_library_recovery_regressions.py::"
REGRESSION_CLASSES = {
    "durable_roundtrip": (
        39,
        (
            "tests/test_recovery_writer_contract.py::test_new_executable_write_rejects_undurable_source_atomically",
            "tests/test_recovery_writer_contract.py::test_generated_queue_writer_restart_preserves_order_and_all_or_nothing",
            "tests/test_recovery_writer_contract.py::test_serialized_source_reason_is_bounded_and_private_input_not_restored",
            "tests/test_recovery_writer_contract.py::test_rejected_source_link_guidance_matches_actual_launch_refusal",
            "tests/test_recovery_missing_retry_url.py",
            "tests/test_run_recovery_observations.py::test_runtime_journal_refusal_is_observed_without_poisoning_recovery",
            "tests/test_run_recovery_observations.py::test_runtime_journal_observation_cannot_change_refusal_or_consent",
            "tests/test_run_recovery_observations.py::test_repeated_runtime_refusals_have_distinct_operations_and_stable_attempt",
        ),
    ),
    "canonical_facts": (
        3,
        (
            _NEW
            + "test_destination_updates_read_canonical_facts_and_never_reingest_rendered_projection",
        ),
    ),
    "selected_item": (
        19,
        (
            _BASE + "test_missing_item_recovery_downloads_only_captured_video",
            _BASE + "test_missing_identity_never_replays_original_playlist",
            _NEW
            + "test_recovery_admission_controls_history_retirement_and_bounded_migration_telemetry",
        ),
    ),
    "retired_presets": (
        27,
        (
            _BASE
            + "test_redownload_migrates_only_retired_presets_after_authority_validation",
            _BASE + "test_audio_recovery_ignores_retired_inactive_mp4_preset",
            _NEW
            + "test_incomplete_profile_only_recognized_legacy_presets_start_everyday",
        ),
    ),
    "bounded_expansion": (
        11,
        (
            _NEW
            + "test_actual_recovery_expansion_uses_one_saved_item_without_playlist_provider_work",
            _NEW
            + "test_recovery_fast_path_cannot_bypass_ordinary_or_mismatched_playlist_lookup",
        ),
    ),
    "draft_coherence": (
        3,
        (
            _NEW
            + "test_legacy_draft_visible_choice_submission_and_lifetime_match_without_saving_defaults",
        ),
    ),
}
REQUIRED_SCENARIOS = frozenset(
    "unit_static.recovery_" + name for name in REGRESSION_CLASSES
)


def source_binding(source: Path) -> dict:
    files = {
        path.relative_to(source).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted((source / "yt_downloader").rglob("*.py"))
    }
    if "yt_downloader/app.py" not in files:
        raise ValueError("Recovery probes require an explicit VODForge source tree")
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {"root": str(source.resolve()), "sha256": digest, "files": files}


def complete_report(
    path: Path, minimum: int, required_nodes: tuple[str, ...] = ()
) -> tuple[bool, int]:
    try:
        cases = ET.parse(path).getroot().findall(".//testcase")
    except (OSError, ET.ParseError):
        return False, 0
    observed = set()
    for case in cases:
        suite = case.get("classname", "").replace(".", "/") + ".py"
        name = case.get("name", "")
        observed.add(suite + "::" + name)
        observed.add(suite + "::" + name.split("[", 1)[0])
    return len(cases) >= minimum and set(required_nodes) <= observed and all(
        not any(case.find(tag) is not None for tag in ("skipped", "failure", "error"))
        for case in cases
    ), len(cases)


def recovery_class_contract(
    repo_root: Path,
    output_dir: Path,
    regression_class: str,
    *,
    source_root: Path | None = None,
    specification: tuple[int, tuple[str, ...]] | None = None,
    scenario_prefix: str = "unit_static.recovery_",
    required_nodes: tuple[str, ...] = (),
):
    minimum, selectors = specification or REGRESSION_CLASSES[regression_class]
    source = (source_root or repo_root).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "isolated-home").mkdir(exist_ok=True)
    report = output_dir / "cases.xml"
    report.unlink(missing_ok=True)
    before = source_binding(source)
    fixture_files = {selector.split("::")[0] for selector in selectors}
    fixtures = {
        name: hashlib.sha256((repo_root / name).read_bytes()).hexdigest()
        for name in sorted(fixture_files)
    }
    # Import the target first. Pytest then loads today's probes with importlib,
    # without allowing an old checkout or its tests to substitute production code.
    bootstrap = (
        "import pathlib,sys; "
        "target=pathlib.Path(sys.argv.pop(1)).resolve(); "
        "sys.path.insert(0,str(target)); "
        "import yt_downloader.app as app; "
        "assert pathlib.Path(app.__file__).resolve().is_relative_to(target); "
        "import pytest; raise SystemExit(pytest.main(sys.argv[1:]))"
    )
    result = run_command(
        [
            sys.executable,
            "-c",
            bootstrap,
            str(source),
            *[str(repo_root / selector) for selector in selectors],
            "--import-mode=importlib",
            "-q",
            f"--junitxml={report}",
        ],
        cwd=repo_root,
        timeout=180,
        env={
            **os.environ,
            "HOME": str(output_dir / "isolated-home"),
            "VODFORGE_NATIVE_UI_TESTS": "0",
            "VODFORGE_ACTUAL_PLAYBACK_TESTS": "0",
            "VODFORGE_DISABLE_TELEMETRY": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )
    after = source_binding(source)
    fixtures_after = {
        name: hashlib.sha256((repo_root / name).read_bytes()).hexdigest()
        if (repo_root / name).is_file()
        else None
        for name in sorted(fixture_files)
    }
    probes_unchanged = fixtures == fixtures_after
    if regression_class == "durable_roundtrip" and not required_nodes:
        required_nodes = tuple(selector for selector in selectors if "::" in selector)
    complete, count = complete_report(report, minimum, required_nodes)
    raw = output_dir / "command.json"
    raw.write_text(json.dumps(result.as_dict(), indent=2) + "\n")
    binding = output_dir / "source-binding.json"
    binding.write_text(
        json.dumps(
            {
                "before": before,
                "after": after,
                "unchanged": before == after,
                "required_nodeids": required_nodes,
                "probe_files": fixtures,
                "probe_files_after": fixtures_after,
                "probes_unchanged": probes_unchanged,
                "scope": "Bound production source, controlled seams and headless Tcl; not packaged or native-window proof",
            },
            indent=2,
        )
        + "\n"
    )
    passed = (
        result.returncode == 0
        and not result.timed_out
        and not result.unavailable
        and complete
        and before == after
        and probes_unchanged
    )
    scenario = {
        "id": scenario_prefix + regression_class,
        "evidence_tier": "unit_static",
        "category": "reliability",
        "status": "passed" if passed else "failed",
        "duration_seconds": result.duration_seconds,
        "metrics": {
            "cases_executed": count,
            "minimum_cases": minimum,
            "required_nodeids": list(required_nodes),
            "source_unchanged": before == after,
            "probes_unchanged": probes_unchanged,
            "timed_out": result.timed_out,
            "unavailable": result.unavailable,
        },
        "evidence": [
            f"Regression class: {regression_class}; production tree SHA256: {before['sha256']}",
            f"Cases: {count}; minimum required: {minimum}; complete success: {complete}",
            "Actual production owners; controlled provider/display seams and headless Tcl traces.",
            "Native resize and exact packaged journey remain separate required gates.",
        ],
        "artifacts": [str(report), str(raw), str(binding)],
        "error": None
        if passed
        else "Regression class failed or evidence was incomplete",
    }
    return scenario, []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, help="Explicit before or candidate source tree"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--class", dest="classes", choices=REGRESSION_CLASSES, action="append"
    )
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    scenarios = [
        recovery_class_contract(
            repo, args.output / name, name, source_root=args.source
        )[0]
        for name in (args.classes or REGRESSION_CLASSES)
    ]
    payload = {
        "scope": "Source regressions only; no packaged/native-window claim",
        "scenarios": scenarios,
        "passed": all(item["status"] == "passed" for item in scenarios),
    }
    (args.output / "recovery-contract.json").write_text(
        json.dumps(payload, indent=2) + "\n"
    )
    print(json.dumps({item["id"]: item["status"] for item in scenarios}, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
