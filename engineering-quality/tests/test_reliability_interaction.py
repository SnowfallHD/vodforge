"""Causal failures and missing observations cannot be masked by functional pass."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from quality_harness.interaction_coverage import interaction_coverage

OBSERVATIONS = json.loads(
    Path(__file__).with_name("reliability_observations.json").read_text()
)
DOMAINS = list(OBSERVATIONS)
COMMON = [
    "prior_output",
    "foreign_case",
    "foreign_owner",
    "retained_child",
    "emergency",
    "observer",
]
FAULTS = [(sid, name, "failed") for sid in DOMAINS for name in COMMON]
FAULTS += [
    (sid, name, "unproven")
    for sid in DOMAINS
    for name in [
        "before_worker",
        "control_trace",
        "progress_trace",
        "staging_trace",
        "active_children_before_harness_cleanup",
    ]
]
NETWORK = [
    "reliability.transient_http_retry",
    "reliability.network_interruption_recovery",
    "reliability.ffmpeg_child_failure",
]
FAULTS += [
    (sid, name, "failed")
    for sid in NETWORK
    for name in [
        "foreign_origin",
        "prior_source_request",
        "late_baseline",
        "late_response",
        "wrong_response_delta",
    ]
]
FAULTS += [
    (sid, name, "unproven")
    for sid in NETWORK
    for name in [
        "fixture_state",
        "fixture_response_trace",
        "fixture_state_after",
        "worker_dispatch",
    ]
]
FAULTS += [
    ("reliability.transient_http_retry", name, "failed")
    for name in [
        "no_503",
        "feedback_foreign_owner",
        "feedback_after_next_request",
        "unbounded_feedback",
        "transfer_before_recovery",
    ]
]
FAULTS += [
    ("reliability.network_interruption_recovery", name, "failed")
    for name in [
        "no_interruption",
        "complete_body",
        "foreign_interruption",
        "late_interruption",
        "no_range_resume",
        "foreign_resume",
        "no_finished_transfer",
    ]
]
FAULTS += [
    (
        "reliability.network_interruption_recovery",
        "fixture_interruption_trace",
        "unproven",
    )
]
FAULTS += [
    ("reliability.unwritable_output_directory", name, "failed")
    for name in [
        "writable",
        "wrong_mode",
        "dispatched_after_refusal",
        "wrong_permission_error",
    ]
]
FAULTS += [("reliability.unwritable_output_directory", "preflight_refused", "unproven")]
FAULTS += [
    ("reliability.malformed_url", name, "failed")
    for name in [
        "valid_url",
        "wrong_input_reason",
        "wrong_input_stage",
        "unexpected_transfer",
    ]
]
FAULTS += [
    ("reliability.ffmpeg_child_failure", name, "failed")
    for name in [
        "no_media_child",
        "foreign_media_child",
        "successful_media_child",
        "escaped_child_input",
        "missing_binary_error",
        "committed_media",
    ]
]
FAULTS += [
    ("reliability.ffmpeg_child_failure", name, "unproven")
    for name in ["child_registration_trace", "dependency_override", "exit_status"]
]


def mutate(raw, name):
    if name == "prior_output":
        raw["before_worker"]["output_files"] = ["old.mp4"]
    elif name == "foreign_case":
        raw["case_id"] = "other"
    elif name == "foreign_owner":
        raw["control_trace"][0]["run_id"] = "other"
    elif name == "retained_child":
        raw["active_children_before_harness_cleanup"] = [{"alive": True}]
    elif name == "emergency":
        raw["harness_emergency_cleanup_used"] = True
    elif name == "observer":
        raw["control_observer_errors"] = ["failed"]
    elif name == "foreign_origin":
        raw["before_worker"]["fixture_state"]["origin"] = "http://127.0.0.1:54321"
    elif name == "prior_source_request":
        from urllib.parse import urlsplit

        raw["before_worker"]["fixture_state"]["requests"][
            urlsplit(raw["job"]["url"]).path
        ] = 1
    elif name == "late_baseline":
        raw["before_worker"]["fixture_elapsed_seconds"] = (
            raw["control_trace"][-1]["elapsed_seconds"] + 1
        )
    elif name == "late_response":
        raw["fixture_response_trace"][0]["elapsed_seconds"] = (
            raw["control_trace"][-1]["elapsed_seconds"] + 1
        )
    elif name == "wrong_response_delta":
        raw["fixture_state_after"]["total_requests"] += 1
    elif name == "worker_dispatch":
        raw["control_trace"] = [
            row for row in raw["control_trace"] if row["phase"] != "worker_dispatched"
        ]
    elif name == "fixture_state":
        del raw["before_worker"][name]
    elif name == "no_503":
        raw["fixture_response_trace"][0]["status"] = 200
    elif name.startswith("feedback") or name == "unbounded_feedback":
        row = next(
            e
            for e in raw["events"]
            if e["kind"] == "job_log" and "retrying attempt" in e["payload"]["line"]
        )
        if name == "feedback_foreign_owner":
            row["payload"]["job"]["run_id"] = "other"
        elif name == "feedback_after_next_request":
            row["elapsed_seconds"] = (
                raw["fixture_response_trace"][1]["elapsed_seconds"] + 0.01
            )
        else:
            row["payload"]["line"] = row["payload"]["line"].replace(
                "attempt 2/6", "attempt 999/999"
            )
    elif name == "transfer_before_recovery":
        raw["progress_trace"][0]["elapsed_seconds"] = raw["fixture_response_trace"][0][
            "elapsed_seconds"
        ]
    elif name in [
        "no_interruption",
        "complete_body",
        "foreign_interruption",
        "late_interruption",
    ]:
        row = raw["fixture_interruption_trace"][0]
        if name == "no_interruption":
            raw["fixture_interruption_trace"] = []
        elif name == "complete_body":
            row["sent_bytes"] = row["advertised_bytes"]
        elif name == "foreign_interruption":
            row["route"] = "/other.ts"
        else:
            row["elapsed_seconds"] = raw["control_trace"][-1]["elapsed_seconds"] + 1
    elif name in ["no_range_resume", "foreign_resume"]:
        row = next(e for e in raw["fixture_response_trace"] if e["status"] == 206)
        row["status" if name == "no_range_resume" else "route"] = (
            200 if name == "no_range_resume" else "/other.ts"
        )
    elif name == "no_finished_transfer":
        raw["progress_trace"] = [
            e for e in raw["progress_trace"] if e["status"] != "finished"
        ]
    elif name == "writable":
        raw["before_worker"]["output_writable"] = True
    elif name == "wrong_mode":
        raw["before_worker"]["output_mode"] = 0o700
    elif name == "dispatched_after_refusal":
        raw["control_trace"].insert(
            -1, dict(raw["control_trace"][-2], phase="worker_dispatched")
        )
    elif name == "wrong_permission_error":
        raw["error"] = "PermissionError: unrelated path"
    elif name == "preflight_refused":
        raw["control_trace"] = [e for e in raw["control_trace"] if e["phase"] != name]
    elif name == "valid_url":
        raw["job"]["url"] = "http://127.0.0.1:12345/page/unicode"
    elif name in ["wrong_input_reason", "wrong_input_stage"]:
        raw["failure_diagnostic"][
            "reason" if name == "wrong_input_reason" else "stage"
        ] = "other"
    elif name == "unexpected_transfer":
        raw["progress_trace"] = [{"status": "downloading", "downloaded_bytes": 1}]
    elif name in [
        "no_media_child",
        "foreign_media_child",
        "successful_media_child",
        "escaped_child_input",
        "exit_status",
    ]:
        rows = [
            e
            for e in raw["child_registration_trace"]
            if "-y" in e["args"] and "-i" in e["args"]
        ]
        if name == "no_media_child":
            raw["child_registration_trace"] = [
                e for e in raw["child_registration_trace"] if e not in rows
            ]
        for row in rows:
            if name == "foreign_media_child":
                row["run_id"] = "other"
            elif name == "successful_media_child":
                row["returncode_after_worker"] = 0
            elif name == "escaped_child_input":
                row["args"][row["args"].index("-i") + 1] = "file:/foreign/media.mp4"
            elif name == "exit_status":
                del row["returncode_after_worker"]
    elif name == "missing_binary_error":
        raw["error"] = (
            "_DownloadItemExecutionError: ERROR: Postprocessing: ffmpeg not found"
        )
    elif name == "committed_media":
        raw["outputs"] = [{"path": "/qa/output/media.mp4"}]
        raw["media_output_count"] = 1
    elif name == "dependency_override":
        del raw["before_worker"][name]
    else:
        del raw[name]


def scenario(tmp_path, sid, raw):
    path = tmp_path / "raw.json"
    path.write_text(json.dumps(raw))
    return {
        "id": sid,
        "status": "passed",
        "evidence_tier": "headless_production_pipeline",
        "raw_result": str(path),
        "raw_result_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


@pytest.mark.parametrize("sid", DOMAINS)
def test_five_reliability_domains_have_independent_temporal_review(tmp_path, sid):
    review = interaction_coverage(scenario(tmp_path, sid, OBSERVATIONS[sid]))
    assert review["status"] == "passed"
    assert review["phase_review"] == dict.fromkeys(
        ["before", "during", "after"], "passed"
    )


@pytest.mark.parametrize("sid,name,expected", FAULTS)
def test_causal_fault_or_absence_is_not_overridden_by_functional_pass(
    tmp_path, sid, name, expected
):
    raw = copy.deepcopy(OBSERVATIONS[sid])
    mutate(raw, name)
    assert interaction_coverage(scenario(tmp_path, sid, raw))["status"] == expected


@pytest.mark.parametrize(
    "fault", [None, "missing_binary_error", "successful_media_child", "no_media_child"]
)
def test_functional_child_failure_requires_actual_ffmpeg_exit(tmp_path, fault):
    from types import SimpleNamespace

    from quality_harness.scenarios import reliability_ffmpeg_failure

    raw = copy.deepcopy(OBSERVATIONS["reliability.ffmpeg_child_failure"])
    if fault:
        mutate(raw, fault)
    raw["job"]["output_dir"] = str(tmp_path / "output")
    runner = SimpleNamespace(run_root=tmp_path, run_job=lambda **kwargs: raw)
    server = SimpleNamespace(
        url=lambda path: "http://127.0.0.1:12345" + path, state=None
    )
    scenario, findings = reliability_ffmpeg_failure(runner, server)
    assert scenario["status"] == ("passed" if fault is None else "failed")
    assert bool(findings) == (fault is not None)
