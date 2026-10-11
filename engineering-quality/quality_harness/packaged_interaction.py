"""Re-evaluate an exact packaged journey from bound native observations.

Pass flags and accumulated test counts are never temporal or UX evidence.
Contextual UX review remains required and binds each dimension to native frames.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .pipeline_interaction import _number, load_observation
from .receipt_composition import read_bound

SID = "packaged_app_e2e.full_journey"
DIMENSIONS = (
    "orientation_navigation",
    "action_hierarchy",
    "progressive_disclosure",
    "visual_hierarchy",
    "sparse_busy_content",
    "feedback",
    "accessibility",
)


def _sha(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing regular evidence file")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def contextual_review(raw, trace_review):
    review = raw.get("contextual_usability_review")
    dimensions = dict.fromkeys(DIMENSIONS, "unproven")
    if not isinstance(review, dict):
        return {
            "status": "unproven",
            "applicability": "required",
            "reason": "No exact-journey contextual reviewer/frame mapping supplied",
            "dimensions": dimensions,
        }
    frames = {
        r["event"]: r
        for r in trace_review.get("screenshot_receipts", [])
        if r.get("valid")
    }
    rows = review.get("dimensions", {})
    reviewer = review.get("reviewer")
    for name in DIMENSIONS:
        row = rows.get(name) if isinstance(rows, dict) else None
        if not isinstance(row, dict):
            continue
        refs = row.get("frames")
        actual = (
            bool(refs)
            and isinstance(refs, list)
            and all(
                isinstance(ref, dict)
                and ref.get("event") in frames
                and ref.get("sha256") == frames[ref["event"]].get("sha256")
                for ref in refs
            )
        )
        complete = (
            isinstance(reviewer, str)
            and bool(reviewer.strip())
            and all(
                isinstance(row.get(k), str) and len(row[k].strip()) >= 12
                for k in ("observed", "expected", "assessment")
            )
        )
        dimensions[name] = (
            "passed"
            if complete and actual and row.get("outcome") == "passed"
            else "failed"
            if row.get("outcome") == "failed" or (refs and not actual)
            else "unproven"
        )
    states = dimensions.values()
    return {
        "status": "failed"
        if "failed" in states
        else "passed"
        if all(s == "passed" for s in states)
        else "unproven",
        "applicability": "required",
        "dimensions": dimensions,
        "reviewer": reviewer,
        "reason": "Seven contextual dimensions independently bound to the exact attested native journey frames",
    }


def _review_payload(scenario, raw):
    if "contextual_review_ref" not in scenario:
        return raw or {}
    try:
        review = read_bound(scenario["contextual_review_ref"])
        if (
            review.get("raw_result_sha256") != scenario.get("raw_result_sha256")
            or review.get("session_nonce") != raw["process_provenance"]["session_nonce"]
            or review.get("candidate_id") != raw["candidate_binding"]["candidate_id"]
        ):
            raise ValueError("Contextual review belongs to another journey")
        return {**raw, "contextual_usability_review": review["review"]}
    except (KeyError, TypeError, ValueError, OSError):
        return {}


def evaluate_packaged_interaction(scenario):
    from .e2e_provenance import bundle_tree_receipt
    from .packaged_e2e import (
        _parse_observed_at,
        _validate_driver_trace,
        pipeline_stage_receipts,
    )

    raw, reason = load_observation(scenario)
    assertions = []
    trace_review = {}

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
        for phase in ("before", "during", "after"):
            check(phase, "original_receipt_binding", False, False, reason)
    else:
        try:
            root = Path(scenario["raw_result"]).parent
            candidate = read_bound(raw.get("candidate_receipt_ref"))
            binding = raw.get("candidate_binding", {})
            artifact = raw.get("artifact_receipt", {})
            check(
                "before",
                "exact_candidate_admission",
                bool(candidate),
                isinstance(candidate.get("candidate_id"), str)
                and bool(candidate["candidate_id"])
                and re.fullmatch("[0-9a-f]{64}", str(binding.get("archive_sha256")))
                is not None
                and re.fullmatch("[0-9a-f]{64}", str(binding.get("bundle_tree_sha256")))
                is not None
                and binding.get("candidate_id") == candidate.get("candidate_id")
                and binding.get("archive_sha256")
                == candidate.get("immutable_archive", {}).get("sha256")
                and binding.get("bundle_tree_sha256")
                == candidate.get("artifact", {}).get("bundle_tree", {}).get("sha256")
                == artifact.get("bundle_tree", {}).get("sha256"),
                "Original immutable candidate receipt agrees with admitted archive and full bundle tree",
            )
            check(
                "before",
                "immutable_archive_bytes",
                "immutable_archive" in candidate,
                _sha(candidate["immutable_archive"]["path"])
                == binding.get("archive_sha256"),
                "Retained archive bytes match the original frozen candidate",
            )
            check(
                "after",
                "complete_bundle_bytes",
                "artifact" in artifact,
                bundle_tree_receipt(Path(artifact["artifact"]))["sha256"]
                == binding.get("bundle_tree_sha256"),
                "Entire retained bundle tree still matches the admitted immutable candidate",
            )
            refs = raw.get("pipeline_observation_refs")
            logs = {"diagnostics": [], "activity": []}
            if isinstance(refs, list):
                for ref in refs:
                    path = Path(ref["path"])
                    if ref.get("kind") not in logs or _sha(path) != ref.get("sha256"):
                        raise ValueError("Changed or malformed pipeline observation")
                    logs[ref["kind"]].append(
                        path.read_text(encoding="utf-8", errors="replace")
                    )
            stages = pipeline_stage_receipts(
                "\n".join(logs["diagnostics"]), "\n".join(logs["activity"])
            )
            check(
                "during",
                "pipeline_stage_observations",
                isinstance(refs, list) and bool(refs),
                all(stages.values()),
                "Recomputed download/transcode/probe/commit evidence from original hash-bound logs",
            )
            start, finish = (
                _parse_observed_at(raw.get(k)) for k in ("started_at", "completed_at")
            )
            event_times = [
                _parse_observed_at(e.get("observed_at"))
                for e in raw.get("driver_trace", {}).get("events", [])
            ]
            check(
                "during",
                "session_time_bounds",
                start is not None and finish is not None,
                start is not None
                and finish is not None
                and start < finish
                and bool(event_times)
                and all(t is not None and start <= t <= finish for t in event_times),
                "Native events occurred within the actual admission/completion interval",
            )
            provenance = raw.get("process_provenance", {})
            launches = raw.get("launches")
            nonce = provenance.get("session_nonce")
            check(
                "before",
                "isolated_launch_inventory",
                isinstance(launches, list) and isinstance(nonce, str),
                bool(launches)
                and len(nonce) >= 12
                and provenance.get("preexisting_processes") == []
                and len({x.get("launch_id") for x in launches}) == len(launches),
                "No preexisting app process; each original launch has one isolated session identity",
            )
            profile = raw.get("scenario", {}).get("metrics", {}).get("e2e_profile")
            check(
                "during",
                "supported_journey_profile",
                profile is not None,
                profile in {"smoke", "deep", "telemetry"},
                "Only maintained complete journey profiles are accepted",
            )
            if (
                profile in {"smoke", "deep", "telemetry"}
                and isinstance(launches, list)
                and isinstance(nonce, str)
            ):
                trace_review = _validate_driver_trace(
                    raw.get("driver_trace", {}),
                    profile=profile,
                    session_dir=root,
                    session_nonce=nonce,
                    launches=launches,
                )
                check(
                    "during",
                    "native_event_order_and_ownership",
                    True,
                    trace_review.get("valid") is True,
                    "Fresh independent validation of every ordered native event, timestamp, screenshot and owned launch",
                )
                for frame in trace_review.get("screenshot_receipts", []):
                    if frame.get("valid"):
                        from PIL import Image

                        with Image.open(frame["path"]) as image:
                            valid = image.width > 0 and image.height > 0
                            image.verify()
                        check(
                            "during",
                            "frame_" + frame["event"],
                            True,
                            valid,
                            "Referenced native frame decodes as a real image",
                        )
            for launch in launches or []:
                valid = (
                    launch.get("executable_sha256") == artifact.get("executable_sha256")
                    and launch.get("bundle_tree_sha256")
                    == artifact.get("bundle_tree", {}).get("sha256")
                    and _number(launch.get("create_time"))
                    and type(launch.get("pid")) is int
                    and launch["pid"] > 0
                    and launch.get("returncode") == 0
                    and not launch.get("timed_out")
                    and launch.get("group_survivors_after_exit") == []
                )
                check(
                    "after",
                    "launch_" + str(launch.get("launch_sequence")),
                    True,
                    valid,
                    "Admitted exact executable/tree returned normally with no surviving owned child",
                )
            check(
                "after",
                "final_owned_cleanup",
                "surviving_owned_processes" in provenance,
                provenance.get("surviving_owned_processes") == []
                and all(
                    x.get("verified_owned") is True and x.get("survivors_after") == []
                    for x in provenance.get("cleanup_receipts", [])
                ),
                "Original owned-process cleanup records contain no survivors",
            )
            integrity = raw.get("artifact_integrity", {})
            expected_tree = artifact.get("bundle_tree", {}).get("sha256")
            check(
                "after",
                "immutable_bundle_tree",
                bool(integrity),
                expected_tree is not None
                and integrity.get("before_bundle_tree_sha256")
                == expected_tree
                == integrity.get("after_bundle_tree_sha256"),
                "Separately observed before/after complete bundle identities agree",
            )
            critical = integrity.get("critical_files", {})
            check(
                "after",
                "critical_executables",
                isinstance(critical, dict),
                bool(critical)
                and all(
                    _sha(v["path"])
                    == v.get("expected_sha256")
                    == v.get("observed_sha256")
                    for v in critical.values()
                ),
                "Actual retained critical executable bytes still match both observations",
            )
            probes = raw.get("media_probes")
            check(
                "after",
                "committed_media_inventory",
                isinstance(probes, list),
                bool(probes),
                "At least one committed output has independent probe evidence",
            )
            for probe in probes or []:
                command = probe.get("ffprobe_command", {})
                parsed = json.loads(command.get("stdout", "{}"))
                expected_argv = [
                    str(probe.get("ffprobe_executable")),
                    "-v",
                    "error",
                    "-print_format",
                    "json",
                    "-show_entries",
                    "format=format_name,size,duration:format_tags:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,bit_rate,pix_fmt,profile,sample_rate,channels:stream_disposition",
                    str(probe.get("path")),
                ]
                valid = (
                    command.get("command") == expected_argv
                    and probe.get("ffprobe_executable")
                    == artifact.get("bundled_ffprobe", {}).get("path")
                    and command.get("returncode") == 0
                    and command.get("timed_out") is False
                    and command.get("unavailable") is False
                    and parsed == probe.get("ffprobe")
                    and isinstance(parsed.get("format"), dict)
                    and bool(parsed.get("streams"))
                    and _sha(probe["path"]) == probe.get("sha256")
                    and Path(probe["path"]).stat().st_size == probe.get("size_bytes")
                    and _sha(probe["ffprobe_executable"])
                    == probe.get("ffprobe_sha256")
                    == artifact.get("bundled_ffprobe", {}).get("sha256")
                    and command.get("command", [])[-1] == probe.get("path")
                )
                check(
                    "after",
                    "media_" + str(probe.get("sha256")),
                    True,
                    valid,
                    "Unchanged output bytes agree with the recorded bundled-ffprobe process and decoded stream payload",
                )
            history = raw.get("history_persistence", {})
            baseline = history.get("pre_restart_snapshot", {})
            check(
                "after",
                "persistent_history_bytes",
                "history_path" in history,
                _sha(history["history_path"]) == baseline.get("history_sha256"),
                "Actual retained history bytes match the before-restart snapshot",
            )
            baseline_media = {m["path"]: m["sha256"] for m in baseline.get("media", [])}
            check(
                "after",
                "persistent_media_bytes",
                "media" in baseline,
                bool(baseline_media)
                and baseline_media == {m["path"]: m["sha256"] for m in probes or []},
                "All committed media identities are stable across the actual restart",
            )
            output = provenance.get("isolated_state_paths", {}).get("output")
            check(
                "after",
                "staging_cleanup",
                isinstance(output, str),
                isinstance(output, str)
                and Path(output).is_dir()
                and not any(".vfstage" in p.parts for p in Path(output).rglob("*")),
                "Owned output tree contains no surviving staging transaction",
            )
        except (KeyError, TypeError, ValueError, AttributeError, IndexError, OSError):
            check(
                "after",
                "original_observation_schema",
                False,
                False,
                "Missing, changed or malformed original constituent; no success inferred",
            )
    phases = {}
    for phase in ("before", "during", "after"):
        states = [a["status"] for a in assertions if a["phase"] == phase]
        phases[phase] = (
            "failed"
            if "failed" in states
            else "unproven"
            if not states or "unproven" in states
            else "passed"
        )
    status = (
        "failed"
        if "failed" in phases.values()
        else "unproven"
        if "unproven" in phases.values()
        else "passed"
    )
    return {
        "status": status,
        "scenario_id": SID,
        "domain_contract": "exact-native-packaged-journey-v1",
        "required_phases": list(phases),
        "phase_review": phases,
        "assertion_mapping": assertions,
        "usability_review": contextual_review(
            _review_payload(scenario, raw), trace_review
        ),
        "reason": "Original admission, exact native event stream and unchanged output/restart/cleanup evidence; contextual review remains separately required",
    }
