"""Failure and recovery oracles over actual bounded worker observations."""

from __future__ import annotations

import math
from collections import Counter
from itertools import pairwise
from typing import Any
from urllib.parse import urlsplit


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _dispatch(
    trace: list[dict[str, Any]], start: float, end: float, check: Any
) -> float | None:
    rows = [row for row in trace if row.get("phase") == "worker_dispatched"]
    value = rows[0].get("elapsed_seconds") if len(rows) == 1 else None
    check(
        "during",
        "production_dispatch",
        _number(value),
        _number(value) and start <= value < end,
        "Actual production dispatch lies within the same-run worker interval",
    )
    return value if _number(value) else None


def _fixture(
    raw: dict[str, Any],
    job: dict[str, Any],
    trace: list[dict[str, Any]],
    start: float,
    end: float,
    route: str,
    check: Any,
) -> list[dict[str, Any]] | None:
    origin = urlsplit(job.get("url", ""))
    before = raw.get("before_worker") or {}
    initial, after = before.get("fixture_state"), raw.get("fixture_state_after")
    bound = isinstance(initial, dict) and isinstance(initial.get("origin"), str)
    check(
        "before",
        "private_fixture_authority",
        bound and bool(job.get("url")),
        bound
        and origin.scheme == "http"
        and origin.hostname == "127.0.0.1"
        and origin.port is not None
        and origin.path == route
        and not origin.query
        and initial["origin"] == f"{origin.scheme}://{origin.netloc}",
        "Independent fixture listening origin matches the enrolled private request",
    )
    baseline_present = (
        isinstance(initial, dict)
        and isinstance(initial.get("requests"), dict)
        and isinstance(initial.get("responses"), list)
        and _number(before.get("fixture_elapsed_seconds"))
    )
    check(
        "before",
        "fixture_before_dispatch",
        baseline_present,
        baseline_present
        and before["fixture_elapsed_seconds"] <= start
        and initial["requests"].get(route, 0) == 0,
        "Target source has not been requested when the independent baseline is captured",
    )
    dispatched = _dispatch(trace, start, end, check)
    responses = raw.get("fixture_response_trace")
    typed = isinstance(responses, list) and all(
        isinstance(row, dict)
        and all(key in row for key in ("route", "status", "elapsed_seconds"))
        for row in responses
    )
    valid = (
        typed
        and dispatched is not None
        and bool(responses)
        and all(
            _number(row["elapsed_seconds"])
            and dispatched <= row["elapsed_seconds"] < end
            and isinstance(row["route"], str)
            and type(row["status"]) is int
            for row in responses
        )
        and all(
            a["elapsed_seconds"] <= b["elapsed_seconds"] for a, b in pairwise(responses)
        )
    )
    check(
        "during",
        "fixture_responses_in_owned_interval",
        typed and dispatched is not None,
        valid,
        "Actual fixture responses occur only during this dispatched worker",
    )
    after_present = (
        baseline_present
        and isinstance(after, dict)
        and isinstance(after.get("responses"), list)
        and isinstance(after.get("statuses"), dict)
        and isinstance(initial.get("statuses"), dict)
        and isinstance(after.get("requests"), dict)
        and _number(raw.get("fixture_after_elapsed_seconds"))
        and bound
        and typed
        and dispatched is not None
    )
    if after_present:
        suffix = after["responses"][len(initial["responses"]) :]
        statuses = Counter(initial["statuses"])
        statuses.update(str(row["status"]) for row in responses)
        requests = Counter(initial["requests"])
        requests.update(row["route"] for row in responses)
        agree = (
            after.get("origin") == initial["origin"]
            and after["responses"][: len(initial["responses"])] == initial["responses"]
            and len(suffix) == len(responses)
            and all(
                a.get("route") == b["route"] and a.get("status") == b["status"]
                for a, b in zip(suffix, responses, strict=True)
            )
            and after["statuses"] == dict(statuses)
            and after["requests"] == dict(requests)
            and after.get("total_requests") == sum(requests.values())
            and raw["fixture_after_elapsed_seconds"] >= end
        )
    else:
        agree = False
    check(
        "after",
        "fixture_response_delta_agrees",
        after_present,
        valid and agree,
        "Post-worker inventory equals the exact response delta from the pre-worker snapshot",
    )
    return responses if typed else None


