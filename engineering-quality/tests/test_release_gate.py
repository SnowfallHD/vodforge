from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from quality_harness.release_gate import (
    DEEP_REQUIRED_SCENARIOS,
    FAST_REQUIRED_COMMANDS,
    NORMAL_REQUIRED_SCENARIOS,
    build_release_receipt,
    evaluate_candidate_binding,
    evaluate_candidate_receipt,
    evaluate_engineering_result,
    evaluate_fast_result,
    evaluate_packaged_e2e_receipt,
    gate_outcome,
    markdown_release_receipt,
    profile_invocations,
    write_release_receipt,
)


def _command(returncode: int = 0, stdout: str = "") -> dict[str, Any]:
    return {
        "command": ["tool"],
        "returncode": returncode,
        "duration_seconds": 0.1,
        "stdout": stdout,
        "stderr": "",
        "timed_out": False,
        "unavailable": False,
    }


def _static_scenario(*, complexity: int = 74) -> dict[str, Any]:
    commands = {name: _command() for name in FAST_REQUIRED_COMMANDS}
    commands["pytest"]["stdout"] = "548 passed in 5.0s\n"
    commands["pytest_harness"]["stdout"] = "24 passed in 0.8s\n"
    return {
        "id": "unit_static.repository_suite",
        "status": "failed" if complexity else "passed",
        "evidence_tier": "unit_static",
        "metrics": {
            "commands": commands,
            "ruff_complexity_finding_count": complexity,
            "command_failures": ["ruff_complexity"] if complexity else [],
            "execution_gate_failures": [],
        },
        "evidence": ["The source receipt remains unchanged."],
    }


def _scenario(scenario_id: str, status: str = "passed") -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    if scenario_id == "lifecycle.repeated_job_soak":
        metrics = {
            "jobs_attempted": 100,
            "jobs_completed": 100,
            "jobs_failed": 0,
            "worker_object_count_deltas": {
                "yt_dlp.YoutubeDL.YoutubeDL": 0,
                "yt_downloader.models.DownloadJob": 0,
            },
            "fd_delta": 0,
            "orphaned_child_processes": 0,
            "peak_zombie_processes": 0,
            "staging_residue_count": 0,
            "rss_delta_bytes": -1024,
            "rss_growth_description": {"post_warmup_linear_slope_per_job": -1.0},
        }
    return {
        "id": scenario_id,
        "status": status,
        "evidence_tier": "headless_production_pipeline",
        "metrics": metrics,
        "evidence": [f"{scenario_id}={status}"],
    }


def _engineering_result(profile: str) -> dict[str, Any]:
    required = (
        DEEP_REQUIRED_SCENARIOS if profile == "deep" else NORMAL_REQUIRED_SCENARIOS
    )
    scenarios = [_scenario(scenario_id) for scenario_id in sorted(required)]
    scenarios.extend(
        [
            _static_scenario(),
            {
                "id": "maintainability.change_surface",
                "status": "failed",
                "evidence_tier": "unit_static",
                "metrics": {"app_module_lines": 12925, "change_probes": []},
                "evidence": ["Broad change surface remains visible."],
            },
            {
                "id": "packaged_app_e2e.full_journey",
                "status": "passed" if profile == "deep" else "skipped",
                "evidence_tier": "packaged_app_e2e",
                "metrics": {},
                "evidence": ["packaged receipt"],
            },
        ]
    )
    return {
        "schema_version": "1.0.0",
        "profile": profile,
        "repository": {"commit": "a" * 40, "branch": "candidate"},
        "machine": {"system": "Darwin", "machine": "arm64"},
        "tool_versions": {"pytest": "9"},
        "summary": {"passed": 24, "failed": 2, "errors": 0, "skipped": 0},
        "aggregate_metrics": {"job_initialization_seconds": {"p50": 0.1}},
        "scenarios": scenarios,
        "findings": [],
    }


