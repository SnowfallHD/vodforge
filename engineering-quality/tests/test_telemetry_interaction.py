"""Altered actual telemetry constituents cannot substitute for local evidence."""

import hashlib
import json
from pathlib import Path

import pytest
from quality_harness.interaction_coverage import interaction_coverage

FIXTURES = json.loads(
    Path(__file__).with_name("telemetry_observations.json").read_text()
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
BACKEND = [
    "dirty_site",
    "changed_site",
    "wrong_digest",
    "prior_report",
    "bad_return",
    "timeout",
    "unavailable",
    "wrong_command",
    "foreign_report",
    "changed_report",
    "missing_case",
    "duplicate_case",
    "renamed_case",
    "failed_case",
    "pending_case",
    "wrong_total",
    "false_success",
]
LOCAL = [
    "dirty_site",
    "changed_site",
    "wrong_digest",
    "prior_client",
    "foreign_endpoint",
    "prior_events",
    "missing_worker",
    "changed_worker",
    "wrong_worker_code",
    "consent_leak",
    "false_denial",
    "duplicate_client",
    "wrong_owner",
    "unchanged_last_seen",
    "changed_first_launch",
    "duplicate_update",
    "missing_payload",
    "duplicate_payload",
    "extra_stored",
    "private_canary",
    "wrong_failure",
    "wrong_timestamp",
    "wrong_install",
    "false_withdrawal",
    "withdrawal_write",
    "missing_ownership",
    "ownership_accepted_foreign",
    "legacy_write",
    "worker_survived",
    "changed_receipt",
] + [f"stored_dimensions:{i}" for i in range(395)]
ISOLATION = [
    "guard_missing",
    "enabled_parent",
    "parent_attempt",
    "changed_parent",
    "bad_return",
    "timeout",
    "unavailable",
    "command_changed",
    "missing_call",
    "wrong_host",
    "wrong_interval",
    "missing_exception",
    "wrong_count",
    "safe_refused",
    "changed_control",
]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, a):
    p.write_text(json.dumps(a, indent=2) + "\n")
    return {"path": str(p), "sha256": sha(p)}


def controls(s):
    return COMMON + (
        BACKEND if "backend" in s["id"] else LOCAL if "local" in s["id"] else ISOLATION
    )


def materialize(tmp_path, f):
    tmp_path.mkdir(parents=True, exist_ok=True)
    a = json.loads(json.dumps(f["raw"]).replace(f["old_root"], str(tmp_path)))
    for rel, text in f["constituents"].items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text.replace(f["old_root"], str(tmp_path)))

    def rebind(v):
        if isinstance(v, dict):
            if (
                isinstance(v.get("path"), str)
                and isinstance(v.get("sha256"), str)
                and Path(v["path"]).is_file()
            ):
                p = Path(v["path"])
                v.update(sha256=sha(p), size_bytes=p.stat().st_size)
            for x in v.values():
                rebind(x)
        elif isinstance(v, list):
            for x in v:
                rebind(x)

    rebind(a)
    root = tmp_path / f["folder"]
    root.mkdir(parents=True, exist_ok=True)
    ref = save(root / "observation.json", a)
    return (
        dict(f["scenario"], raw_result=ref["path"], raw_result_sha256=ref["sha256"]),
        a,
        root,
    )


def edit_constituent(a, ref, transform):
    p = Path(ref["path"])
    old = dict(ref)
    v = json.loads(p.read_text())
    transform(v)
    save(p, v)
    new = {**ref, "sha256": sha(p), "size_bytes": p.stat().st_size}

    def visit(x):
        if isinstance(x, dict):
            if x == old:
                x.update(new)
            for v in x.values():
                visit(v)
        elif isinstance(x, list):
            for v in x:
                visit(v)

    visit(a)


