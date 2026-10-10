"""Observed W3C generic-source cleanliness; no provider support promise."""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

from .pipeline_interaction import _evaluate, _number, load_observation

PUBLIC_CONTRACTS = {
    "correctness.public_w3c_generic_boundary": "observed-public-generic-boundary-v1"
}
URL = "https://media.w3.org/2010/05/sintel/trailer.mp4"


def _refusal(raw, check):
    job, baseline = raw.get("job"), raw.get("before_worker")
    check(
        "before",
        "fresh_real_worker",
        isinstance(job, dict) and isinstance(baseline, dict),
        isinstance(job, dict)
        and isinstance(baseline, dict)
        and baseline.get("output_files") == []
        and baseline.get("output_exists") is False
        and raw.get("pipeline_entrypoint")
        == "yt_downloader.app.DownloadWorkerCore._download_worker_single"
        and isinstance(job.get("run_id"), str)
        and len(job["run_id"]) == 32,
        "A fresh destination and an owned real product worker precede public-source analysis",
    )
    trace = raw.get("control_trace")
    expected = [
        "worker_started",
        "preflight_started",
        "preflight_completed",
        "worker_dispatched",
        "worker_finished",
    ]
    typed = (
        isinstance(trace, list)
        and len(trace) == 5
        and all(isinstance(v, dict) for v in trace)
    )
    check(
        "during",
        "owned_ordered_execution",
        typed,
        typed
        and [v.get("phase") for v in trace] == expected
        and all(
            v.get("run_id") == job.get("run_id")
            and _number(v.get("elapsed_seconds"))
            and v["elapsed_seconds"] >= 0
            for v in trace
        )
        and all(
            a["elapsed_seconds"] < b["elapsed_seconds"] for a, b in pairwise(trace)
        ),
        "Exact same-run preflight, dispatch and terminal observations are strictly ordered",
    )
    if not typed or not all(_number(v.get("elapsed_seconds")) for v in trace):
        return
    start, dispatch, end = (
        trace[0]["elapsed_seconds"],
        trace[3]["elapsed_seconds"],
        trace[4]["elapsed_seconds"],
    )
    events = raw.get("events")
    analysis = (
        [
            v
            for v in events
            if v.get("kind") == "status"
            and "analyzing source formats" in str(v.get("payload"))
        ]
        if isinstance(events, list)
        else []
    )
    job_events = (
        [v for v in events if v.get("kind") == "job_log"]
        if isinstance(events, list)
        else []
    )
    check(
        "during",
        "observed_source_analysis",
        isinstance(events, list),
        bool(analysis)
        and all(
            _number(v.get("elapsed_seconds")) and dispatch <= v["elapsed_seconds"] < end
            for v in analysis
        )
        and bool(job_events)
        and all(
            v.get("payload", {}).get("job", {}).get("run_id") == job.get("run_id")
            and v.get("payload", {}).get("job", {}).get("url") == URL
            for v in job_events
        ),
        "Actual analysis feedback and normalized source/job observations belong to this dispatched public worker",
    )
    check(
        "during",
        "no_transfer_on_analysis_refusal",
        "progress_trace" in raw,
        raw.get("progress_trace") == [],
        "Analysis refusal produces no media transfer callback",
    )
    stage = raw.get("staging_trace")
    stage_typed = (
        isinstance(stage, list)
        and len(stage) >= 3
        and all(
            isinstance(v, dict) and _number(v.get("elapsed_seconds")) for v in stage
        )
    )
    check(
        "before",
        "no_prior_stage",
        stage_typed,
        stage_typed
        and stage[0]["elapsed_seconds"] <= start
        and stage[0].get("entries") == []
        and stage[0].get("root_present") is False,
        "Independent filesystem inventory is empty before worker entry",
    )
    check(
        "during",
        "no_stage_through_analysis",
        stage_typed,
        stage_typed
        and any(dispatch <= v["elapsed_seconds"] < end for v in stage)
        and all(
            a["elapsed_seconds"] <= b["elapsed_seconds"] for a, b in pairwise(stage)
        )
        and all(
            v.get("entries") == []
            and v.get("root_present") is False
            and v.get("run_directories") == []
            for v in stage
        ),
        "Before, during and after inventories show no staging or run directory for analysis refusal",
    )
    diagnostic = raw.get("failure_diagnostic")
    http = diagnostic.get("http_status") if isinstance(diagnostic, dict) else None
    check(
        "after",
        "bounded_analysis_refusal",
        isinstance(diagnostic, dict) and "error" in raw,
        isinstance(raw.get("error"), str)
        and raw["error"].startswith("_DownloadItemExecutionError:")
        and isinstance(diagnostic, dict)
        and diagnostic.get("stage") == "analysis"
        and diagnostic.get("error_type")
        in {
            "ExtractorError",
            "HTTPError",
            "DownloadError",
            "SSLError",
            "TimeoutError",
            "ConnectionError",
            "URLError",
            "OSError",
        }
        and isinstance(diagnostic.get("reason"), str)
        and diagnostic["reason"]
        in {
            "unknown",
            "source_unavailable",
            "network_error",
            "tls_failure",
            "timeout",
            "authentication_required",
        }
        and (http is None or type(http) is int and 100 <= http <= 599)
        and raw.get("cancel_requested") is False
        and raw.get("skip_video_requested") is False
        and raw.get("control_request") is None,
        "Owned analysis failure retains bounded machine cause and is distinct from cancel/skip or a fictitious completion",
    )
    check(
        "after",
        "empty_final_filesystem",
        all(
            k in raw
            for k in (
                "outputs",
                "media_output_count",
                "output_bytes",
                "staging_entries_after",
            )
        )
        and stage_typed,
        raw.get("outputs") == []
        and raw.get("media_output_count") == 0
        and raw.get("output_bytes") == 0
        and raw.get("staging_entries_after") == []
        and stage_typed
        and stage[-1].get("final") is True
        and stage[-1]["elapsed_seconds"] >= end,
        "After worker return no output, output bytes or staging residue is published",
    )
    children = raw.get("active_children_before_harness_cleanup")
    check(
        "after",
        "production_cleanup_before_containment",
        isinstance(children, list) and "harness_emergency_cleanup_used" in raw,
        isinstance(children, list)
        and all(v.get("alive") is False for v in children)
        and raw.get("harness_emergency_cleanup_used") is False
        and raw.get("active_children_after_harness_cleanup") == [],
        "Production child ownership is retired before any emergency harness containment",
    )
    check(
        "after",
        "observer_retired",
        all(k in raw for k in ("control_observer_stopped", "control_observer_errors")),
        raw.get("control_observer_stopped") is True
        and raw.get("control_observer_errors") == [],
        "Observation worker retires without error",
    )


