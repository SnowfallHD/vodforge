"""Controlled composition must reject missing, foreign and mutated observations."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from quality_harness.interaction_coverage import interaction_coverage

FIXTURES = json.loads(
    Path(__file__).with_name("lifecycle_observations.json").read_text()
)
NEGATIVES = [
    "foreign_identity",
    "foreign_contract",
    "initial_child",
    "retained_child",
    "missing_before",
    "missing_after",
    "missing_workers",
    "foreign_origin",
    "missing_constituent",
    "changed_constituent",
    "foreign_constituent",
    "prior_output",
    "escaped_transfer",
    "committed_unreadable",
    "stage_residue",
    "emergency_cleanup",
    "observer_leak",
    "foreign_worker_owner",
    "missing_worker_clock",
]
CONCURRENT = [
    "no_overlap",
    "thread_missing",
    "thread_reordered",
    "thread_survivor",
    "thread_error",
    "duplicate_owner",
    "baseline_after_entry",
    "finish_before_return",
]
SOAK = [
    "wrong_count",
    "wrong_sidecar",
    "retained_full_results",
    "missing_samples",
    "missing_sample_row",
    "reversed_sample_clock",
    "foreign_sample_owner",
    "post_gc_child",
    "post_gc_staging",
    "post_gc_garbage",
]
DEEP = ["missing_object_counts", "retained_worker_object"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data, lines=False):
    path.write_text(
        ("\n".join(json.dumps(x) for x in data) + "\n")
        if lines
        else json.dumps(data, indent=2) + "\n"
    )
    return {"path": str(path), "sha256": sha(path)}


def mutate(s, raw, name, directory):
    concurrent = s["id"].startswith("concurrency")
    if name == "foreign_identity":
        raw["scenario_id"] = "other"
    elif name == "foreign_contract":
        raw["contract"] = "other"
    elif name == "initial_child":
        raw["before"]["children"] = [{"alive": True}]
    elif name == "retained_child":
        raw["after"]["children_before_emergency"] = [{"alive": True}]
    elif name in ["missing_before", "missing_after", "missing_workers"]:
        del raw[name.removeprefix("missing_")]
    elif name == "foreign_origin":
        raw["before"]["fixture"]["origin"] = "http://127.0.0.1:65535"
    elif name in [
        "missing_samples",
        "wrong_count",
        "wrong_sidecar",
        "retained_full_results",
    ]:
        if name == "missing_samples":
            del raw["samples"]
        elif name == "wrong_count":
            raw["workload"]["jobs"] += 1
        elif name == "wrong_sidecar":
            raw["workload"]["write_thumbnail"] = True
        else:
            raw["workload"]["full_pipeline_results_retained_during_sampling"] = True
    elif name in CONCURRENT:
        if name == "no_overlap":
            # Move mp4's actual worker AND thread interval later, preserving their own ordering.
            ref = raw["workers"]["mp4"]
            worker = json.loads(Path(ref["path"]).read_text())
            worker["observation_clock_origin_monotonic"] += 100
            raw["workers"]["mp4"] = save(directory / "worker.json", worker)
            for row in raw["thread_trace"]:
                if row["name"] == "mp4":
                    row["elapsed_seconds"] += 100
            raw["thread_trace"].sort(key=lambda r: r["elapsed_seconds"])
            raw["after"]["elapsed_seconds"] += 100
        elif name == "thread_missing":
            raw["thread_trace"].pop()
        elif name == "thread_reordered":
            raw["thread_trace"].reverse()
        elif name == "thread_survivor":
            raw["after"]["threads_alive"] = ["quality-concurrency-mp3"]
        elif name == "thread_error":
            raw["after"]["errors"] = ["failure"]
        elif name == "baseline_after_entry":
            raw["before"]["elapsed_seconds"] = 100
        elif name == "finish_before_return":
            raw["after"]["elapsed_seconds"] = 0
        else:
            a = json.loads(Path(raw["workers"]["mp4"]["path"]).read_text())
            b = json.loads(Path(raw["workers"]["mp3"]["path"]).read_text())
            a["job"]["run_id"] = b["job"]["run_id"]
            for row in a["control_trace"]:
                row["run_id"] = a["job"]["run_id"]
            raw["workers"]["mp4"] = save(directory / "worker.json", a)
    elif name in SOAK + DEEP:
        samples = [
            json.loads(x) for x in Path(raw["samples"]["path"]).read_text().splitlines()
        ]
        if name == "missing_sample_row":
            samples.pop()
        elif name == "reversed_sample_clock":
            samples[-1]["elapsed_seconds"] = 0
        elif name == "foreign_sample_owner":
            samples[-1]["job"]["case_id"] = "other"
        elif name == "post_gc_child":
            samples[-1]["process"]["child_processes"] = [
                {"pid": 123, "status": "sleeping"}
            ]
        elif name == "post_gc_staging":
            samples[-1]["storage"]["staging_residue_paths"] = ["stage"]
        elif name == "post_gc_garbage":
            samples[-1]["gc"]["uncollectable_garbage_count"] = 1
        elif name == "missing_object_counts":
            del samples[-1]["gc_tracked_objects"]
        elif name == "retained_worker_object":
            samples[-1]["gc_tracked_objects"]["selected_type_counts"][
                "yt_downloader.models.DownloadJob"
            ] = (
                samples[0]["gc_tracked_objects"]["selected_type_counts"][
                    "yt_downloader.models.DownloadJob"
                ]
                + 1
            )
        raw["samples"] = save(directory / "samples.jsonl", samples, True)
    else:
        ref = raw["workers"]["mp3"] if concurrent else raw["workers"][0]
        if name == "missing_constituent":
            ref["path"] = str(directory / "absent.json")
            return
        if name == "changed_constituent":
            ref["sha256"] = "0" * 64
            return
        if name == "foreign_constituent":
            ref["path"] = "/foreign/worker.json"
            return
        worker = json.loads(Path(ref["path"]).read_text())
        if name == "prior_output":
            worker["before_worker"]["output_files"] = ["prior.mp3"]
        elif name == "escaped_transfer":
            next(
                r for r in worker["progress_trace"] if r.get("downloaded_bytes", 0) > 0
            )["filename"] = "/foreign/input"
        elif name == "committed_unreadable":
            next(r for r in worker["outputs"] if r["path"].endswith(".mp3"))[
                "readable"
            ] = False
        elif name == "stage_residue":
            worker["staging_entries_after"] = ["stage"]
        elif name == "emergency_cleanup":
            worker["harness_emergency_cleanup_used"] = True
        elif name == "observer_leak":
            worker["control_observer_stopped"] = False
        elif name == "foreign_worker_owner":
            worker["control_trace"][0]["run_id"] = "other"
        elif name == "missing_worker_clock":
            del worker["observation_clock_origin_monotonic"]
        replacement = save(directory / "worker.json", worker)
        ref.clear()
        ref.update(replacement)
        if not concurrent:
            samples = [
                json.loads(x)
                for x in Path(raw["samples"]["path"]).read_text().splitlines()
            ]
            samples[2]["job"]["artifact"] = replacement["path"]
            samples[2]["job"]["raw_result_sha256"] = replacement["sha256"]
            raw["samples"] = save(directory / "samples.jsonl", samples, True)


def materialize(tmp_path, example):
    root = tmp_path / "cases"
    root.mkdir()
    concurrent = example["id"].startswith("concurrency")
    folder = root if concurrent else root / "lifecycle-soak-observability"
    folder.mkdir(exist_ok=True)
    raw = copy.deepcopy(example["raw"])
    refs = []
    for worker in example["workers"]:
        directory = root / worker["case_id"]
        directory.mkdir()
        refs.append(save(directory / "pipeline-result.json", worker))
    if concurrent:
        raw["workers"] = {
            r["case_id"].removeprefix("concurrency-"): ref
            for r, ref in zip(example["workers"], refs, strict=True)
        }
    else:
        raw["workers"] = refs
        samples = copy.deepcopy(example["samples"])
        for i, ref in enumerate(refs, 1):
            samples[2 * i]["job"]["artifact"] = ref["path"]
            samples[2 * i]["job"]["raw_result_sha256"] = ref["sha256"]
        raw["samples"] = save(folder / "samples.jsonl", samples, True)
    ref = save(folder / "observation.json", raw)
    return (
        {
            "id": example["id"],
            "evidence_tier": "headless_production_pipeline",
            "status": "passed",
            "raw_result": ref["path"],
            "raw_result_sha256": ref["sha256"],
        },
        raw,
        folder,
    )


CASES = [
    (i, name)
    for i, fixture in enumerate(FIXTURES)
    for name in NEGATIVES
    + (CONCURRENT if fixture["id"].startswith("concurrency") else SOAK)
    + (DEEP if fixture["raw"].get("workload", {}).get("tracemalloc_enabled") else [])
]


@pytest.mark.parametrize("index", range(len(FIXTURES)))
def test_actual_composite_shape_qualifies(tmp_path, index):
    scenario, _, _ = materialize(tmp_path, FIXTURES[index])
    result = interaction_coverage(scenario)
    assert result["status"] == "passed", result
    assert result["usability_review"]["status"] == "not_applicable"


@pytest.mark.parametrize("index,name", CASES)
def test_mutated_composite_cannot_qualify(tmp_path, index, name):
    scenario, raw, folder = materialize(tmp_path, FIXTURES[index])
    directory = folder / name
    directory.mkdir()
    mutate(scenario, raw, name, directory)
    ref = save(folder / "mutation.json", raw)
    scenario.update(raw_result=ref["path"], raw_result_sha256=ref["sha256"])
    result = interaction_coverage(scenario)
    assert result["status"] in {"failed", "unproven"}, result
