"""Independent composition of actual worker intervals and post-GC observations.

This certifies controlled worker ownership. RSS trends require comparison, and
native UI memory, navigation and physical-input usability remain separate.
"""

from __future__ import annotations

import hashlib
import json
from itertools import pairwise
from pathlib import Path
from urllib.parse import urlsplit

from .pipeline_interaction import _contained, _evaluate, _number, load_observation

COMPOSITE_CONTRACTS = {
    "concurrency.simultaneous_worker_attack": "owned-concurrent-workers-v1",
    "lifecycle.repeated_job_soak": "owned-repeated-workers-v1",
}


def _payload(reference, root, check, phase, name, *, lines=False):
    present = isinstance(reference, dict) and all(
        isinstance(reference.get(k), str) for k in ("path", "sha256")
    )
    contained = present and _contained(reference["path"], str(root))
    check(
        phase,
        name + "_location",
        present,
        contained,
        "Constituent belongs to the same isolated cases directory",
    )
    if not contained:
        return None
    path = Path(reference["path"])
    try:
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > 32 * 1024 * 1024
        ):
            raise ValueError("not a bounded regular file")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != reference["sha256"]:
            raise ValueError("content changed")
        parsed = (
            [json.loads(line) for line in data.decode().splitlines()]
            if lines
            else json.loads(data)
        )
    except (OSError, ValueError):
        check(
            phase,
            name + "_binding",
            False,
            False,
            "Required constituent absent, changed or malformed",
        )
        return None
    check(
        phase,
        name + "_binding",
        True,
        True,
        "Original constituent content hash matches",
    )
    return parsed


def _worker(reference, root, check, name, output_type, origin, *, concurrent=False):
    raw = _payload(reference, root, check, "during", name)
    if not isinstance(raw, dict):
        return None

    def constituent_check(phase, code, present, valid, detail):
        if concurrent and code == "production_child_cleanup":
            # The registry is global: one returned worker can observe the other
            # worker's active child. The composite observes it after both return.
            check(
                phase,
                name + "_no_emergency",
                "harness_emergency_cleanup_used" in raw,
                raw.get("harness_emergency_cleanup_used") is False,
                "No cleanup masks concurrent registry observations",
            )
        else:
            check(phase, name + "_" + code, present, valid, detail)

    _evaluate(raw, (output_type, None, None, name), constituent_check)
    job = raw.get("job") or {}
    target = urlsplit(job.get("url", ""))
    check(
        "before",
        name + "_fixture_authority",
        isinstance(origin, str) and bool(target.netloc),
        target.scheme == "http"
        and target.hostname == "127.0.0.1"
        and target.port is not None
        and f"{target.scheme}://{target.netloc}" == origin
        and target.path == "/page/unicode"
        and target.query
        == ("concurrent=" + output_type.lower() if concurrent else "soak=controlled"),
        "Actual worker targets the independently observed private origin and workload",
    )
    trace = raw.get("control_trace")
    times = (
        {row["phase"]: row["elapsed_seconds"] for row in trace}
        if isinstance(trace, list)
        else {}
    )
    clock = raw.get("observation_clock_origin_monotonic")
    start, end = times.get("worker_started"), times.get("worker_finished")
    valid = _number(clock) and _number(start) and _number(end)
    check(
        "during",
        name + "_shared_clock",
        valid,
        valid and clock > 0 and 0 <= start < end,
        "Actual worker clock origin binds its interval to the composite timeline",
    )
    return (raw, clock + start, clock + end) if valid else None


def _children(raw, check):
    before, after = raw.get("before") or {}, raw.get("after") or {}
    check(
        "before",
        "no_initial_children",
        isinstance(before.get("children"), list),
        before.get("children") == [],
        "No prior registered child precedes this workload",
    )
    children = after.get("children_before_emergency")
    check(
        "after",
        "all_workers_retired_children",
        isinstance(children, list),
        isinstance(children, list)
        and all(row.get("alive") is False for row in children),
        "Global registry observed after workload return and before emergency containment",
    )


