"""Independent temporal assertions over content-bound real-worker observations.

This domain certifies staging/progress/commit or cancellation ownership in the
headless worker. It makes no native smoothness or product usability claim.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from itertools import pairwise
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import urlsplit

CONTRACTS = {
    "reliability.transient_http_retry": ("MP3", None, None, "reliability-retry-503"),
    "reliability.network_interruption_recovery": (
        "MP4",
        None,
        None,
        "reliability-interrupted-transfer",
    ),
    "reliability.unwritable_output_directory": (
        "MP4",
        None,
        None,
        "reliability-unwritable-output",
    ),
    "reliability.malformed_url": ("MP4", None, None, "reliability-malformed-url"),
    "reliability.ffmpeg_child_failure": (
        "MP4",
        None,
        None,
        "reliability-ffmpeg-child-failure",
    ),
    "reliability.http_404_cleanup": ("MP4", None, None, "reliability-http-404"),
    "correctness.local_mp4_real_pipeline": ("MP4", None, None, "correctness-local-mp4"),
    "correctness.local_mp3_bitrate_real_pipeline": (
        "MP3",
        None,
        None,
        "correctness-local-mp3",
    ),
    "correctness.local_mp4_embedding_disabled": (
        "MP4",
        None,
        None,
        "correctness-local-mp4-embedding-disabled",
    ),
    "correctness.source_quality_selection_360p": (
        "MP4",
        360,
        None,
        "correctness-source-quality-360p",
    ),
    "correctness.source_quality_selection_720p": (
        "MP4",
        540,
        None,
        "correctness-source-quality-720p",
    ),
    "reliability.cancel_during_slow_download": (
        "MP4",
        None,
        "downloading",
        "reliability-cancel-slow",
    ),
    "reliability.cancel_during_transcode": (
        "MP4",
        None,
        "transcoding",
        "reliability-cancel-transcode",
    ),
}


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _contained(path: str, root: str, *, staged: bool = False) -> bool:
    cls = PureWindowsPath if PureWindowsPath(root).drive else PurePosixPath
    try:
        if not cls(path).is_absolute() or not cls(root).is_absolute():
            return False
        relative = cls(path).relative_to(cls(root))
    except (ValueError, TypeError):
        return False
    return (
        bool(relative.parts)
        and ".." not in relative.parts
        and (
            relative.parts[0] == ".vfstage"
            if staged
            else ".vfstage" not in relative.parts
        )
    )


def load_observation(scenario: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """Reject missing/changed raw files instead of trusting scenario pass flags."""
    name, expected = scenario.get("raw_result"), scenario.get("raw_result_sha256")
    if (
        not isinstance(name, str)
        or not isinstance(expected, str)
        or len(expected) != 64
    ):
        return None, "Missing content-bound raw worker receipt"
    try:
        path = Path(name)
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > 32 * 1024 * 1024
        ):
            return None, "Raw receipt is not a bounded regular file"
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != expected:
            return None, "Raw receipt changed after observation"
        raw = json.loads(payload)
    except (OSError, ValueError):
        return None, "Raw receipt is unavailable or malformed"
    return (
        (raw, "Content hash verified")
        if isinstance(raw, dict)
        else (None, "Raw receipt is not an object")
    )


def evaluate_pipeline(scenario: Mapping[str, Any]) -> dict[str, Any]:
    specification = CONTRACTS[str(scenario["id"])]
    raw, reason = load_observation(scenario)
    rows: list[dict[str, str]] = []

    def check(phase: str, code: str, present: bool, valid: bool, detail: str) -> None:
        rows.append(
            {
                "phase": phase,
                "assertion": code,
                "status": "unproven"
                if not present
                else "passed"
                if valid
                else "failed",
                "evidence": detail,
            }
        )

    if raw is None:
        for phase in ("before", "during", "after"):
            check(phase, "raw_receipt_binding", False, False, reason)
    else:
        try:
            _evaluate(raw, specification, check)
        except (KeyError, TypeError, ValueError, AttributeError):
            check(
                "before",
                "observation_schema",
                False,
                False,
                "Required typed worker observation is missing or malformed",
            )
    phase_review = {}
    for phase in ("before", "during", "after"):
        states = [row["status"] for row in rows if row["phase"] == phase]
        phase_review[phase] = (
            "failed"
            if "failed" in states
            else "unproven"
            if not states or "unproven" in states
            else "passed"
        )
    states = list(phase_review.values())
    return {
        "status": "failed"
        if "failed" in states
        else "unproven"
        if "unproven" in states
        else "passed",
        "scenario_id": scenario["id"],
        "reason": "Reviewed real-worker precondition, in-flight staging/progress, and terminal ownership assertions; native UX remains separate.",
        "required_phases": ["before", "during", "after"],
        "assertion_mapping": rows,
        "phase_review": phase_review,
        "domain_contract": "real-worker-staging-control-v1",
    }


def _evaluate_source_quality(
    raw: dict[str, Any],
    job: dict[str, Any],
    events: Any,
    transfers: list[dict[str, Any]],
    start: float,
    end: float,
    ceiling: str,
    height: int,
    check: Any,
) -> None:
    """Bind source selection to observed inventory, owner and pipeline phase."""
    check(
        "before",
        "requested_quality_ceiling",
        "quality_label" in job,
        job.get("quality_label") == ceiling,
        "Requested source ceiling matches the enrolled controlled fixture",
    )
    metadata = (
        [e for e in events if e.get("kind") == "job_metadata"]
        if isinstance(events, list)
        else []
    )
    typed = (
        all(
            isinstance(job.get(k), str) and job[k]
            for k in ("run_id", "url", "output_dir", "output_type")
        )
        and bool(metadata)
        and all(
            isinstance(e.get("payload"), dict)
            and isinstance(e["payload"].get("job"), dict)
            and isinstance(e["payload"].get("info"), dict)
            and _number(e.get("elapsed_seconds"))
            for e in metadata
        )
    )
    check(
        "during",
        "source_metadata_owner",
        typed,
        typed
        and all(
            start <= e["elapsed_seconds"] < end
            and all(
                e["payload"]["job"].get(k) == job.get(k)
                for k in ("run_id", "url", "output_dir", "output_type")
            )
            and e["payload"]["job"].get("quality_label") == ceiling
            for e in metadata
        )
        and all(
            a["elapsed_seconds"] <= b["elapsed_seconds"] for a, b in pairwise(metadata)
        ),
        "Timestamped format metadata belongs to this source and active run",
    )
    if not typed:
        return
    inventories = [e["payload"]["info"].get("formats") for e in metadata]
    inventory_present = all(
        isinstance(fs, list)
        and bool(fs)
        and all(
            isinstance(f, dict)
            and all(k in f for k in ("format_id", "height", "url", "vcodec", "acodec"))
            for f in fs
        )
        for fs in inventories
    )
    inventory_valid = inventory_present and all(
        len(fs) == 2
        and {f["format_id"]: f["height"] for f in fs}
        == {"hls-1100": 360, "hls-2100": 540}
        and all(
            isinstance(f["url"], str)
            and f["url"]
            and f["vcodec"] not in (None, "none")
            and f["acodec"] not in (None, "none")
            for f in fs
        )
        and fs == inventories[0]
        for fs in inventories
    )
    first_byte = min((p["elapsed_seconds"] for p in transfers), default=None)
    check(
        "during",
        "observed_source_inventory",
        inventory_present and _number(first_byte),
        inventory_valid and metadata[0]["elapsed_seconds"] < first_byte,
        "Same-run offered 360/540 source inventory observed before positive transfer bytes",
    )
    selected = [
        e for e in metadata if e["payload"]["job"].get("failure_stage") == "download"
    ]
    transcodes = [
        e["elapsed_seconds"]
        for e in events
        if e.get("kind") == "status"
        and "transcoding" in str(e.get("payload", "")).lower()
        and _number(e.get("elapsed_seconds"))
        and start <= e["elapsed_seconds"] < end
    ]
    selection_present = (
        inventory_present
        and bool(selected)
        and bool(transcodes)
        and all(
            all(k in e["payload"]["info"] for k in ("format_id", "height", "url"))
            for e in selected
        )
        and _number(first_byte)
    )
    best = (
        max(
            (
                f["height"]
                for f in inventories[0]
                if _number(f["height"]) and f["height"] <= int(ceiling[:-1])
            ),
            default=None,
        )
        if inventory_present
        else None
    )
    selection_valid = (
        selection_present
        and inventory_valid
        and best == height
        and all(
            first_byte <= e["elapsed_seconds"] <= min(transcodes)
            and e["payload"]["info"]["height"] == best
            and any(
                f["height"] == best
                and all(e["payload"]["info"][k] == f[k] for k in ("format_id", "url"))
                for f in inventories[0]
            )
            for e in selected
        )
    )
    check(
        "during",
        "observed_source_selection",
        selection_present,
        selection_valid,
        "Chosen source is the highest offered tier within the ceiling, observed after transfer and before transcode",
    )
    terminal = metadata[-1]
    check(
        "after",
        "terminal_source_metadata",
        isinstance(raw.get("latest_metadata"), dict)
        and terminal["payload"]["job"].get("failure_stage") == "commit",
        raw.get("latest_metadata") == terminal["payload"]["info"]
        and bool(selected)
        and all(
            terminal["payload"]["info"].get(k) == selected[-1]["payload"]["info"].get(k)
            for k in ("format_id", "height", "url")
        ),
        "Terminal metadata agrees with the same-run observed source selection",
    )


def _evaluate_http404(
    raw: dict[str, Any],
    job: dict[str, Any],
    trace: list[dict[str, Any]],
    stage: Any,
    events: Any,
    start: float,
    end: float,
    check: Any,
) -> None:
    """Qualify analysis-stage HTTP refusal, distinct from media-transfer cases."""
    origin = urlsplit(job.get("url", ""))
    dispatches = [r for r in trace if r.get("phase") == "worker_dispatched"]
    dispatched = dispatches[0].get("elapsed_seconds") if len(dispatches) == 1 else None
    check(
        "during",
        "actual_worker_dispatch",
        _number(dispatched),
        _number(dispatched) and start <= dispatched < end,
        "Worker dispatch is observed after preflight and before the production seam",
    )
    if not _number(dispatched):
        return
    check(
        "before",
        "controlled_http_origin",
        bool(job.get("url")),
        origin.scheme == "http"
        and origin.hostname == "127.0.0.1"
        and origin.port is not None
        and origin.path == "/status/404"
        and not origin.query,
        "Enrolled request targets the exact private loopback 404 fixture",
    )
    before = raw.get("before_worker") or {}
    initial = before.get("fixture_state")
    check(
        "before",
        "fixture_listener_authority",
        isinstance(initial, dict) and isinstance(initial.get("origin"), str),
        isinstance(initial, dict)
        and initial.get("origin") == f"{origin.scheme}://{origin.netloc}",
        "The independent fixture listening address matches the requested source origin",
    )
    check(
        "before",
        "unrequested_fixture_baseline",
        isinstance(initial, dict) and _number(before.get("fixture_elapsed_seconds")),
        isinstance(initial, dict)
        and initial.get("total_requests") == 0
        and initial.get("responses") == []
        and before.get("fixture_elapsed_seconds", float("inf")) <= start,
        "Fixture inventory has no prior requests before worker entry",
    )
    responses = raw.get("fixture_response_trace")
    response_present = isinstance(responses, list) and all(
        isinstance(r, dict)
        and all(k in r for k in ("route", "status", "elapsed_seconds"))
        for r in responses
    )
    valid_responses = (
        response_present
        and bool(responses)
        and _number(dispatched)
        and all(
            r["route"] == "/status/404"
            and r["status"] == 404
            and _number(r["elapsed_seconds"])
            and dispatched <= r["elapsed_seconds"] < end
            for r in responses
        )
    )
    check(
        "during",
        "actual_fixture_404_response",
        response_present,
        valid_responses,
        "The fixture sent HTTP404 headers during this dispatched worker interval",
    )
    analysis = (
        [
            e
            for e in events
            if e.get("kind") == "status"
            and "analyzing source formats" in str(e.get("payload", ""))
        ]
        if isinstance(events, list)
        else []
    )
    check(
        "during",
        "source_analysis_precedes_refusal",
        isinstance(events, list) and response_present,
        valid_responses
        and any(
            _number(e.get("elapsed_seconds"))
            and dispatched <= e["elapsed_seconds"] <= responses[0]["elapsed_seconds"]
            for e in analysis
        ),
        "Observed source analysis precedes the provider refusal",
    )
    progress = raw.get("progress_trace")
    check(
        "during",
        "no_media_transfer_after_refusal",
        isinstance(progress, list),
        isinstance(progress, list) and progress == [],
        "Analysis refusal produces no media transfer callback",
    )
    stage_present = (
        isinstance(stage, list)
        and bool(stage)
        and all(
            isinstance(r, dict)
            and all(
                k in r for k in ("elapsed_seconds", "entries", "root_present", "final")
            )
            for r in stage
        )
    )
    check(
        "during",
        "no_staging_for_analysis_refusal",
        stage_present,
        stage_present
        and stage[0]["elapsed_seconds"] <= start
        and stage[-1]["elapsed_seconds"] >= end
        and stage[-1]["final"] is True
        and all(_number(r["elapsed_seconds"]) for r in stage)
        and _number(dispatched)
        and any(dispatched <= r["elapsed_seconds"] < end for r in stage)
        and all(
            a["elapsed_seconds"] <= b["elapsed_seconds"] for a, b in pairwise(stage)
        )
        and all(r["entries"] == [] and r["root_present"] is False for r in stage),
        "Independent inventories before, during analysis and after return have no staging root",
    )
    after = raw.get("fixture_state_after")
    check(
        "after",
        "fixture_response_inventory_agrees",
        isinstance(after, dict)
        and isinstance(initial, dict)
        and isinstance(initial.get("origin"), str)
        and isinstance(after.get("origin"), str)
        and response_present
        and _number(raw.get("fixture_after_elapsed_seconds")),
        isinstance(after, dict)
        and valid_responses
        and raw["fixture_after_elapsed_seconds"] >= end
        and isinstance(initial, dict)
        and after.get("origin") == initial.get("origin")
        and after.get("requests") == {"/status/404": len(responses)}
        and after.get("statuses") == {"404": len(responses)}
        and after.get("total_requests") == len(responses)
        and isinstance(after.get("responses"), list)
        and len(after["responses"]) == len(responses)
        and all(
            r.get("route") == "/status/404" and r.get("status") == 404
            for r in after["responses"]
        ),
        "Post-worker fixture counts agree with the actual in-flight response trace",
    )
    diagnostic = raw.get("failure_diagnostic")
    check(
        "after",
        "owned_http404_terminal_failure",
        isinstance(diagnostic, dict) and "error" in raw and "cancel_requested" in raw,
        isinstance(diagnostic, dict)
        and diagnostic.get("http_status") == 404
        and diagnostic.get("stage") == "analysis"
        and diagnostic.get("reason") == "source_unavailable"
        and diagnostic.get("error_type") == "HTTPError"
        and isinstance(raw.get("error"), str)
        and raw["error"].startswith("_DownloadItemExecutionError:")
        and raw.get("cancel_requested") is False
        and raw.get("control_request") is None,
        "Same-job diagnostic records an analysis HTTP404, not cancellation or an unrelated error",
    )
    check(
        "after",
        "no_committed_media_after_refusal",
        "outputs" in raw and "staging_entries_after" in raw,
        raw.get("outputs") == []
        and raw.get("media_output_count") == 0
        and raw.get("staging_entries_after") == [],
        "Post-worker output and staging inventories are empty",
    )
    children = raw.get("active_children_before_harness_cleanup")
    check(
        "after",
        "production_child_cleanup",
        isinstance(children, list) and "harness_emergency_cleanup_used" in raw,
        isinstance(children, list)
        and all(r.get("alive") is False for r in children)
        and raw.get("harness_emergency_cleanup_used") is False,
        "Production children are retired before any emergency harness containment",
    )
    check(
        "after",
        "observer_retired",
        "control_observer_stopped" in raw and "control_observer_errors" in raw,
        raw.get("control_observer_stopped") is True
        and raw.get("control_observer_errors") == [],
        "Observation workers retired without error",
    )


def _evaluate(raw: dict[str, Any], specification: tuple, check: Any) -> None:
    output_type, height, cancel_phase, expected_case = specification
    check(
        "before",
        "scenario_observation_identity",
        isinstance(raw.get("case_id"), str) and bool(raw["case_id"]),
        raw.get("case_id") == expected_case,
        "Raw worker case identity matches the enrolled scenario",
    )
    job = raw.get("job") or {}
    trace = raw.get("control_trace")
    stage = raw.get("staging_trace")
    events = raw.get("events")
    progress = raw.get("progress_trace")
    baseline = raw.get("before_worker")
    check(
        "before",
        "empty_destination",
        isinstance(baseline, dict) and "output_files" in baseline,
        isinstance(baseline, dict) and baseline.get("output_files") == [],
        "Independent destination inventory before worker entry",
    )
    check(
        "before",
        "worker_authority",
        isinstance(job, dict),
        bool(job.get("run_id"))
        and job.get("output_type") == output_type
        and raw.get("pipeline_entrypoint")
        == "yt_downloader.app.DownloadWorkerCore._download_worker_single",
        "Actual worker entrypoint and requested format/run identity",
    )
    times = (
        {row["phase"]: row["elapsed_seconds"] for row in trace if isinstance(row, dict)}
        if isinstance(trace, list)
        else {}
    )
    owner_valid = isinstance(trace, list) and all(
        row.get("run_id") == job.get("run_id") for row in trace
    )
    ordered = (
        isinstance(trace, list)
        and all(
            _number(row.get("elapsed_seconds")) and row["elapsed_seconds"] >= 0
            for row in trace
        )
        and all(
            a["elapsed_seconds"] <= b["elapsed_seconds"] for a, b in pairwise(trace)
        )
    )
    start, end = times.get("worker_started"), times.get("worker_finished")
    valid_bounds = _number(start) and _number(end) and start < end
    check(
        "during",
        "owned_monotonic_worker_interval",
        isinstance(trace, list) and valid_bounds,
        owner_valid
        and ordered
        and sum(row.get("phase") == "worker_started" for row in trace) == 1
        and sum(row.get("phase") == "worker_finished" for row in trace) == 1,
        "Same-run worker/control observations with monotonic start/finish",
    )
    if not valid_bounds:
        return
    if expected_case == "reliability-http-404":
        _evaluate_http404(raw, job, trace, stage, events, start, end, check)
        return
    if expected_case in {"reliability-unwritable-output", "reliability-malformed-url"}:
        from .reliability_interaction import evaluate_refusal

        evaluate_refusal(raw, job, trace, stage, start, end, expected_case, check)
        return
    before_stage = (
        isinstance(stage, list)
        and bool(stage)
        and stage[0].get("elapsed_seconds", float("inf")) <= start
    )
    check(
        "before",
        "no_prior_staging",
        before_stage,
        before_stage
        and stage[0].get("entries") == []
        and stage[0].get("root_present") is False,
        "Synchronous staging inventory before worker starts",
    )
    in_stage = (
        [
            row
            for row in stage
            if _number(row.get("elapsed_seconds"))
            and start <= row["elapsed_seconds"] < end
            and row.get("root_present") is True
            and row.get("run_directories")
        ]
        if isinstance(stage, list)
        else []
    )
    check(
        "during",
        "private_staging_observed",
        isinstance(stage, list),
        bool(in_stage),
        "Actual private staging directory observed while worker remains active",
    )
    transfers = (
        [
            row
            for row in progress
            if row.get("status") == "downloading"
            and _number(row.get("elapsed_seconds"))
            and start <= row["elapsed_seconds"] < end
            and _number(row.get("downloaded_bytes"))
            and row["downloaded_bytes"] > 0
        ]
        if isinstance(progress, list)
        else []
    )
    check(
        "during",
        "transfer_destination_owned",
        isinstance(progress, list),
        bool(transfers)
        and all(
            _contained(
                str(row.get("filename", "")),
                str(job.get("output_dir", "")),
                staged=True,
            )
            for row in transfers
        ),
        "Positive transfer bytes target contained staging paths during active work",
    )
    if expected_case in {"reliability-retry-503", "reliability-interrupted-transfer"}:
        from .reliability_interaction import evaluate_recovery

        evaluate_recovery(raw, job, trace, start, end, expected_case, check)
    if height is not None:
        ceiling = "360p" if expected_case.endswith("360p") else "720p"
        _evaluate_source_quality(
            raw, job, events, transfers, start, end, ceiling, height, check
        )
    if cancel_phase:
        request, dispatch = (
            times.get("control_requested"),
            times.get("control_dispatched"),
        )
        valid_request = (
            _number(request)
            and _number(dispatch)
            and start < request <= dispatch <= end
        )
        check(
            "during",
            "cancel_active_phase",
            isinstance(events, list) and valid_request,
            valid_request
            and any(
                e.get("kind") == "status"
                and cancel_phase in str(e.get("payload", "")).lower()
                and start < e.get("elapsed_seconds", -1) <= request
                for e in events
            ),
            "Cancellation requested only after the designated actual download/transcode phase",
        )
        check(
            "after",
            "cancel_no_committed_media",
            "outputs" in raw and "cancel_requested" in raw,
            raw.get("cancel_requested") is True
            and raw.get("control_request") == "cancel"
            and raw.get("outputs") == []
            and raw.get("media_output_count") == 0
            and raw.get("error")
            == "_DownloadControlRequestError: Download cancelled by user",
            "Owned cancellation terminal error with no committed output",
        )
    elif expected_case == "reliability-ffmpeg-child-failure":
        from .reliability_interaction import evaluate_child_failure

        evaluate_child_failure(raw, job, trace, start, end, check)
    else:
        outputs = raw.get("outputs")
        media = (
            [
                row
                for row in outputs
                if Path(row.get("path", "")).suffix.lower() in {".mp4", ".mp3"}
            ]
            if isinstance(outputs, list)
            else []
        )
        valid_media = (
            len(media) == 1
            and media[0].get("readable") is True
            and _contained(media[0].get("path", ""), job.get("output_dir", ""))
            and _number(media[0].get("size_bytes"))
            and media[0]["size_bytes"] > 0
            and len(media[0].get("sha256", "")) == 64
        )
        streams = media[0].get("ffprobe", {}).get("streams", []) if valid_media else []
        audio = [s for s in streams if s.get("codec_type") == "audio"]
        video = [
            s
            for s in streams
            if s.get("codec_type") == "video"
            and not s.get("disposition", {}).get("attached_pic")
        ]
        contract_valid = (
            len(audio) == 1
            and audio[0].get("codec_name") == ("mp3" if output_type == "MP3" else "aac")
            and (
                not video
                if output_type == "MP3"
                else len(video) == 1
                and video[0].get("codec_name") == "h264"
                and (height is None or video[0].get("height") == height)
            )
        )
        check(
            "after",
            "independent_committed_media",
            isinstance(outputs, list),
            valid_media
            and contract_valid
            and raw.get("error") is None
            and raw.get("cancel_requested") is False,
            "Independent output hash/size/ffprobe and contained committed output match format and source-height contract",
        )
    final_stage = stage[-1] if isinstance(stage, list) and stage else {}
    check(
        "after",
        "retired_staging",
        "staging_entries_after" in raw and bool(final_stage),
        raw.get("staging_entries_after") == []
        and final_stage.get("final") is True
        and final_stage.get("elapsed_seconds", -1) >= end
        and final_stage.get("entries") == []
        and final_stage.get("root_present") is False,
        "Final filesystem inventory after worker return has no staging residue",
    )
    children = raw.get("active_children_before_harness_cleanup")
    check(
        "after",
        "production_child_cleanup",
        isinstance(children, list) and "harness_emergency_cleanup_used" in raw,
        isinstance(children, list)
        and all(row.get("alive") is False for row in children)
        and raw.get("harness_emergency_cleanup_used") is False,
        "Production child registry observed before any harness emergency cleanup",
    )
    check(
        "after",
        "observer_retired",
        "control_observer_stopped" in raw and "control_observer_errors" in raw,
        raw.get("control_observer_stopped") is True
        and raw.get("control_observer_errors") == [],
        "Observation worker stopped without error",
    )
