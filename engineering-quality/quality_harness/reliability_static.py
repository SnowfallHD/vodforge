from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .security import _bind_component
from .transaction_observation import file_observation


def activity_log_failure_receipt_probe(
    case_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Prove optional durable Activity failures are visible, bounded, and recoverable."""
    from yt_downloader import app

    case_dir.mkdir(parents=True, exist_ok=True)
    first_bad_target = case_dir / "first-private-canary"
    second_bad_target = case_dir / "second-private-canary"
    first_bad_target.mkdir()
    second_bad_target.mkdir()
    recovered_target = case_dir / "recovered-activity.log"
    canary = "ACTIVITY-SECRET-CANARY"
    receipts: list[str] = []
    started = time.monotonic()
    trace = []

    def observe(phase):
        trace.append(
            {
                "phase": phase,
                "elapsed_seconds": time.monotonic() - started,
                "receipts": list(receipts),
                "handle_none": app._ACTIVITY_LOG_HANDLE is None,
                "handle_path_none": app._ACTIVITY_LOG_HANDLE_PATH is None,
                "failure_reported": app._ACTIVITY_LOG_FAILURE_REPORTED,
                "first_bad": first_bad_target.is_dir(),
                "second_bad": second_bad_target.is_dir(),
                "recovered_file": file_observation(recovered_target),
                "recovered_text": recovered_target.read_text()
                if recovered_target.is_file()
                else None,
            }
        )

    original_write_diagnostic = app.write_diagnostic
    original_failure_reported = app._ACTIVITY_LOG_FAILURE_REPORTED
    try:
        with app._ACTIVITY_LOG_LOCK:
            try:
                app._close_activity_log_locked()
            except (OSError, ValueError):
                pass
        app.write_diagnostic = receipts.append
        app._ACTIVITY_LOG_FAILURE_REPORTED = False
        observe("before_failed_sink")

        app.prepare_activity_log(first_bad_target)
        app.append_activity_log(
            f"https://user:pass@example.invalid/media?token={canary}#private",
            first_bad_target,
        )
        observe("first_failure_observed")
        receipts_during_first_failure = len(receipts)
        first_failure_detached = (
            app._ACTIVITY_LOG_HANDLE is None and app._ACTIVITY_LOG_HANDLE_PATH is None
        )

        app.append_activity_log("durable activity recovered", recovered_target)
        with app._ACTIVITY_LOG_LOCK:
            app._close_activity_log_locked()
        observe("durable_write_recovered")
        recovered = (
            recovered_target.read_text(encoding="utf-8")
            == "durable activity recovered\n"
        )

        app.append_activity_log("second failed activity line", second_bad_target)
        observe("new_failure_observed")
        receipts_after_new_failure = len(receipts)
        final_failure_detached = (
            app._ACTIVITY_LOG_HANDLE is None and app._ACTIVITY_LOG_HANDLE_PATH is None
        )
    finally:
        with app._ACTIVITY_LOG_LOCK:
            try:
                app._close_activity_log_locked()
            except (OSError, ValueError):
                pass
        app.write_diagnostic = original_write_diagnostic
        app._ACTIVITY_LOG_FAILURE_REPORTED = original_failure_reported

    receipts_secret_free = all(
        canary not in receipt
        and str(first_bad_target) not in receipt
        and str(second_bad_target) not in receipt
        for receipt in receipts
    )
    receipt_text_is_stable = all(
        receipt == app.ACTIVITY_LOG_FAILURE_DIAGNOSTIC for receipt in receipts
    )
    passed = bool(
        receipts_during_first_failure == 1
        and first_failure_detached
        and recovered
        and receipts_after_new_failure == 2
        and final_failure_detached
        and receipts_secret_free
        and receipt_text_is_stable
    )
    evidence = [
        f"Receipts during one uninterrupted failure episode: {receipts_during_first_failure}",
        f"Poisoned handle detached after first failure: {first_failure_detached}",
        f"A later writable target recovered durable activity: {recovered}",
        f"Receipts after recovery and a new failure episode: {receipts_after_new_failure}",
        f"Final failed sink detached: {final_failure_detached}",
        f"Receipts omitted paths and URL secret canary: {receipts_secret_free}",
    ]
    scenario = {
        "id": "unit_static.activity_log_failure_receipt",
        "evidence_tier": "unit_static",
        "category": "reliability",
        "status": "passed" if passed else "failed",
        "duration_seconds": 0.0,
        "metrics": {
            "first_failure_receipt_count": receipts_during_first_failure,
            "recovered": recovered,
            "new_failure_total_receipt_count": receipts_after_new_failure,
            "secret_free_receipts": receipts_secret_free,
            "failed_handle_detached": first_failure_detached and final_failure_detached,
        },
        "evidence": evidence,
        "artifacts": [str(recovered_target)] if recovered_target.exists() else [],
        "error": None,
    }
    findings = []
    if not passed:
        findings.append(
            {
                "id": "REL-ACTIVITY-DURABILITY-001",
                "title": "Persistent Activity failures are silent or retain unusable state",
                "classification": "reliability defect",
                "severity": "medium",
                "area": "yt_downloader/app.py persistent Activity sink",
                "reproduction": [
                    "Run ./engineering-quality/run normal --scenario unit_static.activity_log_failure_receipt.",
                    "Inspect receipt counts, recovery, and cached-handle evidence.",
                ],
                "evidence": evidence,
                "suggested_fix": (
                    "Keep Activity persistence nonfatal, detach failed cached handles, emit one "
                    "generic secret-free diagnostic per failure episode, and reset suppression "
                    "after a successful write."
                ),
                "scenario_id": scenario["id"],
            }
        )
    _bind_component(
        scenario,
        case_dir,
        {
            "scenario_id": scenario["id"],
            "contract": "optional-activity-failure-episodes-v1",
            "scope": "controlled directory refusal and durable log recovery; no native Activity UI",
            "trace": trace,
        },
    )
    return scenario, findings
