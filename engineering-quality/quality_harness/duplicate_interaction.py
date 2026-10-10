"""Independent real-worker duplicate namespace, reuse and sidecar transitions."""

from __future__ import annotations

import copy
from itertools import pairwise
from pathlib import Path

from .lifecycle_interaction import _payload
from .pipeline_interaction import _contained, _evaluate, _number, load_observation
from .transaction_interaction import _file

DUPLICATE_CONTRACTS = {
    "reliability.duplicate_artifact_transitions": "owned-duplicate-reuse-v1"
}
CASES = [
    "duplicate-artifact-first",
    "duplicate-artifact-reuse",
    "variant-mp4-360",
    "variant-mp4-720",
    "variant-mp4-repeat",
    "variant-mp3-128",
    "variant-mp3-192",
    "variant-mp3-repeat",
    *[
        f"original-{codec}-{phase}"
        for codec in ["aac", "opus"]
        for phase in ["first", "repeat", "sidecar-repair"]
    ],
]
REUSED = {
    "duplicate-artifact-reuse",
    "variant-mp4-repeat",
    "variant-mp3-repeat",
    *[
        f"original-{c}-{p}"
        for c in ["aac", "opus"]
        for p in ["repeat", "sidecar-repair"]
    ],
}
MEDIA = {".mp4", ".mp3", ".m4a", ".opus"}


def history_path(info):
    return (
        info.get("vodforge_encoding_summary", {})
        .get("output", {})
        .get("Output file path")
    )