def evaluate_recovery(
    raw: dict[str, Any],
    job: dict[str, Any],
    trace: list[dict[str, Any]],
    start: float,
    end: float,
    case: str,
    check: Any,
) -> None:
    retry = case == "reliability-retry-503"
    route = "/fault/retry/page" if retry else "/fault/interrupt/page"
    responses = _fixture(raw, job, trace, start, end, route, check)
    initial = (raw.get("before_worker") or {}).get("fixture_state")
    after = raw.get("fixture_state_after")
    events, progress = raw.get("events"), raw.get("progress_trace")
    if responses is None:
        return
    if retry:
        pages = [row for row in responses if row["route"] == route]
        present = (
            isinstance(initial, dict)
            and isinstance(after, dict)
            and "retry_failures_remaining" in initial
            and "retry_failures_remaining" in after
        )
        valid = (
            present
            and initial["retry_failures_remaining"] == 2
            and after["retry_failures_remaining"] == 0
            and [row["status"] for row in pages] == [503, 503, 200]
        )
        check(
            "during",
            "two_faults_then_recovery",
            present,
            valid,
            "Two real HTTP503 responses precede the successful source response",
        )
        logs = (
            [
                row
                for row in events
                if row.get("kind") == "job_log"
                and isinstance(row.get("payload"), dict)
                and "source analysis transient network failure"
                in str(row["payload"].get("line", ""))
            ]
            if isinstance(events, list)
            else []
        )
        typed = isinstance(events, list) and all(
            isinstance(row["payload"].get("job"), dict)
            and _number(row.get("elapsed_seconds"))
            for row in logs
        )
        log_valid = (
            typed
            and valid
            and len(logs) == 2
            and all(
                pages[index]["elapsed_seconds"]
                <= row["elapsed_seconds"]
                < pages[index + 1]["elapsed_seconds"]
                and all(
                    row["payload"]["job"].get(key) == job.get(key)
                    for key in ("run_id", "url", "output_type", "output_dir")
                )
                and f"attempt {index + 1}/6; retrying attempt {index + 2}/6"
                in row["payload"]["line"]
                and "HTTP Error 503" in row["payload"]["line"]
                for index, row in enumerate(logs)
            )
        )
        check(
            "during",
            "bounded_same_run_retry_feedback",
            typed and present,
            log_valid,
            "Actual same-run retry feedback follows each refusal and precedes the next request",
        )
        transfers = (
            [
                row
                for row in progress
                if _number(row.get("downloaded_bytes")) and row["downloaded_bytes"] > 0
            ]
            if isinstance(progress, list)
            else []
        )
        check(
            "during",
            "recovery_before_media_transfer",
            isinstance(progress, list) and present,
            valid
            and bool(transfers)
            and pages[-1]["elapsed_seconds"]
            < min(row["elapsed_seconds"] for row in transfers),
            "Media transfer starts only after source analysis recovers",
        )
    else:
        interruptions = raw.get("fixture_interruption_trace")
        typed = isinstance(interruptions, list) and all(
            isinstance(row, dict)
            and all(
                key in row
                for key in (
                    "route",
                    "elapsed_seconds",
                    "sent_bytes",
                    "advertised_bytes",
                )
            )
            for row in interruptions
        )
        valid = (
            typed
            and len(interruptions) == 1
            and isinstance(initial, dict)
            and isinstance(after, dict)
        )
        if valid:
            interruption = interruptions[0]
            valid = (
                initial.get("interruptions_remaining") == 1
                and after.get("interruptions_remaining") == 0
                and after.get("interruptions_injected")
                == initial.get("interruptions_injected", -1) + 1
                and _number(interruption["elapsed_seconds"])
                and start < interruption["elapsed_seconds"] < end
                and _number(interruption["sent_bytes"])
                and _number(interruption["advertised_bytes"])
                and 0 < interruption["sent_bytes"] < interruption["advertised_bytes"]
                and interruption["route"].startswith("/fault/interrupt/")
                and interruption["route"].endswith(".ts")
            )
        check(
            "during",
            "actual_partial_response_interruption",
            typed and isinstance(initial, dict) and isinstance(after, dict),
            valid,
            "The fixture actually closes one partial media body before its advertised length",
        )
        resumed = valid and any(
            row["route"] == interruption["route"]
            and row["status"] == 206
            and row["elapsed_seconds"] > interruption["elapsed_seconds"]
            for row in responses
        )
        finished = (
            [
                row
                for row in progress
                if row.get("status") == "finished"
                and _number(row.get("elapsed_seconds"))
            ]
            if isinstance(progress, list)
            else []
        )
        check(
            "during",
            "same_resource_range_resume",
            typed
            and isinstance(progress, list)
            and isinstance(initial, dict)
            and isinstance(after, dict),
            resumed
            and bool(finished)
            and min(row["elapsed_seconds"] for row in finished)
            > interruption["elapsed_seconds"],
            "A later partial-content response for the interrupted resource precedes observed transfer completion",
        )