def mutate(s, a, name, root):
    if name == "foreign_identity":
        a["scenario_id"] = "other"
    elif name == "foreign_contract":
        a["contract"] = "other"
    elif name == "false_scope":
        a["scope"] = "production native acceptance"
    elif name == "missing_trace":
        del a["trace"]
    elif name == "reversed_trace":
        a["trace"].reverse()
    elif name == "missing_clock":
        del a["trace"][0]["elapsed_seconds"]
    elif name == "foreign_raw_hash":
        pass
    elif "backend" in s["id"]:
        b, d, e = a["trace"]
        if name == "dirty_site":
            b["site"]["status_porcelain"] = [" M secret"]
        elif name == "changed_site":
            e["site"]["commit"] = "0" * 40
        elif name == "wrong_digest":
            b["site"]["source_manifest_sha256"] = "0" * 64
        elif name == "prior_report":
            b["report"]["exists"] = True
        elif name == "bad_return":
            d["result"]["returncode"] = 1
        elif name == "timeout":
            d["result"]["timed_out"] = True
        elif name == "unavailable":
            d["result"]["unavailable"] = True
        elif name == "wrong_command":
            d["result"]["command"][1] = "build"
        elif name == "foreign_report":
            a["test_report"]["path"] = "/foreign/report.json"
        elif name == "changed_report":
            a["test_report"]["sha256"] = "0" * 64
        else:

            def change(v):
                cases = v["testResults"][0]["assertionResults"]
                if name == "missing_case":
                    cases.pop()
                elif name == "duplicate_case":
                    cases[-1] = cases[0]
                elif name == "renamed_case":
                    cases[0]["fullName"] = "foreign"
                elif name == "failed_case":
                    cases[0]["status"] = "failed"
                elif name == "pending_case":
                    cases[0]["status"] = "pending"
                elif name == "wrong_total":
                    v["numTotalTests"] -= 1
                elif name == "false_success":
                    v["success"] = False

            edit_constituent(a, a["test_report"], change)
    elif "local" in s["id"]:
        b, ready, denied, launch, reopen, d, withdrawn, owned, e = a["trace"]
        if name == "dirty_site":
            b["site"]["status_porcelain"] = [" M secret"]
        elif name == "changed_site":
            e["site"]["commit"] = "0" * 40
        elif name == "wrong_digest":
            b["site"]["source_manifest_sha256"] = "0" * 64
        elif name == "prior_client":
            b["client_exists"] = True
        elif name == "foreign_endpoint":
            ready["endpoint"] = "https://getvodforge.com/"
        elif name == "prior_events":
            ready["snapshot"]["events"] = [{"event_name": "old"}]
        elif name == "missing_worker":
            ready["failure_workers"].pop()
        elif name == "changed_worker":
            ready["failure_workers"][0]["worker"]["sha256"] = "0" * 64
        elif name == "wrong_worker_code":
            ready["failure_workers"][0]["diagnostic"]["http_status"] = 500
        elif name == "consent_leak":
            denied["snapshot"]["events"] = [{"event_name": "leak"}]
        elif name == "false_denial":
            denied["refused_launch"] = True
        elif name == "duplicate_client":
            launch["snapshot"]["clients"] *= 2
        elif name == "wrong_owner":
            reopen["snapshot"]["clients"][0]["credential_id"] = "other"
        elif name == "unchanged_last_seen":
            reopen["snapshot"]["installations"][0]["last_seen_at"] = launch["snapshot"][
                "installations"
            ][0]["last_seen_at"]
        elif name == "changed_first_launch":
            reopen["snapshot"]["installations"][0]["first_launched_at"] = "other"
        elif name == "duplicate_update":
            reopen["snapshot"]["events"] *= 2
        elif name == "missing_payload":
            d["delivered"].pop()
        elif name == "duplicate_payload":
            d["delivered"][-1] = d["delivered"][0]
        elif name == "extra_stored":
            d["snapshot"]["events"].append(
                dict(d["snapshot"]["events"][0], event_id="other")
            )
        elif name == "private_canary":
            d["delivered"][0]["dimensions"]["note"] = "PRIVATE note"
        elif name == "wrong_failure":
            next(v for v in d["delivered"] if v["event_name"] == "run_failed")[
                "failure_detail"
            ]["http_status"] = 403
        elif name == "wrong_timestamp":
            d["delivered"][0]["occurred_at"] = "2000-01-01T00:00:00+00:00"
        elif name == "wrong_install":
            d["delivered"][0]["install_id"] = "other"
        elif name == "false_withdrawal":
            withdrawn["event"] = True
        elif name == "withdrawal_write":
            withdrawn["snapshot"]["events"].pop()
        elif name == "missing_ownership":
            owned["cases"].pop()
        elif name == "ownership_accepted_foreign":
            owned["cases"][0]["statuses"][2] = 200
        elif name == "legacy_write":
            owned["cases"][0]["legacy"]["accepted"] = 1
        elif name == "worker_survived":
            e["returncode"] = None
        elif name == "changed_receipt":
            edit_constituent(a, a["receipt"], lambda v: v["events"].pop())
        elif name.startswith("stored_dimensions:"):
            i = int(name.split(":")[1])
            payload = d["delivered"][i]
            stored = next(
                v
                for v in d["snapshot"]["events"]
                if v["event_id"] == payload["event_id"]
            )
            stored["dimensions"] = '{"foreign":"yes"}'
    else:
        b, d, e = a["trace"]
        if name == "guard_missing":
            b["guard_installed"] = False
        elif name == "enabled_parent":
            b["disabled"] = "0"
        elif name == "parent_attempt":
            b["parent_attempts"] = ["production_telemetry_attempt"]
        elif name == "changed_parent":
            e["parent_attempts"] = ["production_telemetry_attempt"]
        elif name == "bad_return":
            d["command_result"]["returncode"] = 1
        elif name == "timeout":
            d["command_result"]["timed_out"] = True
        elif name == "unavailable":
            d["command_result"]["unavailable"] = True
        elif name == "command_changed":
            d["command_result"]["command"][1] = "other"
        elif name == "changed_control":
            a["control"]["sha256"] = "0" * 64
        else:

            def change(v):
                x = json.loads(v["stdout"])
                calls = x["rows"]
                if name == "missing_call":
                    calls.pop()
                elif name == "wrong_host":
                    calls[0]["host"] = "example.invalid"
                elif name == "wrong_interval":
                    calls[0]["returned"] = calls[0]["entered"] - 1
                elif name == "missing_exception":
                    calls[0]["exception_type"] = None
                elif name == "wrong_count":
                    calls[0]["after"] = []
                elif name == "safe_refused":
                    calls[4]["exception_type"] = "RuntimeError"
                v["stdout"] = json.dumps(x) + "\n"
                d["command_result"] = v

            edit_constituent(a, a["control"], change)


@pytest.mark.parametrize("i", range(len(FIXTURES)))
def test_actual_telemetry_shapes_qualify(tmp_path, i):
    s, _, _ = materialize(tmp_path, FIXTURES[i])
    q = interaction_coverage(s)
    assert q["status"] == "passed", q
    assert q["usability_review"]["status"] == "not_applicable"


@pytest.mark.parametrize(
    "i,name", [(i, n) for i, f in enumerate(FIXTURES) for n in controls(f["scenario"])]
)
def test_altered_telemetry_cannot_qualify(tmp_path, i, name):
    s, a, root = materialize(tmp_path, FIXTURES[i])
    mutate(s, a, name, root)
    ref = save(root / "mutation.json", a)
    s.update(
        raw_result=ref["path"],
        raw_result_sha256="0" * 64 if name == "foreign_raw_hash" else ref["sha256"],
    )
    q = interaction_coverage(s)
    assert q["status"] in {"failed", "unproven"}, q
