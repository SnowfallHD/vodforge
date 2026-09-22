from __future__ import annotations

import json
import os
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .util import run_command

MUTANTS = (
    (
        "history_parse_cause_discarded",
        'cause="malformed_json"',
        'cause="unknown"',
    ),
    (
        "pending_history_document_misattributed",
        '_read_history_document(pending_history_path(path), document="pending")',
        '_read_history_document(pending_history_path(path), document="main")',
    ),
    (
        "history_url_query_redaction_removed",
        'return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path or "/", "", ""))',
        'return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path or "/", parsed.query, parsed.fragment))',
    ),
    (
        "history_identity_deduplication_reversed",
        "if history_identity(item) != identity\n        and not (",
        "if history_identity(item) == identity\n        and not (",
    ),
    (
        "run_activity_line_limit_reversed",
        "if len(result) >= MAX_RUN_ACTIVITY_LINES:",
        "if len(result) < MAX_RUN_ACTIVITY_LINES:",
    ),
    (
        "pending_history_staging_removed",
        "        _stage_history_mutation(path, mutation)",
        "        return  # injected missing durable acceptance",
    ),
    (
        "pending_history_restart_replay_removed",
        "records, count = recover_pending_history(path, records)",
        "records, count = _load_history_records(path), 0",
    ),
)

ARTWORK_MUTANTS = (
    (
        "artwork_stale_size_admitted",
        "if result is not None and self._artwork_submitted_size != self._artwork_size:",
        "if False and result is not None:",
    ),
    (
        "artwork_hero_size_ignored",
        'requested_specs.get(\n                        key, (requested_size, "", 8)\n                    )',
        '(requested_size, "", 8)',
    ),
)