def _review(raw, root, check):
    rows = raw.get("rows")
    clock = raw.get("clock_origin_monotonic")
    typed = isinstance(rows, list) and all(isinstance(r, dict) for r in rows)
    timed = (
        typed
        and _number(clock)
        and all(_number(r.get("elapsed_seconds")) for r in rows)
    )
    check(
        "during",
        "ordered_transition_observations",
        timed,
        timed
        and len(rows) == 46
        and rows[0]["elapsed_seconds"] >= 0
        and all(a["elapsed_seconds"] < b["elapsed_seconds"] for a, b in pairwise(rows)),
        "All actual pre/post worker, sidecar and history observations are strictly ordered on one clock",
    )
    if not typed:
        return
    entered = [r for r in rows if r.get("phase") == "worker_entered"]
    returned = [r for r in rows if r.get("phase") == "worker_returned"]
    check(
        "before",
        "complete_worker_matrix",
        True,
        [r.get("case_id") for r in entered] == CASES
        and [r.get("case_id") for r in returned] == CASES,
        "All fourteen expected fresh/reuse/repair workers are bound in original order",
    )
    if len(entered) != 14 or len(returned) != 14:
        return
    chosen = {}
    owners = []
    for case, before, after in zip(CASES, entered, returned, strict=True):
        worker = _payload(after.get("worker"), root.parent, check, "during", case)
        if not isinstance(worker, dict):
            continue
        job = worker.get("job", {})
        output = job.get("output_dir", "")
        original = case.startswith("original")
        reused = case in REUSED
        kind = "ORIGINAL AUDIO" if original else "MP3" if "mp3" in case else "MP4"
        expected_quality = "720p" if case == "variant-mp4-720" else "360p"
        expected_bitrate = 192 if case == "variant-mp3-192" else 128
        check(
            "before",
            case + "_selected_intent",
            "quality_label" in job and "url" in job,
            job.get("quality_label") == expected_quality
            and (
                not case.startswith("variant-mp3")
                or job.get("requested_mp3_bitrate_kbps") == expected_bitrate
            )
            and (not original or job.get("embed_metadata") is False),
            "Requested ceiling/bitrate and Original metadata policy match the declared variant",
        )
        events = worker.get("events", [])
        history = [
            e.get("payload") for e in events if e.get("kind") == "history_record"
        ]
        selected = (
            history_path(history[0].get("info", {})) if len(history) == 1 else None
        )
        outputs = worker.get("outputs", [])
        media = [f for f in outputs if f.get("path") == selected]
        selected_typed = len(media) == 1 and isinstance(selected, str)
        files_before = {f.get("path"): f for f in before.get("files", []) if _file(f)}
        files_after = {f.get("path"): f for f in after.get("files", []) if _file(f)}
        check(
            "before",
            case + "_inventory_authority",
            isinstance(before.get("files"), list),
            before.get("output_dir") == after.get("output_dir") == output
            and _contained(output, str(root.parent))
            and set(files_before)
            == set(worker.get("before_worker", {}).get("output_files", []))
            and len(files_before) == len(before["files"])
            and all(_contained(p, output) for p in files_before),
            "Exact selected root and independent pre-worker file inventory agree",
        )
        control = worker.get("control_trace", [])
        times = {r.get("phase"): r.get("elapsed_seconds") for r in control}
        origin = worker.get("observation_clock_origin_monotonic")
        bounded = _number(origin) and all(
            _number(times.get(k)) for k in ["worker_started", "worker_finished"]
        )
        check(
            "during",
            case + "_observed_worker_window",
            bounded and timed,
            bounded
            and timed
            and before["elapsed_seconds"]
            <= origin + times["worker_started"] - clock
            < origin + times["worker_finished"] - clock
            <= after["elapsed_seconds"],
            "Actual worker interval fits the corresponding filesystem entry/return observations",
        )

        def scoped(
            phase,
            code,
            present,
            valid,
            detail,
            *,
            case=case,
            worker=worker,
            before=before,
            after=after,
            media=media,
            selected=selected,
            original=original,
            reused=reused,
        ):
            if code == "empty_destination":
                valid = worker.get("before_worker", {}).get("output_files") == [
                    f["path"] for f in before.get("files", [])
                ]
                detail = "Existing files match the observed reuse/variant baseline rather than requiring an empty shared root"
            elif reused and code in {
                "private_staging_observed",
                "transfer_destination_owned",
            }:
                valid = worker.get("progress_trace") == [] and all(
                    r.get("root_present") is False and r.get("entries") == []
                    for r in worker.get("staging_trace", [])
                )
                detail = "Reuse has no media transfer or staging transaction; ordinary new exports require both"
            elif original and code == "independent_committed_media":
                streams = (
                    media[0].get("ffprobe", {}).get("streams", [])
                    if len(media) == 1
                    else []
                )
                audio = [r for r in streams if r.get("codec_type") == "audio"]
                video = [
                    r
                    for r in streams
                    if r.get("codec_type") == "video"
                    and not r.get("disposition", {}).get("attached_pic")
                ]
                valid = (
                    len(media) == 1
                    and media[0].get("readable") is True
                    and media[0].get("size_bytes", 0) > 0
                    and len(media[0].get("sha256", "")) == 64
                    and _contained(selected, worker["job"]["output_dir"])
                    and worker.get("error") is None
                    and worker.get("cancel_requested") is False
                    and len(audio) == 1
                    and audio[0].get("codec_name")
                    == ("aac" if "-aac-" in case else "opus")
                    and not video
                )
                detail = "Independently probed selected Original audio has the expected AAC/Opus codec and no video stream"
            check(phase, case + "_" + code, present, valid, detail)

        projected = copy.deepcopy(worker)
        projected["outputs"] = media
        _evaluate(projected, (kind, None, None, case), scoped)
        check(
            "after",
            case + "_bound_history_and_bytes",
            selected_typed,
            selected_typed
            and len(history) == 1
            and history[0].get("job", {}).get("run_id") == job.get("run_id")
            and history[0].get("output_dir") == str(Path(selected).parent)
            and _contained(history[0].get("output_dir", ""), output)
            and selected in files_after
            and files_after[selected]["sha256"] == media[0].get("sha256")
            and all(
                files_after.get(p, {}).get("sha256") == f.get("sha256")
                for p, f in files_before.items()
                if Path(p).suffix in MEDIA
            ),
            "One same-run history publication points to the selected probe/hash; all earlier media bytes remain unchanged",
        )
        logs = [
            e
            for e in events
            if e.get("kind") == "job_log"
            and "Already downloaded and valid — reused existing file."
            in str(e.get("payload", {}).get("line", ""))
        ]
        check(
            "after",
            case + "_reuse_or_fresh",
            isinstance(worker.get("progress_trace"), list),
            len(logs) == (1 if reused else 0)
            and (
                selected in files_before
                and files_before[selected]["sha256"] == media[0].get("sha256")
                if reused and selected_typed
                else selected not in files_before
                if not reused
                else False
            ),
            "Reuse publishes once without replacement; distinct intent creates a new physical selected file",
        )
        if original or case in {"duplicate-artifact-first", "duplicate-artifact-reuse"}:
            sidecars = {
                Path(p).name
                for p in files_after
                if selected and Path(p).parent == Path(selected).parent
            }
            check(
                "after",
                case + "_sidecars",
                selected_typed,
                "metadata.json" in sidecars
                and (original or "thumbnail.jpeg" in sidecars),
                "Metadata and requested thumbnail sidecars exist after fresh/reuse/repair",
            )
        if case == "duplicate-artifact-reuse" or case.endswith("sidecar-repair"):
            names = {
                Path(p).name
                for p in files_before
                if selected and Path(p).parent == Path(selected).parent
            }
            check(
                "before",
                case + "_sidecar_absence",
                selected_typed,
                "metadata.json" not in names
                and (original or "thumbnail.jpeg" not in names),
                "Requested sidecars are actually absent before the repair invocation",
            )
        if selected_typed:
            chosen[case] = media[0]
        owners.append(job.get("run_id"))
    check(
        "after",
        "distinct_execution_owners",
        len(owners) == 14,
        len(set(owners)) == 14 and all(owners),
        "All fourteen executions retain distinct run identities",
    )

    def same(a, b):
        return (
            a in chosen
            and b in chosen
            and chosen[a]["path"] == chosen[b]["path"]
            and chosen[a]["sha256"] == chosen[b]["sha256"]
        )

    check(
        "after",
        "stable_reuse_namespaces",
        len(chosen) == 14,
        all(
            same(a, b)
            for a, b in [
                ("duplicate-artifact-first", "duplicate-artifact-reuse"),
                ("variant-mp4-360", "variant-mp4-repeat"),
                ("variant-mp3-128", "variant-mp3-repeat"),
                *[
                    (f"original-{c}-first", f"original-{c}-{p}")
                    for c in ["aac", "opus"]
                    for p in ["repeat", "sidecar-repair"]
                ],
            ]
        ),
        "Repeat and sidecar repair keep the exact original selected path and bytes",
    )
    separated = [
        "variant-mp4-360",
        "variant-mp4-720",
        "variant-mp3-128",
        "variant-mp3-192",
    ]
    check(
        "after",
        "distinct_intent_namespaces",
        all(k in chosen for k in separated),
        len({Path(chosen[k]["path"]).parent for k in separated if k in chosen}) == 4,
        "MP4 ceilings and MP3 bitrates remain four distinct physical namespaces",
    )
    histories = [r for r in rows if r.get("phase") == "history_updated"]
    durable = [r for r in rows if r.get("phase") == "history_reloaded"]
    check(
        "after",
        "observed_variant_history",
        len(histories) == 6,
        len(histories) == 6
        and [len(r.get("history", [])) for r in histories] == [1, 2, 2, 3, 4, 4]
        and {history_path(x) for x in histories[-1].get("history", [])}
        == {chosen[k]["path"] for k in separated if k in chosen},
        "Actual variant history transitions merge repeats and retain each distinct physical output",
    )
    check(
        "after",
        "durable_original_history",
        len(durable) == 6,
        len(durable) == 6
        and all(
            _file(r.get("durable_file"))
            and history_path(r.get("history", [{}])[0])
            == chosen.get(r.get("case_id"), {}).get("path")
            for r in durable
        )
        and [len(r.get("history", [])) for r in durable] == [1, 1, 1, 2, 2, 2],
        "Actual save/reload retains Original audio owners without creating duplicate rows",
    )
    distinct = next((r for r in rows if r.get("phase") == "distinct_history_paths"), {})
    merged = next(
        (r for r in rows if r.get("phase") == "same_history_path_refreshed"), {}
    )
    missing = next(
        (r for r in rows if r.get("phase") == "exact_history_path_missing"), {}
    )
    check(
        "after",
        "exact_missing_identity",
        all(r for r in [distinct, merged, missing]),
        len(distinct.get("history", [])) == 2
        and len(merged.get("history", [])) == 2
        and merged["history"][0].get("title") == "Primary refreshed"
        and missing.get("exact_state") == "missing"
        and missing.get("primary_exists") is False
        and missing.get("sibling_exists") is True
        and missing.get("primary_path") != missing.get("sibling_path"),
        "Same physical identity refreshes in place, while a present sibling cannot mask an exact missing file",
    )


def evaluate_duplicate(scenario):
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
        for phase in ["before", "during", "after"]:
            check(phase, "raw_receipt_binding", False, False, reason)
    else:
        try:
            check(
                "before",
                "duplicate_identity",
                "scenario_id" in raw and "contract" in raw,
                raw.get("scenario_id") == scenario["id"]
                and raw.get("contract") == DUPLICATE_CONTRACTS[scenario["id"]],
                "Composite identity matches its explicit real-worker reuse contract",
            )
            _review(raw, Path(scenario["raw_result"]).parent, check)
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            check(
                "during",
                "observation_schema",
                False,
                False,
                "Required duplicate observation missing or malformed",
            )
    phases = {}
    for phase in ["before", "during", "after"]:
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
        "domain_contract": DUPLICATE_CONTRACTS[scenario["id"]],
        "reason": "Real-worker namespace/history/sidecar ownership only; native interactions remain separately required.",
    }
