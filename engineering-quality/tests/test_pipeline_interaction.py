"""Independent observation faults must block reviewed worker coverage."""

import copy
import hashlib
import json

import pytest
from quality_harness.interaction_coverage import interaction_coverage
from quality_harness.release_gate import evaluate_engineering_result


def observation():
    raw = {
        "case_id": "correctness-source-quality-360p",
        "pipeline_entrypoint": "yt_downloader.app.DownloadWorkerCore._download_worker_single",
        "before_worker": {"output_files": []},
        "job": {
            "run_id": "run-one",
            "output_type": "MP4",
            "output_dir": "/qa/output",
            "quality_label": "360p",
            "url": "http://127.0.0.1:12345/page/multi?quality=360p",
        },
        "control_trace": [
            {"phase": "worker_started", "run_id": "run-one", "elapsed_seconds": 1.0},
            {"phase": "worker_finished", "run_id": "run-one", "elapsed_seconds": 4.0},
        ],
        "events": [
            {
                "kind": "status",
                "payload": "Video 1 of 1 — downloading",
                "elapsed_seconds": 2.0,
            }
        ],
        "progress_trace": [
            {
                "status": "downloading",
                "elapsed_seconds": 2.5,
                "downloaded_bytes": 1024,
                "filename": "/qa/output/.vfstage/stage-one/media.mp4",
            }
        ],
        "staging_trace": [
            {
                "elapsed_seconds": 0.9,
                "root_present": False,
                "run_directories": [],
                "entries": [],
                "final": False,
            },
            {
                "elapsed_seconds": 2.0,
                "root_present": True,
                "run_directories": ["stage-one"],
                "entries": [{"path": "stage-one", "kind": "directory"}],
                "final": False,
            },
            {
                "elapsed_seconds": 4.1,
                "root_present": False,
                "run_directories": [],
                "entries": [],
                "final": True,
            },
        ],
        "outputs": [
            {
                "path": "/qa/output/media.mp4",
                "readable": True,
                "size_bytes": 2048,
                "sha256": "a" * 64,
                "ffprobe": {
                    "streams": [
                        {"codec_type": "video", "codec_name": "h264", "height": 360},
                        {"codec_type": "audio", "codec_name": "aac"},
                    ]
                },
            }
        ],
        "media_output_count": 1,
        "error": None,
        "cancel_requested": False,
        "control_request": None,
        "staging_entries_after": [],
        "active_children_before_harness_cleanup": [],
        "harness_emergency_cleanup_used": False,
        "control_observer_stopped": True,
        "control_observer_errors": [],
    }
    formats = [
        {
            "format_id": "hls-1100",
            "height": 360,
            "vcodec": "avc1",
            "acodec": "mp4a",
            "url": "http://127.0.0.1:12345/hls/low.m3u8",
        },
        {
            "format_id": "hls-2100",
            "height": 540,
            "vcodec": "avc1",
            "acodec": "mp4a",
            "url": "http://127.0.0.1:12345/hls/high.m3u8",
        },
    ]
    for phase, elapsed in [("analysis", 1.5), ("download", 3.0), ("commit", 3.9)]:
        event_job = copy.deepcopy(raw["job"])
        event_job["failure_stage"] = phase
        info = copy.deepcopy(formats[0])
        info["formats"] = copy.deepcopy(formats)
        raw["events"].append(
            {
                "kind": "job_metadata",
                "payload": {"job": event_job, "info": info},
                "elapsed_seconds": elapsed,
            }
        )
    raw["events"].append(
        {
            "kind": "status",
            "payload": "Video 1 of 1 — transcoding",
            "elapsed_seconds": 3.1,
        }
    )
    raw["events"].sort(key=lambda event: event["elapsed_seconds"])
    raw["latest_metadata"] = copy.deepcopy(info)
    return raw