def _concurrency(raw, root, check):
    before, after = raw.get("before") or {}, raw.get("after") or {}
    clock = raw.get("clock_origin_monotonic")
    trace = raw.get("thread_trace")
    typed = isinstance(trace, list) and all(
        isinstance(row, dict)
        and _number(row.get("elapsed_seconds"))
        and isinstance(row.get("name"), str)
        and isinstance(row.get("phase"), str)
        for row in trace
    )
    check(
        "during",
        "ordered_thread_lifecycle",
        typed,
        typed
        and len(trace) == 4
        and all(
            a["elapsed_seconds"] <= b["elapsed_seconds"] for a, b in pairwise(trace)
        ),
        "Exactly two real entered/returned thread intervals in monotonic order",
    )
    workers = raw.get("workers")
    present = isinstance(workers, dict)
    check(
        "during",
        "two_workers_observed",
        present,
        present and set(workers) == {"mp3", "mp4"},
        "Both independently observed worker receipts are present",
    )
    if not typed or not present:
        return
    intervals = []
    jobs = []
    for name in ("mp3", "mp4"):
        observed = _worker(
            workers.get(name),
            root,
            check,
            "concurrency-" + name,
            name.upper(),
            before.get("fixture", {}).get("origin"),
            concurrent=True,
        )
        bounds = {
            row["phase"]: row["elapsed_seconds"] for row in trace if row["name"] == name
        }
        binding_present = (
            observed is not None
            and _number(clock)
            and all(_number(bounds.get(k)) for k in ("entered", "returned"))
            and _number(before.get("elapsed_seconds"))
            and _number(after.get("elapsed_seconds"))
        )
        valid = (
            binding_present
            and 0
            <= before["elapsed_seconds"]
            <= bounds["entered"]
            <= observed[1] - clock
            < observed[2] - clock
            <= bounds["returned"]
            <= after["elapsed_seconds"]
        )
        check(
            "during",
            name + "_thread_worker_ownership",
            binding_present,
            valid,
            "Same worker interval is enclosed by its actual thread entry/return, after baseline and before final inventory",
        )
        if observed is not None:
            intervals.append((observed[1], observed[2]))
            jobs.append(observed[0].get("job", {}))
    check(
        "during",
        "actual_worker_overlap",
        len(intervals) == 2,
        len(intervals) == 2
        and max(i[0] for i in intervals) < min(i[1] for i in intervals),
        "Actual production worker intervals overlap on one monotonic clock",
    )
    check(
        "before",
        "distinct_worker_owners",
        len(jobs) == 2,
        len(jobs) == 2
        and len({j.get("run_id") for j in jobs}) == 2
        and len({j.get("output_dir") for j in jobs}) == 2,
        "Concurrent workers have distinct durable run and output owners",
    )
    check(
        "after",
        "threads_returned_without_error",
        all(k in after for k in ("threads_alive", "errors")),
        after.get("threads_alive") == [] and after.get("errors") == [],
        "Both threads returned; no masked exceptions or alive workers",
    )


