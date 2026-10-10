"""Actual-shaped bounded security receipts cannot qualify after adversarial edits."""

import hashlib
import json
from pathlib import Path

import pytest
from quality_harness.interaction_coverage import interaction_coverage

FIXTURES = json.loads(
    Path(__file__).with_name("security_observations.json").read_text()
)
COMMON = [
    "foreign_identity",
    "foreign_contract",
    "missing_trace",
    "reversed_trace",
    "missing_clock",
    "foreign_raw_hash",
    "false_scope",
]
SINKS = [
    "history_activity",
    "history_url",
    "persistent_activity",
    "batch_failure",
    "diagnostic",
    "compact_metadata",
]
SECRET = [
    f"{kind}:{sink}"
    for sink in SINKS
    for kind in ("leak", "no_identity", "missing_text")
]
SECRET += [
    f"{kind}:{i}"
    for i in range(4)
    for kind in (
        "prior_file",
        "foreign_file",
        "missing_file",
        "wrong_hash",
        "wrong_size",
        "changed_after",
        "missing_after_text",
    )
]
SECRET += [f"public_mode:{i}" for i in range(3)] + [
    "not_posix",
    "wrong_canary",
    "wrong_input",
]
NETWORK = [
    f"{kind}:{i}"
    for i in range(3)
    for kind in (
        "wrong_url",
        "wrong_source",
        "wrong_timeout",
        "wrong_clock",
        "missing_call_clock",
        "foreign_before",
        "foreign_after",
        "wrong_requests",
        "wrong_response",
        "wrong_payload",
        "wrong_exception",
        "wrong_rejection",
    )
]
NETWORK += [
    "same_origin",
    "external_origin",
    "prior_target",
    "missing_call",
    "reversed_calls",
    "missing_fixture",
    "foreign_fixture",
    "late_target",
    "changed_after_source",
]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, a):
    p.write_text(json.dumps(a, indent=2) + "\n")
    return {"path": str(p), "sha256": sha(p)}


def controls(s):
    return COMMON + (SECRET if "secret" in s["id"] else NETWORK)


def mutate(s, a, name):
    if name == "foreign_identity":
        a["scenario_id"] = "other"
    elif name == "foreign_contract":
        a["contract"] = "other"
    elif name == "missing_trace":
        del a["trace"]
    elif name == "reversed_trace":
        a["trace"].reverse()
    elif name == "missing_clock":
        del a["trace"][0]["elapsed_seconds"]
    elif name == "false_scope":
        a["scope"] = "all network and ACL acceptance"
    elif name == "foreign_raw_hash":
        pass
    elif "secret" in s["id"]:
        before, during, after = a["trace"]
        if ":" in name:
            kind, key = name.split(":")
            if key in SINKS:
                if kind == "leak":
                    during["text"][key] += a["input_url"]
                elif kind == "no_identity":
                    during["text"][key] = "redacted"
                elif kind == "missing_text":
                    del during["text"][key]
            else:
                i = int(key)
                if kind == "prior_file":
                    before["files"][i]["exists"] = True
                elif kind == "foreign_file":
                    during["files"][i]["path"] = "/foreign/log"
                elif kind == "missing_file":
                    during["files"][i]["exists"] = False
                elif kind == "wrong_hash":
                    during["files"][i]["sha256"] = "0" * 64
                elif kind == "wrong_size":
                    during["files"][i]["size_bytes"] += 1
                elif kind == "changed_after":
                    after["files"][i]["sha256"] = "0" * 64
                elif kind == "missing_after_text":
                    del after["text"][
                        [
                            "batch_failure",
                            "persistent_activity",
                            "diagnostic",
                            "compact_metadata",
                        ][i]
                    ]
                elif kind == "public_mode":
                    during["files"][i]["mode"] = 0o644
        elif name == "not_posix":
            a["os_name"] = "nt"
        elif name == "wrong_canary":
            a["canary"] = "other"
        elif name == "wrong_input":
            a["input_url"] = "https://example.invalid/media"
    else:
        if ":" in name:
            kind, i = name.split(":")
            c = a["calls"][int(i)]
            if kind == "wrong_url":
                c["url"] = "http://127.0.0.1:1/other"
            elif kind == "wrong_source":
                c["source_url"] = a["target_url"]
            elif kind == "wrong_timeout":
                c["timeout_seconds"] = 0
            elif kind == "wrong_clock":
                c["returned_seconds"] = c["entered_seconds"] - 1
            elif kind == "missing_call_clock":
                del c["entered_seconds"]
            elif kind == "foreign_before":
                c["target_before"]["total_requests"] = 1
            elif kind == "foreign_after":
                c["target_after"]["total_requests"] = 1
            elif kind == "wrong_requests":
                c["source_after"]["total_requests"] += 1
            elif kind == "wrong_response":
                c["source_after"]["responses"] = [{"route": "/wrong", "status": 500}]
            elif kind == "wrong_payload":
                c["payload_sha256"] = "0" * 64
            elif kind == "wrong_exception":
                c["exception_type"] = (
                    "RuntimeError" if c["exception_type"] is None else None
                )
            elif kind == "wrong_rejection":
                c["rejection"] = "not trusted" if int(i) == 0 else "no refusal"
        elif name == "same_origin":
            a["target_url"] = a["source_url"]
        elif name == "external_origin":
            a["source_url"] = "http://example.invalid/page/normal"
        elif name == "prior_target":
            a["trace"][0]["target"]["total_requests"] = 1
        elif name == "missing_call":
            a["calls"].pop()
        elif name == "reversed_calls":
            a["calls"].reverse()
        elif name == "missing_fixture":
            del a["fixture"]["sha256"]
        elif name == "foreign_fixture":
            a["fixture"]["path"] = "/foreign/thumbnail.jpg"
        elif name == "late_target":
            a["trace"][-1]["target"]["total_requests"] = 1
        elif name == "changed_after_source":
            a["trace"][-1]["source"]["total_requests"] += 1


def materialize(tmp_path, example):
    folder = tmp_path / "cases" / example["folder"]
    folder.mkdir(parents=True)
    a = json.loads(
        json.dumps(example["raw"]).replace(example["old_run_root"], str(tmp_path))
    )
    ref = save(folder / "observation.json", a)
    return (
        dict(
            example["scenario"], raw_result=ref["path"], raw_result_sha256=ref["sha256"]
        ),
        a,
        folder,
    )


CASES = [(i, n) for i, f in enumerate(FIXTURES) for n in controls(f["scenario"])]


@pytest.mark.parametrize("i", range(len(FIXTURES)))
def test_actual_security_shape_qualifies(tmp_path, i):
    s, _, _ = materialize(tmp_path, FIXTURES[i])
    q = interaction_coverage(s)
    assert q["status"] == "passed", q
    assert q["usability_review"]["status"] == "not_applicable"


@pytest.mark.parametrize("i,name", CASES)
def test_altered_security_cannot_qualify(tmp_path, i, name):
    s, a, folder = materialize(tmp_path, FIXTURES[i])
    mutate(s, a, name)
    ref = save(folder / "mutation.json", a)
    s.update(
        raw_result=ref["path"],
        raw_result_sha256="0" * 64 if name == "foreign_raw_hash" else ref["sha256"],
    )
    q = interaction_coverage(s)
    assert q["status"] in {"failed", "unproven"}, q