def _candidate(*, policy: str = "release") -> dict[str, Any]:
    release = policy == "release"
    return {
        "schema_version": "1.0.0",
        "candidate_id": "candidate-1",
        "candidate_version": "0.1.7",
        "artifact_policy": policy,
        "source": {"commit": "a" * 40, "branch": "candidate", "clean": True},
        "build": {"command": ["./build_and_package_macos.sh", "0.1.7"]},
        "immutable_archive": {
            "path": "/candidate/VODForge.zip",
            "sha256": "b" * 64,
            "size_bytes": 123,
        },
        "artifact": {
            "artifact": "/candidate/VODForge.app",
            "artifact_policy": policy,
            "bundle_tree": {"sha256": "c" * 64},
            "bundle_version": "0.1.7",
            "runtime_version": "0.1.7",
            "signature_state": "developer_id" if release else "development_ad_hoc",
            "notarization_state": "stapled" if release else "not_stapled",
            "gatekeeper_state": "accepted" if release else "not_release_accepted",
            "policy_verified": True,
            "release_identity_verified": release,
            "release_eligible": release,
        },
        "verification": {
            "archive_sha256": "b" * 64,
            "bundle_tree_sha256": "c" * 64,
            "packaged_e2e_eligible": True,
            "publish_eligible": release,
            "verified": True,
        },
        "packaged_e2e_eligible": True,
        "publish_eligible": release,
    }


def _packaged_e2e(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "scenario": {
            "id": "packaged_app_e2e.full_journey",
            "status": "passed",
            "evidence_tier": "packaged_app_e2e",
            "evidence": ["full journey"],
            "metrics": {
                "artifact_verified": True,
                "artifact_integrity_verified": True,
                "process_provenance_verified": True,
                "ui_interaction_observed": True,
                "final_output_probed": True,
                "restart_history_persistence_verified": True,
                "clean_exit": True,
                "staging_residue_count": 0,
                "peak_zombie_processes": 0,
                "unexpected_process_exit": False,
                "harness_forced_termination": False,
                "pipeline_stage_receipts": {
                    "yt_dlp_or_download": True,
                    "ffmpeg_transcode": True,
                    "ffprobe_validation": True,
                    "atomic_commit": True,
                },
            },
        },
        "candidate_binding": {
            "candidate_id": candidate["candidate_id"],
            "archive_sha256": candidate["immutable_archive"]["sha256"],
            "bundle_tree_sha256": candidate["artifact"]["bundle_tree"]["sha256"],
            "verified": True,
        },
        "artifact_integrity": {"verified": True},
        "process_provenance": {"verified": True},
        "findings": [],
    }


def test_profile_invocations_use_existing_harness_commands(tmp_path: Path) -> None:
    fast = profile_invocations("fast", output_root=tmp_path)
    normal = profile_invocations("normal", output_root=tmp_path)
    e2e = tmp_path / "e2e-result.json"
    deep = profile_invocations("deep", output_root=tmp_path, packaged_e2e_result=e2e)

    assert fast[0].command[:4] == (
        "./engineering-quality/run",
        "normal",
        "--scenario",
        "unit_static.repository_suite",
    )
    assert normal[0].command[1] == "normal"
    assert deep[0].command[1:4] == ("deep", "--soak-jobs", "100")
    assert str(e2e.resolve()) in deep[0].command
    with pytest.raises(ValueError, match="exact-candidate"):
        profile_invocations("deep", output_root=tmp_path)


def test_fast_gate_preserves_complexity_as_failed_nonblocking_debt() -> None:
    checks = evaluate_fast_result(
        {
            "scenarios": [
                _static_scenario(),
                _scenario("unit_static.bounded_mutation_history", "passed"),
            ]
        }
    )

    required = [item for item in checks if item["required"]]
    complexity = next(item for item in checks if item["id"].endswith("complexity"))
    assert all(item["status"] == "passed" for item in required)
    assert complexity["status"] == "failed"
    assert complexity["required"] is False
    assert gate_outcome(checks) == "passed"


def test_missing_or_failed_required_evidence_fails_closed() -> None:
    missing = evaluate_fast_result({"scenarios": []})
    assert missing[0]["status"] == "unproven"
    assert gate_outcome(missing) == "unproven"

    result = _engineering_result("normal")
    result["scenarios"].append(_scenario("new.security.contract", "failed"))
    checks = evaluate_engineering_result(result, profile="normal")
    new_check = next(item for item in checks if "new.security.contract" in item["id"])
    assert new_check["required"] is True
    assert new_check["status"] == "failed"
    assert gate_outcome(checks) == "failed"


def test_development_candidate_is_testable_but_not_release_trusted() -> None:
    checks = evaluate_candidate_receipt(_candidate(policy="development"))
    trust = next(item for item in checks if item["id"] == "candidate.release_trust")
    assert trust["status"] == "unproven"
    assert trust["required"] is True
    assert gate_outcome(checks) == "unproven"


def test_candidate_binding_requires_all_three_exact_identities() -> None:
    candidate = _candidate()
    packaged = _packaged_e2e(candidate)
    assert evaluate_candidate_binding(candidate, packaged)[0]["status"] == "passed"

    packaged["candidate_binding"]["archive_sha256"] = "d" * 64
    check = evaluate_candidate_binding(candidate, packaged)[0]
    assert check["status"] == "failed"
    assert "match=False" in " ".join(check["evidence"])