def evaluate_refusal(
    raw: dict[str, Any],
    job: dict[str, Any],
    trace: list[dict[str, Any]],
    stage: Any,
    start: float,
    end: float,
    case: str,
    check: Any,
) -> None:
    before = raw.get("before_worker") or {}
    unwritable = case == "reliability-unwritable-output"
    if unwritable:
        present = "output_mode" in before and "output_writable" in before
        check(
            "before",
            "actual_unwritable_destination",
            present,
            before.get("output_mode") == 0o500
            and before.get("output_writable") is False,
            "Independent mode/access observation proves the private destination is not writable",
        )
        phases = {row["phase"]: row["elapsed_seconds"] for row in trace}
        present = all(
            key in phases for key in ("preflight_started", "preflight_refused")
        )
        check(
            "during",
            "preflight_refusal_before_worker_dispatch",
            present,
            present
            and start
            <= phases["preflight_started"]
            <= phases["preflight_refused"]
            <= end
            and "worker_dispatched" not in phases
            and "preflight_completed" not in phases,
            "The real destination preflight refuses before any media worker dispatch",
        )
        check(
            "after",
            "owned_permission_refusal",
            "error" in raw,
            isinstance(raw.get("error"), str)
            and raw["error"].startswith("PermissionError:")
            and job.get("output_dir", "") + "/.vodforge-access-" in raw["error"],
            "Permission error identifies the actual output-directory access probe",
        )
    else:
        check(
            "before",
            "actual_malformed_input",
            "url" in job,
            job.get("url") == "not a URL://[]",
            "The enrolled malformed source is submitted to the production seam",
        )
        dispatched = _dispatch(trace, start, end, check)
        events = raw.get("events")
        analysis = (
            [
                row
                for row in events
                if row.get("kind") == "status"
                and "analyzing source formats" in str(row.get("payload", ""))
            ]
            if isinstance(events, list)
            else []
        )
        check(
            "during",
            "malformed_source_analysis",
            isinstance(events, list) and dispatched is not None,
            any(
                _number(row.get("elapsed_seconds"))
                and dispatched <= row["elapsed_seconds"] < end
                for row in analysis
            ),
            "The same worker actually enters source analysis before input refusal",
        )
        diagnostic = raw.get("failure_diagnostic")
        check(
            "after",
            "owned_invalid_input_refusal",
            isinstance(diagnostic, dict) and "error" in raw,
            isinstance(diagnostic, dict)
            and diagnostic.get("reason") == "invalid_input"
            and diagnostic.get("stage") == "analysis"
            and diagnostic.get("error_type") == "DownloadError"
            and isinstance(raw.get("error"), str)
            and raw["error"].startswith("_DownloadItemExecutionError:")
            and "Unsupported URL:" in raw["error"],
            "Observed terminal error is invalid source input, not a network or dependency failure",
        )
    progress = raw.get("progress_trace")
    check(
        "during",
        "no_media_transfer_after_refusal",
        isinstance(progress, list),
        progress == [],
        "Refusal produces no media transfer callbacks",
    )
    stage_present = (
        isinstance(stage, list)
        and bool(stage)
        and all(
            isinstance(row, dict) and _number(row.get("elapsed_seconds"))
            for row in stage
        )
    )
    check(
        "before",
        "refusal_initial_staging_absent",
        stage_present,
        stage_present
        and stage[0]["elapsed_seconds"] <= start
        and stage[0].get("entries") == []
        and stage[0].get("root_present") is False,
        "Independent initial staging inventory predates worker admission",
    )
    if not unwritable:
        check(
            "during",
            "analysis_staging_absent",
            stage_present,
            stage_present
            and any(start <= row["elapsed_seconds"] < end for row in stage)
            and all(
                row.get("entries") == [] and row.get("root_present") is False
                for row in stage
            ),
            "Actual source analysis leaves private staging absent throughout observation",
        )
    final = stage[-1] if stage_present else {}
    check(
        "after",
        "refusal_outputs_and_staging_absent",
        stage_present and "outputs" in raw and "staging_entries_after" in raw,
        raw.get("outputs") == []
        and raw.get("media_output_count") == 0
        and raw.get("staging_entries_after") == []
        and final.get("final") is True
        and final.get("elapsed_seconds", -1) >= end
        and final.get("entries") == []
        and final.get("root_present") is False
        and raw.get("cancel_requested") is False
        and raw.get("control_request") is None,
        "No committed output, cancellation or residual staging follows the actual refusal",
    )
    cleanup(raw, check)


