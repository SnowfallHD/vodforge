"""Failure-specific temporal assertions cannot be replaced with any error."""

import hashlib
import json
from types import SimpleNamespace

import pytest
from quality_harness.interaction_coverage import interaction_coverage
from quality_harness.release_gate import evaluate_engineering_result


def observation():
    return {
        "case_id": "reliability-http-404",
        "pipeline_entrypoint": "yt_downloader.app.DownloadWorkerCore._download_worker_single",
        "job": {
            "run_id": "http-run",
            "url": "http://127.0.0.1:12345/status/404",
            "output_type": "MP4",
            "output_dir": "/qa/output",
        },
        "before_worker": {
            "output_files": [],
            "fixture_elapsed_seconds": 0.8,
            "fixture_state": {
                "origin": "http://127.0.0.1:12345",
                "total_requests": 0,
                "responses": [],
            },
        },
        "control_trace": [
            {"phase": phase, "run_id": "http-run", "elapsed_seconds": elapsed}
            for phase, elapsed in [
                ("worker_started", 1.0),
                ("worker_dispatched", 1.1),
                ("worker_finished", 3.0),
            ]
        ],
        "events": [
            {
                "kind": "status",
                "payload": "Video 1 of 1 — analyzing source formats",
                "elapsed_seconds": 1.2,
            }
        ],
        "progress_trace": [],
        "staging_trace": [
            {
                "elapsed_seconds": elapsed,
                "root_present": False,
                "entries": [],
                "final": final,
            }
            for elapsed, final in [(0.9, False), (1.5, False), (3.1, True)]
        ],
        "fixture_response_trace": [
            {"route": "/status/404", "status": 404, "elapsed_seconds": 2.0}
        ],
        "fixture_state_after": {
            "origin": "http://127.0.0.1:12345",
            "requests": {"/status/404": 1},
            "statuses": {"404": 1},
            "total_requests": 1,
            "responses": [{"route": "/status/404", "status": 404}],
        },
        "fixture_after_elapsed_seconds": 3.2,
        "failure_diagnostic": {
            "http_status": 404,
            "stage": "analysis",
            "reason": "source_unavailable",
            "error_type": "HTTPError",
        },
        "error": "_DownloadItemExecutionError: HTTP404",
        "cancel_requested": False,
        "control_request": None,
        "outputs": [],
        "media_output_count": 0,
        "staging_entries_after": [],
        "active_children_before_harness_cleanup": [],
        "harness_emergency_cleanup_used": False,
        "control_observer_stopped": True,
        "control_observer_errors": [],
    }


