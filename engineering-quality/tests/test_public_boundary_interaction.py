"""Actual public refusal observations fail closed under bounded mutations."""

import hashlib
import json
from pathlib import Path

import pytest
from quality_harness.interaction_coverage import interaction_coverage

FIXTURE = json.loads(Path(__file__).with_name("public_observation.json").read_text())
CONTROLS = [
    "foreign_raw_hash",
    "foreign_case",
    "foreign_url",
    "foreign_format",
    "foreign_quality",
    "foreign_destination",
    "missing_before",
    "prior_outputs",
    "wrong_entrypoint",
    "missing_run_id",
    "missing_trace",
    "reversed_trace",
    "missing_clock",
    "foreign_owner",
    "duplicate_dispatch",
    "missing_analysis",
    "late_analysis",
    "foreign_job_event",
    "positive_transfer",
    "missing_stage",
    "prior_stage",
    "during_stage",
    "residual_run",
    "missing_final",
    "early_final",
    "missing_diagnostic",
    "missing_error",
    "wrong_error",
    "wrong_stage",
    "unknown_error_type",
    "wrong_reason",
    "invalid_http",
    "cancelled",
    "skipped",
    "control_requested",
    "false_media",
    "false_bytes",
    "committed_output",
    "stage_residue",
    "live_child",
    "missing_child_observation",
    "emergency_cleanup",
    "survivor_after",
    "observer_alive",
    "observer_error",
    "fictitious_success",
]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, a):
    p.write_text(json.dumps(a, indent=2) + "\n")
    return {"path": str(p), "sha256": sha(p)}


def materialize(root):
    root.mkdir(parents=True, exist_ok=True)
    a = json.loads(json.dumps(FIXTURE["raw"]).replace(FIXTURE["old_root"], str(root)))
    ref = save(root / "observation.json", a)
    return dict(
        FIXTURE["scenario"], raw_result=ref["path"], raw_result_sha256=ref["sha256"]
    ), a


def mutate(a, name):
    if name == "foreign_raw_hash":
        pass
    elif name == "foreign_case":
        a["case_id"] = "other"
    elif name == "foreign_url":
        a["job"]["url"] = "https://example.invalid/"
    elif name == "foreign_format":
        a["job"]["output_type"] = "MP3"
    elif name == "foreign_quality":
        a["job"]["quality_label"] = "1080p"
    elif name == "foreign_destination":
        a["job"]["output_dir"] = "/foreign/output"
    elif name == "missing_before":
        del a["before_worker"]
    elif name == "prior_outputs":
        a["before_worker"]["output_files"] = ["prior.mp4"]
    elif name == "wrong_entrypoint":
        a["pipeline_entrypoint"] = "foreign.worker"
    elif name == "missing_run_id":
        del a["job"]["run_id"]
    elif name == "missing_trace":
        del a["control_trace"]
    elif name == "reversed_trace":
        a["control_trace"].reverse()
    elif name == "missing_clock":
        del a["control_trace"][0]["elapsed_seconds"]
    elif name == "foreign_owner":
        a["control_trace"][2]["run_id"] = "other"
    elif name == "duplicate_dispatch":
        a["control_trace"][2]["phase"] = "worker_dispatched"
    elif name == "missing_analysis":
        a["events"] = [v for v in a["events"] if v["kind"] != "status"]
    elif name == "late_analysis":
        next(v for v in a["events"] if v["kind"] == "status")["elapsed_seconds"] = 99
    elif name == "foreign_job_event":
        next(v for v in a["events"] if v["kind"] == "job_log")["payload"]["job"][
            "run_id"
        ] = "other"
    elif name == "positive_transfer":
        a["progress_trace"] = [{"downloaded_bytes": 1}]
    elif name == "missing_stage":
        del a["staging_trace"]
    elif name == "prior_stage":
        a["staging_trace"][0]["entries"] = ["prior"]
    elif name == "during_stage":
        a["staging_trace"][1]["root_present"] = True
    elif name == "residual_run":
        a["staging_trace"][1]["run_directories"] = ["prior"]
    elif name == "missing_final":
        a["staging_trace"][-1]["final"] = False
    elif name == "early_final":
        a["staging_trace"][-1]["elapsed_seconds"] = 0.001
    elif name == "missing_diagnostic":
        del a["failure_diagnostic"]
    elif name == "missing_error":
        del a["error"]
    elif name == "wrong_error":
        a["error"] = "unrelated failure"
    elif name == "wrong_stage":
        a["failure_diagnostic"]["stage"] = "transcode"
    elif name == "unknown_error_type":
        a["failure_diagnostic"]["error_type"] = "ForeignError"
    elif name == "wrong_reason":
        a["failure_diagnostic"]["reason"] = "foreign"
    elif name == "invalid_http":
        a["failure_diagnostic"]["http_status"] = 900
    elif name == "cancelled":
        a["cancel_requested"] = True
    elif name == "skipped":
        a["skip_video_requested"] = True
    elif name == "control_requested":
        a["control_request"] = "pause"
    elif name == "false_media":
        a["media_output_count"] = 1
    elif name == "false_bytes":
        a["output_bytes"] = 1
    elif name == "committed_output":
        a["outputs"] = [{"path": "foreign.mp4"}]
    elif name == "stage_residue":
        a["staging_entries_after"] = ["residue"]
    elif name == "live_child":
        a["active_children_before_harness_cleanup"] = [{"alive": True}]
    elif name == "missing_child_observation":
        del a["active_children_before_harness_cleanup"]
    elif name == "emergency_cleanup":
        a["harness_emergency_cleanup_used"] = True
    elif name == "survivor_after":
        a["active_children_after_harness_cleanup"] = [{"alive": True}]
    elif name == "observer_alive":
        a["control_observer_stopped"] = False
    elif name == "observer_error":
        a["control_observer_errors"] = ["failed"]
    elif name == "fictitious_success":
        a["error"] = None


def test_actual_public_refusal_qualifies(tmp_path):
    s, _ = materialize(tmp_path)
    v = interaction_coverage(s)
    assert v["status"] == "passed", v
    assert v["usability_review"]["status"] == "not_applicable"


@pytest.mark.parametrize("name", CONTROLS)
def test_altered_public_receipt_fails_closed(tmp_path, name):
    s, a = materialize(tmp_path)
    mutate(a, name)
    ref = save(tmp_path / "mutation.json", a)
    s.update(
        raw_result=ref["path"],
        raw_result_sha256="0" * 64 if name == "foreign_raw_hash" else ref["sha256"],
    )
    assert interaction_coverage(s)["status"] in {"failed", "unproven"}
