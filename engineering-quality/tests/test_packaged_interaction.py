"""Exact native journey admission, output, ownership and contextual controls."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PIL import Image
from quality_harness.e2e_provenance import bundle_tree_receipt
from quality_harness.interaction_coverage import interaction_coverage
from quality_harness.packaged_e2e import SMOKE_UI_EVENT_ORDER
from quality_harness.packaged_interaction import (
    DIMENSIONS,
    evaluate_packaged_interaction,
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, obj):
    path.write_text(json.dumps(obj))
    return {"path": str(path), "sha256": sha(path)}


@pytest.fixture
def journey(tmp_path):
    root = tmp_path
    (root / "ui").mkdir()
    bundle = root / "VODForge.app"
    bundle.mkdir()
    executable = bundle / "VODForge"
    executable.write_bytes(b"fixture executable")
    tree = bundle_tree_receipt(bundle)
    archive = root / "candidate.zip"
    archive.write_bytes(b"immutable candidate archive")
    candidate = {
        "candidate_id": "candidate-1",
        "immutable_archive": {"path": str(archive), "sha256": sha(archive)},
        "artifact": {"bundle_tree": tree},
    }
    nonce = "native-test-session-12345"
    launches = [
        {
            "launch_sequence": i,
            "launch_id": "launch-" + str(i),
            "pid": 7000 + i,
            "create_time": 100.0 + i,
            "executable_sha256": sha(executable),
            "bundle_tree_sha256": tree["sha256"],
            "window_token": "window-" + str(i),
            "returncode": 0,
            "timed_out": False,
            "group_survivors_after_exit": [],
        }
        for i in (1, 2)
    ]
    events = []
    now = datetime.now(timezone.utc)
    for index, name in enumerate(SMOKE_UI_EVENT_ORDER):
        launch = launches[1 if name == "restart_observed" else 0]
        frame = root / "ui" / (name + ".png")
        Image.new("RGB", (20, 20), (20, 30, 40)).save(frame)
        events.append(
            {
                "event": name,
                "observed_at": (now + timedelta(seconds=index)).isoformat(),
                "session_nonce": nonce,
                "launch_id": launch["launch_id"],
                "launch_sequence": launch["launch_sequence"],
                "pid": launch["pid"],
                "process_create_time": launch["create_time"],
                "executable_sha256": launch["executable_sha256"],
                "bundle_tree_sha256": launch["bundle_tree_sha256"],
                "window_owner_pid": launch["pid"],
                "window_title_token": launch["window_token"],
                "window_id": launch["pid"],
                "native_window_identity": {
                    "verified": True,
                    "window_id": launch["pid"],
                    "owner_pid": launch["pid"],
                },
                "screenshot": str(frame),
            }
        )
    output = root / "Downloads"
    output.mkdir()
    media = output / "example.mp4"
    media.write_bytes(b"media fixture")
    history = root / "history.json"
    history.write_text("{}")
    parsed = {
        "format": {"duration": "1.0"},
        "streams": [{"codec_type": "video", "codec_name": "h264"}],
    }
    diagnostics = root / "diagnostics.log"
    diagnostics.write_text(
        "download and yt-dlp post-processing elapsed_seconds=1\ntranscode elapsed_seconds=1\nartifact validation elapsed_seconds=1\natomic output commit elapsed_seconds=1\n"
    )
    raw = {
        "started_at": (now - timedelta(seconds=1)).isoformat(),
        "completed_at": (now + timedelta(seconds=30)).isoformat(),
        "pipeline_observation_refs": [
            {
                "path": str(diagnostics),
                "sha256": sha(diagnostics),
                "kind": "diagnostics",
            }
        ],
        "scenario": {"metrics": {"e2e_profile": "smoke"}},
        "candidate_receipt_ref": save(root / "candidate.json", candidate),
        "candidate_binding": {
            "candidate_id": "candidate-1",
            "archive_sha256": sha(archive),
            "bundle_tree_sha256": tree["sha256"],
        },
        "artifact_receipt": {
            "artifact": str(bundle),
            "executable": str(executable),
            "executable_sha256": sha(executable),
            "bundle_tree": tree,
            "bundled_ffprobe": {"path": str(executable), "sha256": sha(executable)},
        },
        "artifact_integrity": {
            "before_bundle_tree_sha256": tree["sha256"],
            "after_bundle_tree_sha256": tree["sha256"],
            "critical_files": {
                "executable": {
                    "path": str(executable),
                    "expected_sha256": sha(executable),
                    "observed_sha256": sha(executable),
                }
            },
        },
        "process_provenance": {
            "session_nonce": nonce,
            "preexisting_processes": [],
            "surviving_owned_processes": [],
            "cleanup_receipts": [{"verified_owned": True, "survivors_after": []}],
            "isolated_state_paths": {"output": str(output)},
        },
        "launches": launches,
        "driver_trace": {
            "events": events,
            "screenshots": [e["screenshot"] for e in events],
        },
        "media_probes": [
            {
                "path": str(media),
                "sha256": sha(media),
                "size_bytes": media.stat().st_size,
                "ffprobe": parsed,
                "ffprobe_executable": str(executable),
                "ffprobe_sha256": sha(executable),
                "ffprobe_command": {
                    "command": [
                        str(executable),
                        "-v",
                        "error",
                        "-print_format",
                        "json",
                        "-show_entries",
                        "format=format_name,size,duration:format_tags:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,bit_rate,pix_fmt,profile,sample_rate,channels:stream_disposition",
                        str(media),
                    ],
                    "returncode": 0,
                    "timed_out": False,
                    "unavailable": False,
                    "stdout": json.dumps(parsed),
                },
            }
        ],
        "history_persistence": {
            "history_path": str(history),
            "pre_restart_snapshot": {
                "history_sha256": sha(history),
                "media": [{"path": str(media), "sha256": sha(media)}],
            },
        },
        "contextual_usability_review": {
            "reviewer": "Synthetic evaluator control, not product qualification",
            "dimensions": {
                name: {
                    "observed": "Observed fixture frame for negative-control qualification.",
                    "expected": "Expected reviewed contract remains concretely visible.",
                    "assessment": "Synthetic control exercises the frame identity binding.",
                    "outcome": "passed",
                    "frames": [
                        {
                            "event": "app_visible",
                            "sha256": sha(root / "ui/app_visible.png"),
                        }
                    ],
                }
                for name in DIMENSIONS
            },
        },
    }
    return root, raw


def assess(root, raw):
    ref = save(root / "e2e-result.json", raw)
    return interaction_coverage(
        {
            "id": "packaged_app_e2e.full_journey",
            "evidence_tier": "packaged_app_e2e",
            "status": "passed",
            "raw_result": ref["path"],
            "raw_result_sha256": ref["sha256"],
        }
    )


def test_bound_packaged_control_requires_both_functional_and_contextual_review(journey):
    root, raw = journey
    result = assess(root, raw)
    assert result["status"] == "passed", [
        a for a in result["assertion_mapping"] if a["status"] != "passed"
    ]
    assert result["usability_review"]["status"] == "passed"


@pytest.mark.parametrize(
    "control",
    [
        "candidate",
        "archive",
        "bundle",
        "missing_event",
        "event_order",
        "foreign_pid",
        "foreign_nonce",
        "changed_frame",
        "survivor",
        "crash",
        "changed_executable",
        "changed_media",
        "changed_history",
        "failed_probe",
        "no_streams",
        "probe_payload",
        "staging",
    ],
)
def test_old_pass_flags_cannot_hide_bad_packaged_observation(journey, control):
    root, raw = journey
    if control == "candidate":
        raw["candidate_binding"]["candidate_id"] = "other"
    elif control == "archive":
        raw["candidate_binding"]["archive_sha256"] = "0" * 64
    elif control == "bundle":
        raw["artifact_integrity"]["after_bundle_tree_sha256"] = "0" * 64
    elif control == "missing_event":
        raw["driver_trace"]["events"].pop()
    elif control == "event_order":
        raw["driver_trace"]["events"].reverse()
    elif control == "foreign_pid":
        raw["driver_trace"]["events"][0]["pid"] = 1
    elif control == "foreign_nonce":
        raw["driver_trace"]["events"][0]["session_nonce"] = "other"
    elif control == "changed_frame":
        (root / "ui/app_visible.png").write_bytes(b"invalid image")
    elif control == "survivor":
        raw["launches"][0]["group_survivors_after_exit"] = [{"pid": 7777}]
    elif control == "crash":
        raw["launches"][0]["returncode"] = 139
    elif control == "changed_executable":
        (root / "VODForge.app/VODForge").write_bytes(b"changed")
    elif control == "changed_media":
        (root / "Downloads/example.mp4").write_bytes(b"changed")
    elif control == "changed_history":
        (root / "history.json").write_text("changed")
    elif control == "failed_probe":
        raw["media_probes"][0]["ffprobe_command"]["returncode"] = 1
    elif control == "no_streams":
        raw["media_probes"][0]["ffprobe"]["streams"] = []
        raw["media_probes"][0]["ffprobe_command"]["stdout"] = json.dumps(
            raw["media_probes"][0]["ffprobe"]
        )
    elif control == "probe_payload":
        raw["media_probes"][0]["ffprobe"]["format"]["duration"] = "999"
    else:
        (root / "Downloads/.vfstage").mkdir()
    assert assess(root, raw)["status"] != "passed"


@pytest.mark.parametrize(
    "control",
    [
        "missing_review",
        "missing_dimension",
        "changed_reference",
        "negative_review",
        "missing_annotation",
        "missing_reviewer",
    ],
)
def test_contextual_review_is_complete_and_exact_frame_bound(journey, control):
    root, raw = journey
    review = raw["contextual_usability_review"]
    if control == "missing_review":
        del raw["contextual_usability_review"]
    elif control == "missing_dimension":
        del review["dimensions"][DIMENSIONS[0]]
    elif control == "changed_reference":
        review["dimensions"][DIMENSIONS[0]]["frames"][0]["sha256"] = "0" * 64
    elif control == "negative_review":
        review["dimensions"][DIMENSIONS[0]]["outcome"] = "failed"
    elif control == "missing_annotation":
        del review["dimensions"][DIMENSIONS[0]]["observed"]
    else:
        del review["reviewer"]
    result = assess(root, raw)
    assert result["status"] == "passed"
    assert result["usability_review"]["status"] != "passed"


@pytest.mark.parametrize(
    "control",
    [
        "missing_logs",
        "changed_logs",
        "missing_stage",
        "missing_time",
        "event_outside_session",
    ],
)
def test_missing_or_changed_pipeline_and_session_evidence_refuses(journey, control):
    root, raw = journey
    if control == "missing_logs":
        del raw["pipeline_observation_refs"]
    elif control == "changed_logs":
        Path(raw["pipeline_observation_refs"][0]["path"]).write_text("replaced")
    elif control == "missing_stage":
        path = Path(raw["pipeline_observation_refs"][0]["path"])
        path.write_text("download and yt-dlp post-processing elapsed_seconds=1")
        raw["pipeline_observation_refs"][0]["sha256"] = sha(path)
    elif control == "missing_time":
        del raw["started_at"]
    elif control == "event_outside_session":
        raw["completed_at"] = raw["started_at"]
    assert assess(root, raw)["status"] != "passed"


@pytest.mark.parametrize(
    "control", [None, "raw", "nonce", "candidate", "changed_review"]
)
def test_separate_context_review_keeps_original_raw_immutable(journey, control):
    root, raw = journey
    review = raw.pop("contextual_usability_review")
    ref = save(root / "e2e-result.json", raw)
    scenario = {
        "id": "packaged_app_e2e.full_journey",
        "evidence_tier": "packaged_app_e2e",
        "raw_result": ref["path"],
        "raw_result_sha256": ref["sha256"],
    }
    original = Path(scenario["raw_result"]).read_bytes()
    payload = {
        "raw_result_sha256": scenario["raw_result_sha256"],
        "session_nonce": raw["process_provenance"]["session_nonce"],
        "candidate_id": raw["candidate_binding"]["candidate_id"],
        "review": review,
    }
    if control == "raw":
        payload["raw_result_sha256"] = "0" * 64
    elif control == "nonce":
        payload["session_nonce"] = "foreign"
    elif control == "candidate":
        payload["candidate_id"] = "foreign"
    ref = save(
        Path(scenario["raw_result"]).parent / "contextual-usability-review.json",
        payload,
    )
    scenario["contextual_review_ref"] = ref
    if control == "changed_review":
        Path(ref["path"]).write_text("{}")
    result = evaluate_packaged_interaction(scenario)
    assert result["status"] == "passed"
    assert (result["usability_review"]["status"] == "passed") is (control is None)
    assert Path(scenario["raw_result"]).read_bytes() == original
