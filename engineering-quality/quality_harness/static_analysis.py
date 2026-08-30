from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from .util import run_command


def _tool_command(python: str, module: str, *args: str) -> list[str]:
    return [python, "-m", module, *args]


def run_static_suite(
    repo_root: Path, case_dir: Path, *, deep: bool = False
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    case_dir.mkdir(parents=True, exist_ok=True)
    python = sys.executable
    commands: list[tuple[str, list[str], float]] = [
        ("pytest", _tool_command(python, "pytest", "-q"), 300),
        (
            "pytest_harness",
            _tool_command(python, "pytest", "-q", "engineering-quality/tests"),
            300,
        ),
        (
            "compileall",
            _tool_command(python, "compileall", "-q", "yt_downloader", "tests"),
            120,
        ),
        (
            "ruff",
            _tool_command(
                python,
                "ruff",
                "check",
                "yt_downloader",
                "tests",
                "--output-format",
                "json",
            ),
            120,
        ),
        (
            "ruff_complexity",
            _tool_command(
                python,
                "ruff",
                "check",
                "yt_downloader",
                "--select",
                "C90,PLR0911,PLR0912,PLR0913,PLR0915",
                "--output-format",
                "json",
            ),
            120,
        ),
        (
            "ruff_format",
            _tool_command(
                python, "ruff", "format", "--check", "yt_downloader", "tests"
            ),
            120,
        ),
        (
            "mypy",
            _tool_command(
                python,
                "mypy",
                "--ignore-missing-imports",
                "--follow-imports=skip",
                "yt_downloader",
            ),
            300,
        ),
        (
            "bandit",
            _tool_command(python, "bandit", "-q", "-r", "yt_downloader", "-f", "json"),
            180,
        ),
        (
            "vulture",
            _tool_command(python, "vulture", "yt_downloader", "--min-confidence", "80"),
            120,
        ),
        (
            "radon_cc",
            _tool_command(python, "radon", "cc", "yt_downloader", "-j", "-s"),
            120,
        ),
        (
            "radon_mi",
            _tool_command(python, "radon", "mi", "yt_downloader", "-j", "-s"),
            120,
        ),
        ("pip_check", _tool_command(python, "pip", "check"), 120),
        (
            "pip_audit",
            _tool_command(python, "pip_audit", "-r", "requirements.txt", "-f", "json"),
            300,
        ),
    ]
    started = time.monotonic()
    outputs: dict[str, dict[str, Any]] = {}
    test_environment = os.environ.copy()
    try:
        original_environment = json.loads(
            test_environment.get("VODFORGE_QUALITY_ORIGINAL_ENV", "{}")
        )
    except json.JSONDecodeError:
        original_environment = {}
    for key in ("HOME", "XDG_DATA_HOME", "LOCALAPPDATA", "TMPDIR", "TMP", "TEMP"):
        original_value = original_environment.get(key)
        if original_value is None:
            test_environment.pop(key, None)
        else:
            test_environment[key] = str(original_value)
    for name, command, timeout in commands:
        command_environment = (
            test_environment if name in {"pytest", "pytest_harness"} else None
        )
        result = run_command(
            command, cwd=repo_root, timeout=timeout, env=command_environment
        )
        outputs[name] = result.as_dict()
        (case_dir / f"{name}.stdout.txt").write_text(result.stdout, encoding="utf-8")
        (case_dir / f"{name}.stderr.txt").write_text(result.stderr, encoding="utf-8")

    pytest_result = outputs["pytest"]
    harness_result = outputs["pytest_harness"]
    unavailable = [name for name, result in outputs.items() if result["unavailable"]]
    signals: dict[str, Any] = {}
    for name in ("ruff", "ruff_complexity"):
        try:
            parsed = json.loads(outputs[name]["stdout"] or "[]")
            signals[f"{name}_finding_count"] = (
                len(parsed) if isinstance(parsed, list) else None
            )
        except json.JSONDecodeError:
            signals[f"{name}_finding_count"] = None
    try:
        bandit = json.loads(outputs["bandit"]["stdout"] or "{}")
        signals["bandit_finding_count"] = len(bandit.get("results") or [])
        signals["bandit_metrics"] = bandit.get("metrics")
    except json.JSONDecodeError:
        signals["bandit_finding_count"] = None
    mypy_text = str(outputs["mypy"]["stdout"] or outputs["mypy"]["stderr"])
    try:
        signals["mypy_error_count"] = int(
            mypy_text.rsplit("Found ", 1)[1].split(" errors", 1)[0]
        )
    except (IndexError, ValueError):
        signals["mypy_error_count"] = 0 if outputs["mypy"]["returncode"] == 0 else None
    signals["format_check_failed"] = outputs["ruff_format"]["returncode"] != 0
    signals["vulture_signal_line_count"] = len(
        [
            line
            for line in str(outputs["vulture"]["stdout"]).splitlines()
            if line.strip()
        ]
    )
    command_failures = [
        name
        for name, result in outputs.items()
        if result["returncode"] not in {0, None}
    ]
    execution_gates = ("pytest", "pytest_harness", "compileall", "pip_check")
    execution_failures = [
        name for name in execution_gates if outputs[name]["returncode"] != 0
    ]
    passed = not unavailable and not command_failures
    findings: list[dict[str, Any]] = []
    if execution_failures:
        findings.append(
            {
                "id": "TEST-BASELINE-001",
                "title": "Existing repository tests failed in the engineering-quality environment",
                "classification": "correctness defect",
                "severity": "high",
                "area": "tests and production source",
                "reproduction": [
                    "Run the recorded pytest command from a clean checkout with harness dependencies installed."
                ],
                "evidence": [
                    pytest_result["stdout"][-2000:],
                    pytest_result["stderr"][-2000:],
                ],
                "suggested_fix": "Repair the failing behavior or test contract before using any downstream benchmark result.",
                "scenario_id": "unit_static.repository_suite",
            }
        )
    if unavailable:
        findings.append(
            {
                "id": "STATIC-TOOLING-UNAVAILABLE-001",
                "title": "The static-analysis benchmark environment is incomplete",
                "classification": "maintainability risk",
                "severity": "medium",
                "area": "engineering-quality dependency setup",
                "reproduction": [
                    "Install engineering-quality/requirements.txt in a clean checkout.",
                    "Run ./engineering-quality/run normal --scenario unit_static.repository_suite.",
                ],
                "evidence": [f"Unavailable tools: {unavailable}"],
                "suggested_fix": "Make every declared static tool installable in the documented harness environment and fail preflight when one is missing.",
                "scenario_id": "unit_static.repository_suite",
            }
        )
    ruff_count = int(signals.get("ruff_finding_count") or 0)
    complexity_count = int(signals.get("ruff_complexity_finding_count") or 0)
    if ruff_count or complexity_count or signals["format_check_failed"]:
        findings.append(
            {
                "id": "STATIC-LINT-COMPLEXITY-001",
                "title": "Lint, formatting, and complexity checks report unresolved quality signals",
                "classification": "code smell",
                "severity": "low",
                "area": "yt_downloader source and tests",
                "reproduction": [
                    "Run the recorded Ruff check, Ruff format check, and Ruff complexity commands."
                ],
                "evidence": [
                    f"Ruff findings: {ruff_count}",
                    f"Ruff complexity findings: {complexity_count}",
                    f"Formatting check failed: {signals['format_check_failed']}",
                ],
                "suggested_fix": "Triage and configure the signal set, repair objective defects and high-complexity hotspots first, then adopt an explicit repository baseline instead of silently ignoring nonzero tools.",
                "scenario_id": "unit_static.repository_suite",
            }
        )
    if signals.get("mypy_error_count"):
        findings.append(
            {
                "id": "STATIC-TYPE-CHECK-001",
                "title": "The source does not pass the configured type check",
                "classification": "maintainability risk",
                "severity": "medium",
                "area": "yt_downloader type contracts",
                "reproduction": ["Run the recorded mypy command."],
                "evidence": [
                    f"Mypy errors: {signals['mypy_error_count']}",
                    mypy_text[-1000:],
                ],
                "suggested_fix": "Introduce a checked baseline by module and remove errors incrementally, prioritizing worker/export-plan unions and state ownership boundaries.",
                "scenario_id": "unit_static.repository_suite",
            }
        )
    if signals.get("bandit_finding_count"):
        findings.append(
            {
                "id": "STATIC-BANDIT-SIGNALS-001",
                "title": "Bandit reports security-review signals that have not been triaged into reproducible findings",
                "classification": "code smell",
                "severity": "low",
                "area": "yt_downloader static security surface",
                "reproduction": [
                    "Run the recorded Bandit JSON command and review each result against reachable behavior."
                ],
                "evidence": [
                    f"Bandit signals: {signals['bandit_finding_count']}",
                    "These are static signals, not claimed vulnerabilities.",
                ],
                "suggested_fix": "Triage each signal, add focused reproductions for reachable issues, and document narrow suppressions for intentional subprocess/network behavior.",
                "scenario_id": "unit_static.repository_suite",
            }
        )
    if (
        outputs["pip_audit"]["returncode"] not in {0, None}
        and not outputs["pip_audit"]["unavailable"]
    ):
        findings.append(
            {
                "id": "STATIC-DEPENDENCY-AUDIT-001",
                "title": "The dependency vulnerability audit returned a nonzero result",
                "classification": "security defect",
                "severity": "medium",
                "area": "Python dependency set",
                "reproduction": [
                    "Run the recorded pip-audit command against requirements.txt."
                ],
                "evidence": [
                    (outputs["pip_audit"]["stdout"] or outputs["pip_audit"]["stderr"])[
                        -2000:
                    ]
                ],
                "suggested_fix": "Verify each advisory against the resolved runtime dependency, then upgrade or constrain affected packages and record the clean audit receipt.",
                "scenario_id": "unit_static.repository_suite",
            }
        )
    status = "passed" if passed else ("error" if unavailable else "failed")
    scenario = {
        "id": "unit_static.repository_suite",
        "evidence_tier": "unit_static",
        "category": "static and test quality",
        "status": status,
        "duration_seconds": round(time.monotonic() - started, 4),
        "metrics": {
            **signals,
            "tools_unavailable": unavailable,
            "command_failures": command_failures,
            "execution_gate_failures": execution_failures,
            "commands": outputs,
        },
        "evidence": [
            f"pytest return code: {pytest_result['returncode']}",
            f"pytest output: {(pytest_result['stdout'] or pytest_result['stderr']).strip()[-500:]}",
            f"harness self-test return code: {harness_result['returncode']}",
            f"Static tools unavailable: {unavailable}",
            f"Nonzero static/test commands: {command_failures}",
            f"Ruff={signals.get('ruff_finding_count')} complexity={signals.get('ruff_complexity_finding_count')} mypy={signals.get('mypy_error_count')} Bandit={signals.get('bandit_finding_count')}",
            "Nonzero static checks fail this benchmark scenario, but their individual outputs remain signals until reproduced and classified.",
        ],
        "artifacts": [str(case_dir)],
        "error": None,
    }
    return scenario, findings
