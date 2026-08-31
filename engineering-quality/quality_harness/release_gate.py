from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .schema_validation import validate_receipt_schema
from .util import json_dump

GateStatus = Literal["passed", "failed", "skipped", "unproven"]
GateProfile = Literal["fast", "normal", "deep"]

RELEASE_RECEIPT_SCHEMA_VERSION = "1.0.0"

# These two scenarios are deliberately retained as visible architecture debt.
# Nothing else is permitted to fail without blocking a release receipt.
NONBLOCKING_DEBT_SCENARIOS = frozenset({"maintainability.change_surface"})

NORMAL_REQUIRED_SCENARIOS = frozenset(
    {
        "correctness.local_mp4_real_pipeline",
        "correctness.local_mp3_bitrate_real_pipeline",
        "correctness.local_mp4_embedding_disabled",
        "correctness.source_quality_selection_360p",
        "correctness.source_quality_selection_720p",
        "correctness.fresh_output_plan_validation",
        "reliability.http_404_cleanup",
        "reliability.transient_http_retry",
        "reliability.cancel_during_slow_download",
        "reliability.cancel_during_transcode",
        "reliability.network_interruption_recovery",
        "reliability.unwritable_output_directory",
        "reliability.ffmpeg_child_failure",
        "reliability.batch_failure_report_reset",
        "unit_static.activity_log_failure_receipt",
        "reliability.malformed_url",
        "lifecycle.repeated_job_soak",
        "concurrency.simultaneous_worker_attack",
        "security.path_and_subprocess_arguments",
        "security.symlink_containment_and_staging_permissions",
        "security.url_secret_persistence",
        "security.thumbnail_network_authority",
        "unit_static.bounded_mutation_history",
    }
)

DEEP_REQUIRED_SCENARIOS = NORMAL_REQUIRED_SCENARIOS | {
    "correctness.public_w3c_generic_boundary",
}

FAST_REQUIRED_COMMANDS = (
    "pytest",
    "pytest_harness",
    "compileall",
    "ruff",
    "ruff_format",
    "mypy",
    "bandit",
    "vulture",
    "pip_check",
    "pip_audit",
)


@dataclass(frozen=True)
class GateInvocation:
    """One existing harness command needed to produce a profile receipt."""

    id: str
    command: tuple[str, ...]
    output_dir: Path

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "command": list(self.command),
            "output_dir": str(self.output_dir),
        }


def profile_invocations(
    profile: GateProfile,
    *,
    output_root: Path,
    harness_command: str = "./engineering-quality/run",
    packaged_e2e_result: Path | None = None,
) -> list[GateInvocation]:
    """Return the ordinary harness commands that supply a gate profile.

    The release gate consumes their original receipts. It does not replace or
    soften scenario execution. Callers run FAST, NORMAL, then DEEP in order.
    """

    output_root = output_root.resolve()
    if profile == "fast":
        output_dir = output_root / "fast"
        return [
            GateInvocation(
                id="fast.unit_static",
                command=(
                    harness_command,
                    "normal",
                    "--scenario",
                    "unit_static.repository_suite",
                    "--scenario",
                    "unit_static.bounded_mutation_history",
                    "--output-dir",
                    str(output_dir),
                ),
                output_dir=output_dir,
            )
        ]
    if profile == "normal":
        output_dir = output_root / "normal"
        return [
            GateInvocation(
                id="normal.engineering_quality",
                command=(
                    harness_command,
                    "normal",
                    "--output-dir",
                    str(output_dir),
                ),
                output_dir=output_dir,
            )
        ]
    if packaged_e2e_result is None:
        raise ValueError("DEEP requires an exact-candidate packaged E2E receipt")
    output_dir = output_root / "deep"
    return [
        GateInvocation(
            id="deep.engineering_quality",
            command=(
                harness_command,
                "deep",
                "--soak-jobs",
                "100",
                "--e2e-result",
                str(packaged_e2e_result.resolve()),
                "--output-dir",
                str(output_dir),
            ),
            output_dir=output_dir,
        )
    ]


def _check(
    check_id: str,
    *,
    label: str,
    status: GateStatus,
    required: bool,
    evidence: Sequence[str],
    source_status: str | None = None,
    metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "label": label,
        "status": status,
        "required": required,
        "source_status": source_status,
        "evidence": [str(item) for item in evidence],
        "metrics": dict(metrics or {}),
    }


def _source_status(value: Any) -> GateStatus:
    if value == "passed":
        return "passed"
    if value == "skipped":
        return "skipped"
    if value in {"failed", "error"}:
        return "failed"
    return "unproven"


