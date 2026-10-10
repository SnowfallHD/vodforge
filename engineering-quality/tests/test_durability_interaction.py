"""Controlled durability and real mutation assertions fail closed after edits."""

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from quality_harness.interaction_coverage import interaction_coverage
from quality_harness.observation_fixtures import relocate_observation

FIXTURES = json.loads(
    Path(__file__).with_name("durability_observations.json").read_text()
)
COMMON = [
    "foreign_identity",
    "foreign_contract",
    "false_scope",
    "missing_trace",
    "reversed_trace",
    "missing_clock",
    "foreign_raw_hash",
]
ACTIVITY = [
    "prior_file",
    "missing_refusal",
    "duplicated_receipt",
    "secret_receipt",
    "retained_handle",
    "retained_path",
    "suppression_missing",
    "no_recovery_reset",
    "wrong_text",
    "wrong_hash",
    "wrong_size",
    "public_mode",
    "foreign_file",
    "changed_after",
    "missing_new_episode",
]
MUTATION = [
    "baseline_bad_return",
    "baseline_skip",
    "baseline_error",
    "baseline_missing_case",
    "baseline_source_changed",
    "missing_mutant",
    "duplicate_mutant",
    "production_changed",
    "baseline_changed",
] + [
    f"{kind}:{i}"
    for i in range(9)
    for kind in (
        "wrong_clock",
        "missing_clock",
        "wrong_old",
        "wrong_new",
        "wrong_file",
        "wrong_count",
        "prior_source_changed",
        "extra_source_changed",
        "wrong_exit",
        "timeout",
        "unavailable",
        "missing_failure",
        "import_error",
        "skip",
        "missing_case",
        "foreign_source",
    )
]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, a):
    p.write_text(json.dumps(a, indent=2) + "\n")
    return {"path": str(p), "sha256": sha(p)}


def controls(s):
    return COMMON + (ACTIVITY if "activity" in s["id"] else MUTATION)


def mutant_xml(ref, folder, name, kind):
    tree = ET.fromstring(Path(ref["path"]).read_text())
    cases = tree.findall(".//testcase")
    if kind == "missing_case":
        for parent in tree.iter():
            if cases[0] in list(parent):
                parent.remove(cases[0])
                break
    elif kind == "missing_failure":
        for c in cases:
            for f in c.findall("failure"):
                c.remove(f)
    elif kind in ("error", "skip"):
        if kind == "error":
            for c in cases:
                for f in c.findall("failure"):
                    c.remove(f)
        ET.SubElement(cases[0], "error" if kind == "error" else "skipped")
    p = folder / ("constituent-" + name + ".xml")
    p.write_bytes(ET.tostring(tree))
    return {**ref, "path": str(p), "size_bytes": p.stat().st_size, "sha256": sha(p)}


