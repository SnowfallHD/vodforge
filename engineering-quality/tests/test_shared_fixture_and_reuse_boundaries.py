"""Prior fixture traffic and atomic sidecar repair retain strict causal boundaries."""

import copy
import json
from pathlib import Path

import pytest
from quality_harness.interaction_coverage import interaction_coverage
from test_duplicate_interaction import materialize, save
from test_http404_interaction import observation, scenario
from test_reliability_interaction import OBSERVATIONS
from test_reliability_interaction import scenario as reliability_scenario


def add_prior_response(raw):
    before = raw["before_worker"]
    initial = before["fixture_state"]
    after = raw["fixture_state_after"]
    offset = len(initial["responses"])
    clock = (
        after["responses"][offset]["observed_at_monotonic"]
        - raw["fixture_response_trace"][0]["elapsed_seconds"]
    )
    raw["observation_clock_origin_monotonic"] = clock
    route = raw["job"]["url"].split("127.0.0.1:")[1].split("/", 1)[1]
    row = {
        "route": "/" + route,
        "status": 200,
        "observed_at_monotonic": clock + before["fixture_elapsed_seconds"] / 2,
    }
    for state in (initial, after):
        state.setdefault("requests", {})[row["route"]] = (
            state.get("requests", {}).get(row["route"], 0) + 1
        )
        state.setdefault("statuses", {})["200"] = (
            state.get("statuses", {}).get("200", 0) + 1
        )
        state["total_requests"] += 1
        state["responses"].insert(offset, copy.deepcopy(row))
    return raw


def http_observation():
    raw = observation()
    raw["before_worker"]["fixture_state"].update(requests={}, statuses={})
    raw["fixture_state_after"]["responses"][0]["observed_at_monotonic"] = 102.0
    return add_prior_response(raw)


@pytest.mark.parametrize("domain", ["http404", "ffmpeg"])
def test_prior_completed_source_request_has_exact_owned_response_delta(
    tmp_path, domain
):
    if domain == "http404":
        s = scenario(tmp_path, http_observation())
    else:
        sid = "reliability.ffmpeg_child_failure"
        raw = add_prior_response(copy.deepcopy(OBSERVATIONS[sid]))
        s = reliability_scenario(tmp_path, sid, raw)
    assert interaction_coverage(s)["status"] == "passed"


@pytest.mark.parametrize(
    "fault",
    [
        "count",
        "count_type",
        "late_prior",
        "altered_prefix",
        "absolute_time",
        "missing_time",
        "extra_response",
    ],
)
def test_shared_server_does_not_waive_causal_inventory(tmp_path, fault):
    raw = http_observation()
    initial = raw["before_worker"]["fixture_state"]
    after = raw["fixture_state_after"]
    if fault == "count":
        initial["requests"]["/status/404"] += 1
    elif fault == "count_type":
        initial["requests"]["/status/404"] = True
    elif fault == "late_prior":
        for state in (initial, after):
            state["responses"][0]["observed_at_monotonic"] = 101.5
    elif fault == "altered_prefix":
        after["responses"][0]["observed_at_monotonic"] -= 1
    elif fault == "absolute_time":
        after["responses"][-1]["observed_at_monotonic"] += 0.5
    elif fault == "missing_time":
        del after["responses"][-1]["observed_at_monotonic"]
    else:
        after["responses"].append(copy.deepcopy(after["responses"][-1]))
    assert interaction_coverage(scenario(tmp_path, raw))["status"] == "failed"


def sidecar_observation(tmp_path, fault=None):
    s, a, folder = materialize(tmp_path)
    row = next(
        r
        for r in a["rows"]
        if r["phase"] == "worker_returned" and r["case_id"] == "variant-mp4-repeat"
    )
    worker = json.loads(Path(row["worker"]["path"]).read_text())
    sample = copy.deepcopy(worker["staging_trace"][1])
    sample.update(
        root_present=True,
        root_mode=0o700,
        run_directories=["18cb4aaf"],
        entries=[
            {"path": "18cb4aaf", "kind": "directory", "size_bytes": None},
            {"path": "18cb4aaf/sidecar", "kind": "file", "size_bytes": 1926},
        ],
    )
    worker["staging_trace"].insert(-1, sample)
    if fault == "media":
        sample["entries"][1]["path"] = "18cb4aaf/media.mp4"
    elif fault == "mode":
        sample["root_mode"] = 0o777
    elif fault == "foreign_directory":
        sample["run_directories"] = ["../other"]
    elif fault == "symlink":
        sample["entries"][1]["kind"] = "symlink"
    elif fault == "late_stage":
        sample["elapsed_seconds"] = worker["control_trace"][-1]["elapsed_seconds"] + 1
    elif fault == "lingering_stage":
        worker["staging_trace"][-1].update(root_present=True, entries=sample["entries"])
    elif fault == "transfer":
        worker["progress_trace"] = [{"status": "downloading", "downloaded_bytes": 10}]
    elif fault == "extra_payload":
        sample["entries"].append(
            {"path": "18cb4aaf/other", "kind": "file", "size_bytes": 1}
        )
    elif fault == "unbounded_size":
        sample["entries"][1]["size_bytes"] = -1
    row["worker"] = save(folder / "sidecar-worker.json", worker)
    ref = save(folder / "sidecar-observation.json", a)
    s.update(raw_result=ref["path"], raw_result_sha256=ref["sha256"])
    return s


def test_existing_media_reuse_allows_atomic_private_sidecar_repair(tmp_path):
    assert interaction_coverage(sidecar_observation(tmp_path))["status"] == "passed"


@pytest.mark.parametrize(
    "fault",
    [
        "media",
        "mode",
        "foreign_directory",
        "symlink",
        "late_stage",
        "lingering_stage",
        "transfer",
        "extra_payload",
        "unbounded_size",
    ],
)
def test_sidecar_permission_cannot_hide_media_transfer_or_escape(tmp_path, fault):
    assert (
        interaction_coverage(sidecar_observation(tmp_path, fault))["status"] == "failed"
    )
