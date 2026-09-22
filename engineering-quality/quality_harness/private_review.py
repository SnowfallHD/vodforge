"""Private installation uses the same behavioral blockers as release review."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

import psutil

from .candidate_artifact import load_and_verify_candidate, materialize_candidate_for_e2e
from .release_gate import (
    evaluate_candidate_binding,
    evaluate_engineering_result,
    evaluate_packaged_e2e_receipt,
)
from .source_identity import validate_manifest
from .util import sha256_file


def candidate_identity(candidate: dict[str, Any]) -> tuple[Any, ...]:
    """Content identity, including dirty-tree distinction; not HEAD alone."""
    return (
        candidate.get("candidate_id"),
        candidate.get("source", {}).get("commit"),
        candidate.get("source", {}).get("manifest_sha256"),
        candidate.get("immutable_archive", {}).get("sha256"),
        candidate.get("artifact", {}).get("bundle_tree", {}).get("sha256"),
    )


def review_failures(
    candidate: dict[str, Any],
    normal: dict[str, Any],
    packaged: dict[str, Any],
    negatives: dict[str, Any],
    ledger: dict[str, Any],
) -> list[str]:
    checks = [
        *evaluate_engineering_result(normal, profile="normal"),
        *evaluate_packaged_e2e_receipt(packaged),
        *evaluate_candidate_binding(candidate, packaged),
    ]
    failures = [
        str(check["id"]) + ":" + str(check["status"])
        for check in checks
        if check.get("required") and check.get("status") != "passed"
    ]
    source = candidate.get("source", {}).get("commit")
    if not source or normal.get("repository", {}).get("commit") != source:
        failures.append("private.source_binding")
    if packaged.get("candidate_binding", {}).get("source_commit") != source:
        failures.append("private.packaged_source_binding")
    if negatives.get("source_commit") != source:
        failures.append("private.negative_control_source_binding")
    manifest = candidate.get("source", {}).get("manifest_sha256")
    if not isinstance(manifest, str) or not re.fullmatch("[0-9a-f]{64}", manifest):
        failures.append("private.source_manifest_missing")
    else:
        for label, observed in (
            ("normal", normal.get("repository", {}).get("source_manifest_sha256")),
            (
                "packaged",
                packaged.get("candidate_binding", {}).get("source_manifest_sha256"),
            ),
            ("negative", negatives.get("fixed_source_manifest_sha256")),
        ):
            if observed != manifest:
                failures.append("private." + label + "_source_manifest_binding")
    for label, payload in (
        ("candidate", candidate.get("source", {}).get("manifest")),
        ("normal", normal.get("repository", {}).get("source_manifest")),
    ):
        if not validate_manifest(payload, manifest):
            failures.append("private." + label + "_source_manifest_invalid")
    if normal.get("repository", {}).get("source_manifest_unchanged") is not True:
        failures.append("private.source_changed_during_checks")
    controls = negatives.get("controls")
    if not isinstance(controls, list) or not controls:
        failures.append("private.negative_controls_missing")
    else:
        for control in controls:
            if (
                not isinstance(control, dict)
                or not control.get("requirement_id")
                or control.get("status") != "detected"
                or control.get("failure_kind") != "behavioral_assertion"
                or not control.get("evidence_sha256")
            ):
                failures.append("private.negative_control_unproven")
    defects = ledger.get("defects")
    if (
        ledger.get("schema_version") != 1
        or not isinstance(defects, list)
        or not defects
    ):
        failures.append("private.defect_ledger_missing")
    else:
        required = {
            item.get("requirement_id")
            for item in controls or []
            if isinstance(item, dict)
        }
        for defect in defects:
            if (
                not isinstance(defect, dict)
                or defect.get("status") != "verified_closed"
            ):
                failures.append(
                    "private.open_user_defect:"
                    + str(defect.get("id") if isinstance(defect, dict) else "invalid")
                )
            elif defect.get("id") not in required:
                failures.append(
                    "private.defect_negative_control_missing:" + str(defect.get("id"))
                )
            elif defect.get("verified_source_manifest_sha256") != manifest:
                failures.append(
                    "private.defect_closure_manifest_binding:" + str(defect.get("id"))
                )
            elif defect.get("verified_source_commit") != source:
                failures.append(
                    "private.defect_closure_source_binding:" + str(defect.get("id"))
                )
    return failures


def install_private_review(args: Any, *, harness_root: Path) -> int:
    """All gates run before extraction or moving the existing installation.

    An explicit known-defect ledger is owned by the harness checkout, not supplied
    by the candidate. This command does not launch the app or touch user data.
    """
    receipt_sha = sha256_file(args.candidate)
    candidate = load_and_verify_candidate(args.candidate)
    expected_identity = candidate_identity(candidate)
    normal = json.loads(args.normal_result.read_text())
    packaged = json.loads(args.e2e_result.read_text())
    negatives = json.loads(args.negative_controls.read_text())
    ledger = json.loads(
        (harness_root / "acceptance/user-reported-defects.json").read_text()
    )
    failures = review_failures(candidate, normal, packaged, negatives, ledger)
    if failures:
        raise RuntimeError("Private installation blocked: " + "; ".join(failures))
    # Evidence references must be readable and match their content binding.
    for control in negatives["controls"]:
        evidence = Path(control["evidence_path"])
        if (
            not evidence.is_file()
            or sha256_file(evidence) != control["evidence_sha256"]
        ):
            raise RuntimeError(
                "Private installation blocked: negative-control evidence mismatch"
            )
        from .negative_controls import evaluate_native_channels

        bad_manifest = control.get("known_bad_source_manifest_sha256")
        if (
            not isinstance(bad_manifest, str)
            or not re.fullmatch("[0-9a-f]{64}", bad_manifest)
            or bad_manifest == candidate.get("source", {}).get("manifest_sha256")
        ):
            raise RuntimeError(
                "Private installation blocked: known-bad source identity missing"
            )
        observed = json.loads(evidence.read_text())
        if (
            control.get("evaluator") != "native_channels_v1"
            or observed.get("source_manifest_sha256") != bad_manifest
            or evaluate_native_channels(observed, control["requirement_id"])
            != "detected"
        ):
            raise RuntimeError(
                "Private installation blocked: negative control did not prove detection"
            )
    target = args.target.absolute()
    if target.suffix != ".app" or target.is_symlink() or not target.is_dir():
        raise RuntimeError("Private target must be an existing real .app directory")
    if target.parent != target.parent.resolve():
        raise RuntimeError("Private target parent must not traverse symlinks")
    for process in psutil.process_iter(["exe"]):
        executable = process.info.get("exe")
        if executable and Path(executable).is_relative_to(target):
            raise RuntimeError("Close the installed app before private replacement")
    token = uuid4().hex
    stage = target.parent / (".private-review-" + token)
    backup = target.with_name(target.stem + ".previous-" + token + ".app")
    artifact, binding = materialize_candidate_for_e2e(args.candidate, stage)
    # Verify the exact preflight identity, not merely another valid candidate.
    refreshed = load_and_verify_candidate(args.candidate)
    expected_binding = {
        "candidate_id": expected_identity[0],
        "source_commit": expected_identity[1],
        "source_manifest_sha256": expected_identity[2],
        "archive_sha256": expected_identity[3],
        "bundle_tree_sha256": expected_identity[4],
        "receipt_sha256": receipt_sha,
    }
    if (
        candidate_identity(refreshed) != expected_identity
        or sha256_file(args.candidate) != receipt_sha
        or any(binding.get(key) != value for key, value in expected_binding.items())
    ):
        raise RuntimeError(
            "Private installation blocked: candidate changed after preflight"
        )
    os.replace(target, backup)
    try:
        os.replace(artifact, target)
    except OSError:
        os.replace(backup, target)
        raise
    (stage / "install-receipt.json").write_text(
        json.dumps(
            {
                "installed": str(target),
                "rollback": str(backup),
                "candidate_binding": binding,
                "scope": "private review; user data untouched; no public release eligibility",
            },
            indent=2,
        )
    )
    return 0
