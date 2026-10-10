"""Real duplicate ownership must reject foreign and altered outcomes."""

import hashlib
import json
from pathlib import Path

import pytest
from quality_harness.duplicate_interaction import CASES, history_path
from quality_harness.interaction_coverage import interaction_coverage
from quality_harness.observation_fixtures import relocate_observation

FIXTURE = json.loads(Path(__file__).with_name("duplicate_observation.json").read_text())
GLOBAL = [
    "foreign_identity",
    "foreign_contract",
    "missing_rows",
    "reversed_rows",
    "missing_clock",
    "missing_worker",
    "changed_worker_hash",
    "foreign_worker_path",
    "missing_history_transition",
    "merged_variant_history",
    "missing_durable_history",
    "changed_durable_file",
    "missing_sibling_masks",
    "wrong_missing_state",
    "unrefreshed_identity",
]
PER_WORKER = [
    "owner",
    "emergency",
    "observer",
    "staging",
    "history_owner",
    "history_path",
    "media_hash",
    "preexisting_hash",
    "worker_clock",
    "wrong_intent",
]
CONTROLS = GLOBAL + [f"{kind}:{case}" for case in CASES for kind in PER_WORKER]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, a):
    p.write_text(json.dumps(a, indent=2) + "\n")
    return {"path": str(p), "sha256": sha(p)}


def mutate(a, name, directory):
    rows = a.get("rows", [])
    if name == "foreign_identity":
        a["scenario_id"] = "other"
    elif name == "foreign_contract":
        a["contract"] = "other"
    elif name == "missing_rows":
        del a["rows"]
    elif name == "reversed_rows":
        rows.reverse()
    elif name == "missing_clock":
        del a["clock_origin_monotonic"]
    elif name in ["missing_worker", "changed_worker_hash", "foreign_worker_path"]:
        row = next(x for x in rows if x["phase"] == "worker_returned")
        if name == "missing_worker":
            row["worker"]["path"] = str(directory / "absent.json")
        elif name == "changed_worker_hash":
            row["worker"]["sha256"] = "0" * 64
        else:
            row["worker"]["path"] = "/foreign/pipeline-result.json"
    elif name == "missing_history_transition":
        rows.remove(next(x for x in rows if x["phase"] == "history_updated"))
    elif name == "merged_variant_history":
        next(x for x in reversed(rows) if x["phase"] == "history_updated")[
            "history"
        ].pop()
    elif name == "missing_durable_history":
        rows.remove(next(x for x in rows if x["phase"] == "history_reloaded"))
    elif name == "changed_durable_file":
        next(x for x in rows if x["phase"] == "history_reloaded")["durable_file"][
            "exists"
        ] = False
    elif name == "missing_sibling_masks":
        next(x for x in rows if x["phase"] == "exact_history_path_missing")[
            "sibling_exists"
        ] = False
    elif name == "wrong_missing_state":
        next(x for x in rows if x["phase"] == "exact_history_path_missing")[
            "exact_state"
        ] = "present"
    elif name == "unrefreshed_identity":
        next(x for x in rows if x["phase"] == "same_history_path_refreshed")["history"][
            0
        ]["title"] = "Primary"
    else:
        kind, case = name.split(":")
        row = next(
            x for x in rows if x["phase"] == "worker_returned" and x["case_id"] == case
        )
        worker = json.loads(Path(row["worker"]["path"]).read_text())
        history = next(
            e["payload"] for e in worker["events"] if e["kind"] == "history_record"
        )
        selected = history_path(history["info"])
        if kind == "owner":
            worker["control_trace"][0]["run_id"] = "other"
        elif kind == "emergency":
            worker["harness_emergency_cleanup_used"] = True
        elif kind == "observer":
            worker["control_observer_stopped"] = False
        elif kind == "staging":
            worker["staging_entries_after"] = ["stage"]
        elif kind == "history_owner":
            history["job"]["run_id"] = "other"
        elif kind == "history_path":
            history["info"]["vodforge_encoding_summary"]["output"][
                "Output file path"
            ] = "/foreign/video.mp4"
        elif kind == "media_hash":
            next(f for f in worker["outputs"] if f["path"] == selected)["sha256"] = (
                "0" * 64
            )
        elif kind == "preexisting_hash":
            next(f for f in row["files"] if f["path"] == selected)["sha256"] = "0" * 64
        elif kind == "worker_clock":
            worker["observation_clock_origin_monotonic"] += 100
        elif kind == "wrong_intent":
            worker["job"]["quality_label"] = "1080p"
        row["worker"] = save(directory / "worker.json", worker)


def materialize(tmp_path):
    root = tmp_path / "cases"
    root.mkdir()
    folder = root / "duplicate-artifact"
    folder.mkdir()
    a = relocate_observation(FIXTURE["raw"], FIXTURE["old_case_root"], root)
    for case, observed in FIXTURE["workers"].items():
        w = relocate_observation(observed, FIXTURE["old_case_root"], root)
        p = root / case
        p.mkdir()
        ref = save(p / "pipeline-result.json", w)
        next(
            x
            for x in a["rows"]
            if x["phase"] == "worker_returned" and x["case_id"] == case
        )["worker"] = ref
    ref = save(folder / "observation.json", a)
    return (
        dict(
            FIXTURE["scenario"], raw_result=ref["path"], raw_result_sha256=ref["sha256"]
        ),
        a,
        folder,
    )


def test_actual_duplicate_shape_qualifies(tmp_path):
    s, _, _ = materialize(tmp_path)
    q = interaction_coverage(s)
    assert q["status"] == "passed", q
    assert q["usability_review"]["status"] == "not_applicable"


@pytest.mark.parametrize("name", CONTROLS)
def test_altered_duplicate_cannot_qualify(tmp_path, name):
    s, a, folder = materialize(tmp_path)
    directory = folder / name.replace(":", "-")
    directory.mkdir()
    mutate(a, name, directory)
    ref = save(folder / "mutation.json", a)
    s.update(raw_result=ref["path"], raw_result_sha256=ref["sha256"])
    q = interaction_coverage(s)
    assert q["status"] in {"failed", "unproven"}, q
