"""Independent owned journal, report-refusal and staging transaction oracles.

A durable recovery seam is not a physical restart. Qt Library calls in staging
coverage are offscreen ownership checks, never native usability acceptance.
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

from .lifecycle_interaction import _payload
from .pipeline_interaction import _contained, _evaluate, _number, load_observation

TRANSACTION_CONTRACTS = {
    "lifecycle.quit_restart_recovery": (
        "headless_production_pipeline",
        "durable-orphan-recovery-v1",
    ),
    "lifecycle.staging_transaction_transitions": (
        "headless_production_pipeline",
        "owned-staging-transactions-v1",
    ),
    "reliability.batch_failure_report_reset": (
        "unit_static",
        "owned-batch-report-refusal-v1",
    ),
}


def _trace(raw, key, phases, check):
    rows = raw.get(key)
    typed = (
        isinstance(rows, list)
        and len(rows) >= len(phases)
        and all(isinstance(r, dict) for r in rows)
    )
    selected = rows[: len(phases)] if typed else []
    timed = typed and all(_number(r.get("elapsed_seconds")) for r in selected)
    check(
        "during",
        key + "_sequence",
        timed,
        timed
        and [r.get("phase") for r in selected] == phases
        and selected[0]["elapsed_seconds"] >= 0
        and all(
            a["elapsed_seconds"] < b["elapsed_seconds"] for a, b in pairwise(selected)
        ),
        "Actual ordered phase observations use an increasing monotonic timeline",
    )
    return selected if timed else None


def _file(value):
    return (
        isinstance(value, dict)
        and value.get("exists") is True
        and value.get("symlink") is False
        and isinstance(value.get("path"), str)
        and type(value.get("size_bytes")) is int
        and value["size_bytes"] > 0
        and isinstance(value.get("sha256"), str)
        and len(value["sha256"]) == 64
    )


def _batch(raw, root, check):
    job = raw.get("job") or {}
    rows = _trace(
        raw, "observations", ["before_reset", "reset_refused", "worker_returned"], check
    )
    if rows is None:
        return
    before, refusal, after = rows
    check(
        "before",
        "fresh_batch_owner",
        isinstance(job.get("urls"), list) and isinstance(job.get("run_id"), str),
        bool(job.get("run_id"))
        and job.get("urls")
        == [
            "https://www.youtube.com/watch?v=one",
            "https://www.youtube.com/watch?v=two",
        ]
        and all(r.get("run_id") == job.get("run_id") for r in rows),
        "Two submitted URLs and all actual callbacks belong to one batch owner",
    )
    report = before.get("report")
    check(
        "before",
        "prior_report_present",
        isinstance(report, dict),
        _file(report)
        and _contained(report["path"], str(root))
        and Path(report["path"]).name == "batch-url-failures.txt"
        and before.get("processed") == []
        and before.get("events") == [],
        "Private prior report exists before the production batch entrypoint; no media work or old events",
    )
    check(
        "during",
        "report_refused_before_work",
        all(k in refusal for k in ("report", "processed", "events")),
        refusal.get("report") == report
        and refusal.get("processed") == []
        and refusal.get("events") == [],
        "Actual unlink refusal occurred before any processing or error callback",
    )
    events = after.get("events")
    errors = (
        [
            r[1]
            for r in events
            if isinstance(r, list) and len(r) == 2 and r[0] == "error"
        ]
        if isinstance(events, list)
        else []
    )
    check(
        "after",
        "truthful_terminal_report_refusal",
        isinstance(events, list) and "processed" in after and "report" in after,
        after.get("report") == report
        and after.get("processed") == []
        and len(errors) == 1
        and "could not reset the batch failure report" in str(errors[0]).lower()
        and not any(
            r[0] in {"complete", "history_record"}
            for r in events
            if isinstance(r, list) and r
        ),
        "Exactly one understandable reset failure; original report hash unchanged and no media dispatch or false completion",
    )


def _restart(raw, root, check):
    rows = _trace(
        raw,
        "snapshots",
        [
            "orphan_launched",
            "active_before_restart_recovery",
            "production_recovery_returned",
            "after_restart_recovery",
        ],
        check,
    )
    if rows is None:
        return
    launched, before, during, after = rows
    state = before.get("run_state")
    typed = (
        isinstance(state, dict)
        and isinstance(state.get("job"), dict)
        and isinstance(state.get("children"), list)
        and isinstance(state.get("staging_dirs"), list)
    )
    job = state.get("job", {}) if isinstance(state, dict) else {}
    pid, argv = launched.get("child_pid"), launched.get("child_argv")
    authority = (
        typed
        and type(pid) is int
        and pid > 1
        and isinstance(argv, list)
        and len(argv) >= 2
        and all(isinstance(v, str) for v in argv)
    )
    check(
        "before",
        "active_orphan_authority",
        authority,
        authority
        and state.get("state") == "active"
        and job.get("run_id") == "hard-exit-run"
        and before.get("child_pid") == pid
        and before.get("child_command") == " ".join(argv)
        and state["children"] == [{"pid": pid, "argv": argv}]
        and before.get("stage_exists") is True
        and before.get("partial_size", 0) > 0
        and len(state["staging_dirs"]) == 1
        and _contained(state["staging_dirs"][0], job.get("output_dir", ""), staged=True)
        and _contained(argv[-1], state["staging_dirs"][0])
        and _contained(job.get("output_dir", ""), str(root)),
        "Actual orphan process command, durable active job and owned partial staging match before recovery",
    )
    terminal = during.get("run_state")
    check(
        "during",
        "production_cleanup_before_fixture",
        all(
            k in during
            for k in (
                "child_command",
                "stage_exists",
                "staging_root_exists",
                "run_state",
            )
        ),
        during.get("child_command") is None
        and during.get("stage_exists") is False
        and during.get("staging_root_exists") is False
        and isinstance(terminal, dict)
        and terminal.get("state") == "idle",
        "Production recovery retired its orphan and staging before guarded fixture cleanup",
    )
    paused = raw.get("paused_store")
    records = paused.get("recovered_failures") if isinstance(paused, dict) else None
    immutable = (
        "url",
        "urls",
        "output_dir",
        "output_type",
        "quality_label",
        "export_mode",
        "manual_settings",
        "mp3_settings",
        "single_video_only",
        "use_nvenc",
        "embed_thumbnail",
        "write_thumbnail",
        "embed_metadata",
        "write_info_json",
        "tags",
        "run_id",
    )
    present = (
        isinstance(records, list)
        and bool(records)
        and all(isinstance(r, dict) and isinstance(r.get("job"), dict) for r in records)
        and typed
    )
    check(
        "after",
        "paused_saved_selection",
        present,
        present
        and len(records) == 1
        and records[0].get("terminal_status") == "Paused"
        and all(
            k in records[0]["job"] and records[0]["job"][k] == job.get(k)
            for k in immutable
        )
        and paused == terminal,
        "Interrupted job durably reloads as Paused with all saved source, output and encoding selections unchanged",
    )
    queues = paused.get("queued_jobs") if isinstance(paused, dict) else None
    check(
        "after",
        "queue_order_preserved",
        isinstance(queues, list) and typed,
        isinstance(queues, list)
        and queues == state.get("queued_jobs")
        and [j.get("run_id") for j in queues] == ["queued-first", "queued-second"],
        "Both queued jobs retain their exact saved order and selections",
    )
    settings_before, settings_after = (
        raw.get("settings_before"),
        raw.get("settings_after"),
    )
    present = isinstance(settings_before, dict) and isinstance(settings_after, dict)
    check(
        "before",
        "private_settings_saved",
        present,
        present
        and _file(settings_before.get("file"))
        and settings_before["file"].get("mode") == 0o600
        and _contained(settings_before["file"]["path"], str(root))
        and settings_before.get("values")
        == {
            "output_dir": job.get("output_dir"),
            "output_type": "MP3",
            "quality": "720p HD",
        },
        "Actual durable settings baseline is private and bound to this output root",
    )
    check(
        "after",
        "settings_preserved",
        present,
        present and settings_after == settings_before,
        "Durable settings values, path, mode and hash unchanged after recovery/transitions",
    )
    final = raw.get("after") or {}
    check(
        "after",
        "owner_removal_retirement",
        all(isinstance(final.get(k), dict) for k in ("journal", "stage")),
        final.get("journal", {}).get("exists") is False
        and final.get("stage", {}).get("exists") is False
        and after.get("child_pid") == pid
        and after.get("recovery_error") is None
        and after.get("recovery_reaped_child") is True
        and after.get("owned_fixture_child_reaped") is True
        and after.get("child_ownership") == "orphan_launcher",
        "Explicit owner removal retires the journal; fixture cleanup cannot stand in for production process retirement",
    )
    stops = raw.get("fast_stop_store") or {}
    stopped = stops.get("recovered_failures")
    check(
        "after",
        "distinct_fast_stops_durable",
        isinstance(stopped, list),
        isinstance(stopped, list)
        and [r.get("job", {}).get("run_id") for r in stopped]
        == ["queued-first", "queued-second"]
        and all(r.get("terminal_status") == "Stopped" for r in stopped),
        "Restored jobs stopped before metadata arrive remain distinct durable terminal owners",
    )


def _staging(raw, root, check):
    rows = _trace(
        raw,
        "transaction_trace",
        [
            "before_skip",
            "after_skip",
            "after_commit",
            "before_library_removal",
            "after_library_removal",
            "after_owner_cleanup",
        ],
        check,
    )
    refs = raw.get("workers")
    check(
        "before",
        "controlled_qt_owner_seam",
        "renderer" in raw,
        raw.get("renderer") == "qt",
        "Reviewed scope is offscreen Qt Library ownership, not native interaction",
    )
    if rows is None or not isinstance(refs, dict):
        check(
            "during",
            "worker_observation_set",
            False,
            False,
            "Missing controlled worker constituents",
        )
        return
    before, after_skip, after_commit, library_before, library_after, final = rows
    clock = raw.get("clock_origin_monotonic")
    workers = {}
    for label, case in (
        ("skipped", "lifecycle-staging-skip"),
        ("completed", "lifecycle-staging-successor"),
    ):
        worker = _payload(refs.get(label), root.parent, check, "during", label)
        if not isinstance(worker, dict):
            continue
        workers[label] = worker

        def scoped(phase, code, present, valid, detail, *, label=label, worker=worker):
            if label == "skipped" and code == "no_prior_staging":
                first = worker.get("staging_trace", [{}])[0]
                valid = (
                    first.get("root_present") is True
                    and first.get("root_mode") == 0o700
                    and first.get("run_directories") == []
                    and first.get("entries")
                    == [{"path": ".DS_Store", "kind": "file", "size_bytes": 25}]
                )
                detail = "Controlled Finder metadata is the only staging baseline; no active run directory"
            elif label == "skipped" and code == "independent_committed_media":
                valid = (
                    worker.get("outputs") == []
                    and worker.get("media_output_count") == 0
                    and worker.get("error") is None
                    and worker.get("cancel_requested") is False
                )
                detail = "Handled skip commits no media and does not masquerade as whole-job cancellation"
            check(phase, label + "_" + code, present, valid, detail)

        _evaluate(worker, ("MP4", None, None, case), scoped)
    skipped, completed = workers.get("skipped"), workers.get("completed")
    if skipped is None or completed is None:
        return
    output = skipped.get("job", {}).get("output_dir")
    check(
        "before",
        "same_selected_destination",
        bool(output) and isinstance(completed.get("job"), dict),
        output == completed["job"].get("output_dir")
        and skipped["job"].get("run_id") != completed["job"].get("run_id"),
        "Skip and successor share the selected root while retaining distinct transaction owners",
    )
    control = skipped.get("control_trace") or []
    times = {r["phase"]: r["elapsed_seconds"] for r in control}
    request, dispatch, end = (
        times.get("control_requested"),
        times.get("control_dispatched"),
        times.get("worker_finished"),
    )
    events = skipped.get("events")
    terminals = (
        [e for e in events if e.get("kind") == "item_terminal"]
        if isinstance(events, list)
        else []
    )
    present = all(_number(t) for t in (request, dispatch, end)) and isinstance(
        events, list
    )
    terminal = (
        terminals[0].get("payload", {}).get("job", {}) if len(terminals) == 1 else {}
    )
    check(
        "during",
        "owned_active_skip_feedback",
        present,
        present
        and skipped.get("control_request") == "skip_video"
        and request <= dispatch < end
        and any(
            e.get("kind") == "status"
            and "downloading" in str(e.get("payload", "")).lower()
            and e.get("elapsed_seconds", end) < request
            for e in events
        )
        and len(terminals) == 1
        and dispatch <= terminals[0].get("elapsed_seconds", -1) <= end
        and bool(terminal.get("run_id"))
        and terminal.get("run_id") != skipped["job"]["run_id"]
        and terminal.get("origin_run_id") == skipped["job"]["run_id"]
        and terminal.get("execution_run_id") == skipped["job"]["run_id"]
        and terminal.get("retry_of_run_id") is None
        and terminal.get("url") == skipped["job"].get("url")
        and terminal.get("urls") == [skipped["job"].get("url")]
        and terminals[0]
        .get("payload", {})
        .get("info", {})
        .get("vodforge_terminal_run_id")
        == terminal.get("run_id")
        and terminal.get("terminal_status") == "Skipped"
        and terminal.get("terminal_message") == "Video skipped by user",
        "Skip requested during actual downloading and emits exactly one truthful item feedback explicitly linked to its active execution",
    )
    intervals = []
    for label, worker in workers.items():
        ts = {r["phase"]: r["elapsed_seconds"] for r in worker.get("control_trace", [])}
        origin = worker.get("observation_clock_origin_monotonic")
        present = (
            _number(clock)
            and _number(origin)
            and all(_number(ts.get(k)) for k in ("worker_started", "worker_finished"))
        )
        interval = (
            (
                origin + ts["worker_started"] - clock,
                origin + ts["worker_finished"] - clock,
            )
            if present
            else (None, None)
        )
        enclosing = (
            (before, after_skip) if label == "skipped" else (after_skip, after_commit)
        )
        check(
            "during",
            label + "_transaction_clock",
            present,
            present
            and enclosing[0]["elapsed_seconds"]
            <= interval[0]
            < interval[1]
            <= enclosing[1]["elapsed_seconds"],
            "Actual worker interval is enclosed by its transaction filesystem observations",
        )
        intervals.append(interval)
    check(
        "after",
        "idle_roots_retired",
        all(isinstance(r.get("root"), dict) for r in (after_skip, after_commit, final)),
        all(
            r.get("root", {}).get("exists") is False
            and r.get("root", {}).get("path") == str(Path(output) / ".vfstage")
            for r in (after_skip, after_commit, final)
        ),
        "Skip, commit and final owner cleanup each leave the selected staging root absent",
    )
    present = all(
        isinstance(r.get(k), dict)
        for r in (library_before, library_after)
        for k in ("stage", "sentinel", "media")
    ) and all(
        isinstance(r.get("history"), list) for r in (library_before, library_after)
    )
    valid = (
        present
        and library_before["stage"].get("exists") is True
        and library_before["stage"].get("mode") == 0o700
        and library_after["stage"] == library_before["stage"]
        and _contained(library_before["stage"].get("path", ""), output, staged=True)
        and all(
            _file(library_before[k]) and library_after[k] == library_before[k]
            for k in ("sentinel", "media")
        )
        and _contained(
            library_before["sentinel"]["path"], library_before["stage"]["path"]
        )
        and _contained(library_before["media"]["path"], output)
        and len(library_before["history"]) == 1
        and library_before["history"][0].get("vodforge_output_path")
        == library_before["media"]["path"]
        and library_after["history"] == []
    )
    check(
        "after",
        "library_removal_preserves_unrelated_owner",
        present,
        valid,
        "Actual history removal preserves exact saved-media hash and an independently active private staging sentinel",
    )
    check(
        "after",
        "only_owner_retires_active_stage",
        isinstance(final.get("stage"), dict),
        final.get("stage", {}).get("exists") is False
        and final.get("stage", {}).get("path")
        == library_before.get("stage", {}).get("path"),
        "Only the explicit owning cleanup retires that same active staging directory",
    )


def evaluate_transaction(scenario):
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
                "transaction_identity",
                all(k in raw for k in ("scenario_id", "contract")),
                raw.get("scenario_id") == scenario["id"]
                and raw.get("contract") == TRANSACTION_CONTRACTS[scenario["id"]][1],
                "Observed transaction identity matches the enrolled contract",
            )
            root = Path(scenario["raw_result"]).parent
            evaluator = {
                "reliability.batch_failure_report_reset": _batch,
                "lifecycle.quit_restart_recovery": _restart,
                "lifecycle.staging_transaction_transitions": _staging,
            }[scenario["id"]]
            evaluator(raw, root, check)
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            check(
                "during",
                "observation_schema",
                False,
                False,
                "Required typed transaction observation is missing or malformed",
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
        "domain_contract": TRANSACTION_CONTRACTS[scenario["id"]][1],
        "reason": "Independent controlled transaction evidence; physical restart and native usability remain separate.",
    }