def _soak(raw, root, check):
    workload = raw.get("workload")
    typed = (
        isinstance(workload, dict)
        and type(workload.get("jobs")) is int
        and type(workload.get("tracemalloc_enabled")) is bool
    )
    jobs = workload.get("jobs", 0) if isinstance(workload, dict) else 0
    detailed = (
        workload.get("tracemalloc_enabled") if isinstance(workload, dict) else None
    )
    valid_workload = (
        typed
        and (jobs in {50, 100} if detailed else jobs == 3)
        and workload.get("contract") == "controlled-repeated-worker-v2"
        and workload.get("source_route") == "/page/unicode?soak=controlled"
        and workload.get("output_type") == "MP3"
        and workload.get("mp3_bitrate_kbps") == 192
        and all(
            workload.get(k) is False
            for k in (
                "write_thumbnail",
                "write_info_json",
                "embed_cover_art",
                "full_pipeline_results_retained_during_sampling",
            )
        )
    )
    check(
        "before",
        "bounded_workload",
        typed,
        valid_workload,
        "Declared 3-job NORMAL or detailed 50/100-job workload; full raw results released before GC",
    )
    samples = _payload(
        raw.get("samples"), root, check, "during", "post_gc_samples", lines=True
    )
    refs = raw.get("workers")
    observed = isinstance(samples, list) and isinstance(refs, list)
    check(
        "during",
        "complete_job_samples",
        observed and typed,
        observed
        and valid_workload
        and len(refs) == jobs
        and len(samples) == 2 * jobs + 1
        and samples[0].get("phase") == "baseline"
        and samples[0].get("job_index") is None
        and all(
            samples[2 * i - 1].get("phase") == "before_job"
            and samples[2 * i].get("phase") == "after_job"
            and samples[2 * i - 1].get("job_index")
            == i
            == samples[2 * i].get("job_index")
            for i in range(1, jobs + 1)
        ),
        "Every declared job has distinct before/after samples following the actual baseline",
    )
    if (
        not observed
        or not valid_workload
        or len(samples) != 2 * jobs + 1
        or len(refs) != jobs
    ):
        return
    origin = samples[0].get("observation_clock_origin_monotonic")
    timed = _number(origin) and all(
        row.get("observation_clock_origin_monotonic") == origin
        and _number(row.get("elapsed_seconds"))
        for row in samples
    )
    check(
        "during",
        "monotonic_sample_clock",
        timed,
        timed
        and all(
            0 <= a["elapsed_seconds"] < b["elapsed_seconds"]
            for a, b in pairwise(samples)
        ),
        "Baseline and all GC samples use one increasing monotonic clock",
    )
    seen = []
    for i, reference in enumerate(refs, 1):
        name = f"lifecycle-soak-{i:03d}"
        worker = _worker(
            reference,
            root,
            check,
            name,
            "MP3",
            raw.get("before", {}).get("fixture", {}).get("origin"),
        )
        before, after = samples[2 * i - 1], samples[2 * i]
        enclosed = timed and worker is not None
        check(
            "during",
            name + "_gc_interval",
            enclosed,
            enclosed
            and before["elapsed_seconds"]
            <= worker[1] - origin
            < worker[2] - origin
            <= after["elapsed_seconds"],
            "Actual production interval lies between its own pre-job and post-GC observations",
        )
        binding = after.get("job")
        check(
            "after",
            name + "_sample_result_binding",
            isinstance(binding, dict),
            isinstance(binding, dict)
            and binding.get("case_id") == name
            and binding.get("artifact") == reference.get("path")
            and binding.get("raw_result_sha256") == reference.get("sha256"),
            "Post-GC summary belongs to the exact hashed worker result",
        )
        if worker is not None:
            seen.append(worker[0].get("job", {}))
    check(
        "before",
        "distinct_repeated_owners",
        len(seen) == jobs,
        len(seen) == jobs
        and len({j.get("run_id") for j in seen}) == jobs
        and len({j.get("output_dir") for j in seen}) == jobs,
        "Repeated jobs have distinct run and destination owners",
    )
    post = [samples[0], *samples[2::2]]
    process_present = all(
        isinstance(s.get("process"), dict)
        and isinstance(s.get("process", {}).get("child_processes"), list)
        and isinstance(s.get("storage"), dict)
        and isinstance(s.get("gc"), dict)
        for s in post
    )
    check(
        "after",
        "post_gc_process_and_staging_retirement",
        process_present,
        process_present
        and all(
            s["process"].get("available") is True
            and s["process"]["child_processes"] == []
            and s["storage"].get("staging_residue_paths") == []
            and s["storage"].get("staging_residue_count") == 0
            and s["gc"].get("uncollectable_garbage_count") == 0
            for s in post
        ),
        "Independent baseline and each post-GC process/filesystem inventory show no retained children, staging or uncollectable garbage",
    )
    types = ("yt_downloader.models.DownloadJob", "yt_dlp.YoutubeDL.YoutubeDL")
    counts = [s.get("gc_tracked_objects", {}) for s in post]
    present = all(isinstance(c, dict) for c in counts)
    if detailed:
        present = present and all(
            c.get("available") is True
            and all(
                type(c.get("selected_type_counts", {}).get(t)) is int for t in types
            )
            for c in counts
        )
        valid = present and all(
            c["selected_type_counts"][t] <= counts[0]["selected_type_counts"][t]
            for c in counts[1:]
            for t in types
        )
    else:
        valid = present and all(
            c.get("available") is False
            and c.get("scope") == "disabled_in_normal_profile"
            for c in counts
        )
    check(
        "after",
        "retained_worker_object_visibility",
        present,
        valid,
        "Detailed workload observes bounded selected worker object counts after every GC; NORMAL explicitly leaves allocation visibility unavailable",
    )


def evaluate_lifecycle(scenario):
    raw, reason = load_observation(scenario)
    rows = []

    def check(phase, name, present, valid, detail):
        rows.append(
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
        for phase in ("before", "during", "after"):
            check(phase, "raw_receipt_binding", False, False, reason)
    else:
        try:
            check(
                "before",
                "composite_identity",
                all(k in raw for k in ("scenario_id", "contract")),
                raw.get("scenario_id") == scenario["id"]
                and raw.get("contract") == COMPOSITE_CONTRACTS[scenario["id"]],
                "Composite identity matches its enrolled workload",
            )
            root = Path(scenario["raw_result"]).parent
            if scenario["id"] == "lifecycle.repeated_job_soak":
                root = root.parent
            _children(raw, check)
            (
                _soak
                if scenario["id"] == "lifecycle.repeated_job_soak"
                else _concurrency
            )(raw, root, check)
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            check(
                "during",
                "observation_schema",
                False,
                False,
                "Required typed composite observation is missing or malformed",
            )
    phases = {}
    for phase in ("before", "during", "after"):
        states = [r["status"] for r in rows if r["phase"] == phase]
        phases[phase] = (
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
        "assertion_mapping": rows,
        "domain_contract": COMPOSITE_CONTRACTS[scenario["id"]],
        "reason": "Independent controlled worker lifecycle evidence; native UX and comparison of memory trends remain separate.",
    }