def evaluate_child_failure(
    raw: dict[str, Any],
    job: dict[str, Any],
    trace: list[dict[str, Any]],
    start: float,
    end: float,
    check: Any,
) -> None:
    _fixture(raw, job, trace, start, end, "/page/unicode", check)
    dependency = (raw.get("before_worker") or {}).get("dependency_override")
    present = isinstance(dependency, dict) and all(
        key in dependency for key in ("path", "sha256", "executable")
    )
    check(
        "before",
        "controlled_executable_identity",
        present,
        present
        and isinstance(dependency["path"], str)
        and dependency["path"].endswith("/tools/ffmpeg")
        and len(dependency["sha256"]) == 64
        and dependency["executable"] is True,
        "The private injected executable exists and has independently observed content identity",
    )
    children = raw.get("child_registration_trace")
    typed = isinstance(children, list) and all(
        isinstance(row, dict)
        and all(
            key in row
            for key in (
                "run_id",
                "pid",
                "args",
                "elapsed_seconds",
                "returncode_after_worker",
                "exit_observed_elapsed_seconds",
            )
        )
        for row in children
    )
    media_children = (
        [
            row
            for row in children
            if isinstance(row.get("args"), list)
            and "-y" in row["args"]
            and "-i" in row["args"]
        ]
        if typed
        else []
    )
    from .pipeline_interaction import _contained

    valid = (
        typed
        and present
        and bool(media_children)
        and all(
            row["run_id"] == job.get("run_id")
            and type(row["pid"]) is int
            and row["pid"] > 0
            and _number(row["elapsed_seconds"])
            and start < row["elapsed_seconds"] < end
            and row["args"][0] == dependency["path"]
            and row["returncode_after_worker"] == 17
            and _number(row["exit_observed_elapsed_seconds"])
            and row["exit_observed_elapsed_seconds"] >= end
            and _contained(
                row["args"][row["args"].index("-i") + 1].removeprefix("file:"),
                job.get("output_dir", ""),
                staged=True,
            )
            for row in media_children
        )
    )
    check(
        "during",
        "actual_owned_failing_media_child",
        typed and present,
        valid,
        "Production registered the exact fixture child with contained staged input and observed exit 17 after return",
    )
    diagnostic = raw.get("failure_diagnostic")
    check(
        "after",
        "specific_child_failure_terminal",
        isinstance(diagnostic, dict) and "error" in raw,
        isinstance(diagnostic, dict)
        and diagnostic.get("reason") == "transcoding"
        and diagnostic.get("stage") == "download"
        and raw.get("error")
        == "_DownloadItemExecutionError: ERROR: Postprocessing: VODForge controlled FFmpeg child exit 17"
        and raw.get("outputs") == []
        and raw.get("media_output_count") == 0
        and raw.get("cancel_requested") is False,
        "Terminal error reports the real injected child failure with no committed media",
    )


def cleanup(raw: dict[str, Any], check: Any) -> None:
    children = raw.get("active_children_before_harness_cleanup")
    check(
        "after",
        "production_child_cleanup",
        isinstance(children, list) and "harness_emergency_cleanup_used" in raw,
        isinstance(children, list)
        and all(row.get("alive") is False for row in children)
        and raw.get("harness_emergency_cleanup_used") is False,
        "Production children retire before any emergency harness containment",
    )
    check(
        "after",
        "observer_retired",
        "control_observer_stopped" in raw and "control_observer_errors" in raw,
        raw.get("control_observer_stopped") is True
        and raw.get("control_observer_errors") == [],
        "Observation workers retire without error",
    )