def _scenario_index(result: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    scenarios = result.get("scenarios")
    if not isinstance(scenarios, list):
        return {}
    return {
        str(item["id"]): item
        for item in scenarios
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }


def _command_check(
    name: str, commands: Mapping[str, Any], *, prefix: str
) -> dict[str, Any]:
    value = commands.get(name)
    if not isinstance(value, Mapping):
        return _check(
            f"{prefix}.command.{name}",
            label=f"{name} command",
            status="unproven",
            required=True,
            evidence=["The static-suite receipt did not contain this command."],
        )
    returncode = value.get("returncode")
    unavailable = value.get("unavailable") is True
    timed_out = value.get("timed_out") is True
    if unavailable or returncode is None:
        status: GateStatus = "unproven"
    else:
        status = "passed" if returncode == 0 and not timed_out else "failed"
    return _check(
        f"{prefix}.command.{name}",
        label=f"{name} command",
        status=status,
        required=True,
        source_status=str(returncode) if returncode is not None else None,
        evidence=[
            f"returncode={returncode!r}",
            f"timed_out={timed_out}",
            f"unavailable={unavailable}",
        ],
        metrics={
            "duration_seconds": value.get("duration_seconds"),
            "returncode": returncode,
        },
    )


def evaluate_fast_result(
    result: Mapping[str, Any], *, prefix: str = "fast"
) -> list[dict[str, Any]]:
    """Evaluate the execution checks inside the existing static-suite receipt."""

    scenarios = _scenario_index(result)
    static = scenarios.get("unit_static.repository_suite")
    if static is None:
        return [
            _check(
                f"{prefix}.static_receipt",
                label="Static/test scenario receipt",
                status="unproven",
                required=True,
                evidence=["unit_static.repository_suite is missing."],
            )
        ]
    metrics = static.get("metrics")
    commands = metrics.get("commands") if isinstance(metrics, Mapping) else None
    if not isinstance(commands, Mapping):
        commands = {}
    checks = [
        _command_check(name, commands, prefix=prefix) for name in FAST_REQUIRED_COMMANDS
    ]

    complexity_count = (
        metrics.get("ruff_complexity_finding_count")
        if isinstance(metrics, Mapping)
        else None
    )
    complexity_status: GateStatus
    if not isinstance(complexity_count, int):
        complexity_status = "unproven"
    else:
        complexity_status = "passed" if complexity_count == 0 else "failed"
    checks.append(
        _check(
            f"{prefix}.debt.complexity",
            label="Visible complexity debt",
            status=complexity_status,
            required=False,
            source_status=str(static.get("status")),
            evidence=[
                f"Ruff complexity signals: {complexity_count!r}",
                "Complexity remains visible but is not a release-safety gate without a reproduced defect.",
            ],
            metrics={"ruff_complexity_finding_count": complexity_count},
        )
    )
    command_failures = (
        metrics.get("command_failures") if isinstance(metrics, Mapping) else None
    )
    if not isinstance(command_failures, list):
        unexpected_failures: list[str] | None = None
        failure_status: GateStatus = "unproven"
    else:
        unexpected_failures = sorted(
            str(name) for name in command_failures if name != "ruff_complexity"
        )
        failure_status = "failed" if unexpected_failures else "passed"
    checks.append(
        _check(
            f"{prefix}.unexpected_command_failures",
            label="No unreviewed static-suite command failures",
            status=failure_status,
            required=True,
            evidence=[
                f"command_failures={command_failures!r}",
                "Only the separately reported Ruff complexity debt is nonblocking.",
            ],
            metrics={"unexpected_failures": unexpected_failures},
        )
    )
    checks.append(
        _scenario_check(
            "unit_static.bounded_mutation_history",
            scenarios.get("unit_static.bounded_mutation_history"),
            prefix=prefix,
            required=True,
        )
    )
    return checks


def _scenario_check(
    scenario_id: str,
    scenario: Mapping[str, Any] | None,
    *,
    prefix: str,
    required: bool,
) -> dict[str, Any]:
    if scenario is None:
        return _check(
            f"{prefix}.scenario.{scenario_id}",
            label=scenario_id,
            status="unproven",
            required=required,
            evidence=["Required scenario is missing from the harness receipt."],
        )
    source = scenario.get("status")
    evidence = scenario.get("evidence")
    return _check(
        f"{prefix}.scenario.{scenario_id}",
        label=scenario_id,
        status=_source_status(source),
        required=required,
        source_status=str(source) if source is not None else None,
        evidence=(
            [str(item) for item in evidence[:6]]
            if isinstance(evidence, list)
            else ["Scenario supplied no evidence list."]
        ),
        metrics=(
            scenario.get("metrics")
            if isinstance(scenario.get("metrics"), Mapping)
            else {}
        ),
    )


def evaluate_engineering_result(
    result: Mapping[str, Any],
    *,
    profile: Literal["normal", "deep"],
    prefix: str | None = None,
) -> list[dict[str, Any]]:
    """Turn an unmodified normal/deep harness receipt into release checks."""

    prefix = prefix or profile
    checks: list[dict[str, Any]] = []
    observed_profile = result.get("profile")
    checks.append(
        _check(
            f"{prefix}.receipt.profile",
            label=f"{profile.upper()} receipt profile",
            status="passed" if observed_profile == profile else "failed",
            required=True,
            evidence=[f"expected={profile!r} observed={observed_profile!r}"],
        )
    )
    scenarios = _scenario_index(result)
    expected = (
        DEEP_REQUIRED_SCENARIOS if profile == "deep" else NORMAL_REQUIRED_SCENARIOS
    )
    for scenario_id in sorted(expected):
        checks.append(
            _scenario_check(
                scenario_id,
                scenarios.get(scenario_id),
                prefix=prefix,
                required=True,
            )
        )

    # Fail closed for newly added harness scenarios. Only the two explicitly
    # reviewed debt surfaces and NORMAL's intentionally separate packaged tier
    # may remain nonblocking.
    reviewed = set(expected) | {
        "unit_static.repository_suite",
        "maintainability.change_surface",
        "packaged_app_e2e.full_journey",
    }
    for scenario_id in sorted(set(scenarios) - reviewed):
        checks.append(
            _scenario_check(
                scenario_id,
                scenarios[scenario_id],
                prefix=prefix,
                required=True,
            )
        )

    checks.extend(evaluate_fast_result(result, prefix=f"{prefix}.static"))
    for scenario_id in sorted(NONBLOCKING_DEBT_SCENARIOS):
        checks.append(
            _scenario_check(
                scenario_id,
                scenarios.get(scenario_id),
                prefix=f"{prefix}.debt",
                required=False,
            )
        )
    packaged = scenarios.get("packaged_app_e2e.full_journey")
    checks.append(
        _scenario_check(
            "packaged_app_e2e.full_journey",
            packaged,
            prefix=prefix,
            required=profile == "deep",
        )
    )
    if profile == "deep":
        checks.append(_deep_soak_contract(scenarios.get("lifecycle.repeated_job_soak")))
    return checks


def _deep_soak_contract(scenario: Mapping[str, Any] | None) -> dict[str, Any]:
    metrics = scenario.get("metrics") if isinstance(scenario, Mapping) else None
    if not isinstance(metrics, Mapping):
        return _check(
            "deep.lifecycle.100_job_contract",
            label="100-job retained-object/lifecycle contract",
            status="unproven",
            required=True,
            evidence=["Deep receipt has no lifecycle soak metrics."],
        )
    deltas = metrics.get("worker_object_count_deltas")
    youtube_delta = (
        deltas.get("yt_dlp.YoutubeDL.YoutubeDL")
        if isinstance(deltas, Mapping)
        else None
    )
    job_delta = (
        deltas.get("yt_downloader.models.DownloadJob")
        if isinstance(deltas, Mapping)
        else None
    )
    conditions = {
        "jobs_attempted_100": metrics.get("jobs_attempted") == 100,
        "jobs_completed_100": metrics.get("jobs_completed") == 100,
        "jobs_failed_zero": metrics.get("jobs_failed") == 0,
        "youtube_dl_delta_zero": youtube_delta == 0,
        "download_job_delta_zero": job_delta == 0,
        "fd_delta_zero": metrics.get("fd_delta") == 0,
        "orphaned_children_zero": metrics.get("orphaned_child_processes") == 0,
        "zombie_signals_zero": metrics.get("peak_zombie_processes") == 0,
        "staging_residue_zero": metrics.get("staging_residue_count") == 0,
    }
    return _check(
        "deep.lifecycle.100_job_contract",
        label="100-job retained-object/lifecycle contract",
        status="passed" if all(conditions.values()) else "failed",
        required=True,
        source_status=str(scenario.get("status")) if scenario else None,
        evidence=[f"{name}={value}" for name, value in conditions.items()],
        metrics={
            **conditions,
            "rss_delta_bytes": metrics.get("rss_delta_bytes"),
            "rss_growth_description": metrics.get("rss_growth_description"),
            "traced_python_growth_description": metrics.get(
                "traced_python_growth_description"
            ),
        },
    )


def evaluate_candidate_receipt(candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
    verification = candidate.get("verification")
    artifact = candidate.get("artifact")
    archive = candidate.get("immutable_archive")
    source = candidate.get("source")
    verification = verification if isinstance(verification, Mapping) else {}
    artifact = artifact if isinstance(artifact, Mapping) else {}
    archive = archive if isinstance(archive, Mapping) else {}
    source = source if isinstance(source, Mapping) else {}
    identity_present = all(
        isinstance(value, str) and bool(value)
        for value in (
            candidate.get("candidate_id"),
            source.get("commit"),
            archive.get("sha256"),
            candidate.get("candidate_version"),
        )
    )
    source_clean = source.get("clean")
    if source_clean is True:
        source_status: GateStatus = "passed"
    elif source_clean is False:
        source_status = "failed"
    else:
        source_status = "unproven"
    bundle_tree = artifact.get("bundle_tree")
    bundle_tree = bundle_tree if isinstance(bundle_tree, Mapping) else {}
    expected_archive_hash = archive.get("sha256")
    observed_archive_hash = verification.get("archive_sha256")
    expected_tree_hash = bundle_tree.get("sha256")
    observed_tree_hash = verification.get("bundle_tree_sha256")
    verification_fields_present = all(
        value is not None
        for value in (
            verification.get("verified"),
            verification.get("packaged_e2e_eligible"),
            expected_archive_hash,
            observed_archive_hash,
            expected_tree_hash,
            observed_tree_hash,
        )
    )
    verification_matches = (
        verification.get("verified") is True
        and verification.get("packaged_e2e_eligible") is True
        and observed_archive_hash == expected_archive_hash
        and observed_tree_hash == expected_tree_hash
    )
    if verification_fields_present and verification_matches:
        verification_status: GateStatus = "passed"
    elif verification_fields_present:
        verification_status = "failed"
    else:
        verification_status = "unproven"
    checks = [
        _check(
            "candidate.identity",
            label="Immutable candidate identity",
            status="passed" if identity_present else "unproven",
            required=True,
            evidence=[
                f"candidate_id={candidate.get('candidate_id')!r}",
                f"commit={source.get('commit')!r}",
                f"archive_sha256={archive.get('sha256')!r}",
                f"version={candidate.get('candidate_version')!r}",
            ],
        ),
        _check(
            "candidate.source_clean",
            label="Clean source checkpoint",
            status=source_status,
            required=True,
            evidence=[f"source.clean={source.get('clean')!r}"],
        ),
        _check(
            "candidate.verification",
            label="Candidate archive and extracted bundle verification",
            status=verification_status,
            required=True,
            evidence=[
                f"verified={verification.get('verified')!r}",
                f"packaged_e2e_eligible={verification.get('packaged_e2e_eligible')!r}",
                f"archive_sha256={verification.get('archive_sha256')!r}",
                f"bundle_tree_sha256={verification.get('bundle_tree_sha256')!r}",
            ],
        ),
    ]
    artifact_policy = candidate.get("artifact_policy")
    release_eligible = (
        artifact_policy == "release"
        and artifact.get("release_eligible") is True
        and verification.get("publish_eligible") is True
        and candidate.get("publish_eligible") is True
    )
    if release_eligible:
        trust_status: GateStatus = "passed"
    elif artifact_policy == "release":
        trust_status = "failed"
    else:
        trust_status = "unproven"
    checks.append(
        _check(
            "candidate.release_trust",
            label="Release signing, notarization, and Gatekeeper trust",
            status=trust_status,
            required=True,
            evidence=[
                f"artifact_policy={artifact.get('artifact_policy')!r}",
                f"signature_state={artifact.get('signature_state')!r}",
                f"notarization_state={artifact.get('notarization_state')!r}",
                f"gatekeeper_state={artifact.get('gatekeeper_state')!r}",
                f"release_eligible={artifact.get('release_eligible')!r}",
            ],
        )
    )
    return checks


def evaluate_packaged_e2e_receipt(
    packaged_e2e: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Require the complete packaged journey and its independent receipts."""

    scenario = packaged_e2e.get("scenario")
    scenario = scenario if isinstance(scenario, Mapping) else {}
    metrics = scenario.get("metrics")
    metrics = metrics if isinstance(metrics, Mapping) else {}
    scenario_status = _source_status(scenario.get("status"))
    raw_evidence = scenario.get("evidence")
    scenario_evidence = (
        [str(item) for item in raw_evidence]
        if isinstance(raw_evidence, list)
        else ["Packaged E2E scenario/evidence is missing."]
    )
    checks = [
        _check(
            "packaged_e2e.full_journey",
            label="Full packaged-app UI/worker/restart journey",
            status=scenario_status,
            required=True,
            source_status=(
                str(scenario.get("status"))
                if scenario.get("status") is not None
                else None
            ),
            evidence=scenario_evidence,
            metrics=metrics,
        )
    ]
    true_contracts = {
        "artifact_verified": "artifact_verified",
        "artifact_integrity_verified": "artifact_integrity_verified",
        "process_provenance_verified": "process_provenance_verified",
        "ui_interaction_observed": "ui_interaction_observed",
        "library_description_visibility_verified": "library_description_visibility_verified",
        "final_output_probed": "final_output_probed",
        "restart_history_persistence_verified": "restart_history_persistence_verified",
        "clean_exit": "clean_exit",
    }
    zero_contracts = {
        "staging_residue_zero": "staging_residue_count",
        "zombie_signals_zero": "peak_zombie_processes",
    }
    false_contracts = {
        "unexpected_exit_absent": "unexpected_process_exit",
        "forced_termination_absent": "harness_forced_termination",
    }
    missing: list[str] = []
    failures: list[str] = []
    conditions: dict[str, bool] = {}
    for label, key in true_contracts.items():
        value = metrics.get(key)
        conditions[label] = value is True
        if key not in metrics:
            missing.append(key)
        elif value is not True:
            failures.append(key)
    for label, key in zero_contracts.items():
        value = metrics.get(key)
        conditions[label] = value == 0
        if key not in metrics:
            missing.append(key)
        elif value != 0:
            failures.append(key)
    for label, key in false_contracts.items():
        value = metrics.get(key)
        conditions[label] = value is False
        if key not in metrics:
            missing.append(key)
        elif value is not False:
            failures.append(key)
    stage_receipts = metrics.get("pipeline_stage_receipts")
    stage_names = (
        "yt_dlp_or_download",
        "ffmpeg_transcode",
        "ffprobe_validation",
        "atomic_commit",
    )
    conditions["all_pipeline_stages_receipted"] = isinstance(
        stage_receipts, Mapping
    ) and all(stage_receipts.get(name) is True for name in stage_names)
    if not isinstance(stage_receipts, Mapping):
        missing.append("pipeline_stage_receipts")
    else:
        missing.extend(
            f"pipeline_stage_receipts.{name}"
            for name in stage_names
            if name not in stage_receipts
        )
        failures.extend(
            f"pipeline_stage_receipts.{name}"
            for name in stage_names
            if name in stage_receipts and stage_receipts.get(name) is not True
        )
    artifact_integrity = packaged_e2e.get("artifact_integrity")
    process_provenance = packaged_e2e.get("process_provenance")
    library_description_visibility = packaged_e2e.get("library_description_visibility")
    conditions["top_level_artifact_integrity_verified"] = (
        isinstance(artifact_integrity, Mapping)
        and artifact_integrity.get("verified") is True
    )
    conditions["top_level_process_provenance_verified"] = (
        isinstance(process_provenance, Mapping)
        and process_provenance.get("verified") is True
    )
    conditions["top_level_library_description_visibility_verified"] = (
        isinstance(library_description_visibility, Mapping)
        and library_description_visibility.get("verified") is True
    )
    if (
        not isinstance(artifact_integrity, Mapping)
        or "verified" not in artifact_integrity
    ):
        missing.append("artifact_integrity.verified")
    elif artifact_integrity.get("verified") is not True:
        failures.append("artifact_integrity.verified")
    if (
        not isinstance(process_provenance, Mapping)
        or "verified" not in process_provenance
    ):
        missing.append("process_provenance.verified")
    elif process_provenance.get("verified") is not True:
        failures.append("process_provenance.verified")
    if (
        not isinstance(library_description_visibility, Mapping)
        or "verified" not in library_description_visibility
    ):
        missing.append("library_description_visibility.verified")
    elif library_description_visibility.get("verified") is not True:
        failures.append("library_description_visibility.verified")
    if failures:
        receipt_status: GateStatus = "failed"
    elif missing:
        receipt_status = "unproven"
    else:
        receipt_status = "passed"
    checks.append(
        _check(
            "packaged_e2e.independent_receipts",
            label="Packaged artifact, process, pipeline, output, and lifecycle receipts",
            status=receipt_status,
            required=True,
            evidence=[
                *[f"{name}={value}" for name, value in conditions.items()],
                f"missing={sorted(set(missing))}",
                f"failures={sorted(set(failures))}",
            ],
            metrics={
                **conditions,
                "missing": sorted(set(missing)),
                "failures": sorted(set(failures)),
            },
        )
    )
    return checks


def evaluate_candidate_binding(
    candidate: Mapping[str, Any], packaged_e2e: Mapping[str, Any]
) -> list[dict[str, Any]]:
    binding = packaged_e2e.get("candidate_binding")
    archive = candidate.get("immutable_archive")
    artifact = candidate.get("artifact")
    binding = binding if isinstance(binding, Mapping) else {}
    archive = archive if isinstance(archive, Mapping) else {}
    artifact = artifact if isinstance(artifact, Mapping) else {}
    bundle_tree = artifact.get("bundle_tree")
    bundle_tree = bundle_tree if isinstance(bundle_tree, Mapping) else {}
    expected = {
        "candidate_id": candidate.get("candidate_id"),
        "archive_sha256": archive.get("sha256"),
        "bundle_tree_sha256": bundle_tree.get("sha256"),
    }
    comparisons = {
        key: bool(value) and binding.get(key) == value
        for key, value in expected.items()
    }
    fields_present = (
        all(
            expected.get(key) not in {None, ""} and binding.get(key) not in {None, ""}
            for key in expected
        )
        and "verified" in binding
    )
    binding_verified = binding.get("verified") is True
    if not fields_present:
        binding_status: GateStatus = "unproven"
    elif binding_verified and all(comparisons.values()):
        binding_status = "passed"
    else:
        binding_status = "failed"
    return [
        _check(
            "packaged_e2e.candidate_binding",
            label="Packaged E2E exact-candidate binding",
            status=binding_status,
            required=True,
            evidence=[
                f"binding.verified={binding.get('verified')!r}",
                *[
                    f"{key}: expected={expected[key]!r} observed={binding.get(key)!r} match={match}"
                    for key, match in comparisons.items()
                ],
            ],
        )
    ]


def _candidate_source_checks(
    candidate: Mapping[str, Any], results: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    source = candidate.get("source")
    source = source if isinstance(source, Mapping) else {}
    expected_commit = source.get("commit")
    checks: list[dict[str, Any]] = []
    for name, result in results.items():
        repository = result.get("repository")
        repository = repository if isinstance(repository, Mapping) else {}
        observed = repository.get("commit")
        if not expected_commit or not observed:
            status: GateStatus = "unproven"
        else:
            status = "passed" if observed == expected_commit else "failed"
        checks.append(
            _check(
                f"source_commit.{name}",
                label=f"{name.upper()} source commit matches candidate",
                status=status,
                required=True,
                evidence=[
                    f"candidate={expected_commit!r}",
                    f"{name}={observed!r}",
                ],
            )
        )
    return checks


def gate_outcome(checks: Sequence[Mapping[str, Any]]) -> GateStatus:
    required = [item for item in checks if item.get("required") is True]
    statuses = [item.get("status") for item in required]
    if required and all(status == "passed" for status in statuses):
        return "passed"
    if "failed" in statuses:
        return "failed"
    if "unproven" in statuses:
        return "unproven"
    if "skipped" in statuses:
        return "skipped"
    return "unproven"


def _test_count(result: Mapping[str, Any], command_name: str) -> int | None:
    static = _scenario_index(result).get("unit_static.repository_suite")
    metrics = static.get("metrics") if isinstance(static, Mapping) else None
    commands = metrics.get("commands") if isinstance(metrics, Mapping) else None
    command = commands.get(command_name) if isinstance(commands, Mapping) else None
    stdout = command.get("stdout") if isinstance(command, Mapping) else None
    if not isinstance(stdout, str):
        return None
    matches = re.findall(r"(?<!\d)(\d+) passed(?:[ ,]|$)", stdout)
    return int(matches[-1]) if matches else None


def _find_scenario(
    result: Mapping[str, Any], scenario_id: str
) -> Mapping[str, Any] | None:
    return _scenario_index(result).get(scenario_id)


def build_release_receipt(
    *,
    candidate: Mapping[str, Any],
    fast_result: Mapping[str, Any],
    normal_result: Mapping[str, Any],
    deep_result: Mapping[str, Any],
    packaged_e2e: Mapping[str, Any],
    commands_used: Sequence[Sequence[str]],
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a fail-closed release receipt from already-produced evidence."""

    checks = [
        *evaluate_candidate_receipt(candidate),
        *evaluate_fast_result(fast_result),
        *evaluate_engineering_result(normal_result, profile="normal"),
        *evaluate_engineering_result(deep_result, profile="deep"),
        *evaluate_packaged_e2e_receipt(packaged_e2e),
        *evaluate_candidate_binding(candidate, packaged_e2e),
        *_candidate_source_checks(
            candidate,
            {"fast": fast_result, "normal": normal_result, "deep": deep_result},
        ),
    ]
    outcome = gate_outcome(checks)
    statuses = Counter(str(item.get("status")) for item in checks)
    required_statuses = Counter(
        str(item.get("status")) for item in checks if item.get("required") is True
    )
    candidate_source = candidate.get("source")
    candidate_source = candidate_source if isinstance(candidate_source, Mapping) else {}
    artifact = candidate.get("artifact")
    artifact = artifact if isinstance(artifact, Mapping) else {}
    archive = candidate.get("immutable_archive")
    archive = archive if isinstance(archive, Mapping) else {}
    deep_soak = _find_scenario(deep_result, "lifecycle.repeated_job_soak") or {}
    soak_metrics = deep_soak.get("metrics")
    soak_metrics = soak_metrics if isinstance(soak_metrics, Mapping) else {}
    normal_summary = normal_result.get("summary")
    deep_summary = deep_result.get("summary")
    normal_summary = normal_summary if isinstance(normal_summary, Mapping) else {}
    deep_summary = deep_summary if isinstance(deep_summary, Mapping) else {}
    findings: list[Mapping[str, Any]] = []
    for result in (normal_result, deep_result, packaged_e2e):
        raw_findings = result.get("findings")
        if isinstance(raw_findings, list):
            findings.extend(item for item in raw_findings if isinstance(item, Mapping))
    known_debt = [
        item
        for item in checks
        if item.get("required") is False
        and item.get("status") != "passed"
        and ".debt." in str(item.get("id"))
    ]
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": RELEASE_RECEIPT_SCHEMA_VERSION,
        "receipt_type": "vodforge_release_gate",
        "generated_at": timestamp,
        "status": outcome,
        "release_eligible": outcome == "passed",
        "candidate": {
            "candidate_id": candidate.get("candidate_id"),
            "version": candidate.get("candidate_version"),
            "source_commit": candidate_source.get("commit"),
            "source_branch": candidate_source.get("branch"),
            "source_clean": candidate_source.get("clean"),
            "archive_path": archive.get("path"),
            "archive_sha256": archive.get("sha256"),
            "archive_size_bytes": archive.get("size_bytes"),
            "artifact_policy": candidate.get("artifact_policy"),
            "signature_state": artifact.get("signature_state"),
            "notarization_state": artifact.get("notarization_state"),
            "gatekeeper_state": artifact.get("gatekeeper_state"),
            "release_identity_verified": artifact.get("release_identity_verified"),
        },
        "summary": {
            "checks": len(checks),
            "status_counts": dict(statuses),
            "required_status_counts": dict(required_statuses),
            "blocking_check_ids": [
                item["id"]
                for item in checks
                if item.get("required") is True and item.get("status") != "passed"
            ],
            "known_debt_count": len(known_debt),
        },
        "checks": checks,
        "test_counts": {
            "repository": _test_count(fast_result, "pytest"),
            "harness_self_tests": _test_count(fast_result, "pytest_harness"),
            "normal_scenarios": {
                "passed": normal_summary.get("passed"),
                "failed": normal_summary.get("failed"),
                "errors": normal_summary.get("errors"),
                "skipped": normal_summary.get("skipped"),
            },
            "deep_scenarios": {
                "passed": deep_summary.get("passed"),
                "failed": deep_summary.get("failed"),
                "errors": deep_summary.get("errors"),
                "skipped": deep_summary.get("skipped"),
            },
        },
        "packaged_e2e": {
            "scenario": packaged_e2e.get("scenario"),
            "candidate_binding": packaged_e2e.get("candidate_binding"),
            "artifact_integrity": packaged_e2e.get("artifact_integrity"),
            "process_provenance": packaged_e2e.get("process_provenance"),
        },
        "security_findings": [
            item for item in findings if item.get("classification") == "security defect"
        ],
        "lifecycle": {
            "jobs_attempted": soak_metrics.get("jobs_attempted"),
            "jobs_completed": soak_metrics.get("jobs_completed"),
            "retained_worker_object_deltas": soak_metrics.get(
                "worker_object_count_deltas"
            ),
            "fd_delta": soak_metrics.get("fd_delta"),
            "orphaned_child_processes": soak_metrics.get("orphaned_child_processes"),
            "peak_zombie_processes": soak_metrics.get("peak_zombie_processes"),
            "staging_residue_count": soak_metrics.get("staging_residue_count"),
            "rss_delta_bytes": soak_metrics.get("rss_delta_bytes"),
            "rss_growth_description": soak_metrics.get("rss_growth_description"),
        },
        "performance_observations": {
            "normal": normal_result.get("aggregate_metrics"),
            "deep": deep_result.get("aggregate_metrics"),
            "comparison_required": True,
        },
        "known_debt": known_debt,
        "commands_used": [list(command) for command in commands_used],
        "machine": deep_result.get("machine"),
        "environment": {
            "fast_tools": fast_result.get("tool_versions"),
            "normal_tools": normal_result.get("tool_versions"),
            "deep_tools": deep_result.get("tool_versions"),
        },
    }


def markdown_release_receipt(receipt: Mapping[str, Any]) -> str:
    candidate = receipt.get("candidate")
    candidate = candidate if isinstance(candidate, Mapping) else {}
    summary = receipt.get("summary")
    summary = summary if isinstance(summary, Mapping) else {}
    lines = [
        "# VODForge release-gate receipt",
        "",
        f"- Status: **{str(receipt.get('status', 'unproven')).upper()}**",
        f"- Eligible to publish this exact hash: **{'yes' if receipt.get('release_eligible') is True else 'no'}**",
        f"- Generated: {receipt.get('generated_at')}",
        f"- Source: `{candidate.get('source_commit')}` on `{candidate.get('source_branch')}`",
        f"- Candidate: `{candidate.get('candidate_id')}` version `{candidate.get('version')}`",
        f"- Immutable archive SHA-256: `{candidate.get('archive_sha256')}`",
        f"- Trust: signature `{candidate.get('signature_state')}`, notarization `{candidate.get('notarization_state')}`, Gatekeeper `{candidate.get('gatekeeper_state')}`",
        "",
        "A required failed, skipped, or unproven check blocks publication. Nonblocking debt remains visible below.",
        "",
        "## Gate checks",
        "",
        "| Status | Required | Check | Evidence |",
        "|---|---:|---|---|",
    ]
    checks = receipt.get("checks")
    for item in checks if isinstance(checks, list) else []:
        if not isinstance(item, Mapping):
            continue
        evidence = item.get("evidence")
        evidence_text = (
            "; ".join(str(value).replace("|", "\\|") for value in evidence[:2])
            if isinstance(evidence, list)
            else ""
        )
        lines.append(
            f"| {str(item.get('status')).upper()} | {'yes' if item.get('required') is True else 'no'} | `{item.get('id')}` | {evidence_text} |"
        )
    lines.extend(
        [
            "",
            "## Test and lifecycle evidence",
            "",
            f"- Test counts: `{json.dumps(receipt.get('test_counts'), sort_keys=True)}`",
            f"- 100-job lifecycle: `{json.dumps(receipt.get('lifecycle'), sort_keys=True)}`",
            f"- Security findings classified as defects: {len(receipt.get('security_findings') or [])}",
            "",
            "## Known debt",
            "",
        ]
    )
    debt = receipt.get("known_debt")
    if isinstance(debt, list) and debt:
        for item in debt:
            if isinstance(item, Mapping):
                lines.append(
                    f"- **{str(item.get('status')).upper()}** `{item.get('id')}` — {item.get('label')}"
                )
    else:
        lines.append(
            "- No nonblocking debt was recorded. This is not a zero-debt claim."
        )
    lines.extend(["", "## Exact commands", ""])
    commands = receipt.get("commands_used")
    for command in commands if isinstance(commands, list) else []:
        if isinstance(command, list):
            lines.append(f"- `{' '.join(str(part) for part in command)}`")
    blockers = summary.get("blocking_check_ids")
    lines.extend(["", "## Publication decision", ""])
    if receipt.get("release_eligible") is True:
        lines.append(
            "This exact immutable archive hash is eligible to publish. Rebuilding produces a different candidate and invalidates this receipt."
        )
    else:
        rendered = ", ".join(f"`{item}`" for item in (blockers or []))
        lines.append(
            f"Publication is blocked by: {rendered or '`unproven gate state`'}."
        )
    return "\n".join(lines) + "\n"


def write_release_receipt(
    output_dir: Path, receipt: Mapping[str, Any]
) -> dict[str, Path]:
    validate_receipt_schema(
        receipt,
        Path(__file__).resolve().parents[1] / "schemas" / "release-receipt.schema.json",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "release-receipt.json"
    markdown_path = output_dir / "release-receipt.md"
    json_dump(json_path, dict(receipt))
    markdown_path.write_text(markdown_release_receipt(receipt), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}