def mutate(s, a, name, folder):
    if name == "foreign_identity":
        a["scenario_id"] = "other"
    elif name == "foreign_contract":
        a["contract"] = "other"
    elif name == "false_scope":
        a["scope"] = "native product acceptance"
    elif name == "missing_trace":
        del a["trace"]
    elif name == "reversed_trace":
        a["trace"].reverse()
    elif name == "missing_clock":
        del a["trace"][0]["elapsed_seconds"]
    elif name == "foreign_raw_hash":
        pass
    elif "activity" in s["id"]:
        before, failed, recovered, after = a["trace"]
        if name == "prior_file":
            before["recovered_file"]["exists"] = True
        elif name == "missing_refusal":
            failed["receipts"] = []
        elif name == "duplicated_receipt":
            failed["receipts"] *= 2
        elif name == "secret_receipt":
            failed["receipts"][0] += " ACTIVITY-SECRET-CANARY"
        elif name == "retained_handle":
            failed["handle_none"] = False
        elif name == "retained_path":
            failed["handle_path_none"] = False
        elif name == "suppression_missing":
            failed["failure_reported"] = False
        elif name == "no_recovery_reset":
            recovered["failure_reported"] = True
        elif name == "wrong_text":
            recovered["recovered_text"] = "wrong"
        elif name == "wrong_hash":
            recovered["recovered_file"]["sha256"] = "0" * 64
        elif name == "wrong_size":
            recovered["recovered_file"]["size_bytes"] += 1
        elif name == "public_mode":
            recovered["recovered_file"]["mode"] = 0o644
        elif name == "foreign_file":
            recovered["recovered_file"]["path"] = "/foreign/log"
        elif name == "changed_after":
            after["recovered_file"]["sha256"] = "0" * 64
        elif name == "missing_new_episode":
            after["receipts"].pop()
    else:
        before, baseline, after = a["trace"]
        if ":" in name:
            kind, i = name.split(":")
            m = a["mutants"][int(i)]
            if kind == "wrong_clock":
                m["returned_seconds"] = m["entered_seconds"] - 1
            elif kind == "missing_clock":
                del m["entered_seconds"]
            elif kind == "wrong_old":
                m["old"] = "other"
            elif kind == "wrong_new":
                m["new"] = "other"
            elif kind == "wrong_file":
                m["file"] = "app.py"
            elif kind == "wrong_count":
                m["replacement_count"] = 2
            elif kind == "prior_source_changed":
                m["source_before"]["yt_downloader/app.py"] = "0" * 64
            elif kind == "extra_source_changed":
                m["source_after"]["yt_downloader/app.py"] = "0" * 64
            elif kind == "wrong_exit":
                m["result"]["returncode"] = 0
            elif kind == "timeout":
                m["result"]["timed_out"] = True
            elif kind == "unavailable":
                m["result"]["unavailable"] = True
            elif kind == "foreign_source":
                m["source_file"]["path"] = "/foreign/history.py"
            else:
                m["report"] = mutant_xml(
                    m["report"],
                    folder,
                    name,
                    "error" if kind == "import_error" else kind,
                )
        elif name == "baseline_bad_return":
            baseline["result"]["returncode"] = 1
        elif name in {"baseline_skip", "baseline_error", "baseline_missing_case"}:
            baseline["report"] = mutant_xml(
                baseline["report"], folder, name, name.split("_", 1)[1]
            )
        elif name == "baseline_source_changed":
            baseline["copied_source"]["yt_downloader/app.py"] = "0" * 64
        elif name == "missing_mutant":
            a["mutants"].pop()
        elif name == "duplicate_mutant":
            a["mutants"][-1] = a["mutants"][0]
        elif name == "production_changed":
            after["production_source"]["yt_downloader/app.py"] = "0" * 64
        elif name == "baseline_changed":
            after["baseline_source"]["yt_downloader/app.py"] = "0" * 64


def materialize(tmp_path, f):
    folder = tmp_path / f["folder"]
    folder.mkdir()
    a = relocate_observation(f["raw"], f["old_root"], folder)
    for rel, text in f["constituents"].items():
        p = folder / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        # Preserve retained constituent hashes across Windows text I/O.
        p.write_text(text, encoding="utf-8", newline="\n")
    ref = save(folder / "observation.json", a)
    return (
        dict(f["scenario"], raw_result=ref["path"], raw_result_sha256=ref["sha256"]),
        a,
        folder,
    )


@pytest.mark.parametrize("i", range(len(FIXTURES)))
def test_actual_durability_shape_qualifies(tmp_path, i):
    s, _, _ = materialize(tmp_path, FIXTURES[i])
    q = interaction_coverage(s)
    assert q["status"] == "passed", q
    assert q["usability_review"]["status"] == "not_applicable"


@pytest.mark.parametrize(
    "i,name", [(i, n) for i, f in enumerate(FIXTURES) for n in controls(f["scenario"])]
)
def test_altered_durability_cannot_qualify(tmp_path, i, name):
    s, a, folder = materialize(tmp_path, FIXTURES[i])
    mutate(s, a, name, folder)
    ref = save(folder / "mutation.json", a)
    s.update(
        raw_result=ref["path"],
        raw_result_sha256="0" * 64 if name == "foreign_raw_hash" else ref["sha256"],
    )
    q = interaction_coverage(s)
    assert q["status"] in {"failed", "unproven"}, q