def _workspace(repo_root: Path, destination: Path) -> Path:
    shutil.copytree(
        repo_root / "yt_downloader",
        destination / "yt_downloader",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    tests = destination / "tests"
    tests.mkdir(parents=True)
    for name in (
        "__init__.py",
        "test_history.py",
        "test_history_pending.py",
        "test_archive_relink.py",
        "test_archive_models.py",
        "test_archive_ui_owners.py",
        "test_archive_work.py",
        "test_archive_artwork.py",
        "test_matte_theme.py",
    ):
        shutil.copy2(repo_root / "tests" / name, tests / name)
    return destination


def mutation_detected(result: Any, report: Path) -> bool:
    """A collection/import error, timeout or unavailable runner is not a kill."""
    if result.returncode != 1 or result.timed_out or result.unavailable:
        return False
    try:
        cases = ET.parse(report).getroot().findall(".//testcase")
    except (OSError, ET.ParseError):
        return False
    return (
        bool(cases)
        and any(case.find("failure") is not None for case in cases)
        and not any(
            case.find("error") is not None or case.find("skipped") is not None
            for case in cases
        )
    )


def run_bounded_mutation_campaign(
    repo_root: Path, case_dir: Path
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run explicit, reviewable mutants in disposable copies of real production code."""
    case_dir.mkdir(parents=True, exist_ok=True)
    python = sys.executable
    environment = os.environ.copy()
    try:
        original_environment = json.loads(
            environment.get("VODFORGE_QUALITY_ORIGINAL_ENV", "{}")
        )
    except json.JSONDecodeError:
        original_environment = {}
    for key in ("HOME", "XDG_DATA_HOME", "LOCALAPPDATA", "TMPDIR", "TMP", "TEMP"):
        original_value = original_environment.get(key)
        if original_value is None:
            environment.pop(key, None)
        else:
            environment[key] = str(original_value)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [
        python,
        "-m",
        "pytest",
        "-q",
        "tests/test_history.py",
        "tests/test_history_pending.py",
        "tests/test_archive_artwork.py",
        "--junitxml=mutation.xml",
    ]
    started = time.monotonic()

    baseline_root = _workspace(repo_root, case_dir / "baseline")
    baseline = run_command(command, cwd=baseline_root, timeout=180, env=environment)
    (case_dir / "baseline.stdout.txt").write_text(baseline.stdout, encoding="utf-8")
    (case_dir / "baseline.stderr.txt").write_text(baseline.stderr, encoding="utf-8")

    mutant_results: list[dict[str, Any]] = []
    targets = [(item, "history.py") for item in MUTANTS] + [
        (item, "archive_artwork.py") for item in ARTWORK_MUTANTS
    ]
    for (mutant_id, original, replacement), source_file in targets:
        mutant_root = _workspace(repo_root, case_dir / mutant_id)
        source_path = mutant_root / "yt_downloader" / source_file
        source = source_path.read_text(encoding="utf-8")
        replacement_count = source.count(original)
        if replacement_count == 1:
            source_path.write_text(
                source.replace(original, replacement, 1), encoding="utf-8"
            )
            command_result = run_command(
                command, cwd=mutant_root, timeout=180, env=environment
            )
        else:
            command_result = None
        stdout = command_result.stdout if command_result else ""
        stderr = (
            command_result.stderr
            if command_result
            else f"expected mutation target count 1, observed {replacement_count}"
        )
        (case_dir / f"{mutant_id}.stdout.txt").write_text(stdout, encoding="utf-8")
        (case_dir / f"{mutant_id}.stderr.txt").write_text(stderr, encoding="utf-8")
        killed = bool(
            command_result
            and mutation_detected(command_result, mutant_root / "mutation.xml")
        )
        mutant_results.append(
            {
                "id": mutant_id,
                "target_replacement_count": replacement_count,
                "killed": killed,
                "returncode": command_result.returncode if command_result else None,
                "timed_out": command_result.timed_out if command_result else False,
                "duration_seconds": command_result.duration_seconds
                if command_result
                else 0.0,
                "output_excerpt": (stdout or stderr)[-800:],
            }
        )

    baseline_passed = baseline.returncode == 0
    killed_count = sum(1 for item in mutant_results if item["killed"])
    total = len(mutant_results)
    passed = baseline_passed and killed_count == total
    scenario = {
        "id": "unit_static.bounded_mutation_history",
        "evidence_tier": "unit_static",
        "category": "test quality",
        "status": "passed" if passed else "failed",
        "duration_seconds": round(time.monotonic() - started, 4),
        "metrics": {
            "baseline_returncode": baseline.returncode,
            "mutants_total": total,
            "mutants_killed": killed_count,
            "mutation_score_percent": round(killed_count / total * 100, 2)
            if total
            else None,
            "mutants": mutant_results,
        },
        "evidence": [
            f"Unmodified copied history and artwork tests return code: {baseline.returncode}",
            f"Bounded explicit mutants killed: {killed_count}/{total}",
            *[
                f"{item['id']}: {'killed' if item['killed'] else 'survived/invalid'} (rc={item['returncode']})"
                for item in mutant_results
            ],
            "This score covers bounded history/privacy/restart-recovery/diagnostic and responsive-artwork regressions and is not a repository-wide mutation score.",
        ],
        "artifacts": [str(case_dir)],
        "error": None,
    }
    findings = []
    if not passed:
        findings.append(
            {
                "id": "TEST-MUTATION-HISTORY-001",
                "title": "Existing history and artwork tests did not kill every bounded high-value mutant",
                "classification": "maintainability risk",
                "severity": "medium",
                "area": "History and Archive artwork production owners and regression tests",
                "reproduction": [
                    "Run ./engineering-quality/run normal --scenario unit_static.bounded_mutation_history.",
                    "Inspect each disposable mutant result under the scenario artifact directory.",
                ],
                "evidence": scenario["evidence"],
                "suggested_fix": "Add a focused assertion for each surviving behavior, then rerun the same bounded mutant set before widening the campaign.",
                "scenario_id": scenario["id"],
            }
        )
    return scenario, findings