def test_packaged_receipt_requires_independent_pipeline_and_provenance_receipts() -> (
    None
):
    candidate = _candidate()
    packaged = _packaged_e2e(candidate)
    checks = evaluate_packaged_e2e_receipt(packaged)
    assert gate_outcome(checks) == "passed"

    packaged["scenario"]["metrics"]["pipeline_stage_receipts"]["atomic_commit"] = False
    checks = evaluate_packaged_e2e_receipt(packaged)
    receipt_check = next(
        item for item in checks if item["id"] == "packaged_e2e.independent_receipts"
    )
    assert receipt_check["status"] == "failed"
    assert gate_outcome(checks) == "failed"


def test_release_receipt_allows_visible_debt_but_blocks_required_gaps() -> None:
    candidate = _candidate()
    fast = {
        **_engineering_result("normal"),
        "scenarios": [
            _static_scenario(),
            _scenario("unit_static.bounded_mutation_history"),
        ],
    }
    normal = _engineering_result("normal")
    deep = _engineering_result("deep")
    packaged = _packaged_e2e(candidate)

    receipt = build_release_receipt(
        candidate=candidate,
        fast_result=fast,
        normal_result=normal,
        deep_result=deep,
        packaged_e2e=packaged,
        commands_used=[["./engineering-quality/run", "fast"]],
        generated_at="2026-08-31T00:00:00+00:00",
    )

    assert receipt["status"] == "passed"
    assert receipt["release_eligible"] is True
    assert receipt["test_counts"]["repository"] == 548
    assert receipt["test_counts"]["harness_self_tests"] == 24
    assert receipt["known_debt"]
    assert {item["status"] for item in receipt["known_debt"]} == {"failed"}
    assert receipt["summary"]["blocking_check_ids"] == []
    schema = json.loads(
        (
            Path(__file__).parents[1] / "schemas" / "release-receipt.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        list(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
                receipt
            )
        )
        == []
    )

    packaged["candidate_binding"]["verified"] = False
    blocked = build_release_receipt(
        candidate=candidate,
        fast_result=fast,
        normal_result=normal,
        deep_result=deep,
        packaged_e2e=packaged,
        commands_used=[],
        generated_at="2026-08-31T00:00:00+00:00",
    )
    assert blocked["status"] == "failed"
    assert blocked["release_eligible"] is False
    assert "packaged_e2e.candidate_binding" in blocked["summary"]["blocking_check_ids"]


def test_markdown_and_json_keep_skipped_unproven_and_failed_distinct(
    tmp_path: Path,
) -> None:
    receipt = {
        "schema_version": "1.0.0",
        "receipt_type": "vodforge_release_gate",
        "status": "unproven",
        "release_eligible": False,
        "generated_at": "2026-08-31T00:00:00+00:00",
        "candidate": {
            "candidate_id": "candidate",
            "version": "1.2.3",
            "source_commit": "a" * 40,
            "source_branch": "test",
            "archive_sha256": "a" * 64,
            "artifact_policy": "development",
        },
        "summary": {
            "checks": 3,
            "status_counts": {"unproven": 1, "skipped": 1, "failed": 1},
            "required_status_counts": {"unproven": 1, "skipped": 1},
            "blocking_check_ids": ["required.unproven"],
            "known_debt_count": 1,
        },
        "checks": [
            {
                "id": "required.unproven",
                "label": "unproven",
                "status": "unproven",
                "required": True,
                "evidence": ["missing"],
                "metrics": {},
            },
            {
                "id": "required.skipped",
                "label": "skipped",
                "status": "skipped",
                "required": True,
                "evidence": ["not run"],
                "metrics": {},
            },
            {
                "id": "debt.failed",
                "label": "debt",
                "status": "failed",
                "required": False,
                "evidence": ["visible"],
                "metrics": {},
            },
        ],
        "test_counts": {},
        "lifecycle": {},
        "packaged_e2e": {},
        "performance_observations": {},
        "machine": {},
        "security_findings": [],
        "known_debt": [],
        "commands_used": [],
    }
    rendered = markdown_release_receipt(receipt)
    assert "| UNPROVEN | yes |" in rendered
    assert "| SKIPPED | yes |" in rendered
    assert "| FAILED | no |" in rendered

    paths = write_release_receipt(tmp_path, receipt)
    stored = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert stored["release_eligible"] is False
    assert paths["markdown"].read_text(encoding="utf-8") == rendered