def evaluate_public_boundary(scenario):
    raw, reason = load_observation(scenario)
    assertions = []

    def check(phase, name, present, valid, detail):
        assertions.append(
            {
                "phase": phase,
                "assertion": name,
                "status": "unproven"
                if not present
                else "passed"
                if valid
                else "failed",
                "evidence": detail,
            }
        )

    if raw is None:
        for p in ("before", "during", "after"):
            check(p, "raw_receipt_binding", False, False, reason)
    else:
        try:
            job = raw.get("job", {})
            check(
                "before",
                "explicit_public_source",
                isinstance(job, dict) and "case_id" in raw,
                raw.get("case_id") == "public-w3c-sintel"
                and job.get("url") == URL
                and job.get("output_type") == "MP4"
                and job.get("quality_label") == "480p"
                and job.get("output_dir")
                == str(Path(scenario["raw_result"]).parent / "output"),
                "Exact public W3C source, output request and owned destination identify this bounded probe",
            )
            if raw.get("error") is None:
                _evaluate(raw, ("MP4", None, None, "public-w3c-sintel"), check)
            else:
                _refusal(raw, check)
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            check(
                "during",
                "observation_schema",
                False,
                False,
                "Missing or malformed public-boundary evidence",
            )
    phases = {}
    for p in ("before", "during", "after"):
        states = [v["status"] for v in assertions if v["phase"] == p]
        phases[p] = (
            "failed"
            if "failed" in states
            else "unproven"
            if not states or "unproven" in states
            else "passed"
        )
    return {
        "status": "failed"
        if "failed" in phases.values()
        else "unproven"
        if "unproven" in phases.values()
        else "passed",
        "scenario_id": scenario["id"],
        "required_phases": list(phases),
        "phase_review": phases,
        "assertion_mapping": assertions,
        "domain_contract": PUBLIC_CONTRACTS[scenario["id"]],
        "reason": "Generic public-source cleanliness only. An analysis refusal proves cleanup, never provider support or successful decoding; no native interface is qualified.",
    }