def scenario(tmp_path, raw):
    path = tmp_path / "raw.json"
    path.write_text(json.dumps(raw))
    return {
        "id": "reliability.http_404_cleanup",
        "status": "passed",
        "evidence_tier": "headless_production_pipeline",
        "raw_result": str(path),
        "raw_result_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def test_http404_domain_reviews_three_actual_phases_and_headless_scope(tmp_path):
    s = scenario(tmp_path, observation())
    s["status"] = "failed"
    result = interaction_coverage(s)
    assert result["status"] == "passed"
    assert result["phase_review"] == dict.fromkeys(
        ["before", "during", "after"], "passed"
    )
    assert result["usability_review"]["applicability"] == "not_applicable"
    checks = evaluate_engineering_result(
        {"profile": "normal", "scenarios": [s]}, profile="normal"
    )
    assert (
        next(c for c in checks if c["id"] == "normal.interaction." + s["id"])["status"]
        == "passed"
    )


FAULTS = [
    "prior_output",
    "prior_request",
    "foreign_owner",
    "external_origin",
    "foreign_loopback_port",
    "wrong_response",
    "foreign_route",
    "late_response",
    "analysis_after_refusal",
    "unexpected_transfer",
    "staging_present",
    "no_inflight_inventory",
    "late_baseline",
    "early_final_inventory",
    "wrong_response_count",
    "unrelated_error",
    "wrong_http_diagnostic",
    "wrong_failure_phase",
    "cancelled",
    "committed_media",
    "retained_child",
    "emergency_cleanup",
    "observer_failure",
]


def mutate(raw, fault):
    if fault == "prior_output":
        raw["before_worker"]["output_files"] = ["old.mp4"]
    elif fault == "prior_request":
        raw["before_worker"]["fixture_state"]["total_requests"] = 1
    elif fault == "foreign_owner":
        raw["control_trace"][1]["run_id"] = "other"
    elif fault == "external_origin":
        raw["job"]["url"] = "https://example.test/status/404"
    elif fault == "foreign_loopback_port":
        raw["job"]["url"] = "http://127.0.0.1:54321/status/404"
    elif fault == "wrong_response":
        raw["fixture_response_trace"][0]["status"] = 500
    elif fault == "foreign_route":
        raw["fixture_response_trace"][0]["route"] = "/other"
    elif fault == "late_response":
        raw["fixture_response_trace"][0]["elapsed_seconds"] = (
            raw["control_trace"][-1]["elapsed_seconds"] + 1
        )
    elif fault == "analysis_after_refusal":
        next(e for e in raw["events"] if e["kind"] == "status")["elapsed_seconds"] = (
            raw["fixture_response_trace"][0]["elapsed_seconds"] + 1
        )
    elif fault == "unexpected_transfer":
        raw["progress_trace"] = [{"downloaded_bytes": 1024}]
    elif fault == "staging_present":
        raw["staging_trace"][1]["root_present"] = True
    elif fault == "no_inflight_inventory":
        raw["staging_trace"] = [raw["staging_trace"][0], raw["staging_trace"][-1]]
    elif fault == "late_baseline":
        raw["before_worker"]["fixture_elapsed_seconds"] = (
            raw["control_trace"][0]["elapsed_seconds"] + 1
        )
    elif fault == "early_final_inventory":
        raw["staging_trace"][-1]["elapsed_seconds"] = (
            raw["control_trace"][-1]["elapsed_seconds"] - 0.1
        )
    elif fault == "wrong_response_count":
        raw["fixture_state_after"]["total_requests"] = 99
    elif fault == "unrelated_error":
        raw["error"] = "ValueError: unrelated exception"
    elif fault == "wrong_http_diagnostic":
        raw["failure_diagnostic"]["http_status"] = 503
    elif fault == "wrong_failure_phase":
        raw["failure_diagnostic"]["stage"] = "transcode"
    elif fault == "cancelled":
        raw["cancel_requested"] = True
    elif fault == "committed_media":
        raw["outputs"] = [{"path": "/qa/output/media.mp4"}]
        raw["media_output_count"] = 1
    elif fault == "retained_child":
        raw["active_children_before_harness_cleanup"] = [{"pid": 42, "alive": True}]
    elif fault == "emergency_cleanup":
        raw["harness_emergency_cleanup_used"] = True
    else:
        raw["control_observer_errors"] = ["observer crashed"]


@pytest.mark.parametrize("fault", FAULTS)
def test_http404_faults_fail_despite_functional_pass(tmp_path, fault):
    raw = observation()
    mutate(raw, fault)
    assert interaction_coverage(scenario(tmp_path, raw))["status"] == "failed"


MISSING = [
    "before_worker",
    "control_trace",
    "events",
    "progress_trace",
    "staging_trace",
    "fixture_response_trace",
    "fixture_state_after",
    "failure_diagnostic",
    "outputs",
    "active_children_before_harness_cleanup",
]


@pytest.mark.parametrize(
    "missing", MISSING + ["worker_dispatch", "fixture_baseline", "fixture_origin"]
)
def test_missing_http404_phase_observations_are_unproven(tmp_path, missing):
    raw = observation()
    if missing == "worker_dispatch":
        raw["control_trace"].pop(1)
    elif missing == "fixture_baseline":
        del raw["before_worker"]["fixture_state"]
    elif missing == "fixture_origin":
        del raw["before_worker"]["fixture_state"]["origin"]
        del raw["fixture_state_after"]["origin"]
    else:
        del raw[missing]
    assert interaction_coverage(scenario(tmp_path, raw))["status"] == "unproven"


def test_fixture_state_retains_timed_route_and_independent_snapshots(monkeypatch):
    from quality_harness import fault_server

    state = fault_server.FaultState()
    before = state.snapshot()
    monkeypatch.setattr(fault_server.time, "monotonic", lambda: 12.345678)
    state.record_request("/status/404")
    state.record_status(404, "/status/404")
    after = state.snapshot()
    assert before["responses"] == [] and before["total_requests"] == 0
    assert after["responses"] == [
        {"observed_at_monotonic": 12.345678, "route": "/status/404", "status": 404}
    ]
    after["responses"][0]["status"] = 500
    assert state.snapshot()["responses"][0]["status"] == 404


def test_preflight_refusal_never_records_worker_dispatch(tmp_path, monkeypatch):
    from quality_harness import pipeline

    import yt_downloader.app as production

    worker_called = []
    app = SimpleNamespace(
        _progress_hook=lambda _: None,
        _download_worker_single=lambda *_args, **_kwargs: worker_called.append(True),
        _find_ffprobe=lambda: "/fixture/ffprobe",
        _find_ffmpeg=lambda: None,
        cancel_requested=False,
        skip_video_requested=False,
    )
    monkeypatch.setattr(pipeline, "make_headless_app", lambda _: app)
    monkeypatch.setattr(production, "DIAGNOSTICS_LOG_PATH", tmp_path / "diagnostic.log")
    monkeypatch.setattr(production, "write_diagnostic", lambda *_: None)

    def refuse(_path):
        raise PermissionError("controlled preflight refusal")

    monkeypatch.setattr(production, "validate_output_directory_access", refuse)
    monkeypatch.setattr(
        pipeline,
        "ResourceSampler",
        lambda *_: SimpleNamespace(start=lambda: SimpleNamespace(stop=dict)),
    )
    result = pipeline.HeadlessPipelineRunner(tmp_path).run_job(
        case_id="refused", url="http://127.0.0.1/status/404", output_type="MP4"
    )
    assert not worker_called
    assert "worker_dispatched" not in [r["phase"] for r in result["control_trace"]]
    assert result["error"].startswith("PermissionError:")