def scenario(tmp_path, raw, sid="correctness.source_quality_selection_360p"):
    path = tmp_path / "raw.json"
    path.write_text(json.dumps(raw))
    return {
        "id": sid,
        "status": "passed",
        "evidence_tier": "headless_production_pipeline",
        "raw_result": str(path),
        "raw_result_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def test_real_worker_receipt_enrollment_recomputes_each_phase(tmp_path):
    s = scenario(tmp_path, observation())
    s["status"] = "failed"
    coverage = interaction_coverage(s)
    # Functional status is a separate gate; it is never the temporal oracle.
    assert coverage["status"] == "passed"
    assert coverage["phase_review"] == dict.fromkeys(
        ["before", "during", "after"], "passed"
    )
    assert len(coverage["assertion_mapping"]) >= 8
    assert coverage["usability_review"]["applicability"] == "not_applicable"
    assert "headless" in coverage["usability_review"]["reason"].lower()


@pytest.mark.parametrize(
    "fault",
    [
        "preexisting_output",
        "prior_stage",
        "wrong_run",
        "backward_clock",
        "absent_stage",
        "zero_transfer",
        "outside_destination",
        "traversal",
        "finished_transfer_only",
        "wrong_codec",
        "wrong_height",
        "unreadable_output",
        "uncommitted_output",
        "residue",
        "early_final",
        "retained_child",
        "emergency_cleanup",
        "observer_alive",
        "observer_error",
    ],
)
def test_observation_negative_controls_fail_even_with_endpoint_pass(tmp_path, fault):
    raw = observation()
    if fault == "preexisting_output":
        raw["before_worker"]["output_files"] = ["old.mp4"]
    elif fault == "prior_stage":
        raw["staging_trace"][0]["root_present"] = True
    elif fault == "wrong_run":
        raw["control_trace"][1]["run_id"] = "other"
    elif fault == "backward_clock":
        raw["control_trace"].insert(
            1, {"phase": "other", "run_id": "run-one", "elapsed_seconds": 0.5}
        )
    elif fault == "absent_stage":
        raw["staging_trace"].pop(1)
    elif fault == "zero_transfer":
        raw["progress_trace"][0]["downloaded_bytes"] = 0
    elif fault == "outside_destination":
        raw["progress_trace"][0]["filename"] = "/private/user.mp4"
    elif fault == "traversal":
        raw["progress_trace"][0]["filename"] = "/qa/output/.vfstage/../../user.mp4"
    elif fault == "finished_transfer_only":
        raw["progress_trace"][0]["status"] = "finished"
    elif fault == "wrong_codec":
        raw["outputs"][0]["ffprobe"]["streams"][0]["codec_name"] = "mpeg4"
    elif fault == "wrong_height":
        raw["outputs"][0]["ffprobe"]["streams"][0]["height"] = 1080
    elif fault == "unreadable_output":
        raw["outputs"][0]["readable"] = False
    elif fault == "uncommitted_output":
        raw["outputs"][0]["path"] = "/qa/output/.vfstage/stage-one/media.mp4"
    elif fault == "residue":
        raw["staging_entries_after"] = ["retained.part"]
    elif fault == "early_final":
        raw["staging_trace"][-1]["elapsed_seconds"] = 3.9
    elif fault == "retained_child":
        raw["active_children_before_harness_cleanup"] = [{"pid": 42, "alive": True}]
    elif fault == "emergency_cleanup":
        raw["harness_emergency_cleanup_used"] = True
    elif fault == "observer_alive":
        raw["control_observer_stopped"] = False
    else:
        raw["control_observer_errors"] = ["observer crashed"]
    assert interaction_coverage(scenario(tmp_path, raw))["status"] == "failed"


@pytest.mark.parametrize(
    "missing",
    [
        "case_id",
        "before_worker",
        "control_trace",
        "staging_trace",
        "progress_trace",
        "outputs",
        "active_children_before_harness_cleanup",
    ],
)
def test_missing_observations_are_unproven_not_exempt(tmp_path, missing):
    raw = observation()
    del raw[missing]
    assert interaction_coverage(scenario(tmp_path, raw))["status"] == "unproven"


def test_mutated_or_unbound_raw_receipt_does_not_certify_coverage(tmp_path):
    s = scenario(tmp_path, observation())
    (tmp_path / "raw.json").write_text("{}")
    assert interaction_coverage(s)["status"] == "unproven"
    del s["raw_result_sha256"]
    assert interaction_coverage(s)["status"] == "unproven"


def cancelled_observation():
    raw = observation()
    raw["outputs"] = []
    raw["media_output_count"] = 0
    raw["case_id"] = "reliability-cancel-slow"
    raw["error"] = "_DownloadControlRequestError: Download cancelled by user"
    raw["cancel_requested"] = True
    raw["control_request"] = "cancel"
    raw["control_trace"][1:1] = [
        {"phase": "control_requested", "run_id": "run-one", "elapsed_seconds": 3.0},
        {"phase": "control_dispatched", "run_id": "run-one", "elapsed_seconds": 3.1},
    ]
    return raw


@pytest.mark.parametrize(
    "fault", [None, "before_phase", "after_finish", "wrong_request", "committed_media"]
)
def test_cancellation_requires_actual_active_phase_and_terminal_absence(
    tmp_path, fault
):
    raw = cancelled_observation()
    if fault == "before_phase":
        raw["control_trace"][1]["elapsed_seconds"] = 1.5
    elif fault == "after_finish":
        raw["control_trace"][1]["elapsed_seconds"] = 4.5
    elif fault == "wrong_request":
        raw["control_request"] = "skip_video"
    elif fault == "committed_media":
        raw["outputs"] = copy.deepcopy(observation()["outputs"])
        raw["media_output_count"] = 1
    result = interaction_coverage(
        scenario(tmp_path, raw, "reliability.cancel_during_slow_download")
    )
    assert result["status"] == ("passed" if fault is None else "failed")


@pytest.mark.parametrize(
    "fault",
    ["duplicate_start", "duplicate_finish", "negative_clock", "relative_destination"],
)
def test_worker_authority_cannot_be_ambiguous(tmp_path, fault):
    raw = observation()
    if fault == "duplicate_start":
        raw["control_trace"].insert(0, copy.deepcopy(raw["control_trace"][0]))
    elif fault == "duplicate_finish":
        raw["control_trace"].append(copy.deepcopy(raw["control_trace"][-1]))
    elif fault == "negative_clock":
        raw["control_trace"].insert(
            0, {"phase": "other", "run_id": "run-one", "elapsed_seconds": -1.0}
        )
    else:
        raw["job"]["output_dir"] = "qa/output"
        raw["progress_trace"][0]["filename"] = "qa/output/.vfstage/stage-one/media.mp4"
    assert interaction_coverage(scenario(tmp_path, raw))["status"] == "failed"


def test_release_gate_consumes_reviewed_assertions_instead_of_blanket_unproven(
    tmp_path,
):
    s = scenario(tmp_path, observation())
    checks = evaluate_engineering_result(
        {"profile": "normal", "scenarios": [s]}, profile="normal"
    )
    assert (
        next(c for c in checks if c["id"] == "normal.interaction." + s["id"])["status"]
        == "passed"
    )
    raw = observation()
    raw["active_children_before_harness_cleanup"] = [{"pid": 42, "alive": True}]
    s = scenario(tmp_path, raw)
    checks = evaluate_engineering_result(
        {"profile": "normal", "scenarios": [s]}, profile="normal"
    )
    assert (
        next(c for c in checks if c["id"] == "normal.interaction." + s["id"])["status"]
        == "failed"
    )


def test_staging_observation_keeps_clock_precision(tmp_path, monkeypatch):
    from quality_harness import pipeline

    events = pipeline.TracingQueue()
    events.started = 0
    recorder = pipeline.StagingTraceRecorder(tmp_path, events)
    monkeypatch.setattr(pipeline.time, "monotonic", lambda: 1.000049)
    recorder._snapshot(final=True)
    assert recorder.trace[0]["elapsed_seconds"] == 1.000049


def test_staging_baseline_precedes_asynchronous_monitor(tmp_path, monkeypatch):
    from quality_harness import pipeline

    events = pipeline.TracingQueue()
    recorder = pipeline.StagingTraceRecorder(tmp_path, events)
    monkeypatch.setattr(recorder._thread, "start", lambda: None)
    recorder.start()
    assert len(recorder.trace) == 1
    assert recorder.trace[0]["root_present"] is False
    assert recorder.trace[0]["entries"] == []


def test_foreign_case_receipt_cannot_qualify_same_format_scenario(tmp_path):
    raw = observation()
    raw["case_id"] = "correctness-local-mp4-embedding-disabled"
    assert interaction_coverage(scenario(tmp_path, raw))["status"] == "failed"


def test_cancellation_flag_cannot_disguise_unrelated_terminal_failure(tmp_path):
    raw = cancelled_observation()
    raw["case_id"] = "reliability-cancel-slow"
    raw["error"] = "PermissionError: unrelated output permission failure"
    assert (
        interaction_coverage(
            scenario(tmp_path, raw, "reliability.cancel_during_slow_download")
        )["status"]
        == "failed"
    )


@pytest.mark.parametrize(
    "ceiling, selected_height, selected_format",
    [("360p", 360, "hls-1100"), ("720p", 540, "hls-2100")],
)
def test_source_quality_uses_observed_best_available_source(
    tmp_path, ceiling, selected_height, selected_format
):
    raw = observation()
    raw["case_id"] = "correctness-source-quality-" + ceiling
    raw["job"]["quality_label"] = ceiling
    for event in raw["events"]:
        if event["kind"] == "job_metadata":
            event["payload"]["job"]["quality_label"] = ceiling
            info = event["payload"]["info"]
            chosen = next(
                f for f in info["formats"] if f["format_id"] == selected_format
            )
            info.update(chosen)
    raw["latest_metadata"] = copy.deepcopy(
        [e["payload"]["info"] for e in raw["events"] if e["kind"] == "job_metadata"][-1]
    )
    raw["outputs"][0]["ffprobe"]["streams"][0]["height"] = selected_height
    assert (
        interaction_coverage(
            scenario(tmp_path, raw, "correctness.source_quality_selection_" + ceiling)
        )["status"]
        == "passed"
    )


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_request",
        "foreign_metadata_owner",
        "foreign_metadata_source",
        "late_selection",
        "wrong_selected_height",
        "wrong_selected_format",
        "wrong_selected_resource",
        "missing_offered_tier",
        "wrong_offered_tier",
        "contradictory_latest_metadata",
    ],
)
def test_source_selection_faults_fail_despite_correct_final_resolution(tmp_path, fault):
    raw = observation()
    metadata = [e for e in raw["events"] if e["kind"] == "job_metadata"]
    selected = metadata[1]
    if fault == "wrong_request":
        raw["job"]["quality_label"] = "720p"
    elif fault == "foreign_metadata_owner":
        selected["payload"]["job"]["run_id"] = "foreign-run"
    elif fault == "foreign_metadata_source":
        selected["payload"]["job"]["url"] = "http://127.0.0.1:12345/other"
    elif fault == "late_selection":
        selected["elapsed_seconds"] = 4.5
    elif fault == "wrong_selected_height":
        selected["payload"]["info"]["height"] = 540
    elif fault == "wrong_selected_format":
        selected["payload"]["info"]["format_id"] = "hls-2100"
    elif fault == "wrong_selected_resource":
        selected["payload"]["info"]["url"] = "http://127.0.0.1:12345/hls/other.m3u8"
    elif fault == "missing_offered_tier":
        metadata[0]["payload"]["info"]["formats"].pop()
    elif fault == "wrong_offered_tier":
        metadata[0]["payload"]["info"]["formats"][0]["height"] = 240
    else:
        raw["latest_metadata"]["height"] = 540
    assert raw["outputs"][0]["ffprobe"]["streams"][0]["height"] == 360
    assert interaction_coverage(scenario(tmp_path, raw))["status"] == "failed"


@pytest.mark.parametrize(
    "missing",
    [
        "quality_label",
        "metadata_events",
        "source_formats",
        "selected_metadata",
        "latest_metadata",
    ],
)
def test_source_selection_requires_raw_observations(tmp_path, missing):
    raw = observation()
    if missing == "quality_label":
        del raw["job"]["quality_label"]
    elif missing == "metadata_events":
        raw["events"] = [e for e in raw["events"] if e["kind"] != "job_metadata"]
    elif missing == "source_formats":
        for event in raw["events"]:
            if event["kind"] == "job_metadata":
                del event["payload"]["info"]["formats"]
        del raw["latest_metadata"]["formats"]
    elif missing == "selected_metadata":
        raw["events"] = [
            e
            for e in raw["events"]
            if e["kind"] != "job_metadata"
            or e["payload"]["job"]["failure_stage"] == "analysis"
        ]
    else:
        del raw["latest_metadata"]
    assert interaction_coverage(scenario(tmp_path, raw))["status"] == "unproven"
